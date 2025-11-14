
from flask_login import login_required, current_user
import requests
from flask import Blueprint, jsonify, current_app, request, render_template
from datetime import datetime, timedelta
from db import create_db_connection

SDK_bp = Blueprint('SDK', __name__)

@SDK_bp.route('/SDK/test', methods=['GET'])
@login_required
def SDK_test_page():
    from flask import render_template
    return render_template('EvolutionSDK/test.html')


@SDK_bp.route("/SDK/fetch_suppliers")
def po_page():
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    Select Distinct DCLink, SupplierName from _uvPO_Outstanding
    """)
    suppliers = [
        {"code": row[0], "name": row[1]}
        for row in cursor.fetchall()
    ]

    conn.close()

    return jsonify({"suppliers": suppliers})


@SDK_bp.route("/get_po_numbers", methods=["POST"])
def get_po_numbers():
    supplier_code = request.json.get("supplier_code")

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT OrderNum, OrderDate, OrderDesc, OrdTotIncl
        FROM _uvPO_Outstanding
        WHERE DcLink = ?
    """, (supplier_code,))

    rows = cursor.fetchall()
    conn.close()

    po_list = [
        {
            "order_num": row[0],
            "order_date": row[1],
            "order_desc": row[2],
            "order_total": row[3]
        }
        for row in rows
    ]

    return jsonify({"po_list": po_list})

@SDK_bp.route("/SDK/fetch_po_lines/<po_number>")
def fetch_po_lines(po_number):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT iStockCodeID, StockDesc, WHName, QtyOutstanding, fUnitPriceExcl
        FROM _uvPO_Outstanding
        WHERE OrderNum = ?
    """, (po_number,))

    rows = cursor.fetchall()
    conn.close()

    po_lines = [
        {
            "iStockCodeID": row[0],
            "StockDesc": row[1],
            "WHName": row[2],
            "QtyOutstanding": float(row[3]),
            "Price": float(row[4])
        }
        for row in rows
    ]

    return jsonify({"po_lines": po_lines})


# The URL of your ASP.NET API
EVOLUTION_API_URL = "http://localhost:5295/api/EvolutionTest/submit-grv"  # adjust port if needed

@SDK_bp.route("/submit_grv", methods=["POST"])
def submit_grv():
    data = request.get_json()
    print(data)
    po_number = data.get("poNumber")
    lines = data.get("lines")  # list of { ProductId, QtyReceived }

    if not po_number or not lines or not isinstance(lines, list):
        return jsonify({"error": "Missing or invalid PO number or lines"}), 400

    # Validate each line has required fields
    for l in lines:
        if "ProductId" not in l or "QtyReceived" not in l:
            return jsonify({"error": "Invalid line format. Each line must have ProductId and QtyReceived"}), 400

    payload = {
        "PoNumber": po_number,
        "Lines": lines
    }
    print("Submitting payload to Evolution API:", payload)

    try:
        response = requests.post(EVOLUTION_API_URL, json=payload)
        print(f"Evolution API Response Status: {response.status_code}")
        print(f"Evolution API Response Body: {response.text}")
        
        api_result = response.json()
        
        # Check if the API returned success=false in the response body
        if not api_result.get("success", False):
            return jsonify({
                "success": False,
                "message": api_result.get("error", "Unknown error from Evolution API")
            }), 400
        
        return jsonify({
            "success": True,
            "message": "GRV submitted to Evolution API successfully",
            "api_result": api_result
        })
        
    except requests.RequestException as e:
        print(f"Evolution API Error: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to call Evolution API: {str(e)}"
        }), 500
    except ValueError as e:
        print(f"JSON Parse Error: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Evolution API returned invalid JSON"
        }), 500

@SDK_bp.route('/SDK/create-sales-order', methods=['POST'])
def SDK_create_sales_order():
    if not current_user.get_db_password():
        return jsonify({
            "success": False,
            "message": "Database credentials are not configured for your account."
        }), 400

    request_payload = request.get_json(silent=True) or {}

    description = request_payload.get(
        "description",
        f"Sales Order - {datetime.now():%d-%m-%Y %H:%M}"
    )
    order_payload = {
        "customerCode": request_payload.get("customerCode", "ZZZ001"),
        "projectCode": request_payload.get("projectCode", "KAL-AAR"),
        "inventoryItemCode": request_payload.get("inventoryItemCode", "AART-STD"),
        "quantity": request_payload.get("quantity", 10),
        "unitPriceIncl": request_payload.get("unitPriceIncl", 12.99),
        "warehouseCode": request_payload.get("warehouseCode", "Mstr"),
        "description": description
    }

    api_payload = {
        "serverName": request_payload.get("serverName", current_user.server_name),
        "commonDatabaseName": request_payload.get("commonDatabaseName", "SageCommon"),
        "databaseName": request_payload.get("databaseName", current_user.database_name),
        "username": request_payload.get("username", current_user.db_username),
        "password": request_payload.get("password", current_user.get_db_password()),
        "order": order_payload
    }

    api_url = current_app.config.get(
        'EVOLUTION_SALES_ORDER_API',
        'http://localhost:5295/api/evolutiontest/create-sales-order'
    )

    try:
        response = requests.post(api_url, json=api_payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        return jsonify({
            "success": False,
            "message": "Failed to reach Evolution API.",
            "error": str(exc)
        }), 502
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Evolution API returned invalid JSON."
        }), 502

    if not data.get('success'):
        return jsonify({
            "success": False,
            "message": data.get('error', 'Evolution API reported a failure.'),
            "payload": data
        }), 500

    return jsonify({
        "success": True,
        "message": data.get('message', 'Sales Order created successfully.'),
        "payload": data
    }), 200

