from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
from datetime import datetime
from decimal import Decimal
import math


@agri_bp.route("/spray-recommendation/create", methods=["GET"])
@login_required
def create_spray_recommendation():
    conn = create_db_connection()
    cur = conn.cursor()

    # project attributes – each row joins a project to its crop/variety/ha
    cur.execute("""
    SELECT 
        p.ProjectLink,
        p.ProjectCode,
        pa.ProjAttrCropId,
        c.CropCode,
        pa.ProjAttrVarietyId,
        v.VarietyCode,
        pa.ProjAttrHa
    FROM cmn._uvProject p
    JOIN agr.ProjectAttributes pa
        ON pa.ProjAttrProjectId = p.ProjectLink
    LEFT JOIN agr.Crop c ON c.IdCrop = pa.ProjAttrCropId
    LEFT JOIN agr.Variety v ON v.IdVariety = pa.ProjAttrVarietyId
    ORDER BY p.ProjectCode
    """)
    projects = cur.fetchall()

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

    # Generate next spray number prefix SPR###
    cur.execute("SELECT ISNULL(MAX(SprayHNo),0) AS max_no FROM agr.SprayHeader WHERE SprayHNo LIKE 'SPR%'")
    max_no_row = cur.fetchone()
    max_no = max_no_row.max_no if max_no_row else None
    if max_no and max_no.upper().startswith('SPR'):
        try:
            next_num = int(max_no[3:]) + 1
        except Exception:
            next_num = 1
    else:
        next_num = 1
    spray_no = f"SPR{next_num:03d}"

    conn.close()

    return render_template(
        "spray_recommendation.html",
        spray_no=spray_no,
        projects=projects,
        methods=spray_methods,
        warehouses=warehouses
    )

@agri_bp.route("/spray-recommendation/default_qty_per_ha/<int:stock_id>", methods=["GET"])
@login_required
def get_default_qty_per_ha(stock_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT [ChemStockDefaultQtyPer100L]
        FROM agr.ChemStock
        WHERE [ChemStockLink] = ?
    """, (stock_id,))
    result = cur.fetchone()

    conn.close()

    if result:
        return jsonify({"default_qty_per_ha": result.ChemStockDefaultQtyPer100L})
    else:
        return jsonify({"default_qty_per_ha": 0})
    
@agri_bp.route("/fetch_products_linked_with_warehouse", methods=["GET"])
@login_required
def fetch_products_linked_with_warehouse():
    whse_id = request.args.get("warehouse_id")
    if not whse_id:
        return jsonify({"status": "error", "message": "Warehouse ID is required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
    SELECT StockLink, StockCode, StockDescription,
    WhseLink, WhseCode, WhseName, QtyOnHand
    ,StockingUnitId, StockingUnitCode
    ,PurchaseUnitId, PurchaseUnitCode
    ,PurchaseUnitCatId, STK.ChemStockActiveIngr
    FROM [stk]._uvInventoryQty QTY
    JOIN [agr].[ChemStock] STK on STK.[ChemStockLink] = QTY.StockLink
    Where WhseLink = ?
    ORDER BY ChemStockActiveIngr, StockDescription
    """, (whse_id,))
    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_link": row.StockLink,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "WhseLink": row.WhseLink,
            "WhseCode": row.WhseCode,
            "WhseName": row.WhseName,
            "qty_in_whse": row.QtyOnHand,
            "stocking_uom_id": row.StockingUnitId,
            "stocking_uom_code": row.StockingUnitCode,
            "purchase_uom_id": row.PurchaseUnitId,
            "purchase_uom_code": row.PurchaseUnitCode,
            "uom_cat_id": row.PurchaseUnitCatId,
            "active_ingredient": row.ChemStockActiveIngr
        }
        for row in rows
    ]
    return jsonify({"products": products_list})


def to_decimal(val):
    if val is None or val == '':
        return None
    return Decimal(str(val))


def generate_spray_no(cursor):
    """
    Example:
    SPR000123
    Replace with your numbering logic if you already have one.
    """
    cursor.execute("""
        SELECT ISNULL(MAX(IdSprayH),0)+1
        FROM agr.SprayHeader
    """)
    next_id = cursor.fetchone()[0]
    return f"SPR-{str(next_id).zfill(6)}"


@agri_bp.route('/spray-recommendation/submit', methods=['POST'])
def submit_spray_recommendation():

    conn = None
    cursor = None

    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "No payload received"
            }), 400

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


        application_type = data.get('application_type')

        if application_type == 'per_100l':
            dose_basis = 'PER_100L'
        else:
            dose_basis = 'PER_HA'

        if application_type == 'per_ha':
            mix = False
        else:
            mix = True


        conn = create_db_connection()
        cursor = conn.cursor()

        spray_no = generate_spray_no(cursor)

        # pull these from form if you add them to payload
        spray_description = data.get('spray_description', 'Spray Recommendation')
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
                SprayHMix
            )
            OUTPUT INSERTED.IdSprayH
            VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
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
            mix
        )

        spray_id = int(cursor.fetchone()[0])


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
                SprayPCropId,
                SprayPVarietyId,
                SprayPBlockNo,
                SprayPPlantDate,
                SprayPAgriculturist,
                SprayPProjectManager
            )
            SELECT
                ?,               -- SprayPSprayId
                ?,               -- SprayPProjectId
                ?,               -- SprayPHa
                ?,               -- SprayPWaterPerHa
                ?,               -- SprayPTotalWater
                ProjAttrCropId,
                ProjAttrVarietyId,
                ProjAttrBlockNo,
                ProjAttrPlantDate,
                ProjAttrAgriculturist,
                ProjAttrProjectManager
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
                    SprayLineTotalQty
                )
                VALUES (?,?,?,?,?,?)
            """,
                spray_id,
                line['stock_id'],
                to_decimal(line.get('qty_per_100l')),
                to_decimal(line.get('qty_per_ha')),
                line.get('uom_id'),
                to_decimal(line['total_qty'])
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
                OUTPUT INSERTED.IdSprayMix
                VALUES (?,?,?,?)
            """,
                spray_id,
                mix['mix_number'],
                to_decimal(mix['mix_ha']),
                to_decimal(mix['mix_water'])
            )

            mix_id = int(cursor.fetchone()[0])


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
    return render_template("spray_recommendation_summary.html")


@agri_bp.route("/spray-recommendations", methods=["GET"])
@login_required
def get_spray_recommendations():
    conn = create_db_connection()
    cur = conn.cursor()

    query = """
    SELECT
        HEA.IdSprayH,
        HEA.SprayHNo,
        HEA.SprayHDate,
        HEA.SprayHStatus,
        HEA.SprayHDescription,
        WHSE.WhseDescription,
        WHSE.WhseLink,
        DATEPART(WEEK, HEA.SprayHDate) AS week_number,
        DATEPART(YEAR, HEA.SprayHDate) AS year,
        CASE WHEN SUM(CASE WHEN REQ.QtyAvailable >= REQ.TotalQty THEN 0 ELSE 1 END) = 0 THEN 1 ELSE 0 END AS sufficient_stock
    FROM agr.SprayHeader HEA
    JOIN [agr].[_uvSprayStockRequirements] REQ on REQ.SprayId = HEA.IdSprayH
    JOIN cmn._uvWarehouses WHSE on WHSE.WhseLink = REQ.WhseId
    WHERE HEA.SprayHExecutionId IS NULL  -- Only show recommendations not already in a execution
    GROUP BY HEA.IdSprayH, HEA.SprayHNo, HEA.SprayHDate, HEA.SprayHStatus, HEA.SprayHDescription, WHSE.WhseDescription, WHSE.WhseLink
    ORDER BY WHSE.WhseDescription, HEA.SprayHDate DESC
    """
    cur.execute(query)
    rows = cur.fetchall()

    # Group by warehouse, then by week
    warehouses = {}
    for row in rows:
        whse_name = row.WhseDescription
        whse_id = row.WhseLink
        week_key = f"Week {row.week_number}, {row.year}"
        
        if whse_name not in warehouses:
            warehouses[whse_name] = {
                "id": whse_id,
                "name": whse_name,
                "weeks": {}
            }
        
        if week_key not in warehouses[whse_name]["weeks"]:
            warehouses[whse_name]["weeks"][week_key] = {
                "week": week_key,
                "recommendations": []
            }
        
        warehouses[whse_name]["weeks"][week_key]["recommendations"].append({
            "id": row.IdSprayH,
            "spray_no": row.SprayHNo,
            "spray_date": str(row.SprayHDate) if row.SprayHDate else None,
            "status": row.SprayHStatus,
            "description": row.SprayHDescription,
            "sufficient_stock": row.sufficient_stock
        })

    # Convert to list format
    result = []
    for whse_name, whse_data in warehouses.items():
        weeks_list = []
        for week_key, week_data in whse_data["weeks"].items():
            weeks_list.append({
                "week": week_key,
                "recommendations": week_data["recommendations"]
            })
        result.append({
            "id": whse_data["id"],
            "name": whse_data["name"],
            "weeks": weeks_list
        })

    conn.close()
    return jsonify(result)

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


@agri_bp.route("/execution/responsible-persons", methods=["GET"])
@login_required
def get_responsible_persons():
    conn = create_db_connection()
    cur = conn.cursor()
    
    # Get users who can be responsible for executions - you might want to filter by role or department
    cur.execute("""
        SELECT IdPerson, PersonName
        FROM agr.People
        WHERE PersonSprayExecutionResponsible = 1 
        ORDER BY PersonName
    """)
    
    persons = [{"id": row.IdPerson, "name": row.PersonName} for row in cur.fetchall()]
    conn.close()
    return jsonify(persons)


@agri_bp.route("/execution/create", methods=["POST"])
@login_required
def create_execution():
    data = request.get_json()
    execution_date = data.get("execution_date")
    responsible_person = data.get("responsible_person")
    recommendation_ids = data.get("recommendation_ids", [])
    
    if not execution_date or not responsible_person or not recommendation_ids:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    conn = create_db_connection()
    cur = conn.cursor()
    
    try:
        # Create the execution
        cur.execute("""
            INSERT INTO agr.SprayExecution (SprExecDate, SprExecResponsiblePerson)
            OUTPUT INSERTED.IdSprExec
            VALUES (?, ?)
        """, execution_date, responsible_person)
        
        execution_id = cur.fetchone()[0]
        
        # Update the spray headers to link them to the execution
        # Note: This assumes SprayHeader has a column called SprayHExecutionId (int, nullable)
        # If this column doesn't exist, you'll need to add it: ALTER TABLE agr.SprayHeader ADD SprayHExecutionId int NULL
        for rec_id in recommendation_ids:
            cur.execute("""
                UPDATE agr.SprayHeader 
                SET SprayHExecutionId = ? , SprayHStatus = 'SCHEDULED'
                WHERE IdSprayH = ?
            """, execution_id, rec_id)
        
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Execution created successfully", "execution_id": execution_id})
    
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error creating execution: {str(e)}"}), 500


@agri_bp.route("/executions/pending", methods=["GET"])
@login_required
def get_pending_executions():
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
