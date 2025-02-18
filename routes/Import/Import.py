from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import create_db_connection, initialize_driver
import pandas as pd
import pypyodbc
from routes.db_functions import get_stock_name
from selenium.webdriver.common.by import By
import time
import os, logging

import_bp = Blueprint('import', __name__)

# Import Page
@import_bp.route('/import_page', methods=['GET'])
def import_page():
    print("succes2")
    return render_template('Import/import.html')


logging.basicConfig(level=logging.INFO)

def get_newest_downloaded_file(existing_files, directory, base_filename, timeout=30):
    """Tracks new downloads by comparing files before and after download."""

    start_time = time.time()
    while time.time() - start_time < timeout:
        current_files = set(os.listdir(directory))
        new_files = current_files - existing_files  # Find newly added files

        # Check if any new files match the expected pattern
        matching_files = [f for f in new_files if f.startswith(base_filename)]
        if matching_files:
            # Sort by modification time and return the most recent one
            return os.path.join(directory, sorted(matching_files, key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)[0])

        time.sleep(1)  # Wait and check again

    return None  # Return None if no new file appears within the timeout

from flask import Response, stream_with_context

@import_bp.route('/auto_import', methods=['GET', 'POST'])
def auto_import():
    """Automates the report import process from the CRM with real-time updates."""

    def generate_status():
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # List existing files before downloading
        download_folder = r"C:\\Users\\kapok\\Downloads"
        existing_files = set(os.listdir(download_folder))

        yield "data: Connecting to Technofresh...\n\n"
        driver = initialize_driver()

        if not driver:
            yield "data: ERROR: Failed to connect.\n\n"
            return
        
        try:
            yield "data: Navigating to report download page...\n\n"
            driver.get("https://crm.technofresh.co.za/reports/view/8/xls")

            driver.execute_script("document.getElementsByName('from_date')[0].value = arguments[0]", start_date)
            driver.execute_script("document.getElementsByName('to_date')[0].value = arguments[0]", end_date)

            driver.find_element(By.NAME, "submit").click()
            yield "data: Report request submitted.\n\n"

            # Wait for the file to download
            base_filename = "Excel_Daily_Sales_Details_Report_"
            yield "data: Waiting for file to download...\n\n"
            
            downloaded_file = get_newest_downloaded_file(existing_files, download_folder, base_filename, timeout=30)

            if not downloaded_file:
                yield "data: ERROR: File download failed.\n\n"
                return

            yield f"data: File downloaded: {downloaded_file}\n\n"

        except Exception as e:
            yield f"data: ERROR: {str(e)}\n\n"
            return

        finally:
            driver.quit()

        # Process the downloaded file
        try:
            yield "data: Inserting data...\n\n"
            insert_data(downloaded_file)
            yield "data: Adding consignments...\n\n"
            add_consignments()
            yield "data: Adding sales...\n\n"
            add_sales()
            yield "data: SUCCESS: Data import completed successfully!\n\n"
        except Exception as e:
            yield f"data: ERROR: {str(e)}\n\n"

    return Response(stream_with_context(generate_status()), content_type="text/event-stream")



@import_bp.route('/upload_excel', methods=['POST'])
def upload_excel():
    file = request.files.get('file')

    insert_data(file)
    add_consignments()
    add_sales()

    return redirect(url_for('import.import_page'))

def insert_data(file):
    if not file:
        flash('No file selected!', 'error')
        return redirect(url_for('import.import_page'))
    
    # Read Excel file into a DataFrame
    df = pd.read_excel(file, skiprows=9)

    # Rename columns to match SQL table column names
    df.columns = [
        'Market', 'Agent', 'Product', 'Variety', 'Size', 'Class', 'Container',
        'Mass_kg', 'Count', 'DeliveryID', 'ConsignmentID', 'SupplierRef',
        'QtySent', 'QtyAmendedTo', 'QtySold', 'DeliveryDate', 'DateSold',
        'DatePaid', 'DocketNumber', 'PaymentReference', 'MarketAvg', 'Price', 'SalesValue'
    ]

    # Ensure date columns are formatted correctly
    date_columns = ['DeliveryDate', 'DateSold', 'DatePaid']
    for col in date_columns:
        df[col] = pd.to_datetime(df[col], format='%m-%d-%y', errors='coerce')

    # Connect to SQL Server
    conn = create_db_connection()
    cursor = conn.cursor()
    count = 0

    # Remove unwanted special characters from string columns (example for a specific column)
    df['DocketNumber'] = df['DocketNumber'].str.replace('*', '-', regex=False)
    df['SupplierRef'] = df['SupplierRef'].str.replace('*', '-', regex=False)
    df['PaymentReference'] = df['PaymentReference'].str.replace('*', '-', regex=False)

    cursor.execute("TRUNCATE TABLE MarketData")
    # Insert data into SQL table
    for _, row in df.iterrows():
        count += 1
        # replace nan with valid data(Null)
        row_data = {col: (None if pd.isna(val) else val) for col, val in row.items()}

        cursor.execute(
            """
            INSERT INTO MarketData (
                Market, Agent, Product, Variety, Size, Class, Container,
                Mass_kg, Count, DeliveryID, ConsignmentID, SupplierRef,
                QtySent, QtyAmendedTo, QtySold, DeliveryDate, DateSold,
                DatePaid, DocketNumber, PaymentReference, MarketAvg, Price, SalesValue
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (row_data['Market'], row_data['Agent'], row_data['Product'], row_data['Variety'],
            row_data['Size'], row_data['Class'], row_data['Container'], row_data['Mass_kg'],
            row_data['Count'], row_data['DeliveryID'], row_data['ConsignmentID'], row_data['SupplierRef'],
            row_data['QtySent'], row_data['QtyAmendedTo'], row_data['QtySold'], row_data['DeliveryDate'],
            row_data['DateSold'], row_data['DatePaid'], row_data['DocketNumber'], row_data['PaymentReference'],
            row_data['MarketAvg'], row_data['Price'], row_data['SalesValue'],)
        )


    conn.commit()
    cursor.close()
    conn.close()
    
    if count > 0:
        flash(f'{count} lines imported successfully!', 'success')
    else:
        flash(f'No lines imported', 'danger')

def add_consignments():
    matched = False
    new_consignment_matches = []
    # Connect to SQL Server
    conn = create_db_connection()
    cursor = conn.cursor()
    if conn:
        print("Database connection successful")
    else:
        print("Database connection failed")

    # Find Delivery Note Lines without ConsignmentID
    cursor.execute("""
        SELECT DelLineIndex
        FROM ZZDeliveryNoteLines 
        WHERE ConsignmentID IS NULL
    """)
    
    lines_without_consig = cursor.fetchall()
    
    # Iterate over lines without ConsignmentID
    for line in lines_without_consig:
        del_line_index = line[0]
        
        # Check if the Delivery Note Line's ID exists in the MarketDataProductView
        cursor.execute("""
            SELECT ConsignmentID 
            FROM [dbo].[MarketDataProductView]
            WHERE DelLineIndex = ?
        """, (del_line_index,))
        
        result = cursor.fetchone()
        
        # If a ConsignmentID is found in the view, update the Delivery Note Line
        if result:
            matched = True
            new_consignment_id = result[0]
            new_consignment_matches.append(del_line_index)

            # Update ConsignmentID in DeliveryNoteLines
            cursor.execute("""
                UPDATE ZZDeliveryNoteLines
                SET ConsignmentID = ?
                WHERE DelLineIndex = ?
            """, (new_consignment_id, del_line_index))
            print(f"Updated ConsignmentID for DelLineIndex {del_line_index}.")

    conn.commit()
    cursor.close()
    conn.close()
    session['consignment_matches'] = new_consignment_matches

    if matched:
        flash(f'{len(new_consignment_matches)} consignmentsID\'s were successfully matched', 'success')
    else:
        flash('No new delivery note line matches', 'warning')


def add_sales():
    error_occured = False
    no_match = False
    success = False
    
    errors = []
    no_matches = [[],[]]
    succesess = []
    # Connect to SQL Server
    conn = create_db_connection()
    cursor = conn.cursor()

    # Select all the relevant data from MarketData table
    market_data_query = """
        SELECT ConsignmentID, QtySold, Price, DateSold, DocketNumber, Id, SupplierRef
        FROM MarketData
    """
    cursor.execute(market_data_query)
    result = cursor.fetchall()

    # Loop over the rows from the MarketData table
    for row in result:
        consignment_id = row[0]
        qty_sold = row[1]
        price = row[2]
        date_sold = row[3]
        docket_number = row[4]
        data_id = row[5]

        # Check if ConsignmentID exists in ZZDeliveryNoteLines
        check_query = """
            SELECT DelLineIndex, DelLineStockId 
            FROM ZZDeliveryNoteLines 
            WHERE ConsignmentID = ?
        """
        cursor.execute(check_query, (consignment_id,))
        check_result = cursor.fetchone()

        # If a matching row is found in ZZDeliveryNoteLines, insert into ZZAutoSales
        if check_result:
            del_line_index = check_result[0]
            try:
                # Insert into ZZSalesLines
                insert_query = """
                    INSERT INTO ZZSalesLines (SalesQty, SalesPrice, 
                    SalesDate, DocketNumber, SalesAmnt, SalesStockId, SalesDelLineId, AutoSale)
                    VALUES (?,?,?,?,?,?,?,?)
                """
                cursor.execute(insert_query, (
                    qty_sold, price,
                    date_sold, docket_number, qty_sold * price, check_result[1], del_line_index, 1
                ))
                success = True
                succesess.append(data_id)
            except pypyodbc.IntegrityError as e:
                errors.append(data_id)
                error_occured = True
        else:
            no_match = True
            no_matches[0].append(data_id)
            no_matches[1].append(has_header(row[6]))

    cursor.commit()
    session['succesess'] = succesess
    session['no_matches'] = no_matches
    session['errors'] = errors
        
    if(success):
        flash(f'<a href="{url_for("import.show_results", result_type="success")}" class="alert-link">'
        f'{len(succesess)} transactions have been successfully added!</a>', 'success')
    else:
        flash('No transactions added', 'warning')
    if(no_match):
        flash(f'<a href="{url_for("import.show_results", result_type="no_match")}" class="alert-link">'
        f'{len(no_matches[0])} transactions have not been matched</a>', 'warning')
    if error_occured:
        flash(f'<a href="{url_for("import.show_results", result_type="error")}" class="alert-link">'
        f'{len(errors)} transactions were already added previously</a>', 'danger')

@import_bp.route('/show_results/<result_type>')
def show_results(result_type):
    no_matches = False
    ids = []

    # Map the result type to the corresponding list
    if result_type == "success":
        ids = session.get("succesess") or []
        title = "Successfully Added Transactions"
        explanation = "These transactions were successfully created in the database:"
    elif result_type == "no_match":
        ids = session.get("no_matches") or [[], []]  # Ensure it has two lists
        title = "Transactions Not Matched"
        explanation = "These transactions didn't have a matching Delivery Note line:"
        no_matches = True
    elif result_type == "error":
        ids = session.get("errors") or []
        title = "Errors in Transactions"
        explanation = "These transactions were already previously added to the database and can't be added again:"
    else:
        title = "Unknown Results"
        explanation = "An unknown error occurred."

    results = []

    # Ensure there are IDs before querying the database
    if ids:
        conn = create_db_connection()
        cursor = conn.cursor()

        if no_matches and ids[0]:  # Ensure ids[0] is not empty
            placeholders = ",".join("?" * len(ids[0]))  # Create placeholders dynamically
            query = f"""
                SELECT 
                    ConsignmentID, SupplierRef, Product, Variety, Size, Class, Mass_kg, QtySold, Price, QtySent
                FROM MarketData
                WHERE Id IN ({placeholders})
            """
            cursor.execute(query, ids[0])
            fetched_results = cursor.fetchall()

            # Append ids[1] to each row safely
            results = [row + (ids[1][index],) for index, row in enumerate(fetched_results)]
        elif not no_matches and ids:  # Regular case
            placeholders = ",".join("?" * len(ids))
            query = f"""
                SELECT 
                    ConsignmentID, SupplierRef, Product, Variety, Size, Class, Mass_kg, QtySold, Price, QtySent
                FROM MarketData
                WHERE Id IN ({placeholders})
            """
            cursor.execute(query, ids)
            results = cursor.fetchall()

        cursor.close()
        conn.close()

    print(result_type)
    # Render the results page with the fetched data
    return render_template('Import/results.html', results=results, title=title, explanation=explanation, no_matches=no_matches, result_type=result_type)



def has_header(header):
    conn = create_db_connection()
    cursor = conn.cursor()
    header_id = header[5:]
    query = """
    Select * from [dbo].[ZZDeliveryNoteHeader]
    WHERE DelNoteNo = ?
    """
    cursor.execute(query, (header_id,))
    check_result = cursor.fetchone()
    if check_result:
        cursor.close()
        conn.close()
        return True
    else:
        cursor.close()
        conn.close()
        return False
    
@import_bp.route('/manual_matching/<string:consignment_id>')
def manual_matching(consignment_id):
    print(f"Consignment ID: {consignment_id}")
    conn = create_db_connection()
    cursor = conn.cursor()

    # Query to fetch details from MarketData
    query = """
    SELECT 
        ConsignmentID, SupplierRef, Product, Variety, Size, Class, Mass_kg, QtySent, SupplierRef
    FROM MarketData
    WHERE ConsignmentID = ?
    """
    cursor.execute(query, (consignment_id,))
    market_data = cursor.fetchone()
    header_number = market_data[8][5:]

    if not market_data:
        return "Consignment ID not found", 404

    query = """
    Select * from [dbo].[ZZDeliveryNoteHeader]
    WHERE DelNoteNo = ?
    """
    cursor.execute(query, (header_number,))
    header_id = cursor.fetchone()

    # Query to fetch details from ZZDeliveryNoteLines
    del_query = """
    SELECT 
        DelHeaderId, DelLineIndex, DelLineStockId, DelLineQuantityBags, ConsignmentID
    FROM ZZDeliveryNoteLines
    WHERE DelHeaderId = ?
    """
    cursor.execute(del_query, (header_id[0],))
    del_lines = cursor.fetchall()
    result = []
    for row in del_lines:
        if row[4] == None:
            stock_description = get_stock_name(row[2], cursor)
            # Split the description into its parts
            description_parts = stock_description[0].split('-')
            result.append([header_number] + description_parts + [row[3]] + [row[1]])

    cursor.close()
    conn.close()

    # Return the results to the template
    return render_template('Import/manual_matching.html', market_data=market_data, del_lines=result)

@import_bp.route('/create_match', methods=['POST'])
def create_match():
    # Extract data from the AJAX request
    data = request.json
    consignment_id = data.get('consignment_id')
    line_id = data.get('line_id')

    conn = create_db_connection()
    cursor = conn.cursor()

    query = """
    UPDATE [dbo].[ZZDeliveryNoteLines]
    SET ConsignmentID = ?
    WHERE DelLineIndex = ?
    """
    cursor.execute(query, (consignment_id, line_id,))
    cursor.commit()
    add_consignments()
    add_sales()

    print("Success")
    return redirect(url_for('import.import_page'))


@import_bp.route('/show_matches', methods=['GET', 'POST'])
def show_matches():
    # Get the selected fields from the form
    selected_fields = request.form.getlist('fields') 

    if request.method == 'GET':
        selected_fields = ['Product', 'Mass', 'Class', 'Size', 'Quantity']

    print(selected_fields, request.method)
    # Base query
    base_query = """
    SELECT ProductNoteNo, DelLineIndex, LineProduct, LineMass, LineClass, LineSize, LineVariety,  LineQty, 
           MarketNoteNo, ConsignmentID, ImportProduct, ImportMass, ImportClass, ImportSize, ImportVariety, ImportQty
    FROM [dbo].[PotentialMatches]
    WHERE 1=1
    """

    # Add conditions based on selected fields
    if 'Product' in selected_fields:
        base_query += " AND LineProduct = ImportProduct"
    if 'Mass' in selected_fields:
        base_query += " AND LineMass = ImportMass"
    if 'Class' in selected_fields:
        base_query += " AND LineClass = ImportClass"
    if 'Size' in selected_fields:
        base_query += " AND LineSize = ImportSize"
    if 'Variety' in selected_fields:
        base_query += " AND LineVariety = ImportVariety"
    if 'Quantity' in selected_fields:
        base_query += " AND LineQty = ImportQty"

    # Execute the query
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute(base_query)
        results = cursor.fetchall()
        conn.close()

        # Render the results in a template or return as JSON
        return render_template('Import/consignment_matches.html', results=results, selected_fields=selected_fields)
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@import_bp.route('/update_match', methods=['POST'])
def update_match():
    data = request.json
    print("Inserting the following data: ", data)
    if not data or 'matches' not in data:
        return jsonify({'message': 'Invalid request'}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    for match in data['matches']:
        print(match)
        cursor.execute(
            "UPDATE ZZDeliveryNoteLines SET ConsignmentID = ? WHERE DelLineIndex = ?",
            (match['consignmentID'], match['lineId']))
    print("These matches were inserted:", data['matches'])
    cursor.commit()
    add_sales()
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Matches updated successfully'})
