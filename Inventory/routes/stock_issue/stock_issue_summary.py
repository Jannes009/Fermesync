import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from datetime import datetime
from Inventory.routes.notifications import emit_event

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route("/SDK/stock_issue_summary", methods=["GET"])
@login_required
def stock_issue_summary():
    # permission check (optional)
    if "STOCK_ISSUE" in current_user.permissions:
        return render_template('EvolutionSDK/stock_issue_summary.html')
    else:
        abort(403)

def submit_stock_issue(warehouse_id, lines):
    description = f"Stock Issue from warehouse {warehouse_id}"
    try:
        with EvolutionConnection():
            SO = Evo.SalesOrder()
            SO.Customer = Evo.Customer("ZZZ001")
            SO.Description = description

            conn = create_db_connection()
            cursor = conn.cursor()

            for line in lines:
                OD = Evo.OrderDetail()
                SO.Detail.Add(OD)

                stock_code = stock_link_to_code(line["product_link"], cursor)
                OD.InventoryItem = Evo.InventoryItem(stock_code)
                OD.Quantity = float(line.get("finalised_qty") or 0)
                OD.Warehouse = Evo.Warehouse(int(warehouse_id))
                OD.Project = Evo.Project(int(line.get("project")))

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
        cursor.execute("Select IssueFinalised from [stk].IssueHeader where IssueId = ?", (issue_id,))
        order_finalised = int(cursor.fetchone()[0]) > 0
        if order_finalised:
            return jsonify({"success": False, "message": "This issue was already finalised. Please refresh page."})
        
        cursor.execute("""
            Update [stk].IssueHeader
            SET IssueFinalised = 1, 
                IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = ?
            WHERE IssueId = ?
        """, (current_user.id, created_at, issue_id))
        for line in lines:
            qty_finalised = line.get("qty_issued") - line.get("qty_returned")
            if qty_finalised > 0:
                containsQty = True
            # fetch stock link for submission
            cursor.execute("""
                Select IssLineStockLink, IssLineProjectId
                from [stk].IssueLines
                where IssLineId = ?
            """, (line.get("line_id"),))
            stock_link_row = cursor.fetchone()
            if not stock_link_row:
                raise Exception(f"No stock link found for line {line.get('line_id')}")

            stock_link = stock_link_row[0]
            project_id = stock_link_row[1]

            submission_lines.append({
                "line_id": line.get("line_id"),
                "product_link": stock_link,
                "project": project_id,
                "finalised_qty": qty_finalised
            })

            cursor.execute("""
                UPDATE [stk].IssueLines
                SET IssLineQtyReceived = ?, IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_returned"), qty_finalised, line.get("line_id")))
        # get Issue details
        cursor.execute("""
            Select IssueWhseId, IssueReturnedToName, IssueToName
            from [stk].IssueHeader
            where IssueId = ?
        """, (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            raise Exception(f"Issue {issue_id} not found.")

        if containsQty:
            order_number = submit_stock_issue(issue.IssueWhseId, submission_lines)
        else:
            order_number = "No Order Created"
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssueInvoiceNo = ?
            WHERE IssueId = ?
        """, (order_number, issue_id))

        conn.commit()

        emit_event(
            event_code="STOCK_ISSUE",
            entity_id=issue_id,
            entity_desc=order_number,
        )
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
