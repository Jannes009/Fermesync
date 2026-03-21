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

    
    order_final = data.get("order_final", False)
    created_at = data.get("created_at", datetime.now().isoformat())
    lines_payload = data.get("lines", [])
    
    issue_mode = data.get("issue_mode", "project")  # "project" or "spray"
    

    if issue_mode not in ["project", "spray"]:
        return jsonify({"status": "error", "message": "Invalid issue mode"}), 400
    elif issue_mode == "project":
        project_id = data.get("project")
        if not project_id:
            return jsonify({"status": "error", "message": "Project ID required for project mode"}), 400
        warehouse_id = data.get("warehouse")
        if not warehouse_id or not lines_payload:
            return jsonify({"status": "error", "message": "Missing required data"}), 400

        return generate_stock_issue_for_project(project_id, warehouse_id, lines_payload, order_final, created_at)
    elif issue_mode == "spray":
        spray_id = data.get("spray_id")    
        if not spray_id:
            return jsonify({"status": "error", "message": "Spray ID required for spray mode"}), 400
        return generate_stock_issue_for_spray(spray_id, lines_payload, order_final, created_at)


def generate_stock_issue_for_project(project_id, warehouse_id, lines_payload, order_final, created_at):
    submission_lines = []
    conn = create_db_connection()
    cursor = conn.cursor()

    # Create issue header (schema may not have project/spray columns yet)
    cursor.execute("""
    INSERT INTO [stk].IssueHeader( 
    IssueWhseId, IssueByUserId, [IssueTimeStamp])
    OUTPUT INSERTED.IdIssue 
    VALUES (?, ?, ?) """, 
    (warehouse_id, current_user.id, created_at))

    stock_issue_id = cursor.fetchone()[0]
    issue_no = f"ISS-{int(stock_issue_id):03d}"
    try:
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssNo = ?
            WHERE IdIssue = ?
        """, (issue_no, stock_issue_id))
    except Exception as e:
        print("Failed to set issue number, continuing with blank IssNo", e)

    # If order is final, mark header final now
    if order_final:
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssueFinalised = 1, IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
            WHERE IdIssue = ?
        """, (current_user.id, stock_issue_id))

    # Insert each line
    for line in lines_payload:       
        cursor.execute("""
            INSERT INTO [stk].IssueLines(
                IssLineHeaderId, IssLineProjectId, IssLineStockLink, IssLineStockCode, IssLineQtyIssued, IssLineUOMId, IssLineUOMCode
            )
            OUTPUT INSERTED.IssLineId
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_issue_id,
            project_id,
            line.get("product_link"),
            line.get("product_code"),
            line.get("qty_to_issue"),
            line.get("uom_id"),
            line.get("uom_code"),
        ))
        last_line_id = cursor.fetchone()[0]
        # If final, set IssLineQtyFinalised for that newly-inserted line
        if order_final:          
            cursor.execute("""
                UPDATE [stk].IssueLines
                SET IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_to_issue"), last_line_id))
            submission_line = {
                "line_id": last_line_id,
                "project": project_id,
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
    return jsonify({
        "status": "success", 
        "message": "Stock issue created.", 
        "issue_id": stock_issue_id, 
        "issue_no": issue_no,
        "project_id": project_id,
        "issue_lines": [{"issue_line_id": issue_line[0], "issue_product_link": issue_line[1]} for issue_line in issue_lines]
    }), 200

def generate_stock_issue_for_spray(spray_id, lines_payload, order_final, created_at):
    submission_lines = []
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("Select SprayHWhseId from [agr].[SprayHeader] Where IdSprayH = ?", (spray_id,))
    warehouse_id = cursor.fetchone()[0]


    # Create issue header (schema may not have project/spray columns yet)
    cursor.execute("""
    INSERT INTO [stk].IssueHeader( 
    IssWhseId, IssByUserId, [IssTimeStamp], IssSprayId)
    OUTPUT INSERTED.IdIssue 
    VALUES (?,?, ?, ?) """, 
    (warehouse_id, current_user.id, created_at, spray_id))

    stock_issue_id = cursor.fetchone()[0]
    issue_no = f"ISS-{int(stock_issue_id):03d}"
    try:
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssNo = ?
            WHERE IdIssue = ?
        """, (issue_no, stock_issue_id))
    except Exception as e:
        print("Failed to set issue number, continuing with blank IssNo", e)

    # If order is final, mark header final now
    if order_final:
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssueFinalised = 1, IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
            WHERE IssueId = ?
        """, (current_user.id, stock_issue_id))

    cursor.execute("""
        Select SprayPProjectId,SprayPHa, SprayPWaterPerHa
        from [agr].[SprayProjects]
        Where SprayPSprayId = ?
    """, (spray_id,))
    spray_project_rows = cursor.fetchall()

    # Determine spray type
    cursor.execute("""
        SELECT SprayHApplicationType
        FROM [agr].[SprayHeader]
        WHERE IdSprayH = ?
    """, (spray_id,))
    spray_type = cursor.fetchone()[0]

    projects = []
    total_weight = 0

    for row in spray_project_rows:
        ha = float(row.SprayPHa or 0)
        water_per_ha = float(row.SprayPWaterPerHa or 0)

        if spray_type == "direct":
            weight = ha
        else:  # "spray"
            weight = ha * water_per_ha

        projects.append({
            "project_id": row.SprayPProjectId,  # <-- make sure you SELECT this!
            "weight": weight
        })

        total_weight += weight

    # Insert each line
    for line in lines_payload:
        total_qty = float(line.get("qty_to_issue") or 0)

        for proj in projects:
            if total_weight == 0:
                project_qty = 0
            else:
                project_qty = (proj["weight"] / total_weight) * total_qty

            project_id = proj["project_id"]

            cursor.execute("""
                INSERT INTO [stk].IssueLines(
                    IssLineIssueId, IssLineProjectId, IssLineStockLink, 
                    IssLineQtyIssued, IssLineUOMId
                )
                OUTPUT INSERTED.IdIssLine
                VALUES (?, ?, ?, ?, ?)
            """, (
                stock_issue_id,
                project_id,
                line.get("product_link"),
                project_qty,
                line.get("uom_id"),
            ))
            last_line_id = cursor.fetchone()[0]
            if order_final:          
                cursor.execute("""
                    UPDATE [stk].IssueLines
                    SET IssLineQtyFinalised = ?
                    WHERE IssLineId = ?
                """, (project_qty, last_line_id))
                submission_line = {
                    "line_id": last_line_id,
                    "project": project_id,
                    "product_link": line.get("product_link"),
                    "finalised_qty": project_qty
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
    Select IdIssLine, IssLineStockLink from [stk].[IssueLines]
    Where IssLineIssueId = ?
    """, (stock_issue_id,))
    issue_lines = cursor.fetchall()
    conn.commit()
    return jsonify({
        "status": "success", 
        "message": "Stock issue created.", 
        "issue_id": stock_issue_id,
        "issue_no": issue_no,
        "issue_lines": [{"issue_line_id": issue_line[0], "issue_product_link": issue_line[1]} for issue_line in issue_lines]
    }), 200

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

