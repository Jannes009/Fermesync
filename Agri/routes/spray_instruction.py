
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
import math

@agri_bp.route("/spray/<int:spray_id>")
@login_required
def spray_execution_page(spray_id):
    # render the HTML page; data loaded via separate API
    return render_template("spray_instruction.html", spray_id=spray_id)

@agri_bp.route("/fetch_spray_instructions", methods=["GET"])
@login_required
def fetch_spray_instructions():
    """Fetch all spray instructions for the user to select from"""
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT IdSprayH, SprayHDate
        FROM agr.SprayHeader
        ORDER BY SprayHDate DESC
    """)
    spray_headers = cur.fetchall()
    conn.close()

    sprays_list = [
        {
            "id": header.IdSprayH,
            "name": f"Spray {header.IdSprayH} - {header.SprayHDate}"
        }
        for header in spray_headers
    ]
    
    return jsonify({"sprays": sprays_list})


@agri_bp.route("/spray/<int:spray_id>/spray_header", methods=["GET"])
@login_required
def get_spray_header(spray_id):

    conn = create_db_connection()
    cur = conn.cursor()

    # HEADER
    cur.execute("""
    SELECT 
        HEA.SprayHNo,
        HEA.SprayHDescription,
        HEA.SprayHDate,
        HEA.SprayHWeek,
        HEA.SprayHWhseId,
        WHSE.Code,
        WHSE.Name,
        HEA.SprayHWeather,
        HEA.SprayLineDoseBasis,
        HEA.SprayHMethodId,
        HEA.SprayHStartDateTime,
        SprayHEndDateTime,
        SprayHExecutionId,
		EXE.SprExecFinalised,
        SprayHWaterPerTank,
        SprayHTotalWater,
        SprayHTotalHa,
        SprayHMix,
        SprayHStatus,
        SprayHScouting,
        SprayHFinalised,
		CASE 
			WHEN SUM(ISNULL(ISS.QtyOut, 0)) OVER (PARTITION BY HEA.IdSprayH) > 0 
			THEN 1 
			ELSE 0 
		END AS IssuesExist
    FROM agr.SprayHeader HEA
    JOIN cmn._uvWhseMst WHSE on WHSE.WhseLink = HEA.SprayHWhseId
	LEFT JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
	LEFT JOIN stk._uvIssueQuantities ISS on ISS.IssSprayExecutionId = EXE.IdSprExec
    WHERE HEA.IdSprayH = ?
    """, spray_id)

    header = cur.fetchone()

    # fetch linked project codes and total hectares plus per-project breakdown
    cur.execute("""
        SELECT p.ProjectCode, ISNULL(sp.SprayPHa, 0) AS SprayPHa, ISNULL(sp.SprayPWaterPerHa, 0) AS SprayPWaterPerHa, ISNULL(SprayPTotalWater, 0) AS SprayPTotalWater
        FROM agr.SprayProjects sp
        JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        WHERE sp.SprayPSprayId = ?
    """, spray_id)
    proj_rows = cur.fetchall()
    project_list = [
        {"project_code": row.ProjectCode, "ha": float(row.SprayPHa or 0), "water_per_ha": float(row.SprayPWaterPerHa or 0), "total_water": float(row.SprayPTotalWater or 0)}
        for row in proj_rows
    ]
    print(project_list)
    conn.close()

    return jsonify({
            "spray_date": str(header.SprayHDate),
            "spray_week": header.SprayHWeek,
            "projects": project_list,
            "total_ha": header.SprayHTotalHa,
            "dose_basis": header.SprayLineDoseBasis,
            "weather": header.SprayHWeather,
            "method_id": header.SprayHMethodId,
            "spray_no": header.SprayHNo,
            "spray_description": header.SprayHDescription,
            "warehouse": {
                "id": header.SprayHWhseId,
                "code": header.Code,
                "name": header.Name
            },
            "water_per_tank": float(header.SprayHWaterPerTank) if header.SprayHWaterPerTank is not None else None,
            "total_water": float(header.SprayHTotalWater) if header.SprayHTotalWater is not None else None,
            "start_datetime": str(header.SprayHStartDateTime) if header.SprayHStartDateTime is not None else None,
            "end_datetime": str(header.SprayHEndDateTime) if header.SprayHEndDateTime is not None else None,
            "mix": bool(header.SprayHMix) if header.SprayHMix is not None else None,
            "execution_id": header.SprayHExecutionId if header.SprayHExecutionId is not None else None,
            "execution_finalised": bool(header.SprExecFinalised) if header.SprExecFinalised is not None else None,
            "status": header.SprayHStatus,
            "scouting": header.SprayHScouting if header.SprayHScouting is not None else None,
            "finalised": bool(header.SprayHFinalised) if header.SprayHFinalised is not None else None,
            "issues_exist": bool(header.IssuesExist) if header.IssuesExist is not None else None
    })

@agri_bp.route("/spray/<int:spray_id>/spray_lines", methods=["GET"])
@login_required
def get_spray_lines(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT SprayLineDoseBasis FROM agr.SprayHeader WHERE IdSprayH = ?
    """, spray_id)
    row = cur.fetchone()
    dose_basis = row.SprayLineDoseBasis
    lines = []
    cur.execute("""
        SELECT LIN.IdSprayLine, LIN.SprayLineStkId, EVOSTK.StockCode, LIN.SprayLineQtyPerHa, LIN.SprayLineQtyPer100L, SprayLineTotalQty, LIN.SprayLineUoMId, UOM.cUnitCode
        FROM [agr].SprayLines LIN
        JOIN [agr].SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
        JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
        LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
        WHERE LIN.SprayLineHeaderId = ?
    """, spray_id)
    lines = [
        {"line_id": row.IdSprayLine,
            "stock_id": row.SprayLineStkId,
            "stock_code": row.StockCode,
            "dose_basis": dose_basis,
            "qty_per_100l": float(row.SprayLineQtyPer100L) if row.SprayLineQtyPer100L is not None else None,
            "qty_per_ha": float(row.SprayLineQtyPerHa) if row.SprayLineQtyPerHa is not None else None,
            "total_qty": float(row.SprayLineTotalQty) if row.SprayLineTotalQty is not None else None,
            "uom_id": row.SprayLineUoMId,
            "uom": row.cUnitCode
        }
        for row in cur.fetchall()
    ]
    return jsonify(lines)



@agri_bp.route("/spray/<int:spray_id>/edit_spray_lines", methods=["POST"])
@login_required
def save_spray_lines(spray_id):
    data = request.get_json(silent=True) or {}
    lines = data.get('lines')
    if not isinstance(lines, list):
        return jsonify({"success": False, "message": "Missing or invalid lines payload."}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    # Check if spray has an execution linked
    cur.execute("""
	Select
		CASE 
			WHEN SUM(ISNULL(ISS.QtyOut, 0)) OVER (PARTITION BY HEA.IdSprayH) > 0 
			THEN 1 
			ELSE 0 
		END AS IssuesExist
    FROM agr.SprayHeader HEA
	LEFT JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
	LEFT JOIN stk._uvIssueQuantities ISS on ISS.IssSprayExecutionId = EXE.IdSprExec
    WHERE HEA.IdSprayH = ?
    """, spray_id)
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Spray recommendation not found."}), 404
    
    if row.IssuesExist == 1:
        conn.close()
        return jsonify({"success": False, "message": "Cannot edit spray lines: this recommendation is linked to an execution."}), 400

    cur.execute("""
        SELECT SprayLineDoseBasis
        FROM agr.SprayHeader
        WHERE IdSprayH = ?
    """, spray_id)
    header_row = cur.fetchone()
    dose_basis = header_row.SprayLineDoseBasis if header_row and header_row.SprayLineDoseBasis is not None else 'PER_HA'

    def as_number(value):
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def as_float(value):
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    try:
        cur.execute("SELECT IdSprayLine FROM agr.SprayLines WHERE SprayLineHeaderId = ?", spray_id)
        existing_ids = {row.IdSprayLine for row in cur.fetchall()}
        incoming_ids = set()

        for line in lines:
            line_id = as_number(line.get('line_id'))
            if line_id is not None:
                incoming_ids.add(line_id)

        delete_ids = existing_ids - incoming_ids
        for line_id in delete_ids:
            cur.execute("DELETE FROM agr.SprayLines WHERE IdSprayLine = ? AND SprayLineHeaderId = ?", line_id, spray_id)

        for line in lines:
            line_id = as_number(line.get('line_id'))
            stock_id = as_number(line.get('stock_id'))
            qty_per_100l = as_float(line.get('qty_per_100l'))
            qty_per_ha = as_float(line.get('qty_per_ha'))
            total_qty = as_float(line.get('total_qty'))
            uom_id = as_number(line.get('uom_id'))

            if line_id is not None:
                cur.execute(
                    """
                    UPDATE agr.SprayLines
                    SET SprayLineStkId = ?, SprayLineQtyPer100L = ?, SprayLineQtyPerHa = ?, SprayLineUoMId = ?, SprayLineTotalQty = ?
                    WHERE IdSprayLine = ? AND SprayLineHeaderId = ?
                    """,
                    stock_id, qty_per_100l, qty_per_ha, uom_id, total_qty, line_id, spray_id
                )
            else:
                cur.execute(
                    """
                    INSERT INTO agr.SprayLines (
                        SprayLineHeaderId,
                        SprayLineStkId,
                        SprayLineQtyPer100L,
                        SprayLineQtyPerHa,
                        SprayLineUoMId,
                        SprayLineTotalQty
                    )
                    VALUES (?,?,?,?,?,?)
                    """,
                    spray_id, stock_id, qty_per_100l, qty_per_ha, uom_id, total_qty
                )

        # Rebuild mix line quantities for existing spray mixes so database reflects the updated spray lines.
        cur.execute("""
            SELECT IdSprayMix, SprayMixWater, SprayMixHa
            FROM agr.SprayMix
            WHERE SprayMixHeaderId = ?
        """, spray_id)
        mix_rows = cur.fetchall()

        if mix_rows:
            mix_ids = [row.IdSprayMix for row in mix_rows]
            placeholders = ",".join("?" for _ in mix_ids)
            cur.execute(f"DELETE FROM agr.SprayMixLines WHERE SprayMixLineMixId IN ({placeholders})", *mix_ids)

            for mix_row in mix_rows:
                mix_id = mix_row.IdSprayMix
                mix_water = float(mix_row.SprayMixWater or 0)
                mix_ha = float(mix_row.SprayMixHa or 0)

                for line in lines:
                    stock_id = as_number(line.get('stock_id'))
                    if stock_id is None:
                        continue

                    qty_per_100l = as_float(line.get('qty_per_100l')) or 0
                    qty_per_ha = as_float(line.get('qty_per_ha')) or 0
                    uom_id = as_number(line.get('uom_id'))

                    if dose_basis == 'PER_100L':
                        mix_qty = (qty_per_100l / 100.0) * mix_water if mix_water else 0
                    elif dose_basis == 'PER_HA':
                        mix_qty = qty_per_ha * mix_ha if mix_ha else 0
                    else:
                        mix_qty = as_float(line.get('total_qty')) or 0

                    cur.execute(
                        """
                        INSERT INTO agr.SprayMixLines (
                            SprayMixLineMixId,
                            SprayMixLineStockId,
                            SprayMixLineQty,
                            SprayMixLineUoMId
                        )
                        VALUES (?,?,?,?)
                        """,
                        mix_id,
                        stock_id,
                        mix_qty,
                        uom_id
                    )

        conn.commit()
        return jsonify({"success": True})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/edit_spray_header", methods=["POST"])
@login_required
def save_spray_header(spray_id):
    data = request.get_json(silent=True) or {}
    spray_description = data.get('spray_description')
    spray_date = data.get('spray_date')
    spray_week = data.get('spray_week')
    scouting = data.get('scouting')

    conn = create_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE agr.SprayHeader
            SET SprayHDescription = ?, SprayHDate = ?, SprayHWeek = ?, SprayHScouting = ?
            WHERE IdSprayH = ?
            """,
            spray_description, spray_date, spray_week, scouting, spray_id
        )
        conn.commit()
        return jsonify({"success": True, "message": "Header changes saved successfully."})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/cancel", methods=["POST"])
@login_required
def cancel_spray(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT SprayHExecutionId FROM agr.SprayHeader WHERE IdSprayH = ?", spray_id)
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Spray recommendation not found."}), 404

        execution_id = row.SprayHExecutionId
        if execution_id is not None:
            return jsonify({"success": False, "message": "Cannot cancel a spray recommendation that is already linked to an execution."}), 400

        cur.execute(
            "UPDATE agr.SprayHeader SET SprayHStatus = ?, SprayHCancelled = 1 WHERE IdSprayH = ?",
            'CANCELLED', spray_id
        )
        conn.commit()
        return jsonify({"success": True, "message": "Spray recommendation cancelled."})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/spray_mix_lines", methods=["GET"])
@login_required
def get_spray_mix_lines(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()

    lines = []

    cur.execute("""
        SELECT LIN.IdSprayMixLine, LIN.SprayMixLineStockId, EVOSTK.StockCode, STK.ChemStockActiveIngr, STK.ChemStockReason, STK.ChemStockWitholdingPeriod,
                LIN.SprayMixLineQty, UOM.cUnitCode, SME.SprayMixNumber, SME.SprayMixWater, SME.SprayMixHa,
                SM.SprayMethodName
        FROM [agr].SprayMixLines LIN
        JOIN [agr].SprayMix SME ON LIN.SprayMixLineMixId = SME.IdSprayMix
        JOIN agr.SprayHeader SH ON SH.IdSprayH = SME.SprayMixHeaderId
        LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = SH.SprayHMethodId
        JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayMixLineStockId
        LEFT JOIN [agr].[ChemStock] STK ON STK.IdChemStock = LIN.SprayMixLineStockId
        LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayMixLineUoMId
        WHERE SME.SprayMixHeaderId = ?
    """, spray_id)
    lines = [
        {
            "line_id": row.IdSprayMixLine,
            "stock_id": row.SprayMixLineStockId,
            "stock_code": row.StockCode,
            "active_ingr": row.ChemStockActiveIngr,
            "reason": row.ChemStockReason,
            "qty": float(row.SprayMixLineQty),
            "uom": row.cUnitCode,
            "withholding_period": row.ChemStockWitholdingPeriod,
            "mix_number": row.SprayMixNumber,
            "water": float(row.SprayMixWater),
            "mix_ha": float(row.SprayMixHa),
            "method_name": row.SprayMethodName
        }
        for row in cur.fetchall()
    ]

    conn.close()
    return lines


@agri_bp.route("/spray/methods", methods=["GET"])
@login_required
def get_spray_methods():
    conn = create_db_connection()
    cur = conn.cursor()

    # Spray Methods
    cur.execute("""
        SELECT
            sm.IdSprayMethod,
            f.FarmName,
            sm.SprayMethodName,
            sm.SprayMethodWaterPerHa,
            sm.SprayMethodTankSize
        FROM agr.SprayMethod sm
        JOIN agr.Farm f ON f.IdFarm = sm.SprayMethodFarmId
    """)
    spray_methods = cur.fetchall()
    conn.close()
    methods_list = []
    for method in spray_methods:
        methods_list.append({
            "id": method.IdSprayMethod,
            "farm_name": method.FarmName,
            "method_name": method.SprayMethodName,
            "water_per_ha": float(method.SprayMethodWaterPerHa),
            "tank_size": float(method.SprayMethodTankSize)
        })
    return jsonify(methods_list)

@agri_bp.route("/spray/<int:spray_id>/fetch_products", methods=["GET"])
@login_required
def fetch_products_for_spray_whse(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT QTY.StockLink, StockCode, StockDescription, QtyOnHand
    FROM [agr].SprayHeader HEA
    JOIN stk._uvInventoryQty QTY on QTY.WhseLink = HEA.SprayHWhseId
    WHERE HEA.IdSprayH = ?
    """, spray_id)
    products = [{
        "stock_link": row.StockLink,
        "stock_code": row.StockCode,
        "stock_description": row.StockDescription,
        "qty_on_hand": float(row.QtyOnHand)
    } for row in cur.fetchall()]
    conn.close()
    return jsonify(products)

# @agri_bp.route("/spray/<int:spray_id>/issue_stock", methods=["GET"])
# @login_required
# def issue_stock_for_spray(spray_id):

#     conn = create_db_connection()
#     cursor = conn.cursor()

#     try:
#         # compute total hectares from projects
#         cursor.execute("""
#             SELECT SUM(sp.SprayPHa)
#             FROM agr.SprayProjects sp
#             WHERE sp.SprayPSprayId = ?
#         """, spray_id)
#         total_ha = cursor.fetchone()[0] or 0

#         cursor.execute("""
#         SELECT 
#             LIN.SprayLineStkId,
#             LIN.SprayLineQtyPerHa,
#             LIN.SprayLineQtyPer100L,
#             ISNULL(QTY.QtyOnHand, 0) QtyAvailable,
#             HEA.SprayHWhseId
#         FROM agr.SprayLines LIN
#         JOIN agr.SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
#         LEFT JOIN stk._uvInventoryQty QTY 
#             ON QTY.StockLink = LIN.SprayLineStkId 
#             AND QTY.WhseLink = HEA.SprayHWhseId
#         WHERE LIN.SprayLineHeaderId = ?
#         """, spray_id)

#         raw_lines = cursor.fetchall()

#         if not raw_lines:
#             return jsonify({
#                 "success": False,
#                 "message": "No stock lines found for this spray recommendation."
#             }), 400

#         shortages = []
#         lines = []
#         for line in raw_lines:
#             per_ha = line.SprayLineQtyPerHa
#             per_100l = line.SprayLineQtyPer100L if hasattr(line, 'SprayLineQtyPer100L') else None
#             if per_ha is not None and per_ha != 0:
#                 qty_to_be = per_ha * total_ha
#             elif per_100l is not None and total_ha > 0:
#                 # approximate per ha from total water if spray method provided? fallback to 0
#                 qty_to_be = 0
#             else:
#                 qty_to_be = 0
#             lines.append({
#                 "product_link": line.SprayLineStkId,
#                 "qty": float(qty_to_be)
#             })
#             if qty_to_be > line.QtyAvailable:
#                 shortages.append({
#                     "product_link": line.SprayLineStkId,
#                     "required": float(qty_to_be),
#                     "available": float(line.QtyAvailable)
#                 })

#         if shortages:
#             return jsonify({
#                 "success": False,
#                 "message": "Not enough stock available for one or more products.",
#                 "shortages": shortages
#             }), 400

#         # -----------------------------
#         # SUCCESS
#         # -----------------------------
#         # collect warehouse and project info
#         cursor.execute("""
#             SELECT SprayHWhseId FROM agr.SprayHeader WHERE IdSprayH = ?
#         """, spray_id)
#         warehouse = cursor.fetchone()[0]

#         cursor.execute("""
#             SELECT STRING_AGG(ProjectCode, ', ')
#             FROM agr.SprayProjects sp
#             JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
#             WHERE sp.SprayPSprayId = ?
#         """, spray_id)
#         projects_str = cursor.fetchone()[0] or ""

#         cursor.execute("""
#             SELECT SprayPProjectId FROM agr.SprayProjects WHERE SprayPSprayId = ?
#         """, spray_id)
#         project_ids = [r.SprayPProjectId for r in cursor.fetchall()]

#         return jsonify({
#             "success": True,
#             "warehouse": warehouse,
#             "projects": project_ids,
#             "project": project_ids[0] if project_ids else None,
#             "lines": lines
#         })


#     except Exception as ex:
#         return jsonify({
#             "success": False,
#             "message": str(ex)
#         }), 400