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
    return jsonify({'status': 'ok', 'weeks': weeks})


@agri_bp.route('/ibt/suggested', methods=['GET'])
@login_required
def ibt_suggested():
    """
    Fetch suggested IBT data grouped by warehouse.
    Returns items that should be transferred to different warehouses.
    """
    week = request.args.get('week')
    if not week:
        return jsonify({'status': 'error', 'message': 'week parameter required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
    WITH LatestWeek AS
    (
        SELECT
            sug.FromWhseId,
            sug.ToWhseId,
            sug.SprayLineStkId,
            sug.SprayHWeek,
            sug.PurchaseUnitsNeeded,
            sug.PurchaseUnitOnHand,
            sug.PurchaseUnitSuggestedIBT,
            S.StockDescription,
            FROMW.WhseDescription AS FromWhseDescription,
            TOW.WhseDescription AS ToWhseDescription,
            sug.PurchasingUnitCode,
            ROW_NUMBER() OVER
            (
                PARTITION BY
                    sug.FromWhseId,
                    sug.ToWhseId,
                    sug.SprayLineStkId
                ORDER BY
                    sug.SprayHWeek DESC
            ) AS rn
        FROM [agr].[_uvSuggestedIBT] sug
        JOIN cmn._uvStockItems S
            ON S.StockLink = sug.SprayLineStkId
        JOIN cmn._uvWarehouses FROMW
            ON FROMW.WhseLink = sug.FromWhseId
        JOIN cmn._uvWarehouses TOW
            ON TOW.WhseLink = sug.ToWhseId
        WHERE sug.SprayHWeek <= ?
    )
    SELECT
        FromWhseId,
        ToWhseId,
        SprayLineStkId,
        SprayHWeek,
        PurchaseUnitsNeeded,
        PurchaseUnitOnHand,
        PurchaseUnitSuggestedIBT,
        StockDescription,
        FromWhseDescription,
        ToWhseDescription,
        PurchasingUnitCode
    FROM LatestWeek
    WHERE rn = 1
    ORDER BY
        ToWhseDescription,
        StockDescription;
    """
    cur.execute(sql, (week,))
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
            'units_suggested': float(r.PurchaseUnitSuggestedIBT),
            'from_whse': int(r.FromWhseId) if hasattr(r, 'FromWhseId') else (int(r.FromWhseId) if 'FromWhseId' in r.__dict__ else None),
            'from_whse_description': r.FromWhseDescription if hasattr(r, 'FromWhseDescription') else (r.FromWhseDescription if 'FromWhseDescription' in r.__dict__ else ''),
            'to_whse': int(r.ToWhseId) if hasattr(r, 'ToWhseId') else (int(r.ToWhseId) if 'ToWhseId' in r.__dict__ else None),
            'uom': r.PurchasingUnitCode
        })

    return jsonify({
        'status': 'ok',
        'week': week,
        'warehouses': list(grouped.values())
    })


@agri_bp.route('/ibt/transfer', methods=['POST'])
@login_required
def ibt_transfer():
    payload = request.get_json() or {}
    from_whse = payload.get('from_whse')
    to_whse = payload.get('to_whse')
    lines = payload.get('lines') or []

    if not from_whse or not to_whse:
        return jsonify({'status': 'error', 'message': 'from_whse and to_whse are required'}), 400
    if not isinstance(lines, list) or not lines:
        return jsonify({'status': 'error', 'message': 'lines array required'}), 400

    # NOTE: This route currently acknowledges the transfer request and returns success.
    # Integrate with Evolution SDK or internal transfer mechanisms as needed.
    return jsonify({'status': 'ok', 'count': len(lines)})
