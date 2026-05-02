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
        print(f"Fetching issue lines for header_id: {header_id}")
        cursor = conn.cursor()
        cursor.execute("""  
        Select 
            IdIssue
            ,HEA.IssSprayExecutionId
            ,IssLineStockLink
            , STK.StockDescription
            ,REC.RecQty
            , LIN.IssLineQtyIssued
            ,ISNULL(LIN.IssLineQtyReceived,0) IssLineQtyReceived
            ,ExecutionNettIssued
            ,LIN.IssLineUoMId, UOM.cUnitCode
        from stk.IssueHeader HEA
        JOIN stk.IssueLines LIN on LIN.IssLineIssueId = HEA.IdIssue
        JOIN cmn._uvStockItems STK on STK.StockLink = LIN.IssLineStockLink
        JOIN cmn._uvUOM UOM on UOM.idUnits = LIN.IssLineUoMId
        LEFT JOIN (
            Select StockId,SprayHExecutionId,SUM(TotalQty) RecQty 
            from [agr].[_uvSprayStockRequirements]
            GROUP BY StockId,SprayHExecutionId
            )REC on REC.StockId = LIN.IssLineStockLink and HEA.IssSprayExecutionId = REC.SprayHExecutionId

        LEFT JOIN(
                Select 
                    HEA.IssSprayExecutionId QTYIssSprayExecutionId
                    ,IssLineStockLink QTYIssLineStockLink
                    ,SUM( LIN.IssLineQtyIssued-ISNULL(LIN.IssLineQtyReceived,0)) ExecutionNettIssued
                from stk.IssueHeader HEA
                JOIN stk.IssueLines LIN on LIN.IssLineIssueId = HEA.IdIssue
                GROUP BY 
                    HEA.IssSprayExecutionId
                    ,IssLineStockLink
                )QTY on QTY.QTYIssSprayExecutionId = HEA.IssSprayExecutionId and QTY.QTYIssLineStockLink = LIN.IssLineStockLink
        Where HEA.IdIssue = ?
        """, (header_id,))

        rows = cursor.fetchall()
        results = [{
            "header_id": r.IdIssue,
            "product_link": r.IssLineStockLink,
            "product_desc": r.StockDescription,
            "uom_id": r.IssLineUoMId,
            "uom_code": r.cUnitCode,
            "qty_issued": r.IssLineQtyIssued,
            "qty_recommended": float(r.RecQty) if r.RecQty is not None else None,
            "nett_issued": float(r.ExecutionNettIssued) if r.ExecutionNettIssued is not None else None,
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

def submit_stock_issue(issue_id, cursor):
    cursor.execute("""
        SELECT IssWhseId
        FROM stk.IssueHeader
        WHERE IdIssue = ?
    """, (issue_id,))
    issue = cursor.fetchone()
    warehouse_id = issue.IssWhseId if issue else None

    description = f"Stock Issue from warehouse {warehouse_id}"

    try:
        with EvolutionConnection():
            SO = Evo.SalesOrder()
            SO.Customer = Evo.Customer("ZZZ001")
            SO.Description = description

            cursor.execute("""              
            Select IssLineStockLink, IssLinProjProjectId, SUM(IssLinProjWeight) as TotalWeight, IssLineQtyFinalised
            from [stk].[IssueHeader] HEA
            JOIN [stk].[IssueLines] LIN on HEA.IdIssue = LIN.IssLineIssueId
            JOIN stk.IssueLineProjects PROJ on PROJ.IssLinProjLineId = LIN.IdIssLine
            Where HEA.IdIssue = ?
            Group by IssLineStockLink, IssLinProjProjectId, IssLineQtyFinalised
            """, (issue_id,))
            lines = cursor.fetchall()

            total_finalised_qty = sum(float(line.IssLineQtyFinalised or 0) for line in lines)
            if total_finalised_qty <= 0:
                return None

            for line in lines:
                total_qty = float(line.IssLineQtyFinalised or 0)

                OD = Evo.OrderDetail()
                SO.Detail.Add(OD)

                weighted_qty = total_qty * line.TotalWeight

                OD.InventoryItem = Evo.InventoryItem(int(line.IssLineStockLink))
                OD.Quantity = weighted_qty
                OD.Warehouse = Evo.Warehouse(int(warehouse_id))
                OD.Project = Evo.Project(int(line.IssLinProjProjectId))

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
    print(data)
    if created_at:
        created_at = datetime.fromisoformat(created_at.replace("Z", ""))
    else:
        created_at = datetime.now()

    lines = data.get("returns") or []
    conn = None
    cursor = None

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # =====================================
        # Check already finalised
        # =====================================
        cursor.execute("""
            SELECT IssFinalised
            FROM stk.IssueHeader
            WHERE IdIssue = ?
        """, (issue_id,))
        order_finalised = int(cursor.fetchone()[0]) > 0

        if order_finalised:
            return jsonify({
                "success": False,
                "message": "This issue was already finalised. Please refresh page."
            })

        # =====================================
        # Finalise header
        # =====================================
        cursor.execute("""
            UPDATE stk.IssueHeader
            SET IssFinalised = 1,
                IssFinalisedByUserId = ?,
                IssFinalisedTimeStamp = ?
            WHERE IdIssue = ?
        """, (current_user.id, created_at, issue_id))

        # =====================================
        # Process returns
        # =====================================
        for line in lines:
            qty_returned = float(line.get("qty_returned") or 0)
            product_link = line.get("product_link")

            # -----------------------------
            # Get issue line for product
            # -----------------------------
            cursor.execute("""
                SELECT IdIssLine, IssLineQtyIssued
                FROM stk.IssueLines
                WHERE IssLineIssueId = ?
                  AND IssLineStockLink = ?
            """, (issue_id, product_link))

            issue_line = cursor.fetchone()

            if not issue_line:
                raise Exception(f"No stock line found for product {product_link}")

            line_id = issue_line.IdIssLine
            qty_issued = float(issue_line.IssLineQtyIssued or 0)

            qty_finalised = qty_issued - qty_returned
            if qty_finalised < 0:
                raise Exception(f"Returned quantity for product {product_link} cannot be greater than issued quantity.")

            # -----------------------------
            # Update issue line
            # -----------------------------
            cursor.execute("""
                UPDATE stk.IssueLines
                SET IssLineQtyReceived = ?,
                    IssLineQtyFinalised = ?
                WHERE IdIssLine = ?
            """, (
                qty_returned,
                qty_finalised,
                line_id
            ))

        # =====================================
        # Get issue details
        # =====================================
        cursor.execute("""
            SELECT IssWhseId
            FROM stk.IssueHeader
            WHERE IdIssue = ?
        """, (issue_id,))

        issue = cursor.fetchone()
        if not issue:
            raise Exception(f"Issue {issue_id} not found.")

        # =====================================
        # Submit remaining qty before committing DB updates
        # =====================================
        order_number = submit_stock_issue(issue_id, cursor)

        if order_number:
            cursor.execute("""
                UPDATE stk.IssueHeader
                SET IssInvoiceNo = ?
                WHERE IdIssue = ?
            """, (order_number, issue_id))

        conn.commit()

        emit_event(
            event_code="STOCK_ISSUE",
            entity_id=issue_id,
            entity_desc=order_number or 'NOT SENT TO EVO',
        )

        return jsonify({
            "success": True,
            "order_number": order_number
        })

    except Exception as e:
        print("process_return error:", e)

        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        return jsonify({
            "success": False,
            "message": str(e)
        })

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