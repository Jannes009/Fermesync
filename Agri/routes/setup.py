from flask import  render_template, request, redirect, url_for
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp


@agri_bp.route("/setup", methods=["GET"])
@login_required
def setup():
    conn = create_db_connection()
    cur = conn.cursor()

    # Farms
    cur.execute("""
        SELECT IdFarm, FarmName
        FROM agr.Farm
        ORDER BY FarmName
    """)
    farms = cur.fetchall()

    # Blocks
    cur.execute("""
        SELECT IdBlock, BlockCode, BlockDescription, BlockHa, BlockFarmId
        FROM agr.Block
        ORDER BY BlockCode
    """)
    blocks = cur.fetchall()

    # Crops
    cur.execute("""
        SELECT IdCrop, CropCode, CropDescription
        FROM agr.Crop
        ORDER BY CropCode
    """)
    crops = cur.fetchall()

    # Varieties
    cur.execute("""
        SELECT IdVariety, VarietyCode, VarietyDescription
        FROM agr.Variety
        ORDER BY VarietyCode
    """)
    varieties = cur.fetchall()

    # Block Harvest Seasons
    cur.execute("""
    Select IdBHS, BlockCode, CropCode, BHSPlantDate, BHSHa
    from agr.BlockHarvestSeason bhs
    JOIN agr.Block b ON b.IdBlock = bhs.BHSBlockId
    JOIN agr.Crop c ON c.IdCrop = bhs.BHSCropId
    """)

    bhs = cur.fetchall()

    # Harvest season varieties (joins to show variety + project + season info)
    cur.execute("""
        SELECT
            bsv.BHSVBlockHarvestSeasonId as IdBHS,
            b.BlockCode,
            c.CropCode,
            bhs.BHSPlantDate,
            v.IdVariety,
            v.VarietyCode,
            p.ProjectLink,
            p.ProjectCode,
            p.ProjectName,
            bsv.BHSVHa
        FROM agr.BlockHarvestSeasonVariety bsv
        JOIN agr.BlockHarvestSeason bhs ON bhs.IdBHS = bsv.BHSVBlockHarvestSeasonId
        JOIN agr.Block b ON b.IdBlock = bhs.BHSBlockId
        JOIN agr.Crop c ON c.IdCrop = bhs.BHSCropId
        JOIN agr.Variety v ON v.IdVariety = bsv.BHSVVarietyId
        LEFT JOIN [mkt]._uvProject p ON p.ProjectLink = bsv.BHSVProjectId
        ORDER BY b.BlockCode, bhs.BHSPlantDate
    """)

    bhsv = cur.fetchall()

    cur.execute("""
        SELECT ProjectLink, ProjectCode, ProjectName
        FROM [mkt]._uvProject
        ORDER BY ProjectCode
    """)
    projects = cur.fetchall()

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

    return render_template(
        "agri_maintanance.html",
        farms=farms,
        blocks=blocks,
        crops=crops,
        varieties=varieties,
        bhs=bhs,
        bhsv=bhsv,
        spray_methods=spray_methods,
        projects=projects 
    )

# =========================
# INSERInventory.routes
# =========================

@agri_bp.route("/setup/farm", methods=["POST"])
@login_required
def add_farm():
    name = request.form["farm_name"]

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.Farm (FarmName)
        VALUES (?)
    """, name)
    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))


@agri_bp.route("/setup/block", methods=["POST"])
@login_required
def add_block():
    code = request.form["code"]
    desc = request.form["description"]
    ha = request.form["ha"]
    farm_id = request.form["farm_id"]

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.Block
        (BlockCode, BlockDescription, BlockHa, BlockFarmId)
        VALUES (?, ?, ?, ?)
    """, code, desc, ha, farm_id)
    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))


@agri_bp.route("/setup/bhs", methods=["POST"])
@login_required
def add_bhs():
    block_id = request.form["block_id"]
    crop_id = request.form["crop_id"]
    plant_date = request.form["plant_date"]
    ha = request.form["ha"]

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.BlockHarvestSeason
        (BHSBlockId, BHSCropId, BHSPlantDate, BHSHa)
        VALUES (?, ?, ?, ?)
    """, block_id, crop_id, plant_date, ha)
    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))


@agri_bp.route("/setup/bhsv", methods=["POST"])
@login_required
def add_bhsv():
    bhs_id = request.form["bhs_id"]
    variety_id = request.form["variety_id"]
    project_id = request.form["project_id"]
    ha = request.form["ha"]
    if not bhs_id or not variety_id or not project_id or not ha:
        return "Missing required fields", 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.BlockHarvestSeasonVariety
        (BHSVBlockHarvestSeasonId,
         BHSVVarietyId,
         BHSVProjectId,
         BHSVHa)
        VALUES (?, ?, ?, ?)
    """, bhs_id, variety_id, project_id, ha)

    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))



@agri_bp.route("/setup/spraymethod", methods=["POST"])
@login_required
def add_spray_method():
    name = request.form["spray_method_name"]
    farm_id = request.form["farm_id"]
    water = request.form["water_per_ha"]
    tank = request.form["tank_size"]

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.SprayMethod
        (SprayMethodName, SprayMethodFarmId, SprayMethodWaterPerHa, SprayMethodTankSize)
        VALUES (?, ?, ?, ?)
    """, name, farm_id, water, tank)
    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))