from datetime import date, datetime

from flask import abort, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp


def format_setup_date(value):
    """Format database date values regardless of the ODBC driver's return type."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return ""
        for parser in (datetime.fromisoformat,):
            try:
                return parser(cleaned).strftime("%Y-%m-%d")
            except ValueError:
                continue
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(cleaned, pattern).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return cleaned
    return str(value)


def table_column_exists(cur, schema, table, column):
    cur.execute("""
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?
    """, schema, table, column)
    return cur.fetchone() is not None


CROP_ICON_DEFAULT = "fa-seedling"
FARM_COLOR_DEFAULT = "#2E7D32"
FARM_COLOUR_PALETTE = (
    ("#2E7D32", "Forest"),
    ("#2563EB", "Ocean"),
    ("#D97706", "Amber"),
    ("#7C3AED", "Purple"),
    ("#0F766E", "Teal"),
    ("#E11D48", "Rose"),
    ("#71852A", "Olive"),
    ("#0284C7", "Sky"),
    ("#8D5A3B", "Brown"),
    ("#64748B", "Slate"),
    ("#4F46E5", "Indigo"),
    ("#D65A45", "Coral"),
)


def row_value(row, name, default=None):
    try:
        return getattr(row, name)
    except (AttributeError, KeyError):
        try:
            return row[name]
        except (KeyError, IndexError, TypeError):
            return default


@agri_bp.route("/setup", methods=["GET"])
@login_required
def setup():
    conn = create_db_connection()
    cur = conn.cursor()

    # Farms
    farm_has_colour = table_column_exists(cur, "agr", "Farm", "FarmColour")
    farm_colour_column = (
        ", FarmColour" if farm_has_colour
        else ", CAST(NULL AS nvarchar(7)) AS FarmColour"
    )
    cur.execute("""
        SELECT IdFarm, FarmName
        %s
        FROM agr.Farm
        ORDER BY FarmName
    """ % farm_colour_column)
    farms = cur.fetchall()

    for farm in farms:
        if not farm_has_colour:
            try:
                farm.FarmColour = FARM_COLOR_DEFAULT
            except Exception:
                pass

    # People
    cur.execute("""
        SELECT p.IdPerson, p.PersonName, p.PersonSprayExecutionResponsible
        FROM agr.People p
        ORDER BY p.PersonName
    """)
    people = cur.fetchall()
    
    # Get farm assignments for each person
    people_farms = {}
    for person in people:
        cur.execute("""
            SELECT f.IdFarm, f.FarmName FROM agr.FarmPeople fp
            JOIN agr.Farm f ON f.IdFarm = fp.FarmId
            WHERE fp.PersonId = ?
            ORDER BY f.FarmName
        """, person[0])
        people_farms[person[0]] = cur.fetchall()

    # Crops
    crop_has_icon = table_column_exists(cur, "agr", "Crop", "CropIcon")
    crop_has_theme = table_column_exists(cur, "agr", "Crop", "CropThemeColor")
    cur.execute("""
        SELECT IdCrop, CropCode, CropDescription
        %s
        %s
        FROM agr.Crop
        ORDER BY CropCode
    """ % (
        ", CropIcon" if crop_has_icon else "",
        ", CropThemeColor" if crop_has_theme else "",
    ))
    crops = cur.fetchall()

    for crop in crops:
        if not crop_has_icon:
            try:
                crop.CropIcon = CROP_ICON_DEFAULT
            except Exception:
                pass
        if not crop_has_theme:
            try:
                crop.CropThemeColor = "#4d7c0f"
            except Exception:
                pass

    # Varieties
    cur.execute("""
        SELECT IdVariety, VarietyCode, VarietyDescription
        FROM agr.Variety
        ORDER BY VarietyCode
    """)
    varieties = cur.fetchall()

    cur.execute("""
        SELECT IdField, FieldDescription
        FROM agr.Field
        ORDER BY FieldDescription
    """)
    fields = cur.fetchall()

    # Projects
    cur.execute(f"""
        SELECT ProjectLink, ProjectCode, ProjectName
        FROM [cmn]._uvProject
        WHERE MainProjectLink IN ({','.join(['?'] * len(current_user.projects))}) 
        ORDER BY ProjectCode
    """, current_user.projects)
    projects = cur.fetchall()

    # Warehouses
    cur.execute(f"""
        SELECT WhseLink, WhseDescription
        FROM [cmn]._uvWarehouses WHSE
		JOIN [agr].[WarehouseAttributes] ATTR on ATTR.WhAttrWhseId = WHSE.WhseLink
        where ATTR.WhAttrWhseType = 'Chemical' and WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
        ORDER BY WhseDescription
    """, current_user.warehouses)
    warehouses = cur.fetchall()

    # Spray Methods
    cur.execute(f"""
        SELECT
            sm.IdSprayMethod,
            sm.SprayMethodFarmId,
            f.FarmName,
            {("f.FarmColour" if farm_has_colour else "CAST(NULL AS nvarchar(7))")} AS FarmColour,
            sm.SprayMethodName,
            sm.SprayMethodWaterPerHa,
            sm.SprayMethodTankSize
        FROM agr.SprayMethod sm
        JOIN agr.Farm f ON f.IdFarm = sm.SprayMethodFarmId
    """)
    spray_methods = cur.fetchall()

    # Spray Projects
    cur.execute(f"""
    SELECT
        pa.IdProjAttr,
        pa.ProjAttrProjectId,
        PRJ.ProjectName,
        pa.ProjAttrFarmId,
        F.FarmName AS ProjAttrFarmName,
        {("F.FarmColour" if farm_has_colour else "CAST(NULL AS nvarchar(7))")} AS ProjAttrFarmColour,
        pa.ProjAttrWhseId,
        WHSE.WhseDescription AS ProjAttrWhseName,
        pa.ProjAttrCropId,
        CRP.CropCode,
        CRP.CropDescription,
        {("CRP.CropIcon" if crop_has_icon else "CAST(NULL AS nvarchar(50))")} AS CropIcon,
        {("CRP.CropThemeColor" if crop_has_theme else "CAST(NULL AS nvarchar(20))")} AS CropThemeColor,
        pa.ProjAttrVarietyId,
        VA.VarietyCode,
        pa.ProjAttrHa,
        pa.ProjAttrPlantDate,
        pa.ProjAttrHarvestDate,
        pa.ProjAttr80PercPetalFallDate,
        pa.ProjAttrProjectManager,
        pa.ProjAttrAgriculturist,
        pa.ProjAttrBlockNo,
        pa.ProjAttrFieldId,
        FLD.FieldDescription AS ProjAttrFieldDescription,
        pa.ProjAttrDefaultSprayMethodId,
        pa.ProjAttrDefaultDose,
        pa.ProjAttrDefaultWaterPerHa,
        pa.ProjAttrDefaultWaterPerTank
    FROM agr.ProjectAttributes PA
    JOIN cmn._uvProject PRJ on PRJ.ProjectLink = PA.ProjAttrProjectId
    LEFT JOIN agr.Farm F on F.IdFarm = PA.ProjAttrFarmId
    LEFT JOIN [cmn]._uvWarehouses WHSE on WHSE.WhseLink = PA.ProjAttrWhseId
    LEFT JOIN agr.Field FLD on FLD.IdField = PA.ProjAttrFieldId
    JOIN agr.Crop CRP on CRP.IdCrop = PA.ProjAttrCropId
    JOIN agr.Variety VA on VA.IdVariety = PA.ProjAttrVarietyId
    Where PRJ.MainProjectLink IN ({','.join(['?'] * len(current_user.projects))})
    Order BY PRJ.ProjectName
    """, current_user.projects)
    spray_projects = cur.fetchall()

    conn.close()

    return render_template(
        "agri_maintanance.html",
        farms=farms,
        crops=crops,
        varieties=varieties,
        fields=fields,
        warehouses=warehouses,
        spray_methods=spray_methods,
        projects=projects,
        spray_projects=spray_projects,
        people=people,
        people_farms=people_farms,
        farm_colour_palette=FARM_COLOUR_PALETTE,
        format_setup_date=format_setup_date
    )

# =========================
# INSERInventory.routes
# =========================

@agri_bp.route("/setup/farm", methods=["POST"])
@login_required
def add_farm():
    name = request.form["farm_name"]
    colour = request.form.get("farm_colour")
    if colour not in {value for value, _ in FARM_COLOUR_PALETTE}:
        abort(400, description="Choose a farm colour from the approved palette.")

    conn = create_db_connection()
    cur = conn.cursor()
    has_colour = table_column_exists(cur, "agr", "Farm", "FarmColour")
    columns = ["FarmName"]
    values = [name]
    if has_colour:
        columns.append("FarmColour")
        values.append(colour)
    placeholders = ", ".join(["?"] * len(columns))
    cur.execute(
        "INSERT INTO agr.Farm ({0}) VALUES ({1})".format(
            ", ".join(columns), placeholders
        ),
        tuple(values)
    )
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
# Also accept trailing slash to avoid 404 when clients POST to `/setup/projectattr/`
@agri_bp.route("/setup/projectattr/", methods=["POST"])
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
        harvest_date = data.get('harvest_date') or None
        petal_fall_date = data.get('80_perc_petal_fall_date') or None
        field_id = data.get('field_id')
        project_manager = data.get('project_manager')
        agriculturist = data.get('agriculturist')
        block_no = data.get('block_no')
        default_spray_method_id = data.get('default_spray_method_id')
        default_dose = data.get('default_dose')
        default_water_per_ha = data.get('default_water_per_ha')
        default_water_per_tank = data.get('default_water_per_tank')
    else:
        project_id = request.form.get('project_id')
        farm_id = request.form.get('farm_id')
        whse_id = request.form.get('warehouse_id')
        crop_id = request.form.get('crop_id')
        variety_id = request.form.get('variety_id')
        ha = request.form.get('ha')
        plant_date = request.form.get('plant_date')
        harvest_date = request.form.get('harvest_date') or None
        petal_fall_date = request.form.get('80_perc_petal_fall_date') or None
        field_id = request.form.get('field_id')
        project_manager = request.form.get('project_manager')
        agriculturist = request.form.get('agriculturist')
        block_no = request.form.get('block_no')
        default_spray_method_id = request.form.get('default_spray_method_id')
        default_dose = request.form.get('default_dose')
        default_water_per_ha = request.form.get('default_water_per_ha')
        default_water_per_tank = request.form.get('default_water_per_tank')

    if not field_id:
        if data:
            return jsonify({"success": False, "message": "Field is required"}), 400
        return redirect(url_for("agri.setup"))

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.ProjectAttributes
        (ProjAttrProjectId, ProjAttrFarmId, ProjAttrWhseId, ProjAttrCropId, ProjAttrVarietyId, ProjAttrHa, ProjAttrPlantDate, ProjAttrHarvestDate, ProjAttr80PercPetalFallDate, ProjAttrProjectManager, ProjAttrAgriculturist, ProjAttrBlockNo, ProjAttrFieldId, ProjAttrDefaultSprayMethodId, ProjAttrDefaultDose, ProjAttrDefaultWaterPerHa, ProjAttrDefaultWaterPerTank)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, project_id, farm_id, whse_id, crop_id, variety_id, ha, plant_date, harvest_date, petal_fall_date, project_manager, agriculturist, block_no, field_id, default_spray_method_id, default_dose, default_water_per_ha, default_water_per_tank)
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
    requested_colour = data.get('farm_colour', data.get('colour'))
    if not farm_id or not name:
        return jsonify({"success": False, "message": "Farm ID and name are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    assignments = ["FarmName = ?"]
    values = [name]
    has_colour = table_column_exists(cur, "agr", "Farm", "FarmColour")
    if requested_colour not in (None, ""):
        approved_colour = (
            isinstance(requested_colour, str)
            and requested_colour in {value for value, _ in FARM_COLOUR_PALETTE}
        )
        if approved_colour:
            if has_colour:
                assignments.append("FarmColour = ?")
                values.append(requested_colour)
        else:
            if not has_colour:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": "Choose a farm colour from the approved palette."
                }), 400
            cur.execute("SELECT FarmColour FROM agr.Farm WHERE IdFarm = ?", farm_id)
            existing = cur.fetchone()
            existing_colour = existing[0] if existing and existing[0] else None
            if requested_colour != existing_colour:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": "Choose a farm colour from the approved palette."
                }), 400
    values.append(farm_id)
    cur.execute(
        "UPDATE agr.Farm SET {0} WHERE IdFarm = ?".format(", ".join(assignments)),
        tuple(values)
    )
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
    harvest_date = data.get('harvest_date') or None
    petal_fall_date = data.get('80_perc_petal_fall_date') or None
    field_id = data.get('field_id')
    project_manager = (data.get('project_manager') or '').strip()
    agriculturist = (data.get('agriculturist') or '').strip()
    block_no = (data.get('block_no') or '').strip()
    default_spray_method_id = data.get('default_spray_method_id')
    default_dose = data.get('default_dose')
    default_water_per_ha = data.get('default_water_per_ha')
    default_water_per_tank = data.get('default_water_per_tank')

    if not attr_id or not project_id or not farm_id or not whse_id or not crop_id or not variety_id or not field_id:
        return jsonify({"success": False, "message": "Project, farm, warehouse, crop, variety and field are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE agr.ProjectAttributes
        SET ProjAttrProjectId = ?, ProjAttrFarmId = ?, ProjAttrWhseId = ?, ProjAttrCropId = ?, ProjAttrVarietyId = ?, ProjAttrHa = ?, ProjAttrPlantDate = ?, ProjAttrHarvestDate = ?, ProjAttr80PercPetalFallDate = ?, ProjAttrProjectManager = ?, ProjAttrAgriculturist = ?, ProjAttrBlockNo = ?, ProjAttrFieldId = ?, ProjAttrDefaultSprayMethodId = ?, ProjAttrDefaultDose = ?, ProjAttrDefaultWaterPerHa = ?, ProjAttrDefaultWaterPerTank = ?
        WHERE IdProjAttr = ?
    """, project_id, farm_id, whse_id, crop_id, variety_id, ha, plant_date, harvest_date, petal_fall_date, project_manager, agriculturist, block_no, field_id, default_spray_method_id, default_dose, default_water_per_ha, default_water_per_tank, attr_id)
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@agri_bp.route('/setup/field', methods=['POST'])
@login_required
def add_field():
    data = request.get_json(silent=True) or {}
    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({"success": False, "message": "Field description is required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO agr.Field (FieldDescription)
            OUTPUT INSERTED.IdField
            VALUES (?)
        """, description)
        field_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"success": True, "field": {"id": field_id, "description": description}})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@agri_bp.route('/setup/farm/<int:farm_id>/spray-methods', methods=['GET'])
@login_required
def get_farm_spray_methods(farm_id):
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT IdSprayMethod, SprayMethodName
            FROM agr.SprayMethod
            WHERE SprayMethodFarmId = ?
            ORDER BY SprayMethodName
        """, farm_id)
        methods = [
            {"id": row.IdSprayMethod, "name": row.SprayMethodName}
            for row in cur.fetchall()
        ]
        return jsonify({"success": True, "methods": methods})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "methods": []}), 500
    finally:
        conn.close()


# =========================
# People Management
# =========================

@agri_bp.route("/setup/person", methods=["POST"])
@login_required
def add_person():
    data = request.get_json(silent=True)
    if data:
        name = (data.get('name') or '').strip()
        is_responsible = data.get('is_spray_execution_responsible', False)
        farm_ids = data.get('farms', [])
    else:
        name = (request.form.get('person_name') or '').strip()
        is_responsible = request.form.get('person_spray_responsible') == 'on'
        farm_ids = request.form.getlist('person_farms')

    if not name:
        if data:
            return jsonify({"success": False, "message": "Person name is required"}), 400
        return redirect(url_for("agri.setup"))

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO agr.People (PersonName, PersonSprayExecutionResponsible)
        VALUES (?, ?)
    """, name, 1 if is_responsible else 0)
    
    # Get the inserted person's ID
    cur.execute("SELECT SCOPE_IDENTITY()")
    person_id = cur.fetchone()[0]
    
    # Insert farm assignments
    for farm_id in farm_ids:
        cur.execute("""
            INSERT INTO agr.FarmPeople (PersonId, FarmId)
            VALUES (?, ?)
        """, person_id, farm_id)
    
    conn.commit()
    conn.close()

    if data:
        return jsonify({"success": True})
    return redirect(url_for("agri.setup"))


@agri_bp.route('/setup/person/update', methods=['POST'])
@login_required
def update_person():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "Missing payload"}), 400

    person_id = data.get('id')
    name = (data.get('name') or '').strip()
    is_responsible = data.get('is_spray_execution_responsible', False)
    farm_ids = data.get('farms', [])

    if not person_id or not name:
        return jsonify({"success": False, "message": "Person ID and name are required"}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    
    # Update person
    cur.execute("""
        UPDATE agr.People
        SET PersonName = ?, PersonSprayExecutionResponsible = ?
        WHERE IdPerson = ?
    """, name, 1 if is_responsible else 0, person_id)
    
    # Delete existing farm assignments
    cur.execute("""
        DELETE FROM agr.FarmPeople WHERE PersonId = ?
    """, person_id)
    
    # Insert new farm assignments
    for farm_id in farm_ids:
        cur.execute("""
            INSERT INTO agr.FarmPeople (PersonId, FarmId)
            VALUES (?, ?)
        """, person_id, farm_id)
    
    conn.commit()
    conn.close()

    return jsonify({"success": True})


@agri_bp.route('/setup/person/<int:person_id>/farms', methods=['GET'])
@login_required
def get_person_farms(person_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT FarmId FROM agr.FarmPeople WHERE PersonId = ?
    """, person_id)
    farm_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "farm_ids": farm_ids})