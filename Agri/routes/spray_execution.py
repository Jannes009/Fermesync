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
        SELECT TOP 1 b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, b.SprExecFinalised,
               p.PersonName, WHSE.WhseDescription
        FROM agr.SprayExecution b
        LEFT JOIN agr.People p ON p.IdPerson = b.SprExecResponsiblePerson
		JOIN [agr].[SprayHeader] HEA on HEA.SprayHExecutionId = b.IdSprExec
		JOIN cmn._uvWarehouses WHSE on WHSE.WhseLink = HEA.SprayHWhseId
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
        "warehouse": execution_row.WhseDescription,
        "finalised": execution_row.SprExecFinalised
    }

    # Get spray instructions in this execution
    cur.execute("""
        SELECT h.IdSprayH, h.SprayHNo, h.SprayHDescription, h.SprayHWeek, h.SprayHStatus,
               h.SprayHDate, h.SprayHStartDateTime, h.SprayHEndDateTime, h.SprayHWeather, h.SprayHFinalised
        FROM agr.SprayHeader h
        JOIN agr.SprayExecution b ON b.IdSprExec = h.SprayHExecutionId
        WHERE b.IdSprExec = ?
        ORDER BY h.IdSprayH
    """, execution_id)

    spray_instructions = [
        {
            "id": row.IdSprayH,
            "spray_no": row.SprayHNo,
            "description": row.SprayHDescription,
            "week_number": row.SprayHWeek,
            "status": row.SprayHStatus,
            "spray_date": row.SprayHDate,
            "start_date_time": row.SprayHStartDateTime,
            "end_date_time": row.SprayHEndDateTime,
            "weather": row.SprayHWeather,
            "finalised": bool(row.SprayHFinalised)
        }
        for row in cur.fetchall()
    ]

    # Determine which execution actions are valid
    cur.execute("""
        SELECT
            COUNT(DISTINCT IdIssue) AS TotalIssues,
            COUNT(DISTINCT CASE WHEN UnFinalisedOut > 0 THEN IdIssue END) AS IssuesWithUnfinalisedQty,
            COUNT(DISTINCT CASE WHEN (FinalisedNett > 0 OR UnFinalisedOut > 0) THEN IdIssue END) AS IssuesWithQty
        FROM stk._uvIssueQuantities
        WHERE IssSprayExecutionId = ?
    """, execution_id)
    issue_stats = cur.fetchone() or type('S', (), {'TotalIssues': 0, 'IssuesWithUnfinalisedQty': 0, 'IssuesWithQty': 0})

    execution_can_finalize = not bool(execution_row.SprExecFinalised) and bool(issue_stats.TotalIssues) and not bool(issue_stats.IssuesWithUnfinalisedQty)
    execution_can_delete = not bool(execution_row.SprExecFinalised) and not bool(issue_stats.IssuesWithQty)

    execution.update({
        "can_finalize": execution_can_finalize,
        "can_delete": execution_can_delete
    })

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
    --Select *
    FROM 
    (
        SELECT 
            EXE.IdSprExec,
            LIN.SprayLineStkId,
            LIN.SprayLineUoMId,
            SUM(LIN.SprayLineTotalQty) AS RecommendedQty
        FROM agr.SprayExecution EXE
        JOIN agr.SprayHeader HEA 
            ON HEA.SprayHExecutionId = EXE.IdSprExec
        JOIN agr.SprayLines LIN 
            ON LIN.SprayLineHeaderId = HEA.IdSprayH
        GROUP BY EXE.IdSprExec, LIN.SprayLineStkId, LIN.SprayLineUoMId
    ) REC
    LEFT JOIN stk._uvIssueQuantities QTY
        ON REC.IdSprExec = QTY.IssSprayExecutionId
    AND REC.SprayLineStkId = QTY.IssLineStockLink
    JOIN cmn._uvStockItems STK 
        ON STK.StockLink = REC.SprayLineStkId
    JOIN cmn._uvUOM UOM 
        ON UOM.idUnits = REC.SprayLineUoMId
    WHERE REC.IdSprExec = ?
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

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form

    start_date_time = data.get('start_date_time')
    end_date_time = data.get('end_date_time')
    weather = data.get('weather')

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
            SprayHWeather = ?,
            SprayHFinalised = 1,
            SprayHStatus = 'FINALISED'
        WHERE IdSprayH = ?
    """, start_dt, end_dt, weather, instruction_id)

    conn.commit()
    conn.close()

    if request.is_json:
        return jsonify({"success": True, "message": "Instruction finalised successfully."})

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


@agri_bp.route("/execution/<int:execution_id>/delete", methods=["POST"])
@login_required
def delete_execution(execution_id):
    conn = create_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if there are any stock issues (finalised or unfinalised quantities)
        cur.execute("""
        SELECT
            COUNT(DISTINCT IdIssue) AS TotalIssues,
            COUNT(DISTINCT CASE 
                WHEN (FinalisedNett > 0 OR UnFinalisedOut > 0) THEN IdIssue 
            END) AS IssuesWithQty
        FROM stk._uvIssueQuantities
        WHERE IssSprayExecutionId = ?
        """, execution_id)
        
        result = cur.fetchone()
        if result and result.IssuesWithQty > 0:
            conn.close()
            return jsonify({"success": False, "message": "Cannot delete execution: There are stock issues with finalised or unfinalised quantities. Please delete the stock issues first."}), 400
        
        # Set SprayHExecutionId to null for all linked spray headers
        cur.execute("""
            UPDATE agr.SprayHeader
            SET SprayHExecutionId = NULL
            WHERE SprayHExecutionId = ?
        """, execution_id)
        
        # Delete the execution
        cur.execute("""
            DELETE FROM agr.SprayExecution
            WHERE IdSprExec = ?
        """, execution_id)
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Execution deleted successfully"})
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error deleting execution: {str(e)}"}), 500