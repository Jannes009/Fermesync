from flask import render_template, jsonify
from Market.db import create_db_connection

from Market.routes import market_bp

@market_bp.route('/api/bill_of_materials')
def api_bill_of_materials():
    conn = create_db_connection()
    cursor = conn.cursor()
    data = get_bill_of_materials(cursor)
    # Convert to list of dicts for JSON
    result = [
        {
            'ProductDescription': row[0],
            'PackHouseName': row[1],
            'QtyDeliveredNotInvoiced': row[2],
            'QtyToManufacture': row[3],
            'QtyOnHand': row[4],
            'QtyOnBOM': row[5],
            'BOMCreated': row[6]
        }
        for row in data
    ]
    cursor.close()
    conn.close()
    return jsonify(result)

@market_bp.route('/bill_of_materials')
def bill_of_materials_page():
    return render_template('Transition pages/BillOfMaterial.html')

@market_bp.route('/api/create_bom', methods=['POST'])
def create_bom():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC SIGCreateBOM")
        conn.commit()
        return jsonify({'success': True, 'message': 'BOM created successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def get_bill_of_materials(cursor):
    query = """
    SELECT ProductDescription, PackHouseName, DeliveredNotInvoiced, QtyToManufacture, QtyOnHand, QtyOnBOM, BOMCreated
    FROM [dbo].[_uvManufactureDashboard]
    """
    cursor.execute(query)
    return cursor.fetchall()

@market_bp.route('/api/create_bom_masterfiles', methods=['POST'])
def create_bom_masterfiles():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC [dbo].[SIGCreateBomMasterfiles]")
        conn.commit()
        return jsonify({'success': True, 'message': 'Masterfiles created successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()