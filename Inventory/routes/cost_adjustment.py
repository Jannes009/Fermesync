from math import isfinite

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required

from Core.auth import close_db_connection, create_db_connection
from Core.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
from Inventory.routes import inventory_bp


_COST_PERMISSION = "COST_ADJUSTMENT"


def _has_cost_permission():
    return _COST_PERMISSION in current_user.permissions


@inventory_bp.route("/adjust_cost", methods=["GET"])
@login_required
def adjust_cost_page():
    if not _has_cost_permission():
        abort(403)
    return render_template("cost_adjustment.html")


@inventory_bp.route("/adjust_cost/products", methods=["GET"])
@login_required
def adjust_cost_products():
    if not _has_cost_permission():
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT StockLink, StockDescription
            FROM cmn._uvStockItems
            ORDER BY StockDescription
        """)
        products = [
            {
                "product_link": int(row.StockLink),
                "description": row.StockDescription,
            }
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "products": products})
    except Exception as ex:
        print("Error fetching cost adjustment products:", str(ex))
        return jsonify({"success": False, "message": "Error fetching products"}), 500
    finally:
        close_db_connection(conn)


@inventory_bp.route("/adjust_cost/current", methods=["GET"])
@login_required
def adjust_cost_current():
    if not _has_cost_permission():
        return jsonify({"success": False, "message": "Permission denied"}), 403

    product_link = request.args.get("product_link")
    if not product_link:
        return jsonify({"success": False, "message": "product_link is required"}), 400

    try:
        product_link = int(product_link)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "product_link must be an integer"}), 400

    conn = create_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SI.StockLink, SI.StockDescription, SC.AverageCost
            FROM cmn._uvStockItems SI
            LEFT JOIN cmn._uvStockCosts SC ON SC.StockID = SI.StockLink
            WHERE SI.StockLink = ?
        """, (product_link,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Product not found"}), 404

        return jsonify({
            "success": True,
            "product_link": int(row.StockLink),
            "description": row.StockDescription,
            "average_cost": float(row.AverageCost) if row.AverageCost is not None else None,
        })
    except Exception as ex:
        print("Error fetching current cost:", str(ex))
        return jsonify({"success": False, "message": "Error fetching current cost"}), 500
    finally:
        close_db_connection(conn)


@inventory_bp.route("/adjust_cost", methods=["POST"])
@login_required
def adjust_cost():
    if not _has_cost_permission():
        return jsonify({"success": False, "message": "Permission denied"}), 403

    data = request.get_json(silent=True) or {}
    product_link = data.get("product_link")
    cost_value = data.get("cost")
    if product_link is None or cost_value is None:
        return jsonify({"success": False, "message": "Product and cost are required"}), 400

    try:
        product_link = int(product_link)
        new_cost = float(cost_value)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Product and cost must be valid numbers"}), 400

    if not isfinite(new_cost) or new_cost < 0:
        return jsonify({"success": False, "message": "Cost must be zero or greater"}), 400

    conn = create_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 SI.StockLink, SI.StockDescription, SC.AverageCost, COALESCE(SW.WhseID, 0) WhseId
            FROM cmn._uvStockItems SI
            LEFT JOIN cmn._uvStockCosts SC ON SC.StockID = SI.StockLink
            LEFT JOIN cmn._uvStockWarehouse SW on SW.StockID = SI.StockLink
            WHERE SI.StockLink = ?
        """, (product_link,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Product not found"}), 404
        description = row.StockDescription
        old_cost = float(row.AverageCost) if row.AverageCost is not None else None
        whse_id = row.WhseId
    finally:
        close_db_connection(conn)

    try:
        with EvolutionConnection():
            stock_cost = Evo.InventoryTransaction()
            stock_cost.TransactionCode = Evo.TransactionCode(Evo.Module.Inventory, "ADJ")
            stock_cost.Operation = Evo.InventoryOperation.CostAdjustment
            stock_cost.InventoryItem = Evo.InventoryItem(product_link)
            stock_cost.UnitCost = new_cost
            stock_cost.Description = f"Fermesync {description} Cost Adjustment"
            stock_cost.Warehouse = Evo.Warehouse(int(whse_id))  # Use the fetched warehouse ID
            stock_cost.Reference = f"Adjusted cost from {old_cost if old_cost is not None else 'N/A'} to {new_cost}";
            stock_cost.Post()

        return jsonify({
            "success": True,
            "message": f"Cost for {description} updated successfully.",
            "product_link": product_link,
            "old_cost": old_cost,
            "new_cost": new_cost,
        })
    except Exception as ex:
        print("Cost Adjustment Error:", str(ex))
        return jsonify({"success": False, "message": str(ex)}), 500
