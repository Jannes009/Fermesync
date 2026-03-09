from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from datetime import datetime

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route("/warehouse-transfer")
@login_required
def warehouse_transfer_page():
    return render_template("warehouse_transfer.html")

# AJAX save
@inventory_bp.route("/warehouse-transfer/save", methods=["POST"])
@login_required
def warehouse_transfer_save():

    data = request.json

    from_whse = data["fromWarehouse"]
    to_whse = data["toWarehouse"]
    lines = data["lines"]

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO [stk].WarehouseTransferH
        (TransferHFromWarehouseId, TransferHToWarehouseId, TransferHCreatedBy)
        OUTPUT INSERTED.IdTransferH
        VALUES (?, ?, ?)
    """, from_whse, to_whse, current_user.id)
    transfer_id = cursor.fetchone()[0]

    with EvolutionConnection():

        for line in lines:

            cursor.execute("""
                INSERT INTO [stk].WarehouseTransferL
                (TransferLineHeaderId, TransferLineStockId, TransferLineQty)
                VALUES (?, ?, ?)
            """, transfer_id, line["stockId"], line["qty"])

            WT = Evo.WarehouseTransfer()
            WT.FromWarehouse = Evo.Warehouse(int(from_whse))
            WT.ToWarehouse = Evo.Warehouse(int(to_whse))
            WT.Account = Evo.InventoryItem(int(line["stockId"]))
            WT.Quantity = float(line["qty"])
            WT.Description = f"Warehouse Transfer {transfer_id} by {current_user.username} on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            WT.Reference = f"WT{transfer_id}"
            WT.Post()

    conn.commit()
    close_db_connection(conn)

    return jsonify({"success": True})