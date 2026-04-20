from datetime import datetime
from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp

def format_decimal(value):
    if value is None:
        return "0"
    try:
        formatted = f"{float(value):,.2f}"
        return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted
    except (ValueError, TypeError):
        return str(value)


def format_datetime(value):
    if value is None:
        return '-'
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M')
    return str(value)


@agri_bp.route("/execution/<int:execution_id>", methods=["GET"])
@login_required
def view_execution(execution_id):
    conn = create_db_connection()
    cur = conn.cursor()

    # Get execution information
    cur.execute("""
        SELECT b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, b.SprExecFinalised,
               p.PersonName
        FROM agr.SprayExecution b
        LEFT JOIN agr.People p ON p.IdPerson = b.SprExecResponsiblePerson
        WHERE b.IdSprExec = ?
    """, execution_id)

    execution_row = cur.fetchone()
    if not execution_row:
        conn.close()
        return "Execution not found", 404

    execution = {
        "id": execution_row.IdSprExec,
        "date": execution_row.SprExecDate,
        "responsible_person": execution_row.PersonName,
        "finalised": execution_row.SprExecFinalised
    }

    # Get spray instructions in this execution
    cur.execute("""
        SELECT h.IdSprayH, h.SprayHNo, h.SprayHDate, h.SprayHDescription, h.SprayHStatus,
               h.SprayHStartDateTime, h.SprayHEndDateTime, h.SprayHWeather,
               DATEPART(WEEK, h.SprayHDate) AS week_number,
               DATEPART(YEAR, h.SprayHDate) AS year,
               WHSE.WhseDescription,
               REQ.SprayId, REQ.QtyAvailable, REQ.TotalQty,
               p.ProjectCode, sp.SprayPHa, sp.SprayPWaterPerHa, sp.SprayPBlockNo,
               sl.IdSprayLine, stk.StockDescription, sl.SprayLineQtyPer100L, sl.SprayLineUoMId
        FROM agr.SprayHeader h
        JOIN agr.SprayExecution b ON b.IdSprExec = h.SprayHExecutionId
        LEFT JOIN [agr].[_uvSprayStockRequirements] REQ on REQ.SprayId = h.IdSprayH
        LEFT JOIN cmn._uvWarehouses WHSE on WHSE.WhseLink = REQ.WhseId
        LEFT JOIN agr.SprayProjects sp ON sp.SprayPSprayId = h.IdSprayH
        LEFT JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        LEFT JOIN agr.SprayLines sl ON sl.SprayLineHeaderId = h.IdSprayH
        LEFT JOIN cmn._uvStockItems stk ON stk.StockLink = sl.SprayLineStkId
        WHERE b.IdSprExec = ?
        ORDER BY h.IdSprayH
    """, execution_id)

    instructions_dict = {}
    for row in cur.fetchall():
        id = row.IdSprayH
        if id not in instructions_dict:
            instructions_dict[id] = {
                "id": id,
                "spray_no": row.SprayHNo,
                "spray_date": str(row.SprayHDate) if row.SprayHDate else None,
                "start_date_time": str(row.SprayHStartDateTime) if row.SprayHStartDateTime else None,
                "end_date_time": str(row.SprayHEndDateTime) if row.SprayHEndDateTime else None,
                "weather": row.SprayHWeather,
                "week_number": row.week_number,
                "year": row.year,
                "description": row.SprayHDescription,
                "status": row.SprayHStatus,
                "warehouses": set(),
                "projects": {},
                "products": {}
            }
        
        # Add project info
        if row.ProjectCode:
            instructions_dict[id]["projects"][row.ProjectCode] = {
                "project_code": row.ProjectCode,
                "ha": row.SprayPHa,
                "water_per_ha": row.SprayPWaterPerHa,
                "block_no": row.SprayPBlockNo
            }
        
        # Add warehouse
        if row.WhseDescription:
            instructions_dict[id]["warehouses"].add(row.WhseDescription)
        
        # Add product info (keyed by description to avoid duplicates)
        if row.StockDescription and (row.QtyAvailable is not None or row.TotalQty is not None):
            instructions_dict[id]["products"][row.StockDescription] = {
                "description": row.StockDescription,
                "qty_available": row.QtyAvailable,
                "total_qty": row.TotalQty,
                "warehouse": row.WhseDescription
            }

    spray_instructions = []
    for instr in instructions_dict.values():
        instr["sufficient_stock"] = all(p.get("qty_available") and p.get("qty_available") >= p.get("total_qty", 0) for p in instr["products"].values() if p.get("total_qty") is not None)
        instr["warehouses"] = list(instr["warehouses"])
        instr["projects"] = list(instr["projects"].values())
        instr["products"] = list(instr["products"].values())
        spray_instructions.append(instr)

    # Set execution warehouse to the first warehouse found
    execution["warehouse"] = spray_instructions[0]["warehouses"][0] if spray_instructions and spray_instructions[0]["warehouses"] else None

    # Get stock movements for this execution
    # This assumes there's a table that tracks stock movements for executions
    # You might need to adjust this based on your actual database schema
    cur.execute("""
        SELECT 
            QTY.IdIssue,
            QTY.IssLineStockLink,
            QTY.IssTimeStamp,
            QTY.IssFinalisedTimeStamp,
            QTY.QtyOut,
            QTY.QtyIn,
            QTY.FinalisedNett,
            QTY.UnFinalisedOut,
            UOM.cUnitCode,
            STK.StockDescription,
            REC.RecommendedQty
        FROM stk._uvIssueQuantities QTY
        JOIN (
            SELECT 
                EXE.IdSprExec,
                LIN.SprayLineStkId,
                SUM(LIN.SprayLineTotalQty) AS RecommendedQty
            FROM agr.SprayExecution EXE
            JOIN agr.SprayHeader HEA 
                ON HEA.SprayHExecutionId = EXE.IdSprExec
            JOIN agr.SprayLines LIN 
                ON LIN.SprayLineHeaderId = HEA.IdSprayH
            GROUP BY EXE.IdSprExec, LIN.SprayLineStkId
        ) REC 
            ON REC.IdSprExec = QTY.IssSprayExecutionId
        AND REC.SprayLineStkId = QTY.IssLineStockLink
        JOIN cmn._uvStockItems STK 
            ON STK.StockLink = QTY.IssLineStockLink
        JOIN cmn._uvUOM UOM 
            ON UOM.idUnits = QTY.IssLineUoMId
        WHERE QTY.IssSprayExecutionId = ?
    """, execution_id)

    stock_dict = {}

    for row in cur.fetchall():
        stock_key = row.IssLineStockLink   # safer than description

        if stock_key not in stock_dict:
            stock_dict[stock_key] = {
                "stock_link": stock_key,
                "stock_description": row.StockDescription,
                "unit_code": row.cUnitCode,
                "qty_recommended": row.RecommendedQty or 0,
                "qty_recommended_display": format_decimal(row.RecommendedQty),
                "qty_out": 0,
                "qty_in": 0,
                "qty_finalised_nett": 0,
                "qty_unfinalised": 0,
                "details": []
            }

        # accumulate totals
        stock_dict[stock_key]["qty_out"] += row.QtyOut or 0
        stock_dict[stock_key]["qty_in"] += row.QtyIn or 0
        stock_dict[stock_key]["qty_finalised_nett"] += row.FinalisedNett or 0
        stock_dict[stock_key]["qty_unfinalised"] += row.UnFinalisedOut or 0

        # keep individual issue detail
        stock_dict[stock_key]["details"].append({
            "issue_id": row.IdIssue,
            "qty_out": row.QtyOut or 0,
            "qty_in": row.QtyIn or 0,
            "qty_finalised_nett": row.FinalisedNett or 0,
            "qty_unfinalised": row.UnFinalisedOut or 0,
            "qty_out_display": format_decimal(row.QtyOut),
            "qty_in_display": format_decimal(row.QtyIn),
            "qty_finalised_nett_display": format_decimal(row.FinalisedNett),
            "qty_unfinalised_display": format_decimal(row.UnFinalisedOut),
            "time_issued": row.IssTimeStamp,
            "time_finalised": row.IssFinalisedTimeStamp,
            "time_issued_display": format_datetime(row.IssTimeStamp),
            "time_finalised_display": format_datetime(row.IssFinalisedTimeStamp)
        })

    stock_movements = list(stock_dict.values())

    conn.close()

    return render_template("spray_execution.html",
                         execution=execution,
                         spray_instructions=spray_instructions,
                         stock_movements=stock_movements)

@agri_bp.route("/execution/issue/<int:issue_id>", methods=["GET"])
@login_required
def get_issue_details(issue_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT HEA.IdIssue, HEA.IssNo, HEA.IssWhseId, HEA.IssTimeStamp, HEA.IssFinalisedTimeStamp,
               HEA.IssFinalised, WHSE.WhseDescription
        FROM stk.IssueHeader HEA
        LEFT JOIN cmn._uvWarehouses WHSE ON WHSE.WhseLink = HEA.IssWhseId
        WHERE HEA.IdIssue = ?
    """, issue_id)

    header = cur.fetchone()
    if not header:
        conn.close()
        return jsonify({"success": False, "message": "Issue not found."}), 404

    cur.execute("""
        SELECT LIN.IdIssLine, LIN.IssLineStockLink, STK.StockDescription,
               LIN.IssLineQtyIssued, LIN.IssLineQtyReceived, LIN.IssLineQtyFinalised,
               UOM.cUnitCode
        FROM stk.IssueLines LIN
        LEFT JOIN cmn._uvStockItems STK ON STK.StockLink = LIN.IssLineStockLink
        LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.IssLineUoMId
        WHERE LIN.IssLineIssueId = ?
    """, issue_id)

    lines = [
        {
            "line_id": row.IdIssLine,
            "product_link": row.IssLineStockLink,
            "product_desc": row.StockDescription,
            "qty_issued": row.IssLineQtyIssued or 0,
            "qty_received": row.IssLineQtyReceived or 0,
            "qty_finalised": row.IssLineQtyFinalised or 0,
            "uom_code": row.cUnitCode
        }
        for row in cur.fetchall()
    ]

    issue = {
        "issue_id": header.IdIssue,
        "issue_no": header.IssNo,
        "whse_id": header.IssWhseId,
        "whse_description": header.WhseDescription,
        "issued_timestamp": format_datetime(header.IssTimeStamp),
        "finalised_timestamp": format_datetime(header.IssFinalisedTimeStamp),
        "finalised": bool(header.IssFinalised)
    }

    conn.close()
    return jsonify({"issue": issue, "lines": lines})


@agri_bp.route("/execution/<int:execution_id>/update_instruction/<int:instruction_id>", methods=["POST"])
@login_required
def update_instruction(execution_id, instruction_id):
    conn = create_db_connection()
    cur = conn.cursor()

    start_date_time = request.form.get('start_date_time')
    end_date_time = request.form.get('end_date_time')
    weather = request.form.get('weather')

    start_dt = None
    end_dt = None

    if start_date_time:
        start_dt = datetime.strptime(start_date_time, "%Y-%m-%dT%H:%M")

    if end_date_time:
        end_dt = datetime.strptime(end_date_time, "%Y-%m-%dT%H:%M")

    cur.execute("""
        UPDATE agr.SprayHeader
        SET SprayHStartDateTime = ?, 
            SprayHEndDateTime = ?, 
            SprayHWeather = ?
        WHERE IdSprayH = ?
    """, start_dt, end_dt, weather, instruction_id)

    conn.commit()
    conn.close()

    return redirect(url_for('agri.view_execution', execution_id=execution_id))

@agri_bp.route("/execution/<int:execution_id>/finalize", methods=["POST"])
@login_required
def finalize_execution(execution_id):
    conn = create_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if there are stock movements with qty used
        cur.execute("""
        SELECT
            COUNT(DISTINCT IdIssue) AS TotalIssues,
            COUNT(DISTINCT CASE 
                WHEN UnFinalisedOut > 0 THEN IdIssue 
            END) AS IssuesWithUnfinalisedQty
        FROM stk._uvIssueQuantities
        Where IssSprayExecutionId = ?
        """, execution_id)
        
        result = cur.fetchone()
        if not result or result.TotalIssues == 0:
            conn.close()
            return jsonify({"success": False, "message": "Cannot finalize execution: No stock issues found for execution"}), 400
        
        if result.IssuesWithUnfinalisedQty > 0:
            conn.close()
            return jsonify({"success": False, "message": "Cannot finalize execution: There are stock issues with unfinalised quantities. Please finalise all stock issues before finalizing the execution."}), 400
        
        cur.execute("""
            UPDATE agr.SprayExecution 
            SET SprExecFinalised = 1 
            WHERE IdSprExec = ?
        """, execution_id)
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Execution finalized successfully"})
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error finalizing execution: {str(e)}"}), 500