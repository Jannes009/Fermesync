from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, jsonify, render_template, abort
from datetime import datetime, timedelta
from decimal import Decimal
import json

@inventory_bp.route("/qty")
@login_required
def inventory_qty():
    if "WHSE_QTYS" not in current_user.permissions:
        abort(403)
    return render_template("qty_dashboard.html")


@inventory_bp.route("/qty/data", methods=["GET"])
@login_required
def inventory_qty_data():
    if "WHSE_QTYS" not in current_user.permissions:
        abort(403)

    try:
        start_date = datetime.strptime(request.args["from"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.args["to"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({"success": False, "message": "Select a valid date range."}), 400
    if start_date > end_date:
        return jsonify({"success": False, "message": "Start date must be on or before end date."}), 400

    start_week = f"{start_date.isocalendar().year:04d}-{start_date.isocalendar().week:02d}"
    end_week = f"{end_date.isocalendar().year:04d}-{end_date.isocalendar().week:02d}"
    warehouses = get_warehouse_list()
    warehouse_ids = tuple(warehouse["WhseLink"] for warehouse in warehouses)
    if not warehouse_ids:
        return jsonify({"success": True, "warehouses": [], "items": []})

    placeholders = ",".join("?" for _ in warehouse_ids)
    query = f"""
        WITH CandidateStocks AS (
            SELECT DISTINCT QTY.StockLink
            FROM stk._uvInventoryQty QTY
            JOIN cmn._uvStockItems STK ON STK.StockLink = QTY.StockLink AND STK.ItemActive = 1
            WHERE QTY.WhseLink IN ({placeholders})
            UNION
            SELECT DISTINCT P.SprayLineStkId
            FROM agr._uvStockProjectionUnitsNeededPerWH P
            JOIN cmn._uvStockItems STK ON STK.StockLink = P.SprayLineStkId AND STK.ItemActive = 1
            WHERE P.SprayHWeek >= ?
              AND P.SprayHWeek <= ?
              AND P.SprayHWhseId IN ({placeholders})
        ), Demand AS (
            SELECT
                P.SprayLineStkId AS StockLink,
                P.SprayHWhseId AS WhseLink,
                SUM(ISNULL(P.StockingUnitsNeeded, 0)) AS QtyNeeded
            FROM agr._uvStockProjectionUnitsNeededPerWH P
            WHERE P.SprayHWeek >= ?
              AND P.SprayHWeek <= ?
              AND P.SprayHWhseId IN ({placeholders})
            GROUP BY P.SprayLineStkId, P.SprayHWhseId
        )
        SELECT
            STK.StockLink,
            STK.StockDescription,
            ACT.ChemActIngredient,
            WHSE.WhseLink,
            WHSE.WhseCode,
            WHSE.WhseDescription,
            CASE WHEN QTY.StockLink IS NOT NULL OR Demand.StockLink IS NOT NULL THEN 1 ELSE 0 END AS IsLinked,
            ISNULL(QTY.QtyOnHand, 0) AS QtyOnHand,
            ISNULL(QTY.QtyOnPO, 0) AS QtyOnPO,
            ISNULL(QTY.QtyOnIBT, 0) AS QtyOnIBT,
            ISNULL(Demand.QtyNeeded, 0) AS QtyNeeded
        FROM CandidateStocks Candidate
        JOIN cmn._uvStockItems STK ON STK.StockLink = Candidate.StockLink
        LEFT JOIN agr.ChemStock Chem ON Chem.ChemStockLink = STK.StockLink
        LEFT JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = Chem.ChemStockActiveIngrId
        CROSS JOIN (
            SELECT WhseLink, WhseCode, WhseDescription
            FROM cmn._uvWarehouses
            WHERE WhseLink IN ({placeholders})
        ) WHSE
        LEFT JOIN stk._uvInventoryQty QTY
            ON QTY.StockLink = STK.StockLink
            AND QTY.WhseLink = WHSE.WhseLink
        LEFT JOIN Demand
            ON Demand.StockLink = STK.StockLink
            AND Demand.WhseLink = WHSE.WhseLink
        ORDER BY STK.StockDescription, WHSE.WhseCode
    """
    params = (
        *warehouse_ids,
        start_week, end_week, *warehouse_ids,
        start_week, end_week, *warehouse_ids,
        *warehouse_ids,
    )

    conn = create_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Unable to connect to the inventory database."}), 500
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        items_by_stock = {}
        for row in cursor.fetchall():
            stock_link = int(row.StockLink)
            qty_on_hand = float(row.QtyOnHand or 0)
            qty_on_po = float(row.QtyOnPO or 0)
            qty_on_ibt = float(row.QtyOnIBT or 0)
            qty_needed = float(row.QtyNeeded or 0)
            is_linked = bool(row.IsLinked)
            status = _warehouse_stock_status(qty_needed, qty_on_hand, qty_on_po, qty_on_ibt) if is_linked else "unlinked"

            item = items_by_stock.setdefault(stock_link, {
                "stock_id": stock_link,
                "description": row.StockDescription,
                "active_ingredient": row.ChemActIngredient,
                "warehouses": [],
            })
            item["warehouses"].append({
                "id": int(row.WhseLink),
                "is_linked": is_linked,
                "qty_available": qty_on_hand,
                "status": status,
            })

        return jsonify({
            "success": True,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "warehouses": warehouses,
            "items": list(items_by_stock.values()),
        })
    except Exception as exc:
        print(f"inventory_qty_data error: {exc}")
        return jsonify({"success": False, "message": "Unable to load warehouse quantities."}), 500
    finally:
        close_db_connection(conn)


@inventory_bp.route("/qty/detail/<int:stock_link>", methods=["GET"])
@login_required
def inventory_qty_detail(stock_link):
    if "WHSE_QTYS" not in current_user.permissions:
        abort(403)

    try:
        start_date = datetime.strptime(request.args["from"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.args["to"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return jsonify({"success": False, "message": "Select a valid date range."}), 400
    if start_date > end_date:
        return jsonify({"success": False, "message": "Start date must be on or before end date."}), 400

    start_week = f"{start_date.isocalendar().year:04d}-{start_date.isocalendar().week:02d}"
    end_week = f"{end_date.isocalendar().year:04d}-{end_date.isocalendar().week:02d}"
    warehouses = get_warehouse_list()
    warehouse_ids = tuple(warehouse["WhseLink"] for warehouse in warehouses)
    if not warehouse_ids:
        return jsonify({"success": True, "warehouses": []})

    placeholders = ",".join("?" for _ in warehouse_ids)
    conn = create_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Unable to connect to the inventory database."}), 500
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            WITH Demand AS (
                SELECT
                    P.SprayLineStkId AS StockLink,
                    P.SprayHWhseId AS WhseLink,
                    SUM(ISNULL(P.StockingUnitsNeeded, 0)) AS QtyNeeded
                FROM agr._uvStockProjectionUnitsNeededPerWH P
                WHERE P.SprayLineStkId = ?
                  AND P.SprayHWeek >= ?
                  AND P.SprayHWeek <= ?
                  AND P.SprayHWhseId IN ({placeholders})
                GROUP BY P.SprayLineStkId, P.SprayHWhseId
            )
            SELECT
                WHSE.WhseLink,
                WHSE.WhseCode,
                WHSE.WhseDescription,
                CASE WHEN QTY.StockLink IS NOT NULL OR Demand.StockLink IS NOT NULL THEN 1 ELSE 0 END AS IsLinked,
                ISNULL(QTY.QtyOnHand, 0) AS QtyOnHand,
                ISNULL(QTY.QtyOnPO, 0) AS QtyOnPO,
                ISNULL(QTY.QtyOnIBT, 0) AS QtyOnIBT,
                ISNULL(Demand.QtyNeeded, 0) AS QtyNeeded
            FROM cmn._uvWarehouses WHSE
            LEFT JOIN stk._uvInventoryQty QTY
                ON QTY.WhseLink = WHSE.WhseLink
                AND QTY.StockLink = ?
            LEFT JOIN Demand
                ON Demand.WhseLink = WHSE.WhseLink
                AND Demand.StockLink = ?
            WHERE WHSE.WhseLink IN ({placeholders})
            ORDER BY WHSE.WhseCode
        """, (
            stock_link, start_week, end_week, *warehouse_ids,
            stock_link, stock_link, *warehouse_ids,
        ))
        warehouses_detail = []
        for row in cursor.fetchall():
            qty_on_hand = float(row.QtyOnHand or 0)
            qty_on_po = float(row.QtyOnPO or 0)
            qty_on_ibt = float(row.QtyOnIBT or 0)
            qty_needed = float(row.QtyNeeded or 0)
            warehouses_detail.append({
                "id": int(row.WhseLink),
                "code": row.WhseCode,
                "name": row.WhseDescription,
                "is_linked": bool(row.IsLinked),
                "qty_available": qty_on_hand,
                "qty_needed": qty_needed,
                "qty_on_po": qty_on_po,
                "qty_on_ibt": qty_on_ibt,
                "status": (
                    _warehouse_stock_status(qty_needed, qty_on_hand, qty_on_po, qty_on_ibt)
                    if row.IsLinked else "unlinked"
                ),
            })
        return jsonify({"success": True, "warehouses": warehouses_detail})
    except Exception as exc:
        print(f"inventory_qty_detail error: {exc}")
        return jsonify({"success": False, "message": "Unable to load warehouse details."}), 500
    finally:
        close_db_connection(conn)


def _warehouse_stock_status(qty_needed, qty_on_hand, qty_on_po, qty_on_ibt):
    if qty_on_hand >= qty_needed:
        return "enough"
    incoming = max(qty_on_po, 0) + max(qty_on_ibt, 0)
    if incoming > 0 and qty_on_hand + incoming >= qty_needed:
        return "incoming"
    return "action"

def get_warehouse_list():
    """Get list of warehouses the user has access to"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        warehouses = current_user.warehouses
        if len(warehouses) == 0:
            return []
        placeholders = ",".join(["?"] * len(warehouses))
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT WhseLink, WhseCode, WhseDescription
            FROM cmn._uvWarehouses
            WHERE WhseLink IN ({placeholders})
            ORDER BY WhseCode
        """, warehouses)
        rows = cursor.fetchall()
        warehouses = [
            {"WhseLink": r.WhseLink, "WhseCode": r.WhseCode, "WhseDescription": r.WhseDescription}
            for r in rows
        ]
        return warehouses

    except Exception as e:
        print(f"Error fetching warehouses: {e}")
        return []
    finally:
        close_db_connection(conn)

def get_warehouse_stock(warehouse_id):
    """Get stock levels for all products in the selected warehouse"""
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = """
        WITH FirstNegative AS (
            SELECT 
                SprayLineStkId,
                SprayHWhseId,
                SprayHWeek,
                ProjectedBalance,
                ROW_NUMBER() OVER (
                    PARTITION BY SprayLineStkId, SprayHWhseId 
                    ORDER BY SprayHWeek
                ) AS rn
            FROM [agr].[_uvStockProjection]
            WHERE ProjectedBalance < 0
        )

        SELECT 
            QTY.StockLink, 
            QTY.StockCode, 
            QTY.StockDescription, 
			ACT.ChemActIngredient,
            QTY.cCategoryName,
            COALESCE(QTY.QtyOnHand, 0) AS QtyOnHand,
            COALESCE(QTY.QtyOnPo, 0) AS QtyOnPo, 
            COALESCE(QTY.IncompleteIssuesQty, 0) AS QtyOnIssues, 
            FN.SprayHWeek
        FROM stk._uvInventoryQty QTY
		LEFT JOIN agr.ChemStock STK on STK.ChemStockLink = QTY.StockLink
		LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
        LEFT JOIN FirstNegative FN 
            ON FN.SprayHWhseId = QTY.WhseLink 
            AND FN.SprayLineStkId = QTY.StockLink
            AND FN.rn = 1
        WHERE QTY.WhseLink = ?
        ORDER BY ACT.ChemActIngredient, QTY.StockCode;
        """
        cursor.execute(query, (warehouse_id,))
        rows = cursor.fetchall()
        stock = [
            {
                "StockLink": r.StockLink,
                "StockCode": r.StockCode,
                "StockDescription": r.StockDescription,
                "ActiveIngredient": r.ChemActIngredient,
                "Category": r.cCategoryName,
                "QtyOnHand": format_qty(r.QtyOnHand),
                "QtyOnPo": format_qty(r.QtyOnPo),
                "QtyOnIssues": format_qty(r.QtyOnIssues),
                "SprayHWeek": r.SprayHWeek
            }
            for r in rows
        ]
        return stock

    except Exception as e:
        print(f"Error fetching warehouse stock: {e}")
        return []
    finally:
        close_db_connection(conn)


def format_qty(value, ndigits=2):
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    try:
        v = float(value)
    except (ValueError, TypeError):
        return value

    if v.is_integer():
        return int(v)
    return round(v, ndigits)
 