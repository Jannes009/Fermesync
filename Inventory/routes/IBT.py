import requests
from flask import request, jsonify, render_template
from . import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required

@inventory_bp.route('/SDK/IBT_issue', methods=['GET'])
@login_required
def IBT_issue():
    return render_template('EvolutionSDK/IBT_issue.html')


@inventory_bp.route("/fetch_products_in_both_whses", methods=["POST"])
def fetch_products_in_both_whses():
    whse_from_code = request.json.get("whse_from_code")
    whse_to_code = request.json.get("whse_to_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT FROMQTY.StockCode FromStockCode, FROMQTY.StockDescription, FROMQTY.QtyOnHand
    FROM _uvInventoryQty FROMQTY
    WHERE  EXISTS(
        SELECT StockLink ToStckLink
        FROM _uvInventoryQty TOQTY
        where TOQTY.WhseCode = ? and TOQTY.StockLink = FROMQTY.StockLink
    )
    And FROMQTY.QtyOnHand > 0 And FROMQTY.WhseCode = ?
    """, (whse_to_code, whse_from_code,))

    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_id": row[0],
            "product_desc": row[1],
            "qty_in_whse": row[2]
        }
        for row in rows
    ]
    print("Products fetched:", products_list)
    return jsonify({"products": products_list})

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
from Pastel.Evolution import WarehouseIBT, WarehouseIBTLine, Warehouse, InventoryItem

@inventory_bp.route("/submit_ibt", methods=["POST"])
def submit_ibt():
    data = request.get_json()
    print(data)
    # -------------------------
    # 1. Connect to Evolution DB
    # -------------------------
    DatabaseContext.CreateCommonDBConnection(
        "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
    )
    DatabaseContext.SetLicense("DE12111082", "9824607")
    DatabaseContext.CreateConnection(
        "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
    )

    # -------------------------
    # 2. Create IBT
    # -------------------------
    ibt = WarehouseIBT()
    ibt.WarehouseFrom = Warehouse((data["WarehouseFrom"]))
    ibt.WarehouseTo = Warehouse(data["WarehouseTo"])
    ibt.Description = data.get("RequestedBy", "")

    for l in data["Lines"]:
        line = WarehouseIBTLine()
        line.InventoryItem = InventoryItem(l["ProductId"])
        line.QuantityIssued = l["QtyIssued"]
        line.Description = data.get("Dispatcher", "")
        line.Reference = data.get("Driver", "")
        ibt.Detail.Add(line)

    # Issue the IBT
    ibt.IssueStock()

    return jsonify({
        "success": True,
        "message": "IBT successfully created",
        "ibtNumber": ibt.Number
    })

# -------------------------
# IBT ISSUE END
# -------------------------

# IBT RECEIVE START
@inventory_bp.route("/SDK/IBT_receive", methods=["GET"])
def IBT_receive():
    return render_template('EvolutionSDK/IBT_receive.html')

@inventory_bp.route("/fetch_issued_ibts", methods=["GET"])
def fetch_issued_ibts():
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select Distinct cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
    from [dbo].[_uvIBTSummary]
    Where StatusID = 1
    """)
    ibts = [
        {
            "ibt_number": row[0],
            "description": row[1],
            "warehouse_from": row[2],
            "warehouse_to": row[3]
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"ibts": ibts})

@inventory_bp.route("/display_ibt", methods=["GET"])
def display_ibt():
    ibt_number = request.args.get("ibt_number")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select 
    cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
    ,StockLink, StockDesc ,cDescription, cReference, fQtyIssued
    from [dbo].[_uvIBTSummary]
    Where StatusID = 1 and cIBTNumber = ?
    """, (ibt_number,))

    rows = cursor.fetchall()
    conn.close()

    ibt_details = [
        {
            "ibt_number": row[0],
            "description": row[1],
            "warehouse_from": row[2],
            "warehouse_to": row[3],
            "product_code": row[4],
            "product_desc": row[5],
            "line_description": row[6],
            "line_reference": row[7],
            "qty_issued": row[8]
        }
        for row in rows
    ]

    return jsonify({"ibt_details": ibt_details})

@inventory_bp.route("/submit_ibt_receive", methods=["POST"])
def submit_ibt_receive():
    data = request.get_json()
    print("Received IBT receive data:", data)

    # -------------------------
    # 1. Connect to Evolution DB
    # -------------------------
    DatabaseContext.CreateCommonDBConnection(
        "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
    )
    DatabaseContext.SetLicense("DE12111082", "9824607")
    DatabaseContext.CreateConnection(
        "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
    )

    # -------------------------
    # 2. Load IBT to receive
    # -------------------------
    ibt = WarehouseIBT(data["ibt_number"])

    # -------------------------
    # 3. Update lines from JSON
    # -------------------------
    for line_data in data.get("lines", []):
        # Find the corresponding IBT line by InventoryItemID
        for ibt_line in ibt.Detail:
            if ibt_line.InventoryItemID == int(line_data["InventoryItemID"]):
                ibt_line.QuantityReceived = line_data.get("QuantityReceived")
                ibt_line.QuantityDamaged = line_data.get("QuantityDamaged")
                ibt_line.QuantityVariance = line_data.get("QuantityVariance")
                ibt_line.Description = line_data.get("Description", "")
                ibt_line.Reference = line_data.get("Reference", "")
                break  # Stop after matching line
            print("Updated IBT line:", ibt_line.InventoryItemID, ibt_line.QuantityReceived, ibt_line.QuantityDamaged, ibt_line.QuantityVariance)

    # -------------------------
    # 4. Commit the receive
    # -------------------------
    ibt.ReceiveStock()
    print("IBT received:", ibt.Number)

    return jsonify({
        "success": True,
        "message": "IBT successfully received",
        "ibtNumber": ibt.Number
    })
