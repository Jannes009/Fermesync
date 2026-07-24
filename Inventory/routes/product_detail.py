from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, render_template, abort, jsonify
from datetime import datetime
from .product_service import ProductService


def parse_date_param(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None


@inventory_bp.route('/product/<int:stock_link>')
@login_required
def product_detail(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    warehouse_id = request.args.get('whse', type=int)
    if warehouse_id is None:
        return 'Warehouse ID is required', 400

    service = ProductService()
    try:
        product = service.build_product_model(stock_link, warehouse_id)
        if not product:
            abort(404)
        product = service.format_for_template(product)
        warehouses = service.load_warehouse_selector(stock_link)
    finally:
        service.close()

    return render_template('product_detail.html', product=product, warehouse_id=warehouse_id, warehouses=warehouses)


@inventory_bp.route('/product/<int:stock_link>/transactions')
@login_required
def product_transaction_history(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    warehouse_id = request.args.get('whse', type=int)
    service = ProductService()
    try:
        transactions = service.load_transaction_rows(stock_link, warehouse_id=None, limit=None)
    finally:
        service.close()

    for txn in transactions:
        if isinstance(txn.get('TxDate'), datetime):
            txn['TxDate'] = txn['TxDate'].strftime('%Y-%m-%d')

    types = sorted({txn['TrnType'] for txn in transactions if txn.get('TrnType')})
    projects = sorted({txn['ProjectName'] for txn in transactions if txn.get('ProjectName')})
    users = sorted({txn['UserName'] for txn in transactions if txn.get('UserName')})
    warehouses = sorted({(txn['WhseLink'], txn['WhseCode']) for txn in transactions if txn.get('WhseLink')}, key=lambda wh: wh[1] or '')
    warehouse_list = [
        {'warehouse_id': wh[0], 'warehouse_code': wh[1]}
        for wh in warehouses
    ]

    return jsonify({
        'transactions': transactions,
        'types': types,
        'projects': projects,
        'users': users,
        'warehouses': warehouse_list,
        'default_warehouse_id': warehouse_id,
    })


@inventory_bp.route("/get-chemstock/<int:stock_link>")
@login_required
def get_chemstock(stock_link):
    """Get ChemStock data for a product with all associated crops"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
    SELECT  STK.ChemStockLink, ACT.ChemActIngredient, CRP.CropDescription, STKCRP.StkCrpRegNumber,
            CLR.ChemColCode, STKCRP.StkCrpType, STKCRP.StkCrpFunctionDef,
            STKCRP.StkCrpWitholdingPeriodDef
    FROM agr.ChemStock STK
    LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
    LEFT JOIN agr.ChemStockCrop STKCRP on STKCRP.StkCrpChemStockId = STK.IdChemStock
    LEFT JOIN agr.ChemColour CLR on CLR.IdChemCol = StK.ChemStockColourCodeId
    LEFT JOIN agr.Crop CRP on CRP.IdCrop = STKCRP.StkCrpCropId
    WHERE STK.ChemStockLink = ?
    ORDER BY CRP.CropDescription
        """, (stock_link,))
        rows = cursor.fetchall()
        if rows:
            first_row = rows[0]
            chemstock = {
                "ChemStockLink": first_row.ChemStockLink,
                "ChemStockActiveIngr": first_row.ChemActIngredient,
                "ChemStockColourCode": first_row.ChemColCode,
                "Crops": [
                    {
                        "CropDescription": row.CropDescription,
                        "RegNumber": row.StkCrpRegNumber,
                        "Type": row.StkCrpType,
                        "Function": row.StkCrpFunctionDef,
                        "WitholdingPeriod": row.StkCrpWitholdingPeriodDef
                    }
                    for row in rows
                ]
            }
            return jsonify(chemstock)
        return jsonify({"error": "ChemStock not found"}), 404
    except Exception as e:
        print(f"Error fetching ChemStock: {e}")
        return jsonify({"error": "Failed to fetch ChemStock"}), 500
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
        cursor.execute("""
            SELECT StockLink, ReorderLevel, ReorderQty, idStockCategories AS ItemCategoryID, cCategoryName
            FROM stk._uvInventoryQty
            WHERE StockLink = ? AND WhseLink = ?
        """, (stock_link, warehouse_id))
        row = cursor.fetchone()
        if row:
            return jsonify({
                "ReorderLevel": row.ReorderLevel,
                "ReorderQty": row.ReorderQty,
                "CategoryId": getattr(row, 'ItemCategoryID', None),
                "Category": row.cCategoryName
            })
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
        EXEC [stk].[sp_UpdateCategoryAndReordering]
            @StockId = ?,
            @Category = ?,
            @ReorderLevel = ?,
            @ReorderQty = ?,
            @WarehouseId = ?;
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


@inventory_bp.route("/categories")
@login_required
def get_categories():
    """Get all available product categories for a warehouse"""
    conn = create_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        warehouse_id = request.args.get('whse', type=int)
        if not warehouse_id:
            return jsonify({"error": "Warehouse ID is required"}), 400

        cursor = conn.cursor()
        cursor.execute("""
        Select ItemCategoryID, cCategoryName 
        from [stk].[_uvWarehouseCategories]
        Where WhseID = ?
        """, (warehouse_id,))
        rows = cursor.fetchall()
        categories = [{"category_id": r.ItemCategoryID, "category_name": r.cCategoryName} for r in rows]
        return jsonify({"status": "ok", "categories": categories})
    except Exception as e:
        print(f"Error fetching categories: {e}")
        return jsonify({"error": "Failed to fetch categories"}), 500
    finally:
        close_db_connection(conn)

