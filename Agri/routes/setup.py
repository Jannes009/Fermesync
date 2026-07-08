from flask import render_template, request, redirect, url_for, jsonify
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

    # Projects
    cur.execute("""
        SELECT ProjectLink, ProjectCode, ProjectName
        FROM [cmn]._uvProject
        ORDER BY ProjectCode
    """)
    projects = cur.fetchall()

    # Warehouses
    cur.execute("""
        SELECT WhseLink, WhseDescription
        FROM [cmn]._uvWarehouses WHSE
		JOIN [agr].[WarehouseAttributes] ATTR on ATTR.WhAttrWhseId = WHSE.WhseLink
        where ATTR.WhAttrWhseType = 'Chemical'
        ORDER BY WhseDescription
    """)
    warehouses = cur.fetchall()

    # Spray Methods
    cur.execute("""
        SELECT
            sm.IdSprayMethod,
            sm.SprayMethodFarmId,
            f.FarmName,
            sm.SprayMethodName,
            sm.SprayMethodWaterPerHa,
            sm.SprayMethodTankSize
        FROM agr.SprayMethod sm
        JOIN agr.Farm f ON f.IdFarm = sm.SprayMethodFarmId
    """)
    spray_methods = cur.fetchall()

    # Spray Projects
    cur.execute("""
    SELECT
        pa.IdProjAttr,
        pa.ProjAttrProjectId,
        PRJ.ProjectName,
        pa.ProjAttrFarmId,
        F.FarmName AS ProjAttrFarmName,
        pa.ProjAttrWhseId,
        WHSE.WhseDescription AS ProjAttrWhseName,
        pa.ProjAttrCropId,
        CRP.CropCode,
        pa.ProjAttrVarietyId,
        VA.VarietyCode,
        pa.ProjAttrHa,
        pa.ProjAttrPlantDate,
        pa.ProjAttrProjectManager,
        pa.ProjAttrAgriculturist,
        pa.ProjAttrBlockNo
    FROM agr.ProjectAttributes PA
    JOIN cmn._uvProject PRJ on PRJ.ProjectLink = PA.ProjAttrProjectId
    LEFT JOIN agr.Farm F on F.IdFarm = PA.ProjAttrFarmId
    LEFT JOIN [cmn]._uvWarehouses WHSE on WHSE.WhseLink = PA.ProjAttrWhseId
    JOIN agr.Crop CRP on CRP.IdCrop = PA.ProjAttrCropId
    JOIN agr.Variety VA on VA.IdVariety = PA.ProjAttrVarietyId
    Order BY PRJ.ProjectName
    """)
    spray_projects = cur.fetchall()

    conn.close()

    return render_template(
        "agri_maintanance.html",
        farms=farms,
        crops=crops,
        varieties=varieties,
        warehouses=warehouses,
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


@agri_bp.route("/setup/projectattr/add", methods=["POST"])
@login_required
def add_project_attr():
    # Accept both form-encoded and JSON payloads (modal posts JSON)
    data = request.get_json(silent=True)
    if data:
        project_id = data.get('project_id')
        farm_id = data.get('farm_id')
        whse_id = data.get('warehouse_id')
        crop_id = data.get('crop_id')
        variety_id = data.get('variety_id')
        ha = data.get('ha')
        plant_date = data.get('plant_date')
        project_manager = data.get('project_manager')
        agriculturist = data.get('agriculturist')
        block_no = data.get('block_no')
    else:
        project_id = request.form.get('project_id')
        farm_id = request.form.get('farm_id')
        whse_id = request.form.get('warehouse_id')
        crop_id = request.form.get('crop_id')
        variety_id = request.form.get('variety_id')
        ha = request.form.get('ha')
        plant_date = request.form.get('plant_date')
        project_manager = request.form.get('project_manager')
        agriculturist = request.form.get('agriculturist')
        block_no = request.form.get('block_no')

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.ProjectAttributes
        (ProjAttrProjectId, ProjAttrFarmId, ProjAttrWhseId, ProjAttrCropId, ProjAttrVarietyId, ProjAttrHa, ProjAttrPlantDate, ProjAttrProjectManager, ProjAttrAgriculturist, ProjAttrBlockNo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, project_id, farm_id, whse_id, crop_id, variety_id, ha, plant_date, project_manager, agriculturist, block_no)
    conn.commit()
    conn.close()

    # If JSON was posted, return JSON response for AJAX flows; otherwise redirect for regular form
    if data:
        return jsonify({"success": True})
    return redirect(url_for("agri.setup"))


@agri_bp.route('/setup/farm/update', methods=['POST'])
@login_required
def update_farm():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Missing payload"}), 400

    farm_id = data.get('id')
    name = (data.get('name') or '').strip()
    if not farm_id or not name:
        return jsonify({"success": False, "message": "Farm ID and name are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE agr.Farm
        SET FarmName = ?
        WHERE IdFarm = ?
    """, name, farm_id)
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@agri_bp.route('/setup/spraymethod/update', methods=['POST'])
@login_required
def update_spray_method():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Missing payload"}), 400

    method_id = data.get('id')
    farm_id = data.get('farm_id')
    name = (data.get('name') or '').strip()
    water_per_ha = data.get('water_per_ha')
    tank_size = data.get('tank_size')

    if not method_id or not farm_id or not name:
        return jsonify({"success": False, "message": "Spray method ID, farm, and name are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE agr.SprayMethod
        SET SprayMethodFarmId = ?, SprayMethodName = ?, SprayMethodWaterPerHa = ?, SprayMethodTankSize = ?
        WHERE IdSprayMethod = ?
    """, farm_id, name, water_per_ha, tank_size, method_id)
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@agri_bp.route('/setup/projectattr/update', methods=['POST'])
@login_required
def update_project_attr():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Missing payload"}), 400

    attr_id = data.get('id')
    project_id = data.get('project_id')
    farm_id = data.get('farm_id')
    whse_id = data.get('warehouse_id')
    crop_id = data.get('crop_id')
    variety_id = data.get('variety_id')
    ha = data.get('ha')
    plant_date = data.get('plant_date')
    project_manager = (data.get('project_manager') or '').strip()
    agriculturist = (data.get('agriculturist') or '').strip()
    block_no = (data.get('block_no') or '').strip()

    if not attr_id or not project_id or not farm_id or not whse_id or not crop_id or not variety_id:
        return jsonify({"success": False, "message": "Project, farm, warehouse, crop and variety are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE agr.ProjectAttributes
        SET ProjAttrProjectId = ?, ProjAttrFarmId = ?, ProjAttrWhseId = ?, ProjAttrCropId = ?, ProjAttrVarietyId = ?, ProjAttrHa = ?, ProjAttrPlantDate = ?, ProjAttrProjectManager = ?, ProjAttrAgriculturist = ?, ProjAttrBlockNo = ?
        WHERE IdProjAttr = ?
    """, project_id, farm_id, whse_id, crop_id, variety_id, ha, plant_date, project_manager, agriculturist, block_no, attr_id)
    conn.commit()
    conn.close()

    return jsonify({"success": True})