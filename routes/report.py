from flask import Blueprint, render_template, send_file, request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from db import create_db_connection
from flask import jsonify

report_bp = Blueprint('report', __name__)

@report_bp.route('/delivery-note-report')
def delivery_note_report():
    return render_template(
        'Reports/reports.html'
    )

@report_bp.route('/api/fetch-delivery-note-report')
def fetch_delivery_note_report():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("Select * from [dbo].[_uvMarketDeliveryNote]")
    columns = [col[0] for col in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return jsonify(data)



