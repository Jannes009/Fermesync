from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
import System
from System import DateTime
from Instance.config import DEFAULT_PURCHASE_ORDER_PROJECT_ID

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
			ISNULL(MAIN.PurchasingUnitId, '') AS PurchasingUnitId,
            ISNULL(MAIN.PurchasingUnitCode, '') AS PurchasingUnitCode,
            ISNULL(MAIN.PurchaseUnitOnHand, 0) AS PurchaseUnitOnHand,
            ISNULL(MAIN.PurchaseUnitOnPO, 0) AS PurchaseUnitOnPO,
            ISNULL(MAIN.PurchaseUnitAvailable, 0) AS PurchaseUnitAvailable,
            ISNULL(MAIN.PurchaseUnitsNeeded, 0) AS PurchaseUnitsNeeded,
            ISNULL(MAIN.PurchaseUnitsToOrder, 0) AS PurchaseUnitsToOrder,
            -- supplier and pricing information (from stock links)
            ISNULL(LINK.iDCLink, 0) AS SupplierDCLink,
            ISNULL(LINK.bDefaultSupplier, 0) AS DefaultSupplier,
            ISNULL(SUP.Name, '') AS SupplierName,
            ISNULL(LINK.LastInvoicePrice, ISNULL(GRV.PurchaseUnitLastGRVCost, 0)) AS LastInvoicePrice,
            MAIN.SprayHWeek,
            ROW_NUMBER() OVER (
                PARTITION BY MAIN.StockLink
                ORDER BY MAIN.SprayHWeek DESC
            ) AS rn
        FROM agr._uvMainWarehouseReordering MAIN
        LEFT JOIN agr.ChemStock S
            ON S.ChemStockLink = MAIN.StockLink
        LEFT JOIN stk._uvStockLinks LINK
            ON LINK.iStockID = MAIN.StockLink
        LEFT JOIN cmn._uvSuppliers SUP
            ON SUP.DCLink = LINK.iDCLink
		LEFT JOIN [cmn].[_uvLastGRVCost] GRV on GRV.StockLink = MAIN.StockLink
        WHERE MAIN.SprayHWeek <= ?
    )
    SELECT
        LatestWeek.StockLink,
        LatestWeek.StockCode,
        LatestWeek.StockDescription,
        LatestWeek.SupplierDCLink,
        LatestWeek.DefaultSupplier,
        LatestWeek.SupplierName,
        LatestWeek.LastInvoicePrice,
        LatestWeek.TotalRequiredStocking,
        LatestWeek.MainWhQty,
        LatestWeek.MainWhQtyOnPO,
        LatestWeek.QtyAvailable,
        LatestWeek.StockingUnitCode,
		LatestWeek.PurchasingUnitId,
        LatestWeek.PurchasingUnitCode,
        LatestWeek.PurchaseUnitOnHand,
        LatestWeek.PurchaseUnitOnPO,
        LatestWeek.PurchaseUnitAvailable,
        LatestWeek.PurchaseUnitsNeeded,
        LatestWeek.PurchaseUnitsToOrder,
        LatestWeek.SprayHWeek
    FROM LatestWeek
    LEFT JOIN cmn._uvUOM UOM ON UOM.cUnitCode = LatestWeek.PurchasingUnitCode
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
            'supplier_dc_link': int(r.SupplierDCLink) if hasattr(r, 'SupplierDCLink') else None,
            'default_supplier': bool(r.DefaultSupplier) if hasattr(r, 'DefaultSupplier') else False,
            'supplier_name': r.SupplierName if hasattr(r, 'SupplierName') else '',
            'last_invoice_price': float(r.LastInvoicePrice) if hasattr(r, 'LastInvoicePrice') else 0.0
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
        SprayHWeek,
		PurchaseQtyOnIBT
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
            'spray_h_week': r.SprayHWeek,
            'PurchaseQtyOnIBT': float(r.PurchaseQtyOnIBT or 0)
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


@agri_bp.route('/suggested-order/stock-suppliers/<int:stock_id>', methods=['GET'])
@login_required
def suggested_order_stock_suppliers(stock_id):
    """Return suppliers linked to a specific stock item including last invoice price and default flag."""
    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
    SELECT
        L.iDCLink AS DCLink,
        ISNULL(S.Name, '') AS Name,
        ISNULL(L.LastInvoicePrice, ISNULL(GCST.PurchaseUnitLastGRVCost,0)) AS LastInvoicePrice,
        ISNULL(L.bDefaultSupplier, 0) AS DefaultSupplier,
        L.iUnitsOfMeasureID AS UnitId,
        UOM.cUnitCode AS UnitCode
    FROM stk._uvStockLinks L
    LEFT JOIN cmn._uvSuppliers S ON S.DCLink = L.iDCLink
    LEFT JOIN cmn._uvUOM UOM on UOM.idUnits = iUnitsOfMeasureID
	LEFT JOIN cmn._uvLastGRVCost GCST on GCST.StockLink = L.iStockID and GCST.iUOMDefPurchaseUnitID = L.iUnitsOfMeasureID
    WHERE L.iStockID = ?
    ORDER BY ISNULL(L.bDefaultSupplier,0) DESC, S.Name
    """
    cur.execute(sql, (stock_id,))
    rows = cur.fetchall()
    conn.close()

    suppliers = [{
        'dc_link': int(r.DCLink),
        'name': r.Name, 
        'last_invoice_price': float(r.LastInvoicePrice),
        'default_supplier': bool(r.DefaultSupplier), 
        'unit_id': int(r.UnitId) if hasattr(r, 'UnitId') and r.UnitId is not None else None,
        'unit_code': r.UnitCode} 
        for r in rows
        ]
    return jsonify({'status': 'ok', 'suppliers': suppliers})


@agri_bp.route('/suggested-order/order-warehouses', methods=['POST'])
@login_required
def suggested_order_warehouses():
    payload = request.get_json() or {}
    stock_ids = payload.get('stock_ids') or []
    if not isinstance(stock_ids, list) or not stock_ids:
        return jsonify({'status': 'error', 'message': 'stock_ids array is required'}), 400

    ids = [int(i) for i in stock_ids if isinstance(i, (int, str)) and str(i).strip() != '']
    if not ids:
        return jsonify({'status': 'error', 'message': 'stock_ids must contain at least one value'}), 400

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

    return jsonify({'status': 'ok', 'warehouses': warehouses})


@agri_bp.route('/suggested-order/create-order', methods=['POST'])
@login_required
def suggested_order_create_order():
    payload = request.get_json() or {}
    supplier_id = payload.get('supplier_id')
    warehouse_id = payload.get('warehouse_id')
    lines = payload.get('lines') or []
    print(f"Received payload for order creation: {payload}")  # Debugging line

    if not supplier_id:
        return jsonify({'status': 'error', 'message': 'supplier_id is required'}), 400
    if not warehouse_id:
        return jsonify({'status': 'error', 'message': 'warehouse_id is required'}), 400
    
    try:
        with EvolutionConnection():
            PO = Evo.PurchaseOrder()
            PO.Supplier = Evo.Supplier(int(supplier_id))
            PO.OrderDate = DateTime.Now
            PO.Description = f"Suggested Order generated by {current_user.username}"

            for line in lines:
                OD = Evo.OrderDetail()
                PO.Detail.Add(OD)

                OD.InventoryItem = Evo.InventoryItem(int(line.get('product_id')))
                OD.Quantity = float(line.get('qty'))
                OD.Unit = Evo.Unit(int(line.get('unit_id')))
                OD.UnitSellingPrice = float(line.get('unit_price'))
                OD.Warehouse = Evo.Warehouse(int(warehouse_id))
                OD.Project = Evo.Project(int(DEFAULT_PURCHASE_ORDER_PROJECT_ID))  # Use the default project ID
            PO.Save()
            order_number = PO.OrderNo    

        created = [{
            'supplier_dc_link': supplier_id,
            'warehouse_id': warehouse_id,
            'lines': [{
                'product_id': line.get('product_id'),
                'unit_id': line.get('unit_id'),
                'qty': line.get('qty'),
                'unit_price': line.get('unit_price')
            } for line in lines],
            'count': len(lines)
        }]

        return jsonify({'status': 'ok', 'order_number': order_number, 'created_orders': created})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500