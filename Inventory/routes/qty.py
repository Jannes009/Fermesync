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

@inventory_bp.route("/get-product/<int:stock_link>")
@login_required
def get_product(stock_link):
    """Get product details for editing"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # get warehouse filter parameter for details request
        warehouse_id = request.args.get('whse', type=int)

        # Get product details from StkItem table
        cursor.execute("""
            SELECT StockCode, StockDescription, ReorderLevel, ReorderQty
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
        """, (stock_link,))

        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Product not found"}), 404

        # Get current stock numbers for selected warehouse
        qty_query = """
            SELECT
                COALESCE(QtyOnHand, 0) AS QtyOnHand,
                COALESCE(QtyOnPo, 0) AS QtyOnPo,
                COALESCE(IncompleteIssuesQty, 0) AS QtyOnIssues
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
        """

        params = [stock_link]
        if warehouse_id is not None:
            qty_query += " AND WhseLink = ?"
            params.append(warehouse_id)

        cursor.execute(qty_query, tuple(params))
        qty_row = cursor.fetchone()

        if qty_row:
            qty_on_hand = qty_row.QtyOnHand
            qty_on_po = qty_row.QtyOnPo
            qty_on_issues = qty_row.QtyOnIssues
        else:
            qty_on_hand = qty_on_po = qty_on_issues = 0

        # Get quantities in other warehouses for this product
        other_wh_query = """
            SELECT WhseLink, WhseCode, WhseName, COALESCE(QtyOnHand, 0) AS QtyOnHand, COALESCE(QtyOnPo, 0) AS QtyOnPo
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
        """
        if warehouse_id is not None:
            other_wh_query += " AND WhseLink <> ?"
            cursor.execute(other_wh_query, (stock_link, warehouse_id))
        else:
            cursor.execute(other_wh_query, (stock_link,))

        other_wh_rows = cursor.fetchall()
        other_warehouses = [
            {
                'WhseLink': r.WhseLink,
                'WhseCode': r.WhseCode,
                'WhseName': r.WhseName,
                'QtyOnHand': r.QtyOnHand,
                'QtyOnPo': r.QtyOnPo
            }
            for r in other_wh_rows
        ]

        cursor.execute("""
        Select SprayId, SprayHNo, SprayHDate, StockId, TotalQty
        FROM [agr].[_uvSprayStockRequirements]
        WHERE StockId = ? And WhseId = ?
        """, (stock_link, warehouse_id))
        sprays = cursor.fetchall()

        product = {
            "StockLink": stock_link,
            "StockCode": row.StockCode,
            "StockDescription": row.StockDescription,
            "ReorderLevel": format_qty(row.ReorderLevel),
            "ReorderQty": format_qty(row.ReorderQty),
            "QtyOnHand": format_qty(qty_on_hand),
            "QtyOnPo": format_qty(qty_on_po),
            "QtyOnIssues": format_qty(qty_on_issues),
            "OtherWarehouses": other_warehouses,
            "Sprays": [
                {
                    "SprayId": s.SprayId
                    , "SprayHDate": s.SprayHDate if s.SprayHDate else None
                    , "SprayNo": s.SprayHNo
                    , "TotalQty": s.TotalQty
                } for s in sprays]
        }
        print(product)

        return jsonify(product)

    except Exception as e:
        print(f"Error fetching product: {e}")
        return jsonify({"error": "Failed to fetch product"}), 500
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
    """Get upcoming demand grouped by time periods"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Get spray stock requirements with product details
        base_sql = """
        SELECT 
            StockId,
            STK.StockCode, STK.StockDescription,
            WhseId, STK.QtyOnPO,

            -- Qty needed THIS WEEK
            SUM(CASE 
                WHEN SprayHDate >= CAST(GETDATE() AS DATE)
                AND SprayHDate < DATEADD(WEEK, 1, CAST(GETDATE() AS DATE))
                THEN TotalQty 
                ELSE 0 
            END) AS QtyThisWeek,

            -- Qty needed NEXT WEEK
            SUM(CASE 
                WHEN SprayHDate >= DATEADD(WEEK, 1, CAST(GETDATE() AS DATE))
                AND SprayHDate < DATEADD(WEEK, 2, CAST(GETDATE() AS DATE))
                THEN TotalQty 
                ELSE 0 
            END) AS QtyNextWeek,

            -- Qty needed THIS MONTH
            SUM(CASE 
                WHEN MONTH(SprayHDate) = MONTH(GETDATE())
                AND YEAR(SprayHDate) = YEAR(GETDATE())
                THEN TotalQty 
                ELSE 0 
            END) AS QtyThisMonth,

            -- Qty on hand (same per product/warehouse)
            MAX(QtyAvailable) AS QtyAvailable

        FROM agr._uvSprayStockRequirements QTY
        JOIN stk._uvInventoryQty STK on STK.StockLink = QTY.StockId
        """

        params = []
        if warehouse_id is not None:
            base_sql += "\n WHERE WhseId = ?"
            params.append(warehouse_id)

        base_sql += "\n GROUP BY StockId, WhseId, STK.StockCode, STK.StockDescription, STK.QtyOnPO\n ORDER BY StockId;"

        cursor.execute(base_sql, tuple(params))

        results = cursor.fetchall()

        # Group by time periods
        this_week_items = []
        next_week_items = []
        this_month_items = []

        for row in results:
            stock_link = row.StockId
            stock_code = row.StockCode
            description = row.StockDescription
            qty_this_week = format_qty(row.QtyThisWeek)
            qty_next_week = format_qty(row.QtyNextWeek)
            qty_this_month = format_qty(row.QtyThisMonth)
            qty_available = format_qty(row.QtyAvailable)
            qty_on_po = format_qty(row.QtyOnPO)

            # Determine status for each period
            def get_status(required, available, on_po):
                if required <= available:
                    return 'sufficient'
                elif on_po >= (required - available):
                    return 'short_on_order'
                else:
                    return 'short_need_order'

            # This week demand
            if qty_this_week > 0:
                status = get_status(qty_this_week, qty_available, qty_on_po)
                this_week_items.append({
                    "StockLink": stock_link,
                    "StockCode": stock_code,
                    "StockDescription": description,
                    "Required": qty_this_week,
                    "Available": qty_available,
                    "OnPO": qty_on_po,
                    "Status": status
                })

            # Next week demand
            if qty_next_week > 0:
                status = get_status(qty_next_week, qty_available, qty_on_po)
                next_week_items.append({
                    "StockLink": stock_link,
                    "StockCode": stock_code,
                    "StockDescription": description,
                    "Required": qty_next_week,
                    "Available": qty_available,
                    "OnPO": qty_on_po,
                    "Status": status
                })

            # This month demand (excluding already counted weeks)
            remaining_monthly = format_qty(qty_this_month - qty_this_week - qty_next_week)
            if remaining_monthly > 0:
                status = get_status(remaining_monthly, qty_available, qty_on_po)
                this_month_items.append({
                    "StockLink": stock_link,
                    "StockCode": stock_code,
                    "StockDescription": description,
                    "Required": remaining_monthly,
                    "Available": qty_available,
                    "OnPO": qty_on_po,
                    "Status": status
                })

        demand_groups = [
            {
                "label": "This Week",
                "items": this_week_items[:10]  # Limit to top 10
            },
            {
                "label": "Next Week",
                "items": next_week_items[:10]
            },
            {
                "label": "This Month",
                "items": this_month_items[:10]
            }
        ]

        # Remove empty groups
        demand_groups = [group for group in demand_groups if group["items"]]

        return demand_groups

    except Exception as e:
        print(f"Error fetching upcoming demand: {e}")
        return []
    finally:
        close_db_connection(conn)

def get_warehouse_stock(warehouse_id=None):
    """Get warehouse stock levels for all items"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Query warehouse stock levels using the inventory view
        base_sql = """
            SELECT
                StockLink,
                StockCode,
                StockDescription,
                COALESCE(QtyOnHand, 0) as Available,
                cCategoryName as Category,
                COALESCE(IncompleteIssuesQty, 0) as TempIssues,
                COALESCE(QtyOnPo, 0) as OnPO,
                0 as OtherWH,
                CASE
                    WHEN COALESCE(QtyOnHand, 0) < ReorderLevel THEN ReorderQty
                    ELSE 0
                END as ToOrder,
                WhseLink,
                WhseCode,
                WhseName
            FROM stk._uvInventoryQty
        """

        params = []
        if warehouse_id is not None:
            base_sql += "\n            WHERE WhseLink = ?"
            params.append(warehouse_id)

        base_sql += "\n            ORDER BY StockCode"

        cursor.execute(base_sql, tuple(params))

        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            # Normalize numeric fields to avoid infinite decimal noise
            for k in ("Available", "TempIssues", "OnPO", "ToOrder"):
                if k in row_dict:
                    row_dict[k] = format_qty(row_dict[k])
            results.append(row_dict)

        return results

    except Exception as e:
        print(f"Error fetching warehouse stock: {e}")
        return []
    finally:
        close_db_connection(conn)


def get_warehouse_list():
    """Get warehouses available for the current user"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        wh_list = current_user.warehouses if hasattr(current_user, 'warehouses') and current_user.warehouses else []
        if not wh_list:
            return []

        # Use parameterized IN list
        params = ','.join(['?'] * len(wh_list))
        cursor.execute(f"""
            SELECT DISTINCT WhseLink, WhseCode, WhseName
            FROM stk._uvInventoryQty
            WHERE WhseLink IN ({params})
            ORDER BY WhseName, WhseCode
        """, tuple(wh_list))

        rows = cursor.fetchall()
        return [
            {
                'WhseLink': row.WhseLink,
                'WhseCode': row.WhseCode,
                'WhseName': row.WhseName,
            }
            for row in rows
        ]

    except Exception as e:
        print(f"Error fetching warehouse list: {e}")
        return []
    finally:
        close_db_connection(conn)