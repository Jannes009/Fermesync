
from flask import request, jsonify, render_template, abort
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo                   

@inventory_bp.route("/add_stock", methods=["POST"])
@login_required
def add_stock():
    data = request.json
    product_link = data.get("product_link")
    warehouse_code = data.get("warehouse_code")
    quantity = data.get("quantity")
    print(product_link)
    if not product_link or not warehouse_code or quantity is None:
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
                from _uvInventoryQty
                Where StockLink = ? AND WhseLink = ?""",
                (product_link, warehouse_code_to_link(warehouse_code, cursor)))
            qty_on_hand = cursor.fetchone()[0]

            ItemInc.InventoryItem = Evo.InventoryItem(stock_code)
            ItemInc.Operation = Evo.InventoryOperation.Increase
            ItemInc.Quantity = float(quantity)
            ItemInc.Warehouse = Evo.Warehouse(warehouse_code)
            ItemInc.Reference = f"ADJUSTMENT-{warehouse_code}"
            ItemInc.Description = f"{stock_code} adjusted from {qty_on_hand} to {qty_on_hand + float(quantity)} by {current_user.username}"
            ItemInc.Post()

            conn.close()
            return jsonify ({"success": True})
    except Exception as ex:
        print("Stock Issue Submission Error:", str(ex))
        return jsonify({"success": False, "error:": str(ex)})