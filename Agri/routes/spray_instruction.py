
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
            BHS.IdBHS,
            BHS.BHSPlantDate,
            HEA.SprayHProjectManagerId,
            HEA.SprayHAgriculturistId,
            BLK.BlockDescription,
            CRP.CropDescription,
            BHS.BHSHa,
            HEA.SprayHOperatorId,
            HEA.SprayHWeather,
            MTD.IdSprayMethod,
            MTD.SprayMethodName,
            MTD.SprayMethodTankSize,
            MTD.SprayMethodWaterPerHa
        FROM agr.SprayHeader HEA
        JOIN agr.BlockHarvestSeason BHS on BHS.IdBHS = HEA.SprayHBHSId
        JOIN agr.Block BLK on BLK.IdBlock = BHS.BHSBlockId
        JOIN agr.Crop CRP on CRP.IdCrop = BHS.BHSCropId
        JOIN agr.SprayMethod MTD on MTD.IdSprayMethod = HEA.SprayHMethodId
        WHERE HEA.IdSprayH = ?
    """, spray_id)

    header = cur.fetchone()
    conn.close()

    return jsonify({
            "spray_date": str(header.SprayHDate),
            "bhs_id": header.IdBHS,
            "plant_date": str(header.BHSPlantDate),
            "manager_id": header.SprayHProjectManagerId,
            "agriculturist_id": header.SprayHAgriculturistId,
            "block": header.BlockDescription,
            "crop": header.CropDescription,
            "ha": float(header.BHSHa),
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

    data = request.get_json()

    result = calculate_spray_mixes(
        method_id=data["method_id"],
        harvest_season_id=data["bhs_id"],
        lines=data["lines"]
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
        cursor.execute("""
        Select 
            LIN.SprayLineStkId,
            LIN.SprayLineQtyPerHa * BHSHa QtyToBeSprayed,
            ISNULL(QTY.QtyOnHand, 0) QtyAvailable,
            BHSV.BHSVProjectId,
            HEA.SprayHWhseId
        FROM agr.SprayHeader HEA
        JOIN agr.BlockHarvestSeason BHS on BHS.IdBHS = HEA.SprayHBHSId
        JOIN agr.BlockHarvestSeasonVariety BHSV on BHSV.BHSVBlockHarvestSeasonId = BHS.IdBHS
        JOIN agr.SprayLines LIN on LIN.SprayLineHeaderId = HEA.IdSprayH
        LEFT JOIN stk._uvInventoryQty QTY 
            ON QTY.StockLink = LIN.SprayLineStkId 
            AND QTY.WhseLink = HEA.SprayHWhseId
        Where HEA.IdSprayH = ?
        """, spray_id)

        lines = cursor.fetchall()

        if not lines:
            return jsonify({
                "success": False,
                "message": "No stock lines found for this spray recommendation."
            }), 400

        # -----------------------------
        # CHECK FOR INSUFFICIENT STOCK
        # -----------------------------
        shortages = []

        for line in lines:
            if line.QtyToBeSprayed > line.QtyAvailable:
                shortages.append({
                    "product_link": line.SprayLineStkId,
                    "required": float(line.QtyToBeSprayed),
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
        return jsonify({
            "success": True,
            "warehouse": lines[0].SprayHWhseId,
            "project": lines[0].BHSVProjectId,
            "lines": [
                {
                    "product_link": line.SprayLineStkId,
                    "qty": float(line.QtyToBeSprayed)
                }
                for line in lines
            ]
        })

    except Exception as ex:
        return jsonify({
            "success": False,
            "message": str(ex)
        }), 400