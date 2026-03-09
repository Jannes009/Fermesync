from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp

import math


@agri_bp.route("/spray-recommendation/create", methods=["GET"])
@login_required
def create_spray_recommendation():
    conn = create_db_connection()
    cur = conn.cursor()

    # Block Harvest Seasons
    cur.execute("""
        SELECT
            bhs.IdBHS,
            b.BlockCode,
            c.CropCode,
            bhs.BHSPlantDate
        FROM agr.BlockHarvestSeason bhs
        JOIN agr.Block b ON b.IdBlock = bhs.BHSBlockId
        JOIN agr.Crop c ON c.IdCrop = bhs.BHSCropId
        ORDER BY bhs.BHSPlantDate DESC
    """)
    bhs_list = cur.fetchall()

    # Chem stock
    cur.execute("""
    SELECT Distinct
        cs.IdChemStock,
        stk.StockDescription,
        cs.ChemStockActiveIngr,
        ct.ChemTypeName,
        stk.StockingUnitCode
    FROM agr.ChemStock cs
    JOIN agr.ChemType ct ON ct.IdChemType = cs.ChemStockTypeId
    JOIN [stk]._uvInventoryQty stk ON stk.StockLink = cs.IdChemStock
    ORDER BY cs.ChemStockActiveIngr
    """)
    chem_stock = cur.fetchall()

    # Scout master
    cur.execute("""
        SELECT
            IdScoutMstr,
            ScoutMstrName
        FROM agr.ScoutMstr
        ORDER BY ScoutMstrName
    """)
    scouts = cur.fetchall()

    cur.execute("""
        SELECT IdSprayMethod, SprayMethodName
        FROM agr.SprayMethod
        """)
    spray_methods = cur.fetchall()

    cur.execute("""
		Select WhseLink, WhseDescription 
        from [cmn]._uvWarehouses
        """)
    warehouses = cur.fetchall()

    conn.close()

    return render_template(
        "spray_recommendation.html",
        bhs_list=bhs_list,
        chem_stock=chem_stock,
        scouts=scouts,
        methods=spray_methods,
        warehouses=warehouses
    )

@agri_bp.route("/spray-recommendation/create", methods=["POST"])
@login_required
def save_spray_recommendation():
    conn = create_db_connection()
    cur = conn.cursor()

    try:
        spray_date = request.form.get("spray_date")
        bhs_id = request.form.get("bhs_id")
        method_id = request.form.get("method_id")
        warehouse_id = request.form.get("warehouse_id")

        if not spray_date or not bhs_id:
            return jsonify({"success": False, "message": "Date and Block Harvest Season are required."}), 400
        
        if not method_id:
            return jsonify({"success": False, "message": "Spray Method is required."}), 400

        # Insert header
        cur.execute("""
            INSERT INTO agr.SprayHeader
            (SprayHDate, SprayHBHSId, SprayHRecUserId, SprayHMethodId, [SprayHWhseId], SprayHStatus)
            OUTPUT INSERTED.IdSprayH
            VALUES (?, ?, ?, ?, ?, ?)
        """, spray_date, bhs_id, current_user.id, method_id, warehouse_id, "RECOMMENDED")

        spray_header_id = cur.fetchone()[0]

        # Get all line indexes from form
        line_indexes = request.form.getlist("line_index[]")

        for idx in line_indexes:
            stk_id = request.form.get(f"product_{idx}")
            qty = request.form.get(f"qty_{idx}")
            
            if not stk_id or not qty:
                # skip incomplete row
                continue

            # Insert spray line
            cur.execute("""
                INSERT INTO agr.SprayLines
                (SprayLineHeaderId, SprayLineStkId, SprayLineQtyPerHa)
                OUTPUT INSERTED.IdSprayLine
                VALUES (?, ?, ?)
            """, spray_header_id, stk_id, qty)

            spray_line_id = cur.fetchone()[0]

            # Get scout IDs for this specific line
            scout_ids = request.form.getlist(f"scout_{idx}_id[]")
            for scout_id in scout_ids:
                if scout_id:  # skip empty scout selections
                    cur.execute("""
                        INSERT INTO agr.SprayScoutLines
                        (SprayScoutLineRecId, SprayScoutLinePestId)
                        VALUES (?, ?)
                    """, spray_line_id, scout_id)

        conn.commit()
        conn.close()

        recalculate_and_store_mix(spray_header_id, method_id)
        
        
        return jsonify({"success": True, "message": "Spray recommendation saved successfully!", "id": spray_header_id})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": f"Error saving spray recommendation: {str(e)}"}), 500

@agri_bp.route("/spray-recommendation/preview", methods=["POST"])
@login_required
def spray_recommendation_preview():

    data = request.get_json(silent=True) or {}

    bhs_id = data.get("bhs_id")
    method_id = data.get("method_id")
    lines = data.get("lines", [])

    if not bhs_id or not method_id or not lines:
        return {"mixes": []}

    # Build simple line structure
    calc_lines = []
    for line in lines:
        calc_lines.append({
            "stock_id": line["stock_id"],
            "stock_description": line.get("stock_description", ""),
            "uom": line.get("uom", ""),
            "qty_per_ha": line["qty_per_ha"]
        })

    result = calculate_spray_mixes(
        method_id=method_id,
        harvest_season_id=bhs_id,
        lines=calc_lines
    )

    return result

def recalculate_and_store_mix(spray_header_id, method_id):

    conn = create_db_connection()
    cur = conn.cursor()

    # Delete old mix data
    cur.execute("""
        DELETE FROM agr.SprayMixLines
        WHERE SprayMixLineMixId IN (
            SELECT IdSprayMix
            FROM agr.SprayMix
            WHERE SprayMixHeaderId = ?
        )
    """, spray_header_id)

    cur.execute("""
        DELETE FROM agr.SprayMix
        WHERE SprayMixHeaderId = ?
    """, spray_header_id)


    cur.execute("""
        SELECT SprayHBHSId
        FROM agr.SprayHeader
        WHERE IdSprayH = ?
    """, spray_header_id)
    bhs_id = cur.fetchone()[0]

    cur.execute("""
        SELECT SprayLineStkId, SprayLineQtyPerHa
        FROM agr.SprayLines
        WHERE SprayLineHeaderId = ?
    """, spray_header_id)
    lines = cur.fetchall()
    calc_lines = []
    for line in lines:
        calc_lines.append({
            "stock_id": line[0],
            "qty_per_ha": line[1]
        })

    result = calculate_spray_mixes(
        method_id=method_id,
        harvest_season_id=bhs_id,
        lines=calc_lines
    )


    for mix in result["mixes"]:

        cur.execute("""
            INSERT INTO agr.SprayMix
            (SprayMixHeaderId, SprayMixNumber, SprayMixHa, SprayMixWater)
            OUTPUT INSERTED.IdSprayMix
            VALUES (?, ?, ?, ?)
        """, spray_header_id, mix["mix_no"], mix["ha"], mix["water"])

        mix_id = cur.fetchone()[0]

        for product in mix["products"]:
            cur.execute("""
                INSERT INTO agr.SprayMixLines
                (SprayMixLineMixId, SprayMixLineStockId, SprayMixLineQty)
                VALUES (?, ?, ?)
            """, mix_id, product["stock_id"], product["qty"])

    conn.commit()
    conn.close()

def calculate_spray_mixes(method_id, harvest_season_id, lines):
    """
    lines = list of dicts:
        [
            {"stock_id": 1, "qty_per_ha": 2.5},
            ...
        ]
    """

    # Fetch method details
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT SprayMethodWaterPerHa, SprayMethodTankSize
        FROM agr.SprayMethod
        WHERE IdSprayMethod = ?
    """, method_id)
    water_per_ha, tank_size = cur.fetchone()

    # Get total hectares
    cur.execute("""
        SELECT bhs.BHSHa
        FROM agr.BlockHarvestSeason bhs
        WHERE bhs.IdBHS = ?
    """, harvest_season_id)

    total_ha = float(cur.fetchone()[0])
    conn.close()


    total_water = total_ha * water_per_ha
    mixes = math.ceil(total_water / tank_size)
    ha_per_full_tank = tank_size / water_per_ha

    print(total_ha, water_per_ha, tank_size, total_water, mixes, ha_per_full_tank)

    remaining_ha = total_ha
    result_mixes = []

    for mix_no in range(1, mixes + 1):

        if remaining_ha >= ha_per_full_tank:
            mix_ha = ha_per_full_tank
            mix_water = tank_size
        else:
            mix_ha = remaining_ha
            mix_water = mix_ha * water_per_ha

        mix_products = []

        for line in lines:
            qty = round(mix_ha * float(line["qty_per_ha"]), 1)

            mix_products.append({
                "stock_id": line["stock_id"],
                "stock_description": line.get("stock_description", ""),
                "uom": line.get("uom", ""),
                "qty": qty
            })

        result_mixes.append({
            "mix_no": mix_no,
            "ha": round(mix_ha, 1),
            "water": round(mix_water, 1),
            "products": mix_products
        })

        remaining_ha -= mix_ha

    return {
        "total_ha": round(total_ha, 1),
        "total_water": round(total_water, 1),
        "number_of_mixes": mixes,
        "mixes": result_mixes
    }


@agri_bp.route("/spray-recommendations-summary", methods=["GET"])
@login_required
def spray_recommendations_summary():
    return render_template("spray_recommendation_summary.html")


@agri_bp.route("/spray-recommendations/filter-data", methods=["GET"])
@login_required
def get_filter_data():
    conn = create_db_connection()
    cur = conn.cursor()

    # Get all blocks
    cur.execute("""
        SELECT DISTINCT b.IdBlock, b.BlockCode
        FROM agr.Block b
        JOIN agr.BlockHarvestSeason bhs ON bhs.BHSBlockId = b.IdBlock
        ORDER BY b.BlockCode
    """)
    blocks = [{"id": row[0], "code": row[1]} for row in cur.fetchall()]

    # Get all crops
    cur.execute("""
        SELECT DISTINCT c.IdCrop, c.CropCode
        FROM agr.Crop c
        JOIN agr.BlockHarvestSeason bhs ON bhs.BHSCropId = c.IdCrop
        ORDER BY c.CropCode
    """)
    crops = [{"id": row[0], "code": row[1]} for row in cur.fetchall()]

    conn.close()
    return jsonify({"blocks": blocks, "crops": crops})


@agri_bp.route("/spray-recommendations", methods=["GET"])
@login_required
def get_spray_recommendations():
    conn = create_db_connection()
    cur = conn.cursor()

    query = """
        SELECT 
            sh.IdSprayH,
            b.BlockCode,
            c.CropCode,
            sh.SprayHDate,
            bhs.BHSPlantDate,
            bhs.BHSHa,
            sh.SprayHStatus
        FROM agr.SprayHeader sh
        JOIN agr.BlockHarvestSeason bhs ON bhs.IdBHS = sh.SprayHBHSId
        JOIN agr.Block b ON b.IdBlock = bhs.BHSBlockId
        JOIN agr.Crop c ON c.IdCrop = bhs.BHSCropId
        ORDER BY sh.SprayHDate DESC
    """
    cur.execute(query)
    rows = cur.fetchall()

    recommendations = [
        {
            "id": row[0],
            "block": row[1],
            "crop": row[2],
            "spray_date": str(row[3]),
            "plant_date": str(row[4]),
            "ha": float(row[5]),
            "status": row[6]
        }
        for row in rows
    ]

    conn.close()
    return jsonify(recommendations)
