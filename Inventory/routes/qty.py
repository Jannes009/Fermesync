from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort
from datetime import datetime, timedelta
from decimal import Decimal
import json

@inventory_bp.route("/qty")
@login_required
def inventory_qty():
    # Get currently selected warehouse
    if "WHSE_QTYS" not in current_user.permissions:
        abort(403)
    warehouse_id = request.args.get('whse', type=int)

    # Build warehouse list from user-accessible warehouses
    warehouses = get_warehouse_list()

    if warehouse_id is None and warehouses:
        warehouse_id = warehouses[0]['WhseLink']

    # Fetch data for the template filtered by warehouse
    warehouse_stock = get_warehouse_stock(warehouse_id)

    return render_template("qty.html",
                         warehouse_stock=warehouse_stock,
                         warehouses=warehouses,
                         selected_warehouse=warehouse_id)

def get_warehouse_list():
    """Get list of warehouses the user has access to"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        warehouses = current_user.warehouses
        if len(warehouses) == 0:
            return []
        placeholders = ",".join(["?"] * len(warehouses))
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT WhseLink, WhseCode, WhseDescription
            FROM cmn._uvWarehouses
            WHERE WhseLink IN ({placeholders})
            ORDER BY WhseCode
        """, warehouses)
        rows = cursor.fetchall()
        warehouses = [
            {"WhseLink": r.WhseLink, "WhseCode": r.WhseCode, "WhseDescription": r.WhseDescription}
            for r in rows
        ]
        return warehouses

    except Exception as e:
        print(f"Error fetching warehouses: {e}")
        return []
    finally:
        close_db_connection(conn)

def get_warehouse_stock(warehouse_id):
    """Get stock levels for all products in the selected warehouse"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = """
        WITH FirstNegative AS (
            SELECT 
                SprayLineStkId,
                SprayHWhseId,
                SprayHWeek,
                ProjectedBalance,
                ROW_NUMBER() OVER (
                    PARTITION BY SprayLineStkId, SprayHWhseId 
                    ORDER BY SprayHWeek
                ) AS rn
            FROM [agr].[_uvStockProjection]
            WHERE ProjectedBalance < 0
        )

        SELECT 
            QTY.StockLink, 
            QTY.StockCode, 
            QTY.StockDescription, 
			ACT.ChemActIngredient,
            QTY.cCategoryName,
            COALESCE(QTY.QtyOnHand, 0) AS QtyOnHand,
            COALESCE(QTY.QtyOnPo, 0) AS QtyOnPo, 
            COALESCE(QTY.IncompleteIssuesQty, 0) AS QtyOnIssues, 
            FN.SprayHWeek
        FROM stk._uvInventoryQty QTY
		LEFT JOIN agr.ChemStock STK on STK.ChemStockLink = QTY.StockLink
		LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
        LEFT JOIN FirstNegative FN 
            ON FN.SprayHWhseId = QTY.WhseLink 
            AND FN.SprayLineStkId = QTY.StockLink
            AND FN.rn = 1
        WHERE QTY.WhseLink = ?
        ORDER BY ACT.ChemActIngredient, QTY.StockCode;
        """
        cursor.execute(query, (warehouse_id,))
        rows = cursor.fetchall()
        stock = [
            {
                "StockLink": r.StockLink,
                "StockCode": r.StockCode,
                "StockDescription": r.StockDescription,
                "ActiveIngredient": r.ChemActIngredient,
                "Category": r.cCategoryName,
                "QtyOnHand": format_qty(r.QtyOnHand),
                "QtyOnPo": format_qty(r.QtyOnPo),
                "QtyOnIssues": format_qty(r.QtyOnIssues),
                "SprayHWeek": r.SprayHWeek
            }
            for r in rows
        ]
        return stock

    except Exception as e:
        print(f"Error fetching warehouse stock: {e}")
        return []
    finally:
        close_db_connection(conn)


def format_qty(value, ndigits=2):
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
 