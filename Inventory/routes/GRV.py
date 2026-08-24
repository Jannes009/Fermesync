
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from Core.auth import create_db_connection, close_db_connection
from Inventory.routes import inventory_bp
from Core.sdk_connection import EvolutionConnection, EvolutionAgentNotFoundError, EvolutionConnectionError
import Pastel.Evolution as Evo
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



@inventory_bp.route("/get_po_numbers", methods=["POST"])
def get_po_numbers():
    data = request.get_json(silent=True) or {}
    supplier_code = data.get("supplier_code")

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # If a supplier_code is provided, filter by it; otherwise return POs across all warehouses
        if supplier_code:
            query = f"""
                 SELECT DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl,
                     CASE WHEN MIN(ISNULL(fUnitPriceExcl, 0)) <= 0 THEN 1 ELSE 0 END AS HasZeroCost
            FROM [stk]._uvPO_Outstanding
            WHERE DcLink = ? AND WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
                 GROUP BY DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl
            """
            params = [supplier_code] + current_user.warehouses
        else:
            query = f"""
                 SELECT DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl,
                     CASE WHEN MIN(ISNULL(fUnitPriceExcl, 0)) <= 0 THEN 1 ELSE 0 END AS HasZeroCost
            FROM [stk]._uvPO_Outstanding
            WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
                 GROUP BY DcLink, SupplierName, OrderNum, OrderDate, OrderDesc, OrdTotIncl
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
                "order_total": row[5],
                "has_zero_cost": bool(row[6])
            }
            for row in rows
        ]

        return jsonify({"success": True, "po_list": po_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@inventory_bp.route("/SDK/fetch_po_lines/<po_number>")
def fetch_po_lines(po_number):
    try:
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
        return jsonify({"success": True, "po_lines": po_lines})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


from win32com.client import Dispatch
from flask import request, jsonify
import clr  # pythonnet
import sys

from Core.sdk_connection import EvolutionConnection
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

    line_ids = [line.get("lineId") for line in lines if line.get("lineId") is not None]
    if len(line_ids) != len(lines):
        return jsonify({"success": False, "error": "Every submitted line must have a line ID"}), 400

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(line_ids))
        cursor.execute(
            f"""
            SELECT iLineID, StockDesc, ISNULL(fUnitPriceExcl, 0)
            FROM [stk]._uvPO_Outstanding
            WHERE OrderNum = ?
              AND iLineID IN ({placeholders})
              AND WhseLink IN ({','.join(['?'] * len(current_user.warehouses))})
            """,
            [po_number] + line_ids + list(current_user.warehouses)
        )
        zero_cost_lines = [row[1] for row in cursor.fetchall() if float(row[2] or 0) <= 0]
        conn.close()
        if zero_cost_lines:
            return jsonify({
                "success": False,
                "error": "Cannot submit a GRV containing lines with zero cost: " + ", ".join(zero_cost_lines)
            }), 400
    except Exception as ex:
        if 'conn' in locals() and conn:
            conn.close()
        return jsonify({"success": False, "error": str(ex)}), 400

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
    