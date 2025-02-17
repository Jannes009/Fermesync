from flask import Blueprint, render_template, request, jsonify
from db import create_db_connection, close_db_connection
from routes.db_functions import get_agent_codes, get_stock_id, get_products, del_note_number_to_del_id

view_bp = Blueprint('view', __name__)

@view_bp.route('/view_entries', methods=['GET', 'POST'])
def view_entries():
    filters = {
    "agent_name": request.form.get('ZZAgentName', ''),
    "start_date": request.form.get('start_date', ''),
    "end_date": request.form.get('end_date', ''),
    "del_note_number": request.form.get('DeliveryNoteNo', ''),
    "Invoiced": request.form.get('Invoiced', '0'),  # Defaults to '0' if not sent
    "Not_Invoiced": request.form.get('Not_Invoiced', '1')  # Defaults to '0' if not sent
    }

    # Create the base query
    query = """
    SELECT DelIndex, DelDate, DelNoteNo, AgentName, MarketName,
           SUM(DelLineQuantityBags) QtyLoaded,
           SUM(TotalQtySold) QtySold,
           SUM(TotalQtyInvoiced) QtyInvoiced,
           DelIsFullyInvoiced
    FROM [dbo].[_uvMarketDeliveryNote] WHERE 1=1
    """
    params = []

    # Add filters to the query
    if filters["agent_name"]:
        query += " AND Agent = ?"
        params.append(filters["agent_name"])
    
    if filters["start_date"]:
        query += " AND DelDate >= ?"
        params.append(filters["start_date"])
    
    if filters["end_date"]:
        query += " AND DelDate <= ?"
        params.append(filters["end_date"])
    
    if filters["del_note_number"]:
        query += " AND DelNoteNo LIKE ?"
        filters["del_note_number"] = filters["del_note_number"].replace('%', '\\%').replace('_', '\\_')
        params.append(f"%{filters['del_note_number']}%")

    query += " GROUP BY DelIndex, DelDate, DelNoteNo, AgentName, MarketName, DelIsFullyInvoiced"

    # Connect to the database
    conn = create_db_connection()
    cursor = conn.cursor()

    # Execute the query with the dynamic filters
    cursor.execute(query, tuple(params))
    entries = cursor.fetchall()

    # Fetch agent names for the dropdown
    agent_codes = get_agent_codes(cursor)

    # Close the connection
    close_db_connection(cursor, conn)

    return render_template(
        'Transition pages/view_entries.html',
        entries=entries,
        filters=filters,
        agent_codes=agent_codes
    )


@view_bp.route('/entry/details/<entry_id>', methods=["GET"])
def get_entry_details(entry_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    product_options = get_products(cursor)
    query = """
    Select DelLineIndex, ProductDescription, DelLineQuantityBags, 
    TotalQtySold, TotalQtyInvoiced, LineFullyInvoiced, DelLineStockId 
    from [dbo].[_uvMarketDeliveryNote]
    Where DelIndex = ?
    """
    rows = cursor.execute(query, (entry_id,))
    data = [{'lineId': row[0], 'description': row[1], 'quantity': row[2], 'qty_sold': row[3], 'qty_invoiced': row[4], 'fullyInvoiced': bool(int(row[5])), 'product_id': row[6]} for row in rows]
    return jsonify({"data": data, "product_options": product_options, "success": True})

@view_bp.route('/submit_sales_entries', methods=['POST'])
def submit_sales_entry():
    data = request.get_json()
    lines = data.get('salesEntries')
    print(data)

    conn = create_db_connection()
    cursor = conn.cursor()

    total_quantity = sum(float(item['quantity']) for item in lines)
    
    cursor.execute("Select TotalQtyInvoiced, TotalQtyDelivered from [dbo].[_uvDelQuantities] WHERE DelLineIndex = ?",
    (lines[0]['lineId'],))
    quantities = cursor.fetchone()
    if(quantities[1] - quantities[0] - total_quantity < 0):
        print("Not enough stock")
        return jsonify({'success': False, 'message': 'Not enough stock'})


    try:
        for item in lines:
            lineId = item['lineId']
            salesId = item['salesId']
            date = item['date']
            price = item['price']
            quantity = item['quantity']
            amount = item['amount']
            stockId = get_stock_id(lineId, cursor)

            # workout price or amount
            if price == 0 and amount != 0:
                price = int(amount) / int(quantity)
            elif amount == 0 and price != 0:
                amount = int(price) * int(quantity)

            if salesId != None:
                cursor.execute("""
                UPDATE ZZSalesLines
                    SET SalesDate = ?, SalesQty = ?, salesAmnt = ?, SalesStockId = ?, SalesPrice = ?
                    WHERE SalesLineIndex = ?
                """, (date, quantity, amount, stockId, price, salesId))
            else:
                cursor.execute("""
                INSERT INTO ZZSalesLines (SalesDelLineId, SalesDate, SalesQty, SalesAmnt, SalesPrice, SalesStockId, AutoSale)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (lineId, date, quantity, amount, price, stockId, 0))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Error inserting data'})



@view_bp.route('/get_sales_entries/<int:lineId>', methods=['GET'])
def get_sales_entries(lineId):
    # Retrieve the `viewMode` parameter from the query string
    view_mode = request.args.get('viewMode', 'false').lower() == 'true'

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        if(view_mode != True):
            query = """
            SELECT SalesDate, SalesQty, SalesPrice, SalesAmnt, SalesStockId, SalesLineIndex
            FROM [dbo].[_uvMarketSales]
            WHERE SalesDelLineId = ? AND Invoiced = 'FALSE'
            """
        elif(view_mode == True):
           query = """
            SELECT SalesDate, SalesQty, SalesPrice, SalesAmnt, SalesStockId, SalesLineIndex
            FROM [dbo].[ZZSalesLines]
            WHERE SalesDelLineId = ?
            """ 
        cursor.execute(query, (lineId,))
        rows = cursor.fetchall()

        query = """
        Select AvailableQtyForSale from [dbo].[_uvDelQuantities] Where DelLineIndex = ?
        """
        cursor.execute(query, (lineId,))
        available_for_sale = cursor.fetchone()

        conn.close()

        # Format the results as a list of dictionaries
        sales_entries = [
            {
                'date': row[0],
                'quantity': row[1],
                'price': row[2],
                'amount': row[3],
                'stockId': row[4],
                'salesLineIndex': row[5]
            }
            for row in rows 
        ]

        return jsonify({'success': True, 'sales_entries': sales_entries, 'available_for_sale': available_for_sale})
    except Exception as e:
        print(f'Error retrieving sales entries: {e}')
        return jsonify({'success': False, 'message': 'Error retrieving sales entries'})
    




@view_bp.route('/delete_sales_entry/<int:sales_id>', methods=['DELETE'])
def delete_sales_entry(sales_id):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Delete the entry from the database
        cursor.execute("DELETE FROM ZZSalesLines WHERE SalesLineIndex = ?", (sales_id,))
        conn.commit()

        # Check if any rows were deleted
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'No entry found to delete'}), 404

        return jsonify({'success': True, 'message': 'Entry deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting entry: {e}")
        return jsonify({'success': False, 'message': 'Failed to delete entry'}), 500
    finally:
        close_db_connection(cursor, conn)

@view_bp.route('/filter_sales_entries', methods=['GET'])
def search_sales():
    # Retrieve query parameters (e.g., start date, end date)
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    line_id = request.args.get('lineId')
    
    if not start_date or not end_date:
        return jsonify({"error": "Both start date and end date are required"}), 400
    
    # Create the SQL query to fetch records between start and end dates
    query = """
    SELECT * FROM [dbo].[ZZSalesLines]
    WHERE SalesDate BETWEEN ? AND ? AND SalesDelLineId = ?
    """

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, (start_date, end_date, line_id))
    results = cursor.fetchall()

    # Format results as a list of dictionaries
    sales = []
    for row in results:
        sales.append({
            "id": row[0],  # Access by column name
            "sale_date": row[1],
            "quantity": row[4],
            "price": row[5],
            "amount": row[6]
        })

    return jsonify({'success': True, 'sales_entries': sales})

    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500
    # finally:
    conn.close()

@view_bp.route('/get_qty_available', methods=['GET'])
def get_qty_available():
    sale_id = request.args.get('saleId')
    
    if not sale_id:
        return jsonify({"error": "Sale ID is required"}), 400

    # Query to fetch quantity available for the given sale ID
    query = """
    Select AvailableQtyForSale from [dbo].[_uvDelQuantities] Where DelLineIndex = ?
    """

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, (sale_id,))
        result = cursor.fetchone()

        if result:
            qty_available = result[0]
            return jsonify({"qtyAvailable": qty_available})
        else:
            return jsonify({"error": "Sale not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        conn.close()

@view_bp.route('/api/fetch_products', methods=['GET'])
def fetch_products():
    conn = create_db_connection()
    cursor = conn.cursor()
    products = get_products(cursor)
    return products

@view_bp.route('/api/save_product', methods=['POST'])
def save_product():
    data = request.get_json()
    line_id = data.get('line_id')
    product_id = data.get('product_id')
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            UPDATE ZZDeliveryNoteLines
            SET DelLineStockId = ?
            WHERE DelLineIndex = ?
        """
        cursor.execute(query, (product_id, line_id))
        conn.commit()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@view_bp.route('/get_delivery_note_id', methods=['POST'])
def get_delivery_note_id():
    # Get the JSON data sent in the request
    data = request.get_json()
    delivery_note_header = data.get('delivery_note_header')
    print(delivery_note_header)

    if not delivery_note_header:
        return jsonify({'error': 'Delivery note header is required'}), 400
    
    conn = create_db_connection()
    result = del_note_number_to_del_id(delivery_note_header, conn.cursor())

    if result:
        return jsonify({'id': result[0]}), 200  # Return the ID if found
    else:
        return jsonify({'error': 'Delivery note not found'}), 404
