
from flask import request, jsonify, render_template, abort
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_link_to_code, project_code_to_link, stock_link_to_code
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo           
from Instance.config import DEFAULT_STOCK_ADJUSTMENT_PROJECT_ID        

@inventory_bp.route("/adjust_stock", methods=["POST"])
@login_required
def adjust_stock():
    data = request.json
    # Permission check
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        return jsonify({"success": False, "error": "Permission denied"}), 403
    product_link = data.get("product_link")
    warehouse_link = data.get("warehouse_link")
    quantity = data.get("quantity")
    operation = (data.get("operation") or "add").lower()
    print(product_link)
    if not product_link or not warehouse_link or quantity is None:
        return jsonify({"success": False, "message": "Missing required fields"}), 400

    try:
        with EvolutionConnection():
            ItemInc = Evo.InventoryTransaction()

            ItemInc.TransactionCode = Evo.TransactionCode(Evo.Module.Inventory, "ADJ")

            conn = create_db_connection()
            cursor = conn.cursor()
            stock_code = stock_link_to_code(product_link, cursor)

            if not stock_code:
                raise ValueError(f"No stock code found for product_link={product_link}")
            
            cursor.execute("""
                Select QtyOnHand
                from stk._uvInventoryQty
                Where StockLink = ? AND WhseLink = ?""",
                (product_link, warehouse_link))
            qty_on_hand = cursor.fetchone()[0]

            ItemInc.InventoryItem = Evo.InventoryItem(stock_code)

            # Determine operation and quantity to post
            qty_float = float(quantity)
            if operation == 'set':
                # compute delta between desired and current
                delta = qty_float - float(qty_on_hand)
                if delta == 0:
                    conn.close()
                    return jsonify({"success": True, "message": "No change needed"})
                if delta > 0:
                    ItemInc.Operation = Evo.InventoryOperation.Increase
                    ItemInc.Quantity = delta
                else:
                    ItemInc.Operation = Evo.InventoryOperation.Decrease
                    ItemInc.Quantity = abs(delta)
            elif operation == 'subtract' or operation == 'decrease' or operation == 'remove':
                ItemInc.Operation = Evo.InventoryOperation.Decrease
                ItemInc.Quantity = qty_float
            else:
                # default to add/increase
                ItemInc.Operation = Evo.InventoryOperation.Increase
                ItemInc.Quantity = qty_float
            ItemInc.Warehouse = Evo.Warehouse(int(warehouse_link))
            ItemInc.Reference = f"ADJUSTMENT-{warehouse_link_to_code(warehouse_link, cursor)}"
            ItemInc.Description = f"{stock_code} adjusted from {qty_on_hand} to {qty_on_hand + float(quantity)} by {current_user.username}"
            ItemInc.Project = Evo.Project(DEFAULT_STOCK_ADJUSTMENT_PROJECT_ID)
            ItemInc.Post()

            conn.close()
            return jsonify({"success": True})
    except Exception as ex:
        print("Stock Issue Submission Error:", str(ex))
        return jsonify({"success": False, "error": str(ex)}), 500


@inventory_bp.route("/adjust_stock", methods=["GET"])
@login_required
def adjust_stock_page():
    """Render the stock adjustment page. Can be loaded as a full page."""
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        abort(403)
    return render_template('stock_adjustment.html', embed=False)


@inventory_bp.route('/adjust_stock/popup', methods=['GET'])
@login_required
def adjust_stock_popup():
    """Return the page fragment suitable for embedding in a modal."""
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        abort(403)
    return render_template('stock_adjustment.html', embed=True)


@inventory_bp.route('/adjust_stock/products', methods=['GET'])
@login_required
def adjust_stock_products():
    """Return a short list of products for the dropdown (id + description + units)."""
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
    SELECT DISTINCT
       q.StockLink,
       q.StockDescription,
       u.PurchasingUnitCode,
       u.StockingUnitCode,
       u.ConversionFactor
    FROM stk._uvInventoryQty q
    LEFT JOIN cmn._uvStockUnitConversion u ON u.StockLink = q.StockLink
    WHERE q.WhseItem = 1 AND q.ServiceItem = 0
    ORDER BY q.StockDescription
    """
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    products = [{
        'product_link': int(r.StockLink),
        'description': r.StockDescription,
        'purchasing_unit_code': r.PurchasingUnitCode or '',
        'stocking_unit_code': r.StockingUnitCode or '',
        'conversion_factor': float(r.ConversionFactor) if r.ConversionFactor else 1.0
    } for r in rows]
    return jsonify({'status': 'ok', 'products': products})


@inventory_bp.route('/adjust_stock/warehouses', methods=['GET'])
@login_required
def adjust_stock_warehouses():
    """Return warehouses that allow buying into for the selected stock item."""
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
    stock_link = request.args.get('stock_link')
    if not stock_link:
        return jsonify({'status': 'error', 'message': 'stock_link is required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    sql = """
    SELECT DISTINCT W.WhseLink, S.WhseDescription
    FROM cmn._uvStockWarehouse S
    JOIN cmn._uvWarehouses W ON W.WhseLink = S.WhseID
    WHERE S.bAllowToBuyInto = 1
      AND S.StockID = ?
    ORDER BY S.WhseDescription
    """
    cur.execute(sql, (stock_link,))
    rows = cur.fetchall()
    conn.close()
    whs = [{ 'whse_link': r.WhseLink, 'whse_description': r.WhseDescription } for r in rows]
    return jsonify({'status': 'ok', 'warehouses': whs})


@inventory_bp.route('/adjust_stock/qty', methods=['GET'])
@login_required
def adjust_stock_qty():
    """Return qty on hand for a selected product and warehouse with unit information."""
    if "STOCK_ADJUSTMENT" not in current_user.permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
    stock_link = request.args.get('stock_link')
    warehouse_link = request.args.get('warehouse_link')
    if not stock_link or not warehouse_link:
        return jsonify({'status': 'error', 'message': 'stock_link and warehouse_link are required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                q.QtyOnHand,
                u.PurchasingUnitCode,
                u.StockingUnitCode,
                u.ConversionFactor
            FROM stk._uvInventoryQty q
            LEFT JOIN cmn._uvStockUnitConversion u ON u.StockLink = q.StockLink
            WHERE q.StockLink = ? AND q.WhseLink = ?
        """, (stock_link, warehouse_link))
        row = cur.fetchone()
        if row:
            qty_on_hand = float(row[0])
            purchasing_unit = row[1] or ''
            stocking_unit = row[2] or ''
            conversion_factor = float(row[3]) if row[3] else 1.0
        else:
            qty_on_hand = 0.0
            purchasing_unit = ''
            stocking_unit = ''
            conversion_factor = 1.0
    finally:
        conn.close()

    return jsonify({
        'status': 'ok',
        'stock_link': int(stock_link),
        'warehouse_link': int(warehouse_link),
        'qty_on_hand': qty_on_hand,
        'purchasing_unit_code': purchasing_unit,
        'stocking_unit_code': stocking_unit,
        'conversion_factor': conversion_factor
    })