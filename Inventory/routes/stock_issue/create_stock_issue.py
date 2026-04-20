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
    lines_payload = data.get("lines", [])
    
    issue_mode = data.get("issue_mode", "project")  # "project" or "spray"
    

    if issue_mode not in ["project", "spray"]:
        return jsonify({"status": "error", "message": "Invalid issue mode"}), 400
    elif issue_mode == "project":
        projects = data.get("projects")
        if not projects or not isinstance(projects, list) or len(projects) == 0:
            return jsonify({"status": "error", "message": "Projects list required for project mode"}), 400
        warehouse_id = data.get("warehouse")
        if not warehouse_id or not lines_payload:
            return jsonify({"status": "error", "message": "Missing required data"}), 400

        return generate_stock_issue_for_projects(projects, warehouse_id, lines_payload, order_final)
    elif issue_mode == "spray":
        spray_id = data.get("spray_id")    
        if not spray_id:
            return jsonify({"status": "error", "message": "Spray ID required for spray mode"}), 400
        return generate_stock_issue_for_spray(spray_id, lines_payload, order_final)


def generate_stock_issue_for_projects(project_ids, warehouse_id, lines_payload, order_final):
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # =========================
        # Create issue header
        # =========================
        cursor.execute("""
            INSERT INTO [stk].IssueHeader (
                IssWhseId, IssByUserId, IssTimeStamp
            )
            OUTPUT INSERTED.IdIssue
            VALUES (?, ?, GETDATE())
        """, (warehouse_id, current_user.id))

        stock_issue_id = cursor.fetchone()[0]
        issue_no = f"ISS-{int(stock_issue_id):03d}"

        cursor.execute("""
            UPDATE [stk].IssueHeader
            SET IssNo = ?
            WHERE IdIssue = ?
        """, (issue_no, stock_issue_id))

        if order_final:
            cursor.execute("""
                UPDATE [stk].IssueHeader
                SET IssFinalised = 1,
                    IssFinalisedByUserId = ?,
                    IssFinalisedTimeStamp = GETDATE()
                WHERE IdIssue = ?
            """, (current_user.id, stock_issue_id))

        # =========================
        # Equal weight per project
        # =========================
        weight = 1 / len(project_ids) if project_ids else 0

        # =========================
        # Insert lines
        # =========================
        for line in lines_payload:
            cursor.execute("""
                INSERT INTO [stk].IssueLines(
                    IssLineIssueId,
                    IssLineStockLink,
                    IssLineQtyIssued,
                    IssLineUOMId
                )
                OUTPUT INSERTED.IdIssLine
                VALUES (?, ?, ?, ?)
            """, (
                stock_issue_id,
                line.get("product_link"),
                line.get("qty_to_issue"),
                line.get("uom_id"),
            ))

            last_line_id = cursor.fetchone()[0]

            # =========================
            # Insert project allocations
            # =========================
            for project_id in project_ids:
                cursor.execute("""
                    INSERT INTO [stk].IssueLineProjects(
                        IssLinProjLineId,
                        IssLinProjProjectId,
                        IssLinProjWeight
                    )
                    VALUES (?, ?, ?)
                """, (
                    last_line_id,
                    project_id,
                    weight
                ))

            # =========================
            # Finalised qty
            # =========================
            if order_final:
                cursor.execute("""
                    UPDATE [stk].IssueLines
                    SET IssLineQtyFinalised = ?
                    WHERE IdIssLine = ?
                """, (line.get("qty_to_issue"), last_line_id))

        # =========================
        # Submit to Evolution
        # =========================
        if order_final:
            order_number = submit_stock_issue(stock_issue_id, cursor)

            cursor.execute("""
                UPDATE [stk].IssueHeader
                SET IssInvoiceNo = ?
                WHERE IdIssue = ?
            """, (order_number, stock_issue_id))

            emit_event(
                event_code="STOCK_ISSUE",
                entity_id=stock_issue_id,
                entity_desc=order_number,
            )

        conn.commit()

        cursor.execute("""
            SELECT IdIssLine, IssLineStockLink
            FROM [stk].[IssueLines]
            WHERE IssLineIssueId = ?
        """, (stock_issue_id,))

        issue_lines = cursor.fetchall()

        return jsonify({
            "status": "success",
            "message": "Stock issue created.",
            "issue_id": stock_issue_id,
            "issue_no": issue_no,
            "project_ids": project_ids,
            "issue_lines": [
                {
                    "issue_line_id": row[0],
                    "issue_product_link": row[1]
                } for row in issue_lines
            ]
        }), 200

    except Exception as ex:
        conn.rollback()
        return jsonify({
            "status": "error",
            "message": str(ex)
        }), 400
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


def generate_stock_issue_for_spray(execution_id, lines_payload, order_final):
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # check if execution exists and is open
        cursor.execute("""
            SELECT COUNT(1)
            FROM agr.SprayExecution
            WHERE IdSprExec = ? AND SprExecFinalised = 0
        """, (execution_id,))
        if cursor.fetchone()[0] == 0:
            return jsonify({"status": "error", "message": "Spray execution not found or already finalised"}), 400
        # =====================================
        # Get warehouse
        # =====================================
        cursor.execute("""
            SELECT TOP 1 HEA.SprayHWhseId
            FROM agr.SprayExecution EXE
            JOIN agr.SprayHeader HEA
                ON EXE.IdSprExec = HEA.SprayHExecutionId
            WHERE EXE.IdSprExec = ?
        """, (execution_id,))
        warehouse_id = cursor.fetchone()[0]

        # =====================================
        # Create issue header
        # =====================================
        cursor.execute("""
            INSERT INTO stk.IssueHeader(
                IssWhseId,
                IssByUserId,
                IssTimeStamp,
                IssSprayExecutionId
            )
            OUTPUT INSERTED.IdIssue
            VALUES (?, ?, GETDATE(), ?)
        """, (
            warehouse_id,
            current_user.id,
            execution_id
        ))

        stock_issue_id = cursor.fetchone()[0]
        issue_no = f"ISS-{int(stock_issue_id):03d}"

        cursor.execute("""
            UPDATE stk.IssueHeader
            SET IssNo = ?
            WHERE IdIssue = ?
        """, (issue_no, stock_issue_id))

        if order_final:
            cursor.execute("""
                UPDATE stk.IssueHeader
                SET IssFinalised = 1,
                    IssFinalisedByUserId = ?,
                    IssFinalisedTimeStamp = GETDATE()
                WHERE IdIssue = ?
            """, (current_user.id, stock_issue_id))

        # =====================================
        # Insert issue lines
        # =====================================
        for line in lines_payload:
            stock_id = line.get("product_link")
            total_qty = float(line.get("qty_to_issue") or 0)

            # ---------------------------------
            # Create ONE issue line per product
            # ---------------------------------
            cursor.execute("""
                INSERT INTO stk.IssueLines(
                    IssLineIssueId,
                    IssLineStockLink,
                    IssLineQtyIssued,
                    IssLineUOMId
                )
                OUTPUT INSERTED.IdIssLine
                VALUES (?, ?, ?, ?)
            """, (
                stock_issue_id,
                stock_id,
                total_qty,
                line.get("uom_id"),
            ))

            issue_line_id = cursor.fetchone()[0]

            if order_final:
                cursor.execute("""
                    UPDATE stk.IssueLines
                    SET IssLineQtyFinalised = ?
                    WHERE IdIssLine = ?
                """, (total_qty, issue_line_id))

            # =====================================
            # Get project-specific weights for this stock
            # =====================================
            cursor.execute("""
                SELECT ProjectId, ProjectWeight, IdSprayH
                FROM [agr].[_uvSprayExecutionProjectWeights]
                WHERE IdSprExec = ? AND StockId = ?
            """, (execution_id, stock_id))

            project_rows = cursor.fetchall()

            # =====================================
            # Insert project allocations
            # =====================================
            for row in project_rows:
                cursor.execute("""
                    INSERT INTO [stk].[IssueLineProjects](
                        [IssLinProjLineId],
                        [IssLinProjProjectId],
                        [IssLinProjWeight],
                        [IssLinProjSprayId]
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    issue_line_id,
                    row.ProjectId,
                    row.ProjectWeight,
                    row.IdSprayH
                ))
            

        # =====================================
        # Submit to Evolution
        # =====================================
        if order_final:
            order_number = submit_stock_issue(stock_issue_id, cursor)

            cursor.execute("""
                UPDATE stk.IssueHeader
                SET IssInvoiceNo = ?
                WHERE IdIssue = ?
            """, (order_number, stock_issue_id))

            emit_event(
                event_code="STOCK_ISSUE",
                entity_id=stock_issue_id,
                entity_desc=order_number,
            )

        conn.commit()

        cursor.execute("""
            SELECT IdIssLine, IssLineStockLink
            FROM stk.IssueLines
            WHERE IssLineIssueId = ?
        """, (stock_issue_id,))

        issue_lines = cursor.fetchall()

        return jsonify({
            "status": "success",
            "message": "Stock issue created.",
            "issue_id": stock_issue_id,
            "issue_no": issue_no,
            "issue_lines": [
                {
                    "issue_line_id": row[0],
                    "issue_product_link": row[1]
                } for row in issue_lines
            ]
        }), 200

    except Exception as ex:
        conn.rollback()
        return jsonify({
            "status": "error",
            "message": str(ex)
        }), 400
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

