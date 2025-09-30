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
        SALLIN.DiscountPercent,
        SALLIN.SalesAmnt,
        LIN.DelLineIndex,
        LIN.DelLineStockId,
        HEA.DeliClientId,
        SALLIN.SalesLineIndex,
        SALLIN.SalesDate--,
        --CASE 
            --WHEN INVLIN.InvoiceSaleLineIndex IS NOT NULL THEN 1
            ---ELSE 0
        --END AS HasInvoice
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
    LEFT JOIN (SELECT SalesDelLineId, SalesQty, SalesPrice, DiscountPercent, SalesAmnt, SalesLineIndex, SalesDate 
            FROM ZZSalesLines) SALLIN 
        ON SALLIN.SalesDelLineId = LIN.DelLineIndex
    LEFT JOIN (SELECT InvoiceSaleLineIndex FROM ZZInvoiceLines) INVLIN 
        ON INVLIN.InvoiceSaleLineIndex = SALLIN.SalesLineIndex
    WHERE InvoiceSaleLineIndex IS NULL and HEA.DelNoteNo = ?
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
    # try:
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

    # except odbc.IntegrityError as e:
    #     print(f"Error: {e}")
    #     return jsonify({'success': False, 'error': "This invoice is already captured. Please change the invoice number."})
    
    # except Exception as e:
    #     print(f"Error: {e}")
    #     return jsonify({'success': False, 'error': str(e)})


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

@invoice_bp.route('/api/refresh-invoices', methods=['POST'])
@role_required()
def refresh_invoices():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC [dbo].[SIGUpdateMarketFromEvoInvoices]" \
        "; EXEC [dbo].[SIGRemoveCreditNotedInvoice];")
        conn.commit()
        return jsonify({'success': True, 'message': 'Invoices refreshed successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# =========================
# Correct Invoice workflow
# =========================

@invoice_bp.route('/api/correct-invoice/agents')
@role_required()
def correct_invoice_agents():
    """List available agents (markets)."""
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT Account, Name FROM _uvMarketAgent ORDER BY Name")
        rows = cursor.fetchall()
        return jsonify([{"id": r[0], "name": r[1]} for r in rows])
    finally:
        close_db_connection(cursor, conn)




@invoice_bp.route('/api/correct-invoice/old-prod-units-and-invoices/<del_note_no>')
@role_required()
def correct_invoice_old_prod_units_and_invoices(del_note_no):
    """
    Return production units currently used in delivery note and invoices for that delivery note.
    """
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch production units currently used in the delivery note
        cursor.execute(
            """
            SELECT DISTINCT PU.ProjectLink, PU.ProdUnitName
            FROM ZZDeliveryNoteHeader H
            JOIN ZZDeliveryNoteLines L ON L.DelHeaderId = H.DelIndex
            JOIN _uvMarketProdUnit PU ON PU.ProjectLink = L.DelLineFarmId
            WHERE H.DelNoteNo = ?
            ORDER BY PU.ProdUnitName
            """,
            (del_note_no,)
        )
        old_prod_units = [{"id": r[0], "name": r[1]} for r in cursor.fetchall()]
        
        # Fetch invoices for the delivery note (same as agent step)
        cursor.execute("""
            SELECT InvoiceIndex, InvoiceNo, InvoiceDate, InvoiceGross, InvoiceNett, Status
            FROM _uvInvoiceSOStatus
            WHERE InvoiceDelNoteNo = ?
            ORDER BY InvoiceDate DESC, InvoiceIndex DESC
        """, (del_note_no,))
        invoice_rows = cursor.fetchall()
        invoice_columns = [desc[0] for desc in cursor.description]
        invoices = [dict(zip(invoice_columns, row)) for row in invoice_rows]
        
        return jsonify({"old_prod_units": old_prod_units, "invoices": invoices})
    finally:
        close_db_connection(cursor, conn)


@invoice_bp.route('/api/correct-invoice/all-prod-units')
@role_required()
def correct_invoice_all_prod_units():
    """
    Return all available production units from _uvMarketProdUnit.
    """
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ProjectLink, ProdUnitName FROM _uvMarketProdUnit ORDER BY ProdUnitName")
        rows = cursor.fetchall()
        return jsonify([{"id": r[0], "name": r[1]} for r in rows])
    finally:
        close_db_connection(cursor, conn)


@invoice_bp.route('/api/correct-invoice/lines-and-invoices')
@role_required()
def correct_invoice_lines_and_invoices():
    """
    Given del_note_no and old_prod_unit_id, return lines under that prod unit and the invoices
    that contain sales lines for those delivery lines.
    """
    del_note_no = request.args.get('del_note_no')
    old_prod_unit_id = request.args.get('old_prod_unit_id')
    if not del_note_no or not old_prod_unit_id:
        return jsonify({"error": "del_note_no and old_prod_unit_id are required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch delivery lines for the given production unit
        cursor.execute(
            """
            SELECT L.DelLineIndex, P.ProductDescription, PU.ProdUnitName
            FROM ZZDeliveryNoteHeader H
            JOIN ZZDeliveryNoteLines L ON L.DelHeaderId = H.DelIndex
            JOIN _uvMarketProduct P ON P.StockLink = L.DelLineStockId
            JOIN _uvMarketProdUnit PU ON PU.ProjectLink = L.DelLineFarmId
            WHERE H.DelNoteNo = ? AND L.DelLineFarmId = ?
            ORDER BY L.DelLineIndex
            """,
            (del_note_no, old_prod_unit_id,)
        )
        line_rows = cursor.fetchall()

        invoices = []
        # Find invoices containing sales lines that reference these delivery lines
        cursor.execute(
            """
        SELECT DISTINCT
            INV.InvoiceIndex,
            INV.InvoiceNo,
            INV.InvoiceDate,
            INV.InvoiceNett,
            INV.Status,
            DELL.DelLineIndex
        FROM _uvInvoiceSOStatus INV
        JOIN ZZInvoiceLines ZIL
            ON ZIL.InvoiceHeaderId = INV.InvoiceIndex
        JOIN ZZSalesLines ZSL
            ON ZSL.SalesLineIndex = ZIL.InvoiceSaleLineIndex
        JOIN ZZDeliveryNoteLines DELL
            ON DELL.DelLineIndex = ZSL.SalesDelLineId
        JOIN ZZDeliveryNoteHeader DELH
            ON DELH.DelIndex = DELL.DelHeaderId
        WHERE DELH.DelNoteNo = ?;
            """, (del_note_no,)
        )
        invoices = [
            {"InvoiceIndex": r[0], "InvoiceNo": r[1], "InvoiceDate": r[2], "InvoiceNett": r[3], "InvoiceStatus": r[4], "DelLineIndex": r[5]}
            for r in cursor.fetchall()
        ]

        lines = [{"DelLineIndex": r[0], "ProductDescription": r[1], "ProdUnitName": r[2]} for r in line_rows]
        return jsonify({"lines": lines, "invoices": invoices})
    finally:
        close_db_connection(cursor, conn)


@invoice_bp.route('/api/correct-invoice/submit-agent-change', methods=['POST'])
@role_required()
def submit_agent_change():
    data = request.get_json(force=True)
    del_note_no = data.get('del_note_no')
    new_agent_id = data.get('new_agent_id')
    if not del_note_no or not new_agent_id:
        return jsonify({"error": "del_note_no and new_agent_id are required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        # Update the delivery note header agent (client)
        cursor.execute("""
            EXEC [SIGUpdateProcessedAgentAccount]
                @DelNoteNo = ?,
                @NewAgentAccount = ?;
            """,(del_note_no,new_agent_id,)
        )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@invoice_bp.route('/api/correct-invoice/submit-produnit-change', methods=['POST'])
@role_required()
def submit_produnit_change():
    data = request.get_json(force=True)
    del_note_no = data.get('del_note_no')
    old_prod_unit_id = data.get('old_prod_unit_id')
    new_prod_unit_id = data.get('new_prod_unit_id')
    if not del_note_no or not old_prod_unit_id or not new_prod_unit_id:
        return jsonify({"error": "del_note_no, old_prod_unit_id, new_prod_unit_id are required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    print(del_note_no, old_prod_unit_id, new_prod_unit_id)
    try:
        # Update lines for this delivery note that match the old production unit
        cursor.execute(
            """
        EXEC [dbo].[SIGChangeProcessedProject]
            @DelNoteNo       = ?,
            @OldProjectId  = ?,
            @NewProjectId  = ?;
            """,
            (del_note_no, old_prod_unit_id, new_prod_unit_id,)
        )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()