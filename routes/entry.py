from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, make_response
from db import create_db_connection, close_db_connection
import pypyodbc as odbc
from routes.db_functions import (
    get_agent_codes, get_transporter_codes, get_production_unit_codes,
    get_market_codes, get_products, agent_code_to_agent_name,
    market_Id_to_market_name, transporter_account_to_transporter_name,
    project_link_to_production_unit_name,
    get_stock_id
)

entry_bp = Blueprint('entry', __name__)

def fetch_dropdown_options(cursor):
    return {
        'agent_codes': get_agent_codes(cursor),
        'transporter_codes': get_transporter_codes(cursor),
        'production_unit_codes': get_production_unit_codes(cursor),
        'market_codes': get_market_codes(cursor),
        'product_options': get_products(cursor)
    }

def integrity_error(error, form_data):
    print(f"IntegrityError: {error}")
    return {
        "error_message": (
            "Entry not created. This might be due to duplicate data "
            "or missing required fields. Please check your inputs and try again."
        ),
        "form_data": form_data,
    }


def fetch_header_data(request_form):
    return {key: request_form.get(key) for key in [
        'ZZAgentName', 'ZZDelNoteNo', 'ZZDelDate', 'ZZProductionUnitCode',
        'ZZTransporterCode', 'ZZTransporterCost', 'ZZMarket'
    ]}

def fetch_lines_data(request_form):
    return {
        'products': request_form.getlist('ZZProduct[]'),
        'quantities': request_form.getlist('ZZQuantityBags[]'),
        'prices': request_form.getlist('ZZEstimatedPrice[]'),
        'unit': request_form.getlist('ZZProductionUnitLine[]')
    }

def store_header(cursor, form_data):
    print(form_data)
    cursor.execute("""
        INSERT INTO ZZDeliveryNoteHeader 
        (DeliClientId, DelNoteNo, DelDate, DelFarmId, DelTransporter,  DelTransportCostExcl, DelMarketId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, tuple(form_data.values()))
    cursor.connection.commit()

def store_lines(cursor, header_id, line_data, linesId=None):
    total_quantity = 0
    count = 0
    for product, quantity, price, unit, in zip(
        line_data['products'], line_data['quantities'], line_data['prices'], line_data['unit']):
        total_quantity += float(quantity)
        if linesId == None or len(linesId) <= count:
            cursor.execute("""
                INSERT INTO ZZDeliveryNoteLines 
                (DelHeaderId, DelLineStockId, DelLineQuantityBags, DelLinePriceEstimate, DelLineFarmId)
                VALUES (?, ?, ?, ?, ?)
            """, (header_id, product, quantity, price, unit))
        else:
            
            cursor.execute("""
                        UPDATE ZZDeliveryNoteLines 
                        SET DelLineStockId = ?, DelLineQuantityBags = ?, DelLinePriceEstimate = ?, DelLineFarmId = ?
                        WHERE DelLineIndex = ?
            """, (product, quantity, price, unit, linesId[count]))
        count+=1
    cursor.connection.commit()
    return total_quantity

def update_header_quantity(cursor, header_id, total_quantity):
    cursor.execute("""
        UPDATE ZZDeliveryNoteHeader SET DelQuantityBags = ? WHERE DelIndex = ?
    """, (total_quantity, header_id))
    cursor.connection.commit()

def fetch_lines(cursor, entry_id):
    cursor.execute("SELECT * FROM ZZDeliveryNoteLines WHERE DelHeaderId = ?", (entry_id,))
    return cursor.fetchall()

@entry_bp.route('/create_entry', methods=['GET', 'POST'])
def create_entry():
    print("Entry created")
    error_message = None
    form_data = None
    connection = create_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        print("Entry creating")
        try:
            form_data = fetch_header_data(request.form)
            lines_data = fetch_lines_data(request.form)

            store_header(cursor, form_data)
            cursor.execute("SELECT DelIndex FROM ZZDeliveryNoteHeader WHERE DelNoteNo = ?", (form_data['ZZDelNoteNo'],))
            header_id = cursor.fetchone()[0]

            total_quantity = store_lines(cursor, header_id, lines_data)
            update_header_quantity(cursor, header_id, total_quantity)

            session['del_note_no'] = form_data['ZZDelNoteNo']
            print(form_data['ZZDelNoteNo'], session.get('del_note_no'))
            return redirect(url_for('entry.submission_success'))

        except odbc.IntegrityError as e:
            error_data = integrity_error(e, request.form)
            error_message = error_data["error_message"]
            form_data = error_data["form_data"]

    dropdown_options = fetch_dropdown_options(cursor)

    close_db_connection(cursor, connection)

    return render_template('Bill Of Lading page/create_entry.html',
                           error_message=error_message,
                           form_data=form_data,
                           product_quantity_pairs=[],
                           **dropdown_options)

@entry_bp.route('/submission_success')
def submission_success():
    del_note_no = session.get('del_note_no')
    if not del_note_no:
        return render_template('Transition pages/submission_success.html', message="No recent entry found.")
    return render_template('Transition pages/submission_success.html',
                           message="Entry submitted successfully!",
                           del_note_no=del_note_no)

import json
from flask import request, jsonify

DATA_FILE = 'saved_stock_form.json'

@entry_bp.route('/api/save-form', methods=['POST'])
def save_form():
    form_data = request.json
    with open(DATA_FILE, 'w') as file:
        json.dump(form_data, file)
    return jsonify({"message": "Form data saved successfully!"}), 200


@entry_bp.route('/api/load-form', methods=['GET'])
def load_form():
    try:
        with open(DATA_FILE, 'r') as file:
            form_data = json.load(file)
        return jsonify(form_data), 200
    except FileNotFoundError:
        return jsonify({"message": "No saved form data found."}), 404

@entry_bp.route('/api/clear-saved-form', methods=['POST'])
def clear_saved_form():
    print("Attempt to clear")
    try:
        # Write an empty JSON object to ensure valid JSON structure
        with open(DATA_FILE, 'w') as file:
            json.dump({}, file)  # Use {} for an empty object or [] for an empty list

        print(f"Saved data cleared at {DATA_FILE}")
        return jsonify({"message": "Saved data cleared successfully"}), 200
    except Exception as e:
        print(f"Error clearing data: {e}")
        return jsonify({"error": str(e)}), 500


@entry_bp.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for('index')))
    resp.set_cookie('remember_token', '', expires=0)  # Clear remember token cookie
    return resp

@entry_bp.route('/check_session', methods=['GET'])
def check_session():
    if 'username' in session: 
        return jsonify({"session_active": True})
    return jsonify({"session_active": False})

@entry_bp.route('/check_delivery_note', methods=['POST'])
def check_delivery_note():
    data = request.json
    del_note_no = data.get('ZZDelNoteNo')

    conn = create_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM ZZDeliveryNoteHeader WHERE DelNoteNo = ?", (del_note_no,))
    exists = cursor.fetchone()[0] > 0

    conn.close()
    return jsonify({'exists': exists})

@entry_bp.route("/get-last-sales-price", methods=["POST"])
def get_last_sales_price():
    data = request.json
    stock_link = data.get("stockLink")
    whse_link = data.get("whseLink")

    if not stock_link or not whse_link:
        return jsonify({"error": "Missing parameters"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT LastSalesPrice 
        FROM _uvMarketProductWhse 
        WHERE StockLink = ? AND WhseLink = ?
    """, (stock_link, whse_link))
    result = cursor.fetchone()

    if result:
        return jsonify({"lastSalesPrice": result[0]})
    else:
        return jsonify({"lastSalesPrice": None})

@entry_bp.route("/get-default-transport-cost", methods=["POST"])
def get_default_transport_cost_api():
    """
    API endpoint to get the default transport cost based on agent, packhouse, and transporter.
    """
    data = request.json
    agent_code = data.get("agentCode")
    packhouse_code = data.get("packhouseCode") 
    transporter_code = data.get("transporterCode")
    print(agent_code, packhouse_code, transporter_code)

    if not agent_code or not packhouse_code or not transporter_code:
        return jsonify({"error": "Missing required parameters: agentCode, packhouseCode, transporterCode"}), 400

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # fetch agent destination
        query = """
        Select AgentDestination from _uvMarketAgent
        Where DCLink = ?
        """
        cursor.execute(query, (agent_code,))
        destination_result = cursor.fetchone()
        print(destination_result)
        default_cost = 0.0
        if destination_result and destination_result[0] is not None:
            destination = destination_result[0]
            query = """
            Select LastTransportCost from [dbo].[_uvLastTransportCost]
            where TransporterAccount = ? AND PackhouseLink = ? AND AgentDestination = ? 
            """
            cursor.execute(query, (transporter_code, packhouse_code, destination))
            result = cursor.fetchone()
            print(transporter_code, packhouse_code, destination, result)
            if result and result[0] is not None:
                default_cost = float(result[0])
            else:
                default_cost = 0
        else:
            default_cost = 0
        
        close_db_connection(cursor, conn)
        
        return jsonify({"defaultTransportCost": default_cost})
        
    except Exception as e:
        print(f"Error in get_default_transport_cost_api: {e}")
        return jsonify({"error": "Failed to get default transport cost"}), 500
