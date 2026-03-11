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

    cur.execute("""
        SELECT ProjectLink, ProjectCode, ProjectName
        FROM [cmn]._uvProject
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

    cur.execute("""
    SELECT
    IdProjAttr, ProjAttrProjectId, ProjAttrCropId, ProjAttrVarietyId, ProjAttrHa
    FROM agr.ProjectAttributes
    """)
    spray_projects = cur.fetchall()

    conn.close()

    return render_template(
        "agri_maintanance.html",
        farms=farms,
        crops=crops,
        varieties=varieties,
        spray_methods=spray_methods,
        projects=projects,
        spray_projects=spray_projects
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


@agri_bp.route("/setup/projectattr", methods=["POST"])
@login_required
def add_project_attr():
    project_id = request.form["project_id"]
    crop_id = request.form["crop_id"]
    variety_id = request.form["variety_id"]
    ha = request.form["ha"]

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.ProjectAttributes
        (ProjAttrProjectId, ProjAttrCropId, ProjAttrVarietyId, ProjAttrHa)
        VALUES (?, ?, ?, ?)
    """, project_id, crop_id, variety_id, ha)
    conn.commit()
    conn.close()

    return redirect(url_for("agri.setup"))