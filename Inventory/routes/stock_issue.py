
import sys
from flask import request, jsonify, render_template
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required
# Add the path to your Evolution DLLs
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")  # <-- replace with your DLL folder

# Load Evolution DLLs
clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")

# Import classes
import Pastel.Evolution as evo

@inventory_bp.route("/SDK/stock_issue", methods=["GET"])
@login_required
def stock_issue():
    return render_template('EvolutionSDK/stock_issue.html')

@inventory_bp.route("/SDK/fetch_warehouses")
def fetch_warehouses():
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select Distinct WhseLink, WhseCode, WhseName from _uvInventoryQty
    """)
    suppliers = [
        {"id": row[0], "code": row[1], "name": row[2]}
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"suppliers": suppliers})

@inventory_bp.route("/fetch_projects", methods=["POST"])
def fetch_projects():

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("Select ProdUnitCode, ProdUnitName from _uvProject")

    rows = cursor.fetchall()
    conn.close()

    projects_list = [
        {
            "code": row[0],
            "name": row[1],
        }
        for row in rows
    ]
    print("Products fetched:", projects_list)
    return jsonify({"prod_projects": projects_list})

@inventory_bp.route("/fetch_products_in_whse", methods=["POST"])
def fetch_products_in__whse():
    whse_code = request.json.get("whse_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT StockCode, StockDescription, QtyOnHand, StockingUnitCode
    FROM _uvInventoryQty 
    WHERE QtyOnHand > 0 And WhseCode = ?
    """, (whse_code,))

    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_id": row[0],
            "product_desc": row[1],
            "qty_in_whse": row[2],
            "uom": row[3]
        }
        for row in rows
    ]
    print("Products fetched:", products_list)
    return jsonify({"products": products_list})

@inventory_bp.route("/SDK/submit_stock_issue", methods=["POST"])
def submit_stock_issue():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        warehouse_code = data.get("warehouse")
        project_code = data.get("project")
        issued_by = data.get("issued_by")
        lines = data.get("lines", [])

        if not warehouse_code or not project_code or not issued_by or not lines:
            return jsonify({"status": "error", "message": "Missing required data"}), 400

        # -------------------------
        # Connect to Evolution
        # -------------------------
        evo.DatabaseContext.CreateCommonDBConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
        )
        evo.DatabaseContext.SetLicense("DE12111082", "9824607")
        evo.DatabaseContext.CreateConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
        )

        # -------------------------
        # Create Sales Order (Stock Issue)
        # -------------------------
        SO = evo.SalesOrder()
        SO.Customer = evo.Customer("ZZZ001")  # Always the same customer
        SO.Project = evo.Project(project_code)  # From frontend

        # Add each line
        for line in lines:
            OD = evo.OrderDetail()
            SO.Detail.Add(OD)

            OD.InventoryItem = evo.InventoryItem(line["product_id"])
            OD.Quantity = float(line["qty_to_issue"])
            OD.Warehouse = evo.Warehouse(warehouse_code)

        # Complete the Sales Order
        SO.Complete()

        return jsonify({"status": "success", "message": "Stock issue submitted."}), 200

    except Exception as ex:
        print("Stock Issue Error:", str(ex))
        return jsonify({"status": "error", "message": "Stock Issue Error: " + str(ex)}), 500
