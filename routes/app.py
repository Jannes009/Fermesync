from flask import Flask, render_template, jsonify, Blueprint, request
from datetime import datetime
from db import create_db_connection, close_db_connection

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/sales')
def sales_page():
    return render_template('Sales/sales.html')

@sales_bp.route('/api/sales')
def get_sales():
    conn = create_db_connection()
    cursor = conn.cursor()
    
    # Fetch sales data
    sales_query = """
    SELECT 
        DelNoteNo,
        DelDate,
        Agent,
        SalesDate,
        Product,
        ProdUnitName,
        SalesQty,
        SalesPrice,
        GrossSalesAmnt,
        DiscountPercent,
        DiscountAmnt,
        SalesAmnt,
        NettSalesAmnt,
        SalesLineIndex,
        InvStatus,
        InvoiceNo,
        AutoSale
    FROM _uvMarketSales
    ORDER BY DelNoteNo, AutoSale DESC, SalesDate
    """
    cursor.execute(sales_query)
    sales_rows = cursor.fetchall()

    # Fetch linked/matched counts
    cons_query = '''
    SELECT 
        DelNoteNo, 
        SUM(CASE WHEN LINConsignmentIDExist = 1 THEN 1 ELSE 0 END) AS linked_count,
        SUM(CASE WHEN LINConsignmentIDExist = 0 AND HEADelNoteNoExist = 1 THEN 1 ELSE 0 END) AS matched_count
    FROM _uvMarketTRNConsignments
    GROUP BY DelNoteNo
    '''
    cursor.execute(cons_query)
    cons_rows = cursor.fetchall()
    cons_map = {row[0]: {'linked': row[1], 'matched': row[2]} for row in cons_rows}

    # Group sales by delivery note
    sales_data = []
    current_delnote = None
    current_group = None
    
    for row in sales_rows:
        # pypyodbc returns a list of values, so we need to access by index
        delnote_no = row[0]  # DelNoteNo
        del_date = row[1]    # DelDate
        agent = row[2]       # Agent
        sales_date = row[3]  # SalesDate
        product = row[4]     # Product
        prod_unit = row[5]   # ProdUnitName
        qty = row[6]         # SalesQty
        price = row[7]       # SalesPrice
        gross_amount = row[8] # GrossSalesAmnt
        discount_percent = row[9] # DiscountPercent
        discount_amount = row[10]  # DiscountAmnt
        sales_amount = row[11]    # SalesAmnt
        net_amount = row[12]      # NettSalesAmnt
        line_index = row[13]      # SalesLineIndex
        inv_status = row[14]      # InvStatus
        invoice_no = row[15]      # InvoiceNo
        auto_sale = row[16]      # AutoSale

        if current_delnote != delnote_no:
            if current_group:
                sales_data.append(current_group)
            current_delnote = delnote_no
            linked = cons_map.get(delnote_no, {}).get('linked', 0)
            matched = cons_map.get(delnote_no, {}).get('matched', 0)
            current_group = {
                'delnote_no': delnote_no,
                'del_date': del_date.strftime('%Y-%m-%d') if isinstance(del_date, datetime) else del_date,
                'agent': agent,
                'linked_count': linked,
                'matched_count': matched,
                'lines': []
            }
        
        current_group['lines'].append({
            'line': line_index,
            'sales_date': sales_date.strftime('%Y-%m-%d') if isinstance(sales_date, datetime) else sales_date,
            'product': product,
            'prod_unit': prod_unit,
            'price': price,
            'qty': qty,
            'gross_amount': gross_amount,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'sales_amount': sales_amount,
            'net_amount': net_amount,
            'inv_status': inv_status,
            'invoice_no': invoice_no,
            'auto_sale': auto_sale
        })
    
    if current_group:
        sales_data.append(current_group)
    
    cursor.close()
    conn.close()
    
    return jsonify(sales_data)

@sales_bp.route('/api/consignments')
def api_consignments():
    conn = create_db_connection()
    cursor = conn.cursor()
    query = '''
    SELECT * FROM _uvMarketTRNConsignments
    '''
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    print(columns)
    consignments = {}
    for row in cursor.fetchall():
        row_dict = {columns[i]: row[i] for i in range(len(columns))}
        delnote = str(row_dict['delnoteno'])
        if delnote not in consignments:
            consignments[delnote] = []
        consignments[delnote].append(row_dict)
    cursor.close()
    conn.close()
    return jsonify(consignments)

@sales_bp.route('/api/dockets')
def api_dockets():
    consignment_id = request.args.get('consignment_id')
    conn = create_db_connection()
    cursor = conn.cursor()
    # Replace DocketsTable and fields with your actual table/fields
    query = '''
    SELECT DocketNumber, QtySold, Price, SalesValue, DateSold
    FROM ZZMarketDataTrn
    WHERE ConsignmentID = ?
    '''
    cursor.execute(query, (consignment_id,))
    columns = [col[0] for col in cursor.description]
    dockets = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(dockets)

@sales_bp.route('/api/linked_lines')
def api_linked_lines():
    delnote_no = request.args.get('delnote_no')
    conn = create_db_connection()
    cursor = conn.cursor()
    query = '''
    SELECT DelHeaderId, DelNoteNo, DelLineStockId, DelProductDescription, DelQtySent, TotalSalesQty, TotalInvoicedQty,
           TrnConsignmentID, TrnDelNoteNo, TrnProduct, TrnVariety, TrnSize, TrnClass, TrnMass, TrnBrand, TrnQtySent,
           DelLineIndex
    FROM _uvDelNoteVSMktTrn
    WHERE DelNoteNo = ? OR TrnDelNoteNo = ?
    '''
    cursor.execute(query, (delnote_no, delnote_no))
    columns = [col[0] for col in cursor.description]
    lines = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(lines)

@sales_bp.route('/api/delivery_note_lines')
def api_delivery_note_lines():
    del_line_index = request.args.get('del_line_index')
    conn = create_db_connection()
    cursor = conn.cursor()
    query = '''
    SELECT SalesQty, SalesPrice, GrossSalesAmnt, DiscountPercent, DiscountAmnt, AutoSale, SalesDate, InvoiceNo
    FROM _uvMarketSales
    WHERE SalesDelLineId = ?
    ORDER BY AutoSale DESC
    '''
    print(del_line_index)
    cursor.execute(query, (del_line_index,))
    columns = [col[0] for col in cursor.description]
    lines = [dict(zip(columns, row)) for row in cursor.fetchall()]
    print(lines)
    cursor.close()
    conn.close()
    return jsonify(lines)
