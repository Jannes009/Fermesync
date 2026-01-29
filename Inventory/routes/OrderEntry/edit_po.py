
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from Inventory.db import create_db_connection
from Inventory.routes import inventory_bp
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo
from Inventory.routes.notifications import emit_event, send_notification

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
            POLineId,
            StockId,
            OrderedQty,
            DeliveredQty
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
            SELECT POLineId, DeliveredQty
            FROM POChangeRequestLine
            WHERE RequestId = ?
        """, (request_id,)).fetchall()

        # 🔧 Apply to Evolution
        with EvolutionConnection():
            PO = Evo.PurchaseOrder(req.PONumber)

            for detail in PO.Detail:
                for l in lines:
                    print(f"Checking line {detail.Index} against {l.POLineId}")
                    if detail.Index == l.POLineId:
                        detail.Quantity = float(l.DeliveredQty) + detail.Processed
                        print(f"Updating line {detail.Index} to qty {detail.Quantity}")

            PO.Save()

        cursor.execute("""
            UPDATE POChangeRequest
            SET Status = 'APPLIED',
                ReviewedByUserId = ?,
                ReviewedAt = GETDATE()
            WHERE Id = ?
        """, (current_user.id, request_id))

        conn.commit()
        
        if current_user.id != req.RequestedByUserId:
            send_notification(
                user_id=req.RequestedByUserId,
                title="GRV Change Request Aprroved",
                message=f"The change requested for {req.PONumber} was approved and applied.",
                relative_url=f"/inventory/grv/{request_id}",
                push_mode="batched"
            )
        emit_event(
            event_code="GRV_EDIT",
            entity_id=req.PONumber,
            entity_desc="Purchase Order"
        )
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
    send_notification(
        user_id=req.RequestedByUserId,
        title="Requested PO change rejected",
        message=f"The change requested for {req.PONumber} was approved and applied.",
        relative_url=f"/inventory/po-change/{request_id}",
        push_mode="batched")
    return {"success": True}


@inventory_bp.route("/incorrect_po", methods=["POST"])
@login_required
def incorrect_po():
    data = request.json
    print(data)

    po_number = data["poNumber"]
    receiver = data["receiverName"]
    supplier_ref = data.get("supplierRef")
    overQtys = data["overQtys"]

    conn = create_db_connection()
    cursor = conn.cursor()

    # try:
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
    for q in overQtys:
        cursor.execute("""
            INSERT INTO POChangeRequestLine
            (RequestId, StockId, [POLineId], [OrderedQty], [DeliveredQty])
            VALUES (?, ?, ?, ?, ?)
        """, (
            request_id,
            q["StockId"],
            q["LineId"],
            q["QtyOrdered"],
            q["QtyDelivered"]
        ))

    conn.commit()

    emit_event(
        event_code="GRV_CHANGE_REQUEST",
        entity_id=request_id,
        entity_desc="Purchase Order"
    )

    return {"success": True}

    # except Exception as ex:
    #     conn.rollback()
    #     return {"success": False, "message": str(ex)}, 400
