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
            SELECT * FROM [dbo].[_uvMarketDeliveryNote]
            WHERE DelDate BETWEEN ? AND ?
        """
        cursor.execute(query, (start_date, end_date))
        
        # Map rows to dictionary
        columns = [col[0] for col in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()

        # Prepare response with parameters
        response = {
            "parameters": {
                "startDate": start_date,
                "endDate": end_date
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



