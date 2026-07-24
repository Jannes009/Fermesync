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
    low_stock = get_low_stock_items(warehouse_id)
    demand_groups = get_upcoming_demand(warehouse_id)
    warehouse_stock = get_warehouse_stock(warehouse_id)

    return render_template("qty.html",
                         low_stock=low_stock,
                         demand_groups=demand_groups,
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


def get_low_stock_items(warehouse_id=None):
    """Get items that are low on stock or need attention"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Query for items where available stock is below reorder level
        # This is a simplified query - adjust based on your actual database schema
        base_sql = """
        SELECT
            StockLink,
            StockCode,
            StockDescription,
            COALESCE(QtyOnHand, 0) as Available,
            ReorderLevel,
            COALESCE(QtyOnPo, 0) AS QtyOnPo,
            COALESCE(IncompleteIssuesQty, 0) AS QtyOnIssues,
            QtyOnPo
        FROM stk._uvInventoryQty
        WHERE COALESCE(QtyOnHand, 0) < ReorderLevel
            AND ReorderLevel > 0
        """

        params = []
        if warehouse_id is not None:
            base_sql += "\n            AND WhseLink = ?"
            params.append(warehouse_id)

        base_sql += "\n        ORDER BY (ReorderLevel - COALESCE(QtyOnHand, 0)) DESC"

        cursor.execute(base_sql, tuple(params))

        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return results

    except Exception as e:
        print(f"Error fetching low stock items: {e}")
        return []
    finally:
        close_db_connection(conn)

def get_upcoming_demand(warehouse_id=None):
    """Get upcoming demand grouped by week with running balances"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Get stock projections with product details
        base_sql = """
        SELECT 
            PJN.SprayLineStkId as StockId,
            STK.StockCode, STK.StockDescription,
            PJN.SprayHWhseId as WhseId,
            PJN.QtyOnPO,
            PJN.SprayHWeek,
            PJN.OpeningBalance,
            PJN.QtyNeeded,
            PJN.ProjectedBalance
        FROM agr._uvStockProjection PJN
        JOIN cmn._uvStockItems STK on STK.StockLink = PJN.SprayLineStkId
        """

        params = []
        if warehouse_id is not None:
            base_sql += "\n WHERE PJN.SprayHWhseId = ?"
            params.append(warehouse_id)

        base_sql += "\n ORDER BY PJN.SprayHWeek, PJN.SprayLineStkId"

        cursor.execute(base_sql, tuple(params))

        results = cursor.fetchall()

        # Group by week
        weeks = {}
        for row in results:
            week = row.SprayHWeek
            if week not in weeks:
                weeks[week] = []
            
            status = 'shortage' if row.ProjectedBalance < 0 else 'sufficient'
            
            weeks[week].append({
                "StockLink": row.StockId,
                "StockCode": row.StockCode,
                "StockDescription": row.StockDescription,
                "OpeningBalance": format_qty(row.OpeningBalance),
                "QtyNeeded": format_qty(row.QtyNeeded),
                "ProjectedBalance": format_qty(row.ProjectedBalance),
                "QtyOnPO": format_qty(row.QtyOnPO),
                "Status": status
            })
        

        # Convert to list format with attention/sufficient separation
        demand_groups = []
        for week_key in sorted(weeks.keys()):
            items = weeks[week_key]
            items_needing_attention = [item for item in items if item["Status"] == "shortage"]
            sufficient_items = [item for item in items if item["Status"] == "sufficient"]
            
            if items_needing_attention or sufficient_items:
                demand_groups.append({
                    "label": f"Week {week_key}",
                    "items_needing_attention": items_needing_attention,
                    "sufficient_items": sufficient_items,
                    "attention_count": len(items_needing_attention),
                    "total_count": len(items)
                })
        return demand_groups
    except Exception as e:
        print(f"Error fetching upcoming demand: {e}")
        return []
    finally:
        close_db_connection(conn)

 