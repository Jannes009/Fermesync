import requests
from flask import request, jsonify, render_template, abort
from .. import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import current_user
from flask_login import login_required
from datetime import datetime
from ..db_conversions import category_link_to_name, warehouse_link_to_code
from Inventory.routes.sdk_connection import EvolutionConnection
import Pastel.Evolution as Evo

@inventory_bp.route("/start_stock_count")
@login_required
def stock_count_start():
    return render_template("stock_count/stock_count.html")

@inventory_bp.route("/create_stock_count", methods=["POST"])
@login_required
def create_stock_count():
    if "STOCK_COUNT" not in current_user.permissions:
        abort(403)

    data = request.get_json()
    whse_id = data["warehouse"]
    cat_id = data["category"]
    if not whse_id or not cat_id:
        abort(400, "Warehouse and Category are required")

    conn = create_db_connection()
    cursor = conn.cursor()
    cat_name = category_link_to_name(cat_id, cursor)
    whse_code = warehouse_link_to_code(whse_id, cursor)
    
    # Header = session
    cursor.execute("""
        INSERT INTO [stk].InventoryCountHeaders (
            InvCountWhseId,
            InvCountWhseCode,
            InvCountCatId,
            InvCountCatName,
            InvCountUserId,
            InvCountUserName,
            InvCountStatus,
            InvCountTimeCreated
        )
        OUTPUT INSERTED.InvCountHeaderId
        VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', GETDATE())
    """, (whse_id, whse_code, cat_id, cat_name, current_user.id, current_user.username))

    header_id = cursor.fetchone()[0]

    # Snapshot system quantities ONCE
    cursor.execute("""
        INSERT INTO [stk].InventoryCountLines (
            InvCountLineHeaderId,
            InvCountLineStockCode,
            InvCountLineQtyOnHand
        )
        SELECT ?, StockCode, QtyOnHand
        FROM [stk]._uvInventoryQty
        WHERE WhseLink = ?
          AND idStockCategories = ?
    """, (header_id, whse_id, cat_id))

    conn.commit()
    conn.close()

    return jsonify({"session_id": header_id})


@inventory_bp.route("/fetch_categories", methods=["POST"])
def fetch_categories():
    whse_id = request.json.get("whse_id")
    conn = create_db_connection()
    cursor = conn.cursor()
    print(whse_id)

    cursor.execute("""
    Select Distinct ItemCategoryID, cCategoryName
    from [stk].[_uvWarehouseCategories]
    where WhseID = ?
    """, (whse_id,))

    rows = cursor.fetchall()

    conn.close()

    categories_list = [
        {
            "category_id": row.ItemCategoryID,
            "category_name": row.cCategoryName,
        }
        for row in rows
    ]
    return jsonify({"categories": categories_list})

@inventory_bp.route("/stock-counts/<int:header_id>")
@login_required
def stock_count_session(header_id):
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            InvCountHeaderId,
            InvCountTimeFinalised
        FROM [stk].InventoryCountHeaders
        WHERE InvCountHeaderId = ?
    """, header_id)
    row = cursor.fetchone()
    conn.close()
    print(row.InvCountTimeFinalised)
    if not row:
        abort(404)
    if row.InvCountTimeFinalised is not None:
        abort(409, "Stock count already finalised")
    return render_template(
        "stock_count/stock_count.html",
        session_id=header_id
    )

@inventory_bp.route("/stock-counts/<int:header_id>/products")
@login_required
def fetch_session_products(header_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            InvCountLineStockCode,
            InvCountLineQtyOnHand,
            InvCountLineQtyCounted
        FROM [stk].InventoryCountLines
        WHERE InvCountLineHeaderId = ?
    """, (header_id,))

    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        "products": [{
            "product_code": r.InvCountLineStockCode,
            "system_qty": float(r.InvCountLineQtyOnHand),
            "counted_qty": r.InvCountLineQtyCounted
        } for r in rows]
    })

@inventory_bp.route("/stock-counts/<int:header_id>/lines", methods=["POST"])
@login_required
def save_count_lines(header_id):
    data = request.get_json()
    lines = data["lines"]

    conn = create_db_connection()
    cursor = conn.cursor()

    for l in lines:
        cursor.execute("""
            UPDATE [stk].InventoryCountLines
            SET InvCountLineQtyCounted = ?
            WHERE InvCountLineHeaderId = ?
              AND InvCountLineStockCode = ?
        """, (
            l["counted_qty"],
            header_id,
            l["product_code"]
        ))

    conn.commit()
    conn.close()

    return jsonify({"success": True})

@inventory_bp.route("/stock-counts/<int:header_id>/finalise", methods=["POST"])
@login_required
def finalise_stock_count(header_id):
    if "STOCK_COUNT" not in current_user.permissions:
        abort(403)

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT InvCountWhseId, InvCountCatName
            FROM [stk].InventoryCountHeaders
            WHERE InvCountHeaderId = ?
              AND InvCountTimeFinalised IS NULL
        """, (header_id,))

        header = cursor.fetchone()
        if not header:
            abort(400, "Stock count already finalised or missing")

        cursor.execute("""
            SELECT InvCountLineStockCode, InvCountLineQtyOnHand, InvCountLineQtyCounted
            FROM [stk].InventoryCountLines
            WHERE InvCountLineQtyOnHand <> InvCountLineQtyCounted
              AND InvCountLineHeaderId = ?
        """, (header_id,))
        products = cursor.fetchall()

        whse_id, cat_name = header

        # fetch project for warehouse
        cursor.execute("""
            SELECT WhseAttrProjectDef FROM [stk].[WhseAttributes]
            WHERE WhseAttrWhseId = ?
        """, whse_id)
        result = cursor.fetchone()
        project = int(result[0]) if result and result[0] is not None else None

        with EvolutionConnection():
            for item in products:
                code = item.InvCountLineStockCode
                system_qty = float(item.InvCountLineQtyOnHand)
                counted_qty = float(item.InvCountLineQtyCounted)
                diff = counted_qty - system_qty

                if diff == 0:
                    continue

                trans = Evo.InventoryTransaction()
                trans.TransactionCode = Evo.TransactionCode(Evo.Module.Inventory, "ADJ")
                trans.InventoryItem = Evo.InventoryItem(code)
                trans.Quantity = abs(diff)
                trans.Operation = (
                    Evo.InventoryOperation.Increase
                    if diff > 0 else
                    Evo.InventoryOperation.Decrease
                )
                trans.Warehouse = Evo.Warehouse(int(whse_id))
                trans.Reference = f"STOCKTAKE-{header_id}"
                trans.Reference2 = cat_name
                trans.Description = f"Stocktake adjustment"
                if project:
                    trans.Project = Evo.Project(project)

                trans.Post()

        cursor.execute("""
            UPDATE [stk].InventoryCountHeaders
            SET InvCountTimeFinalised = GETDATE(),
                InvCountStatus = 'FINALISED'
            WHERE InvCountHeaderId = ?
        """, (header_id,))
        cursor.execute("""
            UPDATE [stk].[InventoryCountSchedule]
            SET LastCountDate = GETDATE()
            WHERE WhseId = (SELECT InvCountWhseId FROM [stk].InventoryCountHeaders WHERE InvCountHeaderId = ?)
                AND CategoryId = (SELECT InvCountCatId FROM [stk].InventoryCountHeaders WHERE InvCountHeaderId = ?)
        """, (header_id, header_id))

        conn.commit()

        return jsonify({"success": True})

    except Exception as ex:
        print(str(ex))
        conn.rollback()
        return jsonify({"success": False, "error": str(ex)}), 500

    finally:
        cursor.close()
        conn.close()
