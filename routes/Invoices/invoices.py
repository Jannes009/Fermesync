from flask import render_template, Blueprint, request, jsonify
import pypyodbc as odbc
from db import create_db_connection, close_db_connection
from routes.db_functions import agent_code_to_agent_name, get_stock_name, get_invoice_id, del_note_number_to_del_id

invoice_bp = Blueprint('invoice', __name__)

@invoice_bp.route('/create_invoice')
def invoice_page():
    return render_template('Invoice page/base.html')

# Function to get delivery note details, lines, and sales
def get_delivery_note_details(note_number, start_date, end_date):
    # Establish connection
    conn = create_db_connection()
    cursor = conn.cursor()

    print(start_date, end_date)
    if start_date == "":
        start_date = '1000/01/01'
    if end_date == "":
        end_date = '3000/01/01'

    # Step 1: Fetch the Delivery Note ID (DelIndex) and Market (DelMarketId)
    cursor.execute("""
        SELECT DelIndex, DeliClientId
        FROM dbo.ZZDeliveryNoteHeader
        WHERE DelNoteNo = ?
    """, (note_number,))
    header = cursor.fetchone()

    if header:
        del_index, del_client_id = header

        # find agent's agentComm and MarketComm
        cursor.execute("""
            SELECT marketComm, agentComm
            FROM _uvMarketAgent
            WHERE DCLink = ?
        """, (del_client_id,))
        commissions = cursor.fetchone()
        if (not commissions):
            print("No agent found")
            commissions = [0,0]


        client = agent_code_to_agent_name(del_client_id, cursor)

        # Step 2: Fetch all delivery note lines (DelLineIndex) with their Stock id (DelLineStockId)
        cursor.execute("""
            SELECT DelLineIndex, DelLineStockId, DelHeaderId
            FROM dbo.ZZDeliveryNoteLines
            WHERE DelHeaderId = ?
        """, (del_index,))
        lines = cursor.fetchall()

        # Prepare the results structure to store line and sales details
        result = {
            'note_number': note_number,
            'market_id': client[1],
            'market_comm': commissions[0],
            'agent_comm': commissions[1],
            'lines': []
        }

        

        # Step 3: For each delivery line, find the corresponding sales lines (SalesLineIndex, SalesAmnt)
        for line in lines:
            del_line_index, del_line_stock_id, del_header_id = line
            stock_name = get_stock_name(del_line_stock_id, cursor)

            # Step 3a: Fetch sales lines for the current delivery note line
            cursor.execute("""
                SELECT SalesLineIndex, SalesAmnt, SalesDate, SalesQty, SalesPrice
                FROM [dbo].[_uvMarketSales]
                WHERE SalesDelLineId = ? AND Invoiced = 'FALSE' AND SalesDate >= ? AND SalesDate <= ?
                ORDER BY SalesDate
            """, (del_line_index, start_date, end_date,))
            sales_lines = cursor.fetchall()

            # Add sales lines and amount details to the current line
            line_data = {
                'line_id': del_line_index,
                'stock_id': stock_name,
                'sales_lines': [{'sales_line_id': sales_line[0], 'amount': sales_line[1], 'date': sales_line[2], 'quantity': sales_line[3], 'price': sales_line[4]} for sales_line in sales_lines],
                'total_sales': sum(sale[1] for sale in sales_lines)  # Calculate the sum of sales amounts
            }
            if(sales_lines):
                result['lines'].append(line_data)
        close_db_connection(cursor, conn)
        if result['lines'] == []:
            return result, 310
        return result
    else:
        close_db_connection(cursor, conn)
        return None

@invoice_bp.route('/get_delivery_note_lines', methods=['POST'])
def get_delivery_note_lines():
    # Get the delivery note number from the POST request
    data = request.get_json()  # For handling JSON data
    note_number = data.get('note_number')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    # Fetch delivery note details and associated lines
    delivery_note_details = get_delivery_note_details(note_number, start_date, end_date)
    print(delivery_note_details)

    if delivery_note_details is None:
        return "No delivery header found with that number", 400
    elif isinstance(delivery_note_details, tuple) and delivery_note_details[1] == 310:
        return jsonify(delivery_note_details[0]), 310
    else:
        return jsonify(delivery_note_details)

    

@invoice_bp.route('/submit_invoice', methods=['POST'])
def submit_invoice():
    try:
        data = request.json
        print(data)

        # Extract data from request
        InvoiceDate = data.get('InvoiceDate')
        InvoiceNo = data.get('InvoiceNo')
        InvoiceDelNoteNo = data.get('InvoiceDelNoteNo')
        InvoiceQty = data.get('InvoiceQty')
        InvoiceGross = data.get('InvoiceGross')
        InvoiceTotalDeducted = data.get('InvoiceTotalDeducted')
        InvoiceMarketCommIncl = data.get('InvoiceMarketCommIncl')
        InvoiceAgentCommIncl = data.get('InvoiceAgentCommIncl')
        InvoiceOtherCostsIncl = data.get('InvoiceOtherCostsIncl')
        SalesLines = data.get('tickedLines')

        # Insert into database
        conn = create_db_connection()
        cursor = conn.cursor()

        DelNoteId = del_note_number_to_del_id(InvoiceDelNoteNo, cursor)
        print(DelNoteId)

        query = """
        Select [DeliClientId] From [dbo].[ZZDeliveryNoteHeader]
        Where [DelNoteNo] = ?
        """
        cursor.execute(query, (InvoiceDelNoteNo, )),
        clientId = cursor.fetchone()

        query = """
        INSERT INTO [dbo].[ZZInvoiceHeader] (
            [InvoiceDate], [InvoiceNo], [InvoiceDelNoteId], [InvoiceDelNoteNo],
            [InvoiceQty], [InvoiceGross], [InvoiceTotalDeducted],
            [InvoiceMarketCommIncl], [InvoiceAgentCommIncl], [InvoiceOtherCostsIncl], 
            [InvoiceiClientId]
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query, (
            InvoiceDate, InvoiceNo, DelNoteId[0], InvoiceDelNoteNo,
            InvoiceQty, InvoiceGross, InvoiceTotalDeducted,
            InvoiceMarketCommIncl, InvoiceAgentCommIncl, InvoiceOtherCostsIncl,
            clientId[0],
        ))

        headerId = get_invoice_id(InvoiceNo, cursor)

        for line in SalesLines:
            line = dict(line)
            print(headerId, type(headerId))
            query = """
            INSERT INTO [dbo].[ZZInvoiceLines] (
                [InvoiceHeaderId], [InvoiceSaleLineIndex] 
            ) VALUES (?, ?)
            """
            cursor.execute(query, (
                headerId, line['salesLineId'],
            ))

        # create invoice
        cursor.execute("EXEC [dbo].[SIGCreateSalesOrder]")

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})

    except odbc.IntegrityError as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': "This invoice is already captured. Please change the invoice number."})
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@invoice_bp.route('/get-tax-rate', methods=['GET'])
def get_tax_rate():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date parameter is required'}), 400

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        print(date_str)
        cursor.execute("EXEC SIGGetTaxRateByDate @InputDate = ?", [date_str])
        result = cursor.fetchone()

        if result:
            return jsonify({'date': date_str, 'tax_rate': float(result[0])})
        else:
            return jsonify({'date': date_str, 'message': 'No tax rate found for the given date'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        if 'conn' in locals():
            conn.close()