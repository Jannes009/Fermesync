from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp


@agri_bp.route('/suggested-order/popup', methods=['GET'])
@login_required
def suggested_order_popup():
    if 'SPRAY_REC_VIEW' not in current_user.permissions:
        abort(403)
    return render_template('suggested_order_section.html')


@agri_bp.route('/suggested-order/data', methods=['GET'])
@login_required
def suggested_order_data():
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
        clauses.append('MAIN.SprayHWeek >= ?')
        params.append(from_week)
    if to_week:
        clauses.append('MAIN.SprayHWeek <= ?')
        params.append(to_week)

    where_clause = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    print(where_clause, params)

    conn = create_db_connection()
    cur = conn.cursor()

    # Use main reordering view for aggregated main-warehouse quantities and purchase-unit values
    sql = f"""
        SELECT
            MAIN.StockLink,
            ISNULL(S.ChemStockCode, '') AS StockCode,
            ISNULL(S.ChemStockName, '') AS StockDescription,
            SUM(ISNULL(MAIN.QtyNeeded, 0)) AS TotalRequiredStocking,
            ISNULL(MAIN.QtyOnHand, 0) AS MainWhQty,
            ISNULL(MAIN.QtyOnPO, 0) AS MainWhQtyOnPO,
            ISNULL(MAIN.QtyAvailable, 0) AS QtyAvailable,
            ISNULL(MAIN.StockingUnitCode, '') AS StockingUnitCode,
            ISNULL(MAIN.PurchasingUnitId, '') AS PurchasingUnitId,
            ISNULL(MAIN.PurchasingUnitCode, '') AS PurchasingUnitCode,
            ISNULL(MAIN.PurchaseUnitOnHand, 0) AS PurchaseUnitOnHand,
            ISNULL(MAIN.PurchaseUnitOnPO, 0) AS PurchaseUnitOnPO,
            ISNULL(MAIN.PurchaseUnitAvailable, 0) AS PurchaseUnitAvailable,
            SUM(ISNULL(MAIN.PurchaseUnitsNeeded, 0)) AS PurchaseUnitsNeeded,
            SUM(ISNULL(MAIN.PurchaseUnitsToOrder, 0)) AS PurchaseUnitsToOrder,
            CASE WHEN EXISTS (
                SELECT 1
                FROM stk._uvStockLinks SL
                WHERE SL.iStockID = MAIN.StockLink
            ) THEN 1 ELSE 0 END AS HasStockLink
        FROM agr._uvMainWarehouseReordering MAIN

        LEFT JOIN agr.ChemStock S
            ON S.ChemStockLink = MAIN.StockLink

        {where_clause}
        GROUP BY MAIN.StockLink, S.ChemStockCode, S.ChemStockName, MAIN.QtyOnHand
        , MAIN.QtyOnPO, MAIN.QtyAvailable, MAIN.StockingUnitCode, MAIN.PurchasingUnitId, 
        MAIN.PurchasingUnitCode, MAIN.PurchaseUnitOnHand, MAIN.PurchaseUnitOnPO, MAIN.PurchaseUnitAvailable
        ORDER BY StockDescription
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            'stock_link': r.StockLink,
            'stock_code': r.StockCode,
            'stock_description': r.StockDescription,
            'purchase_unit_id': int(r.PurchasingUnitId) if hasattr(r, 'PurchasingUnitId') and r.PurchasingUnitId is not None else None,
            'total_required_stocking': float(r.TotalRequiredStocking),
            'main_wh_qty': float(r.MainWhQty),
            'on_po_qty': float(r.MainWhQtyOnPO),
            'qty_available': float(r.QtyAvailable),
            'stocking_uom': r.StockingUnitCode,
            'purchasing_uom': r.PurchasingUnitCode,
            'purchase_unit_on_hand': float(r.PurchaseUnitOnHand),
            'purchase_unit_on_po': float(r.PurchaseUnitOnPO),
            'purchase_unit_available': float(r.PurchaseUnitAvailable),
            'purchase_units_needed': float(r.PurchaseUnitsNeeded),
            'purchase_units_to_order': float(r.PurchaseUnitsToOrder),
            'has_stock_link': bool(r.HasStockLink)
        })

    return jsonify({'success': True, 'from_week': from_week, 'to_week': to_week, 'week': to_week or from_week, 'data': results})


@agri_bp.route('/suggested-order/detail/<int:stock_id>', methods=['GET'])
@login_required
def suggested_order_detail(stock_id):
    legacy_week = request.args.get('week')
    from_week = request.args.get('from_week') or None
    to_week = request.args.get('to_week') or legacy_week

    if not from_week and not to_week and not legacy_week:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    if from_week and to_week and from_week > to_week:
        from_week, to_week = to_week, from_week

    clauses = []
    params = []
    if from_week:
        clauses.append('P.SprayHWeek >= ?')
        params.append(from_week)
    if to_week:
        clauses.append('P.SprayHWeek <= ?')
        params.append(to_week)

    if not clauses:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    where_clause = ' WHERE ' + ' AND '.join(clauses)

    conn = create_db_connection()
    cur = conn.cursor()
    sql = f"""
    WITH LatestWeek AS
    (
        SELECT
            ISNULL(Inv.StockLink, P.SprayLineStkId) AS StockLink,
            ISNULL(Inv.StockDescription, '') AS StockDescription,
            P.SprayHWhseId AS WhseId,
            ISNULL(Inv.WhseName, '') AS WhseName,
            ISNULL(Inv.QtyOnHand, 0) AS QtyOnHand,
            ISNULL(Inv.QtyOnPO, 0) AS QtyOnPO,
            ISNULL(P.StockingUnitCode, '') AS StockingUnitCode,
            ISNULL(P.PurchaseUnitsNeeded, 0) AS PurchaseUnitsNeeded,
            ISNULL(P.PurchasingUnitCode, '') AS PurchasingUnitCode,
            P.SprayHWeek,
			ISNULL(Inv.QtyOnIBT / NULLIF(CONV.InverseConversionFactor, 0), 0) AS PurchaseQtyOnIBT,
            ROW_NUMBER() OVER (
                PARTITION BY P.SprayHWhseId
                ORDER BY P.SprayHWeek DESC
            ) AS rn
        FROM agr._uvStockProjectionUnitsNeededPerWH P
		JOIN agr._uvChemStockUnitConversion  CONV ON CONV.ChemStockLink = P.SprayLineStkId
        LEFT JOIN stk._uvInventoryQty Inv
            ON Inv.WhseLink = P.SprayHWhseId
            AND Inv.StockLink = P.SprayLineStkId
        {where_clause}
        AND P.SprayLineStkId = ?
    )
    SELECT
        StockLink,
        StockDescription,
        WhseId,
        WhseName,
        QtyOnHand,
        QtyOnPO,
        StockingUnitCode,
        PurchaseUnitsNeeded,
        PurchasingUnitCode,
        SprayHWeek,
		PurchaseQtyOnIBT
    FROM LatestWeek
    WHERE rn = 1
    ORDER BY WhseName;
        """

    params.append(stock_id)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    results = [
        {
            'whse_id': r.WhseId,
            'stock_link': r.StockLink,
            'stock_description': r.StockDescription,
            'whse_name': r.WhseName,
            'qty_on_hand': float(r.QtyOnHand),
            'qty_on_po': float(r.QtyOnPO),
            'stocking_uom': r.StockingUnitCode,
            'purchase_units_needed': float(r.PurchaseUnitsNeeded),
            'purchasing_unit_code': r.PurchasingUnitCode,
            'spray_h_week': r.SprayHWeek,
            'PurchaseQtyOnIBT': float(r.PurchaseQtyOnIBT or 0)
        }
        for r in rows
    ]
    return jsonify({'success': True, 'from_week': from_week, 'to_week': to_week, 'week': to_week or from_week, 'stock_id': stock_id, 'warehouses': results})


@agri_bp.route('/suggested-order/detail/<int:stock_id>/warehouse/<int:whse_id>', methods=['GET'])
@login_required
def suggested_order_warehouse_detail(stock_id, whse_id):
    legacy_week = request.args.get('week')
    from_week = request.args.get('from_week') or None
    to_week = request.args.get('to_week') or legacy_week

    if not from_week and not to_week and not legacy_week:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    if from_week and to_week and from_week > to_week:
        from_week, to_week = to_week, from_week

    clauses = []
    params = []
    if from_week:
        clauses.append('HEA.SprayHWeek >= ?')
        params.append(from_week)
    if to_week:
        clauses.append('HEA.SprayHWeek <= ?')
        params.append(to_week)

    if not clauses:
        return jsonify({'success': False, 'message': 'week or range required'}), 400

    where_clause = ' AND '.join(clauses)

    conn = create_db_connection()
    cur = conn.cursor()

    sql = f"""
    Select 
	Lin.SprayLineHeaderId,
	HEA.SprayHNo,
	HEA.SprayHDescription,
	StockLink
    ,StockDescription   
    ,Sum(LIN.SprayLineTotalQty) QtyRecommended
    ,ProjectQty Finalised,
    cUnitCode
    --Select *
    from [agr].[SprayHeader] HEA
    JOIN [agr].[SprayLines] LIN on LIN.SprayLineHeaderId = HEA.IdSprayH
    LEFT JOIN (
        Select 
        IssLinProjSprayId, IssLineStockLink--, IssLineQtyFinalised,IssLinProjWeight
        ,SUM(IssLineQtyFinalised*IssLinProjWeight) ProjectQty
        from  stk.IssueLineProjects WT 
        JOIN stk.IssueLines ISSLIN on ISSLIN.IdIssLine = WT.IssLinProjLineId
        GROUP BY IssLinProjSprayId, IssLineStockLink
	)ISSQTY on ISSQTY.IssLinProjSprayId = HEA.IdSprayH and ISSQTY.IssLineStockLink = LIN.SprayLineStkId
    JOIN cmn._uvStockItems EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
    LEFT JOIN agr.ChemStock STK ON STK.ChemStockLink = LIN.SprayLineStkId
    LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
    WHERE {where_clause} AND LIN.SprayLineStkId = ? AND HEA.SprayHWhseId = ?
    GROUP BY StockLink ,StockDescription
    ,LIN.SprayLineFunction ,Lin.SprayLineWitholdingPeriod
    ,IssLineStockLink ,cUnitCode, ProjectQty, 	Lin.SprayLineHeaderId,
	HEA.SprayHNo,
	HEA.SprayHDescription
    """

    params.extend([stock_id, whse_id])
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    results = [
        {
            'spray_id': r.SprayLineHeaderId,
            'spray_h_no': r.SprayHNo,
            'spray_h_description': r.SprayHDescription,
            'recommended_qty': float(r.QtyRecommended),
            'stocking_uom': r.cUnitCode,
            'finalised_qty': float(r.Finalised or 0)
        }
        for r in rows
    ]
    return jsonify({'success': True, 'from_week': from_week, 'to_week': to_week, 'week': to_week or from_week, 'stock_id': stock_id, 'whse_id': whse_id, 'sprays': results})


@agri_bp.route('/suggested-order/stock-suppliers/<int:stock_id>', methods=['GET'])
@login_required
def suggested_order_stock_suppliers(stock_id):
    """Return suppliers linked to a specific stock item including last invoice price and default flag."""
    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
    SELECT DISTINCT
        L.iDCLink AS DCLink,
        ISNULL(S.Name, '') AS Name,
        ISNULL(L.bDefaultSupplier, 0) AS DefaultSupplier
    FROM stk._uvStockLinks L
    LEFT JOIN cmn._uvSuppliers S ON S.DCLink = L.iDCLink
    WHERE L.iStockID = ?
    """
    cur.execute(sql, (stock_id,))
    rows = cur.fetchall()
    conn.close()

    suppliers = [{
        'dc_link': int(r.DCLink),
        'name': r.Name, 
        'default_supplier': bool(r.DefaultSupplier), 
        } for r in rows
        ]
    return jsonify({'success': True, 'suppliers': suppliers})


@agri_bp.route('/suggested-order/order-warehouses', methods=['GET', 'POST'])
@login_required
def suggested_order_warehouses():
    payload = request.get_json(silent=True) or {}
    if request.method == 'GET' and not payload:
        stock_ids = request.args.getlist('stock_ids')
    else:
        stock_ids = payload.get('stock_ids') or []
    print(payload)
    if not isinstance(stock_ids, list) or not stock_ids:
        return jsonify({'success': False, 'message': 'stock_ids array is required'}), 400

    ids = [int(i) for i in stock_ids if isinstance(i, (int, str)) and str(i).strip() != '']
    if not ids:
        return jsonify({'success': False, 'message': 'stock_ids must contain at least one value'}), 400

    placeholders = ','.join(['?'] * len(ids))
    sql = f"""
    SELECT DISTINCT
        WhseID,
        WhseDescription
    FROM cmn._uvStockWarehouse
    WHERE bAllowToBuyInto = 1
      AND StockID IN ({placeholders})
    ORDER BY WhseDescription;
    """

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute(sql, ids)
    rows = cur.fetchall()
    conn.close()

    warehouses = [{
        'whse_id': int(r.WhseID),
        'whse_description': r.WhseDescription
    } for r in rows]
    print(warehouses)
    return jsonify({'success': True, 'warehouses': warehouses})

