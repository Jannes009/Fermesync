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


@inventory_bp.route("/SDK/incomplete_issues", methods=["GET"])
def incomplete_issues():
    conn = create_db_connection()
    cur = conn.cursor()

    sql = """
    Select IdIssue, IssNo, HEA.IssWhseId, WHSE.WhseDescription, HEA.IssTimeStamp
    from stk.IssueHeader HEA
    JOIN cmn._uvWarehouses WHSE on WHSE.WhseLink = HEA.IssWhseId
    WHERE HEA.IssFinalised = 0
    """

    cur.execute(sql)
    rows = cur.fetchall()

    # build grouped structure: one issue → many lines
    issues = [{
        "IssueId": r.IdIssue,
        "IssueNo": r.IssNo,
        "IssueTimeStamp": r.IssTimeStamp,
        "WhseId": r.IssWhseId,
        "WhseDescription": r.WhseDescription,
        "isReturned": False,
        "lines": []
    } for r in rows
    ]

    return jsonify({"issues": issues})


@inventory_bp.route("/SDK/incomplete_issue_lines/<int:header_id>", methods=["GET"])
def incomplete_issue_lines(header_id):
    if "STOCK_ISSUE" not in current_user.permissions:
        abort(403)  # Forbidden

    results = []
    conn = None
    cursor = None
    try:
        conn = create_db_connection()
        if conn is None:
            return jsonify([]), 500

        cursor = conn.cursor()
        cursor.execute("""  
        Select IdIssue, IssLineStockLink, QTY.StockDescription,SUM(LIN.IssLineQtyIssued) QtyIssued
        ,LIN.IssLineUoMId, UOM.cUnitCode
        from stk.IssueHeader HEA
        JOIN stk.IssueLines LIN on LIN.IssLineIssueId = HEA.IdIssue
        JOIN stk._uvInventoryQty QTY on QTY.StockLink = LIN.IssLineStockLink
        JOIN cmn._uvUOM UOM on UOM.idUnits = LIN.IssLineUoMId
        Where HEA.IdIssue = ?
        GROUP BY IssLineStockLink, IdIssue, StockDescription, IssLineUoMId, cUnitCode
        """, (header_id,))

        rows = cursor.fetchall()
        results = [{
            "header_id": r.IdIssue,
            "product_link": r.IssLineStockLink,
            "product_desc": r.StockDescription,
            "uom_id": r.IssLineUoMId,
            "uom_code": r.cUnitCode,
            "qty_issued": r.QtyIssued
        } for r in rows]
    except Exception as e:
        print("fetch_products_for_return error:", e)
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

    # return {"issue_lines": results}
    return jsonify({"issue_lines": results})

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
        cursor.execute("Select IssFinalised from [stk].IssueHeader where IdIssue = ?", (issue_id,))
        order_finalised = int(cursor.fetchone()[0]) > 0
        if order_finalised:
            return jsonify({"success": False, "message": "This issue was already finalised. Please refresh page."})
        
        cursor.execute("""
            Update [stk].IssueHeader
            SET IssFinalised = 1, 
                IssFinalisedByUserId = ?, IssFinalisedTimeStamp = ?
            WHERE IdIssue = ?
        """, (current_user.id, created_at, issue_id))
        for line in lines:
            qty_returned = line.get("qty_returned")
            product_link = line.get("product_link")
            
            # Find all IssueLines for this stock_link and this issue
            cursor.execute("""
                Select IdIssLine, IssLineProjectId, IssLineQtyIssued
                from [stk].IssueLines
                where IssLineIssueId = ? AND IssLineStockLink = ?
            """, (issue_id, product_link))
            
            issue_lines = cursor.fetchall()
            if not issue_lines:
                raise Exception(f"No stock lines found for product {product_link}")
            
            # Calculate total issued for this product across all projects
            total_issued = sum(row[2] for row in issue_lines)
            
            # Distribute return proportionally by project
            for issue_line in issue_lines:
                line_id = issue_line[0]
                project_id = issue_line[1]
                qty_issued_for_project = issue_line[2]
                
                # Proportion of this project's issue
                proportion = qty_issued_for_project / total_issued
                qty_returned_for_project = qty_returned * proportion
                qty_finalised = qty_issued_for_project - qty_returned_for_project
                
                if qty_finalised > 0:
                    containsQty = True
                
                submission_lines.append({
                    "line_id": line_id,
                    "product_link": product_link,
                    "project": project_id,
                    "finalised_qty": qty_finalised
                })
                
                # Update this line with proportional quantities
                cursor.execute("""
                    UPDATE [stk].IssueLines
                    SET IssLineQtyReceived = ?, IssLineQtyFinalised = ?
                    WHERE IdIssLine = ?
                """, (qty_returned_for_project, qty_finalised, line_id))
        # get Issue details
        cursor.execute("""
            Select IssWhseId, IssToName
            from [stk].IssueHeader
            where IdIssue = ?
        """, (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            raise Exception(f"Issue {issue_id} not found.")

        if containsQty:
            order_number = submit_stock_issue(issue.IssWhseId, submission_lines)
        else:
            order_number = "No Order Created"
        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssInvoiceNo = ?
            WHERE IdIssue = ?
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
