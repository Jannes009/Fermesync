from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp

@agri_bp.route("/fetch_spray_for_issue", methods=["GET"])
def fetch_spray_for_issue():
    # Implementation for fetching spray information for stock issue
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
    Select IdSprExec, SprExecDate, PPL.PersonName, HEA.SprayHWhseId
    from agr.SprayExecution EXE
    JOIN [agr].[SprayHeader] HEA on HEA.SprayHExecutionId = EXE.IdSprExec
    JOIN [agr].[People] PPL on PPL.IdPerson = EXE.SprExecResponsiblePerson
    Where EXE.SprExecFinalised = 0
    """)
    rows = cursor.fetchall()
    conn.close()
    return jsonify({"executions": [
        {"execution_id": row.IdSprExec, "date": row.SprExecDate, "responsible_person": row.PersonName, "warehouse_id": row.SprayHWhseId}
        for row in rows
    ]})

@agri_bp.route("/fetch_spray_products", methods=["GET"])
@login_required
def fetch_spray_products():
    try:
        execution_id = request.args.get("execution_id")
        if not execution_id:
            return jsonify({"status": "error", "message": "Execution ID is required"}), 400

        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        Select WhseId, StockId, SUM(TotalQty) as TotalQty, QtyAvailable, UoMId
        from [agr].[_uvSprayStockRequirements]
        Where SprayHExecutionId = ?
        Group by WhseId, StockId, QtyAvailable, UoMId
        """, (execution_id,))
        rows = cursor.fetchall()

        conn.close()

        products_list = []
        for row in rows:
            products_list.append({
                "stock_id": row.StockId,
                "total_qty": row.TotalQty,
                "qty_available": row.QtyAvailable,
                "warehouse_id": row.WhseId,
                "uom_id": row.UoMId
            })
        return jsonify({"spray_products": products_list})
    except Exception as e:
        print("Error fetching spray products:", e)
        return jsonify({"status": "error", "message": "Failed to fetch spray products"}), 500

@agri_bp.route("/fetch_products_for_spray_execution", methods=["GET"])
@login_required
def fetch_products_for_spray():
    """Returns only products that are on the spray instruction"""
    execution_id = request.args.get("execution_id")
    if not execution_id:
        return jsonify({"status": "error", "message": "Execution ID is required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    Select DISTINCT StockId, STK.StockCode, STK.StockDescription, UoMId, UOM.cUnitCode, QtyAvailable, WhseId
    from [agr].[_uvSprayStockRequirements] REQ
    JOIN [cmn].[_uvStockItems] STK on STK.StockLink = REQ.StockId
    JOIN [cmn].[_uvUOM] UOM on UOM.idUnits = UoMId
    Where SprayHExecutionId = ?
    """, (execution_id,))
    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_link": row.StockId,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "stocking_uom_id": row.UoMId,
            "stocking_uom_code": row.cUnitCode,
            "warehouse_id": row.WhseId,
            "qty_in_whse": row.QtyAvailable or 0
        }
        for row in rows
    ]
    return jsonify({"products": products_list})

