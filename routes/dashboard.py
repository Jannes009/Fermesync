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

    # Deliveries this month
    delivery_query = """
    Select DelNoteNo, DelDate,Agent, TotalQtyDelivered, TotalQtySold, AvailableQtyForSale, TotalQtyInvoiced, TotalNotInvoiced, DelIsFullyInvoiced from [dbo].[_uvDelQuantitiesHeader]
    WHERE DelDate >= ?
    """
    cursor.execute(delivery_query, (start_of_month,))
    delivery_rows = cursor.fetchall()

    # Incomplete delivery notes (not fully invoiced, with agent name)
    incomplete_query = """
    Select DEL.DelNoteNo, AGENT.Name as AgentName, DEL.DelDate, DEL.TotalQtyDelivered, DEL.TotalQtySold, DEL.TotalQtyInvoiced, DEL.TotalNotInvoiced
    from [dbo].[_uvDelQuantitiesHeader] DEL
    JOIN (Select DCLink, Name from _uvMarketAgent) AGENT on AGENT.DCLink = DEL.Agent
    where DEL.DelIsFullyInvoiced = 0
    order by DEL.DelDate asc
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
            "qty_invoiced": row[5],
            "qty_not_invoiced": row[6]
        }
        for row in incomplete_rows
    ]

    # Sales this week
    sales_query = """
    SELECT SUM(SalesQty) AS TotalQty
    FROM [dbo].[_uvMarketSales]
    WHERE SalesDate >= ?
    """
    cursor.execute(sales_query, (start_of_week,))
    sales_rows = cursor.fetchone()
    sold_this_week = sales_rows[0]

    # Invoices this week
    invoice_query = """
    SELECT InvoiceDate, InvoiceNo, DelNoteNo, SUM(SalesQty) AS TotalQty, SUM(SalesAmnt) AS TotalAmount
    FROM [dbo].[_uvMarketInvoices]
    WHERE InvoiceDate >= ?
    GROUP BY InvoiceDate, InvoiceNo, DelNoteNo
    ORDER BY InvoiceDate DESC
    """
    cursor.execute(invoice_query, (start_of_week,))
    invoice_rows = cursor.fetchall()

    this_month_delivery_count = len({row[0] for row in delivery_rows})

    # Invoicing summary
    invoiced_this_week = sum(row[3] for row in invoice_rows)
    recent_invoices = [
        {
            "invoice_no": row[1],
            "delivery_note": row[2],
            "amount": float(row[4]),
            "date": row[0].strftime('%Y-%m-%d') if isinstance(row[0], datetime) else str(row[0])
        }
        for row in invoice_rows[:5]
    ]

    conn.close()
    return jsonify({
        "month_deliveries": this_month_delivery_count,
        "total_sent": sold_this_week,
        "total_sold": sold_this_week,
        "total_invoiced": invoiced_this_week,
        "incomplete_delivery_notes": incomplete_delivery_notes,
        "recent_invoices": recent_invoices
    })
