from flask import Blueprint, render_template, send_file, request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from db import create_db_connection
from flask import jsonify
import json
import os

report_bp = Blueprint('report', __name__)

@report_bp.route('/delivery-note-report')
def delivery_note_report():
    return render_template(
        'Reports/reports.html'
    )

@report_bp.route('/delivery-note-report-template')
def delivery_note_report_template():
    return render_template(
        'Reports/reports_templates.html'
    )

from datetime import datetime

@report_bp.route('/api/fetch-delivery-note-report', methods=['GET'])
def fetch_delivery_note_report():
    json_file_path = os.path.join('static', 'delivery_note_data.json')
    
    # Get query parameters
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    
    # Validate dates
    try:
        if not start_date or not end_date:
            return jsonify({"error": "Both startDate and endDate are required"}), 400
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        if start_date_obj > end_date_obj:
            return jsonify({"error": "startDate cannot be after endDate"}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    try:
        # Fetch from database
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # Parameterized query to prevent SQL injection
        query = """
            SELECT * FROM [dbo].[_uvMarketDeliveryNotetbl]
            WHERE DelDate BETWEEN ? AND ?
        """
        cursor.execute(query, (start_date, end_date))
        
        # Map rows to dictionary
        columns = [col[0] for col in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()

        # Prepare response with parameters including date created
        response = {
            "parameters": {
                "startDate": start_date,
                "endDate": end_date,
                "dateCreated": datetime.now().strftime('%Y-%m-%d')
            },
            "data": data
        }

        # Save to JSON file
        try:
            with open(json_file_path, 'w') as f:
                json.dump(response, f)
        except Exception as e:
            print(f"Error writing to JSON file: {e}")
            # Continue even if file write fails, as API response is priority
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Error fetching data from database: {e}")
        return jsonify({"error": "Failed to fetch report data"}), 500



from flask import Blueprint, request, jsonify
import json
import os
import tempfile

TEMPLATE_DIR = "static/"
os.makedirs(TEMPLATE_DIR, exist_ok=True)
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "report_templates.json")


def read_templates_file():
    """Return the templates object from disk, or {} on error / missing file."""
    if not os.path.exists(TEMPLATE_FILE):
        return {}
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        # If the file is corrupt or unreadable, return empty dict
        return {}


def write_templates_file(templates_obj):
    """Atomically write templates_obj to TEMPLATE_FILE."""
    # write to a temp file in same dir then replace (atomic on most platforms)
    fd, tmp_path = tempfile.mkstemp(dir=TEMPLATE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            json.dump(templates_obj, tmpf, indent=4, ensure_ascii=False)
        os.replace(tmp_path, TEMPLATE_FILE)
    finally:
        # if anything left, try to remove tmp
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

@report_bp.route("/save_template", methods=["POST"])
def save_template():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    name = data.get("name")
    if not name:
        return jsonify({"error": "Missing required field: 'name'"}), 400

    template_name = str(name).strip()
    template_entry = {
        "name": template_name,
        "levels": data.get("levels", []),
        "fields": data.get("fields", [])
    }

    try:
        templates = read_templates_file()
        if not isinstance(templates, dict):
            templates = {}

        templates[template_name] = template_entry
        write_templates_file(templates)
        return jsonify({"message": "Template saved", "template": template_name}), 200
    except Exception as exc:
        return jsonify({"error": "Failed to save template", "details": str(exc)}), 500
