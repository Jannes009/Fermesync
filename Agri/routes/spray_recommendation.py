from flask import render_template, request, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
from datetime import datetime, timedelta
from decimal import Decimal
import math


@agri_bp.route("/spray-recommendation/create", methods=["GET"])
@login_required
def create_spray_recommendation():
    if "SPRAY_REC_CREATE" not in current_user.permissions:
        abort(403)

    return render_template(
        "spray_recommendation.html"
    )

@agri_bp.route("/spray-recommendation/methods/<int:project_id>", methods=["GET"])
@login_required
def methods_for_project(project_id):
    if "SPRAY_REC_CREATE" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT
                SM.IdSprayMethod,
                SM.SprayMethodName
            FROM agr.ProjectAttributes PA
            JOIN agr.SprayMethod SM
                ON SM.SprayMethodFarmId = PA.ProjAttrFarmId
            WHERE PA.ProjAttrProjectId = ?
              AND PA.ProjAttrIsActive = 1
            ORDER BY SM.SprayMethodName
        """, (project_id,))

        methods = [
            {
                "id": row.IdSprayMethod,
                "name": row.SprayMethodName
            }
            for row in cur.fetchall()
        ]
        return jsonify({"success": True, "methods": methods})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "methods": []}), 500
    finally:
        conn.close()

def _fetch_all_product_catalog(cursor, warehouse_ids):
    placeholders = ','.join('?' for _ in warehouse_ids)
    cursor.execute(f"""
        SELECT
            SW.StockID AS StockLink,
            SI.StockCode,
            SI.StockDescription,
            SW.WhseID AS WhseLink,
            STK.ChemStockStockingUnitId AS StockingUnitId,
            STOCKUOM.cUnitCode AS StockingUnitCode,
            STK.ChemStockPurchasingUnitId AS PurchaseUnitId,
            PURCHASEUOM.cUnitCode AS PurchaseUnitCode,
            ACT.ChemActIngredient,
            CRP.StkCrpCropId AS CropId,
            CRP.StkCrpRegNumber,
            CRP.StkCrpWitholdingPeriodDef,
            CRP.StkCrpFunctionDef
        FROM cmn._uvStockWarehouse SW
        JOIN cmn._uvStockItems SI ON SI.StockLink = SW.StockID
        JOIN agr.ChemStock STK ON STK.ChemStockLink = SW.StockID
        LEFT JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = STK.ChemStockActiveIngrId
        LEFT JOIN agr.ChemStockCrop CRP ON CRP.StkCrpChemStockId = STK.IdChemStock
        LEFT JOIN cmn._uvStockUnits SU ON SU.StockLink = SW.StockID
            AND SU.PurchaseUnitId = STK.ChemStockPurchasingUnitId
        LEFT JOIN cmn._uvUOM STOCKUOM ON STOCKUOM.idUnits = STK.ChemStockStockingUnitId
        LEFT JOIN cmn._uvUOM PURCHASEUOM ON PURCHASEUOM.idUnits = SU.PurchaseUnitId
        WHERE SW.WhseID IN ({placeholders})
        ORDER BY ACT.ChemActIngredient, SI.StockDescription
    """, tuple(warehouse_ids))

    products = {}
    for row in cursor.fetchall():
        product = products.setdefault(row.StockLink, {
            "product_link": row.StockLink,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "warehouse_ids": [],
            "crop_ids": [],
            "stocking_uom_id": row.StockingUnitId,
            "stocking_uom_code": row.StockingUnitCode,
            "purchase_uom_id": row.PurchaseUnitId,
            "purchase_uom_code": row.PurchaseUnitCode,
            "active_ingredient": row.ChemActIngredient,
            "crop_details": []
        })
        if row.WhseLink not in product["warehouse_ids"]:
            product["warehouse_ids"].append(row.WhseLink)
        if row.CropId is not None and row.CropId not in product["crop_ids"]:
            product["crop_ids"].append(row.CropId)
            product["crop_details"].append({
                "crop_id": row.CropId,
                "reg_number": row.StkCrpRegNumber,
                "witholding_period": row.StkCrpWitholdingPeriodDef,
                "function": row.StkCrpFunctionDef
            })
    return list(products.values())

@agri_bp.route("/fetch_products_for_catalog", methods=["GET"])
@login_required
def fetch_products_for_catalog():
    if not current_user.warehouses:
        return jsonify({"success": False, "message": "No warehouses available", "products": []}), 400
    conn = create_db_connection()
    try:
        products = _fetch_all_product_catalog(conn.cursor(), current_user.warehouses)
        return jsonify({"success": bool(products), "products": products, "message": None if products else "No products found for selected warehouse and crop"})
    finally:
        conn.close()


@agri_bp.route("/fetch_methods_for_farms", methods=["GET"])
@login_required
def fetch_methods_for_farms():
    conn = create_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT IdSprayMethod, SprayMethodFarmId, SprayMethodName,
                   SprayMethodWaterPerHa, SprayMethodTankSize
            FROM agr.SprayMethod
            ORDER BY SprayMethodFarmId, SprayMethodName
        """)
        methods = [{
            "id": row.IdSprayMethod,
            "farm_id": row.SprayMethodFarmId,
            "name": row.SprayMethodName,
            "water_per_ha": row.SprayMethodWaterPerHa,
            "tank_size": row.SprayMethodTankSize
        } for row in cur.fetchall()]
        return jsonify({"success": True, "methods": methods})
    finally:
        conn.close()


@agri_bp.route("/fetch_projects_for_warehouse", methods=["GET"])
@login_required
def fetch_projects_for_warehouse():
    # Accept optional warehouse_id; if omitted, return projects for current user's warehouses
    warehouse_id = request.args.get("warehouse_id")

    conn = create_db_connection()
    cursor = conn.cursor()

    if warehouse_id:
        cursor.execute("""
            SELECT DISTINCT p.ProjectLink, p.ProjectCode, pa.ProjAttrCropId, pa.ProjAttrHa,
                     c.CropThemeColor, pa.ProjAttrBlockNo, pa.ProjAttrWhseId, pa.ProjAttrFarmId,
                     pa.ProjAttrDefaultSprayMethodId, pa.ProjAttrDefaultDose,
                     pa.ProjAttrDefaultWaterPerHa, pa.ProjAttrDefaultWaterPerTank
            FROM cmn._uvProject p
            JOIN agr.ProjectAttributes pa
                ON pa.ProjAttrProjectId = p.ProjectLink
            LEFT JOIN agr.Crop c
                ON c.IdCrop = pa.ProjAttrCropId
            WHERE pa.ProjAttrWhseId = ?
              AND pa.ProjAttrIsActive = 1
            ORDER BY p.ProjectCode
        """, (warehouse_id,))
    else:
        whse_ids = tuple(current_user.warehouses or [])
        if not whse_ids:
            conn.close()
            return jsonify({"success": False, "message": "No warehouses available for current user", "projects": []}), 400
        placeholders = ','.join('?' for _ in whse_ids)
        cursor.execute(f"""
            SELECT DISTINCT p.ProjectLink, p.ProjectCode, pa.ProjAttrCropId, pa.ProjAttrHa,
                     c.CropThemeColor, pa.ProjAttrBlockNo, pa.ProjAttrWhseId, pa.ProjAttrFarmId,
                     pa.ProjAttrDefaultSprayMethodId, pa.ProjAttrDefaultDose,
                     pa.ProjAttrDefaultWaterPerHa, pa.ProjAttrDefaultWaterPerTank
            FROM cmn._uvProject p
            JOIN agr.ProjectAttributes pa
                ON pa.ProjAttrProjectId = p.ProjectLink
            LEFT JOIN agr.Crop c
                ON c.IdCrop = pa.ProjAttrCropId
            WHERE pa.ProjAttrWhseId IN ({placeholders})
              AND pa.ProjAttrIsActive = 1
            ORDER BY p.ProjectCode
        """, whse_ids)

    rows = cursor.fetchall()
    conn.close()

    projects = [
        {
            "project_id": row.ProjectLink,
            "project_code": row.ProjectCode,
            "proj_attr_crop_id": row.ProjAttrCropId,
            "proj_attr_ha": float(row.ProjAttrHa or 0),
            "crop_theme_color": row.CropThemeColor,
            "proj_attr_block_no": getattr(row, 'ProjAttrBlockNo', None) if hasattr(row, 'ProjAttrBlockNo') else (row[5] if len(row) > 5 else None),
            "proj_attr_whse_id": getattr(row, 'ProjAttrWhseId', None) if hasattr(row, 'ProjAttrWhseId') else (row[6] if len(row) > 6 else None),
            "proj_attr_farm_id": getattr(row, 'ProjAttrFarmId', None) if hasattr(row, 'ProjAttrFarmId') else (row[7] if len(row) > 7 else None),
            "default_spray_method_id": getattr(row, 'ProjAttrDefaultSprayMethodId', None),
            "default_dose": getattr(row, 'ProjAttrDefaultDose', None),
            "default_water_per_ha": getattr(row, 'ProjAttrDefaultWaterPerHa', None),
            "default_water_per_tank": getattr(row, 'ProjAttrDefaultWaterPerTank', None)
        }
        for row in rows
    ]

    return jsonify({"success": True, "projects": projects})


@agri_bp.route("/spray-recommendation/context", methods=["GET"])
@login_required
def spray_recommendation_context():
    if "SPRAY_REC_CREATE" not in current_user.permissions:
        abort(403)

    project_ids = []
    for raw_project_id in request.args.getlist("project_id"):
        try:
            project_ids.append(int(raw_project_id))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid project ID"}), 400

    project_ids = list(dict.fromkeys(project_ids))
    if not project_ids:
        return jsonify({"success": True, "items": [], "year": datetime.now().year})

    start_week = request.args.get("start_week")
    end_week = request.args.get("end_week")

    conn = create_db_connection()
    cur = conn.cursor()
    project_placeholders = ",".join("?" for _ in project_ids)
    cur.execute(f"""
        SELECT DISTINCT HEA.SprayHWeek
        FROM agr._uvSprayStockRequirementsPerProject QTY
        JOIN agr.SprayHeader HEA ON HEA.IdSprayH = QTY.IdSprayH
        WHERE QTY.ProjectId IN ({project_placeholders})
          AND HEA.SprayHWeek IS NOT NULL
        ORDER BY HEA.SprayHWeek
    """, tuple(project_ids))
    existing_weeks = [str(row.SprayHWeek) for row in cur.fetchall()]

    def week_number(value):
        try:
            year_text, week_text = value.split("-", 1)
            year_value = int(year_text)
            week_value = int(week_text)
            if len(year_text) != 4 or not 1 <= week_value <= 53:
                raise ValueError
            return year_value, week_value
        except (AttributeError, TypeError, ValueError):
            return None

    parsed_weeks = [week_number(value) for value in existing_weeks]
    parsed_weeks = [value for value in parsed_weeks if value is not None]
    available_weeks = []
    if parsed_weeks:
        first_year, first_week = min(parsed_weeks)
        last_year, last_week = max(parsed_weeks)
        current_year, current_week = first_year, first_week
        while (current_year, current_week) <= (last_year, last_week):
            available_weeks.append(f"{current_year:04d}-{current_week:02d}")
            current_week += 1
            if current_week > 53:
                current_year += 1
                current_week = 1

    if not available_weeks:
        conn.close()
        return jsonify({"success": True, "items": [], "available_weeks": []})

    start_week = start_week or available_weeks[0]
    end_week = end_week or available_weeks[-1]
    if start_week not in available_weeks or end_week not in available_weeks:
        conn.close()
        return jsonify({"success": False, "message": "Invalid week range"}), 400
    if start_week > end_week:
        conn.close()
        return jsonify({"success": False, "message": "Invalid week range"}), 400

    cur.execute(f"""
        SELECT
            QTY.ProjectId,
            PROJ.ProjectName,
            QTY.StockId,
            STK.StockDescription,
            SUM(QTY.SprayLineTotalQty) AS TotalQty,
            QTY.UoMId,
            UOM.cUnitCode,
            HEA.SprayHWeek,
            HEA.SprayHDescription,
            CA.ChemActIngredient
        FROM agr._uvSprayStockRequirementsPerProject QTY
        JOIN cmn._uvStockItems STK ON STK.StockLink = QTY.StockId
        JOIN cmn._uvUOM UOM ON UOM.idUnits = QTY.UoMId
        JOIN agr.SprayHeader HEA ON HEA.IdSprayH = QTY.IdSprayH
        LEFT JOIN cmn._uvProject PROJ ON PROJ.ProjectLink = QTY.ProjectId
        JOIN agr.ChemStock CS on CS.ChemStockLink = QTY.StockId
        LEFT JOIN agr.ChemActiveIngredient CA on CA.IdChemAct = CS.ChemStockActiveIngrId
        WHERE QTY.ProjectId IN ({project_placeholders})
          AND HEA.SprayHWeek >= ?
          AND HEA.SprayHWeek <= ?
        GROUP BY QTY.ProjectId, PROJ.ProjectName, QTY.StockId,
                 CA.ChemActIngredient,
                 STK.StockDescription, QTY.UoMId, UOM.cUnitCode,
                 HEA.SprayHWeek, HEA.SprayHDescription
        ORDER BY CA.ChemActIngredient, STK.StockDescription, QTY.ProjectId, HEA.SprayHWeek
    """, tuple(project_ids) + (start_week, end_week))

    items = []
    for row in cur.fetchall():
        items.append({
            "project_id": row.ProjectId,
            "project_name": row.ProjectName,
            "stock_id": row.StockId,
            "stock_description": row.StockDescription,
            "total_qty": float(row.TotalQty or 0),
            "uom_id": row.UoMId,
            "uom": row.cUnitCode,
            "spray_week": row.SprayHWeek,
            "description": row.SprayHDescription,
            "active_ingredient": row.ChemActIngredient
        })

    conn.close()
    return jsonify({"success": True, "items": items, "available_weeks": available_weeks,
                    "start_week": start_week, "end_week": end_week})



def to_decimal(val):
    if val is None or val == '':
        return None
    return Decimal(str(val))


def get_inserted_id(cursor, table_name):
    row = cursor.fetchone()
    value = row[0] if row else None

    if value is None:
        cursor.execute(f"SELECT CAST(IDENT_CURRENT('{table_name}') AS int) AS last_id")
        row = cursor.fetchone()
        value = row[0] if row else None

    if value is None:
        raise ValueError(f"Unable to read the inserted ID for {table_name}.")

    return int(value)


def generate_spray_no(cursor):
    cursor.execute("""
        DECLARE @DocumentNumber VARCHAR(30);
        EXEC cmn.sp_GetNextDocumentNumber @DocumentType = ?, @DocumentNumber = @DocumentNumber OUTPUT;
        SELECT @DocumentNumber AS DocumentNumber;
    """, ('REC',))
    row = cursor.fetchone()
    if not row:
        return None
    return getattr(row, 'DocumentNumber', row[0])


@agri_bp.route('/spray-recommendation/submit', methods=['POST'])
def submit_spray_recommendation():
    if "SPRAY_REC_CREATE" not in current_user.permissions:
        abort(403)
    
    conn = None
    cursor = None

    try:
        data = request.get_json()

        if not data:
            print("No JSON payload received in request.")
            return jsonify({
                "success": False,
                "message": "No payload received"
            }), 400
        print(data)
        projects = data.get('projects', [])
        lines = data.get('lines', [])
        mixes = data.get('mixes', [])

        if not projects:
            return jsonify({
                "success": False,
                "message": "No projects supplied"
            }), 400

        if not lines:
            return jsonify({
                "success": False,
                "message": "No product lines supplied"
            }), 400

        # Validate description is provided
        spray_description = (data.get('spray_description') or '').strip()
        if not spray_description:
            return jsonify({
                "success": False,
                "message": "Spray description is required"
            }), 400


        application_type = data.get('application_type')

        if application_type == 'per_100l':
            dose_basis = 'PER_100L'
        else:
            dose_basis = 'PER_HA'

        if application_type == 'per_ha_direct':
            mix = False
        else:
            mix = True


        conn = create_db_connection()
        cursor = conn.cursor()

        # spray_description already validated above
        spray_date = data.get('spray_date', datetime.today().date())
        created_by = current_user.id
        scouting_note = data.get('scouting_note')
        warehouse_id = data.get('warehouse_id', 1)
        method_id = data.get('method_id')

        # if spray_date may be a string from JSON:
        if isinstance(spray_date, str):
            math_spray_date = datetime.strptime(spray_date, "%Y-%m-%d").date()
        else:           
            math_spray_date = spray_date

        iso_year, iso_week, _ = math_spray_date.isocalendar()

        spray_week = f"{iso_year}-{iso_week:02d}"

        # Extract crop ID from first project (all projects must have same crop now)
        crop_id = None
        if projects:
            first_project_id = projects[0].get('project_id')
            cursor.execute("""
                SELECT ProjAttrCropId FROM agr.ProjectAttributes 
                WHERE ProjAttrProjectId = ? AND ProjAttrIsActive = 1
            """, first_project_id)
            crop_row = cursor.fetchone()
            if crop_row:
                crop_id = crop_row[0]

        spray_no = generate_spray_no(cursor)
        # -------------------------------
        # INSERT HEADER
        # -------------------------------

        cursor.execute("""
            INSERT INTO agr.SprayHeader (
                SprayHNo,
                SprayHDescription,
                SprayHDate,
                SprayHCreatedBy,
                SprayHCreatedAt,
                SprayHStatus,
                SprayHScouting,
                SprayHMethodId,
                SprayHWhseId,
                SprayLineDoseBasis,
                SprayHWeek,
                SprayHWaterPerTank,
                SprayHWaterPerHa,
                SprayHTotalWater,
                SprayHTotalHa,
                SprayHMix,
                SprayHCropId,
                SprayHRequireDateTime,
                SprayHRequireWeather,
                SprayHModifiedAt
            )
            VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """,
            spray_no,
            spray_description,
            spray_date,
            created_by,
            datetime.now(),
            'RECOMMENDED',
            scouting_note,
            method_id,
            warehouse_id,
            dose_basis,
            spray_week,
            to_decimal(data.get('water_per_tank')),
            to_decimal(data.get('water_per_ha')),
            to_decimal(data.get('total_water')),
            to_decimal(data.get('total_ha')),
            mix,
            crop_id,
            1 if data.get('require_date_time', True) else 0,
            1 if data.get('require_weather', True) else 0,
            datetime.now()
        )

        cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS int) AS spray_id")
        spray_id = get_inserted_id(cursor, 'agr.SprayHeader')


        # -------------------------------
        # INSERT PROJECTS
        # -------------------------------

        for p in projects:

            cursor.execute("""
            INSERT INTO agr.SprayProjects (
                SprayPSprayId,
                SprayPProjectId,
                SprayPHa,
                SprayPWaterPerHa,
                SprayPTotalWater,
                SprayPVarietyId,
                SprayPBlockNo,
                SprayPPlantDate,
                SprayPAgriculturist,
                SprayPProjectManager,
                SprayPHarvestDate,
                SprayH80PercPetalFallDate
            )
            SELECT
                ?,               -- SprayPSprayId
                ?,               -- SprayPProjectId
                ?,               -- SprayPHa
                ?,               -- SprayPWaterPerHa
                ?,               -- SprayPTotalWater
                ProjAttrVarietyId,
                ProjAttrBlockNo,
                ProjAttrPlantDate,
                ProjAttrAgriculturist,
                ProjAttrProjectManager,
                ProjAttrHarvestDate,
                ProjAttr80PercPetalFallDate
            FROM agr.ProjectAttributes
            WHERE ProjAttrIsActive = 1
            AND ProjAttrProjectId = ?
            """,
                spray_id,
                p['project_id'],
                to_decimal(p['ha']),
                to_decimal(p.get('water_per_ha')),
                to_decimal(p.get('total_water')),
                p['project_id']
            )


        # -------------------------------
        # INSERT PRODUCT LINES
        # -------------------------------

        for line in lines:

            cursor.execute("""
                INSERT INTO agr.SprayLines (
                    SprayLineHeaderId,
                    SprayLineStkId,
                    SprayLineQtyPer100L,
                    SprayLineQtyPerHa,
                    SprayLineUoMId,
                    SprayLineTotalQty,
                    SprayLineRegNumber,
                    SprayLineWitholdingPeriod,
                    SprayLineFunction
                )
                VALUES (?,?,?,?,?,?,?,?,?)
            """,
                spray_id,
                line['stock_id'],
                to_decimal(line.get('qty_per_100l')),
                to_decimal(line.get('qty_per_ha')),
                line.get('uom_id'),
                to_decimal(line['total_qty']),
                line.get('reg_number'),
                line.get('witholding_period'),
                line.get('function')
            )


        # -------------------------------
        # INSERT MIXES
        # -------------------------------

        for mix in mixes:

            cursor.execute("""
                INSERT INTO agr.SprayMix (
                    SprayMixHeaderId,
                    SprayMixNumber,
                    SprayMixHa,
                    SprayMixWater
                )
                VALUES (?,?,?,?)
            """,
                spray_id,
                mix['mix_number'],
                to_decimal(mix['mix_ha']),
                to_decimal(mix['mix_water'])
            )

            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS int) AS mix_id")
            mix_id = get_inserted_id(cursor, 'agr.SprayMix')


            # ---------------------------
            # INSERT MIX LINES
            # ---------------------------

            for ml in mix.get('lines', []):

                cursor.execute("""
                    INSERT INTO agr.SprayMixLines (
                        SprayMixLineMixId,
                        SprayMixLineStockId,
                        SprayMixLineQty,
                        SprayMixLineUoMId
                    )
                    VALUES (?,?,?,?)
                """,
                    mix_id,
                    ml['stock_id'],
                    to_decimal(ml['qty']),
                    ml.get('uom_id')
                )


        # -------------------------------
        # COMMIT
        # -------------------------------

        conn.commit()

        return jsonify({
            "success": True,
            "id": spray_id,
            "spray_no": spray_no
        })


    except Exception as e:
        print(f"Error occurred while submitting spray recommendation: {e}")
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@agri_bp.route("/spray-recommendations-summary", methods=["GET"])
@login_required
def spray_recommendations_summary():
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)
    return render_template("spray_recommendation_summary.html")


@agri_bp.route("/spray-recommendations", methods=["GET"])
@login_required
def get_spray_recommendations():
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()

    whse_ids = tuple(current_user.warehouses or [])
    if not whse_ids:
        return jsonify({"success": False, "message": "No warehouses available", "items": []}), 400

    placeholders = ','.join('?' for _ in whse_ids)
    query = f"""
    SELECT
        HEA.IdSprayH,
        HEA.SprayHNo,
        HEA.SprayHDescription,
        HEA.SprayHWeek,
        HEA.SprayHStatus,
        HEA.SprayHStartDateTime,
        HEA.SprayHEndDateTime,
        HEA.SprayHWhseId,
        WHSE.WhseDescription AS WarehouseName,
        HEA.SprayHExecutionId,
        HEA.SprayHFinalised,
        HEA.SprayHModifiedAt,
        BLK.ProjAttrBlockNo,
        FRM.FarmName
    FROM agr.SprayHeader HEA
    LEFT JOIN cmn._uvWarehouses WHSE ON WHSE.WhseLink = HEA.SprayHWhseId
    OUTER APPLY (
        SELECT STRING_AGG(X.ProjAttrBlockNo, ', ') AS ProjAttrBlockNo
        FROM (
            SELECT DISTINCT PROJ.ProjAttrBlockNo
            FROM agr.SprayProjects SPROJ
            JOIN agr.ProjectAttributes PROJ
                ON PROJ.ProjAttrProjectId = SPROJ.SprayPProjectId
            WHERE SPROJ.SprayPSprayId = HEA.IdSprayH
        ) X
    ) BLK
    OUTER APPLY (
        SELECT STRING_AGG(X.FarmName, ', ') AS FarmName
        FROM (
            SELECT DISTINCT FRM.FarmName
            FROM agr.SprayProjects SPROJ
            JOIN agr.ProjectAttributes PROJ
                ON PROJ.ProjAttrProjectId = SPROJ.SprayPProjectId
            LEFT JOIN agr.Farm FRM
                ON FRM.IdFarm = PROJ.ProjAttrFarmId
            WHERE SPROJ.SprayPSprayId = HEA.IdSprayH
        ) X
    ) FRM
    WHERE SprayHWhseId IN ({placeholders})
    ORDER BY HEA.SprayHNo DESC;
    """
    cur.execute(query, whse_ids)
    rows = cur.fetchall()

    result = []
    for row in rows:
        result.append({
            "id": row.IdSprayH,
            "spray_no": row.SprayHNo,
            "description": row.SprayHDescription,
            "week": row.SprayHWeek,
            "status": row.SprayHStatus,
            "start_date": row.SprayHStartDateTime.isoformat() if row.SprayHStartDateTime else None,
            "end_date": row.SprayHEndDateTime.isoformat() if row.SprayHEndDateTime else None,
            "warehouse_id": row.SprayHWhseId,
            "warehouse_name": row.WarehouseName,
            "execution_id": row.SprayHExecutionId,
            "block_no": row.ProjAttrBlockNo,
            "farm_name": row.FarmName,
            "finalised": bool(row.SprayHFinalised),
            "modified_at": row.SprayHModifiedAt.isoformat() if row.SprayHModifiedAt else None
        })

    conn.close()
    print(f"Returning {len(result)} spray recommendations for warehouses: {whse_ids}")
    return jsonify({"success": True, "items": result})

@agri_bp.route("/spray-recommendation/method-water/<int:method_id>", methods=["GET"])
@login_required
def get_method_water(method_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT SprayMethodWaterPerHa FROM agr.SprayMethod WHERE IdSprayMethod = ?", method_id)
    row = cur.fetchone()
    conn.close()
    if row:
        return jsonify({"water_per_ha": row[0]})
    else:
        return jsonify({"water_per_ha": None}), 404



@agri_bp.route("/execution/create", methods=["POST"])
@login_required
def create_execution():
    if "SPRAY_EXEC_CREATE" not in current_user.permissions:
        abort(403)
    
    data = request.get_json() or {}
    recommendation_ids = data.get("recommendation_ids", [])
    execution_date = data.get("execution_date")

    try:
        recommendation_ids = [int(r) for r in recommendation_ids if isinstance(r, (int, str)) and str(r).strip().isdigit()]
    except Exception:
        recommendation_ids = []

    recommendation_ids = list(dict.fromkeys(recommendation_ids))
    if not recommendation_ids:
        return jsonify({"success": False, "message": "Invalid recommendation IDs"}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    placeholders = ','.join('?' for _ in recommendation_ids)
    cur.execute(f"""
        SELECT SprayHWhseId, SprayHExecutionId
        FROM agr.SprayHeader
        WHERE IdSprayH IN ({placeholders})
    """, tuple(recommendation_ids))
    rows = cur.fetchall()

    if len(rows) != len(recommendation_ids):
        conn.close()
        return jsonify({"success": False, "message": "One or more selected recommendations do not exist"}), 400

    warehouse_ids = [row.SprayHWhseId for row in rows]
    existing_execution = [row.SprayHExecutionId for row in rows if row.SprayHExecutionId is not None]

    if existing_execution:
        conn.close()
        return jsonify({"success": False, "message": "One or more selected recommendations are already assigned to an execution"}), 400

    if len(set(warehouse_ids)) > 1:
        conn.close()
        return jsonify({"success": False, "message": "Selected recommendations must all come from the same warehouse"}), 400

    try:
        if execution_date:
            if isinstance(execution_date, str):
                try:
                    execution_date = datetime.strptime(execution_date, "%Y-%m-%d").date()
                except ValueError:
                    execution_date = datetime.strptime(execution_date, "%Y-%m-%d %H:%M:%S").date()
            elif isinstance(execution_date, datetime):
                execution_date = execution_date.date()
        else:
            # Determine execution date as earliest scheduled date among the selected recommendations
            placeholders = ','.join('?' for _ in recommendation_ids)
            cur.execute(f"SELECT MIN(COALESCE(SprayHStartDateTime, SprayHDate)) AS EarliestDate FROM agr.SprayHeader WHERE IdSprayH IN ({placeholders})", tuple(recommendation_ids))
            row = cur.fetchone()
            execution_date = None
            if row:
                try:
                    execution_date = row.EarliestDate
                except Exception:
                    execution_date = row[0]

            if execution_date is None:
                execution_date = datetime.now()

        if hasattr(execution_date, 'isoformat'):
            execution_date = execution_date.isoformat()

        # Use a driver-safe insert path to avoid ODBC SQLBindParameter issues on OUTPUT INSERTED.
        cur.execute("""
            INSERT INTO agr.SprayExecution (SprExecDate, SprExecResponsiblePerson)
            VALUES (CONVERT(date, ?), NULL)
        """, (execution_date,))
        cur.execute("SELECT CAST(SCOPE_IDENTITY() AS int) AS execution_id")
        execution_id = get_inserted_id(cur, 'agr.SprayExecution')

        # Link all selected spray headers to this execution in a single update
        cur.execute(f"UPDATE agr.SprayHeader SET SprayHExecutionId = ?, SprayHStatus = 'SCHEDULED', SprayHModifiedAt = ? WHERE IdSprayH IN ({placeholders})", (execution_id, datetime.now()) + tuple(recommendation_ids))

        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Execution created successfully", "execution_id": execution_id})
    except Exception as e:
        print(f"Error creating execution: {e}")
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error creating execution: {str(e)}"}), 500


@agri_bp.route("/executions/pending", methods=["GET"])
@login_required
def get_pending_executions():
    if "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, p.PersonName,
               COUNT(h.IdSprayH) as rec_count
        FROM agr.SprayExecution b
        LEFT JOIN agr.People p ON p.IdPerson = b.SprExecResponsiblePerson
        LEFT JOIN agr.SprayHeader h ON h.SprayHExecutionId = b.IdSprExec
        WHERE b.SprExecFinalised != 1
        GROUP BY b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, p.PersonName
        ORDER BY b.SprExecDate DESC
    """)
    
    executions = []
    for row in cur.fetchall():
        executions.append({
            "id": row.IdSprExec,
            "date": row.SprExecDate.isoformat() if row.SprExecDate else None,
            "responsible_person": row.PersonName,
            "recommendation_count": row.rec_count
        })
    
    conn.close()
    return jsonify(executions)

@agri_bp.route("/executions/completed", methods=["GET"])
@login_required
def get_completed_executions():
    if "SPRAY_EXEC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, p.PersonName,
               COUNT(h.IdSprayH) as rec_count
        FROM agr.SprayExecution b
        LEFT JOIN agr.People p ON p.IdPerson = b.SprExecResponsiblePerson
        LEFT JOIN agr.SprayHeader h ON h.SprayHExecutionId = b.IdSprExec
        WHERE b.SprExecFinalised = 1
        GROUP BY b.IdSprExec, b.SprExecDate, b.SprExecResponsiblePerson, p.PersonName
        ORDER BY b.SprExecDate DESC
    """)

    executions = []
    for row in cur.fetchall():
        executions.append({
            "id": row.IdSprExec,
            "date": row.SprExecDate.isoformat() if row.SprExecDate else None,
            "responsible_person": row.PersonName,
            "recommendation_count": row.rec_count
        })

    conn.close()
    return jsonify(executions)
