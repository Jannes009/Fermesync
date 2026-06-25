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
    week = request.args.get('week')
    if not week:
        return jsonify({'status': 'error', 'message': 'week parameter required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    # Use main reordering view for aggregated main-warehouse quantities and purchase-unit values
    sql = """
    WITH LatestWeek AS
    (
        SELECT
            MAIN.StockLink,
            ISNULL(S.ChemStockCode, '') AS StockCode,
            ISNULL(S.ChemStockName, '') AS StockDescription,
            ISNULL(MAIN.QtyNeeded, 0) AS TotalRequiredStocking,
            ISNULL(MAIN.QtyOnHand, 0) AS MainWhQty,
            ISNULL(MAIN.QtyOnPO, 0) AS MainWhQtyOnPO,
            ISNULL(MAIN.QtyAvailable, 0) AS QtyAvailable,
            ISNULL(MAIN.StockingUnitCode, '') AS StockingUnitCode,
            ISNULL(MAIN.PurchasingUnitCode, '') AS PurchasingUnitCode,
            ISNULL(MAIN.PurchaseUnitOnHand, 0) AS PurchaseUnitOnHand,
            ISNULL(MAIN.PurchaseUnitOnPO, 0) AS PurchaseUnitOnPO,
            ISNULL(MAIN.PurchaseUnitAvailable, 0) AS PurchaseUnitAvailable,
            ISNULL(MAIN.PurchaseUnitsNeeded, 0) AS PurchaseUnitsNeeded,
            ISNULL(MAIN.PurchaseUnitsToOrder, 0) AS PurchaseUnitsToOrder,
            MAIN.SprayHWeek,
            ROW_NUMBER() OVER (
                PARTITION BY MAIN.StockLink
                ORDER BY MAIN.SprayHWeek DESC
            ) AS rn
        FROM agr._uvMainWarehouseReordering MAIN
        LEFT JOIN agr.ChemStock S
            ON S.ChemStockLink = MAIN.StockLink
        WHERE MAIN.SprayHWeek <= ?
    )
    SELECT
        StockLink,
        StockCode,
        StockDescription,
        TotalRequiredStocking,
        MainWhQty,
        MainWhQtyOnPO,
        QtyAvailable,
        StockingUnitCode,
        PurchasingUnitCode,
        PurchaseUnitOnHand,
        PurchaseUnitOnPO,
        PurchaseUnitAvailable,
        PurchaseUnitsNeeded,
        PurchaseUnitsToOrder,
        SprayHWeek
    FROM LatestWeek
    WHERE rn = 1
    ORDER BY StockCode;
    """

    cur.execute(sql, (week,))
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            'stock_link': r.StockLink,
            'stock_code': r.StockCode,
            'stock_description': r.StockDescription,
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
            'purchase_units_to_order': float(r.PurchaseUnitsToOrder)
        })

    return jsonify({'status': 'ok', 'week': week, 'data': results})


@agri_bp.route('/suggested-order/detail/<int:stock_id>', methods=['GET'])
@login_required
def suggested_order_detail(stock_id):
    week = request.args.get('week')
    if not week:
        return jsonify({'status': 'error', 'message': 'week parameter required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
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
            ROW_NUMBER() OVER (
                PARTITION BY P.SprayHWhseId
                ORDER BY P.SprayHWeek DESC
            ) AS rn
        FROM agr._uvStockProjectionUnitsNeededPerWH P
        LEFT JOIN stk._uvInventoryQty Inv
            ON Inv.WhseLink = P.SprayHWhseId
            AND Inv.StockLink = P.SprayLineStkId
        WHERE P.SprayHWeek <= ?
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
        SprayHWeek
    FROM LatestWeek
    WHERE rn = 1
    ORDER BY WhseName;
        """

    cur.execute(sql, (week, stock_id))
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
            'spray_h_week': r.SprayHWeek
        }
        for r in rows
    ]
    return jsonify({'status': 'ok', 'week': week, 'stock_id': stock_id, 'warehouses': results})


@agri_bp.route('/suggested-order/detail/<int:stock_id>/warehouse/<int:whse_id>', methods=['GET'])
@login_required
def suggested_order_warehouse_detail(stock_id, whse_id):
    week = request.args.get('week')
    if not week:
        return jsonify({'status': 'error', 'message': 'week parameter required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    sql = """
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
    WHERE HEA.SprayHWeek <= ? AND LIN.SprayLineStkId = ? AND HEA.SprayHWhseId = ?
    GROUP BY StockLink ,StockDescription
    ,LIN.SprayLineFunction ,Lin.SprayLineWitholdingPeriod
    ,IssLineStockLink ,cUnitCode, ProjectQty, 	Lin.SprayLineHeaderId,
	HEA.SprayHNo,
	HEA.SprayHDescription
    """

    cur.execute(sql, (week, stock_id, whse_id))
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
    return jsonify({'status': 'ok', 'week': week, 'stock_id': stock_id, 'whse_id': whse_id, 'sprays': results})
