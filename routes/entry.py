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
        'ZZTransporterCode', 'ZZPalletsOut', 'ZZPalletsBack', 'ZZMarket'
    ]}

def fetch_lines_data(request_form):
    return {
        'products': request_form.getlist('ZZProduct[]'),
        'quantities': request_form.getlist('ZZQuantityBags[]'),
        'prices': request_form.getlist('ZZEstimatedPrice[]'),
        'comments': request_form.getlist('ZZComments[]')
    }

def store_header(cursor, form_data):
    cursor.execute("""
        INSERT INTO ZZDeliveryNoteHeader 
        (DeliClientId, DelNoteNo, DelDate, DelFarmId, DelTransporter, DelPalletsOut, DelPalletsIn, DelMarketId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, tuple(form_data.values()))
    cursor.connection.commit()

def store_lines(cursor, header_id, line_data, linesId=None):
    total_quantity = 0
    count = 0
    for product, quantity, price, comments, in zip(
        line_data['products'], line_data['quantities'], line_data['prices'], line_data['comments']):
        total_quantity += float(quantity)
        if linesId == None or len(linesId) <= count:
            cursor.execute("""
                INSERT INTO ZZDeliveryNoteLines 
                (DelHeaderId, DelLineStockId, DelLineQuantityBags, DelLinePriceEstimate, DelLineComment)
                VALUES (?, ?, ?, ?, ?)
            """, (header_id, product, quantity, price, comments))
        else:
            
            cursor.execute("""
                        UPDATE ZZDeliveryNoteLines 
                        SET DelLineStockId = ?, DelLineQuantityBags = ?, DelLinePriceEstimate = ?, DelLineComment = ?
                        WHERE DelLineIndex = ?
            """, (product, quantity, price, comments, linesId[count]))
        count+=1
    cursor.connection.commit()
    return total_quantity

def update_header_quantity(cursor, header_id, total_quantity):
    cursor.execute("""
        UPDATE ZZDeliveryNoteHeader SET DelQuantityBags = ? WHERE DelIndex = ?
    """, (total_quantity, header_id))
    cursor.connection.commit()

def fetch_entry(cursor, entry_id):
    cursor.execute("SELECT * FROM ZZDeliveryNoteHeader WHERE DelIndex = ?", (entry_id,))
    return cursor.fetchone()

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

            session['last_entry_id'] = header_id
            print(header_id, session.get('last_entry_id'))
            return redirect(url_for('entry.create_entry'))

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
    last_entry_id = session.get('last_entry_id')
    if not last_entry_id:
        return render_template('Transition pages/submission_success.html', message="No recent entry found.")
    return render_template('Transition pages/submission_success.html',
                           message="Entry submitted successfully!",
                           last_entry_id=last_entry_id)

@entry_bp.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
def edit_entry(entry_id):
    error_message = None
    form_data = None
    connection = create_db_connection()
    cursor = connection.cursor()

    # check that no sales had been made for delivery note
    # cursor.execute("""
    #     Select TotalQtySold from [dbo].[_uvDelQuantitiesHeader]
    #     Where DelHeaderId = ?
    # """, (entry_id,))
    # salesQty = cursor.fetchone()
    # if salesQty[0] > 0:
    #     return render_template('Transition pages/submission_success.html',
    #                        message="Entry already have sales. Cannot be edited",
    #                        last_entry_id=0)

    print("Entry edited")
    if request.method == 'POST':
        try:
            form_data = fetch_header_data(request.form)
            lines_data = fetch_lines_data(request.form)

            cursor.execute("""
                UPDATE ZZDeliveryNoteHeader
                SET DeliClientId = ?, DelNoteNo = ?, DelDate = ?, DelFarmId = ?, DelTransporter = ?, 
                    DelPalletsOut = ?, DelPalletsIn = ?, DelMarketId = ?
                WHERE DelIndex = ?
            """, (*form_data.values(), entry_id))
            cursor.connection.commit()

            cursor.execute("SELECT * FROM ZZDeliveryNoteLines WHERE DelHeaderId = ?", (entry_id,))
            rows = cursor.fetchall()  # Fetch all rows once

            if rows:  # Check if rows exist
                lineIds = [row[0] for row in rows]  # Extract DelLineIndex from rows
            else:
                lineIds = None  # Assign an empty list if no rows are returned

            # cursor.execute("DELETE FROM ZZDeliveryNoteLines WHERE DelHeaderId = ?", (entry_id,))  
            total_quantity = store_lines(cursor, entry_id, lines_data, lineIds)
            update_header_quantity(cursor, entry_id, total_quantity)

            session['last_entry_id'] = entry_id
            return redirect(url_for('entry.submission_success'))

        except odbc.IntegrityError as e:
            error_data = integrity_error(e, request.form)
            error_message = error_data["error_message"]
            form_data = error_data["form_data"]

    entry_data = fetch_entry(cursor, entry_id)
    if not entry_data:
        return render_template('Transition pages/submission_success.html', message="Entry not found!")

    form_data = {
        'ZZDelNoteNo': entry_data[2],
        'ZZDelDate': entry_data[1],
        'ZZAgentName': agent_code_to_agent_name(entry_data[3], cursor),
        'ZZProductionUnitCode': project_link_to_production_unit_name(entry_data[5], cursor),
        'ZZTransporterCode': transporter_account_to_transporter_name(entry_data[6], cursor),
        'ZZPalletsOut': entry_data[7],
        'ZZPalletsBack': entry_data[8],
        'ZZMarket': market_Id_to_market_name(entry_data[4], cursor),
        'ZZTotalQty': entry_data[9],
    }

    rows = fetch_lines(cursor, entry_id)
    product_quantity_pairs = [(row[2], row[5], row[6], row[7], row[0]) for row in rows]
    print(product_quantity_pairs)

    dropdown_options = fetch_dropdown_options(cursor)
    close_db_connection(cursor, connection)

    return render_template('Bill Of Lading Page/create_entry.html',
                           error_message=error_message,
                           form_data=form_data,
                           product_quantity_pairs=product_quantity_pairs,
                           **dropdown_options)

@entry_bp.route('/delete-row', methods=['POST'])
def delete_row():
    data = request.json
    row_id = data.get('id')


    if not row_id:
        return "Row ID is required.", 400
    
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("Delete From ZZDeliveryNoteLines Where DelLineIndex = ?", (row_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return "Row deleted successfully.", 200

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
    if 'username' in session:  # Replace 'user_id' with your session key for the logged-in user
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