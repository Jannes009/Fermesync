from flask import Blueprint, render_template, send_file, request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from db import create_db_connection

report_bp = Blueprint('report', __name__)

# Ensure that None values are handled gracefully
def safe_draw_string(c, x, y, text):
    if text is None:
        text = ""  # Replace None with empty string
    c.drawString(x, y, str(text))  # Ensure the value is converted to a string

@report_bp.route('/report')
def generate_report():
    del_note_no = request.args.get('del_note_no', '22137')  # you can make this dynamic
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM [dbo].[_uvMarketDeliveryNote]
    WHERE DelNoteNo = ?
    """, (del_note_no,))
    lines = cursor.fetchall()
    conn.close()

    if not lines:
        return "No data found", 404

    header = lines[0]
    
    # Create PDF in memory
    pdf_io = BytesIO()
    c = canvas.Canvas(pdf_io, pagesize=letter)

    # Set up margins
    left_margin = 50
    right_margin = 550

    # --- Header Section ---
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(300, 770, "Delivery Report")

    # Draw a line under title
    c.setLineWidth(1)
    c.line(left_margin, 760, right_margin, 760)

    # Delivery Details
    c.setFont("Helvetica", 12)

    details_y = 740
    safe_draw_string(c, left_margin, details_y, f"Delivery Note No:")
    safe_draw_string(c, left_margin + 130, details_y, header[2])

    safe_draw_string(c, 350, details_y, f"Date:")
    safe_draw_string(c, 400, details_y, str(header[1]))

    details_y -= 20
    safe_draw_string(c, left_margin, details_y, f"Agent:")
    safe_draw_string(c, left_margin + 130, details_y, header[4])

    safe_draw_string(c, 350, details_y, f"Transporter:")
    safe_draw_string(c, 450, details_y, header[12])

    details_y -= 20
    safe_draw_string(c, left_margin, details_y, f"Market:")
    safe_draw_string(c, left_margin + 130, details_y, header[6])

    safe_draw_string(c, 350, details_y, f"Product Unit:")
    safe_draw_string(c, 450, details_y, header[10])

    # Draw a line under the delivery details
    c.line(left_margin, details_y - 10, right_margin, details_y - 10)

    # --- Product Details Section ---
    y_position = details_y - 40

    c.setFont("Helvetica-Bold", 14)
    safe_draw_string(c, left_margin, y_position, "Product Details")

    y_position -= 20
    c.setFont("Helvetica-Bold", 11)

    # Column headers
    safe_draw_string(c, left_margin, y_position, "Description")
    safe_draw_string(c, 300, y_position, "Quantity")
    safe_draw_string(c, 400, y_position, "Price Estimate")

    # Draw a line under column headers
    c.line(left_margin, y_position - 5, right_margin, y_position - 5)

    # Reset font for table rows
    c.setFont("Helvetica", 10)
    y_position -= 20

    total = 0

    for line in lines:
        safe_draw_string(c, left_margin, y_position, line[17])
        safe_draw_string(c, 300, y_position, str(line[24]))
        safe_draw_string(c, 400, y_position, str(line[26]))

        try:
            total += float(line[24] or 0)
        except:
            pass

        y_position -= 15

        # Add a new page if needed
        if y_position < 100:
            c.showPage()
            y_position = 750

    # Total section
    c.setFont("Helvetica-Bold", 12)
    y_position -= 10
    c.line(left_margin, y_position, right_margin, y_position)

    y_position -= 20
    safe_draw_string(c, left_margin, y_position, "Total:")
    safe_draw_string(c, 300, y_position, str(total))

    # Save PDF
    c.save()
    pdf_io.seek(0)

    return send_file(pdf_io, download_name=f"DeliveryReport_{del_note_no}.pdf", as_attachment=True)

