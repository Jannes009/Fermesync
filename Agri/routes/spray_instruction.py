"""
Spray instruction backend with corrected mix calculation, display payload, and persistence.

Replace the corresponding helpers/routes in your agri blueprint with this logic.
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
import math


def _normalize_dose_basis(value):
    if value is None:
        return 'PER_HA'
    normalized = str(value).strip().upper().replace('-', '_').replace(' ', '_')
    compact = normalized.replace('_', '')
    if compact in ('PER100L', 'PER100', '100L'):
        return 'PER_100L'
    if compact in ('PERHADIRECT', 'PERHAD', 'DIRECTPERHA', 'HADIRECT'):
        return 'PER_HA_DIRECT'
    if compact in ('PERHA', 'HA', 'PERHAMIX'):
        return 'PER_HA'
    if normalized in ('PER_100L', 'PER_HA', 'PER_HA_DIRECT'):
        return normalized
    return 'PER_HA'


def _has_mixing(dose_basis):
    return _normalize_dose_basis(dose_basis) in ('PER_100L', 'PER_HA')


def _as_float(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _build_mix_plan(dose_basis, total_water, total_ha, water_per_ha, water_per_tank, max_mixes=50):
    """Split the job into tank loads. Mix Plan is derived, not free-form."""
    dose_basis = _normalize_dose_basis(dose_basis)
    total_water = _as_float(total_water) or 0.0
    total_ha = _as_float(total_ha) or 0.0
    water_per_ha = _as_float(water_per_ha)
    water_per_tank = _as_float(water_per_tank)

    if water_per_ha is None and total_ha > 0 and total_water > 0:
        water_per_ha = total_water / total_ha

    if dose_basis == 'PER_HA_DIRECT':
        return []

    mixes = []

    if dose_basis == 'PER_100L':
        if total_water <= 0:
            return [{'mix_number': 1, 'mix_water': 0.0, 'mix_ha': total_ha}]
        tank = water_per_tank if water_per_tank and water_per_tank > 0 else total_water
        remaining = total_water
        n = 1
        while remaining > 1e-9 and n <= max_mixes:
            mix_water = remaining if n == max_mixes else min(tank, remaining)
            mix_ha = (total_ha * mix_water / total_water) if total_water else 0.0
            mixes.append({
                'mix_number': n,
                'mix_water': mix_water,
                'mix_ha': mix_ha,
            })
            remaining = round(remaining - mix_water, 6)
            n += 1
        return mixes

    if dose_basis == 'PER_HA':
        if total_ha <= 0:
            return [{'mix_number': 1, 'mix_water': total_water, 'mix_ha': 0.0}]
        if water_per_tank and water_per_tank > 0 and water_per_ha and water_per_ha > 0:
            ha_per_tank = water_per_tank / water_per_ha
        elif water_per_tank and water_per_tank > 0 and total_water > 0:
            ha_per_tank = total_ha * (water_per_tank / total_water)
        else:
            ha_per_tank = total_ha

        remaining_ha = total_ha
        n = 1
        while remaining_ha > 1e-9 and n <= max_mixes:
            mix_ha = remaining_ha if n == max_mixes else min(ha_per_tank, remaining_ha)
            if water_per_ha and water_per_ha > 0:
                mix_water = water_per_ha * mix_ha
            elif total_ha > 0:
                mix_water = total_water * mix_ha / total_ha
            else:
                mix_water = 0.0
            mixes.append({
                'mix_number': n,
                'mix_water': mix_water,
                'mix_ha': mix_ha,
            })
            remaining_ha = round(remaining_ha - mix_ha, 6)
            n += 1
        return mixes

    return []


def _mix_line_qty(dose_basis, line, mix_water, mix_ha):
    dose_basis = _normalize_dose_basis(dose_basis)
    qty_per_100l = _as_float(line.get('qty_per_100l')) or 0.0
    qty_per_ha = _as_float(line.get('qty_per_ha')) or 0.0
    total_qty = _as_float(line.get('total_qty')) or 0.0
    if dose_basis == 'PER_100L':
        return (qty_per_100l / 100.0) * mix_water if mix_water else 0.0
    if dose_basis == 'PER_HA':
        return qty_per_ha * mix_ha if mix_ha else 0.0
    return total_qty


def _load_header_mix_inputs(cur, spray_id):
    cur.execute(
        """
        SELECT
            SprayLineDoseBasis,
            SprayHTotalWater,
            SprayHTotalHa,
            SprayHWaterPerHa,
            SprayHWaterPerTank
        FROM agr.SprayHeader
        WHERE IdSprayH = ?
        """,
        spray_id,
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        'dose_basis': _normalize_dose_basis(row.SprayLineDoseBasis),
        'total_water': _as_float(row.SprayHTotalWater),
        'total_ha': _as_float(row.SprayHTotalHa),
        'water_per_ha': _as_float(row.SprayHWaterPerHa),
        'water_per_tank': _as_float(row.SprayHWaterPerTank),
    }


def _load_spray_line_payload(cur, spray_id):
    cur.execute(
        """
        SELECT
            IdSprayLine,
            SprayLineStkId,
            SprayLineQtyPer100L,
            SprayLineQtyPerHa,
            SprayLineTotalQty,
            SprayLineUoMId
        FROM agr.SprayLines
        WHERE SprayLineHeaderId = ?
        """,
        spray_id,
    )
    lines = []
    for row in cur.fetchall():
        lines.append({
            'line_id': row.IdSprayLine,
            'stock_id': row.SprayLineStkId,
            'qty_per_100l': _as_float(row.SprayLineQtyPer100L),
            'qty_per_ha': _as_float(row.SprayLineQtyPerHa),
            'total_qty': _as_float(row.SprayLineTotalQty),
            'uom_id': row.SprayLineUoMId,
        })
    return lines


def _rebuild_spray_mixes(cur, spray_id, header=None, lines=None):
    """Always rebuild mix rows from current header + line rates + tank size."""
    cur.execute(
        """
        DELETE FROM agr.SprayMixLines
        WHERE SprayMixLineMixId IN (
            SELECT IdSprayMix FROM agr.SprayMix WHERE SprayMixHeaderId = ?
        )
        """,
        spray_id,
    )
    cur.execute("DELETE FROM agr.SprayMix WHERE SprayMixHeaderId = ?", spray_id)

    header = header or _load_header_mix_inputs(cur, spray_id)
    if not header:
        return

    dose_basis = _normalize_dose_basis(header.get('dose_basis'))
    if not _has_mixing(dose_basis):
        return

    lines = lines if lines is not None else _load_spray_line_payload(cur, spray_id)
    usable_lines = []
    for line in lines:
        stock_id = _as_int(line.get('stock_id'))
        if stock_id is None:
            continue
        usable_lines.append({
            'stock_id': stock_id,
            'qty_per_100l': _as_float(line.get('qty_per_100l')) or 0.0,
            'qty_per_ha': _as_float(line.get('qty_per_ha')) or 0.0,
            'total_qty': _as_float(line.get('total_qty')) or 0.0,
            'uom_id': _as_int(line.get('uom_id')),
        })
    if not usable_lines:
        return

    mix_plan = _build_mix_plan(
        dose_basis,
        header.get('total_water'),
        header.get('total_ha'),
        header.get('water_per_ha'),
        header.get('water_per_tank'),
    )

    for mix in mix_plan:
        cur.execute(
            """
            INSERT INTO agr.SprayMix (
                SprayMixHeaderId,
                SprayMixNumber,
                SprayMixWater,
                SprayMixHa
            ) 
            OUTPUT INSERTED.IdSprayMix
            VALUES (?, ?, ?, ?)
            """,
            spray_id,
            mix['mix_number'],
            mix['mix_water'],
            mix['mix_ha'],
        )
        mix_row = cur.fetchone()
        mix_id = mix_row[0] if mix_row else None
        if mix_id is None:
            continue

        for line in usable_lines:
            qty = _mix_line_qty(dose_basis, line, mix['mix_water'], mix['mix_ha'])
            cur.execute(
                """
                INSERT INTO agr.SprayMixLines (
                    SprayMixLineMixId,
                    SprayMixLineStockId,
                    SprayMixLineQty,
                    SprayMixLineUoMId
                ) VALUES (?, ?, ?, ?)
                """,
                mix_id,
                line['stock_id'],
                qty,
                line['uom_id'],
            )


def _recompute_line_quantities(dose_basis, line, total_water, total_ha):
    dose_basis = _normalize_dose_basis(dose_basis)
    qty_per_100l = _as_float(line.get('qty_per_100l'))
    qty_per_ha = _as_float(line.get('qty_per_ha'))
    total_qty = _as_float(line.get('total_qty'))
    total_water = _as_float(total_water)
    total_ha = _as_float(total_ha)

    if dose_basis == 'PER_100L':
        if total_water and total_water > 0:
            if qty_per_100l is None and total_qty is not None:
                qty_per_100l = (total_qty * 100.0) / total_water
            if qty_per_100l is not None:
                total_qty = (qty_per_100l / 100.0) * total_water
        qty_per_ha = None
    elif dose_basis == 'PER_HA_DIRECT':
        if total_ha and total_ha > 0:
            if qty_per_ha is None and total_qty is not None:
                qty_per_ha = total_qty / total_ha
            if qty_per_ha is not None:
                total_qty = qty_per_ha * total_ha
        qty_per_100l = None
    else:
        if total_ha and total_ha > 0:
            if qty_per_ha is None and total_qty is not None:
                qty_per_ha = total_qty / total_ha
            if qty_per_ha is not None:
                total_qty = qty_per_ha * total_ha
        qty_per_100l = None

    line['qty_per_100l'] = qty_per_100l
    line['qty_per_ha'] = qty_per_ha
    line['total_qty'] = total_qty
    return line


@agri_bp.route("/spray/<int:spray_id>")
@login_required
def spray_execution_page(spray_id):
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)
    return render_template("spray_instruction.html", spray_id=spray_id)


@agri_bp.route("/fetch_spray_instructions", methods=["GET"])
@login_required
def fetch_spray_instructions():
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT IdSprayH, SprayHDate
            FROM agr.SprayHeader
            ORDER BY SprayHDate DESC
        """)
        spray_headers = cur.fetchall()
        sprays_list = [
            {
                "id": header.IdSprayH,
                "name": f"Spray {header.IdSprayH} - {header.SprayHDate}"
            }
            for header in spray_headers
        ]
        return jsonify({"success": True, "sprays": sprays_list})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/spray_header", methods=["GET"])
@login_required
def get_spray_header(spray_id):
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
        SELECT
            HEA.SprayHNo,
            HEA.SprayHDescription,
            HEA.SprayHDate,
            HEA.SprayHWeek,
            HEA.SprayHWhseId,
            WHSE.Code,
            WHSE.Name,
            HEA.SprayHWeather,
            HEA.SprayLineDoseBasis,
            HEA.SprayHMethodId,
            HEA.SprayHStartDateTime,
            HEA.SprayHEndDateTime,
            HEA.SprayHExecutionId,
            EXE.SprExecFinalised,
            HEA.SprayHWaterPerTank,
            HEA.SprayHWaterPerHa,
            HEA.SprayHTotalWater,
            HEA.SprayHTotalHa,
            HEA.SprayHMix,
            HEA.SprayHStatus,
            HEA.SprayHScouting,
            HEA.SprayHFinalised,
            CRP.CropThemeColor,
            SM.SprayMethodName,
            CASE
                WHEN SUM(ISNULL(ISS.QtyOut, 0)) OVER (PARTITION BY HEA.IdSprayH) > 0
                THEN 1
                ELSE 0
            END AS IssuesExist
        FROM agr.SprayHeader HEA
        JOIN cmn._uvWhseMst WHSE on WHSE.WhseLink = HEA.SprayHWhseId
        LEFT JOIN agr.Crop CRP on CRP.IdCrop = HEA.SprayHCropId
        LEFT JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
        LEFT JOIN stk._uvIssueQuantities ISS on ISS.IssSprayExecutionId = EXE.IdSprExec
        LEFT JOIN agr.SprayMethod SM on SM.IdSprayMethod = HEA.SprayHMethodId
        WHERE HEA.IdSprayH = ?
        """, spray_id)

        header = cur.fetchone()
        if not header:
            return jsonify({"success": False, "message": "Spray recommendation not found."}), 404

        cur.execute("""
            SELECT
                sp.SprayPProjectId,
                p.ProjectCode,
                ISNULL(sp.SprayPHa, 0) AS SprayPHa,
                ISNULL(sp.SprayPWaterPerHa, 0) AS SprayPWaterPerHa,
                ISNULL(sp.SprayPTotalWater, 0) AS SprayPTotalWater
            FROM agr.SprayProjects sp
            JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
            WHERE sp.SprayPSprayId = ?
        """, spray_id)
        proj_rows = cur.fetchall()
        project_list = [
            {
                "project_id": row.SprayPProjectId,
                "project_code": row.ProjectCode,
                "ha": float(row.SprayPHa or 0),
                "water_per_ha": float(row.SprayPWaterPerHa or 0),
                "total_water": float(row.SprayPTotalWater or 0)
            }
            for row in proj_rows
        ]

        total_ha = _as_float(header.SprayHTotalHa)
        total_water = _as_float(header.SprayHTotalWater)
        water_per_ha = _as_float(header.SprayHWaterPerHa)
        if water_per_ha is None and total_ha and total_ha > 0 and total_water and total_water > 0:
            water_per_ha = total_water / total_ha

        return jsonify({
            "success": True,
            "spray_date": str(header.SprayHDate),
            "spray_week": header.SprayHWeek,
            "projects": project_list,
            "total_ha": total_ha,
            "dose_basis": _normalize_dose_basis(header.SprayLineDoseBasis),
            "weather": header.SprayHWeather,
            "method_id": header.SprayHMethodId,
            "spray_no": header.SprayHNo,
            "spray_description": header.SprayHDescription,
            "method_name": header.SprayMethodName,
            "warehouse": {
                "id": header.SprayHWhseId,
                "code": header.Code,
                "name": header.Name
            },
            "water_per_tank": _as_float(header.SprayHWaterPerTank),
            "water_per_ha": water_per_ha,
            "total_water": total_water,
            "start_datetime": str(header.SprayHStartDateTime) if header.SprayHStartDateTime is not None else None,
            "end_datetime": str(header.SprayHEndDateTime) if header.SprayHEndDateTime is not None else None,
            "mix": bool(header.SprayHMix) if header.SprayHMix is not None else None,
            "execution_id": header.SprayHExecutionId if header.SprayHExecutionId is not None else None,
            "execution_finalised": bool(header.SprExecFinalised) if header.SprExecFinalised is not None else None,
            "crop_theme_color": header.CropThemeColor if header.CropThemeColor is not None else None,
            "status": header.SprayHStatus,
            "scouting": header.SprayHScouting if header.SprayHScouting is not None else None,
            "finalised": bool(header.SprayHFinalised) if header.SprayHFinalised is not None else None,
            "issues_exist": bool(header.IssuesExist) if header.IssuesExist is not None else None
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/spray_lines", methods=["GET"])
@login_required
def get_spray_lines(spray_id):
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT SprayLineDoseBasis FROM agr.SprayHeader WHERE IdSprayH = ?
        """, spray_id)
        row = cur.fetchone()
        dose_basis = _normalize_dose_basis(row.SprayLineDoseBasis if row else None)
        cur.execute("""
            SELECT LIN.IdSprayLine, LIN.SprayLineStkId, EVOSTK.StockDescription, ACT.ChemActIngredient,
                   LIN.SprayLineQtyPerHa, LIN.SprayLineQtyPer100L, SprayLineTotalQty, LIN.SprayLineUoMId, UOM.cUnitCode
            FROM [agr].SprayLines LIN
            JOIN [agr].SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
            JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
            JOIN agr.ChemStock STK on STK.ChemStockLink = LIN.SprayLineStkId
            LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
            WHERE LIN.SprayLineHeaderId = ?
        """, spray_id)
        lines = [
            {
                "line_id": row.IdSprayLine,
                "stock_id": row.SprayLineStkId,
                "stock_description": row.StockDescription,
                "active_ingredient": row.ChemActIngredient,
                "dose_basis": dose_basis,
                "qty_per_100l": float(row.SprayLineQtyPer100L) if row.SprayLineQtyPer100L is not None else None,
                "qty_per_ha": float(row.SprayLineQtyPerHa) if row.SprayLineQtyPerHa is not None else None,
                "total_qty": float(row.SprayLineTotalQty) if row.SprayLineTotalQty is not None else None,
                "uom_id": row.SprayLineUoMId,
                "uom": row.cUnitCode
            }
            for row in cur.fetchall()
        ]
        return jsonify({"success": True, "lines": lines})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/edit_spray_lines", methods=["POST"])
@login_required
def save_spray_lines(spray_id):
    if "SPRAY_REC_EDIT" not in current_user.permissions:
        abort(403)
    data = request.get_json(silent=True) or {}
    lines = data.get('lines')
    if not isinstance(lines, list):
        return jsonify({"success": False, "message": "Missing or invalid lines payload."}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
	Select
		CASE
			WHEN SUM(ISNULL(ISS.QtyOut, 0)) OVER (PARTITION BY HEA.IdSprayH) > 0
			THEN 1
			ELSE 0
		END AS IssuesExist
    FROM agr.SprayHeader HEA
	LEFT JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
	LEFT JOIN stk._uvIssueQuantities ISS on ISS.IssSprayExecutionId = EXE.IdSprExec
    WHERE HEA.IdSprayH = ?
    """, spray_id)
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Spray recommendation not found."}), 404

    if row.IssuesExist == 1:
        conn.close()
        return jsonify({"success": False, "message": "Cannot edit spray lines: this recommendation is linked to an execution."}), 400

    header = _load_header_mix_inputs(cur, spray_id)
    dose_basis = header['dose_basis'] if header else 'PER_HA'
    total_water = header['total_water'] if header else None
    total_ha = header['total_ha'] if header else None

    try:
        cur.execute("SELECT IdSprayLine FROM agr.SprayLines WHERE SprayLineHeaderId = ?", spray_id)
        existing_ids = {row.IdSprayLine for row in cur.fetchall()}
        incoming_ids = set()

        for line in lines:
            stock_id = _as_int(line.get('stock_id'))
            if stock_id is None:
                return jsonify({"success": False, "message": "Every spray line must have a product selected."}), 400

            uom_id = _as_int(line.get('uom_id'))
            if uom_id is None:
                cur.execute("""
                    SELECT TOP 1 QTY.StockingUnitId
                    FROM agr.SprayHeader HEA
                    JOIN stk._uvInventoryQty QTY ON QTY.WhseLink = HEA.SprayHWhseId
                    WHERE HEA.IdSprayH = ? AND QTY.StockLink = ?
                """, spray_id, stock_id)
                uom_row = cur.fetchone()
                uom_id = _as_int(uom_row[0]) if uom_row else None
                line['uom_id'] = uom_id

            if uom_id is None:
                return jsonify({"success": False, "message": "No unit of measure is configured for the selected product."}), 400

            line_id = _as_int(line.get('line_id'))
            if line_id is not None:
                incoming_ids.add(line_id)

        delete_ids = existing_ids - incoming_ids
        for line_id in delete_ids:
            cur.execute("DELETE FROM agr.SprayLines WHERE IdSprayLine = ? AND SprayLineHeaderId = ?", line_id, spray_id)

        saved_lines = []
        for line in lines:
            line = _recompute_line_quantities(dose_basis, line, total_water, total_ha)
            line_id = _as_int(line.get('line_id'))
            stock_id = _as_int(line.get('stock_id'))
            uom_id = _as_int(line.get('uom_id'))

            if line_id is not None:
                cur.execute(
                    """
                    UPDATE agr.SprayLines
                    SET SprayLineStkId = ?, SprayLineQtyPer100L = ?, SprayLineQtyPerHa = ?, SprayLineUoMId = ?, SprayLineTotalQty = ?
                    WHERE IdSprayLine = ? AND SprayLineHeaderId = ?
                    """,
                    stock_id, line['qty_per_100l'], line['qty_per_ha'], uom_id, line['total_qty'], line_id, spray_id
                )
            else:
                cur.execute(
                    """
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
                    spray_id, stock_id, line['qty_per_100l'], line['qty_per_ha'], uom_id, line['total_qty']
                )

            saved_lines.append({
                'stock_id': stock_id,
                'qty_per_100l': line['qty_per_100l'],
                'qty_per_ha': line['qty_per_ha'],
                'total_qty': line['total_qty'],
                'uom_id': uom_id,
            })

        _rebuild_spray_mixes(cur, spray_id, header=header, lines=saved_lines)
        conn.commit()
        return jsonify({"success": True})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/edit_spray_header", methods=["POST"])
@login_required
def save_spray_header(spray_id):
    if "SPRAY_REC_EDIT" not in current_user.permissions:
        abort(403)

    data = request.get_json(silent=True) or {}
    spray_description = data.get('spray_description')
    spray_date = data.get('spray_date')
    spray_week = data.get('spray_week')
    scouting = data.get('scouting')
    weather = data.get('weather')
    start_datetime = data.get('start_datetime')
    end_datetime = data.get('end_datetime')
    method_id = data.get('method_id')

    if spray_description is None:
        return jsonify({"success": False, "message": "Spray description is required."}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE agr.SprayHeader
            SET SprayHDescription = ?,
                SprayHDate = ?,
                SprayHWeek = ?,
                SprayHScouting = ?,
                SprayHWeather = ?,
                SprayHMethodId = ?,
                SprayHStartDateTime = ?,
                SprayHEndDateTime = ?
            WHERE IdSprayH = ?
            """,
            spray_description,
            spray_date,
            spray_week,
            scouting,
            weather,
            method_id,
            start_datetime,
            end_datetime,
            spray_id
        )
        conn.commit()
        return jsonify({"success": True, "message": "Header changes saved successfully."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/edit_spray_projects", methods=["POST"])
@login_required
def save_spray_projects(spray_id):
    if "SPRAY_REC_EDIT" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                CASE
                    WHEN SUM(ISNULL(ISS.QtyOut, 0)) OVER (PARTITION BY HEA.IdSprayH) > 0 THEN 1
                    ELSE 0
                END AS IssuesExist,
                HEA.SprayHFinalised
            FROM agr.SprayHeader HEA
            LEFT JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
            LEFT JOIN stk._uvIssueQuantities ISS on ISS.IssSprayExecutionId = EXE.IdSprExec
            WHERE HEA.IdSprayH = ?
            """,
            spray_id,
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "Spray recommendation not found."}), 404

        if row.IssuesExist == 1:
            conn.close()
            return jsonify({"success": False, "message": "Cannot edit projects: this recommendation has issues recorded."}), 400

        if row.SprayHFinalised == 1:
            conn.close()
            return jsonify({"success": False, "message": "Cannot edit projects: this recommendation is finalised."}), 400
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500

    data = request.get_json(silent=True) or {}
    dose_basis = _normalize_dose_basis(data.get('dose_basis'))
    mix_flag = 0 if dose_basis == 'PER_HA_DIRECT' else 1

    if dose_basis == 'PER_HA_DIRECT':
        water_per_tank = None
        water_per_ha = None
        total_water = None
    else:
        water_per_tank = _as_float(data.get('water_per_tank'))
        water_per_ha = _as_float(data.get('water_per_ha'))
        total_water = _as_float(data.get('total_water'))

    total_ha = _as_float(data.get('total_ha'))
    projects = data.get('projects') if isinstance(data.get('projects'), list) else []
    lines = data.get('lines') if isinstance(data.get('lines'), list) else []

    try:
        if water_per_ha is None and dose_basis != 'PER_HA_DIRECT' and total_ha and total_ha > 0 and total_water and total_water > 0:
            water_per_ha = total_water / total_ha

        cur.execute(
            """
            UPDATE agr.SprayHeader
            SET SprayLineDoseBasis = ?,
                SprayHWaterPerTank = ?,
                SprayHWaterPerHa = ?,
                SprayHTotalWater = ?,
                SprayHMix = ?
            WHERE IdSprayH = ?
            """,
            dose_basis,
            water_per_tank,
            water_per_ha,
            total_water,
            mix_flag,
            spray_id
        )

        for project in projects:
            project_id = project.get('project_id')
            if project_id is None:
                continue
            proj_water_per_ha = _as_float(project.get('water_per_ha'))
            proj_total_water = _as_float(project.get('total_water'))
            cur.execute(
                """
                UPDATE agr.SprayProjects
                SET SprayPWaterPerHa = ?, SprayPTotalWater = ?
                WHERE SprayPSprayId = ? AND SprayPProjectId = ?
                """,
                proj_water_per_ha,
                proj_total_water,
                spray_id,
                project_id
            )

        if lines:
            for line in lines:
                line_id = _as_int(line.get('line_id'))
                stock_id = _as_int(line.get('stock_id'))
                if stock_id is None or line_id is None:
                    continue
                line = _recompute_line_quantities(dose_basis, line, total_water, total_ha)
                cur.execute(
                    """
                    UPDATE agr.SprayLines
                    SET SprayLineStkId = ?,
                        SprayLineQtyPer100L = ?,
                        SprayLineQtyPerHa = ?,
                        SprayLineUoMId = ?,
                        SprayLineTotalQty = ?
                    WHERE IdSprayLine = ? AND SprayLineHeaderId = ?
                    """,
                    stock_id,
                    line['qty_per_100l'],
                    line['qty_per_ha'],
                    _as_int(line.get('uom_id')),
                    line['total_qty'],
                    line_id,
                    spray_id
                )

        header = {
            'dose_basis': dose_basis,
            'total_water': total_water,
            'total_ha': total_ha,
            'water_per_ha': water_per_ha,
            'water_per_tank': water_per_tank,
        }
        _rebuild_spray_mixes(cur, spray_id, header=header)
        conn.commit()
        return jsonify({"success": True, "message": "Project settings saved successfully."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/cancel", methods=["POST"])
@login_required
def cancel_spray(spray_id):
    if "SPRAY_REC_CREATE" not in current_user.permissions:
        abort(403)
    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT SprayHExecutionId FROM agr.SprayHeader WHERE IdSprayH = ?", spray_id)
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Spray recommendation not found."}), 404

        execution_id = row.SprayHExecutionId
        if execution_id is not None:
            return jsonify({"success": False, "message": "Cannot cancel a spray recommendation that is already linked to an execution."}), 400

        cur.execute(
            "UPDATE agr.SprayHeader SET SprayHStatus = ?, SprayHCancelled = 1 WHERE IdSprayH = ?",
            'CANCELLED', spray_id
        )
        conn.commit()
        return jsonify({"success": True, "message": "Spray recommendation cancelled."})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/spray_mix_lines", methods=["GET"])
@login_required
def get_spray_mix_lines(spray_id):
    if "SPRAY_REC_VIEW" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT LIN.IdSprayMixLine, LIN.SprayMixLineStockId, EVOSTK.StockDescription,
                    LIN.SprayMixLineQty, UOM.cUnitCode, SME.SprayMixNumber, SME.SprayMixWater, SME.SprayMixHa,
                    SM.SprayMethodName
            FROM [agr].SprayMixLines LIN
            JOIN [agr].SprayMix SME ON LIN.SprayMixLineMixId = SME.IdSprayMix
            JOIN agr.SprayHeader SH ON SH.IdSprayH = SME.SprayMixHeaderId
            LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = SH.SprayHMethodId
            JOIN [cmn].[_uvStockItems] EVOSTK ON EVOSTK.StockLink = LIN.SprayMixLineStockId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = LIN.SprayMixLineUoMId
            WHERE SME.SprayMixHeaderId = ?
            ORDER BY SME.SprayMixNumber, LIN.IdSprayMixLine
        """, spray_id)
        lines = [
            {
                "line_id": row.IdSprayMixLine,
                "stock_id": row.SprayMixLineStockId,
                "stock_description": row.StockDescription,
                "qty": float(row.SprayMixLineQty) if row.SprayMixLineQty is not None else 0.0,
                "uom": row.cUnitCode,
                "mix_number": row.SprayMixNumber,
                "water": float(row.SprayMixWater) if row.SprayMixWater is not None else 0.0,
                "mix_ha": float(row.SprayMixHa) if row.SprayMixHa is not None else 0.0,
                "method_name": row.SprayMethodName
            }
            for row in cur.fetchall()
        ]
        return jsonify({"success": True, "lines": lines})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@agri_bp.route("/spray/<int:spray_id>/methods", methods=["GET"])
@login_required
def get_spray_methods(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT
            sm.IdSprayMethod,
            sm.SprayMethodName
        FROM agr.SprayMethod sm
        JOIN agr.Farm f ON f.IdFarm = sm.SprayMethodFarmId
        JOIN agr.ProjectAttributes PA on PA.ProjAttrFarmId = sm.SprayMethodFarmId
        JOIN agr.SprayProjects SP on SP.SprayPProjectId = PA.ProjAttrProjectId
        Where SP.SprayPSprayId = ?
    """, (spray_id,))
    spray_methods = cur.fetchall()
    conn.close()
    methods_list = []
    for method in spray_methods:
        methods_list.append({
            "id": method.IdSprayMethod,
            "method_name": method.SprayMethodName,
        })
    return jsonify({"success": True, "methods": methods_list})


@agri_bp.route("/spray/<int:spray_id>/fetch_products", methods=["GET"])
@login_required
def fetch_products_for_spray_whse(spray_id):
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT QTY.StockLink, StockCode, StockDescription, QtyOnHand, ACT.ChemActIngredient, QTY.StockingUnitId, QTY.StockingUnitCode
    FROM [agr].SprayHeader HEA
    JOIN stk._uvInventoryQty QTY on QTY.WhseLink = HEA.SprayHWhseId
	JOIN agr.ChemStock STK on STK.ChemStockLink = QTY.StockLink
	JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
    WHERE HEA.IdSprayH = ?
    ORDER BY ACT.ChemActIngredient, StockDescription
    """, spray_id)
    products = [{
        "stock_link": row.StockLink,
        "stock_code": row.StockCode,
        "stock_description": row.StockDescription,
        "qty_on_hand": float(row.QtyOnHand),
        "active_ingredient": row.ChemActIngredient,
        "stocking_uom_id": row.StockingUnitId,
        "stocking_uom_code": row.StockingUnitCode
    } for row in cur.fetchall()]
    conn.close()
    return jsonify({"success": True, "products": products})
