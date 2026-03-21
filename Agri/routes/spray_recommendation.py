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

    # Generate next spray number prefix SPR###
    cur.execute("SELECT MAX(SprayHNo) AS max_no FROM agr.SprayHeader WHERE SprayHNo LIKE 'SPR%'")
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
        scouts=scouts,
        methods=spray_methods,
        warehouses=warehouses
    )

@agri_bp.route("/spray-recommendation/create", methods=["POST"])
@login_required
def save_spray_recommendation():
    conn = create_db_connection()
    cur = conn.cursor()

    json_data = request.get_json(silent=True)
    if json_data is not None:
        data = json_data
        spray_date = data.get("spray_date")
        application_type = data.get("application_type")
        method_id = data.get("method_id")
        warehouse_id = data.get("warehouse_id")
        projects = data.get("projects", []) or []
        lines = data.get("lines", []) or []
        print(data)
    else:
        data = request.form
        spray_date = data.get("spray_date")
        application_type = data.get("application_type")
        method_id = data.get("method_id")
        warehouse_id = data.get("warehouse_id")
        project_ids = data.getlist("project_ids")
        project_has = data.getlist("project_ha[]")
        project_water = data.getlist("project_water_per_ha[]")
        print(data)
        projects = []
        for pi, ha, w in zip(project_ids, project_has, project_water):
            projects.append({"project_id": pi, "ha": float(ha or 0), "water_per_ha": float(w or 0)})
        lines = []
        line_indexes = data.getlist("line_index[]")
        line_uom_ids = data.getlist("line_uom_id[]")
        for i, idx in enumerate(line_indexes):
            stk_id = data.get(f"product_{idx}")
            qty = data.get(f"qty_{idx}")
            qty_type = "per100l" if application_type == "spray" else "perha"
            uom_id = line_uom_ids[i] if i < len(line_uom_ids) else None
            if stk_id and qty:
                lines.append({
                    "stock_id": stk_id,
                    "qty": float(qty),
                    "qty_type": qty_type,
                    "uom_id": uom_id
                })

    try:

        if not spray_date:
            return jsonify({"success": False, "message": "Date is required."}), 400
        if not projects:
            return jsonify({"success": False, "message": "At least one project is required."}), 400
        if application_type not in ["spray", "direct"]:
            return jsonify({"success": False, "message": "Invalid application type."}), 400

        # method_id is optional for direct but required for spray
        if application_type == "spray" and not method_id:
            return jsonify({"success": False, "message": "Spray method is required for spray application."}), 400

        # Generate SPR### number
        cur.execute("SELECT MAX(SprayHNo) AS max_no FROM agr.SprayHeader WHERE SprayHNo LIKE 'SPR%'")
        max_no_row = cur.fetchone()
        max_no = max_no_row.max_no if max_no_row else None
        if max_no and max_no.upper().startswith('SPR'):
            try:
                next_int = int(max_no[3:]) + 1
            except Exception:
                next_int = 1
        else:
            next_int = 1
        spray_no = f"SPR{next_int:03d}"

        spray_description = data.get("spray_description", "")
        scouting_note = data.get("scouting_note", "")

        try:
            cur.execute("""
                INSERT INTO agr.SprayHeader
                (SprayHNo, SprayHDescription, SprayHScouting, SprayHDate, SprayHRecUserId, SprayHApplicationType, SprayHMethodId, SprayHWhseId, SprayHStatus)
                OUTPUT INSERTED.IdSprayH
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, spray_no, spray_description, scouting_note, spray_date, current_user.id, application_type, method_id, warehouse_id, "RECOMMENDED")
        except Exception:
            # fallback if SprayHScouting column does not exist
            cur.execute("""
                INSERT INTO agr.SprayHeader
                (SprayHNo, SprayHDescription, SprayHDate, SprayHRecUserId, SprayHApplicationType, SprayHMethodId, SprayHWhseId, SprayHStatus)
                OUTPUT INSERTED.IdSprayH
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, spray_no, spray_description, spray_date, current_user.id, application_type, method_id, warehouse_id, "RECOMMENDED")
        spray_header_id = cur.fetchone()[0]

        for project in projects:
            project_id = project.get("project_id")
            ha = float(project.get("ha") or 0)
            water_per_ha = project.get("water_per_ha")
            water = None
            if application_type == "spray" and water_per_ha not in [None, ""]:
                water = float(water_per_ha)

            cur.execute("""
            INSERT INTO agr.SprayProjects
            (SprayPSprayId, SprayPProjectId, SprayPHa, SprayPWaterPerHa, 
            SprayPPlantDate, SprayPAgriculturist, SprayPProjectManager, SprayPCropId, SprayPVarietyId, SprayPBlockNo)
            SELECT ?, ?, ?, ?, 
                ProjAttrPlantDate, ProjAttrAgriculturist, ProjAttrProjectManager, ProjAttrCropId, ProjAttrVarietyId, ProjAttrBlockNo
            FROM agr.ProjectAttributes
            WHERE ProjAttrProjectId = ?
            """, spray_header_id, project_id, ha, water, project_id)

        # insert spray lines
        if lines:
            for line in lines:
                stk_id = line.get("stock_id")
                qty = line.get("qty")
                qty_type = line.get("qty_type")
                if not stk_id or qty in [None, ""]:
                    continue
                qty = float(qty)
                qty_per_100l = qty if qty_type == "per100l" else None
                qty_per_ha = qty if qty_type == "perha" else None
                print(line.get("uom_id"))

                cur.execute("""
                    INSERT INTO agr.SprayLines
                    (SprayLineHeaderId, SprayLineStkId, SprayLineQtyPer100L, SprayLineQtyPerHa, SprayLineUoMId)
                    OUTPUT INSERTED.IdSprayLine
                    VALUES (?, ?, ?, ?, ?)
                """, spray_header_id, stk_id, qty_per_100l, qty_per_ha, line.get("uom_id"))

        conn.commit()

        if application_type == "spray":
            recalculate_and_store_mix(spray_header_id, method_id)
        else:
            recalculate_and_store_mix(spray_header_id, method_id, application_type=application_type)

        conn.close()
        return jsonify({"success": True, "message": "Spray recommendation saved successfully!", "id": spray_header_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error saving spray recommendation: {str(e)}"}), 500


@agri_bp.route("/spray-recommendation/preview", methods=["POST"])
@login_required
def spray_recommendation_preview():
    data = request.get_json(silent=True) or {}
    application_type = data.get("application_type")
    method_id = data.get("method_id")
    projects = data.get("projects") or []
    lines = data.get("lines") or []

    if application_type == "direct":
        return {"application_type": "direct", "total_ha": 0, "total_water": 0, "number_of_mixes": 0, "mixes": []}

    if application_type != "spray" or not method_id or not projects or not lines:
        return {"mixes": []}

    total_ha = 0.0
    total_water = 0.0
    for proj in projects:
        ha = float(proj.get("ha") or 0)
        water = float(proj.get("water_per_ha") or 0)
        total_ha += ha
        total_water += ha * water

    calc_lines = []
    for line in lines:
        if line.get("qty_type") != "per100l":
            continue
        calc_lines.append({
            "stock_id": line.get("stock_id"),
            "product_code": line.get("product_code", ""),
            "stock_description": line.get("stock_description", ""),
            "uom": line.get("uom", ""),
            "qty_per_100l": float(line.get("qty") or 0)
        })

    result = calculate_spray_mixes(
        method_id=method_id,
        total_ha=total_ha,
        total_water=total_water,
        lines=calc_lines,
        application_type=application_type
    )
    result["method_name"] = data.get("method_name", "")
    return result

def recalculate_and_store_mix(spray_header_id, method_id=None, application_type='spray'):
    conn = create_db_connection()
    cur = conn.cursor()

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

    if application_type != 'spray':
        conn.commit()
        conn.close()
        return

    cur.execute("""
        SELECT SUM(SprayPHa), SUM(SprayPHa * SprayPWaterPerHa)
        FROM agr.SprayProjects
        WHERE SprayPSprayId = ?
    """, spray_header_id)
    row = cur.fetchone()
    total_ha = float(row[0] or 0)
    total_water = float(row[1] or 0)

    cur.execute("""
        SELECT SprayLineStkId, SprayLineQtyPer100L, SprayLineUoMId
        FROM agr.SprayLines
        WHERE SprayLineHeaderId = ?
    """, spray_header_id)
    lines = cur.fetchall()
    calc_lines = []
    for line in lines:
        sku = line[0]
        qty_per_100l = line[1]
        uom_id = line[2]
        if qty_per_100l is None:
            continue
        calc_lines.append({
            "stock_id": sku,
            "qty_per_100l": float(qty_per_100l),
            "uom_id": uom_id
        })

    result = calculate_spray_mixes(
        method_id=method_id,
        total_ha=total_ha,
        total_water=total_water,
        lines=calc_lines,
        application_type='spray'
    )

    for mix in result.get("mixes", []):
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
                (SprayMixLineMixId, SprayMixLineStockId, SprayMixLineQty, SprayMixLineUoMId)
                VALUES (?, ?, ?, ?)
            """, mix_id, product["stock_id"], product["qty"], product.get("uom_id"))

    conn.commit()
    conn.close()


def calculate_spray_mixes(method_id, lines, total_ha: float = 0.0, total_water: float | None = None, application_type='spray'):
    if application_type != 'spray':
        return {"total_ha": round(total_ha, 1), "total_water": 0, "number_of_mixes": 0, "mixes": []}

    total_ha = float(total_ha or 0)
    total_water = float(total_water if total_water is not None else 0)

    if total_ha <= 0 or total_water <= 0:
        return {"total_ha": round(total_ha, 1), "total_water": round(total_water, 1), "number_of_mixes": 0, "mixes": []}

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT SprayMethodTankSize
        FROM agr.SprayMethod
        WHERE IdSprayMethod = ?
    """, method_id)
    row = cur.fetchone()
    conn.close()

    if not row or row[0] is None:
        return {"total_ha": round(total_ha, 1), "total_water": round(total_water, 1), "number_of_mixes": 0, "mixes": []}

    tank_size = float(row[0])
    if tank_size <= 0:
        return {"total_ha": round(total_ha, 1), "total_water": round(total_water, 1), "number_of_mixes": 0, "mixes": []}

    mixes = math.ceil(total_water / tank_size)
    avg_water_per_ha = total_water / total_ha
    if avg_water_per_ha <= 0:
        return {"total_ha": round(total_ha, 1), "total_water": round(total_water, 1), "number_of_mixes": 0, "mixes": []}

    ha_per_full_tank = tank_size / avg_water_per_ha
    remaining_ha = total_ha
    result_mixes = []

    for mix_no in range(1, mixes + 1):
        mix_ha = ha_per_full_tank if remaining_ha >= ha_per_full_tank else remaining_ha
        mix_water = mix_ha * avg_water_per_ha

        mix_products = []
        for line in lines:
            qty = round((mix_water / 100.0) * float(line.get("qty_per_100l", 0)), 1)
            mix_products.append({
                "stock_id": line.get("stock_id"),
            "product_code": line.get("product_code", ""),
                "uom_id": line.get("uom_id"),
                "qty": qty
            })
        result_mixes.append({
            "mix_no": mix_no,
            "ha": round(mix_ha, 1),
            "water": round(mix_water, 1),
            "products": mix_products
        })
        remaining_ha -= mix_ha

    return {"total_ha": round(total_ha, 1), "total_water": round(total_water, 1), "number_of_mixes": mixes, "mixes": result_mixes}


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
            sh.IdSprayH,
            STRING_AGG(p.ProjectCode, ', ') AS project_codes,
            ISNULL(SUM(sp.SprayPHa),0) AS total_ha,
            sh.SprayHDate,
            sh.SprayHStatus,
            sh.SprayHApplicationType,
            m.SprayMethodName
        FROM agr.SprayHeader sh
        LEFT JOIN agr.SprayProjects sp ON sp.SprayPSprayId = sh.IdSprayH
        LEFT JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        LEFT JOIN agr.SprayMethod m ON m.IdSprayMethod = sh.SprayHMethodId
        GROUP BY sh.IdSprayH, sh.SprayHDate, sh.SprayHStatus, sh.SprayHApplicationType, m.SprayMethodName
        ORDER BY sh.SprayHDate DESC
    """
    cur.execute(query)
    rows = cur.fetchall()

    recommendations = [
        {
            "id": row[0],
            "projects": row[1] or "",
            "ha": float(row[2]),
            "spray_date": str(row[3]),
            "status": row[4],
            "application_type": row[5] or 'spray',
            "method_name": row[6] or ''
        }
        for row in rows
    ]

    conn.close()
    return jsonify(recommendations)

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
