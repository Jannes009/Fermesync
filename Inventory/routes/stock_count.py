import requests
from flask import request, jsonify, render_template
from . import inventory_bp
from Inventory.db import create_db_connection
from flask_login import current_user
from flask_login import login_required

@inventory_bp.route('/SDK/stock_count', methods=['GET'])
@login_required
def IBT_stock_count():
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

@inventory_bp.route("/create_inventory_count", methods=["POST"])
def create_inventory_count():
    whse_code = request.json.get("whse_code")
    category_name = request.json.get("category_name")
    count_storeman = request.json.get("count_storeman")

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

    cursor.execute("""
    INSERT INTO [InventoryCountHeaders] (
        [InvCountWhseId]
        ,[InvCountWhseCode]
        ,[InvCountTimeCreated]
        ,[InvCountUserId]
        ,[InvCountUserName]
        ,[InvCountStoreManName]
        )
    (
    Select WhseLink, Code WhseCode, GETDATE() DateStmpCreated, (?), (?), (?)
    from [UB_UITDRAAI_BDY].[dbo].[WhseMst] WH
    where Wh.Code = ?
    )

    INSERT INTO [InventoryCountLines] (
    [InvCountLineHeaderId] ,
    [InvCountStockId],
    [InvCountStockCode],
    [InvCountStockDesc],
    [InvCountQtyOnHand]
    )
    (
    Select 
        (
        Select MAX([InvCountHeaderId]) from [InventoryCountHeaders]
        where NOT EXISTS (Select * from [dbo].[InventoryCountLines] where InvCountLineHeaderId = [InvCountHeaderId])
        )HeaderID
        ,StockLInk, StockCode ,StockDescription ,QtyOnHand
        
    from [dbo].[_uvInventoryQty]
    where WhseCode = ? and cCategoryName = ?
    )
    """, (current_user.id, current_user.username, count_storeman, whse_code, whse_code, category_name,))
    conn.commit()
    cursor.execute("Select MAX([InvCountHeaderId]) from [InventoryCountHeaders]")
    stock_count_id = cursor.fetchone()[0]

    print("Products fetched:", products_list)
    conn.close()
    return jsonify({"products": products_list, "stock_count_id": stock_count_id})

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
    data = request.get_json()
    

    stock_count_id = data.get("stock_count_id")
    warehouse = data.get("warehouse")
    category = data.get("category")
    products = data.get("products", [])

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE [dbo].[InventoryCountHeaders]
        SET InvCountTimeFinalised = GETDATE()
    WHERE InvCountHeaderId = ?
    """, (stock_count_id,))

    try:
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

        for item in products:
            product_code = item["product_code"]
            system_qty = float(item["system_qty"])
            counted_qty = float(item["counted_qty"])
            difference = counted_qty - system_qty

            cursor.execute("""
            UPDATE [dbo].[InventoryCountLines]
                SET InvCountQtyCounted = ?
            WHERE InvCountLineHeaderId = ? AND InvCountStockCode = ?
            """, (counted_qty, stock_count_id, product_code,))

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
        conn.commit()
        return jsonify({
            "success": True,
            "message": "Stock adjustments completed successfully",
            "adjustments": results
        })

    except Exception as ex:
        print("Stock Count Error:", str(ex))
        return jsonify({"success": False, "error": str(ex)}), 500
