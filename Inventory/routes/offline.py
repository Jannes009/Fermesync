from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort

@inventory_bp.route("/fetch_warehouses") 
def fetch_warehouses(): 
    try:
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
        return jsonify({"success": True, "warehouses": warehouses})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/fetch_projects", methods=["POST", "GET"])
@login_required
def fetch_projects():
    try:
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
        return jsonify({"success": True, "prod_projects": projects_list})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/fetch_products", methods=["GET"])
@login_required
def fetch_products():

    try:
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
                "product_link": row[0],
                "product_code": row[1],
                "product_desc": row[2],
                "WhseLink": row[3],
                "WhseCode": row[4],
                "WhseName": row[5],
                "qty_in_whse": row[6],
                "stocking_uom_id": row[7],
                "stocking_uom_code": row[8],
                "purchase_uom_id": row[9],
                "purchase_uom_code": row[10],
                "uom_cat_id": row[11],
            }
            for row in rows
        ]
        return jsonify({"success": True, "products": products_list})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
