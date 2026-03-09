import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from datetime import datetime
from Inventory.routes.notifications import emit_event
from .stock_issue_summary import submit_stock_issue

@inventory_bp.route("/SDK/stock_issue_wizard", methods=["GET"])
@login_required
def stock_issue_wizard():
    # permission check (optional)
    if "STOCK_ISSUE" in current_user.permissions:
        return render_template('EvolutionSDK/stock_issue.html')
    else:
        abort(403)


# -------------------------
# Create stock issue (fixed SQL inserts, SCOPE_IDENTITY usage)
# -------------------------
@inventory_bp.route("/SDK/create_stock_issue", methods=["POST"])
@login_required
def create_stock_issue():
    if "STOCK_ISSUE" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    warehouse_id = data.get("warehouse")
    # try: 
    order_final = data.get("order_final", False)
    created_at = data.get("created_at", datetime.now().isoformat())
    lines_payload = data.get("lines", [])
    submission_lines = []

    if not warehouse_id or not lines_payload:
        return jsonify({"status": "error", "message": "Missing required data"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO [stk].IssueHeader( 
    IssueWhseId, IssueByUserId, [IssueTimeStamp])
    OUTPUT INSERTED.IssueId 
    VALUES (?, ?, ?) """, 
    (warehouse_id, current_user.id, created_at))

    stock_issue_id = cursor.fetchone()[0]

    # If order is final, mark header final now
    if order_final:
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssueFinalised = 1, IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
            WHERE IssueId = ?
        """, (current_user.id, stock_issue_id))

    # Insert each line (six columns -> six placeholders)
    for line in lines_payload:
        print(line)
        cursor.execute("""
            INSERT INTO [stk].IssueLines(
                IssLineHeaderId, [IssLineProjectId], IssLineStockLink, IssLineStockCode, IssLineQtyIssued, IssLineUOMId, IssLineUOMCode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_issue_id,
            line.get("project"),
            line.get("product_link"),
            line.get("product_code"),
            line.get("qty_to_issue"),
            line.get("uom_id"),
            line.get("uom_code"),
        ))
        # If final, set IssLineQtyFinalised for that newly-inserted line
        if order_final:
            cursor.execute("SELECT MAX(IssLineId) FROM [stk].IssueLines")
            last_line_id = cursor.fetchone()[0]
            cursor.execute("""
                UPDATE [stk].IssueLines
                SET IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_to_issue"), last_line_id))
            submission_line = {
                "line_id": last_line_id,
                "project": line.get("project"),
                "product_link": line.get("product_link"),
                "finalised_qty": line.get("qty_to_issue")
            }
            submission_lines.append(submission_line)

    # If order_final we can attempt to submit to Evolution in the background call;
    # keep it synchronous here for simplicity. If submit_stock_issue raises, log it but do not fail DB insert.
    if order_final:
        try:
            order_number = submit_stock_issue(warehouse_id, submission_lines)
            print(order_number,stock_issue_id)
            cursor.execute("""
                UPDATE [stk].IssueHeader
                SET IssueInvoiceNo = ?
                WHERE IssueId = ?
            """, (order_number, stock_issue_id))
            emit_event(
                event_code="STOCK_ISSUE",
                entity_id=stock_issue_id,
                entity_desc=order_number,
            )
            conn.commit()
        except Exception as ex:
            conn.rollback()
            return jsonify({
                "status": "error",
                "message": str(ex)
            }), 400

    cursor.execute("""
    Select IssLineId, IssLineStockLink from [stk].[IssueLines]
    Where IssLineHeaderId = ?
    """, (stock_issue_id,))
    issue_lines = cursor.fetchall()
    conn.commit()
    return jsonify({"status": "success", "message": "Stock issue created.", "issue_id": stock_issue_id, 
        "issue_lines": [{"issue_line_id": issue_line[0], "issue_product_link": issue_line[1]} for issue_line in issue_lines]}), 200

    # except Exception as ex:
    #     conn.rollback()
    #     print("Stock Issue Error:", str(ex))
    #     return jsonify({"status": "error", "message": "Stock Issue Error: " + str(ex)}), 500
    # finally:
    if conn:
        conn.close()

@inventory_bp.route("/SDK/fetch_products_in_warehouse", methods=["GET"])
def fetch_products_in_warehouse():

    whse_id = request.args.get("warehouse_id")
    if not whse_id:
        return jsonify({"status": "error", "message": "Warehouse ID is required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT StockLink, StockCode, StockDescription,
        WhseLink, WhseCode, WhseName, QtyOnHand
        ,StockingUnitId, StockingUnitCode
        ,PurchaseUnitId, PurchaseUnitCode
        ,PurchaseUnitCatId
        FROM [stk]._uvInventoryQty
        Where WhseLink = ? AND QtyOnHand > 0
    """, (whse_id,))
    rows = cursor.fetchall()
    conn.close()
    products_list = [
        {
            "product_link": row.StockLink,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "WhseLink": row.WhseLink,
            "WhseCode": row.WhseCode,
            "WhseName": row.WhseName,
            "qty_in_whse": row.QtyOnHand,
            "stocking_uom_id": row.StockingUnitId,
            "stocking_uom_code": row.StockingUnitCode
        }
        for row in rows
    ]
    return jsonify({"products": products_list})