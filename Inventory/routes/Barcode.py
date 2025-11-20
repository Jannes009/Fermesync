import sys
from flask import request, jsonify, render_template
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required


# ============================
#   BARCODE SCANNER PAGE
# ============================
@inventory_bp.route("/barcode_scanner", methods=["GET"])
@login_required
def barcode_scanner():
    return render_template("barcode_scanner.html")


# ============================
#   FETCH PRODUCTS
# ============================
@inventory_bp.route("/fetch_products", methods=["POST"])
def fetch_products():
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT StockLink, StockDescription, PurchaseUnitCode, UOMCategoryId
            FROM _uvInventoryQty
        """)

        rows = cursor.fetchall()
        conn.close()

        products_list = [
            {
                "product_id": row[0],
                "product_desc": row[1],
                "purchase_uom": row[2],
                "uom_cat_id": row[3],
            }
            for row in rows
        ]

        return jsonify({"success": True, "products": products_list})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================
#   FETCH PRODUCT UOMs
# ============================
@inventory_bp.route("/fetch_product_uoms", methods=["POST"])
def fetch_product_uoms():
    try:
        data = request.get_json()
        uom_cat_id = data.get("uom_cat_id")

        if uom_cat_id is None:
            return jsonify({"success": False, "error": "Missing uom_cat_id"}), 400

        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT idUnits, cUnitCode
            FROM _uvUOM
            WHERE iUnitCategoryID = ?
        """, (uom_cat_id,))

        rows = cursor.fetchall()
        conn.close()

        uom_list = [
            {"id": row[0], "code": row[1]}
            for row in rows
        ]

        return jsonify({"success": True, "uoms": uom_list})

    except Exception as e:
        print(sys.exc_info(), e)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================
#   SUBMIT BARCODE SCAN
# ============================
@inventory_bp.route("/submit_barcode_scan", methods=["POST"])
def submit_barcode_scan():
    try:
        item = request.get_json()

        required = ["barcode", "stock_code", "uom"]
        for field in required:
            if field not in item:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400

        conn = create_db_connection()
        cursor = conn.cursor()

        # check if barcode already exists
        cursor.execute("""
            SELECT COUNT(*)
            FROM [UB_UITDRAAI_BDY].dbo.[_etblBarcodes]
            WHERE Barcode = ?
        """, (item["barcode"],))
        exists = cursor.fetchone()[0]
        if exists:
            return jsonify({
                "success": False,
                "error": "Barcode already exists."
            }), 400

        cursor.execute("""
            INSERT INTO [UB_UITDRAAI_BDY].dbo.[_etblBarcodes] (
                Barcode, 
                StockID, 
                WhseID, 
                UOMID,
                _etblBarcodes_iBranchID,
                _etblBarcodes_dCreatedDate
            )
            VALUES (?, ?, -1, ?, 0, GETDATE())
        """, (
            item["barcode"],
            item["stock_code"],
            item["uom"]
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Barcode scan saved successfully."
        })

    except Exception as e:
        print(sys.exc_info(), e)
        return jsonify({"success": False, "error": str(e)}), 500
