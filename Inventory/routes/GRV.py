
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from Core.auth import create_db_connection, close_db_connection
from Inventory.routes import inventory_bp
from Core.sdk_connection import EvolutionConnection, EvolutionAgentNotFoundError, EvolutionConnectionError
import Pastel.Evolution as Evo
from datetime import datetime
from System import DateTime

def _can_view_grv_history():
    return "GRV_HIST" in (current_user.permissions or [])


@inventory_bp.route("/grv")
@login_required
def grv_summary():
    return render_template(
        "EvolutionSDK/grv_summary.html",
        can_view_history=_can_view_grv_history()
    )


@inventory_bp.route("/grv/<po_number>")
@login_required
def grv_receive(po_number):
    return render_template(
        "EvolutionSDK/grv_receive.html",
        po_number=po_number
    )


@inventory_bp.route("/grv/history", methods=["GET"])
@login_required
def grv_history():
    if not _can_view_grv_history():
        abort(403)

    warehouses = list(current_user.warehouses or [])
    if not warehouses:
        return jsonify({"success": True, "orders": []})

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    state = request.args.get("state")
    warehouse_placeholders = ",".join(["?"] * len(warehouses))
    query = f"""
         SELECT OrderNum, MAX(OrderDate), MAX(SupplierName), MAX(SupplierAccount),
             MAX(WarehouseName), MAX(Description), MAX(OrdTotIncl), MAX(DocState), MAX(DocStateText)
        FROM [stk]._uvPurchaseOrders
        WHERE iWarehouseID IN ({warehouse_placeholders})
    """
    params = list(warehouses)
    if start_date:
        query += " AND OrderDate >= ?"
        params.append(start_date)
    if end_date:
        query += " AND OrderDate < DATEADD(day, 1, ?)"
        params.append(end_date)
    if state:
        try:
            params.append(int(state))
        except ValueError:
            return jsonify({"success": False, "error": "Invalid order state"}), 400
        query += " AND DocState = ?"
    query += " GROUP BY OrderNum ORDER BY MAX(OrderDate) DESC, OrderNum DESC"

    conn = None
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        orders = [
            {
                "order_num": row[0],
                "order_date": row[1].isoformat() if row[1] else None,
                "supplier_name": row[2],
                "supplier_account": row[3],
                "warehouse_name": row[4],
                "description": row[5],
                "order_total": float(row[6] or 0),
                "state": int(row[7]) if row[7] is not None else 0,
                "state_text": row[8]
            }
            for row in cursor.fetchall()
        ]
        return jsonify({"success": True, "orders": orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@inventory_bp.route("/grv/history/<po_number>", methods=["GET"])
@login_required
def grv_history_detail_page(po_number):
    if not _can_view_grv_history():
        abort(403)

    return render_template(
        "EvolutionSDK/grv_history_detail.html",
        po_number=po_number
    )


@inventory_bp.route("/grv/history/<po_number>/data", methods=["GET"])
@login_required
def grv_history_detail(po_number):
    if not _can_view_grv_history():
        abort(403)

    warehouses = list(current_user.warehouses or [])
    if not warehouses:
        return jsonify({"success": False, "error": "Purchase order not found"}), 404

    warehouse_placeholders = ",".join(["?"] * len(warehouses))
    query = f"""
         SELECT OrderNum, OrderDate, SupplierName, SupplierAccount, Description,
               OrdTotIncl, DocState, DocStateText, cDescription, fQuantity,
             fQtyProcessed, UnitCode, fUnitPriceIncl, WarehouseName, GrvNumber
        FROM [stk]._uvPurchaseOrders
        WHERE OrderNum = ? AND iWarehouseID IN ({warehouse_placeholders})
        ORDER BY iLineID
    """
    conn = None
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, [po_number] + warehouses)
        rows = cursor.fetchall()
        if not rows:
            return jsonify({"success": False, "error": "Purchase order not found"}), 404

        header = rows[0]
        cursor.execute(f"""
                SELECT WhseName, Description_1, TxDate, DTStamp, Reference,
                                UserName, Qty, UNIT.StockingUnitCode UnitCode, UnitCost, ProjectCode
                FROM cmn._uvStockTransactions TRN
                JOIN [cmn].[_uvStockUnits] UNIT on UNIT.StockLink = TRN.StockLink
                WHERE WhseLink IN ({warehouse_placeholders}) and Order_No = ?
                ORDER BY TxDate DESC, DTStamp DESC
        """, warehouses + [po_number])
        transaction_rows = cursor.fetchall()

        return jsonify({
            "success": True,
            "order": {
                "order_num": header[0],
                "order_date": header[1].isoformat() if header[1] else None,
                "supplier_name": header[2],
                "supplier_account": header[3],
                "description": header[4],
                "order_total": float(header[5] or 0),
                "state": int(header[6]) if header[6] is not None else 0,
                "state_text": header[7],
                "lines": [
                    {
                        "description": row[8],
                        "quantity": float(row[9] or 0),
                        "processed": float(row[10] or 0),
                        "unit_code": row[11],
                        "unit_price": float(row[12] or 0),
                        "warehouse_name": row[13]
                    }
                    for row in rows
                ],
                "transactions": [
                    {
                        "warehouse_name": row[0],
                        "description": row[1],
                        "tx_date": row[2].isoformat() if row[2] else None,
                        "timestamp": row[3].isoformat() if row[3] else None,
                        "reference": row[4],
                        "user_name": row[5],
                        "quantity": float(row[6] or 0),
                        "unit_code": row[7],
                        "unit_cost": float(row[8] or 0),
                        "project_code": row[9]
                    }
                    for row in transaction_rows
                ]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()



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
    