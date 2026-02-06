from flask import request, jsonify, render_template, abort
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Inventory.routes.db_conversions import stock_link_to_code
from Inventory.routes.OrderEntry.PurchaseOrder import create_purchase_order


def load_po_udf_metadata():
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
    return header_udfs, line_udfs

@inventory_bp.route("/create_po")
def create_po():
    if not "PO_REQUISITION_CREATE" or not "PO_CREATE" in current_user.permissions:
        abort(403)
    header_udfs, line_udfs = load_po_udf_metadata()

    return render_template(
        "po_form.html",
        mode="create",
        header_udfs=header_udfs,
        line_udfs=line_udfs
    )

@inventory_bp.route("/po/requisition/<int:requisition_id>")
@login_required
def view_po_requisition(requisition_id):
    if not "PO_CREATE" or not "PO_EDIT" in current_user.permissions:
        abort(403)
    header_udfs, line_udfs = load_po_udf_metadata()
    cursor = create_db_connection().cursor()
    cursor.execute("SELECT Status FROM inventory.PO_RequisitionHeader WHERE Id = ?", requisition_id)
    status = cursor.fetchone()
    if not status:
        cursor.execute("Select Count(AutoIndex) as cnt from [inventory].[_uvPO_Outstanding] Where AutoIndex = ?", requisition_id)
        cnt = cursor.fetchone()
        if cnt.cnt == 0:
            abort(404)
        status = "POSTED"
    else:
        status = status.Status
    cursor.connection.close()
    return render_template(
        "po_form.html",
        mode="view",
        header_udfs=header_udfs,
        line_udfs=line_udfs,
        form_id=requisition_id,
        status=status
    )


@inventory_bp.route("/fetch_distinct_products", methods=["GET"])
@login_required
def fetch_distinct_products():
    
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT Distinct StockLink, StockCode, StockDescription
        FROM inventory._uvInventoryQty 
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
        FROM inventory._uvInventoryQty
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
            FROM [common].[_uvUOM]
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
    FROM common_uvSuppliers
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
    data = request.json
    print(data)
    
    try:
        # -------------------------
        # HEADER
        # -------------------------
        cursor.execute("""
            INSERT INTO inventory.PO_RequisitionHeader (
                SupplierId, OrderDate, DueDate,
                Description, CreatedByUserId, STATUS
            )
            OUTPUT INSERTED.Id
            VALUES (?, ?, ?, ?, ?, 'PENDING APPROVAL')
        """, (
            data["header"]["supplier"],
            data["header"]["order_date"],
            data["header"]["due_date"],
            data["header"]["description"],
            current_user.id
        ))

        requisition_id = cursor.fetchone()[0]

        # -------------------------
        # HEADER UDFS
        # -------------------------
        for field_name, field_value in data.get("header_udfs", {}).items():
            if field_value:
                cursor.execute("""
                    INSERT INTO inventory.PO_RequisitionUdf (
                        RequisitionId, Scope, FieldName, FieldValue
                    )
                    VALUES (?, 'HEADER', ?, ?)
                """, (requisition_id, field_name, field_value))

        # -------------------------
        # LINES
        # -------------------------
        line_ids = []
        for i, line_data in enumerate(data.get("lines", [])):
            product_link = line_data["product_id"]
            product_code = stock_link_to_code(product_link, cursor)
            
            cursor.execute("""
                INSERT INTO inventory.PO_RequisitionLine (
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
                line_data.get("qty") or None,
                line_data.get("price") or None,
                line_data.get("uom_id") or None,
                line_data.get("warehouse_id") or None,
                line_data.get("project_id") or None
            ))
            
            line_ids.append(cursor.fetchone()[0])

        # -------------------------
        # LINE UDFS
        # -------------------------
        for i, line_data in enumerate(data.get("lines", [])):
            for field_name, field_value in line_data.get("udf", {}).items():
                if field_value:
                    cursor.execute("""
                        INSERT INTO inventory.PO_RequisitionUdf (
                            RequisitionId, LineId, Scope, FieldName, FieldValue
                        )
                        VALUES (?, ?, 'LINE', ?, ?)
                    """, (requisition_id, line_ids[i], field_name, field_value))

        conn.commit()
        if data.get("process"):
            return approve_requisition(requisition_id)
        return {"success": True, "id": requisition_id}

    except Exception as e:
        conn.rollback()
        print(e)
        raise

    finally:
        conn.close()

def get_value(lst, idx):
    try:
        val = lst[idx]
        return val if val != "" else None
    except IndexError:
        return None
    
@inventory_bp.route("/po/requisition/<int:requisition_id>/update", methods=["POST"])
@login_required
def update_po_requisition(requisition_id):
    data = request.json

    # -------------------------------
    # PHASE 1: DATABASE ONLY
    # -------------------------------
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT Status FROM inventory.PO_RequisitionHeader WHERE Id = ?",
            requisition_id
        )
        status = cursor.fetchone()[0]

        if status == "REJECTED":
            return {"success": False, "error": "Cannot edit a rejected requisition"}, 400

        # Header
        cursor.execute("""
            UPDATE inventory.PO_RequisitionHeader
            SET SupplierId = ?, OrderDate = ?, DueDate = ?, Description = ?
            WHERE Id = ?
        """, (
            data["header"]["supplier"],
            data["header"]["order_date"],
            data["header"]["due_date"],
            data["header"].get("description"),
            requisition_id
        ))

        # Header UDFs
        cursor.execute("""
            DELETE FROM inventory.PO_RequisitionUdf
            WHERE RequisitionId = ? AND Scope = 'HEADER'
        """, requisition_id)

        for k, v in data.get("header_udfs", {}).items():
            if v:
                cursor.execute("""
                    INSERT INTO inventory.PO_RequisitionUdf
                    (RequisitionId, Scope, FieldName, FieldValue)
                    VALUES (?, 'HEADER', ?, ?)
                """, (requisition_id, k, v))

        # Lines + line UDFs
        cursor.execute("""
            DELETE FROM inventory.PO_RequisitionUdf
            WHERE RequisitionId = ? AND Scope = 'LINE'
        """, requisition_id)

        cursor.execute("""
            DELETE FROM inventory.PO_RequisitionLine
            WHERE RequisitionId = ?
        """, requisition_id)

        for idx, line in enumerate(data["lines"], start=1):
            print(line, idx, requisition_id)
            product_code = stock_link_to_code(line["product_id"], cursor)
            cursor.execute("""
                INSERT INTO inventory.PO_RequisitionLine (
                    RequisitionId, LineIndex, ProductId, ProductCode,
                    Quantity, Price, UomId, WarehouseId, ProjectId
                )
                OUTPUT INSERTED.LineId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                requisition_id,
                idx,
                line["product_id"],
                product_code,
                line["qty"],
                line["price"],
                line["uom_id"],
                line["warehouse_id"],
                line["project_id"]
            ))

            line_id = cursor.fetchone()[0]

            for udf, val in line.get("udf", {}).items():
                if val:
                    cursor.execute("""
                        INSERT INTO inventory.PO_RequisitionUdf
                        (RequisitionId, LineId, Scope, FieldName, FieldValue)
                        VALUES (?, ?, 'LINE', ?, ?)
                    """, (requisition_id, line_id, udf, val))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
    return {"success": True}


@inventory_bp.route("/po/requisition/<int:requisition_id>/approve", methods=["POST"])
@login_required
def approve_requisition(requisition_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # ------------------------------------------------------------------
        # STATUS CHECK
        # ------------------------------------------------------------------
        cursor.execute("""
            SELECT Status
            FROM inventory.PO_RequisitionHeader
            WHERE Id = ?
        """, requisition_id)

        row = cursor.fetchone()
        if not row:
            abort(404)

        if row.Status != "PENDING APPROVAL":
            return {
                "success": False,
                "error": f"Cannot approve requisition in status '{row.Status}'"
            }, 400

        # ------------------------------------------------------------------
        # FETCH FULL REQUISITION DATA
        # ------------------------------------------------------------------
        requisition = fetch_po_requisition(requisition_id).get_json()

        header = requisition["header"]
        lines = requisition["lines"]
        header_udfs = requisition["header_udfs"]
        line_udfs = requisition["line_udfs"]

        # ------------------------------------------------------------------
        # CREATE PURCHASE ORDER IN EVOLUTION
        # ------------------------------------------------------------------
        order_no = create_purchase_order(
            header=header,
            lines=lines,
            header_udfs=header_udfs,
            line_udfs=line_udfs
        )

        # ------------------------------------------------------------------
        # UPDATE REQUISITION STATUS
        # ------------------------------------------------------------------
        cursor.execute("""
            UPDATE inventory.PO_RequisitionHeader
            SET Status = 'POSTED',
                ApprovedByUserId = ?,
                ApprovedAt = GETDATE(),
                PONumber = ?
            WHERE Id = ?
        """, (
            current_user.id,
            order_no,
            requisition_id
        ))

        conn.commit()
        return {"success": True, "order_no": order_no}

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


@inventory_bp.route("/po/requisition/<int:requisition_id>/reject", methods=["POST"])
@login_required
def reject_requisition(requisition_id):
    reason = request.json.get("reason")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE inventory.PO_RequisitionHeader
        SET Status = 'REJECTED',
            RejectedByUserId = ?,
            RejectedAt = GETDATE(),
            RejectionReason = ?
        WHERE Id = ? AND Status = 'PENDING APPROVAL'
    """, current_user.id, reason, requisition_id)

    conn.commit()
    conn.close()

    return {"success": True}


@inventory_bp.route("/api/po/requisition/<int:requisition_id>")
@login_required
def fetch_po_requisition(requisition_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    # ---------- HEADER ----------
    cursor.execute("SELECT * FROM inventory.PO_RequisitionHeader WHERE Id = ?", requisition_id)
    header = cursor.fetchone()
    if not header:
        abort(404)

    # ---------- HEADER UDFS ----------
    cursor.execute("""
        SELECT FieldName, FieldValue
        FROM inventory.PO_RequisitionUdf
        WHERE RequisitionId = ?
          AND Scope = 'HEADER'
    """, requisition_id)
    header_udfs = {
        row.FieldName: row.FieldValue
        for row in cursor.fetchall()
    }

    # ---------- LINES ----------
    cursor.execute("""
        SELECT * FROM inventory.PO_RequisitionLine
        WHERE RequisitionId = ?
        ORDER BY LineIndex
    """, requisition_id)
    lines = cursor.fetchall()

    # ---------- LINE UDFS ----------
    cursor.execute("""
        SELECT LineId, FieldName, FieldValue
        FROM inventory.PO_RequisitionUdf
        WHERE RequisitionId = ?
          AND Scope = 'LINE'
    """, requisition_id)
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

@inventory_bp.route("/po/last_invoice_price", methods=["POST"])
@login_required
def fetch_last_invoice_price():
    data = request.json
    supplier = data.get("supplier")
    product_link = data.get("product_link")
    uom_id = data.get("uom_id")
    if not product_link or not supplier or not uom_id:
        return jsonify({"error": "Product link, Supplier and UOM ID required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        Select fUnitPriceExcl, * from inventory._uvLastSupplierInvoicePrice
        Where AccountID = ? AND iStockCodeID = ? AND iUnitsOfMeasureID = ?
        """, (supplier, product_link, uom_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "error": "No price found"}), 404
        return jsonify({
            "success": True,
            "price": row.fUnitPriceExcl
        })
    except Exception as e:
        print(e)
        return jsonify({"success": False, "error": "Error fetching price"}), 500
    finally:
        conn.close()