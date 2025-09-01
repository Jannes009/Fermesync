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


@dashboard_bp.route('/dashboard/summary')
def dashboard_summary():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("EXEC SIGGetDashboardSummary")
    row = cursor.fetchone()
    conn.close()

    return jsonify({
        "month_deliveries": row[0],
        "total_unsold_qty": row[1],
        "total_sold_this_week": row[2],
        "total_uninvoiced_qty": row[3],
    })


@dashboard_bp.route('/dashboard/incomplete')
def dashboard_incomplete():
    conn = create_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT TOP 5 DelNoteNo, AgentName, DelDate, QtyLoaded, QtySold, QtyInvoiced
        FROM [dbo].[_uvViewEntriesPage]
        WHERE QtyInvoiced < QtyLoaded
        ORDER BY DelDate ASC
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "note": r[0],
            "agent_name": r[1],
            "del_date": r[2],
            "qty_delivered": r[3],
            "qty_sold": r[4],
            "qty_invoiced": r[5],
        }
        for r in rows
    ])


@dashboard_bp.route('/dashboard/invoices')
def dashboard_invoices():
    conn = create_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT TOP 5 InvoiceDate, InvoiceNo, DelNoteNo,
                      SUM(SalesQty) AS TotalQty,
                      SUM(SalesAmnt) AS TotalAmount
        FROM [dbo].[_uvMarketInvoices]
        GROUP BY InvoiceDate, InvoiceNo, DelNoteNo
        ORDER BY InvoiceDate DESC;
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "invoice_no": r[1],
            "delivery_note": r[2],
            "amount": float(r[4]),
            "date": r[0],
        }
        for r in rows
    ])
