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
    Select DelNoteNo, DelDate,Agent, TotalQtyDelivered, TotalQtySold, TotalQtyInvoiced from [dbo].[_uvDelQuantitiesHeader]
    WHERE DelDate >= ?
    """
    cursor.execute(delivery_query, (start_of_month,))
    delivery_rows = cursor.fetchall()

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


    # Prepare delivery data
    del_note_numbers = set()
    sent_this_week = 0
    uninvoiced_by_agent = {}
    uninvoiced_by_note = {}

    for row in delivery_rows:
        del_note_no, del_date, agent_name, qty_sent, qty_sold, qty_invoiced = row

        del_note_numbers.add(del_note_no)

        if parse_date(del_date) >= start_of_week:
            sent_this_week += qty_sent

        if qty_invoiced < qty_sold and qty_sold != 0:
            uninvoiced_by_agent[agent_name] = uninvoiced_by_agent.get(agent_name, 0) + (qty_sent - qty_invoiced)
            uninvoiced_by_note[del_note_no] = {
                "agent": agent_name,
                "qty_sent": qty_sent,
                "qty_sold": qty_sold,
                "qty_invoiced": qty_invoiced
            }

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
        "total_sent": sent_this_week,
        "total_sold": sold_this_week,
        "total_invoiced": invoiced_this_week,
        "uninvoiced_notes": [
            {
                "note": note,
                "agent": info["agent"],
                "qty_sent": info["qty_sent"],
                "qty_sold": info["qty_sold"],
                "qty_invoiced": info["qty_invoiced"]
            }
            for note, info in uninvoiced_by_note.items()
        ],
        "recent_invoices": recent_invoices
    })
