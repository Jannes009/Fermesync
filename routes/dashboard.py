from flask import Blueprint, jsonify
from datetime import datetime, timedelta
from db import create_db_connection

dashboard_bp = Blueprint('dashboard', __name__)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value, '%Y-%m-%d').date()
    return value  # already a date


@dashboard_bp.route('/dashboard/data')
def dashboard_data():
    conn = create_db_connection()
    cursor = conn.cursor()

    today = datetime.today().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    print(start_of_month)

    # Deliveries this month
    delivery_query = """
        SELECT COUNT(DelIndex)
        FROM ZZDeliveryNoteHeader
        WHERE DelDate >= ?
    """
    cursor.execute(delivery_query, (start_of_month,))
    delivery_count = cursor.fetchone()

    # Incomplete delivery notes (not fully invoiced, with agent name)
    incomplete_query = """
        SELECT TOP 5 DelNoteNo, AgentName, DelDate, QtyLoaded, QtySold, QtyInvoiced
        FROM [dbo].[_uvViewEntriesPage]
        WHERE QtyInvoiced < QtyLoaded
        ORDER BY DelDate ASC
    """
    cursor.execute(incomplete_query)
    incomplete_rows = cursor.fetchall()

    incomplete_delivery_notes = [
        {
            "note": row[0],
            "agent_name": row[1],
            "del_date": row[2].strftime('%Y-%m-%d') if isinstance(row[2], datetime) else str(row[2]),
            "qty_delivered": row[3],
            "qty_sold": row[4],
            "qty_invoiced": row[5]
        }
        for row in incomplete_rows
    ]

    quantities_query = """
        SELECT SUM(QtyLoaded) TotalQtyDelivered,
               SUM(QtySold) TotalQtySold,
               SUM(QtyInvoiced) TotalQtyInvoiced
        FROM [dbo].[_uvViewEntriesPage]
    """
    cursor.execute(quantities_query)
    quantities = cursor.fetchone()

    # Sales this week
    sales_query = """
        SELECT SUM(SalesQty) AS TotalQty
        FROM ZZSalesLines
        WHERE SalesDate >= ?
    """
    cursor.execute(sales_query, (start_of_week,))
    sales_rows = cursor.fetchone()
    sold_this_week = sales_rows[0] or 0

    # Invoices this week (top 5 most recent)
    invoice_query = """
        SELECT TOP 5 InvoiceDate, InvoiceNo, DelNoteNo,
                      SUM(SalesQty) AS TotalQty,
                      SUM(SalesAmnt) AS TotalAmount
        FROM [dbo].[_uvMarketInvoices]
        GROUP BY InvoiceDate, InvoiceNo, DelNoteNo
        ORDER BY InvoiceDate DESC;
    """
    cursor.execute(invoice_query)
    invoice_rows = cursor.fetchall()

    recent_invoices = [
        {
            "invoice_no": row[1],
            "delivery_note": row[2],
            "amount": float(row[4]),
            "date": row[0].strftime('%Y-%m-%d') if isinstance(row[0], datetime) else str(row[0])
        }
        for row in invoice_rows
    ]

    conn.close()

    return jsonify({
        "month_deliveries": delivery_count[0],
        "total_unsold_qty": quantities[0] - quantities[1],
        "total_sold_this_week": sold_this_week,
        "total_uninvoiced_qty": quantities[1] - quantities[2],
        "incomplete_delivery_notes": incomplete_delivery_notes,
        "recent_invoices": recent_invoices
    })
