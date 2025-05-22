from flask import Blueprint, render_template, request, jsonify
from db import create_db_connection
from datetime import datetime
from routes.db_functions import get_stock_id, get_products
view_entry_bp = Blueprint('view_entry', __name__)

@view_entry_bp.route('/delivery-note/<del_note_no>')
def delivery_note(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch delivery note header (distinct values for the header info)
    cursor.execute("""
        SELECT TOP 1 DelNoteNo, DelDate, AgentAccount, AgentName,
                      MarketCode, MarketName, TransporterAccount,
                      TransporterName
        FROM [dbo].[_uvMarketDeliveryNote]
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

    # Fetch line items
    cursor.execute("""
        SELECT DelLineIndex, ProductDescription, MainProdUnitName,
               DelLineQuantityBags, TotalQtySold, SalesGrossAmnt,
               TotalQtyInvoiced, InvoicedGrossAmnt
        FROM [dbo].[_uvMarketDeliveryNote]
        WHERE DelNoteNo = ?
        ORDER BY DelLineIndex
    """, (del_note_no,))
    lines = cursor.fetchall()

    # Fetch sales data for this delivery note
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

    # Convert sales rows to list of dictionaries
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

    # Summary calculations
    total_qty_sold = sum([l[4] for l in lines])
    total_sales_gross = sum([l[5] for l in lines])
    total_qty_invoiced = sum([l[6] for l in lines])
    total_invoiced_gross = sum([l[7] for l in lines])
    avg_price = (total_sales_gross / total_qty_sold) if total_qty_sold else 0

    return render_template(
        'Bill Of Lading Page/View_Delivery_note.html',
        header=header,
        lines=lines,
        sales=sales,
        linked_count=linked_count,
        matched_count=matched_count,
        summary={
            'total_qty_sold': total_qty_sold,
            'avg_price': avg_price,
            'total_qty_invoiced': total_qty_invoiced,
            'total_invoiced_gross': total_invoiced_gross
        }
    )

@view_entry_bp.route('/submit_sales_entries', methods=['POST'])
def submit_sales_entry():
    data = request.get_json()
    lines = data.get('salesEntries')
    print(lines)
    conn = create_db_connection()
    cursor = conn.cursor()

    total_quantity = sum(float(item['quantity']) for item in lines)
    
    # cursor.execute("Select TotalQtyInvoiced, TotalQtyDelivered from [dbo].[_uvDelQuantities] WHERE DelLineIndex = ?",
    # (lines[0]['lineId'],))
    # quantities = cursor.fetchone()
    # if(quantities[1] - quantities[0] - total_quantity < 0):
    #     print("Not enough stock")
    #     return jsonify({'success': False, 'message': 'Not enough stock'})


    # try:
    for item in lines:
        print(item)
        lineId = item['lineId']
        salesId = item['salesId']
        date = item['date']
        price = item['price']
        quantity = item['quantity']
        discount = item['discount']
        discountAmnt = item['discountAmnt']
        amount = item['amount']
        destroyed = 1 if item['destroyed'] else 0


        print(destroyed, type(destroyed))
        stockId = get_stock_id(lineId, cursor)

        print(discount, item)
        # workout price or amount
        if price == 0 and amount != 0:
            price = int(amount) / int(quantity)
        elif amount == 0 and price != 0:
            amount = int(price) * int(quantity)

        gross_amount = float(price) * float(quantity)

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
            SELECT AgentComm, MarketComm FROM [dbo].[_uvDelLinCommission]
            WHERE DelLineIndex = ?
            """,(lineId,))
            row = cursor.fetchone()
            agent_commission = row[0]
            market_commission = row[1]
            net_sales = float(amount) - (float(amount) * (float(agent_commission) + float(market_commission)) / 100)
        
            cursor.execute("""
            UPDATE ZZSalesLines
                SET SalesDate = ?, SalesQty = ?, DiscountPercent = ?, DiscountAmnt = ?, 
                SalesAmnt = ?, SalesStockId = ?, SalesPrice = ?, GrossSalesAmnt = ?, 
                SalesMarketComPercent = ?, SalesAgentComPercent = ?, NettSalesAmnt = ?,
                Destroyed = ?
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
    conn.commit()
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

@view_entry_bp.route('/api/refresh-sales/<del_note_no>')
def refresh_sales(del_note_no):
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch sales data for this delivery note
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


    # Convert sales rows to list of dictionaries
    sales = []
    for row in sales_rows:
        sales_line_index = row[9]
        del_line_id = row[13]
        
        sale_dict = {
            'sales_date': row[0].strftime('%Y-%m-%d') if isinstance(row[0], datetime) else row[0],
            'product': row[1],
            'qty': row[2],
            'price': row[3],
            'discount_percent': row[4],
            'discount_amount': row[5],
            'gross_amount': row[6],
            'sales_amount': row[7],
            'net_amount': row[8],
            'sales_line_index': sales_line_index,
            'inv_status': row[10],
            'invoice_no': row[11],
            'auto_sale': row[12],
            'del_line_id': del_line_id
        }
        sales.append(sale_dict)
        print(sales)

    cursor.close()
    conn.close()

    return render_template('Bill Of Lading Page/sales_table.html', sales=sales, header={'delnoteno': del_note_no})

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
            UPDATE ZZDeliveryNoteLines
            SET DelLineStockId = ?
            WHERE DelLineIndex = ?
        """
        cursor.execute(query, (product_id, line_id))
        conn.commit()
        return jsonify({'message': 'Product updated successfully'})
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