from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context, session
from db import create_db_connection
import pandas as pd
import os, logging, time
from selenium.webdriver.common.by import By
from routes.db_functions import get_stock_name
import pypyodbc
from db import initialize_driver

import_bp = Blueprint('import', __name__)

@import_bp.route('/main', methods=['GET'])
def import_page():
    return render_template('Import/import.html')

logging.basicConfig(level=logging.INFO)

def get_newest_downloaded_file(existing_files, directory, base_filename, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        current_files = set(os.listdir(directory))
        new_files = current_files - existing_files
        matching_files = [f for f in new_files if f.startswith(base_filename)]
        if matching_files:
            return os.path.join(directory, sorted(matching_files, key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)[0])
        time.sleep(1)
    return None

@import_bp.route('/get_imported_results', methods=['GET'])
def get_import_results():
    conn = create_db_connection()
    cursor = conn.cursor()

    # Get unique records from MarketData
    cursor.execute("""
        SELECT DISTINCT
            SupplierRef, ConsignmentID, Product, Variety, Size, Class, Mass_kg, QtySent
        FROM MarketData
    """)
    summary_data = cursor.fetchall()

    results = []
    for row in summary_data:
        supplier_ref, consignment_id, product, variety, size, class_, mass_kg, qty_sent = row

        # Check if ConsignmentID exists in ZZDeliveryNoteLines
        cursor.execute("SELECT COUNT(*) FROM ZZDeliveryNoteLines WHERE ConsignmentID = ?", (consignment_id,))
        match_count = cursor.fetchone()[0]
        matched_status = "Yes" if match_count > 0 else "No"

        # Get the top MatchCount and MaxMatchDuplicate from PotentialMatches
        cursor.execute("""
            SELECT 
                MAX(MatchCount) AS TopMatchCount,
                CASE 
                    WHEN COUNT(*) > 1 THEN 'Yes' 
                    ELSE 'No' 
                END AS MaxMatchDuplicate
            FROM PotentialMatches
            WHERE ConsignmentID = ?
        """, (consignment_id,))
        match_result = cursor.fetchone()
        top_match_count = match_result[0] if match_result[0] is not None else 0
        max_match_duplicate = match_result[1]

        results.append({
            "SupplierRef": supplier_ref,
            "ConsignmentID": consignment_id,
            "Product": product,
            "Variety": variety,
            "Size": size,
            "Class": class_,
            "Mass_kg": mass_kg,
            "QtySent": qty_sent,
            "Matched": matched_status,
            "TopMatchCount": top_match_count,
            "MaxMatchDuplicate": max_match_duplicate
        })

    conn.close()
    return jsonify(results)


@import_bp.route('/get_dockets/<consignment_id>', methods=['GET'])
def get_dockets(consignment_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DocketNumber, QtySold, Price, SalesValue, DateSold
        FROM MarketData
        WHERE ConsignmentID = ?
    """, (consignment_id,))

    dockets = cursor.fetchall()
    conn.close()

    return jsonify([{
        "DocketNumber": row[0],
        "QtySold": row[1],
        "Price": row[2],
        "SalesValue": row[3],
        "Date": row[4], 
    } for row in dockets])



@import_bp.route('/auto_import', methods=['GET'])
def auto_import():
    def generate_status():
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date or not end_date:
            yield "data: ERROR: Missing start_date or end_date.\n\n"
            return

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
            yield "data: Report request submitted...\n\n"

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

        try:
            yield "data: Inserting data...\n\n"
            docket_count = insert_data(downloaded_file)  # Modify `insert_data` to return count
            yield f"data: Dockets imported: {docket_count}\n\n"
            yield "data: SUCCESS: Data import completed successfully!\n\n"
        except Exception as e:
            yield f"data: ERROR: {str(e)}\n\n"

    return Response(stream_with_context(generate_status()), content_type="text/event-stream")


@import_bp.route('/upload_excel', methods=['POST'])
def upload_excel():
    file = request.files.get('file')
    if not file:
        return jsonify({"results": [{"file": "N/A", "status": "Failed", "message": "No file selected!"}]}), 400

    try:
        count = insert_data(file)  # Import the data and get the count of inserted rows

        return jsonify({
            "results": [{
                "file": file.filename,
                "status": "Success" if count > 0 else "Failed",
                "message": f"{count} lines imported successfully!" if count > 0 else "No lines imported"
            }]
        }), 200

    except Exception as e:
        return jsonify({
            "results": [{
                "file": file.filename if file else "Unknown",
                "status": "Failed",
                "message": str(e)
            }]
        }), 500



def insert_data(file):
    df = pd.read_excel(file, skiprows=9)
    df.columns = [
        'Market', 'Agent', 'Product', 'Variety', 'Size', 'Class', 'Container',
        'Mass_kg', 'Count', 'DeliveryID', 'ConsignmentID', 'SupplierRef',
        'QtySent', 'QtyAmendedTo', 'QtySold', 'DeliveryDate', 'DateSold',
        'DatePaid', 'DocketNumber', 'PaymentReference', 'MarketAvg', 'Price', 'SalesValue'
    ]
    
    date_columns = ['DeliveryDate', 'DateSold', 'DatePaid']
    for col in date_columns:
        df[col] = pd.to_datetime(df[col], format='%m-%d-%y', errors='coerce')

    conn = create_db_connection()
    cursor = conn.cursor()

    df['DocketNumber'] = df['DocketNumber'].astype(str).str.replace('*', '-', regex=False)
    df['SupplierRef'] = df['SupplierRef'].astype(str).str.replace('*', '-', regex=False)
    df['PaymentReference'] = df['PaymentReference'].astype(str).str.replace('*', '-', regex=False)

    cursor.execute("TRUNCATE TABLE MarketData")
    
    count = 0
    for _, row in df.iterrows():
        count += 1
        row_data = {col: (None if pd.isna(val) else val) for col, val in row.items()}
        cursor.execute("""
            INSERT INTO MarketData (
                Market, Agent, Product, Variety, Size, Class, Container, Mass_kg, Count,
                DeliveryID, ConsignmentID, SupplierRef, QtySent, QtyAmendedTo, QtySold,
                DeliveryDate, DateSold, DatePaid, DocketNumber, PaymentReference, 
                MarketAvg, Price, SalesValue
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(row_data.values()))

    conn.commit()
    cursor.close()
    conn.close()

    return count  # Return number of inserted rows

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


def get_consignment_details(consignment_id):
    query = """
    SELECT DISTINCT 
        ImportProduct, ImportVariety, ImportClass, ImportMass, ImportSize, ImportQty
    FROM PotentialMatches
    WHERE ConsignmentID = ?
    """
    
    matches_query = """
    SELECT 
        ProductNoteNo, MarketNoteNo, DelLineIndex, ConsignmentID,
        LineProduct, ImportProduct, LineMass, ImportMass, 
        LineClass, ImportClass, LineSize, ImportSize, 
        LineVariety, ImportVariety, LineQty, ImportQty, MatchCount, DuplicateMaxMatch,
        LineBrand  -- Add this column to the query
    FROM PotentialMatches
    WHERE ConsignmentID = ?
    ORDER BY MatchCount DESC
    """

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Get consignment details
        cursor.execute(query, (consignment_id,))
        consignment = cursor.fetchone()

        if not consignment:
            return jsonify({"error": "Consignment not found"}), 404

        consignment_details = {
            "ImportProduct": consignment[0],
            "ImportVariety": consignment[1],
            "ImportClass": consignment[2],
            "ImportMass": consignment[3],
            "ImportSize": consignment[4],
            "ImportQty": consignment[5]
        }

        # Get top matches
        cursor.execute(matches_query, (consignment_id,))
        matches = cursor.fetchall()

        matches_list = [
            {
                "ProductNoteNo": row[0],
                "MarketNoteNo": row[1],
                "DelLineIndex": row[2],
                "ConsignmentID": row[3],
                "LineProduct": row[4],
                "ImportProduct": row[5],
                "LineMass": row[6],
                "ImportMass": row[7],
                "LineClass": row[8],
                "ImportClass": row[9],
                "LineSize": row[10],
                "ImportSize": row[11],
                "LineVariety": row[12],
                "ImportVariety": row[13],
                "LineQty": row[14],
                "ImportQty": row[15],
                "MatchCount": row[16],
                "DuplicateMaxMatch": row[17],
                "LineBrand": row[18]  # Add this line to handle the new field
            }
            for row in matches
        ]

        return jsonify({
            "consignment_details": consignment_details,
            "matches": matches_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@import_bp.route("/get_consignment_details", methods=["GET"])
def fetch_consignment_details():
    consignment_id = request.args.get("consignment_id")

    if not consignment_id:
        return jsonify({"error": "Consignment ID is required"}), 400

    return get_consignment_details(consignment_id)
