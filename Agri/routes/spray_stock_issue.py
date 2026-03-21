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
    Select SprayHNo, SprayHDescription, SprayHWhseId, IdSprayH
    --Select * 
    from [agr].[SprayHeader]
    """)
    rows = cursor.fetchall()
    conn.close()
    return jsonify({"sprays": [
        {"spray_id": row.IdSprayH, "description": row.SprayHDescription, "warehouse_id": row.SprayHWhseId, "spray_no": row.SprayHNo}
        for row in rows
    ]})

@agri_bp.route("/fetch_spray_products", methods=["GET"])
@login_required
def fetch_spray_products():
    spray_id = request.args.get("spray_id")
    if not spray_id:
        return jsonify({"status": "error", "message": "Spray ID is required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT SprayHApplicationType FROM [agr].[SprayHeader] WHERE IdSprayH = ?
    """, (spray_id,))
    spray_type_row = cursor.fetchone()
    app_type = spray_type_row.SprayHApplicationType if spray_type_row else "Unknown"
    if app_type == "spray":
        cursor.execute("""
        SELECT 
            SprayMixLineStockId, SUM(SprayMixLineQty) TotalQty, IsNULL(QTY.QtyOnHand, 0) QtyAvailable, SPRHEA.SprayHWhseId
        FROM agr.SprayMixLines LIN
        JOIN agr.SprayMix HEA ON HEA.IdSprayMix = LIN.SprayMixLineMixId
        JOIN [agr].[SprayHeader] SPRHEA on SPRHEA.IdSprayH = HEA.SprayMixHeaderId
        LEFT JOIN stk._uvInventoryQty QTY 
            ON QTY.StockLink = LIN.SprayMixLineStockId 
            AND QTY.WhseLink = SPRHEA.SprayHWhseId
        WHERE HEA.SprayMixHeaderId = ?
        GROUP BY SprayMixLineStockId, QtyOnHand, SprayHWhseId
        """, (spray_id,))
        rows = cursor.fetchall()
    elif app_type == "direct":
        cursor.execute("""
        Select SprayLineStkId, ISNULL(SprayLineQtyPerHa * SUM(PA.ProjAttrHa), 0) TotalQty, IsNULL(QTY.QtyOnHand, 0) QtyAvailable, HEA.SprayHWhseId
        --Select *
        from [agr].[SprayLines] LIN
        JOIN [agr].[SprayHeader] HEA on HEA.IdSprayH = LIN.SprayLineHeaderId
        JOIN [agr].[SprayProjects] SP on SP.SprayPSprayId = HEA.IdSprayH
        JOIN [agr].[ProjectAttributes] PA on PA.ProjAttrProjectId = SP.SprayPProjectId
        LEFT JOIN stk._uvInventoryQty QTY 
            ON QTY.StockLink = LIN.SprayLineStkId 
            AND QTY.WhseLink = HEA.SprayHWhseId
        WHERE HEA.IdSprayH = ?
        GROUP BY SprayLineStkId, QtyOnHand, SprayHWhseId, SprayLineQtyPerHa)
        """, (spray_id,))
        rows = cursor.fetchall()

    conn.close()

    methods_list = []
    for row in rows:
        methods_list.append({
            "stock_id": row.SprayMixLineStockId,
            "total_qty": row.TotalQty,
            "qty_available": row.QtyAvailable,
            "warehouse_id": row.SprayHWhseId
        })
    return jsonify({"spray_products": methods_list})

@agri_bp.route("/fetch_products_for_spray", methods=["GET"])
@login_required
def fetch_products_for_spray():
    """Returns only products that are on the spray instruction"""
    spray_id = request.args.get("spray_id")
    if not spray_id:
        return jsonify({"status": "error", "message": "Spray ID is required"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT
        LIN.SprayMixLineStockId,
        INV.StockCode,
        INV.StockDescription,
        INV.StockingUnitId,
        INV.StockingUnitCode,
        SPRHEA.SprayHWhseId,
        INV.QtyOnHand
    FROM agr.SprayMixLines LIN
    JOIN agr.SprayMix HEA ON HEA.IdSprayMix = LIN.SprayMixLineMixId
    JOIN [agr].[SprayHeader] SPRHEA on SPRHEA.IdSprayH = HEA.SprayMixHeaderId
    JOIN [stk]._uvInventoryQty INV ON INV.StockLink = LIN.SprayMixLineStockId AND INV.WhseLink = SPRHEA.SprayHWhseId
    WHERE HEA.SprayMixHeaderId = ?
    """, (spray_id,))
    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_link": row.SprayMixLineStockId,
            "product_code": row.StockCode,
            "product_desc": row.StockDescription,
            "stocking_uom_id": row.StockingUnitId,
            "stocking_uom_code": row.StockingUnitCode,
            "warehouse_id": row.SprayHWhseId,
            "qty_in_whse": row.QtyOnHand or 0
        }
        for row in rows
    ]
    return jsonify({"products": products_list})

