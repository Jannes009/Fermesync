
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
import math
from .spray_recommendation import calculate_spray_mixes

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
            HEA.SprayHOperator,
            HEA.SprayHWeather,
            HEA.SprayHApplicationType,
            HEA.SprayHMethodId
        FROM agr.SprayHeader HEA
        WHERE HEA.IdSprayH = ?
    """, spray_id)

    header = cur.fetchone()

    # fetch linked project codes and total hectares plus per-project breakdown
    cur.execute("""
        SELECT p.ProjectCode, ISNULL(sp.SprayPHa, 0) AS SprayPHa, ISNULL(sp.SprayPWaterPerHa, 0) AS SprayPWaterPerHa
        FROM agr.SprayProjects sp
        JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        WHERE sp.SprayPSprayId = ?
    """, spray_id)
    proj_rows = cur.fetchall()
    project_list = [
        {"project_code": row.ProjectCode, "ha": float(row.SprayPHa or 0), "water_per_ha": float(row.SprayPWaterPerHa or 0)}
        for row in proj_rows
    ]
    print(project_list)
    total_ha = sum([p["ha"] for p in project_list])

    cur.execute("""
        SELECT SprayPProjectId
        FROM agr.SprayProjects
        WHERE SprayPSprayId = ?
    """, spray_id)
    project_ids = [r.SprayPProjectId for r in cur.fetchall()]

    conn.close()

    return jsonify({
            "spray_date": str(header.SprayHDate),
            "spray_week": header.SprayHWeek,
            "projects": project_list,
            "total_ha": total_ha,
            "project_ids": project_ids,
            "application_type": header.SprayHApplicationType,
            "operator": header.SprayHOperator,
            "weather": header.SprayHWeather,
            "method_id": header.SprayHMethodId,
            "spray_no": header.SprayHNo,
            "spray_description": header.SprayHDescription
    })

@agri_bp.route("/spray/<int:spray_id>/spray_lines", methods=["GET"])
@login_required
def get_spray_lines(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT SprayHApplicationType FROM agr.SprayHeader WHERE IdSprayH = ?
    """, spray_id)
    row = cur.fetchone()
    application_type = row.SprayHApplicationType
    lines = []
    if application_type == 'spray':
        cur.execute("""
            SELECT LIN.SprayLineStkId, EVOSTK.StockCode, LIN.SprayLineQtyPerHa, LIN.SprayLineQtyPer100L, UOM.cUnitCode
            FROM [agr].SprayLines LIN
            JOIN [agr].SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
            JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
            WHERE LIN.SprayLineHeaderId = ?
        """, spray_id)
        lines = [
            {"stock_id": row.SprayLineStkId,
             "stock_code": row.StockCode,
             "qty_per_ha": float(row.SprayLineQtyPerHa) if row.SprayLineQtyPerHa is not None else None,
             "qty_per_100l": float(row.SprayLineQtyPer100L) if row.SprayLineQtyPer100L is not None else None,
             "uom": row.cUnitCode
            }
            for row in cur.fetchall()
        ]
    elif application_type == 'direct':
        cur.execute("""
            SELECT LIN.SprayLineStkId, EVOSTK.StockCode, LIN.SprayLineQtyPerHa, UOM.cUnitCode
            FROM [agr].SprayLines LIN
            JOIN [agr].SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
            JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
            WHERE LIN.SprayLineHeaderId = ?
        """, spray_id)
        lines = [
            {"stock_id": row.SprayLineStkId,
             "stock_code": row.StockCode,
             "qty_per_ha": float(row.SprayLineQtyPerHa) if row.SprayLineQtyPerHa is not None else None,
             "uom": row.cUnitCode
            }
            for row in cur.fetchall()
        ]
    return jsonify(lines)



@agri_bp.route("/spray/<int:spray_id>/spray_mix_lines", methods=["GET"])
@login_required
def get_spray_mix_lines(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT SprayHApplicationType FROM agr.SprayHeader WHERE IdSprayH = ?
    """, spray_id)
    row = cur.fetchone()
    application_type = row.SprayHApplicationType
    lines = []
    if application_type == 'spray':
        cur.execute("""
            SELECT LIN.SprayMixLineStockId, EVOSTK.StockCode, STK.ChemStockActiveIngr, STK.ChemStockReason, STK.ChemStockWitholdingPeriod,
                   LIN.SprayMixLineQty, UOM.cUnitCode, SME.SprayMixNumber, SME.SprayMixWater, SME.SprayMixHa,
                   SM.SprayMethodName, SM.SprayMethodTankSize
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
            {"stock_id": row.SprayMixLineStockId,
             "stock_code": row.StockCode,
             "active_ingr": row.ChemStockActiveIngr,
             "reason": row.ChemStockReason,
             "qty": float(row.SprayMixLineQty),
             "uom": row.cUnitCode,
             "withholding_period": row.ChemStockWitholdingPeriod,
             "mix_number": row.SprayMixNumber,
             "water": float(row.SprayMixWater),
             "mix_ha": float(row.SprayMixHa),
             "method_name": row.SprayMethodName,
             "method_tank_size": float(row.SprayMethodTankSize) if row.SprayMethodTankSize is not None else None
            }
            for row in cur.fetchall()
        ]
    elif application_type == 'direct':
        cur.execute("""
            SELECT LIN.SprayLineStkId, EVOSTK.StockCode, STK.ChemStockActiveIngr, STK.ChemStockReason, STK.ChemStockWitholdingPeriod,
                   LIN.SprayLineQtyPerHa, UOM.cUnitCode, SUM(SPJ.SprayPHa) AS TotalHa,
                   SM.SprayMethodName, SM.SprayMethodTankSize
            FROM [agr].SprayLines LIN
            JOIN [agr].SprayHeader HEA ON LIN.SprayLineHeaderId = HEA.IdSprayH
            LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = HEA.SprayHMethodId
            JOIN [agr].SprayProjects SPJ ON SPJ.SprayPSprayId = HEA.IdSprayH
            JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
            LEFT JOIN [agr].[ChemStock] STK ON STK.IdChemStock = LIN.SprayLineStkId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
            WHERE HEA.IdSprayH = ?
            GROUP BY LIN.SprayLineStkId, EVOSTK.StockCode, STK.ChemStockActiveIngr, STK.ChemStockReason, STK.ChemStockWitholdingPeriod, LIN.SprayLineQtyPerHa, UOM.cUnitCode, SM.SprayMethodName, SM.SprayMethodTankSize
        """, spray_id)
        lines = [
            {"stock_id": row.SprayLineStkId,
             "stock_code": row.StockCode,
             "active_ingr": row.ChemStockActiveIngr,
             "reason": row.ChemStockReason,
             "qty_per_ha": float(row.SprayLineQtyPerHa),
             "total_qty": float(row.SprayLineQtyPerHa) * float(row.TotalHa),
             "uom": row.cUnitCode,
             "withholding_period": row.ChemStockWitholdingPeriod,
             "method_name": row.SprayMethodName,
             "method_tank_size": float(row.SprayMethodTankSize) if row.SprayMethodTankSize is not None else None
            }
            for row in cur.fetchall()
        ]
        print(lines)


    conn.close()
    return lines


@agri_bp.route("/spray/recalculate", methods=["POST"])
@login_required
def recalculate_spray():

    data = request.get_json() or {}
    spray_id = data.get("spray_id")
    method_id = data.get("method_id")
    lines = data.get("lines", [])

    # calculate total hectares for this spray from linked projects
    total_ha = 0
    if spray_id:
        conn = create_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT SUM(sp.SprayPHa)
            FROM agr.SprayProjects sp
            WHERE sp.SprayPSprayId = ?
        """, spray_id)
        total_ha = cur.fetchone()[0] or 0
        conn.close()

    # if we have a spray id, fetch per-100L product lines from this spray recommendation
    if spray_id:
        conn = create_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT SprayLineStkId, SprayLineQtyPer100L
            FROM agr.SprayLines
            WHERE SprayLineHeaderId = ?
        """, spray_id)
        spray_lines = cur.fetchall()
        conn.close()

        lines = []
        spray_lines = spray_lines or []
        for line in spray_lines:
            if line.SprayLineQtyPer100L is None:
                continue
            lines.append({
                "stock_id": line.SprayLineStkId,
                "qty_per_100l": float(line.SprayLineQtyPer100L)
            })

    # use method water per ha to compute total water for spray recalc
    total_water = 0
    if method_id:
        conn = create_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT SprayMethodWaterPerHa
            FROM agr.SprayMethod
            WHERE IdSprayMethod = ?
        """, method_id)
        row = cur.fetchone()
        if row and row[0] is not None:
            total_water = float(row[0]) * float(total_ha or 0)
        conn.close()

    result = calculate_spray_mixes(
        method_id=method_id,
        total_ha=total_ha,
        total_water=total_water,
        lines=lines,
        application_type='spray'
    )

    return jsonify(result)

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


@agri_bp.route("/spray/<int:spray_id>/issue_stock", methods=["GET"])
@login_required
def issue_stock_for_spray(spray_id):

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # compute total hectares from projects
        cursor.execute("""
            SELECT SUM(sp.SprayPHa)
            FROM agr.SprayProjects sp
            WHERE sp.SprayPSprayId = ?
        """, spray_id)
        total_ha = cursor.fetchone()[0] or 0

        cursor.execute("""
        SELECT 
            LIN.SprayLineStkId,
            LIN.SprayLineQtyPerHa,
            LIN.SprayLineQtyPer100L,
            ISNULL(QTY.QtyOnHand, 0) QtyAvailable,
            HEA.SprayHWhseId
        FROM agr.SprayLines LIN
        JOIN agr.SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
        LEFT JOIN stk._uvInventoryQty QTY 
            ON QTY.StockLink = LIN.SprayLineStkId 
            AND QTY.WhseLink = HEA.SprayHWhseId
        WHERE LIN.SprayLineHeaderId = ?
        """, spray_id)

        raw_lines = cursor.fetchall()

        if not raw_lines:
            return jsonify({
                "success": False,
                "message": "No stock lines found for this spray recommendation."
            }), 400

        shortages = []
        lines = []
        for line in raw_lines:
            per_ha = line.SprayLineQtyPerHa
            per_100l = line.SprayLineQtyPer100L if hasattr(line, 'SprayLineQtyPer100L') else None
            if per_ha is not None and per_ha != 0:
                qty_to_be = per_ha * total_ha
            elif per_100l is not None and total_ha > 0:
                # approximate per ha from total water if spray method provided? fallback to 0
                qty_to_be = 0
            else:
                qty_to_be = 0
            lines.append({
                "product_link": line.SprayLineStkId,
                "qty": float(qty_to_be)
            })
            if qty_to_be > line.QtyAvailable:
                shortages.append({
                    "product_link": line.SprayLineStkId,
                    "required": float(qty_to_be),
                    "available": float(line.QtyAvailable)
                })

        if shortages:
            return jsonify({
                "success": False,
                "message": "Not enough stock available for one or more products.",
                "shortages": shortages
            }), 400

        # -----------------------------
        # SUCCESS
        # -----------------------------
        # collect warehouse and project info
        cursor.execute("""
            SELECT SprayHWhseId FROM agr.SprayHeader WHERE IdSprayH = ?
        """, spray_id)
        warehouse = cursor.fetchone()[0]

        cursor.execute("""
            SELECT STRING_AGG(ProjectCode, ', ')
            FROM agr.SprayProjects sp
            JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
            WHERE sp.SprayPSprayId = ?
        """, spray_id)
        projects_str = cursor.fetchone()[0] or ""

        cursor.execute("""
            SELECT SprayPProjectId FROM agr.SprayProjects WHERE SprayPSprayId = ?
        """, spray_id)
        project_ids = [r.SprayPProjectId for r in cursor.fetchall()]

        return jsonify({
            "success": True,
            "warehouse": warehouse,
            "projects": project_ids,
            "project": project_ids[0] if project_ids else None,
            "lines": lines
        })


    except Exception as ex:
        return jsonify({
            "success": False,
            "message": str(ex)
        }), 400