
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from Inventory.db import create_db_connection
from Inventory.routes import inventory_bp
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
from Inventory.routes.notifications import notify_user

@inventory_bp.route("/po-change/<int:request_id>", methods=["GET"])
@login_required
def po_change_review(request_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Header
    header = cursor.execute("""
        SELECT
            Id, PONumber, SupplierRef, ReceiverName,
            RequestedByUserId, RequestedAt, Status,
            ReviewedByUserId, ReviewedAt
        FROM POChangeRequest
        WHERE Id = ?
    """, (request_id,)).fetchone()

    if not header:
        abort(404)

    # Lines
    lines = cursor.execute("""
        SELECT
            StockId,
            OriginalQty,
            NewQty,
            OriginalPrice,
            NewPrice
        FROM POChangeRequestLine
        WHERE RequestId = ?
    """, (request_id,)).fetchall()

    return render_template(
        "po_change_review.html",
        request=header,
        lines=lines
    )


@inventory_bp.route("/po-change/<int:request_id>/approve", methods=["POST"])
@login_required
def approve_po_change(request_id):
    conn = create_db_connection()
    cursor = conn.cursor()


    try:
        req = cursor.execute("""
            SELECT PONumber, Status, RequestedByUserId
            FROM POChangeRequest
            WHERE Id = ?
        """, (request_id,)).fetchone()

        if not req or req.Status != "PENDING":
            raise Exception("Request not pending")

        lines = cursor.execute("""
            SELECT StockId, NewQty, NewPrice
            FROM POChangeRequestLine
            WHERE RequestId = ?
        """, (request_id,)).fetchall()

        # 🔧 Apply to Evolution
        with EvolutionConnection():
            PO = Evo.PurchaseOrder(req.PONumber)

            for detail in PO.Detail:
                for l in lines:
                    if detail.InventoryItemID == l.StockId:
                        detail.Quantity = float(l.NewQty) + detail.Processed
                        detail.UnitSellingPrice = float(l.NewPrice)

            PO.Save()

        cursor.execute("""
            UPDATE POChangeRequest
            SET Status = 'APPLIED',
                ReviewedByUserId = ?,
                ReviewedAt = GETDATE()
            WHERE Id = ?
        """, (current_user.id, request_id))

        conn.commit()
        notify_user(
            user_id=req.RequestedByUserId, 
            title="Requested PO change applied",
            body=f"The change requested for {req.PONumber} was approved and applied.",
            relative_url=f"/inventory/grv/{req.PONumber}")
        return {"success": True}

    except Exception as ex:
        conn.rollback()
        return {"success": False, "message": str(ex)}, 400
    
@inventory_bp.route("/po-change/<int:request_id>/reject", methods=["POST"])
@login_required
def reject_po_change(request_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("Select RequestedByUserId, PONumber From POChangeRequest Where Id = ?", (request_id,))
    req = cursor.fetchone()

    cursor.execute("""
        UPDATE POChangeRequest
        SET Status = 'REJECTED',
            ReviewedByUserId = ?,
            ReviewedAt = SYSDATETIME()
        WHERE Id = ? AND Status = 'PENDING'
    """, (current_user.id, request_id))

    conn.commit()
    notify_user(
        user_id=req.RequestedByUserId,
        title="Requested PO change rejected",
        body=f"The change requested for {req.PONumber} was approved and applied.",
        relative_url=f"/inventory/po-change/{request_id}")
    return {"success": True}


@inventory_bp.route("/incorrect_po", methods=["POST"])
@login_required
def incorrect_po():
    data = request.json

    po_number = data["poNumber"]
    receiver = data["receiverName"]
    supplier_ref = data.get("supplierRef")
    mismatches = data["mismatches"]

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # 1️⃣ Insert header
        cursor.execute("""
            INSERT INTO POChangeRequest
            (PONumber, SupplierRef, ReceiverName, RequestedByUserId)
            OUTPUT INSERTED.Id
            VALUES (?, ?, ?, ?)
        """, (
            po_number,
            supplier_ref,
            receiver,
            current_user.id
        ))

        request_id = cursor.fetchone()[0]

        # 2️⃣ Insert lines
        for m in mismatches:
            cursor.execute("""
                INSERT INTO POChangeRequestLine
                (RequestId, StockId, OriginalQty, NewQty, OriginalPrice, NewPrice)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                m["ProductId"],
                m["OriginalQty"],
                m["QtyReceived"],
                m["OriginalPrice"],
                m["PriceReceived"]
            ))

        conn.commit()

        # 3️⃣ Notify supervisor
        supervisor_id = 1 # replace with role lookup if you have it

        notify_user(
            supervisor_id,
            title="PO Change Request",
            body=f"PO {po_number} requires approval",
            relative_url=f"/inventory/po-change/{request_id}"
        )

        return {"success": True}

    except Exception as ex:
        conn.rollback()
        return {"success": False, "message": str(ex)}, 400
