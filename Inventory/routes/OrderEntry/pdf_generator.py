from Inventory.routes import inventory_bp
from flask import render_template, Response, current_app, send_file
from flask_login import login_required
import pdfkit
import os, tempfile
from playwright.sync_api import sync_playwright

@inventory_bp.route("/test/po/pdf")
@login_required
def test_po_pdf():

    
    html = render_template(
        "pdf/po/uitdraai.html"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name

    html_to_pdf(html, pdf_path)

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name="po-playwright.pdf"
    )

def html_to_pdf(html: str, output_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Set HTML directly
        page.set_content(
            html,
            wait_until="networkidle"
        )

        # Generate PDF
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={
                "top": "5mm",
                "right": "5mm",
                "bottom": "20mm",
                "left": "5mm"
            }
        )

        browser.close()



@inventory_bp.route("/test/po/html")
@login_required
def test_po_html():
    sample_po = {
        "company": {
            "id": 1,
            "name": "Uitdraai BDY",
            "logo": "http://localhost:5000/static/logos/uitdraai.png",
            "vat": "4123456789",
            "address": "123 Market Street"
        },
        "supplier": {
            "name": "ABC Produce",
            "vat": "4987654321"
        },
        "po": {
            "number": "PO-TEST-001",
            "date": "2026-01-15",
            "due_date": "2026-01-20"
        },
        "lines": [
            {
                "code": "APL01",
                "description": "Apples Grade A",
                "qty": 10,
                "price": 25.00,
                "total": 250.00
            },
            {
                "code": "BAN02",
                "description": "Bananas",
                "qty": 5,
                "price": 18.00,
                "total": 90.00
            }
        ],
        "totals": {
            "subtotal": 340.00,
            "vat": 51.00,
            "total": 391.00
        }
    }
        
    return render_template(
        "pdf/po/uitdraai.html",
        po=sample_po
    )