import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import warehouse_code_to_link, project_code_to_link, stock_link_to_code
from datetime import datetime
from Inventory.routes.notifications import emit_event
from Inventory.routes.offline import fetch_warehouses

@inventory_bp.route("/qty-summary")
@login_required
def inventory_qty_summary():
    conn = create_db_connection()
    cursor = conn.cursor()
    
    sql = f"""
    SELECT
        WhseLink, WhseCode, WhseName,
        SUM(QtyOnHand) QtyOnHand,
        COUNT(DISTINCT StockLink) ItemCount,
        --SUM(IncompleteIssuesQty) IncompleteIssuesQty,
        --SUM(QtyOnPo) QtyOnPo,
        SUM(ToBeOrdered) ToBeOrdered
    FROM inventory._uvInventoryQty
    WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
    GROUP BY WhseLink, WhseCode, WhseName
    ORDER BY WhseName, WhseCode
    """
    cursor.execute(sql, current_user.warehouses)
    warehouses = cursor.fetchall()
    
    return render_template(
        "qty_summary.html",
        warehouses=warehouses
    )


@inventory_bp.route("/qty-summary/<int:warehouse_id>")
@login_required
def inventory_qty_summary_warehouse(warehouse_id):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT
            QTY.StockCode,
            QTY.StockDescription,
            QTY.cCategoryName,
            QTY.EvoQtyOnHand,
            QTY.IncompleteIssuesQty,
            QTY.QtyOnPo,
            QTY.ReorderLevel,
            QTY.ToBeOrdered,
            CNT.DateLastCounted
        FROM inventory._uvInventoryQty QTY
        LEFT JOIN (
            SELECT 
                InvCountCatId,
                MAX(InvCountTimeFinalised) AS DateLastCounted
            FROM inventory.InventoryCountHeaders
            WHERE InvCountWhseId = ?
            AND InvCountStatus = 'FINALISED'
            GROUP BY InvCountCatId
        ) CNT 
            ON CNT.InvCountCatId = QTY.idStockCategories
        WHERE QTY.WhseLink = ?
        ORDER BY 
            CASE WHEN QTY.ToBeOrdered > 0 THEN 1 ELSE 0 END DESC,
            QTY.StockDescription;
        """
        
        cursor.execute(sql, (warehouse_id, warehouse_id))
        rows = cursor.fetchall()
        
        # Convert rows to list of dicts
        columns = [desc[0] for desc in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]
        
        cursor.close()
        conn.close()
        
        return jsonify(data)
    
    except Exception as e:
        print(f"Error fetching inventory qty: {e}")
        return jsonify({"error": str(e)}), 500


# Add new endpoint
@inventory_bp.route("/bulk-update-stock", methods=["POST"])
@login_required
def bulk_update_stock():
    try:
        data = request.get_json()
        stock_ids = data.get("stockIds", [])
        category = data.get("category")
        reorder_level = data.get("reorderLevel")
        reorder_qty = data.get("reorderQty")

        if not stock_ids:
            return jsonify({"success": False, "error": "No items selected"}), 400

        conn = create_db_connection()
        cursor = conn.cursor()

        for stock_id in stock_ids:
            updates = []
            params = []

            if category:
                updates.append("cCategoryLink = ?")
                params.append(category)
            if reorder_level is not None:
                updates.append("ReorderLevel = ?")
                params.append(reorder_level)
            if reorder_qty is not None:
                updates.append("ReorderQty = ?")
                params.append(reorder_qty)

            if updates:
                params.append(stock_id)
                sql = f"UPDATE inventory._uvInventoryQty SET {', '.join(updates)} WHERE StockId = ?"
                cursor.execute(sql, params)

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": f"Updated {len(stock_ids)} items"})

    except Exception as e:
        print(f"Error bulk updating stock: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
