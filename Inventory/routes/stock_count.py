import requests
from flask import request, jsonify, render_template, abort
from . import inventory_bp
from Inventory.db import create_db_connection
from flask_login import current_user
from flask_login import login_required
from datetime import datetime

@inventory_bp.route('/SDK/stock_count', methods=['GET'])
@login_required
def IBT_stock_count():
    if "StockCount" not in current_user.permissions:
        abort(403)  # Forbidden
    return render_template('EvolutionSDK/stock_count.html')

@inventory_bp.route("/fetch_categories", methods=["POST"])
def fetch_categories():
    whse_code = request.json.get("whse_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select Distinct cCategoryName
    from [dbo].[_uvInventoryQty]
    where cCategoryName is not null
    and WhseCode = ?
    """, (whse_code,))

    rows = cursor.fetchall()

    conn.close()

    categories_list = [
        {
            "category_name": row[0]
        }
        for row in rows
    ]
    print("Products fetched:", categories_list)
    return jsonify({"products": categories_list})


@inventory_bp.route("/fetch_inventory_count_products", methods=["POST"])
def fetch_inventory_count_products():
    whse_code = request.json.get("whse_code")
    category_name = request.json.get("category_name")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select StockCode, StockDescription, QtyOnHand 
    ,StockingUnitCode
    from _uvInventoryQty
    Where WhseCode = ? and cCategoryName = ?
    """, (whse_code, category_name,))

    rows = cursor.fetchall()
    products_list = [
        {
            "product_code": row[0],
            "product_desc": row[1],
            "qty_in_whse": row[2],
            "stock_unit": row[3],
        }
        for row in rows
    ]

    conn.close()
    
    # Add current timestamp
    current_time = datetime.now().isoformat()  # Returns ISO format like "2024-01-15T14:30:45.123456"
    
    return jsonify({
        "products": products_list,
        "opening_timestamp": current_time
    })

import sys
from flask import request, jsonify
import clr  # pythonnet

# Add the path to your Evolution DLLs
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")  # <-- replace with your DLL folder

# Load Evolution DLLs
clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")

# Import classes
from Pastel.Evolution import DatabaseContext
from Pastel.Evolution import InventoryTransaction, InventoryItem, TransactionCode, InventoryOperation, Module, Warehouse
@inventory_bp.route("/submit_stock_count", methods=["POST"])
def submit_stock_count():
    if "GRV" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.get_json()
    
    warehouse = data.get("warehouse")
    category = data.get("category")
    products = data.get("products", [])
    counted_by = data.get("counted_by")
    opening_timestamp = data.get("count_start_timestamp")

    # Convert to SQL Server compatible format (YYYY-MM-DD HH:MM:SS)
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(opening_timestamp.replace('Z', '+00:00'))
        sql_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        # Fallback to current time if conversion fails
        sql_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = create_db_connection()
    cursor = conn.cursor()
    
    try:
        # First, get the warehouse ID
        cursor.execute("SELECT WhseLink FROM _uvWarehouses WHERE WhseCode = ?", (warehouse,))
        whse_result = cursor.fetchone()
        if not whse_result:
            return jsonify({"success": False, "error": "Warehouse not found"}), 400
        whse_id = whse_result[0]

        # Insert the header and get the stock_count_id in separate steps
        cursor.execute("""
            INSERT INTO [InventoryCountHeaders] (
                [InvCountWhseId],
                [InvCountWhseCode],
                [InvCountUserId],
                [InvCountUserName],
                [InvCountCountedBy],
                [InvCountCatName],
                [InvCountTimeCreated]
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (whse_id, warehouse, current_user.id, current_user.username, counted_by, category, sql_timestamp,))
        
        # Now get the SCOPE_IDENTITY() in a separate query
        cursor.execute("""
        Select MAX(InvCountHeaderId) InvCountHeaderId
        from [dbo].[InventoryCountHeaders] HEA
        WHERE NOT EXISTS (Select * from [InventoryCountLines] LIN where LIN.InvCountLineHeaderId = HEA.InvCountHeaderId)
         """)
        stock_count_id = cursor.fetchone()[0]
        
        # -------------------------
        # Connect to Evolution
        # -------------------------
        DatabaseContext.CreateCommonDBConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
        )
        DatabaseContext.SetLicense("DE12111082", "9824607")
        DatabaseContext.CreateConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
        )

        results = []
        print(products)

        for item in products:
            product_code = item["product_code"]
            system_qty = float(item["system_qty"])
            counted_qty = float(item["counted_qty"])
            difference = counted_qty - system_qty

            # Fix: Correct column names in INSERT statement
            cursor.execute("""
                INSERT INTO [InventoryCountLines] (
                    [InvCountLineHeaderId],
                    [InvCountLineStockCode],
                    [InvCountLineQtyOnHand],
                    [InvCountLineQtyCounted]
                ) VALUES (?, ?, ?, ?)
            """, (stock_count_id, product_code, system_qty, counted_qty))

            if difference == 0:
                continue  # No adjustment needed

            # -------------------------
            # Build Inventory Transaction
            # -------------------------
            trans = InventoryTransaction()
            trans.TransactionCode = TransactionCode(Module.Inventory, "ADJ")
            trans.InventoryItem = InventoryItem(product_code)

            # Increase or decrease?
            if difference > 0:
                trans.Operation = InventoryOperation.Increase
                trans.Quantity = difference
            else:
                trans.Operation = InventoryOperation.Decrease
                trans.Quantity = abs(difference)

            # Optional metadata
            trans.Reference = f"STOCKTAKE-{warehouse}"
            trans.Reference2 = category or ""
            trans.Description = f"Stocktake Adjustment ({counted_qty} counted, {system_qty} in system)"
            trans.Warehouse = Warehouse(warehouse)

            # Save into Evolution
            trans.Post()
            print(f"Posted adjustment for {product_code}: qty {difference}")

            results.append({
                "product_code": product_code,
                "adjusted_by": difference,
                "status": "posted"
            })
        
        # Commit all the line items
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Stock adjustments completed successfully",
            "adjustments": results
        })

    except Exception as ex:
        conn.rollback()
        print("Stock Count Error:", str(ex))
        return jsonify({"success": False, "error": str(ex)}), 500
    finally:
        cursor.close()
        conn.close()