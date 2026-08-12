from Inventory.routes import inventory_bp
from flask import request, render_template, abort, jsonify
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user

from Core.sdk_connection import EvolutionConnection, EvolutionAgentNotFoundError, EvolutionConnectionError
import Pastel.Evolution as Evo
import System
from System import DateTime
from Instance.local_settings import DEFAULT_PURCHASE_ORDER_PROJECT_ID

@inventory_bp.route('/create_purchase_order')
def create_purchase_order_page():
    if "PO_CREATE" not in current_user.permissions:
        abort(403)
    return render_template('purchase_order_create.html')

@inventory_bp.route('/purchase_order/suppliers', methods=['GET'])
def get_suppliers():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        Select DCLink, Name
        from cmn._uvSuppliers
        """)
        suppliers = cursor.fetchall()

        return jsonify({
            "success": True,
            "suppliers": [{'DCLink': row[0], 'Name': row[1]} for row in suppliers]
        })
    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        close_db_connection(conn)

@inventory_bp.route('/purchase_order/products', methods=['GET'])
def get_products():

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        warehouse_id = request.args.get('warehouse_id')
        supplier_id = request.args.get('supplier_id')
        if not warehouse_id or not supplier_id:
            return jsonify({"success": False, "message": "Missing warehouse_id or supplier_id"}), 400

        cursor.execute("""
            Select DISTINCT StockLink, StockCode, StockDescription, LINK.DefaultTaxTypeId, LINK.DefaultTaxRate
            from cmn._uvStockItems STK
            JOIN stk._uvStockLinks LINK on LINK.iStockID = STK.StockLink and iDCLink = ?
            JOIN [cmn].[_uvStockWarehouse] STKWHSE on STKWHSE.StockID = STK.StockLink and STKWHSE.WhseID = ?
        """, (supplier_id, warehouse_id))
        products = cursor.fetchall()

        return jsonify({
            "success": True,
            "products": [
                {
                    'StockLink': row[0],
                    'StockCode': row[1],
                    'StockDescription': row[2],
                    'DefaultTaxTypeId': row[3],
                    'DefaultTaxRate': row[4]
                }
                for row in products
            ]
        })
    except Exception as e:
        print(f"Error fetching products: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        close_db_connection(conn)

@inventory_bp.route('/purchase_order/stock_item_units/<int:stock_id>', methods=['GET'])
def purchase_order_stock_item_units(stock_id):
    """Return units of measure for a specific stock item."""
    conn = create_db_connection()
    cur = conn.cursor()
    supplier_id = request.args.get('supplier_id')
    if not supplier_id:
        return jsonify({'success': False, 'message': 'supplier_id parameter required'}), 400
    sql = """
    Select idUnits, cUnitCode,
    COALESCE(LastInvoicePrice, CST.PurchaseUnitLastGRVCost, 0) AS Cost,
	LINK.InvDate,
    CASE WHEN STKUOM.PurchaseUnitId = UOM.idUnits THEN 1 ELSE 0 END AS DefaultUnit
    from [cmn].[_uvStockUnits] STKUOM
    JOIN [cmn].[_uvStockItems] STK on STK.StockLink = STKUOM.StockLink
    JOIN [cmn].[_uvUOM] UOM on UOM.iUnitCategoryID = PurchaseUnitCatId
    LEFT JOIN [stk].[_uvStockLinks] LINK on LINK.iStockID = STKUOM.StockLink and LINK.iUnitsOfMeasureID = UOM.idUnits and LINK.iDCLink = ?
    LEFT JOIN [cmn].[_uvLastGRVCost] CST on CST.StockLink = STKUOM.StockLink and CST.iUOMDefPurchaseUnitID = UOM.idUnits and CST.iDCLink = ?
    WHERE STKUOM.StockLink = ?
    """
    cur.execute(sql, (supplier_id, supplier_id, stock_id))
    rows = cur.fetchall()
    conn.close()

    units = [
        {
            'unit_id': int(r.idUnits),
            'unit_code': r.cUnitCode,
            'cost': float(r.Cost),
            'inv_date': r.InvDate.isoformat() if r.InvDate else None,
            'default_unit': bool(r.DefaultUnit)
        }
        for r in rows
    ]

    return jsonify({'success': True, 'units': units})

@inventory_bp.route('/purchase_order/create-order', methods=['POST'])
@login_required
def create_purchase_order():
    if "PO_CREATE" not in current_user.permissions:
        abort(403)
    payload = request.get_json() or {}
    supplier_id = payload.get('supplier_id')
    warehouse_id = payload.get('warehouse_id')
    lines = payload.get('lines') or []
    print(f"Received payload for order creation: {payload}")  # Debugging line

    if not supplier_id:
        return jsonify({'success': False, 'message': 'supplier_id is required'}), 400
    if not warehouse_id:
        return jsonify({'success': False, 'message': 'warehouse_id is required'}), 400

    try:
        with EvolutionConnection():
            PO = Evo.PurchaseOrder()
            PO.Supplier = Evo.Supplier(int(supplier_id))
            PO.OrderDate = DateTime.Now
            PO.Description = f"Suggested Order generated by {current_user.username}"

            for line in lines:
                OD = Evo.OrderDetail()
                PO.Detail.Add(OD)

                OD.InventoryItem = Evo.InventoryItem(int(line.get('item_id')))
                OD.Quantity = float(line.get('qty'))
                OD.Unit = Evo.Unit(int(line.get('unit_id')))
                OD.UnitSellingPrice = float(line.get('unit_price'))
                OD.Warehouse = Evo.Warehouse(int(warehouse_id))
                OD.Project = Evo.Project(int(DEFAULT_PURCHASE_ORDER_PROJECT_ID))  # Use the default project ID
                OD.TaxType = Evo.TaxRate(int(line.get('tax_type_id'))) if line.get('tax_type_id') else None
            PO.Save()
            order_number = PO.OrderNo    

        created = [{
            'supplier_dc_link': supplier_id,
            'warehouse_id': warehouse_id,
            'lines': [{
                'item_id': line.get('item_id'),
                'unit_id': line.get('unit_id'),
                'qty': line.get('qty'),
                'unit_price': line.get('unit_price'),
                'tax_type_id': line.get('tax_type_id')
            } for line in lines],
            'count': len(lines)
        }]

        return jsonify({'success': True, 'order_number': order_number, 'created_orders': created})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500