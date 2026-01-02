from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort

@inventory_bp.route("/fetch_warehouses") 
def fetch_warehouses(): 
    conn = create_db_connection() 
    cursor = conn.cursor() 
    query = f""" 
    Select WhseLink, WhseCode, WhseDescription
    from [_uvWarehouses] 
    WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
    """ 
    cursor.execute(query, current_user.warehouses)
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
    cursor.execute("SELECT ProjectLink, ProjectCode, ProjectName FROM _uvProject")
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
        FROM _uvInventoryQty 
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


@inventory_bp.route("/SDK/incomplete_issues", methods=["GET"])
def incomplete_issues():
    conn = create_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT Distinct IssueId, IssueTimeStamp, ProjectName, IssueToName, IssueWhseId
        FROM [dbo].[_uvStockIssue]
        WHERE IssueFinalised = 0
        ORDER BY IssueId, IssueTimeStamp, ProjectName, IssueToName
    """

    cur.execute(sql)
    rows = cur.fetchall()

    # build grouped structure: one issue → many lines
    issues = [{
        "IssueId": r.IssueId,
        "IssueTimeStamp": r.IssueTimeStamp,
        "ProjectName": r.ProjectName,
        "IssueToName": r.IssueToName,
        "WhseId": r.IssueWhseId,
        "isReturned": False,
        "lines": []
    } for r in rows
    ]

    return jsonify({"issues": issues})


@inventory_bp.route("/SDK/incomplete_issue_lines", methods=["GET"])
def incomplete_issue_lines():
    if "StockIssue" not in current_user.permissions:
        abort(403)  # Forbidden

    results = []
    conn = None
    cursor = None
    try:
        conn = create_db_connection()
        if conn is None:
            return jsonify([]), 500

        cursor = conn.cursor()
        cursor.execute("""  
        Select IssueId, IssLineId, IssLineStockLink, StockDescription, 
                IssLineUOMID, ISSLineUOMCode, ISSLineQtyIssued 
        from [_uvStockIssue]
        Where IssLineQtyFinalised Is NULL
        """)

        rows = cursor.fetchall()
        results = [{
            "header_id": r.IssueId,
            "line_id": r.IssLineId,
            "product_link": r.IssLineStockLink,
            "product_desc": r.StockDescription,
            "uom_id": r.IssLineUOMID,
            "uom_code": r.ISSLineUOMCode,
            "qty_issued": r.ISSLineQtyIssued
        } for r in rows]
    except Exception as e:
        print("fetch_products_for_return error:", e)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # return {"issue_lines": results}
    return jsonify({"issue_lines": results})