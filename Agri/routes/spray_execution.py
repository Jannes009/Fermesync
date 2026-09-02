from datetime import datetime
from flask import render_template, request, redirect, url_for, jsonify, abort
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


@agri_bp.route("/spray-executions-summary", methods=["GET"])
@login_required
def spray_executions_summary():
    if "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()

    whse_ids = tuple(current_user.warehouses or [])
    if not whse_ids:
        return jsonify([])

    placeholders = ','.join('?' for _ in whse_ids)

    cur.execute(f"""
        SELECT
            EXE.IdSprExec,
            HEA.IdSprayH,
            HEA.SprayHNo,
            HEA.SprayHDescription,
            HEA.SprayHWhseId,
            People.PersonName,
            EXE.SprExecFinalised,
            SP.SprayPBlockNo,
            FRM.FarmName,
            EXE.SprExecDate
        FROM agr.SprayExecution EXE
        JOIN agr.SprayHeader HEA
            ON HEA.SprayHExecutionId = EXE.IdSprExec
        JOIN [agr].[SprayProjects] SP on SP.SprayPSprayId = HEA.IdSprayH
        JOIN [agr].[ProjectAttributes] PA on PA.ProjAttrProjectId = SP.SprayPProjectId
        JOIN [agr].Farm FRM on FRM.IdFarm = PA.ProjAttrFarmId
        LEFT JOIN agr.People People on People.IdPerson = EXE.SprExecResponsiblePerson
        WHERE HEA.SprayHWhseId IN ({placeholders})
        ORDER BY EXE.SprExecDate DESC, EXE.IdSprExec DESC
    """, whse_ids)

    executions = {}
    for row in cur.fetchall():
        exec_id = row.IdSprExec
        if exec_id not in executions:
            executions[exec_id] = {
                "id": exec_id,
                "date": row.SprExecDate,
                "responsible_person": row.PersonName,
                "finalised": bool(row.SprExecFinalised),
                "farm_names": [],
                "block_numbers": [],
                "descriptions": [],
                "spray_nos": []
            }

        if row.IdSprayH:
            description = (row.SprayHDescription or '').strip()
            if description:
                executions[exec_id]["descriptions"].append(description)

            block_no = row.SprayPBlockNo
            if block_no not in (None, ''):
                executions[exec_id]["block_numbers"].append(str(block_no))

            farm_name = (row.FarmName or '').strip()
            if farm_name:
                executions[exec_id]["farm_names"].append(farm_name)

            spray_no = (row.SprayHNo or '').strip()
            if spray_no:
                executions[exec_id]["spray_nos"].append(spray_no)

    execution_rows = []
    all_farms = []
    all_blocks = []
    for execution in executions.values():
        unique_descriptions = []
        for description in execution["descriptions"]:
            if description and description not in unique_descriptions:
                unique_descriptions.append(description)

        unique_spray_nos = []
        for spray_no in execution["spray_nos"]:
            if spray_no and spray_no not in unique_spray_nos:
                unique_spray_nos.append(spray_no)

        unique_farms = []
        for farm_name in execution["farm_names"]:
            if farm_name and farm_name not in unique_farms:
                unique_farms.append(farm_name)
                if farm_name not in all_farms:
                    all_farms.append(farm_name)

        unique_blocks = []
        for block_no in execution["block_numbers"]:
            if block_no and block_no not in unique_blocks:
                unique_blocks.append(block_no)
                if block_no not in all_blocks:
                    all_blocks.append(block_no)

        execution_rows.append({
            "id": execution["id"],
            "date": format_datetime(execution["date"]),
            "responsible_person": execution["responsible_person"] or '-',
            "finalised": execution["finalised"],
            "farm_names": unique_farms,
            "farm_name_text": ', '.join(unique_farms) if unique_farms else '-',
            "block_numbers": unique_blocks,
            "block_text": ', '.join(unique_blocks) if unique_blocks else '-',
            "description": ', '.join(unique_descriptions) if unique_descriptions else '-',
            "spray_no": ', '.join(unique_spray_nos) if unique_spray_nos else '-',
            "recommendations_count": len(unique_descriptions)
        })

    conn.close()
    return render_template("spray_execution_summary.html",
                           executions=execution_rows,
                            farm_filter_options=sorted(all_farms, key=str.lower),
                            block_filter_options=sorted(all_blocks, key=str.lower),)


@agri_bp.route("/execution/<int:execution_id>", methods=["GET"])
@login_required
def view_execution(execution_id):
    if "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
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
        "responsible_person_id": execution_row.SprExecResponsiblePerson,
        "responsible_person": execution_row.PersonName,
        "warehouse": execution_row.WhseDescription,
        "finalised": execution_row.SprExecFinalised
    }

    # Get spray instructions in this execution
    cur.execute("""
        SELECT h.IdSprayH, h.SprayHNo, h.SprayHDescription, h.SprayHWeek, h.SprayHStatus,
             h.SprayHDate, h.SprayHFinalised,
             ISNULL(h.SprayHRequireDateTime, 1) AS SprayHRequireDateTime,
             ISNULL(h.SprayHRequireWeather, 1) AS SprayHRequireWeather
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
            "require_date_time": bool(row.SprayHRequireDateTime),
            "require_weather": bool(row.SprayHRequireWeather),
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

    execution_can_finalize = (
        not bool(execution_row.SprExecFinalised)
        and bool(execution_row.SprExecResponsiblePerson)
        and bool(issue_stats.TotalIssues)
        and not bool(issue_stats.IssuesWithUnfinalisedQty)
    )
    if bool(execution_row.SprExecFinalised):
        finalize_block_reason = "This execution is already finalised."
    elif not bool(execution_row.SprExecResponsiblePerson):
        finalize_block_reason = "Assign a responsible person before finalising."
    elif not bool(issue_stats.TotalIssues):
        finalize_block_reason = "Issue stock before finalising this instruction."
    elif bool(issue_stats.IssuesWithUnfinalisedQty):
        finalize_block_reason = "Finalise or return all outstanding stock issues before finalising this instruction."
    else:
        finalize_block_reason = None
    execution_can_delete = not bool(execution_row.SprExecFinalised) and not bool(issue_stats.IssuesWithQty)

    execution.update({
        "can_finalize": execution_can_finalize,
        "finalize_block_reason": finalize_block_reason,
        "can_delete": execution_can_delete
    })

    # Get stock movements for this execution
    # This assumes there's a table that tracks stock movements for executions
    # You might need to adjust this based on your actual database schema
    cur.execute("""
    SELECT 
        QTY.IdIssue,
        REC.SprayLineStkId,
        QTY.IssTimeStamp,
        QTY.IssFinalisedTimeStamp,
        QTY.QtyOut,
        QTY.QtyIn,
        QTY.FinalisedNett,
        QTY.UnFinalisedOut,
        UOM.cUnitCode,
        EVOSTK.StockDescription,
		ACT.ChemActIngredient,
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
    LEFT JOIN stk._uvIssueQuantities QTY  ON REC.IdSprExec = QTY.IssSprayExecutionId AND REC.SprayLineStkId = QTY.IssLineStockLink
	JOIN cmn._uvStockItems EVOSTK on EVOSTK.StockLink = REC.SprayLineStkId
    JOIN agr.ChemStock STK ON STK.ChemStockLink = REC.SprayLineStkId
	JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
    JOIN cmn._uvUOM UOM 
        ON UOM.idUnits = REC.SprayLineUoMId
    WHERE REC.IdSprExec = ?
    """, execution_id)

    stock_dict = {}

    for row in cur.fetchall():
        stock_key = row.SprayLineStkId   # safer than description

        if stock_key not in stock_dict:
            stock_dict[stock_key] = {
                "stock_link": stock_key,
                "stock_description": row.StockDescription,
                "active_ingredient": row.ChemActIngredient,
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
    if "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
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

@agri_bp.route("/execution/responsible-persons/<int:execution_id>", methods=["GET"])
@login_required
def get_responsible_persons(execution_id):
    if "SPRAY_EXEC_FINALISE" not in current_user.permissions and "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
    
    conn = create_db_connection()
    cur = conn.cursor()
    


    cur.execute(f"""
        Select DISTINCT P.IdPerson, P.PersonName
        from agr.SprayExecution EXE
        JOIN agr.SprayHeader HEA on HEA.SprayHExecutionId = EXE.IdSprExec
        JOIN agr.SprayProjects SP ON SP.SprayPSprayId = HEA.IdSprayH
        JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = SP.SprayPProjectId
        JOIN agr.FarmPeople FP ON FP.FarmId = PA.ProjAttrFarmId
        JOIN agr.People P on P.IdPerson = FP.PersonId
        Where PersonSprayExecutionResponsible = 1 and EXE.IdSprExec = ?
    """, execution_id)

    
    persons = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "persons": persons})

@agri_bp.route("/execution/<int:execution_id>/update_responsible_person", methods=["POST"])
@login_required
def update_responsible_person(execution_id):
    if "SPRAY_EXEC_FINALISE" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()

    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
        else:
            data = request.form

        person_id_raw = data.get('person_id')
        if person_id_raw in (None, '', 'None', 'null'):
            responsible_person_id = None
        else:
            try:
                responsible_person_id = int(person_id_raw)
            except (TypeError, ValueError):
                conn.close()
                return jsonify({"success": False, "message": "Invalid responsible person."}), 400

        cur.execute("SELECT SprExecFinalised FROM agr.SprayExecution WHERE IdSprExec = ?", execution_id)
        execution_row = cur.fetchone()
        if not execution_row:
            conn.close()
            return jsonify({"success": False, "message": "Execution not found."}), 404
        if bool(execution_row.SprExecFinalised):
            conn.close()
            return jsonify({"success": False, "message": "Cannot update the responsible person on a finalised execution."}), 400

        cur.execute(
            "UPDATE agr.SprayExecution SET SprExecResponsiblePerson = ? WHERE IdSprExec = ?",
            responsible_person_id,
            execution_id,
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Responsible person updated."})
    except Exception as exc:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error updating responsible person: {str(exc)}"}), 500


@agri_bp.route("/execution/<int:execution_id>/finalize", methods=["POST"])
@login_required
def finalize_execution(execution_id):
    if "SPRAY_EXEC_FINALISE" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT IdSprExec, SprExecFinalised, SprExecResponsiblePerson
            FROM agr.SprayExecution
            WHERE IdSprExec = ?
        """, execution_id)
        execution_row = cur.fetchone()
        if not execution_row:
            conn.close()
            return jsonify({"success": False, "message": "Execution not found."}), 404
        if bool(execution_row.SprExecFinalised):
            conn.close()
            return jsonify({"success": False, "message": "Execution is already finalised."}), 400
        if execution_row.SprExecResponsiblePerson in (None, ''):
            conn.close()
            return jsonify({"success": False, "message": "Assign a responsible person before finalising this execution."}), 400

        cur.execute("""
            SELECT COUNT(DISTINCT IdIssue) AS TotalIssues,
                   COUNT(DISTINCT CASE WHEN UnFinalisedOut > 0 THEN IdIssue END) AS IssuesWithUnfinalisedQty
            FROM stk._uvIssueQuantities
            WHERE IssSprayExecutionId = ?
        """, execution_id)
        issue_stats = cur.fetchone()
        if not issue_stats or not int(issue_stats.TotalIssues or 0):
            conn.close()
            return jsonify({"success": False, "message": "Cannot finalise execution without any stock issues."}), 400
        if int(issue_stats.IssuesWithUnfinalisedQty or 0) > 0:
            conn.close()
            return jsonify({"success": False, "message": "Cannot finalise execution while there are unfinalised stock issues."}), 400

        cur.execute("""
            UPDATE agr.SprayExecution
            SET SprExecFinalised = 1,
                SprExecFinalisedTimestamp = GETDATE()
            WHERE IdSprExec = ?
            AND ISNULL(SprExecFinalised, 0) = 0
        """, execution_id)
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Execution finalised successfully."})
    except Exception as exc:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error finalising execution: {str(exc)}"}), 500


@agri_bp.route("/execution/<int:execution_id>/update_instruction/<int:instruction_id>", methods=["POST"])
@login_required
def update_instruction(execution_id, instruction_id):
    if "SPRAY_EXEC_FINALISE" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()

    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form

    cur.execute("SELECT SprExecFinalised, SprExecResponsiblePerson FROM agr.SprayExecution WHERE IdSprExec = ?", execution_id)
    execution_row = cur.fetchone()
    if not execution_row:
        conn.close()
        return jsonify({"success": False, "message": "Execution not found."}), 404
    if bool(execution_row.SprExecFinalised):
        conn.close()
        return jsonify({"success": False, "message": "This execution is already finalised."}), 400
    if execution_row.SprExecResponsiblePerson in (None, ''):
        conn.close()
        return jsonify({"success": False, "message": "Assign a responsible person before finalising an instruction."}), 400

    start_date_time = data.get('start_date_time')
    end_date_time = data.get('end_date_time')
    weather = data.get('weather')

    cur.execute("""
        SELECT ISNULL(SprayHRequireDateTime, 1), ISNULL(SprayHRequireWeather, 1)
        FROM agr.SprayHeader
        WHERE IdSprayH = ? AND SprayHExecutionId = ?
    """, instruction_id, execution_id)
    requirement_row = cur.fetchone()
    if not requirement_row:
        conn.close()
        return jsonify({"success": False, "message": "Instruction not found in this execution."}), 404

    require_date_time = bool(requirement_row[0])
    require_weather = bool(requirement_row[1])

    if require_date_time and (not start_date_time or not end_date_time):
        conn.close()
        return jsonify({"success": False, "message": "Start and end date/time are required for this instruction."}), 400

    if require_weather and not weather:
        conn.close()
        return jsonify({"success": False, "message": "Weather is required for this instruction."}), 400

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

    cur.execute("""
        UPDATE EXE
        SET
            SprExecFinalised = 1,
            SprExecFinalisedTimestamp = GETDATE()
        FROM agr.SprayExecution EXE
        WHERE EXE.IdSprExec = ?
        AND ISNULL(EXE.SprExecFinalised, 0) = 0          -- only if not already finalised
        AND NOT EXISTS (
                SELECT 1
                FROM agr.SprayHeader HEA
                WHERE HEA.SprayHExecutionId = EXE.IdSprExec
                AND ISNULL(HEA.SprayHFinalised, 0) = 0   -- still has un-finalised sprays
            );
      """, execution_id)

    conn.commit()
    conn.close()

    if request.is_json:
        return jsonify({"success": True, "message": "Instruction finalised successfully."})

    return redirect(url_for('agri.view_execution', execution_id=execution_id))


@agri_bp.route("/execution/<int:execution_id>/delete", methods=["POST"])
@login_required
def delete_execution(execution_id):
    if "SPRAY_EXEC_CREATE" not in current_user.permissions:
        abort(403)
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