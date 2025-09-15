from flask import render_template, Blueprint, request, jsonify
import pypyodbc as odbc
from db import create_db_connection, close_db_connection
from routes.db_functions import agent_code_to_agent_name, get_stock_name, get_invoice_id, del_note_number_to_del_id
from auth import role_required

invoice_bp = Blueprint('invoice', __name__)

@invoice_bp.route('/create_sales_order')
@role_required()
def invoice_page():
    return render_template('Invoice page/base.html')

def get_delivery_note_details(note_number):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            HEA.DelNoteNo,
            AGENT.AgentName,
            PROD.ProductDescription,
            PRODUN.ProdUnitName,
            SALLIN.SalesQty,
            SALLIN.SalesPrice,
            SALLIN.DiscountAmnt,
            SALLIN.SalesAmnt,
            LIN.DelLineIndex,
            LIN.DelLineStockId,
            HEA.DeliClientId,
            SALLIN.SalesLineIndex,
            SALLIN.SalesDate
        FROM ZZDeliveryNoteHeader HEA
        JOIN (SELECT DCLink, Name AgentName, MarketComm, AgentComm FROM _uvMarketAgent) AGENT 
            ON AGENT.DCLink = HEA.DeliClientId
        JOIN (SELECT DelHeaderId, DelLineIndex, DelLineFarmId, DelLineStockId 
              FROM ZZDeliveryNoteLines) LIN 
            ON LIN.DelHeaderId = HEA.DelIndex
        JOIN (SELECT StockLink, ProductDescription FROM _uvMarketProduct) PROD 
            ON PROD.StockLink = LIN.DelLineStockId
        JOIN (SELECT ProjectLink, ProdUnitName FROM _uvMarketProdUnit) PRODUN 
            ON PRODUN.ProjectLink = LIN.DelLineFarmId
        LEFT JOIN (SELECT SalesDelLineId, SalesQty, SalesPrice, DiscountAmnt, SalesAmnt, SalesLineIndex, SalesDate 
                   FROM ZZSalesLines) SALLIN 
            ON SALLIN.SalesDelLineId = LIN.DelLineIndex
        WHERE HEA.DelNoteNo = ?
    """, (note_number,))
    rows = cursor.fetchall()

    if not rows:
        close_db_connection(cursor, conn)
        return None

    # Header info from first row
    del_note_no = rows[0][0]
    agent_name = rows[0][1]
    del_client_id = rows[0][10]

    # Commissions
    cursor.execute("""
        SELECT MarketComm, AgentComm
        FROM _uvMarketAgent
        WHERE DCLink = ?
    """, (del_client_id,))
    commissions = cursor.fetchone() or (0, 0)
    market_comm, agent_comm = commissions

    result = {
        "note_number": del_note_no,
        "market_id": agent_name,
        "production_units": list({r[3] for r in rows if r[3]}),  # ProdUnitName
        "market_comm": market_comm,
        "agent_comm": agent_comm,
        "lines": []
    }

    # Group by delivery line
    lines_dict = {}
    for row in rows:
        product_desc = row[2]
        prod_unit = row[3]
        qty = row[4]
        price = row[5]
        discount = row[6]
        amount = row[7]
        line_id = row[8]
        stock_id = row[9]
        sales_line_id = row[11]
        sales_date = row[12]

        if line_id not in lines_dict:
            lines_dict[line_id] = {
                "line_id": line_id,
                "stock": product_desc,
                "prod_unit": prod_unit,
                "sales_lines": []
            }

        if qty is not None:
            lines_dict[line_id]["sales_lines"].append({
                "sales_line_id": sales_line_id,
                "date": sales_date,
                "quantity": qty,
                "price": price,
                "discount": discount,
                "amount": amount
            })

    result["lines"] = list(lines_dict.values())

    close_db_connection(cursor, conn)
    return result



@invoice_bp.route('/get_delivery_note_lines', methods=['POST'])
@role_required()
def get_delivery_note_lines():
    # Get the delivery note number from the POST request
    data = request.get_json()  # For handling JSON data
    note_number = data.get('note_number')

    # Fetch delivery note details and associated lines
    delivery_note_details = get_delivery_note_details(note_number)

    if delivery_note_details is None:
        return "No delivery header found with that number", 400
    elif isinstance(delivery_note_details, tuple) and delivery_note_details[1] == 310:
        return jsonify(delivery_note_details[0]), 310
    else:
        return jsonify(delivery_note_details)

    

@invoice_bp.route('/submit_invoice', methods=['POST'])
@role_required()
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
        TaxRate = data.get('TaxRate')
        print(InvoiceDate, InvoiceNo, InvoiceDelNoteNo, InvoiceQty, InvoiceGross, InvoiceTotalDeducted, InvoiceMarketCommIncl, InvoiceAgentCommIncl, InvoiceOtherCostsIncl, SalesLines, TaxRate)
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
            [InvoiceiClientId], [InvoiceTaxRate]
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query, (
            InvoiceDate, InvoiceNo, DelNoteId[0], InvoiceDelNoteNo,
            InvoiceQty, InvoiceGross, InvoiceTotalDeducted,
            InvoiceMarketCommIncl, InvoiceAgentCommIncl, InvoiceOtherCostsIncl,
            clientId[0], TaxRate,
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
        conn.commit()
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
@role_required()
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

@invoice_bp.route('/check_invoice_no', methods=['POST'])
def check_delivery_note():
    data = request.json
    invoice_number = data.get('salesOrderNo')

    conn = create_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM ZZInvoiceHeader WHERE InvoiceNo = ?", (invoice_number,))
    exists = cursor.fetchone()[0] > 0
    print(invoice_number, exists)

    conn.close()
    return jsonify({'exists': exists})

@invoice_bp.route('/sales-order/<int:sales_order_id>')
def sales_order_detail_page(sales_order_id):
    return render_template('Invoice page/sales_order_detail.html')

@invoice_bp.route('/api/sales-order/<int:sales_order_id>')
def api_sales_order_detail(sales_order_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch sales order header from _uvInvoiceSOStatus
    cursor.execute("""
        SELECT InvoiceIndex, InvoiceDate, InvoiceDelNoteNo, InvoiceNo, AgentName, InvoiceTaxRate, InvoiceGross, InvoiceTotalDeducted, InvoiceAgentCommIncl, InvoiceMarketCommIncl, InvoiceOtherCostsIncl, InvoiceNett, InvoiceQty, InvoiceEvoSONumber, Status
        FROM _uvInvoiceSOStatus
        WHERE InvoiceIndex = ?
    """, (sales_order_id,))
    header_row = cursor.fetchone()
    if not header_row:
        close_db_connection(cursor, conn)
        return jsonify({"error": "Sales order not found"}), 404

    header_columns = [desc[0] for desc in cursor.description]
    sales_order_header = dict(zip(header_columns, header_row))

    # Fetch sales order lines (keep as is)
    cursor.execute("SELECT * FROM _uvMarketInvoiceLines WHERE InvoiceIndex = ?", (sales_order_id,))
    line_rows = cursor.fetchall()
    line_columns = [desc[0] for desc in cursor.description]
    sales_order_lines = [dict(zip(line_columns, row)) for row in line_rows]

    close_db_connection(cursor, conn)
    return jsonify({"sales_order_header": sales_order_header, "sales_order_lines": sales_order_lines})

@invoice_bp.route('/sales-orders')
def sales_order_summary_page():
    return render_template('Invoice page/sales_order_summary.html')

@invoice_bp.route('/api/sales-orders')
def api_sales_orders():
    conn = create_db_connection()
    cursor = conn.cursor()
    # Fetch all sales order headers from _uvInvoiceSOStatus, now including InvoiceNo and InvoiceQty
    cursor.execute("""
        SELECT InvoiceIndex, InvoiceDate, InvoiceDelNoteNo, InvoiceNo, AgentName, InvoiceTaxRate, InvoiceGross, 
        InvoiceGross, InvoiceTotalDeducted, InvoiceAgentCommIncl, InvoiceMarketCommIncl, InvoiceOtherCostsIncl, 
        InvoiceNett, InvoiceQty, InvoiceEvoSONumber, Status
        FROM _uvInvoiceSOStatus
        ORDER BY InvoiceDate DESC, InvoiceIndex DESC
    """)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    sales_orders = [dict(zip(columns, row)) for row in rows]
    close_db_connection(cursor, conn)
    return jsonify(sales_orders)

@invoice_bp.route('/purchase-orders')
def purchase_order_summary_page():
    return render_template('Invoice page/purchase_order_summary.html')

@invoice_bp.route('/api/purchase-orders')
def api_purchase_orders():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DelIndex, DelNoteNo, DelTransporter, DelTransportCostExcl, TransportEvoPONumber, Status FROM _uvTransportPOStatus ORDER BY DelIndex DESC")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    purchase_orders = [dict(zip(columns, row)) for row in rows]
    print(purchase_orders)
    close_db_connection(cursor, conn)
    return jsonify(purchase_orders)

@invoice_bp.route('/api/invoices-for-delivery-note/<del_note_no>')
def api_invoices_for_delivery_note(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()
    print(del_note_no)
    cursor.execute("""
        SELECT InvoiceIndex, InvoiceNo, InvoiceDate, InvoiceGross, InvoiceNett, Status
        FROM _uvInvoiceSOStatus
        WHERE InvoiceDelNoteNo = ?
        ORDER BY InvoiceDate DESC, InvoiceIndex DESC
    """, (del_note_no,))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    invoices = [dict(zip(columns, row)) for row in rows]
    print(invoices)
    close_db_connection(cursor, conn)
    return jsonify(invoices)