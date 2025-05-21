from flask import Blueprint, render_template
from db import create_db_connection

view_entry_bp = Blueprint('view_entry', __name__)

@view_entry_bp.route('/delivery-note/<del_note_no>')
def delivery_note(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch delivery note header (distinct values for the header info)
    cursor.execute("""
        SELECT TOP 1 DelNoteNo, DelDate, AgentAccount, AgentName,
                      MarketCode, MarketName, TransporterAccount,
                      TransporterName
        FROM [dbo].[_uvMarketDeliveryNote]
        WHERE DelNoteNo = ?
    """, (del_note_no,))  # Pass as tuple
    header = cursor.fetchone()

    if not header:
        return "Delivery note not found", 404

    # Fetch line items
    cursor.execute("""
        SELECT DelLineIndex, ProductDescription, MainProdUnitName,
               DelLineQuantityBags, TotalQtySold, SalesGrossAmnt,
               TotalQtyInvoiced, InvoicedGrossAmnt
        FROM [dbo].[_uvMarketDeliveryNote]
        WHERE DelNoteNo = ?
        ORDER BY DelLineIndex
    """, (del_note_no,))  # Pass as tuple
    lines = cursor.fetchall()

    # Summary calculations
    total_qty_sold = sum([l[3] for l in lines])
    total_sales_gross = sum([l[4] for l in lines])
    total_qty_invoiced = sum([l[5] for l in lines])
    total_invoiced_gross = sum([l[6] for l in lines])
    avg_price = (total_sales_gross / total_qty_sold) if total_qty_sold else 0

    return render_template(
        'Bill Of Lading Page/View_Delivery_note.html',
        header=header,
        lines=lines,
        summary={
            'total_qty_sold': total_qty_sold,
            'avg_price': avg_price,
            'total_qty_invoiced': total_qty_invoiced,
            'total_invoiced_gross': total_invoiced_gross
        }
    )
