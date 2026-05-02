from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort

@inventory_bp.route("/fetch_warehouses") 
def fetch_warehouses(): 
    conn = create_db_connection() 
    cursor = conn.cursor() 
    query = f""" 
    Select WhseLink, WhseCode, WhseDescription
    from cmn.[_uvWarehouses] 
    WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
    """ 
    cursor.execute(query, current_user.warehouses)
    print(current_user.warehouses)
    warehouses = [ 
        {"id": row[0], "code": row[1], "name": row[2]} 
        for row in cursor.fetchall() ] 
    conn.close() 
    return jsonify({"warehouses": warehouses})

@inventory_bp.route("/fetch_projects", methods=["POST", "GET"])
@login_required
def fetch_projects():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT ProjectLink, ProjectCode, ProjectName
        FROM cmn._uvProject
        WHERE MainProjectLink IN ({','.join(['?'] * len(current_user.projects))}) 
    """, current_user.projects)
    rows = cursor.fetchall()
    conn.close()

    projects_list = [
        {"id": row[0], "code": row[1], "name": row[2]}
        for row in rows
    ]
    return jsonify({"prod_projects": projects_list})

@inventory_bp.route("/fetch_products", methods=["GET"])
@login_required
def fetch_products():
    
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT StockLink, StockCode, StockDescription,
        WhseLink, WhseCode, WhseName, QtyOnHand
        ,StockingUnitId, StockingUnitCode
        ,PurchaseUnitId, PurchaseUnitCode
        ,PurchaseUnitCatId
        FROM [stk]._uvInventoryQty 
        WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
    """, current_user.warehouses)
    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_link": row.StockLink,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "WhseLink": row.WhseLink,
            "WhseCode": row.WhseCode,
            "WhseName": row.WhseName,
            "qty_in_whse": row.QtyOnHand,
            "stocking_uom_id": row.StockingUnitId,
            "stocking_uom_code": row.StockingUnitCode,
            "purchase_uom_id": row.PurchaseUnitId,
            "purchase_uom_code": row.PurchaseUnitCode,
            "uom_cat_id": row.PurchaseUnitCatId,
        }
        for row in rows
    ]
    return jsonify({"products": products_list})
