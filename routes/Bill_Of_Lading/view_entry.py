from flask import Blueprint, render_template, request, jsonify
from db import create_db_connection
from datetime import datetime
from routes.db_functions import get_stock_id, get_products,  get_agent_codes, get_transporter_codes, get_market_codes, production_unit_name_to_production_unit_id, get_destinations, get_production_unit_codes
view_entry_bp = Blueprint('view_entry', __name__)


@view_entry_bp.route('/delivery-note/<del_note_no>')
def delivery_note(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()
    
    # Fetch delivery note header (distinct values for the header info)
    cursor.execute("""
    SELECT DelNoteNo, DelDate, 
        AgentAccount, AgentName, 
        DelTotalQuantity
        ,PackhouseCode, PackhouseName,
        TransporterAccount, TransporterName, 
        DelTransportCostExcl, DestinationId, DestinationDescription
    FROM _uvDeliveryNoteHeader
    WHERE DelNoteNo = ?
    """, (del_note_no,))
    header = cursor.fetchone()

    if not header:
        return "Delivery note not found", 404

    # Get linked count
    cursor.execute("""
        Select Count(ConsignmentID) 
        from ZZDeliveryNoteLines LIN
        JOIN ZZDeliveryNoteHeader HEA on HEA.DelIndex = LIN.DelHeaderId
        where DelNoteNo = ? AND ConsignmentID Is Not NULL
    """, (del_note_no,))
    linked_count = cursor.fetchone()[0] or 0

    # Get matched count
    cursor.execute("""
        SELECT Count(TrnConsignmentID)
        FROM _uvDelNoteVSMktTrn
        WHERE TrnDelNoteNo = ? AND DelNoteNo IS NULL
    """, (del_note_no,))
    matched_count = cursor.fetchone()[0] or 0

    # Get discount percent
    cursor.execute("""
    Select DiscountPercent from _uvMarketAgent
    WHERE Account = ?
    """, ( header[2],))
    discount_percent = cursor.fetchone()

    return render_template(
        'Bill Of Lading Page/View_Delivery_note.html',
        header=header,
        linked_count=linked_count,
        matched_count=matched_count,
        discount_percent=discount_percent[0]
    )

@view_entry_bp.route('/api/fetch_delivery_note_lines/<del_note_no>')
def fetch_delivery_note_lines(del_note_no):
    print("DelNoteNo", del_note_no)
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DelLineIndex, ProductDescription,ProdUnitName,
               DelLineQuantityBags, TotalQtySold, TotalQtyInvoiced
        FROM [dbo].[_uvMarketDeliveryNote]
        WHERE DelNoteNo = ?
        ORDER BY DelLineIndex
    """, (del_note_no,))
    lines = cursor.fetchall()
    # Convert to list of dicts for JSON
    lines_dict = [
        {
            'dellineindex': row[0],
            'productdescription': row[1],
            'produnitname': row[2],
            'dellinequantitybags': row[3],
            'totalqtysold': row[4],
            'totalqtyinvoiced': row[5]
        }
        for row in lines
    ]
    return jsonify({'lines': lines_dict})

@view_entry_bp.route('/api/fetch_sales_note_lines/<del_note_no>')
def fetch_sales_lines(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            SalesDate,
            Product,
            SalesQty,
            SalesPrice,
            DiscountPercent,
            DiscountAmnt,
            GrossSalesAmnt,
            SalesAmnt,
            NettSalesAmnt,
            SalesLineIndex,
            InvStatus,
            InvoiceNo,
            AutoSale,
            SalesDelLineId
        FROM _uvMarketSales
        WHERE DelNoteNo = ?
        ORDER BY AutoSale DESC, SalesDate
    """, (del_note_no,))
    sales_rows = cursor.fetchall()
    sales = []
    for row in sales_rows:
        sales.append({
            'sales_date': row[0].strftime('%Y-%m-%d') if isinstance(row[0], datetime) else row[0],
            'product': row[1],
            'qty': row[2],
            'price': row[3],
            'discount_percent': row[4],
            'discount_amount': row[5],
            'gross_amount': row[6],
            'sales_amount': row[7],
            'net_amount': row[8],
            'sales_line_index': row[9],
            'inv_status': row[10],
            'invoice_no': row[11],
            'auto_sale': row[12],
            'del_line_id': row[13]
        })
    cursor.close()
    conn.close()
    return jsonify({'lines': sales})

@view_entry_bp.route('/submit_sales_entries', methods=['POST'])
def submit_sales_entry():
    data = request.get_json()
    lines = data.get('salesEntries')

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        total_quantity = sum(float(item['quantity']) for item in lines)
    
        # cursor.execute("Select TotalQtyInvoiced, TotalQtyDelivered from [dbo].[_uvDelQuantities] WHERE DelLineIndex = ?",
        # (lines[0]['lineId'],))
        # quantities = cursor.fetchone()
        # if(quantities[1] - quantities[0] - total_quantity < 0):
        #     print("Not enough stock")
        #     return jsonify({'success': False, 'message': 'Not enough stock'})


        # try:
        for item in lines:
            lineId = item['lineId']
            salesId = item['salesId']
            date = item['date']
            price = item['price']
            quantity = item['quantity']
            discount = item['discount']
            destroyed = 1 if item['destroyed'] else 0

            stockId = get_stock_id(lineId, cursor)

            # workout price or amount
            gross_amount = float(price) * float(quantity)
            amount = gross_amount * (1 - float(discount) / 100)
            discountAmnt = gross_amount * (float(discount) / 100)

            cursor.execute("""
            SELECT AgentComm, MarketComm FROM [dbo].[_uvDelLinCommission]
            WHERE DelLineIndex = ?
            """,(lineId,))
            row = cursor.fetchone()
            agent_commission = row[0]
            market_commission = row[1]
            net_sales = float(amount) - (float(amount) * (float(agent_commission) + float(market_commission)) / 100)
            if salesId != None:
                cursor.execute("""
                UPDATE ZZSalesLines
                    SET SalesDate = ?, SalesQty = ?, DiscountPercent = ?, DiscountAmnt = ?, 
                    SalesAmnt = ?, SalesStockId = ?, SalesPrice = ?, GrossSalesAmnt = ?, 
                    SalesMarketComPercent = ?, SalesAgentComPercent = ?, NettSalesAmnt = ?,
                    Destroyed = ?, SalesLineTransportCostExcl = NULL
                    WHERE SalesLineIndex = ?
                """, (date, quantity, discount, discountAmnt, amount, stockId, price, 
                      gross_amount, market_commission, agent_commission, net_sales, destroyed, salesId, ))
            else:  
                cursor.execute("""
                INSERT INTO ZZSalesLines (
                SalesDelLineId, SalesDate, SalesQty, SalesAmnt,
                SalesPrice, SalesStockId, AutoSale, DiscountPercent,
                DiscountAmnt, GrossSalesAmnt,
                SalesMarketComPercent, SalesAgentComPercent, NettSalesAmnt,
                Destroyed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (lineId, date, quantity, amount, 
                        price, stockId, 0, discount, 
                        discountAmnt, gross_amount,
                        market_commission, agent_commission, net_sales, destroyed,))
            cursor.execute("""
            EXEC [dbo].[SIGUpdatePackagingCost]
            EXEC [dbo].[SIGUpdateWeightTransport]
            EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]
            """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return jsonify({'success': True})

@view_entry_bp.route('/api/available-lines/<del_note_no>')
def get_available_lines(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch lines that aren't fully sold
    cursor.execute("""
        SELECT 
            DelLineIndex,
            ProductDescription,
            DelLineQuantityBags,
            TotalQtySold,
            (DelLineQuantityBags - TotalQtySold) as available_qty
        FROM [dbo].[_uvMarketDeliveryNote]
        WHERE DelNoteNo = ?
        AND (DelLineQuantityBags - TotalQtySold) > 0
        ORDER BY DelLineIndex
    """, (del_note_no,))
    
    lines = []
    for row in cursor.fetchall():
        lines.append({
            'dellineindex': row[0],
            'productdescription': row[1],
            'total_qty': row[2],
            'sold_qty': row[3],
            'available_qty': row[4]
        })

    cursor.close()
    conn.close()

    return jsonify({'lines': lines})

@view_entry_bp.route('/delete_sales_entry/<int:sales_id>', methods=['DELETE'])
def delete_sales_entry(sales_id):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            Select DocketNumber 
            from [dbo].[ZZSalesLines]
            where SalesLineIndex = ?
        """,(sales_id,))
        docket_number = cursor.fetchone()

        # Delete the entry from the database
        cursor.execute("""
            Delete
            from [dbo].[ZZSalesLines]
            where SalesLineIndex = ?

            Update TRN SET Deleted = 1
            from [dbo].[ZZMarketDataTrn] TRN 
            where DocketNumber = ?;
        """, (sales_id, docket_number[0]))
        cursor.execute("EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]")
        conn.commit()

        # Check if any rows were deleted
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'No entry found to delete'}), 404

        return jsonify({'success': True, 'message': 'Entry deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting entry: {e}")
        return jsonify({'success': False, 'message': 'Failed to delete entry'}), 500
    finally:
        cursor.close()
        conn.close()

@view_entry_bp.route('/api/unlink-consignment/<consignment_id>', methods=['POST'])
def unlink_consignment(consignment_id):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Execute the stored procedure to unlink the consignment
        cursor.execute("EXEC SIGUnlinkConsignment @ConsignmentID = ?", (consignment_id,))
        cursor.execute("EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]")
        conn.commit()

        return jsonify({'success': True, 'message': 'Consignment unlinked successfully'})
    except Exception as e:
        print(f"Error unlinking consignment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@view_entry_bp.route('/api/update-counts/<del_note_no>')
def update_counts(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Get linked count
    cursor.execute("""
        Select Count(ConsignmentID) 
        from ZZDeliveryNoteLines LIN
        JOIN ZZDeliveryNoteHeader HEA on HEA.DelIndex = LIN.DelHeaderId
        where DelNoteNo = ? AND ConsignmentID Is Not NULL
    """, (del_note_no,))
    linked_count = cursor.fetchone()[0] or 0

    # Get matched count
    cursor.execute("""
        SELECT Count(TrnConsignmentID)
        FROM _uvDelNoteVSMktTrn
        WHERE TrnDelNoteNo = ? AND DelNoteNo IS NULL
    """, (del_note_no,))
    matched_count = cursor.fetchone()[0] or 0

    cursor.close()
    conn.close()

    return jsonify({
        'linked_count': linked_count,
        'matched_count': matched_count
    })

@view_entry_bp.route('/api/save_product', methods=['POST'])
def save_product():
    data = request.get_json()
    line_id = data.get('line_id')
    product_id = data.get('product_id')
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        query = """
        EXEC [SIGChangeDelNoteStockItem]
            @NewStockLink = ?,
            @LineId = ?;
        """
        cursor.execute(query, (product_id, line_id))
        cursor.execute("""
        EXEC [dbo].[SIGUpdatePackagingCost]
        EXEC [dbo].[SIGUpdateWeightTransport]
        EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]
        """)
        conn.commit()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@view_entry_bp.route('/api/save_production_unit', methods=['POST'])
def save_productuction_unit():
    data = request.get_json()
    line_id = data.get('line_id')
    production_unit_id = data.get('unit_id')
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            UPDATE ZZDeliveryNoteLines
            SET DelLineFarmId = ?
            WHERE DelLineIndex = ?
        """
        cursor.execute(query, (production_unit_id, line_id))
        conn.commit()
        return jsonify({'message': 'Production unit updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@view_entry_bp.route('/api/products')
def get_products_api():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # Get products using the existing function
        products = get_products(cursor)
        
        # Convert to list of dictionaries
        product_list = [{
            'StockLink': p[0],
            'display_name': p[1]
        } for p in products]
        
        return jsonify(product_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@view_entry_bp.route('/api/production_units')
def get_producttion_units_api():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # Get products using the existing function
        products = get_production_unit_codes(cursor)
        
        # Convert to list of dictionaries
        production_unit_list = [{
            'UnitId': p[0],
            'UnitName': p[1]
        } for p in products]
        
        return jsonify(production_unit_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@view_entry_bp.route('/api/delivery-header/<delnote_no>')
def get_delivery_header(delnote_no):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # Get header data from the view
        cursor.execute("""
        SELECT DelNoteNo, DelDate, DeliClientId, DelMarketId,
               DelTransporter, DelQuantityBags, DelTransportCostExcl, DelDestinationId
        From ZZDeliveryNoteHeader	
        WHERE DelNoteNo = ?
        """, (delnote_no,))
        
        header = cursor.fetchone()
        if not header:
            return jsonify({'error': 'Delivery note not found'}), 404
        return jsonify({
            'delnoteno': header[0],
            'deldate': header[1],
            'deliclientid': header[2],
            'delmarketid': header[3],
            'deltransporter': header[4],
            'delquantitybags': header[5],
            'deltransportcostexcl': header[6],
            'destinationid': header[7]
        })
        
    except Exception as e:
        print(f"Error in get_delivery_header: {str(e)}")  # Add logging
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@view_entry_bp.route('/api/save-delivery-header/<delnote_no>', methods=['POST'])
def save_delivery_header(delnote_no):
    data = request.get_json()
    new_delnoteno = data['delnoteno']
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # If the delivery note number is being changed, update it everywhere
        if new_delnoteno != delnote_no:
            # Check if the new DelNoteNo already exists (prevent duplicates)
            cursor.execute("SELECT COUNT(*) FROM ZZDeliveryNoteHeader WHERE DelNoteNo = ?", (new_delnoteno,))
            if cursor.fetchone()[0] > 0:
                return jsonify({'success': False, 'message': 'A delivery note with this number already exists.'}), 400

            # Update the header
            cursor.execute("""
                UPDATE ZZDeliveryNoteHeader
                SET DelNoteNo = ?
                WHERE DelNoteNo = ?
            """, (new_delnoteno, delnote_no))

        delnote_no = new_delnoteno  # For the next update
        # Update the rest of the fields
        cursor.execute("""
            UPDATE ZZDeliveryNoteHeader
            SET DelDate = ?,
                DeliClientId = ?,
                DelMarketId = ?,
                DelTransporter = ?,
                DelQuantityBags = ?,
                DelTransportCostExcl = ?,
                DelDestinationId = ?
            WHERE DelNoteNo = ? 
        """, (
            data['deldate'],
            data['deliclientid'],
            data['delmarketid'],
            data['deltransporter'],
            data['delquantitybags'],
            data['deltransportcostexcl'],
            data['destinationid'],
            delnote_no
        ))
        cursor.execute("""
        EXEC [SIGUpdateProcessedAgentAccount]
            @DelNoteNumber = ?,
            @NewAgentId = ?;
                """,(delnote_no, data['deliclientid']))
        conn.commit()

        # Edit Transport PO
        cursor.execute("EXEC [dbo].[SIGCreateTransportPO]")
        cursor.execute("""
        EXEC [dbo].[SIGUpdateWeightTransport]
        EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]
        """)

        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

@view_entry_bp.route('/api/agents')
def get_agents():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        agents = get_agent_codes(cursor)
        
        # Convert to list of dictionaries with proper format
        agent_list = [{
            'DCLink': agent[0],
            'display_name': agent[1]
        } for agent in agents]
        
        return jsonify(agent_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@view_entry_bp.route('/api/packhouses')
def get_packhouses():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        markets = get_market_codes(cursor)
        
        # Convert to list of dictionaries with proper format
        market_list = [{
            'WhseLink': market[0],
            'display_name': market[1]
        } for market in markets]
        
        return jsonify(market_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@view_entry_bp.route('/api/transporters')
def get_transporters():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        
        transporters = get_transporter_codes(cursor)
        
        # Convert to list of dictionaries with proper format
        transporter_list = [{
            'TransporterAccount': transporter[0],
            'display_name': transporter[1]
        } for transporter in transporters]
        
        return jsonify(transporter_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@view_entry_bp.route('/api/destinations')
def get_destination_api():
    
    conn = create_db_connection()
    cursor = conn.cursor()
    
    destinations = get_destinations(cursor)
    
    # Convert to list of dictionaries with proper format
    destination_list = [{
        'DestinationId': destination[0],
        'display_name': destination[1]
    } for destination in destinations]
    
    return jsonify(destination_list)
  
    #     return jsonify({'error': str(e)}), 500
    # finally:
    #     if 'conn' in locals():
    #         conn.close()

@view_entry_bp.route('/api/update-line-quantities', methods=['POST'])
def update_line_quantities():
# try:
    data = request.get_json()
    quantities = data.get('quantities', {})
    new_line_info = data.get('new_line_info', {})  # Expecting: {product_id, prod_unit, quantity, del_note_no}
    new_line_id = None
    
    if not quantities:
        return jsonify({'success': False, 'message': 'No quantities provided'}), 400
        
    conn = create_db_connection()
    cursor = conn.cursor()

    # If there is a 'new' line, insert it first
    if 'new' in quantities and new_line_info:
        # Insert new line
        cursor.execute("""
            SELECT TOP 1 DelIndex FROM ZZDeliveryNoteHeader WHERE DelNoteNo = ?
        """, (new_line_info['delNoteNo'],))
        header_row = cursor.fetchone()
        production_unit_id = production_unit_name_to_production_unit_id(new_line_info['prod_unit'], cursor)
        if not header_row:
            return jsonify({'success': False, 'message': 'Delivery note not found'}), 404
        header_id = header_row[0]
        cursor.execute("""
            INSERT INTO ZZDeliveryNoteLines (DelHeaderId, DelLineStockId, DelLineFarmId, DelLineQuantityBags)
            VALUES (?, ?, ?, ?)
        """, (header_id, new_line_info['product_id'], production_unit_id, new_line_info['quantity']))
        conn.commit()
        # Get the new line's ID
        cursor.execute("""
            SELECT TOP 1 DelLineIndex FROM ZZDeliveryNoteLines WHERE DelHeaderId = ? ORDER BY DelLineIndex DESC
        """, (header_id,))
        new_line_id = cursor.fetchone()[0]
        # Replace 'new' with the real id in quantities
        quantities[new_line_id] = quantities['new']
        del quantities['new']

    # Get the header ID and total quantity from the first line (after possible insert)
    first_line_id = list(quantities.keys())[0]
    cursor.execute("""
        SELECT DelHeaderId, DelQuantityBags
        FROM ZZDeliveryNoteLines LIN
        JOIN ZZDeliveryNoteHeader HEA ON HEA.DelIndex = LIN.DelHeaderId
        WHERE DelLineIndex = ?
    """, (first_line_id,))
    result = cursor.fetchone()
    
    if not result:
        return jsonify({'success': False, 'message': 'Line not found'}), 404
        
    header_id, header_total = result
    
    # Validate total quantity matches header total
    total_new_quantity = sum(quantities.values())
    if total_new_quantity != header_total:
        return jsonify({
            'success': False, 
            'message': f'Total quantity must equal {header_total} bags'
        }), 400
    
    # Validate each line's new quantity
    for line_id, new_qty in quantities.items():
        cursor.execute("""
            SELECT TotalQtySold, TotalQtyInvoiced
            FROM _uvMarketDeliveryNote
            WHERE DelLineIndex = ?
        """, (line_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'success': False, 'message': f'Line {line_id} not found'}), 404
        sold_qty, invoiced_qty = result
        min_qty = sold_qty
        if new_qty < min_qty:
            return jsonify({
                'success': False, 
                'message': f'Quantity for line {line_id} cannot be less than {min_qty} bags (sold quantity)'
            }), 400
    # Update all quantities in a single transaction
    for line_id, new_qty in quantities.items():
        cursor.execute("""
            UPDATE ZZDeliveryNoteLines
            SET DelLineQuantityBags = ?
            WHERE DelLineIndex = ?
        """, (new_qty, line_id))
    cursor.execute("""
    EXEC [dbo].[SIGUpdatePackagingCost]
    EXEC [dbo].[SIGUpdateWeightTransport]
    EXEC [dbo].[SIGUpdateDeliveryNoteLineTotals]
    """)
    conn.commit()
    return jsonify({
        'success': True,
        'quantities': {str(k): v for k, v in quantities.items()},
        'new_line_id': new_line_id,
        'message': 'Quantities updated successfully'
    })
# except Exception as e:
    if 'conn' in locals():
        conn.rollback()
    return jsonify({'success': False, 'message': str(e)}), 500
# finally:
    if 'conn' in locals():
        cursor.close()
        conn.close() 

@view_entry_bp.route('/api/delete-delivery-line/<int:line_id>', methods=['DELETE'])
def delete_delivery_line(line_id):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        # Optionally, add safety checks here (e.g., not deleting if sold/invoiced qty > 0)
        cursor.execute("""
            DELETE FROM ZZDeliveryNoteLines WHERE DelLineIndex = ?
            DELETE FROM [dbo].[ZZDeliveryNoteLineTotals] WHERE DelLineId = ?
        """, (line_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': 'No line found to delete'}), 404
        return jsonify({'success': True, 'message': 'Line deleted successfully'})
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close() 

@view_entry_bp.route('/api/linked_lines')
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

    
@view_entry_bp.route('/api/dockets')
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


@view_entry_bp.route('/api/delivery_note_lines')
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
    cursor.execute(query, (del_line_index,))
    columns = [col[0] for col in cursor.description]
    lines = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(lines)

@view_entry_bp.route('/api/order-status/<delnote_no>')
def get_order_status(delnote_no):
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Transport PO Status
        cursor.execute("""
            SELECT TOP 1 Status
            FROM _uvTransportPOStatus
            WHERE DelNoteNo = ?
        """, (delnote_no,))
        result = cursor.fetchone()
        status = result[0] if result else None

        # Invoice existence
        cursor.execute("""
            SELECT COUNT(*) 
            FROM ZZInvoiceHeader
            WHERE InvoiceDelNoteNo = ?
        """, (delnote_no,))
        invoice_count = cursor.fetchone()[0]

        return jsonify({
            'status': status,
            'isProcessed': status == 'Processed',
            'hasInvoice': invoice_count > 0
        })

    except Exception as e:
        print(f"Error in get_order_status: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

