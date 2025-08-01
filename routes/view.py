from flask import Blueprint, render_template, request, jsonify
from db import create_db_connection, close_db_connection
from routes.db_functions import get_agent_codes, get_stock_id, get_products, del_note_number_to_del_id

view_bp = Blueprint('view', __name__)

@view_bp.route('/view_entries', methods=['GET', 'POST'])
def view_entries():
    # Create the base query
    query = """
    SELECT DelIndex, DelDate, DelNoteNo, AgentName, PackhouseName, ProdUnitName,
        QtyLoaded,QtySold,QtyInvoiced
    FROM [dbo].[_uvViewEntriesPage]
    """

    # Connect to the database
    conn = create_db_connection()
    cursor = conn.cursor()

    # Execute the query with the dynamic filters
    cursor.execute(query,)
    entries = cursor.fetchall()

    # Close the connection
    close_db_connection(cursor, conn)

    return render_template(
        'Transition pages/view_entries.html',
        entries=entries
    )

@view_bp.route('/get_sales_entries/<int:lineId>', methods=['GET'])
def get_sales_entries(lineId):
    # Retrieve the `viewMode` parameter from the query string
    view_mode = request.args.get('viewMode', 'false').lower() == 'true'

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        if(view_mode != True):
            query = """
            SELECT SalesDate, SalesQty, SalesPrice, DiscountPercent, SalesAmnt, SalesStockId, SalesLineIndex, Destroyed
            FROM [dbo].[_uvMarketSales]
            WHERE SalesDelLineId = ? AND Invoiced = 'FALSE'
            """
        elif(view_mode == True):
           query = """
            SELECT SalesDate, SalesQty, SalesPrice, DiscountPercent, SalesAmnt, SalesStockId, SalesLineIndex, Destroyed
            FROM [dbo].[ZZSalesLines]
            WHERE SalesDelLineId = ?
            """ 
        cursor.execute(query, (lineId,))
        rows = cursor.fetchall()
        print(rows)
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
                'discount': row[3],
                'amount': row[4],
                'stockId': row[5],
                'salesLineIndex': row[6],
                'destroyed': row[7]
            }
            for row in rows 
        ]

        return jsonify({'success': True, 'sales_entries': sales_entries, 'available_for_sale': available_for_sale})
    except Exception as e:
        print(f'Error retrieving sales entries: {e}')
        return jsonify({'success': False, 'message': 'Error retrieving sales entries'})
