from flask import render_template, jsonify
from Market.db import create_db_connection
from Market.routes import market_bp

# Helper to drain all resultsets from stored proc
def drain_resultsets(cursor):
    try:
        while cursor.nextset():
            pass
    except Exception:
        pass

@market_bp.route('/api/bill_of_materials')
def api_bill_of_materials():
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        data = get_bill_of_materials(cursor)
        # Convert to list of dicts for JSON
        result = []
        for row in data:
            if len(row) < 7:
                # Log warning and skip malformed rows
                print(f"WARNING: Skipping malformed row (expected 7 cols, got {len(row)}): {row}")
                continue
            result.append({
                'ProductDescription': row[0],
                'PackHouseName': row[1],
                'QtyDeliveredNotInvoiced': row[2],
                'QtyToManufacture': row[3],
                'QtyOnHand': row[4],
                'QtyOnBOM': row[5],
                'BOMCreated': row[6]
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

@market_bp.route('/bill_of_materials')
def bill_of_materials_page():
    return render_template('Transition pages/BillOfMaterial.html')

@market_bp.route('/api/create_bom', methods=['POST'])
def create_bom():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC SIGCreateBOM")
        drain_resultsets(cursor)  # drain all result sets
        conn.commit()
        return jsonify({'success': True, 'message': 'BOM created successfully.'})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

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
        drain_resultsets(cursor)  # drain all result sets
        conn.commit()
        return jsonify({'success': True, 'message': 'Masterfiles created successfully.'})
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass