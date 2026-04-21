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
            QTY.cCategoryName,
            COALESCE(QTY.QtyOnHand, 0) AS QtyOnHand,
            COALESCE(QTY.QtyOnPo, 0) AS QtyOnPo, 
            COALESCE(QTY.IncompleteIssuesQty, 0) AS QtyOnIssues, 
            FN.SprayHWeek
        FROM stk._uvInventoryQty QTY
        LEFT JOIN FirstNegative FN 
            ON FN.SprayHWhseId = QTY.WhseLink 
            AND FN.SprayLineStkId = QTY.StockLink
            AND FN.rn = 1
        WHERE QTY.WhseLink = ?
        ORDER BY QTY.StockCode;
        """
        cursor.execute(query, (warehouse_id,))
        rows = cursor.fetchall()
        stock = [
            {
                "StockLink": r.StockLink,
                "StockCode": r.StockCode,
                "StockDescription": r.StockDescription,
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

@inventory_bp.route("/get-chemstock/<int:stock_link>")
@login_required
def get_chemstock(stock_link):
    """Get ChemStock data for a product"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT IdChemStock, ChemStockLink, ChemStockActiveIngr, ChemStockRegNumber,
                   ChemStockColourCodeId, ChemStockTypeId, ChemStockReason,
                   ChemStockWitholdingPeriod, ChemStockDefaultQtyPer100L
            FROM agr.ChemStock
            WHERE ChemStockLink = ?
        """, (stock_link,))
        
        row = cursor.fetchone()
        if row:
            chemstock = {
                "IdChemStock": row.IdChemStock,
                "ChemStockLink": row.ChemStockLink,
                "ChemStockActiveIngr": row.ChemStockActiveIngr,
                "ChemStockRegNumber": row.ChemStockRegNumber,
                "ChemStockColourCodeId": row.ChemStockColourCodeId,
                "ChemStockTypeId": row.ChemStockTypeId,
                "ChemStockReason": row.ChemStockReason,
                "ChemStockWitholdingPeriod": row.ChemStockWitholdingPeriod,
                "ChemStockDefaultQtyPer100L": row.ChemStockDefaultQtyPer100L
            }
            return jsonify(chemstock)
        else:
            return jsonify({"error": "ChemStock not found"}), 404

    except Exception as e:
        print(f"Error fetching ChemStock: {e}")
        return jsonify({"error": "Failed to fetch ChemStock"}), 500
    finally:
        close_db_connection(conn)

@inventory_bp.route("/update-chemstock/<int:stock_link>", methods=["POST"])
@login_required
def update_chemstock(stock_link):
    """Update ChemStock data"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        data = request.get_json()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE agr.ChemStock
            SET ChemStockActiveIngr = ?,
                ChemStockRegNumber = ?,
                ChemStockColourCodeId = ?,
                ChemStockTypeId = ?,
                ChemStockReason = ?,
                ChemStockWitholdingPeriod = ?,
                ChemStockDefaultQtyPer100L = ?
            WHERE ChemStockLink = ?
        """, (
            data.get("activeIngr"),
            data.get("regNumber"),
            data.get("colourCodeId"),
            data.get("typeId"),
            data.get("reason"),
            data.get("witholdingPeriod"),
            data.get("defaultQtyPer100L"),
            stock_link
        ))
        
        conn.commit()
        return jsonify({"success": True, "message": "ChemStock updated successfully"})

    except Exception as e:
        conn.rollback()
        print(f"Error updating ChemStock: {e}")
        return jsonify({"error": "Failed to update ChemStock"}), 500
    finally:
        close_db_connection(conn)

@inventory_bp.route("/get-reordering/<int:stock_link>")
@login_required
def get_reordering(stock_link):
    """Get reordering data (ReorderLevel, ReorderQty, Category)"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        warehouse_id = request.args.get('whse', type=int)
        cursor = conn.cursor()
        
        if warehouse_id:
            cursor.execute("""
                SELECT StockLink, ReorderLevel, ReorderQty, cCategoryName
                FROM stk._uvInventoryQty
                WHERE StockLink = ? AND WhseLink = ?
            """, (stock_link, warehouse_id))
        else:
            cursor.execute("""
                SELECT StockLink, ReorderLevel, ReorderQty, cCategoryName
                FROM stk._uvInventoryQty
                WHERE StockLink = ?
            """, (stock_link,))
        
        row = cursor.fetchone()
        if row:
            print(row)
            return jsonify({
                "ReorderLevel": row.ReorderLevel,
                "ReorderQty": row.ReorderQty,
                "Category": row.cCategoryName
            })
        else:
            return jsonify({"error": "Reordering data not found"}), 404

    except Exception as e:
        print(f"Error fetching reordering data: {e}")
        return jsonify({"error": "Failed to fetch reordering data"}), 500
    finally:
        close_db_connection(conn)

@inventory_bp.route("/update-reordering/<int:stock_link>", methods=["POST"])
@login_required
def update_reordering(stock_link):
    """Update reordering data via stored procedure"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        data = request.get_json()
        warehouse_id = data.get("warehouseId")
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO #StockIds (StockId)
            VALUES (?);  

            EXEC stk.sp_BulkUpdateStock
                @Category = ?,
                @ReorderLevel = ?,
                @ReorderQty = ?,
                @WarehouseId = ?
        """, (
            stock_link,
            data.get("category"),
            data.get("reorderLevel"),
            data.get("reorderQty"),
            warehouse_id
        ))
        
        conn.commit()
        return jsonify({"success": True, "message": "Reordering data updated successfully"})

    except Exception as e:
        conn.rollback()
        print(f"Error updating reordering data: {e}")
        return jsonify({"error": "Failed to update reordering data"}), 500
    finally:
        close_db_connection(conn)

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

 