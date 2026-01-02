import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required, current_user
from auth import get_common_db_connection, close_connection
from Inventory.routes.db_conversions import stock_link_to_code
from datetime import datetime


from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
import System
from System import DateTime

@inventory_bp.route("/create_po")
def create_po():
    conn = create_db_connection()
    cursor = conn.cursor()

    # -------------------------
    # Header UDFs (grouped by page)
    # -------------------------
    cursor.execute("""
        SELECT
            cFieldName,
            cFieldDescription,
            iFieldType,
            cLookupOptions,
            bForceValue,
            cDefaultValue,
            cPageName
        FROM [UB_UITDRAAI_BDY].dbo._rtblUserDict
        WHERE cTableName = 'INVNUM'
          AND cFieldName LIKE '%POrd%'
        ORDER BY cPageName, cFieldName
    """)

    header_udfs = {}
    for row in cursor.fetchall():
        page = row.cPageName or "General"
        header_udfs.setdefault(page, []).append({
            "name": row.cFieldName,
            "label": row.cFieldDescription,
            "type": row.iFieldType,
            "lookup": row.cLookupOptions,
            "required": bool(row.bForceValue),
            "default": row.cDefaultValue
        })

    # -------------------------
    # Line UDFs
    # -------------------------
    cursor.execute("""
        SELECT
            cFieldName,
            cFieldDescription,
            iFieldType,
            cLookupOptions,
            bForceValue,
            cDefaultValue
        FROM [UB_UITDRAAI_BDY].dbo._rtblUserDict
        WHERE cTableName = '_btblInvoiceLines'
          AND cFieldName LIKE '%POrd%'
        ORDER BY cFieldName
    """)

    line_udfs = [{
        "name": row.cFieldName,
        "label": row.cFieldDescription,
        "type": row.iFieldType,
        "lookup": row.cLookupOptions,
        "required": bool(row.bForceValue),
        "default": row.cDefaultValue
    } for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "po_create.html",
        header_udfs=header_udfs,
        line_udfs=line_udfs
    )


@inventory_bp.route("/fetch_distinct_products", methods=["GET"])
@login_required
def fetch_distinct_products():
    
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT Distinct StockLink, StockCode, StockDescription
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
        }
        for row in rows
    ]
    return jsonify({"products": products_list})


@inventory_bp.route("/fetch_item_uom_warehouse")
def fetch_item_uom_warehouse():
    product_link = request.args.get("product_link")
    print(product_link)
    if not product_link:
        return jsonify({"error": "Missing product_link"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    # Base inventory flags
    cursor.execute("""
        SELECT DISTINCT
            bUOMItem,
            WhseItem,
            PurchaseUnitId,
            PurchaseUnitCatId
        FROM _uvInventoryQty
        WHERE StockLink = ?
    """, product_link)

    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    result = {
        "bUOMItem": int(row.bUOMItem),
        "WhseItem": int(row.WhseItem),
        "PurchaseUnitId": row.PurchaseUnitId,
        "PurchaseUnitCatId": row.PurchaseUnitCatId,
        "uoms": [],
        "warehouses": []
    }

    # Fetch UOMs if UOM item
    if row.bUOMItem == 1:
        cursor.execute("""
            SELECT idUnits, cUnitCode
            FROM [dbo].[_uvUOM]
            WHERE iUnitCategoryID = ?
        """, row.PurchaseUnitCatId)

        result["uoms"] = [
            {"id": u.idUnits, "code": u.cUnitCode}
            for u in cursor.fetchall()
        ]

    conn.close()
    return jsonify(result)

@inventory_bp.route("/fetch_suppliers")
def fetch_suppliers():
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT DISTINCT DCLink, Name
    FROM _uvSuppliers
    """)
    suppliers = [
        {"id": row[0], "name": row[1]}
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"suppliers": suppliers})

@inventory_bp.route("/po/requisition/save", methods=["POST"])
@login_required
def save_po_requisition():
    conn = create_db_connection()
    cursor = conn.cursor()
    print(dict(request.form))
    try:
        # -------------------------
        # HEADER
        # -------------------------
        cursor.execute("""
            INSERT INTO PO_RequisitionHeader (
                SupplierCode, OrderDate, DueDate,
                Description, CreatedByUserId, STATUS
            )
            OUTPUT INSERTED.Id
            VALUES (?, ?, ?, ?, ?, 'SUBMITTED')
        """, (
            request.form["supplier"],
            request.form["order_date"],
            request.form["due_date"],
            request.form.get("description"),
            current_user.id
        ))

        requisition_id = cursor.fetchone()[0]

        # -------------------------
        # HEADER UDFS
        # -------------------------
        for field, value in request.form.items():
            if field.__contains__("IDPOrd") and value != '':  # your UDF naming rule
                cursor.execute("""
                    INSERT INTO PO_RequisitionUdf (
                        RequisitionId, Scope, FieldName, FieldValue
                    )
                    VALUES (?, 'HEADER', ?, ?)
                """, (requisition_id, field, value))

        # -------------------------
        # LINES
        # -------------------------
        product_links = request.form.getlist("inventory-item[]")
        qtys = request.form.getlist("qty[]")
        prices = request.form.getlist("price[]")
        uoms = request.form.getlist("uom[]")
        warehouses = request.form.getlist("warehouse[]")
        projects = request.form.getlist("project[]")
        print(warehouses, product_links, qtys, prices, uoms, projects)
        line_ids = []

        for i, product_link in enumerate(product_links):
            product_code = stock_link_to_code(product_link, cursor)
            cursor.execute("""
                INSERT INTO PO_RequisitionLine (
                    RequisitionId, LineIndex, ProductId, ProductCode,
                    Quantity, Price, UomId, WarehouseId, ProjectId
                )
                OUTPUT INSERTED.LineId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                requisition_id,
                i + 1,
                product_link,
                product_code,
                qtys[i],
                prices[i],
                get_value(uoms, i),
                get_value(warehouses, i),
                projects[i]
            ))

            line_ids.append(cursor.fetchone()[0])

        # -------------------------
        # LINE UDFS (data-driven)
        # -------------------------
        for field in request.form:
            if not field.endswith("[]"):
                continue

            field_name = field[:-2]  # strip []
            values = request.form.getlist(field)

            # Only treat known line UDFs
            if not field_name.__contains__("IDPOrd") or value == '':
                continue

            for idx, value in enumerate(values):
                if not value:
                    continue

                cursor.execute("""
                    INSERT INTO PO_RequisitionUdf (
                        RequisitionId,
                        LineId,
                        Scope,
                        FieldName,
                        FieldValue
                    )
                    VALUES (?, ?, 'LINE', ?, ?)
                """, (
                    requisition_id,
                    line_ids[idx],
                    field_name,
                    value
                ))



        conn.commit()
        return {"success": True, "id": requisition_id}

    except Exception as e:
        conn.rollback()
        raise

    finally:
        conn.close()

def get_value(lst, idx):
    try:
        val = lst[idx]
        return val if val != "" else None
    except IndexError:
        return None




@inventory_bp.route("/debug/po", methods=["GET"])
def create_purchase_order():
    with EvolutionConnection():
        # -------------------------
        # Create Purchase Order
        # -------------------------
        PO = Evo.PurchaseOrder()
        PO.Supplier = Evo.Supplier("AAR001")
        PO.OrderDate = DateTime.Now
        PO.DueDate = DateTime.Now
        PO.Description = "desc"

        # User Defined Field
        PO.SetUserField("ulIDPOrdOrderedBy", "Louise")

        # -------------------------
        # Add Order Line
        # -------------------------
        OD = Evo.OrderDetail()
        PO.Detail.Add(OD)

        OD.InventoryItem = Evo.InventoryItem(5997)   # StockLink / ID
        OD.Quantity = 1
        OD.UnitSellingPrice = 1
        OD.Project = Evo.Project("M01-AAR-24")
        OD.Warehouse = Evo.Warehouse("CHE-000")

        # -------------------------
        # Save Purchase Order
        # -------------------------
        PO.Save()

        # Correct property name
        order_number = PO.OrderNo

        return order_number
