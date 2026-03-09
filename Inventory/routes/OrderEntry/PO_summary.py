import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required



@inventory_bp.route("/po/requisition", methods=["GET"])
@login_required
def list_po_requisitions():
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # fetch po requistions
        cursor.execute("""
        SELECT
            Id,
            Name SupplierName,
            OrderDate,
            DueDate,
            Description,
            Status,
            PONumber
        FROM [stk].PO_RequisitionHeader POHEA
        JOIN [common].[_uvSuppliers] SUP on SUP.DCLink = POHEA.SupplierId
        Where Status <> 'POSTED'
        ORDER BY CreatedAt ASC
        """)

        rows = cursor.fetchall()

        requisitions = []
        for r in rows:
            requisitions.append({
                "id": r.Id,
                "supplier": r.SupplierName,
                "order_date": r.OrderDate[:10] if r.OrderDate else None,
                "due_date": r.DueDate[:10] if r.DueDate else None,
                "description": r.Description,
                "status": r.Status,
                "po_number": r.PONumber
            })

        # fetch posted po's from evolution
        cursor.execute("""
        Select DISTINCT AutoIndex, SupplierName, OrderDate, DueDate, OrderDesc, OrderNum, DocStatus
        from [inventory].[_uvPurchaseOrders]
        Where DocState in (1,3)
        ORDER BY OrderDate ASC
        """)

        rows = cursor.fetchall()
        for r in rows:
            requisitions.append({
                "id": r.AutoIndex,
                "supplier": r.SupplierName,
                "order_date": fmt_date(r.OrderDate),
                "due_date": fmt_date(r.DueDate),
                "description": r.OrderDesc,
                "status": r.DocStatus,
                "po_number": r.OrderNum
            })

        return render_template(
            "po_summary.html",
            requisitions=requisitions
        )

    finally:
        conn.close()

def fmt_date(d):
    return d.strftime("%Y-%m-%d") if d else None
