import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required, current_user
from auth import get_common_db_connection, close_connection
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from datetime import datetime

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route("/SDK/stock_issue", methods=["GET"])
@login_required
def stock_issue():
    # permission check (optional)
    if "StockIssue" in current_user.permissions:
        return render_template('EvolutionSDK/stock_issue.html')
    else:
        abort(403)

# -------------------------
# Create stock issue (fixed SQL inserts, SCOPE_IDENTITY usage)
# -------------------------
@inventory_bp.route("/SDK/create_stock_issue", methods=["POST"])
@login_required
def create_stock_issue():
    if "StockIssue" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    warehouse_code = data.get("warehouse")
    try: 
        project_code = data.get("project")
        issued_to = data.get("issued_to")
        order_final = data.get("order_final", False)
        created_at = data.get("created_at", datetime.now().isoformat())
        lines_payload = data.get("lines", [])
        submission_lines = []

        if not warehouse_code or not project_code or not issued_to or not lines_payload:
            return jsonify({"status": "error", "message": "Missing required data"}), 400

        conn = create_db_connection()
        cursor = conn.cursor()
        whse_link = warehouse_code_to_link(warehouse_code, cursor)
        project_link = project_code_to_link(project_code, cursor)

        cursor.execute("""
        INSERT INTO IssueHeader( 
        IssueWhseId, IssueProjectId, IssueByUserId, IssueToName, [IssueTimeStamp])
        OUTPUT INSERTED.IssueId 
        VALUES (?, ?, ?, ?, ?) """, 
        (whse_link, project_link, current_user.id, issued_to, created_at))

        stock_issue_id = cursor.fetchone()[0]

        # If order is final, mark header final now
        if order_final:
            cursor.execute("""
                UPDATE IssueHeader
                SET IssueFinalised = 1, IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
                WHERE IssueId = ?
            """, (current_user.id, stock_issue_id))

        # Insert each line (six columns -> six placeholders)
        for line in lines_payload:
            print(line)
            cursor.execute("""
                INSERT INTO IssueLines(
                    IssLineHeaderId, IssLineStockLink, IssLineStockCode, IssLineQtyIssued, IssLineUOMId, IssLineUOMCode
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                stock_issue_id,
                line.get("product_link"),
                line.get("product_code"),
                line.get("qty_to_issue"),
                line.get("uom_id"),
                line.get("uom_code"),
            ))
            # If final, set IssLineQtyFinalised for that newly-inserted line
            if order_final:
                cursor.execute("SELECT MAX(IssLineId) FROM IssueLines")
                last_line_id = cursor.fetchone()[0]
                cursor.execute("""
                    UPDATE IssueLines
                    SET IssLineQtyFinalised = ?
                    WHERE IssLineId = ?
                """, (line.get("qty_to_issue"), last_line_id))
                submission_line = {
                    "line_id": last_line_id,
                    "product_link": line.get("product_link"),
                    "finalised_qty": line.get("qty_to_issue")
                }
                submission_lines.append(submission_line)

        # If order_final we can attempt to submit to Evolution in the background call;
        # keep it synchronous here for simplicity. If submit_stock_issue raises, log it but do not fail DB insert.
        if order_final:
            try:
                order_number = submit_stock_issue(warehouse_code, project_code, submission_lines, issued_to)
                print(order_number,stock_issue_id)
                cursor.execute("""
                    UPDATE IssueHeader
                    SET IssueInvoiceNo = ?
                    WHERE IssueId = ?
                """, (order_number, stock_issue_id))
                conn.commit()
            except Exception as ex:
                conn.rollback()
                return jsonify({
                    "status": "error",
                    "message": str(ex)
                }), 400

        complete_stock_issue(stock_issue_id, complete=order_final)
        cursor.execute("""
        Select IssLineId, IssLineStockLink from [dbo].[IssueLines]
        Where IssLineHeaderId = ?
        """, (stock_issue_id,))
        issue_lines = cursor.fetchall()
        conn.commit()
        return jsonify({"status": "success", "message": "Stock issue created.", "issue_id": stock_issue_id, 
            "issue_lines": [{"issue_line_id": issue_line[0], "issue_product_link": issue_line[1]} for issue_line in issue_lines]}), 200

    except Exception as ex:
        conn.rollback()
        print("Stock Issue Error:", str(ex))
        return jsonify({"status": "error", "message": "Stock Issue Error: " + str(ex)}), 500
    finally:
        if conn:
            conn.close()


def submit_stock_issue(warehouse_code, project_code, lines, issued_to, returned_to=None):
    description = f"{issued_to}, {returned_to}" if returned_to else f"{issued_to}"
    try:
        with EvolutionConnection():
            SO = Evo.SalesOrder()
            SO.Customer = Evo.Customer("ZZZ001")
            SO.Project = Evo.Project(project_code)
            SO.Description = description

            conn = create_db_connection()
            cursor = conn.cursor()

            for line in lines:
                OD = Evo.OrderDetail()
                SO.Detail.Add(OD)

                stock_code = stock_link_to_code(line["product_link"], cursor)
                OD.InventoryItem = Evo.InventoryItem(stock_code)
                OD.Quantity = float(line.get("finalised_qty") or 0)
                OD.Warehouse = Evo.Warehouse(warehouse_code)

            SO.Complete()
            return SO.OrderNo
    except Exception as ex:
        print("Stock Issue Submission Error:", str(ex))
        raise ex

@inventory_bp.route("/process_return", methods=["POST"])
@login_required
def process_return():
    data = request.json
    issue_id = data.get("issue_id")
    returned_to = data.get("returned_to")
    created_at = data.get("created_at")
    if created_at:
        created_at = datetime.fromisoformat(created_at.replace("Z", ""))
    else:
        print("No created_at provided, using current time.")
        created_at = datetime.now()
    lines = data.get("returns") or []
    submission_lines = []
    containsQty = False

    conn = None
    cursor = None
    try:
        conn = create_db_connection()
        if conn is None:
            return jsonify({"success": False, "message": "Database connection could not be established."}), 500

        cursor = conn.cursor()

        # check if issue was already processed
        cursor.execute("Select IssueFinalised from IssueHeader where IssueId = ?", (issue_id,))
        order_finalised = int(cursor.fetchone()[0]) > 0
        if order_finalised:
            return jsonify({"success": False, "message": "This issue was already finalised. Please refresh page."})
        
        cursor.execute("""
            Update IssueHeader
            SET IssueReturnedToName = ?, IssueFinalised = 1, 
                IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = ?
            WHERE IssueId = ?
        """, (returned_to, current_user.id, created_at, issue_id))
        for line in lines:
            qty_finalised = line.get("qty_issued") - line.get("qty_returned")
            if qty_finalised > 0:
                containsQty = True
            # fetch stock link for submission
            cursor.execute("""
                Select IssLineStockLink
                from IssueLines
                where IssLineId = ?
            """, (line.get("line_id"),))
            stock_link_row = cursor.fetchone()
            if not stock_link_row:
                raise Exception(f"No stock link found for line {line.get('line_id')}")

            stock_link = stock_link_row[0]

            submission_lines.append({
                "line_id": line.get("line_id"),
                "product_link": stock_link,
                "finalised_qty": qty_finalised
            })

            cursor.execute("""
                UPDATE IssueLines
                SET IssLineQtyReceived = ?, IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_returned"), qty_finalised, line.get("line_id")))
        # get Issue details
        cursor.execute("""
            Select IssueWhseId, IssueProjectId, IssueReturnedToName, IssueToName
            from IssueHeader
            where IssueId = ?
        """, (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            raise Exception(f"Issue {issue_id} not found.")

        if containsQty:
            order_number = submit_stock_issue(issue.IssueWhseId, issue.IssueProjectId, submission_lines, issue.IssueToName, issue.IssueReturnedToName)
        else:
            order_number = "No Order Created"
        cursor.execute("""
            UPDATE IssueHeader
            SET IssueInvoiceNo = ?
            WHERE IssueId = ?
        """, (order_number, issue_id))

        conn.commit()

        complete_stock_issue(issue_id, complete=True)
        print("Return processed, order number:", order_number)
        return jsonify({"success": True, "order_number": order_number})

    except Exception as e:
        print("process_return error:", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "message": str(e)})
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def complete_stock_issue(issue_id, complete):
    conn, cursor = get_common_db_connection()
    
    # 1. Find users who want notifications, SubmitStockIssue has EventId 6
    cursor.execute("""
        SELECT UserId 
        FROM [dbo].[NotificationPreferences]
        WHERE EventId = 6
    """)
    users = cursor.fetchall()

    # 2. Determine message based on `complete`
    if complete:
        message = f"Stock issue #{issue_id} has been finalised."
    else:
        message = f"Stock issue #{issue_id} is pending returns."

    # 3. Create notification per user
    for (user_id,) in users:
        if user_id == current_user.id:
            continue  # skip notifying the current user
        cursor.execute("""
            INSERT INTO Notifications (UserID, EventCode, Title, Message, EntityID, ActionURL)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            'StockIssue',
            f'Stock issue #{issue_id} completed by {current_user.username}',
            message,  # <-- Use dynamic message here
            issue_id,
            f'/inventory/stock_issue/{issue_id}'
        ))

    conn.commit()
    close_connection(conn, cursor)
