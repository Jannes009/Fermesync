import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from datetime import datetime, timedelta
from System import DateTime as NetDateTime
import System
from System.Reflection import BindingFlags
from .spray_issue_validation import validate_spray_execution_quantities

from Core.sdk_connection import EvolutionConnection, EvolutionAgentNotFoundError, EvolutionConnectionError
import Pastel.Evolution as Evo

STOCK_ISSUE_PERMISSIONS = {
    "STOCK_ISSUE_CANCEL",
    "STOCK_ISSUE_CREATE",
    "STOCK_ISSUE_VIEW",
}


def _has_stock_issue_permission(*permissions):
    return bool(STOCK_ISSUE_PERMISSIONS.intersection(permissions).intersection(current_user.permissions))


def _stock_issue_warehouse_ids():
    return tuple(int(warehouse_id) for warehouse_id in (current_user.warehouses or []) if warehouse_id is not None)


@inventory_bp.route("/SDK/stock_issue_summary", methods=["GET"])
@login_required
def stock_issue_summary():
    # permission check (optional)
    if not _has_stock_issue_permission(*STOCK_ISSUE_PERMISSIONS):
        abort(403)
    return render_template(
        'EvolutionSDK/stock_issue_summary.html',
        can_create="STOCK_ISSUE_CREATE" in current_user.permissions,
        can_view="STOCK_ISSUE_VIEW" in current_user.permissions,
        can_cancel="STOCK_ISSUE_CANCEL" in current_user.permissions,
    )


@inventory_bp.route("/SDK/stock_issue_details/<int:issue_id>", methods=["GET"])
@login_required
def stock_issue_details(issue_id):
    if not _has_stock_issue_permission("STOCK_ISSUE_VIEW"):
        abort(403)
    return render_template("EvolutionSDK/stock_issue_details.html", issue_id=issue_id)


@inventory_bp.route("/SDK/incomplete_issues", methods=["GET"])
@login_required
def incomplete_issues():
    if not _has_stock_issue_permission(*STOCK_ISSUE_PERMISSIONS):
        abort(403)

    status = request.args.get("status", "all")
    if not _has_stock_issue_permission("STOCK_ISSUE_VIEW") and status in {"finalised", "all"}:
        status = "outstanding"
    if status not in {"all", "outstanding", "finalised"}:
        return jsonify({"success": False, "message": "Invalid status filter."}), 400

    warehouse_ids = _stock_issue_warehouse_ids()
    if not warehouse_ids:
        return jsonify({"success": True, "issues": []})

    today = datetime.now().date()
    default_start = today - timedelta(days=6)
    try:
        start_date = datetime.strptime(request.args.get("from", default_start.isoformat()), "%Y-%m-%d").date()
        end_date = datetime.strptime(request.args.get("to", today.isoformat()), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"success": False, "message": "Dates must use YYYY-MM-DD format."}), 400
    if start_date > end_date:
        return jsonify({"success": False, "message": "Start date must be on or before end date."}), 400

    if status == "outstanding":
        status_clause = "HEA.IssFinalised = 0 AND ISNULL(HEA.IssCancelled, 0) = 0"
        params = ()
    elif status == "finalised":
        status_clause = "HEA.IssFinalised = 1 AND HEA.IssTimeStamp >= CONVERT(date, ?) AND HEA.IssTimeStamp < DATEADD(day, 1, CONVERT(date, ?))"
        params = (start_date.isoformat(), end_date.isoformat())
    else:
        status_clause = "(HEA.IssFinalised = 0 AND ISNULL(HEA.IssCancelled, 0) = 0) OR ((HEA.IssFinalised = 1 OR ISNULL(HEA.IssCancelled, 0) = 1) AND COALESCE(HEA.IssCancelledTimeStamp, HEA.IssTimeStamp) >= CONVERT(date, ?) AND COALESCE(HEA.IssCancelledTimeStamp, HEA.IssTimeStamp) < DATEADD(day, 1, CONVERT(date, ?)))"
        params = (start_date.isoformat(), end_date.isoformat())

    params = (*params, *warehouse_ids)
    warehouse_placeholders = ",".join("?" for _ in warehouse_ids)
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT
                HEA.IdIssue,
                HEA.IssNo,
                HEA.IssInvoiceNo,
                HEA.IssWhseId,
                WHSE.WhseDescription,
                HEA.IssTimeStamp,
                HEA.IssFinalised,
                HEA.IssCancelled,
                HEA.IssEvolutionCreditNoteNo,
                HEA.IssSprayExecutionId,
                EXE.SprExecFinalised,
                (SELECT STRING_AGG(NULLIF(LTRIM(RTRIM(SH.SprayHDescription)), ''), ', ')
                 FROM agr.SprayHeader SH
                 WHERE SH.SprayHExecutionId = HEA.IssSprayExecutionId) AS ExecutionDescription
            FROM stk.IssueHeader HEA
            LEFT JOIN cmn._uvWarehouses WHSE ON WHSE.WhseLink = HEA.IssWhseId
            LEFT JOIN agr.SprayExecution EXE ON EXE.IdSprExec = HEA.IssSprayExecutionId
                        WHERE ({status_clause})
                            AND HEA.IssWhseId IN ({warehouse_placeholders})
            ORDER BY HEA.IssTimeStamp DESC, HEA.IdIssue DESC
        """, params)
        rows = cur.fetchall()

        issues = [{
            "IssueId": r.IdIssue,
            "IssueNo": r.IssNo,
            "EvolutionReference": r.IssInvoiceNo,
            "IssueTimeStamp": r.IssTimeStamp,
            "WhseId": r.IssWhseId,
            "WhseDescription": r.WhseDescription,
            "IsFinalised": bool(r.IssFinalised),
            "IsCancelled": bool(r.IssCancelled),
            "EvolutionCreditNoteNo": r.IssEvolutionCreditNoteNo,
            "ExecutionId": r.IssSprayExecutionId,
            "ExecutionFinalised": bool(r.SprExecFinalised) if r.SprExecFinalised is not None else None,
            "ExecutionDescription": r.ExecutionDescription,
        } for r in rows]

        return jsonify({"success": True, "issues": issues})
    except Exception as e:
        print("incomplete_issues error:", e)
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()


@inventory_bp.route("/SDK/stock_issue_details_data/<int:issue_id>", methods=["GET"])
@login_required
def stock_issue_details_data(issue_id):
    if not _has_stock_issue_permission("STOCK_ISSUE_VIEW"):
        abort(403)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                HEA.IdIssue,
                HEA.IssNo,
                HEA.IssInvoiceNo,
                HEA.IssDate,
                HEA.IssTimeStamp,
                HEA.IssByUserId,
                CreatedBy.username AS CreatedBy,
                HEA.IssFinalised,
                HEA.IssFinalisedByUserId,
                FinalisedBy.username AS FinalisedBy,
                HEA.IssFinalisedTimeStamp,
                HEA.IssCancelled,
                HEA.IssCancelledByUserId,
                CancelledBy.username AS CancelledBy,
                HEA.IssCancelledTimeStamp,
                HEA.IssEvolutionCreditNoteNo,
                HEA.IssWhseId,
                WHSE.WhseDescription,
                HEA.IssSprayExecutionId,
                EXE.SprExecFinalised,
                (SELECT STRING_AGG(NULLIF(LTRIM(RTRIM(SH.SprayHDescription)), ''), ', ')
                 FROM agr.SprayHeader SH
                 WHERE SH.SprayHExecutionId = HEA.IssSprayExecutionId) AS ExecutionDescription
            FROM stk.IssueHeader HEA
            LEFT JOIN users.Users CreatedBy ON CreatedBy.id = HEA.IssByUserId
            LEFT JOIN users.Users FinalisedBy ON FinalisedBy.id = HEA.IssFinalisedByUserId
            LEFT JOIN users.Users CancelledBy ON CancelledBy.id = HEA.IssCancelledByUserId
            LEFT JOIN cmn._uvWarehouses WHSE ON WHSE.WhseLink = HEA.IssWhseId
            LEFT JOIN agr.SprayExecution EXE ON EXE.IdSprExec = HEA.IssSprayExecutionId
            WHERE HEA.IdIssue = ?
        """, (issue_id,))
        header = cursor.fetchone()
        if not header:
            return jsonify({"success": False, "message": "Stock issue not found."}), 404

        cursor.execute("""
            SELECT
                LIN.IdIssLine,
                LIN.IssLineStockLink,
                STK.StockDescription,
                LIN.IssLineQtyIssued,
                ISNULL(LIN.IssLineQtyReceived, 0) AS IssLineQtyReceived,
                LIN.IssLineQtyFinalised,
                LIN.IssLineUoMId,
                UOM.cUnitCode
            FROM stk.IssueLines LIN
            LEFT JOIN cmn._uvStockItems STK ON STK.StockLink = LIN.IssLineStockLink
            LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.IssLineUoMId
            WHERE LIN.IssLineIssueId = ?
            ORDER BY LIN.IdIssLine
        """, (issue_id,))
        lines_by_id = {row.IdIssLine: {
            "line_id": row.IdIssLine,
            "product_link": row.IssLineStockLink,
            "product_desc": row.StockDescription,
            "qty_issued": row.IssLineQtyIssued,
            "qty_received": row.IssLineQtyReceived,
            "qty_finalised": row.IssLineQtyFinalised,
            "uom_id": row.IssLineUoMId,
            "uom_code": row.cUnitCode,
            "project_allocations": [],
        } for row in cursor.fetchall()}

        cursor.execute("""
            SELECT
                LIN.IdIssLine,
                ILP.IssLinProjProjectId,
                ILP.IssLinProjWeight,
                PROJ.ProjectCode,
                PROJ.ProjectName
            FROM stk.IssueLines LIN
            JOIN stk.IssueLineProjects ILP ON ILP.IssLinProjLineId = LIN.IdIssLine
            LEFT JOIN cmn._uvProject PROJ ON PROJ.ProjectLink = ILP.IssLinProjProjectId
            WHERE LIN.IssLineIssueId = ?
            ORDER BY LIN.IdIssLine, ILP.IssLinProjProjectId
        """, (issue_id,))
        for allocation in cursor.fetchall():
            line = lines_by_id.get(allocation.IdIssLine)
            if not line:
                continue
            weight = float(allocation.IssLinProjWeight or 0)
            line["project_allocations"].append({
                "project_code": allocation.ProjectCode,
                "project_name": allocation.ProjectName,
                "weight": weight,
                "qty_issued": float(line["qty_issued"] or 0) * weight,
                "qty_received": float(line["qty_received"] or 0) * weight,
                "qty_finalised": (
                    float(line["qty_finalised"]) * weight
                    if line["qty_finalised"] is not None else None
                ),
            })
        lines = list(lines_by_id.values())

        return jsonify({
            "success": True,
            "issue": {
                "id": header.IdIssue,
                "number": header.IssNo,
                "evolution_reference": header.IssInvoiceNo,
                "issue_date": header.IssDate,
                "created_at": header.IssTimeStamp,
                "created_by_id": header.IssByUserId,
                "created_by": header.CreatedBy,
                "is_finalised": bool(header.IssFinalised),
                "finalised_by_id": header.IssFinalisedByUserId,
                "finalised_by": header.FinalisedBy,
                "finalised_at": header.IssFinalisedTimeStamp,
                "is_cancelled": bool(header.IssCancelled),
                "cancelled_by_id": header.IssCancelledByUserId,
                "cancelled_by": header.CancelledBy,
                "cancelled_at": header.IssCancelledTimeStamp,
                "evolution_credit_note_no": header.IssEvolutionCreditNoteNo,
                "warehouse_id": header.IssWhseId,
                "warehouse": header.WhseDescription,
                "execution_id": header.IssSprayExecutionId,
                "execution_finalised": bool(header.SprExecFinalised) if header.SprExecFinalised is not None else None,
                "execution_description": header.ExecutionDescription,
                "lines": lines,
            }
        })
    except Exception as e:
        print("stock_issue_details_data error:", e)
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@inventory_bp.route("/SDK/cancel_stock_issue", methods=["POST"])
@login_required
def cancel_stock_issue():
    if "STOCK_ISSUE_CANCEL" not in current_user.permissions:
        abort(403)

    data = request.get_json(silent=True) or {}
    issue_id = data.get("issue_id")
    if not issue_id:
        return jsonify({"success": False, "message": "Stock issue ID is required."}), 400

    conn = None
    cursor = None
    warehouse_ids = _stock_issue_warehouse_ids()
    if not warehouse_ids:
        return jsonify({"success": False, "message": "Stock issue not found."}), 404
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT
            HEA.IssInvoiceNo,
            PO.AutoIndex,
            PO.OrderNum,
            HEA.IssCancelled,
            HEA.IssSprayExecutionId,
            EXE.SprExecFinalised
        FROM stk.IssueHeader HEA WITH (UPDLOCK, HOLDLOCK)
        LEFT JOIN agr.SprayExecution EXE ON EXE.IdSprExec = HEA.IssSprayExecutionId
        LEFT JOIN stk._uvSalesOrders PO on PO.InvNumber = HEA.IssInvoiceNo
                WHERE HEA.IdIssue = ?
                """, (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            return jsonify({"success": False, "message": "Stock issue not found."}), 404
        if bool(issue.IssCancelled):
            return jsonify({"success": False, "message": "This stock issue has already been cancelled."}), 409
        # if issue.IssSprayExecutionId is not None and (
        #     issue.SprExecFinalised is None or bool(issue.SprExecFinalised)):
        #     return jsonify({
        #         "success": False,
        #         "message": "This issue cannot be cancelled because its linked execution is finalised or unavailable."
        #     }), 409
        if not issue.AutoIndex and issue.IssInvoiceNo:
            return jsonify({
                "success": False,
                "message": "This issue cannot be cancelled because it has an invoice number but no linked Evolution sales order."
            }), 409
        if not issue.AutoIndex:
            cursor.execute("""
                UPDATE stk.IssueHeader
                SET IssCancelled = 1,
                    IssCancelledByUserId = ?,
                    IssCancelledTimeStamp = GETDATE(),
                    IssEvolutionCreditNoteNo = NULL,
                    IssFinalised = 1
                WHERE IdIssue = ? AND ISNULL(IssCancelled, 0) = 0
            """, (current_user.id, issue_id))
            if cursor.rowcount != 1:
                raise RuntimeError("The stock issue cancellation could not be recorded.")
            conn.commit()
            return jsonify({
                "success": True,
                "credited": False,
                "message": "Issue cancelled in Fermesync. No Evolution sales order existed to credit."
            })

        with EvolutionConnection():
            sales_order = Evo.SalesOrder(int(issue.AutoIndex))
            print(issue.AutoIndex, issue.OrderNum, sales_order.OrderNo, sales_order.LongID)
            print(f"Retrieved Evolution sales order: {sales_order.OrderNo}, LongID: {sales_order.LongID}")
            if not sales_order.LongID or str(sales_order.OrderNo).strip() != str(issue.OrderNum).strip():
                raise ValueError("The Evolution sales order reference could not be matched exactly.")

            credit_note = Evo.CreditNote()
            credit_note.OrderNo = sales_order.OrderNo
            credit_note.Customer = Evo.Customer("ZZZ001")
            credit_note.InvoiceDate = NetDateTime.Now
            credit_note.InvoiceNumber = issue.IssInvoiceNo
            credit_note.Description = sales_order.Description
            credit_note.InvoiceDate = sales_order.InvoiceDate

            record_field = clr.GetClrType(Evo.OrderBase).GetField(
                "record",
                BindingFlags.Instance | BindingFlags.NonPublic
            )
            if record_field is None:
                raise RuntimeError("Could not find OrderBase.record for linked credit note setup.")
            credit_record = record_field.GetValue(credit_note)
            if credit_record is None:
                raise RuntimeError("Credit note record was not initialized by Evolution.")

            record_type = credit_record.GetType()
            linked_doc_property = record_type.GetProperty(
                "iLinkedDocID",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            )
            linked_template_property = record_type.GetProperty(
                "bLinkedTemplate",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            )
            if linked_doc_property is None or linked_template_property is None:
                raise RuntimeError("Evolution linked-document properties are unavailable.")
            linked_doc_property.SetValue(
                credit_record,
                System.Int64(sales_order.LongID)
            )

            linked_template_property.SetValue(credit_record, True)

            line_count = 0
            for source_line in sales_order.Detail:
                quantity = float(source_line.Quantity or 0)
                if quantity <= 0:
                    continue
                credit_line = Evo.OrderDetail()
                credit_note.Detail.Add(credit_line)
                credit_line.InventoryItem = source_line.InventoryItem
                credit_line.Quantity = quantity
                credit_line.ToProcess = quantity
                credit_line.UnitSellingPrice = float(source_line.UnitSellingPrice or 0)
                credit_line.Unit = source_line.Unit
                credit_line.Warehouse = source_line.Warehouse
                credit_line.Project = source_line.Project
                line_count += 1

            if not line_count:
                raise ValueError("The linked Evolution sales order has no quantities to credit.")

            credit_note_number = credit_note.Process()

        cursor.execute("""
            UPDATE stk.IssueHeader
            SET IssCancelled = 1,
                IssCancelledByUserId = ?,
                IssCancelledTimeStamp = GETDATE(),
                IssEvolutionCreditNoteNo = ?,
                IssFinalised = 1
            WHERE IdIssue = ? AND ISNULL(IssCancelled, 0) = 0
        """, (current_user.id, credit_note_number, issue_id))
        if cursor.rowcount != 1:
            raise RuntimeError("The stock issue cancellation could not be recorded.")
        conn.commit()
        return jsonify({
            "success": True,
            "credited": True,
            "credit_note_number": str(credit_note_number),
        })
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print("cancel_stock_issue error:", e)
        return jsonify({"success": False, "message": str(e)}), 500
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


@inventory_bp.route("/SDK/incomplete_issue_lines/<int:header_id>", methods=["GET"])
@login_required
def incomplete_issue_lines(header_id):
    if "STOCK_ISSUE_CREATE" not in current_user.permissions:
        abort(403)  # Forbidden

    warehouse_ids = _stock_issue_warehouse_ids()
    if not warehouse_ids:
        return jsonify({"success": True, "issue_lines": []})
    warehouse_placeholders = ",".join("?" for _ in warehouse_ids)
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
                    AND HEA.IssFinalised = 0
                    AND ISNULL(HEA.IssCancelled, 0) = 0
                    AND HEA.IssWhseId IN ({warehouse_placeholders})
                """.format(warehouse_placeholders=warehouse_placeholders), (header_id, *warehouse_ids))

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

    # return {"issue_lines": results}
    return jsonify({"success": True, "issue_lines": results})

def submit_stock_issue(issue_id, cursor):
    cursor.execute("""
        SELECT IssWhseId, IssDate
        FROM stk.IssueHeader
        WHERE IdIssue = ?
    """, (issue_id,))
    issue = cursor.fetchone()
    warehouse_id = issue.IssWhseId if issue else None
    issue_date = None
    if issue:
        # IssDate may be returned as a datetime or string depending on driver
        try:
            issue_date = issue.IssDate
        except Exception:
            try:
                issue_date = issue[1]
            except Exception:
                issue_date = None

    description = f"Stock Issue from warehouse {warehouse_id}"
    print(issue_date)

    try:
        with EvolutionConnection():
            SO = Evo.SalesOrder()
            SO.Customer = Evo.Customer("ZZZ001")
            SO.Description = description
            issue_date = issue.IssDate if issue else None

            if issue_date is None:
                issue_date = datetime.now()
            elif isinstance(issue_date, str):
                issue_date = datetime.fromisoformat(issue_date)

            # Explicitly create a .NET System.DateTime
            net_issue_date = NetDateTime(
                issue_date.year,
                issue_date.month,
                issue_date.day,
                issue_date.hour,
                issue_date.minute,
                issue_date.second
            )

            print("Python date:", issue_date, type(issue_date))
            print("NET date:", net_issue_date, net_issue_date.GetType())

            SO.InvoiceDate = net_issue_date

            cursor.execute("""              
            Select IssLineStockLink, IssLinProjProjectId, SUM(IssLinProjWeight) as TotalWeight, IssLineQtyFinalised, IssLineUoMId
            from [stk].[IssueHeader] HEA
            JOIN [stk].[IssueLines] LIN on HEA.IdIssue = LIN.IssLineIssueId
            JOIN stk.IssueLineProjects PROJ on PROJ.IssLinProjLineId = LIN.IdIssLine
            Where HEA.IdIssue = ?
            Group by IssLineStockLink, IssLinProjProjectId, IssLineQtyFinalised, IssLineUoMId
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
                print(weighted_qty, warehouse_id)

                OD.InventoryItem = Evo.InventoryItem(int(line.IssLineStockLink))
                OD.Quantity = weighted_qty
                OD.Unit = Evo.Unit(int(line.IssLineUoMId))
                OD.Warehouse = Evo.Warehouse(int(warehouse_id))
                OD.Project = Evo.Project(int(line.IssLinProjProjectId))

            invoice_no = SO.Complete()
            return invoice_no

    except Exception as ex:
        print("Stock Issue Submission Error:", str(ex))
        raise ex

    
@inventory_bp.route("/process_return", methods=["POST"])
@login_required
def process_return():
    if "STOCK_ISSUE_CREATE" not in current_user.permissions:
        abort(403)

    data = request.get_json(silent=True) or {}
    issue_id = data.get("issue_id")
    if not issue_id:
        return jsonify({"success": False, "message": "Stock issue ID is required."}), 400
    created_at = data.get("created_at")
    print(data)
    if created_at:
        created_at = datetime.fromisoformat(created_at.replace("Z", ""))
    else:
        created_at = datetime.now()

    lines = data.get("returns") or []
    warehouse_ids = _stock_issue_warehouse_ids()
    if not warehouse_ids:
        return jsonify({"success": False, "message": "Stock issue not found."}), 404
    conn = None
    cursor = None

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # =====================================
        # Check already finalised
        # =====================================
        cursor.execute("""
            SELECT IssFinalised, IssSprayExecutionId, IssWhseId, IssCancelled
            FROM stk.IssueHeader
            WHERE IdIssue = ?
        """, (issue_id,))
        issue_header = cursor.fetchone()
        if not issue_header:
            return jsonify({"success": False, "message": "Stock issue not found."}), 404
        if int(issue_header.IssWhseId) not in warehouse_ids:
            return jsonify({"success": False, "message": "Stock issue not found."}), 404
        if bool(issue_header.IssCancelled):
            return jsonify({"success": False, "message": "This stock issue has been cancelled."}), 409
        order_finalised = int(issue_header.IssFinalised or 0) > 0

        if order_finalised:
            return jsonify({
                "success": False,
                "message": "This issue was already finalised. Please refresh page."
            })

        execution_id = issue_header.IssSprayExecutionId
        if execution_id is not None:
            validate_spray_execution_quantities(
                cursor, execution_id, lines, "qty_returned", -1
            )

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