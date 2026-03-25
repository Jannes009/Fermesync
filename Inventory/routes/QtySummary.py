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
    FROM [stk]._uvInventoryQty
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
            QTY.StockLink,
            QTY.StockCode,
            QTY.StockDescription,
            QTY.cCategoryName,
            QTY.EvoQtyOnHand,
            QTY.IncompleteIssuesQty,
            QTY.QtyOnPo,
            QTY.ReorderLevel,
            QTY.ToBeOrdered,
            CNT.DateLastCounted
        FROM [stk]._uvInventoryQty QTY
        LEFT JOIN (
            SELECT 
                InvCountCatId,
                MAX(InvCountTimeFinalised) AS DateLastCounted
            FROM [stk].InventoryCountHeaders
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
@inventory_bp.route("/bulk-update-stock", methods=["POST"])
@login_required
def bulk_update_stock():
    try:
        data = request.get_json()
        stock_ids = data.get("stockIds", [])
        warehouse_id = data.get("warehouseId")  # Get warehouse ID from request
        category = data.get("category")
        reorder_level = data.get("reorderLevel")
        reorder_qty = data.get("reorderQty")

        if not stock_ids:
            return jsonify({"success": False, "error": "No items selected"}), 400

        conn = create_db_connection()
        cursor = conn.cursor()

        # 1️⃣ Create temp table
        cursor.execute("CREATE TABLE #StockIds (StockId INT);")

        # 2️⃣ Bulk insert IDs
        cursor.fast_executemany = True
        cursor.executemany(
            "INSERT INTO #StockIds (StockId) VALUES (?)",
            [(sid,) for sid in stock_ids]
        )

        # 3️⃣ Call stored procedure with warehouse filter
        cursor.execute("""
            EXEC [stk].sp_BulkUpdateStock
                @Category = ?,
                @ReorderLevel = ?,
                @ReorderQty = ?,
                @WarehouseId = ?
        """, (category, reorder_level, reorder_qty, warehouse_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"Updated {len(stock_ids)} items"
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@inventory_bp.route("/fetch_all_categories", methods=["GET"])
def fetch_all_categories():
    conn = create_db_connection()
    cursor = conn.cursor()
    try:

        cursor.execute("""
        Select Distinct idStockCategories, cCategoryName
        from common.[_uvCategories]
        """)

        rows = cursor.fetchall()

        conn.close()

        categories_list = [
            {
                "category_id": row.idStockCategories,
                "category_name": row.cCategoryName,
            }
            for row in rows
        ]
        return jsonify({"categories": categories_list})
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return jsonify({"error": str(e)}), 500
    
@inventory_bp.route("/add-category", methods=["POST"])
@login_required
def add_category():
    data = request.get_json()

    name = data.get("name")
    description = data.get("description")

    if not name:
        return jsonify(success=False, error="Category name required")

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            EXEC [stk].sp_InsertStockCategory
            @CategoryName = ?,
            @CategoryDescription = ?;
        """, (name, description))

        row = cursor.fetchone()

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(
            success=True,
            category_id=row.CategoryId,
            category_name=row.CategoryName
        )

    except Exception as e:
        return jsonify(success=False, error=str(e))
