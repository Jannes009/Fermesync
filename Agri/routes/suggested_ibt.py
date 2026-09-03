from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp


@agri_bp.route('/ibt/popup', methods=['GET'])
@login_required
def ibt_popup():
    return render_template('suggested_ibt_section.html')


@agri_bp.route('/ibt/weeks', methods=['GET'])
@login_required
def ibt_weeks():
    """Generate ISO week strings for dropdown (current and future weeks)"""
    from datetime import datetime, timedelta
    weeks = []
    today = datetime.now()
    for i in range(6):  # current week + 5 future weeks
        dt = today + timedelta(weeks=i)
        date = datetime(dt.year, dt.month, dt.day)
        day_num = date.weekday() or 7
        date = date - timedelta(days=day_num - 1)
        year_start = datetime(date.year, 1, 1)
        week_no = ((date - year_start).days // 7) + 1
        week_str = f"{date.year}-{str(week_no).zfill(2)}"
        weeks.append(week_str)
    return jsonify({'success': True, 'weeks': weeks})


@agri_bp.route('/ibt/suggested', methods=['GET'])
@login_required
def ibt_suggested():
    """
    Fetch suggested IBT data grouped by warehouse.
    Returns items that should be transferred to different warehouses.
    """
    legacy_week = request.args.get('week')
    from_week = request.args.get('from_week') or None
    to_week = request.args.get('to_week') or legacy_week

    if not from_week and not to_week and not legacy_week:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    if from_week and to_week and from_week > to_week:
        from_week, to_week = to_week, from_week

    if not from_week and legacy_week and not to_week:
        to_week = legacy_week

    if not from_week and not to_week:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    clauses = []
    params = []
    if from_week:
        clauses.append('sug.SprayHWeek >= ?')
        params.append(from_week)
    if to_week:
        clauses.append('sug.SprayHWeek <= ?')
        params.append(to_week)

    where_clause = ' WHERE ' + ' AND '.join(clauses) if clauses else ''

    conn = create_db_connection()
    cur = conn.cursor()
    sql = f"""
        SELECT
            sug.FromWhseId,
            sug.ToWhseId,
            sug.SprayLineStkId,
            SUM(sug.PurchaseUnitsNeeded) PurchaseUnitsNeeded,
            sug.PurchaseUnitOnHand,
            ISNULL(TOINV.QtyOnHand / NULLIF(CONV.InverseConversionFactor, 0), 0) AS ToPurchaseUnitOnHand,
            SUM(sug.PurchaseUnitSuggestedIBT) PurchaseUnitSuggestedIBT,
            S.StockDescription,
            FROMW.WhseDescription AS FromWhseDescription,
            TOW.WhseDescription AS ToWhseDescription,
            sug.PurchasingUnitCode
        FROM [agr].[_uvSuggestedIBT] sug
        JOIN cmn._uvStockItems S
            ON S.StockLink = sug.SprayLineStkId
        JOIN cmn._uvWarehouses FROMW
            ON FROMW.WhseLink = sug.FromWhseId
        JOIN cmn._uvWarehouses TOW
            ON TOW.WhseLink = sug.ToWhseId
        LEFT JOIN stk._uvInventoryQty TOINV
            ON TOINV.WhseLink = sug.ToWhseId
            AND TOINV.StockLink = sug.SprayLineStkId
        LEFT JOIN agr._uvChemStockUnitConversion CONV
            ON CONV.ChemStockLink = sug.SprayLineStkId
       {where_clause}
    GROUP BY sug.FromWhseId, sug.ToWhseId, sug.SprayLineStkId, sug.PurchaseUnitOnHand,
    TOINV.QtyOnHand, CONV.InverseConversionFactor,
       S.StockDescription, FROMW.WhseDescription, TOW.WhseDescription, sug.PurchasingUnitCode
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    # Group by warehouse
    grouped = {}
    for r in rows:
        whse_id = int(r.ToWhseId)
        if whse_id not in grouped:
            grouped[whse_id] = {
                'whse_id': whse_id,
                'whse_description': r.ToWhseDescription,
                'items': []
            }
        grouped[whse_id]['items'].append({
            'stock_link': int(r.SprayLineStkId),
            'stock_description': r.StockDescription,
            'units_needed': float(r.PurchaseUnitsNeeded),
            'units_on_hand': float(r.PurchaseUnitOnHand),
            'to_units_on_hand': float(r.ToPurchaseUnitOnHand),
            'units_suggested': float(r.PurchaseUnitSuggestedIBT),
            'from_whse': int(r.FromWhseId) if hasattr(r, 'FromWhseId') else (int(r.FromWhseId) if 'FromWhseId' in r.__dict__ else None),
            'from_whse_description': r.FromWhseDescription if hasattr(r, 'FromWhseDescription') else (r.FromWhseDescription if 'FromWhseDescription' in r.__dict__ else ''),
            'to_whse': int(r.ToWhseId) if hasattr(r, 'ToWhseId') else (int(r.ToWhseId) if 'ToWhseId' in r.__dict__ else None),
            'uom': r.PurchasingUnitCode
        })

    return jsonify({
        'success': True,
        'from_week': from_week,
        'to_week': to_week,
        'week': to_week or from_week,
        'warehouses': list(grouped.values())
    })


@agri_bp.route('/ibt/suggested/detail/<int:stock_id>/warehouse/<int:whse_id>', methods=['GET'])
@login_required
def ibt_suggested_detail(stock_id, whse_id):
    legacy_week = request.args.get('week')
    from_week = request.args.get('from_week') or None
    to_week = request.args.get('to_week') or legacy_week

    if not from_week and not to_week:
        return jsonify({'success': False, 'message': 'week or range required'}), 400
    if from_week and to_week and from_week > to_week:
        from_week, to_week = to_week, from_week

    predicates = ['HEA.SprayHWhseId = ?', 'LIN.SprayLineStkId = ?']
    params = [whse_id, stock_id]
    if from_week:
        predicates.append('HEA.SprayHWeek >= ?')
        params.append(from_week)
    if to_week:
        predicates.append('HEA.SprayHWeek <= ?')
        params.append(to_week)

    conn = create_db_connection()
    cur = conn.cursor()
    sql = f"""
        SELECT
            HEA.IdSprayH AS SprayId,
            HEA.SprayHNo,
            HEA.SprayHDescription,
            SUM(LIN.SprayLineTotalQty) AS RecommendedQty,
            UOM.cUnitCode AS UnitCode
        FROM agr.SprayHeader HEA
        JOIN agr.SprayLines LIN ON LIN.SprayLineHeaderId = HEA.IdSprayH
        LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
        WHERE {' AND '.join(predicates)}
        GROUP BY HEA.IdSprayH, HEA.SprayHNo, HEA.SprayHDescription, UOM.cUnitCode
        ORDER BY HEA.SprayHNo
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    return jsonify({
        'success': True,
        'from_week': from_week,
        'to_week': to_week,
        'stock_id': stock_id,
        'whse_id': whse_id,
        'sprays': [{
            'spray_id': r.SprayId,
            'spray_h_no': r.SprayHNo,
            'spray_h_description': r.SprayHDescription,
            'recommended_qty': float(r.RecommendedQty or 0),
            'uom': r.UnitCode or ''
        } for r in rows]
    })


@agri_bp.route('/ibt/transfer', methods=['POST'])
@login_required
def ibt_transfer():
    payload = request.get_json() or {}
    from_whse = payload.get('from_whse')
    to_whse = payload.get('to_whse')
    lines = payload.get('lines') or []

    if not from_whse or not to_whse:
        return jsonify({'success': False, 'message': 'from_whse and to_whse are required'}), 400
    if not isinstance(lines, list) or not lines:
        return jsonify({'success': False, 'message': 'lines array required'}), 400

    # NOTE: This route currently acknowledges the transfer request and returns success.
    # Integrate with Evolution SDK or internal transfer mechanisms as needed.
    return jsonify({'success': True, 'count': len(lines)})
