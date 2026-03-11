
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

@agri_bp.route("/spray/<int:spray_id>/spray_header", methods=["GET"])
@login_required
def get_spray_header(spray_id):

    conn = create_db_connection()
    cur = conn.cursor()

    # HEADER
    cur.execute("""
        SELECT 
            HEA.SprayHDate,
            HEA.SprayHProjectManagerId,
            HEA.SprayHAgriculturistId,
            HEA.SprayHWhseId,
            HEA.SprayHOperatorId,
            HEA.SprayHWeather,
            MTD.IdSprayMethod,
            MTD.SprayMethodName,
            MTD.SprayMethodTankSize,
            MTD.SprayMethodWaterPerHa
        FROM agr.SprayHeader HEA
        JOIN agr.SprayMethod MTD on MTD.IdSprayMethod = HEA.SprayHMethodId
        WHERE HEA.IdSprayH = ?
    """, spray_id)

    header = cur.fetchone()

    # fetch linked project codes and total hectares
    cur.execute("""
        SELECT STRING_AGG(p.ProjectCode, ', '), ISNULL(SUM(pa.ProjAttrHa),0)
        FROM agr.SprayProjects sp
        JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayProjectProjectId
        LEFT JOIN agr.ProjectAttributes pa ON pa.ProjAttrProjectId = p.ProjectLink
        WHERE sp.SprayProjectSprayId = ?
    """, spray_id)
    proj_info = cur.fetchone()
    project_codes = proj_info[0] or ""
    total_ha = float(proj_info[1] or 0)

    # also collect project ids array
    cur.execute("""
        SELECT SprayProjectProjectId
        FROM agr.SprayProjects
        WHERE SprayProjectSprayId = ?
    """, spray_id)
    project_ids = [r.SprayProjectProjectId for r in cur.fetchall()]

    conn.close()

    return jsonify({
            "spray_date": str(header.SprayHDate),
            "projects": project_codes,
            "project_ids": project_ids,
            "ha": total_ha,
            "manager_id": header.SprayHProjectManagerId,
            "agriculturist_id": header.SprayHAgriculturistId,
            "operator_id": header.SprayHOperatorId,
            "weather": header.SprayHWeather,
            "method_id": header.IdSprayMethod,
            "method_name": header.SprayMethodName,
            "tank_size": float(header.SprayMethodTankSize),
            "water_per_ha": float(header.SprayMethodWaterPerHa)
    })

@agri_bp.route("/spray/<int:spray_id>/spray_lines", methods=["GET"])
@login_required
def get_spray_lines(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        Select LIN.SprayMixLineStockId,  EVOSTK.StockCode, STK.ChemStockActiveIngr, STK.ChemStockReason, STK.ChemStockWitholdingPeriod
        ,LIN.SprayMixLineQty
        ,SprayMixNumber, SprayMixWater, SprayMixHa
        from [agr].SprayMixLines LIN
        JOIN [common].[_uvStockItems] EVOSTK on EVOSTK.StockLink = LIN.SprayMixLineStockId
        JOIN [agr].[ChemStock] STK on STK.IdChemStock = LIN.SprayMixLineStockId
        JOIN [agr].[SprayMix] HEA on LIN.SprayMixLineMixId = HEA.IdSprayMix
        Where HEA.SprayMixHeaderId = ?
    """, spray_id)

    lines = [
        {"stock_id": row.SprayMixLineStockId, 
         "stock_code": row.StockCode, 
         "active_ingr": row.ChemStockActiveIngr, 
         "reason": row.ChemStockReason, 
         "qty": float(row.SprayMixLineQty),
         "withholding_period": row.ChemStockWitholdingPeriod, 
         "mix_number": row.SprayMixNumber, 
         "water": float(row.SprayMixWater),
         "qty_per_ha": float(row.SprayMixHa)}
        for row in cur.fetchall()
    ]

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
            SELECT SUM(pa.ProjAttrHa)
            FROM agr.ProjectAttributes pa
            JOIN agr.SprayProjects sp ON sp.SprayProjectProjectId = pa.ProjAttrProjectId
            WHERE sp.SprayProjectSprayId = ?
        """, spray_id)
        total_ha = cur.fetchone()[0] or 0
        conn.close()

    result = calculate_spray_mixes(
        method_id=method_id,
        total_ha=total_ha,
        lines=lines
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
            SELECT SUM(pa.ProjAttrHa)
            FROM agr.ProjectAttributes pa
            JOIN agr.SprayProjects sp ON sp.SprayProjectProjectId = pa.ProjAttrProjectId
            WHERE sp.SprayProjectSprayId = ?
        """, spray_id)
        total_ha = cursor.fetchone()[0] or 0

        cursor.execute("""
        SELECT 
            LIN.SprayLineStkId,
            LIN.SprayLineQtyPerHa,
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
            qty_to_be = line.SprayLineQtyPerHa * total_ha
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
            JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayProjectProjectId
            WHERE sp.SprayProjectSprayId = ?
        """, spray_id)
        projects_str = cursor.fetchone()[0] or ""

        cursor.execute("""
            SELECT SprayProjectProjectId FROM agr.SprayProjects WHERE SprayProjectSprayId = ?
        """, spray_id)
        project_ids = [r.SprayProjectProjectId for r in cursor.fetchall()]

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