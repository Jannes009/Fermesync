
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from Core.auth import create_db_connection, close_db_connection
from Inventory.routes import inventory_bp
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
from Inventory.routes.notifications import emit_event, send_notification
from datetime import datetime
from System import DateTime

@inventory_bp.route("/grv")
@login_required
def grv_summary():
    return render_template(
        "EvolutionSDK/grv_summary.html"
    )


@inventory_bp.route("/grv/<po_number>")
@login_required
def grv_details(po_number):
    return render_template(
        "EvolutionSDK/grv_details.html",
        po_number=po_number
    )



@inventory_bp.route("/SDK/fetch_outstanding_po_suppliers")
def fetch_outstanding_po_suppliers():
    # supplier endpoint removed — supplier dropdown no longer used
    return jsonify({"suppliers": []})


@inventory_bp.route("/get_po_numbers", methods=["POST"])
def get_po_numbers():
    data = request.get_json(silent=True) or {}
    supplier_code = data.get("supplier_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    # If a supplier_code is provided, filter by it; otherwise return POs across all warehouses
    if supplier_code:
        query = f"""
        SELECT DISTINCT DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl
        FROM [stk]._uvPO_Outstanding
        WHERE DcLink = ? AND WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
        """
        params = [supplier_code] + current_user.warehouses
    else:
        query = f"""
        SELECT DISTINCT DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl
        FROM [stk]._uvPO_Outstanding
        WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
        """
        params = list(current_user.warehouses)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    po_list = [
        {
            "supplier_code": row[0],
            "supplier_name": row[1],
            "order_num": row[2],
            "order_date": row[3],
            "order_desc": row[4],
            "order_total": row[5]
        }
        for row in rows
    ]

    return jsonify({"po_list": po_list})

@inventory_bp.route("/SDK/fetch_po_lines/<po_number>")
def fetch_po_lines(po_number):
    conn = create_db_connection()
    cursor = conn.cursor()

    query = f"""
        SELECT iLineID, iStockCodeID, StockDesc, WHName, QtyOutstanding, fUnitPriceExcl, UnitCode
        FROM [stk]._uvPO_Outstanding
        WHERE OrderNum = ? and WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
    """
    cursor.execute(query, [po_number] + current_user.warehouses)
    rows = cursor.fetchall()
    conn.close()

    po_lines = [
        {
            "LineId": row[0],
            "StockId": row[1],
            "StockDesc": row[2],
            "WHName": row[3],
            "QtyOutstanding": float(row[4]),
            "Price": float(row[5]),
            "UOM": row[6]
        }
        for row in rows
    ]
    return jsonify({"po_lines": po_lines})


from win32com.client import Dispatch
from flask import request, jsonify
import clr  # pythonnet
import sys

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route("/submit_grv", methods=["POST"])
def submit_grv():
    if "GRV_CREATE" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.get_json()

    po_number = data.get("poNumber")
    supplierRef = data.get("supplierRef")
    lines = data.get("lines")  # list of { ProductId, QtyReceived }
    print(po_number, supplierRef, lines)

    # -------------------------
    # Basic validation
    # -------------------------
    if not po_number:
        return jsonify({"success": False, "error": "PoNumber is required"}), 400

    if not lines or not isinstance(lines, list) or len(lines) == 0:
        return jsonify({"success": False, "error": "Lines collection required"}), 400

    try:
        with EvolutionConnection():
            PO = Evo.PurchaseOrder(po_number)
            PO.SupplierInvoiceNo = supplierRef
            PO.InvoiceDate = DateTime.Now

            for line in lines:
                if "lineId" not in line or "qty" not in line:
                    print("Skipping invalid line:", line)
                    continue
                qty_received = float(line["qty"])

                # Loop through Evolution PO Lines
                for detail in PO.Detail:
                    if str(detail.Index) == str(line["lineId"]):
                        detail.ToProcess = qty_received
                        break

            PO.ProcessStock()
            # audit_trail = PO.GetAuditTrail()
            grv_number = PO.Reference
            audit_number = PO.Audit
            print("Evo processed")
            
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO [stk].GRV (GRVUserId, GRVPONumber, GRVNumber, GRVAuditNumber, GRVSuppRef)
            VALUES (?, ?, ?, ?, ?)
        """, (current_user.id,  po_number, grv_number, audit_number, supplierRef))
        conn.commit()
        conn.close()

        print("Emitting event")
        emit_event(
            event_code="GRV_CREATE",
            entity_id=grv_number,
            entity_desc="Goods Received Voucher"
        )
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
    