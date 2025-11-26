
from flask_login import login_required, current_user
import requests
from flask import Blueprint, jsonify, current_app, request, render_template, abort
from datetime import datetime, timedelta
from Inventory.db import create_db_connection

from Inventory.routes import inventory_bp

@inventory_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    return render_template('dashboard.html')


@inventory_bp.route('/SDK/GRV', methods=['GET'])
@login_required
def GRV_page():
    # Permission check
    if "GRV" not in current_user.permissions:
        abort(403)  # Forbidden

    return render_template('EvolutionSDK/GRV.html')


@inventory_bp.route("/SDK/fetch_suppliers")
def po_page():
    conn = create_db_connection()
    cursor = conn.cursor()

    warehouses = current_user.warehouses
    if len(warehouses) == 0:
        return jsonify({"suppliers": []})
    placeholders = ",".join(["?"] * len(warehouses))
    query = f"""
    SELECT DISTINCT DCLink, SupplierName
    FROM _uvPO_Outstanding
    WHERE WhseLink IN ({placeholders})
    """

    cursor.execute(query, warehouses)
    print(f"Executed query: {query} with warehouses: {warehouses}")
    suppliers = [
        {"code": row[0], "name": row[1]}
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"suppliers": suppliers})


@inventory_bp.route("/get_po_numbers", methods=["POST"])
def get_po_numbers():
    supplier_code = request.json.get("supplier_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    query = f"""
    SELECT DISTINCT OrderNum, OrderDate, OrderDesc, OrdTotIncl
    FROM _uvPO_Outstanding
    WHERE DcLink = ? and WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
    """
    cursor.execute(query, [supplier_code] + current_user.warehouses)

    rows = cursor.fetchall()
    conn.close()

    po_list = [
        {
            "order_num": row[0],
            "order_date": row[1],
            "order_desc": row[2],
            "order_total": row[3]
        }
        for row in rows
    ]

    return jsonify({"po_list": po_list})

@inventory_bp.route("/SDK/fetch_po_lines/<po_number>")
def fetch_po_lines(po_number):
    conn = create_db_connection()
    cursor = conn.cursor()

    query = f"""
        SELECT iStockCodeID, StockDesc, WHName, QtyOutstanding, fUnitPriceExcl, UnitCode
        FROM _uvPO_Outstanding
        WHERE OrderNum = ? and WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
    """
    cursor.execute(query, [po_number] + current_user.warehouses)
    rows = cursor.fetchall()
    conn.close()

    po_lines = [
        {
            "iStockCodeID": row[0],
            "StockDesc": row[1],
            "WHName": row[2],
            "QtyOutstanding": float(row[3]),
            "Price": float(row[4]),
            "UOM": row[5]
        }
        for row in rows
    ]

    return jsonify({"po_lines": po_lines})


from win32com.client import Dispatch
from flask import request, jsonify
import clr  # pythonnet
import sys

# Add the path to your Evolution DLLs
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")  # <-- replace with your DLL folder

# Load Evolution DLLs
clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")

# Import classes
from Pastel.Evolution import DatabaseContext
from Pastel.Evolution import PurchaseOrder

@inventory_bp.route("/submit_grv", methods=["POST"])
def submit_grv():
    if "GRV" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.get_json()

    po_number = data.get("poNumber")
    receiver = data.get("receiverName")
    lines = data.get("lines")  # list of { ProductId, QtyReceived }

    # -------------------------
    # Basic validation
    # -------------------------
    if not po_number:
        return jsonify({"success": False, "error": "PoNumber is required"}), 400

    if not lines or not isinstance(lines, list) or len(lines) == 0:
        return jsonify({"success": False, "error": "Lines collection required"}), 400

    for l in lines:
        if "ProductId" not in l or "QtyReceived" not in l:
            return jsonify({
                "success": False,
                "error": "Each line must contain ProductId and QtyReceived"
            }), 400

    try:
        # -------------------------
        # Connect to Evolution SDK
        # -------------------------
        DatabaseContext.CreateCommonDBConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
        )
        DatabaseContext.SetLicense("DE12111082", "9824607")
        DatabaseContext.CreateConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
        )

        # -------------------------
        # Load Purchase Order
        # -------------------------
        PO = PurchaseOrder(po_number)

        # -------------------------
        # Match lines to PO.Detail
        # -------------------------
        for line in lines:
            pid = str(line["ProductId"])
            qty_received = float(line["QtyReceived"])

            # Loop through Evolution PO Lines
            for detail in PO.Detail:
                if str(detail.InventoryItemID) == pid:
                    detail.ToProcess = qty_received
                    break

        # -------------------------
        # Process the GRV (same as C#: PO.ProcessStock())
        # -------------------------
        PO.ProcessStock()
        # audit_trail = PO.GetAuditTrail()
        grv_number = PO.Reference
        audit_number = PO.Audit
        
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO GRV (GRVUserId, GRVReceivedBy, GRVPONumber, GRVNumber, GRVAuditNumber)
            VALUES (?, ?, ?, ?, ?)
        """, (current_user.id,  receiver, po_number, grv_number, audit_number))
        conn.commit()
        conn.close()
        return jsonify({
            "success": True,
            "message": "GRV submitted successfully"
        })

    except Exception as ex:
        print("GRV Processing Error:", str(ex))
        return jsonify({
            "success": False,
            "error": str(ex)
        }), 400
