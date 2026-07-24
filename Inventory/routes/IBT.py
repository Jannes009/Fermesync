import requests
from flask import request, jsonify, render_template
from . import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Instance.config import DEFAULT_TRANSFER_PROJECT_ID

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route('/SDK/IBT_issue', methods=['GET'])
@login_required
def IBT_issue():
    return render_template('EvolutionSDK/IBT_issue.html')

@inventory_bp.route("/SDK/fetch_all_warehouses") 
def fetch_all_warehouses(): 
    conn = create_db_connection() 
    cursor = conn.cursor() 
    query = f""" 
    Select WhseLink, WhseCode, WhseDescription
    from cmn.[_uvWarehouses] 
    """ 
    cursor.execute(query) 
    warehouses = [ 
        {"id": row[0], "code": row[1], "name": row[2]} 
        for row in cursor.fetchall() ] 
    conn.close() 
    return jsonify({"warehouses": warehouses})


@inventory_bp.route("/fetch_products_in_both_whses", methods=["POST"])
def fetch_products_in_both_whses():
    whse_from_id = request.json.get("whse_from_id")
    whse_to_id = request.json.get("whse_to_id")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT FROMQTY.StockLink FromStockLink,
           FROMQTY.StockDescription,
           FROMQTY.QtyOnHand / CONV.ConversionFactor PurchaseQtyOnHand,
           FROMQTY.PurchaseUnitId,
           FROMQTY.PurchaseUnitCode,
           CONV.iUOMStockingUnitID,
           CONV.StockingUnitCode,
           CONV.ConversionFactor
    FROM [stk]._uvInventoryQty FROMQTY
    JOIN [cmn].[_uvStockUnitConversion] CONV on CONV.StockLink = FROMQTY.StockLink
    WHERE EXISTS(
        SELECT StockLink ToStockLink
        FROM [stk]._uvInventoryQty TOQTY
        WHERE TOQTY.WhseLink = ? AND TOQTY.StockLink = FROMQTY.StockLink
    )
    AND FROMQTY.QtyOnHand > 0 AND FROMQTY.WhseLink = ? AND FROMQTY.ItemActive = 1
    """, (whse_to_id, whse_from_id,))

    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_id": row.FromStockLink,
            "product_desc": row.StockDescription,
            "qty_in_whse": row.PurchaseQtyOnHand,
            "purchasing_unit_id": row.PurchaseUnitId,
            "purchasing_unit_code": row.PurchaseUnitCode,
            "stocking_unit_id": row.iUOMStockingUnitID,
            "stocking_unit_code": row.StockingUnitCode,
            "conversion_factor": row.ConversionFactor
        }
        for row in rows
    ]
    return jsonify({"products": products_list})

import sys
from flask import request, jsonify
import clr  # pythonnet

@inventory_bp.route("/submit_ibt", methods=["POST"])
def submit_ibt():
    data = request.get_json()

    try:
        with EvolutionConnection():
            ibt = Evo.WarehouseIBT()
            ibt.WarehouseFrom = Evo.Warehouse(int(data["WarehouseFrom"]))
            ibt.WarehouseTo = Evo.Warehouse(int(data["WarehouseTo"]))
            ibt.Description = current_user.username + " IBT"
            ibt.Project = Evo.Project(DEFAULT_TRANSFER_PROJECT_ID)  # Set the project for the IBT

            for l in data["Lines"]:
                line = Evo.WarehouseIBTLine()
                line.InventoryItem = Evo.InventoryItem(int(l["ProductId"]))
                line.QuantityIssued = l["QtyIssued"]
                print("QtyIssued:", l["QtyIssued"])
                line.Description = "IBT line issued via SDK"
                line.Reference = current_user.username
                ibt.Detail.Add(line)

            ibt.IssueStock()

        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO [stk].[IBT](
        [IBTId],
        [IBTDispatchUserId],
        [IBTDispatchTimeStamp],
        [IBTNo],
        [IBTDispatchAuditNo]
        )VALUES(?,?,GETDATE(),?,?)
        """, (ibt.ID, current_user.id, ibt.Number, ibt.AuditNumberIssued))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "IBT successfully created",
            "ibtNumber": ibt.Number,
            "ibtId": ibt.ID
        })

    except Exception as e:
        print("ERROR DURING IBT CREATION:", str(e))

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


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

    warehouses = current_user.warehouses
    if len(warehouses) == 0:
        return jsonify({"ibts": []})
    placeholders = ",".join(["?"] * len(warehouses))
    cursor.execute(f"""
    Select Distinct IDWhseIBT, cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
    from [stk].[_uvIBTSummary]
    Where StatusID = 1 AND ToWhseLink IN ({placeholders})
    """, warehouses)
    ibts = [
        {
            "ibt_id": row.IDWhseIBT,
            "ibt_number": row.cIBTNumber,
            "description": row.cIBTDescription,
            "warehouse_from": row.FromWhseName,
            "warehouse_to": row.ToWhseName
        }
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"ibts": ibts})

@inventory_bp.route("/display_ibt", methods=["GET"])
def display_ibt():
    ibt_id = request.args.get("ibt_id")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select 
    IDWhseIBT, cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
    ,IDWhseIBTLines
    ,IBT.StockLink, StockDesc ,cDescription, cReference, fQtyIssued,
    CONV.StockingUnitCode, CONV.PurchasingUnitCode, CONV.ConversionFactor
    from [stk].[_uvIBTSummary] IBT
	JOIN [cmn].[_uvStockUnitConversion] CONV on CONV.StockLink = IBT.StockLink
    Where StatusID = 1 and IDWhseIBT = ?
    """, (ibt_id,))

    rows = cursor.fetchall()
    conn.close()

    ibt_details = [
        {
            "ibt_id": row.IDWhseIBT,
            "ibt_number": row.cIBTNumber,
            "description": row.cIBTDescription,
            "warehouse_from": row.FromWhseName,
            "warehouse_to": row.ToWhseName,
            "ibt_line_id": row.IDWhseIBTLines,
            "product_id": row.StockLink,
            "product_desc": row.StockDesc,
            "line_description": row.cDescription,
            "line_reference": row.cReference,
            "qty_issued": row.fQtyIssued,
            "stocking_unit_code": row.StockingUnitCode,
            "purchasing_unit_code": row.PurchasingUnitCode,
            "conversion_factor": row.ConversionFactor
        }
        for row in rows
    ]
    return jsonify({"ibt_details": ibt_details})

@inventory_bp.route("/submit_ibt_receive", methods=["POST"])
def submit_ibt_receive():
    try:
        data = request.get_json()
        ibt_id = data.get("ibt_id")

        with EvolutionConnection():
            ibt = Evo.WarehouseIBT(int(ibt_id))

            for line_data in data.get("lines", []):
                matched = False
                line_id = line_data.get("ibt_line_id")
                for ibt_line in ibt.Detail:
                    if ibt_line.ID == int(line_id):
                        print(line_data.get("QuantityReceived"), line_data.get("QuantityVariance"))
                        ibt_line.QuantityReceived = line_data.get("QuantityReceived")
                        ibt_line.QuantityVariance = line_data.get("QuantityVariance")
                        ibt_line.Description = line_data.get("Description", "")
                        ibt_line.Reference = line_data.get("Reference", "")
                        matched = True
                        break
                if not matched:
                    missing_id = line_id if line_id is not None else line_data.get("InventoryItemID")
                    return jsonify({"success": False, "message": f"IBT line not found for line id {missing_id}"}), 400

            ibt.ReceiveStock()
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE [stk].[IBT]
        SET [IBTRecUserId] = ?, [IBTRecTimeStamp] = GETDATE(),
        [IBTRecAuditNo] = ?
        WHERE [IBTId] = ?
        """, (current_user.id, ibt.AuditNumberReceived, ibt_id))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "IBT successfully received",
            "ibtNumber": ibt.Number
        })

    except Exception as e:
        print("Error submitting IBT receive:", str(e))
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500
