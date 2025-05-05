from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context
from db import create_db_connection
import logging
from flask_login import current_user
from models import ConnectedService
from routes.Import.freshlinq import Freshlinq
from auth import role_required
from routes.Import.technofresh import Technofresh
from flask_login import current_user

import_bp = Blueprint('import', __name__)

@import_bp.route('/main', methods=['GET'])
@role_required()
def import_page():
    connected_services = ConnectedService.query.filter_by(user_id=current_user.id).all()
    return render_template("Import/import.html", services=[service.service_type for service in connected_services])

logging.basicConfig(level=logging.INFO)

@import_bp.route('/get_imported_results', methods=['GET'])
@role_required()
def get_import_results():
    conn = create_db_connection()
    cursor = conn.cursor()

    # Fetch data from _uvMarketTrnConsignments
    cursor.execute("SELECT * FROM _uvMarketTrnConsignments")
    rows = cursor.fetchall()

    # Get column names
    column_names = [column[0] for column in cursor.description]

    # Process data into list of dictionaries
    results = [dict(zip(column_names, row)) for row in rows]

    # Close connections
    cursor.close()
    conn.close()

    return jsonify(results)


@import_bp.route('/get_dockets/<consignment_id>', methods=['GET'])
@role_required()
def get_dockets(consignment_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DocketNumber, QtySold, Price, SalesValue, DateSold
        FROM ZZMarketDataTrn
        WHERE ConsignmentID = ?
    """, (consignment_id,))

    dockets = cursor.fetchall()
    conn.close()

    return jsonify([{
        "DocketNumber": row[0],
        "QtySold": row[1],
        "Price": row[2],
        "SalesValue": row[3],
        "Date": row[4], 
    } for row in dockets])


@import_bp.route("/update_supplier_ref", methods=["POST"])
@role_required()
def update_supplier_ref():
    data = request.json  # Extract JSON data from the frontend
    new_del_note_no = data.get("newDelNoteNo")  # Ensure key matches frontend
    old_del_note_no = data.get("oldDelNoteNo")  # Ensure key matches frontend

    if not new_del_note_no or not old_del_note_no:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ZZMarketDataTrn SET DelNoteNo = ?
            FROM ZZMarketDataTrn
            WHERE DelNoteNo = ?
        """, (new_del_note_no, old_del_note_no))
        
        conn.commit()  # Commit changes
        return jsonify({"status": "success", "message": "Supplier Reference updated successfully"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

        
# @import_bp.route('/upload_excel', methods=['POST'])
# @role_required()
# def upload_excel():
#     file = request.files.get('file')
#     if not file:
#         return jsonify({"results": [{"file": "N/A", "status": "Failed", "message": "No file selected!"}]}), 400

#     try:
#         count = insert_data(file)  # Import the data and get the count of inserted rows

#         return jsonify({
#             "results": [{
#                 "file": file.filename,
#                 "status": "Success" if count > 0 else "Failed",
#                 "message": f"{count} lines imported successfully!" if count > 0 else "No lines imported"
#             }]
#         }), 200

#     except Exception as e:
#         return jsonify({
#             "results": [{
#                 "file": file.filename if file else "Unknown",
#                 "status": "Failed",
#                 "message": str(e)
#             }]
#         }), 500

@import_bp.route('/auto_import', methods=['GET'])
@role_required()
def auto_import():
    def generate_status():
        def yield_status(message):
            # Yield message in SSE format and give a small delay for delivery
            yield f"data: {message}\n\n"

        service = request.args.get('service')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not service:
            yield from yield_status("ERROR: Missing service parameter.")
            return
        if not start_date or not end_date:
            yield from yield_status("ERROR: Missing start_date or end_date.")
            return

        if service == "Technofresh":
            # extract_technofresh should also be updated similarly (not shown here)
            yield from Technofresh(current_user, start_date, end_date)
        elif service == "FreshLinq":
            yield from Freshlinq(current_user, start_date)

        else:
            yield from yield_status("ERROR: Invalid service type.")

    return Response(stream_with_context(generate_status()), content_type="text/event-stream")

def get_consignment_details(consignment_id):
    query = """
    SELECT DISTINCT 
        Product ,Variety ,Class ,Mass_kg ,Size ,QtySent ,Brand ,DelNoteNo
    FROM [dbo].[ZZMarketDataTrn]
    WHERE ConsignmentID = ?
    """
    
    matches_query = """
    Select DelLineIndex ,Product ,Variety ,Class ,Mass ,Size ,Brand ,DelLineQuantityBags
    from DelNoteLineLookup
    Where DelNoteNo = ?
    """

    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Get consignment details
        cursor.execute(query, (consignment_id,))
        consignment = cursor.fetchone()
        if not consignment:
            return jsonify({"error": "Consignment not found"}), 404

        consignment_details = {
            "ImportProduct": consignment[0],
            "ImportVariety": consignment[1],
            "ImportClass": consignment[2],
            "ImportMass": consignment[3],
            "ImportSize": consignment[4],
            "ImportQty": consignment[5],
            "ImportBrand": consignment[6]
        }
        DelNoteNo = consignment[7]

        # Get top matches
        cursor.execute(matches_query, (DelNoteNo,))
        matches = cursor.fetchall()

        matches_list = [
            {
                "DelLineIndex": row[0],
                "LineProduct": row[1],
                "LineMass": row[4],
                "LineClass": row[3],
                "LineSize": row[5],
                "LineVariety": row[2],
                "LineQty": row[7],
                "LineBrand": row[6]  # Add this line to handle the new field
            }
            for row in matches
        ]

        return jsonify({
            "consignment_details": consignment_details,
            "matches": matches_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@import_bp.route("/get_consignment_details", methods=["GET"])
@role_required()
def fetch_consignment_details():
    consignment_id = request.args.get("consignment_id")

    if not consignment_id:
        return jsonify({"error": "Consignment ID is required"}), 400

    return get_consignment_details(consignment_id)

@import_bp.route("/match_consignment/<consignment_id>/<int:line_id>", methods=["POST"])
@role_required()
def match_consignment(consignment_id, line_id):
    query = """
    UPDATE ZZDeliveryNoteLines
    SET ConsignmentID = ?
    WHERE DelLineIndex = ?
    """

    try:
        conn = create_db_connection() 
        cursor = conn.cursor()

        # Execute the update query
        cursor.execute(query, (consignment_id, line_id))
        conn.commit()

        # Check if any rows were affected
        if cursor.rowcount == 0:
            return jsonify({"error": "No matching line found for the given line ID."}), 404
        
        cursor.execute("EXEC SIGCreateSalesFromTrn")
        conn.commit()

        return jsonify({"message": "Consignment matched successfully."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()