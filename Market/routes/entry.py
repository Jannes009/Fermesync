from flask import render_template, request, redirect, url_for, session, jsonify, make_response
from Core.auth import create_db_connection, close_db_connection
import pyodbc as odbc
from Market.routes.db_functions import (
    get_agent_codes, get_transporter_codes, get_production_unit_codes,
    get_market_codes, get_products, get_destinations
)
import threading
from flask_login import current_user

from Market.routes import market_bp

def fetch_dropdown_options(cursor):
    return {
        'agent_codes': get_agent_codes(cursor),
        'transporter_codes': get_transporter_codes(cursor),
        'production_unit_codes': get_production_unit_codes(cursor),
        'destinations': get_destinations(cursor),
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
        'ZZTransporterCode', 'ZZTransporterCost', 'ZZMarket', 'ZZDestination'
    ]}

def fetch_lines_data(request_form):
    return {
        'products': request_form.getlist('ZZProduct[]'),
        'quantities': request_form.getlist('ZZQuantityBags[]'),
        'prices': request_form.getlist('ZZEstimatedPrice[]'),
        'unit': request_form.getlist('ZZProductionUnitLine[]')
    }

def store_header(cursor, form_data):
    cursor.execute("""
        INSERT INTO [mkt].ZZDeliveryNoteHeader 
        (DeliClientId, DelNoteNo, DelDate, DelFarmId, DelTransporter, DelTransportCostExcl, DelMarketId, DelDestinationId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                INSERT INTO [mkt].ZZDeliveryNoteLines 
                (DelHeaderId, DelLineStockId, DelLineQuantityBags, DelLinePriceEstimate, DelLineFarmId)
                VALUES (?, ?, ?, ?, ?)
            """, (header_id, product, quantity, price, unit))
        else:
            
            cursor.execute("""
                        UPDATE [mkt].ZZDeliveryNoteLines 
                        SET DelLineStockId = ?, DelLineQuantityBags = ?, DelLinePriceEstimate = ?, DelLineFarmId = ?
                        WHERE DelLineIndex = ?
            """, (product, quantity, price, unit, linesId[count]))
        count+=1
    cursor.connection.commit()
    return total_quantity

def update_header_quantity(cursor, header_id, total_quantity):
    cursor.execute("""
        UPDATE [mkt].ZZDeliveryNoteHeader SET DelQuantityBags = ? WHERE DelIndex = ?
    """, (total_quantity, header_id))
    cursor.connection.commit()

def fetch_lines(cursor, entry_id):
    cursor.execute("SELECT * FROM [mkt].ZZDeliveryNoteLines WHERE DelHeaderId = ?", (entry_id,))
    return cursor.fetchall()

@market_bp.route('/create_entry', methods=['GET', 'POST'])
def create_entry():
    error_message = None
    form_data = None

    # Get connection for dropdowns and form processing
    connection = create_db_connection()
    if not connection:
        return "Database connection failed. Contact admin."

    cursor = connection.cursor()

    if request.method == 'POST':
        try:
            form_data = fetch_header_data(request.form)
            lines_data = fetch_lines_data(request.form)

            # Store header
            store_header(cursor, form_data)

            cursor.execute("SELECT DelIndex FROM [mkt].ZZDeliveryNoteHeader WHERE DelNoteNo = ?", 
                           (form_data['ZZDelNoteNo'],))
            header_row = cursor.fetchone()
            if not header_row:
                raise Exception("Header not found after insert.")
            header_id = header_row[0]

            # Store lines
            total_quantity = store_lines(cursor, header_id, lines_data)

            # Update header totals
            update_header_quantity(cursor, header_id, total_quantity)

            # Commit main write
            connection.commit()

            del_note_no = form_data['ZZDelNoteNo']

            # --------------------------
            # Close main connection
            # --------------------------
            close_db_connection(cursor, connection)

            # --------------------------
            # Run background procedures
            # --------------------------
            threading.Thread(
                target=run_background_procedures, 
                args=(del_note_no)
            ).start()

            session['del_note_no'] = del_note_no
            return redirect(url_for('submission_success'))

        except odbc.IntegrityError as e:
            error_data = integrity_error(e, request.form)
            error_message = error_data["error_message"]
            form_data = error_data["form_data"]

        except Exception as e:
            error_message = f"An error occurred: {str(e)}"

    # --------------------------
    # GET request or POST error path
    # --------------------------

    # Ensure dropdowns are loaded from a fresh connection/cursor in case the
    # original cursor/connection was closed during POST processing.
    dropdown_options_conn = create_db_connection()
    if not dropdown_options_conn:
        return "Database connection failed. Contact admin."

    dropdown_options_cursor = dropdown_options_conn.cursor()
    try:
        dropdown_options = fetch_dropdown_options(dropdown_options_cursor)
    finally:
        close_db_connection(dropdown_options_cursor, dropdown_options_conn)


    # Close connection after dropdowns are fetched
    close_db_connection(cursor, connection)
    print(dropdown_options)
    return render_template(
        'Bill Of Lading page/create_entry.html',
        error_message=error_message,
        **dropdown_options
    )

def run_background_procedures(del_note_no):
    conn = None
    cursor = None
    try:
        conn = create_db_connection()
        if not conn:
            print("Failed to create DB connection in background thread.")
            return

        cursor = conn.cursor()
        print(f"Running stored procedures for DelNoteNo {del_note_no}...")

        cursor.execute("EXEC [mkt].IGCreateTransportPO")
        cursor.execute("EXEC [mkt].SIGUpdateDelQuantities")
        cursor.execute("EXEC [mkt].SIGUpdateWeightTransport")
        cursor.execute("EXEC [mkt].[SIGUpdatePackagingCost]")
        cursor.execute("EXEC [mkt].[SIGUpdateWeightTransport]")

        conn.commit()
        print(f"Finished background procedures for DelNoteNo {del_note_no}")

    except Exception as e:
        print(f"Background error: {e}")

    finally:
        if cursor and conn:
            close_db_connection(cursor, conn)




@market_bp.route('/submission_success')
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

@market_bp.route('/api/save-form', methods=['POST'])
def save_form():
    form_data = request.json
    with open(DATA_FILE, 'w') as file:
        json.dump(form_data, file)
    return jsonify({"message": "Form data saved successfully!"}), 200


@market_bp.route('/api/load-form', methods=['GET'])
def load_form():
    try:
        with open(DATA_FILE, 'r') as file:
            form_data = json.load(file)
        return jsonify(form_data), 200
    except FileNotFoundError:
        return jsonify({"message": "No saved form data found."}), 404

@market_bp.route('/api/clear-saved-form', methods=['POST'])
def clear_saved_form():
    try:
        # Write an empty JSON object to ensure valid JSON structure
        with open(DATA_FILE, 'w') as file:
            json.dump({}, file)  # Use {} for an empty object or [] for an empty list

        return jsonify({"message": "Saved data cleared successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@market_bp.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for('index')))
    resp.set_cookie('remember_token', '', expires=0)  # Clear remember token cookie
    return resp

@market_bp.route('/check_session', methods=['GET'])
def check_session():
    if 'username' in session: 
        return jsonify({"session_active": True})
    return jsonify({"session_active": False})

@market_bp.route('/check_delivery_note', methods=['POST'])
def check_delivery_note():
    data = request.json
    del_note_no = data.get('ZZDelNoteNo')

    conn = create_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM [mkt].ZZDeliveryNoteHeader WHERE DelNoteNo = ?", (del_note_no,))
    exists = cursor.fetchone()[0] > 0

    conn.close()
    return jsonify({'exists': exists})

@market_bp.route("/get-last-sales-price", methods=["POST"])
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
        FROM [mkt]._uvMarketProductWhse 
        WHERE StockLink = ? AND WhseLink = ?
    """, (stock_link, whse_link))
    result = cursor.fetchone()

    if result:
        return jsonify({"lastSalesPrice": result[0]})
    else:
        return jsonify({"lastSalesPrice": None})

@market_bp.route("/get-default-transport-cost", methods=["POST"])
def get_default_transport_cost_api():
    """
    API endpoint to get the default transport cost based on agent, packhouse, and transporter.
    """
    data = request.json
    agent_code = data.get("agentCode")
    packhouse_code = data.get("packhouseCode") 
    transporter_code = data.get("transporterCode")

    if not agent_code or not packhouse_code or not transporter_code:
        return jsonify({"error": "Missing required parameters: agentCode, packhouseCode, transporterCode"}), 400

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # fetch agent destination
        query = """
        Select AgentDestination from [mkt]._uvMarketAgent
        Where DCLink = ?
        """
        cursor.execute(query, (agent_code,))
        destination_result = cursor.fetchone()
        default_cost = 0.0
        if destination_result and destination_result[0] is not None:
            destination = destination_result[0]
            query = """
            Select LastTransportCost from [mkt].[_uvLastTransportCost]
            where TransporterAccount = ? AND PackhouseLink = ? AND AgentDestination = ? 
            """
            cursor.execute(query, (transporter_code, packhouse_code, destination))
            result = cursor.fetchone()
            if result and result[0] is not None:
                default_cost = float(result[0])
            else:
                default_cost = 0
        else:
            default_cost = 0
        
        close_db_connection(cursor, conn)
        
        return jsonify({"defaultTransportCost": default_cost})
        
    except Exception as e:
        return jsonify({"error": "Failed to get default transport cost"}), 500


