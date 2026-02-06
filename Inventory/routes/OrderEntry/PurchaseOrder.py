import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import stock_link_to_code, supplier_link_to_code, unit_link_to_code

from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
import System
from System import DateTime


@inventory_bp.route("/po/purchase_order/<int:order_id>/update", methods=["POST"])
@login_required
def update_purchase_order(order_id):
    data = request.json
    print(data, order_id, file=sys.stderr)

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    Select TOP 1 OrderNum from inventory._uvPO_Outstanding
	Where AutoIndex = ?
    """, order_id)
    order_no = cursor.fetchone().OrderNum
    conn.close()
    edit_purchase_order(
        order_no=order_no,
        header=data["header"],
        lines=data["lines"],
        header_udfs=data["header_udfs"]
    )

    return {"success": True}


def edit_purchase_order(order_no, header, lines, header_udfs):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        with EvolutionConnection():
            PO = Evo.PurchaseOrder(order_no)

            # -------------------------
            # Header
            # -------------------------
            supplier = supplier_link_to_code(header["supplier"], cursor)
            PO.Supplier = Evo.Supplier(supplier)
            PO.OrderDate = DateTime.Now
            PO.DueDate = DateTime.Now
            PO.Description = header.get("description", "")

            # -------------------------
            # Header UDFs
            # -------------------------
            for field_name, field_value in header_udfs.items():
                PO.SetUserField(field_name, field_value)

            # -------------------------
            # Lines
            # -------------------------
            for line in list(PO.Detail):
                line.Delete()

            for line in lines:
                OD = Evo.OrderDetail()
                PO.Detail.Add(OD)

                OD.InventoryItem = Evo.InventoryItem(int(line["product_id"]))
                OD.Quantity = float(line["qty"])
                OD.UnitSellingPrice = float(line["price"])

                if line.get("project_id"):
                    OD.Project = Evo.Project(int(line["project_id"]))

                if line.get("warehouse_id"):
                    OD.Warehouse = Evo.Warehouse(int(line["warehouse_id"]))

                if line.get("uom_id"):
                    OD.Unit = Evo.Unit(int(line["uom_id"]))
                print(line.get("udf", {}))
                for field_name, field_value in line.get("udf", {}).items():
                    print(field_name, field_value)
                    OD.SetUserField(field_name, field_value)

            PO.Save()
            return PO.OrderNo
    finally:
        conn.close()


def create_purchase_order(header, lines, header_udfs, line_udfs):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        with EvolutionConnection():
            PO = Evo.PurchaseOrder()

            # -------------------------
            # Header
            # -------------------------
            supplier = supplier_link_to_code(header["SupplierId"], cursor)
            PO.Supplier = Evo.Supplier(supplier)
            PO.OrderDate = DateTime.Now
            PO.DueDate = DateTime.Now
            PO.Description = header.get("Description", "")

            # -------------------------
            # Header UDFs
            # -------------------------
            for field_name, field_value in header_udfs.items():
                PO.SetUserField(field_name, field_value)

            # -------------------------
            # Lines
            # -------------------------
            for line in lines:
                OD = Evo.OrderDetail()
                PO.Detail.Add(OD)

                OD.InventoryItem = Evo.InventoryItem(line["ProductId"])
                OD.Quantity = line["Quantity"]
                OD.UnitSellingPrice = line["Price"]

                if line.get("ProjectId"):
                    OD.Project = Evo.Project(line["ProjectId"])

                if line.get("WarehouseId"):
                    OD.Warehouse = Evo.Warehouse(line["WarehouseId"])

                if line.get("UomId"):
                    unit_code = unit_link_to_code(line["UomId"], cursor)
                    OD.Unit = Evo.Unit(unit_code)


                # Line UDFs
                for field_name, field_value in line_udfs.get(line["LineId"], {}).items():
                    OD.SetUserField(field_name, field_value)

            # -------------------------
            # Save
            # -------------------------
            PO.Save()
            return PO.OrderNo
    finally:
        conn.close()

@inventory_bp.route("/api/po/<int:po_id>")
@login_required
def fetch_purchase_order(po_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    # ---------- HEADER ----------
    cursor.execute("""
    Select DISTINCT DCLink SupplierId, OrderDate, DueDate, OrderDesc Description
    from [inventory].[_uvPurchaseOrders]
    Where  AutoIndex = ?
    """, po_id)
    header = cursor.fetchone()
    if not header:
        abort(404)

    # ---------- HEADER UDFS ----------
    cursor.execute("""
    Select cFieldName, UserValue
    from [inventory].[_uvPurchaseOrderHeaderUDFs]
    Where AutoIndex = ?
    """, po_id)
    header_udfs = {
        row.cFieldName: row.UserValue
        for row in cursor.fetchall()
    }

    # ---------- LINES ----------
    cursor.execute("""
    Select iLineID LineId, iStockCodeID ProductId,  fQuantity Quantity, fQtyProcessed QtyProcessed, fUnitPriceExcl Price
    ,ProjectId, UomId, WhseLink WarehouseId
    from inventory.[_uvPurchaseOrders]
    Where AutoIndex = ?
    """, po_id)
    lines = cursor.fetchall()

    # ---------- LINE UDFS ----------
    cursor.execute("""
    SELECT
        U.idInvoiceLines LineId,
        U.FieldName,
        U.FieldValue
    FROM inventory.._uvPurchaseOrderLineUDFs U
    JOIN inventory.._uvPurchaseOrders L
        ON L.iLineID = U.idInvoiceLines
    WHERE L.AutoIndex = ?
    """, po_id)
    line_udfs_map = {}

    for row in cursor.fetchall():
        line_udfs_map.setdefault(row.LineId, {})[row.FieldName] = row.FieldValue


    conn.close()

    return jsonify({
        "header": row_to_dict(header),
        "header_udfs": header_udfs,
        "lines": [row_to_dict(l) for l in lines],
        "line_udfs": line_udfs_map
    })

 
def row_to_dict(row):
    if row is None:
        return None
    return {
        column[0]: getattr(row, column[0])
        for column in row.cursor_description
    }