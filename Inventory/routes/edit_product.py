from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort
from datetime import datetime, timedelta
from decimal import Decimal
import json


def format_qty(value, ndigits=2):
    """Format quantity to avoid infinite decimals"""
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    try:
        v = float(value)
    except (ValueError, TypeError):
        return value
    
    if v.is_integer():
        return int(v)
    return round(v, ndigits)


@inventory_bp.route('/edit-product/<int:product_id>', methods=['GET'])
@login_required
def edit_product_page(product_id):
    """Render the edit product modal page"""
    return render_template('edit_product.html')


@inventory_bp.route("/product/<int:stock_id>", methods=["GET"])
@login_required
def get_product_for_modal(stock_id):
    """Get product details for the modal editor - REST API endpoint"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # Get product basic info from StkItem via the inventory view
        cursor.execute("""
            SELECT 
                StockLink,
                StockCode,
                StockDescription,
                COALESCE(ReorderLevel, 0) AS ReorderLevel,
                COALESCE(ReorderQty, 0) AS ReorderQty,
                COALESCE(LeadTime, 0) AS LeadTime
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
            GROUP BY StockLink, StockCode, StockDescription, ReorderLevel, ReorderQty, LeadTime
        """, (stock_id,))

        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Product not found"}), 404

        # Get warehouse configuration for this product
        cursor.execute("""
            SELECT 
                w.WhseLink,
                w.WhseName,
                COALESCE(spl.PrefSupplierId, 0) AS pref_supplier_id
            FROM cmn._uvWarehouses w
            LEFT JOIN stk.StockSupplier spl 
                ON spl.StockSupplierStockId = ? 
                AND spl.StockSupplierWarehouseId = w.WhseLink
            ORDER BY w.WhseName
        """, (stock_id,))

        warehouse_rows = cursor.fetchall()
        warehouses = []
        
        for wh in warehouse_rows:
            # Get suppliers for this warehouse
            cursor.execute("""
                SELECT 
                    SupplierLink,
                    SupplierName
                FROM cmn._uvSuppliers
                WHERE SupplierActive = 1
                ORDER BY SupplierName
            """)
            
            suppliers = [
                {"id": s.SupplierLink, "name": s.SupplierName}
                for s in cursor.fetchall()
            ]
            
            warehouses.append({
                "id": wh.WhseLink,
                "name": wh.WhseName,
                "active": True,
                "suppliers": suppliers,
                "pref_supplier": wh.pref_supplier_id if wh.pref_supplier_id else None
            })

        product = {
            "id": row.StockLink,
            "code": row.StockCode,
            "desc": row.StockDescription,
            "reorder_level": format_qty(row.ReorderLevel),
            "reorder_qty": format_qty(row.ReorderQty),
            "lead_time": format_qty(row.LeadTime),
            "warehouses": warehouses
        }

        return jsonify(product)

    except Exception as e:
        print(f"Error fetching product for modal: {e}")
        return jsonify({"error": "Failed to fetch product"}), 500
    finally:
        close_db_connection(conn)


@inventory_bp.route("/product/update", methods=["POST"])
@login_required
def update_product():
    """Update product reorder levels and warehouse preferences - REST API endpoint"""
    data = request.get_json()
    
    if not data or "id" not in data:
        return jsonify({"error": "Missing product ID"}), 400

    stock_id = data.get("id")
    reorder_level = data.get("reorder_level")
    reorder_qty = data.get("reorder_qty")
    
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # Check if product exists
        cursor.execute("""
            SELECT StockLink FROM stk._uvInventoryQty WHERE StockLink = ?
        """, (stock_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Product not found"}), 404

        # Update reorder level and qty if provided
        if reorder_level is not None or reorder_qty is not None:
            updates = []
            params = []
            
            if reorder_level is not None:
                updates.append("ReorderLevel = ?")
                params.append(float(reorder_level))
            
            if reorder_qty is not None:
                updates.append("ReorderQty = ?")
                params.append(float(reorder_qty))
            
            if updates:
                params.append(stock_id)
                update_query = f"UPDATE stk.StkItem SET {', '.join(updates)} WHERE StockLink = ?"
                cursor.execute(update_query, tuple(params))

        conn.commit()
        return jsonify({"success": True, "message": "Product updated successfully"})

    except Exception as e:
        conn.rollback()
        print(f"Error updating product: {e}")
        return jsonify({"error": f"Failed to update product: {str(e)}"}), 500
    finally:
        close_db_connection(conn)
