import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required, current_user
from auth import get_common_db_connection, close_connection
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
    FROM _uvInventoryQty
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
        FROM _uvInventoryQty QTY
        LEFT JOIN (
            SELECT 
                InvCountCatId,
                MAX(InvCountTimeFinalised) AS DateLastCounted
            FROM InventoryCountHeaders
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

