import requests
from flask import request, jsonify, render_template, abort
from .. import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import current_user
from flask_login import login_required
from datetime import datetime, timedelta, date
from Inventory.routes.db_conversions import category_link_to_name, warehouse_link_to_code


def _normalize_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def format_date_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return "N/A"
        try:
            return datetime.fromisoformat(cleaned).date().strftime("%Y-%m-%d")
        except ValueError:
            try:
                return datetime.strptime(cleaned, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                return cleaned
    return str(value)


def get_count_age_tone(value):
    last_count = _normalize_date(value)
    if last_count is None:
        return "date-grey"

    days_since = (datetime.now().date() - last_count).days
    if days_since <= 14:
        return "date-green"
    if days_since <= 30:
        return "date-yellow"
    return "date-red"


def get_shelf_detail_data(warehouse_id, category_id):
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        warehouse = cursor.execute(
            "SELECT WhseCode, WhseDescription FROM cmn._uvWarehouses WHERE WhseLink = ?",
            (warehouse_id,)
        ).fetchone()
        if not warehouse:
            abort(404, description="Warehouse not found")

        category = cursor.execute(
            "SELECT cCategoryName FROM cmn._uvCategories WHERE idStockCategories = ?",
            (category_id,)
        ).fetchone()
        if not category:
            abort(404, description="Shelf not found")

        latest_count = cursor.execute("""
            SELECT TOP 1 InvCountTimeFinalised
            FROM [stk].InventoryCountHeaders
            WHERE InvCountWhseId = ?
              AND InvCountCatId = ?
              AND InvCountStatus = 'FINALISED'
            ORDER BY InvCountTimeFinalised DESC
        """, (warehouse_id, category_id)).fetchone()

        last_count = _normalize_date(latest_count[0]) if latest_count and latest_count[0] else None
        status = evaluate_count_status(last_count)

        cursor.execute("""
            SELECT
                h.InvCountHeaderId,
                CONVERT(date, h.InvCountTimeFinalised) AS CountDate,
                h.InvCountUserName,
                COUNT(l.InvCountLineHeaderId) AS TotalProducts,
                COUNT(l.InvCountLineQtyCounted) AS ProductsCounted,
                AVG(
                    CASE
                        WHEN l.InvCountLineQtyOnHand = 0 THEN NULL
                        WHEN l.InvCountLineQtyCounted IS NULL THEN NULL
                        ELSE (l.InvCountLineQtyCounted - l.InvCountLineQtyOnHand) * 100.0 / l.InvCountLineQtyOnHand
                    END
                ) AS AvgVariancePct
            FROM [stk].InventoryCountHeaders h
            LEFT JOIN [stk].InventoryCountLines l ON l.InvCountLineHeaderId = h.InvCountHeaderId
            WHERE h.InvCountWhseId = ?
              AND h.InvCountCatId = ?
              AND h.InvCountStatus = 'FINALISED'
            GROUP BY h.InvCountHeaderId, h.InvCountTimeFinalised, h.InvCountUserName
            ORDER BY h.InvCountTimeFinalised DESC
        """, (warehouse_id, category_id))

        history = []
        for r in cursor.fetchall():
            history.append({
                "headerId": r.InvCountHeaderId,
                "date": format_date_value(r.CountDate),
                "user": r.InvCountUserName,
                "productsCounted": r.ProductsCounted,
                "totalProducts": r.TotalProducts,
                "avgVariancePct": float(r.AvgVariancePct) if r.AvgVariancePct is not None else None,
            })

        cursor.execute("""
            SELECT
                STK.StockLink AS product_id,
                STK.StockDescription AS description,
                QTY.QtyOnHand AS system_qty,
                UOM.cUnitCode AS unit_code
            FROM [stk]._uvInventoryQty QTY
            LEFT JOIN [cmn]._uvStockItems STK ON STK.StockLink = QTY.StockLink
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = QTY.StockingUnitId
            WHERE QTY.WhseLink = ?
              AND QTY.idStockCategories = ?
            ORDER BY STK.StockDescription
        """, (warehouse_id, category_id))

        products = [{
            "product_id": r.product_id,
            "description": r.description or "Unknown product",
            "system_qty": float(r.system_qty) if r.system_qty is not None else 0,
            "unit_code": r.unit_code or ""
        } for r in cursor.fetchall()]

        return {
            "warehouse": {"id": warehouse_id, "code": warehouse[0], "description": warehouse[1]},
            "category": {"id": category_id, "name": category[0]},
            "last_count": format_date_value(last_count) if last_count else None,
            "last_count_tone": get_count_age_tone(last_count),
            "next_due": None,
            "status": status["status"],
            "status_label": status["label"],
            "history": history,
            "products": products,
            "product_count": len(products),
        }
    finally:
        conn.close()


def evaluate_count_status(last_count_date, next_due_date=None, today=None):
    today = today or datetime.now().date()
    last_count_date = _normalize_date(last_count_date)
    next_due_date = _normalize_date(next_due_date)

    if last_count_date is None:
        return {
            "status": "never",
            "label": "Never counted",
            "days_since": None,
            "days_until": None,
        }

    days_since = (today - last_count_date).days

    if next_due_date is not None:
        days_until = (next_due_date - today).days
        if next_due_date < today:
            days_overdue = (today - next_due_date).days
            return {
                "status": "overdue",
                "label": f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue",
                "days_since": days_since,
                "days_until": days_until,
            }
        if days_until <= 7:
            return {
                "status": "due",
                "label": "Due today" if days_until == 0 else f"Due in {days_until} day{'s' if days_until != 1 else ''}",
                "days_since": days_since,
                "days_until": days_until,
            }

    if days_since <= 14:
        return {
            "status": "recent",
            "label": "Today" if days_since == 0 else f"{days_since} day{'s' if days_since != 1 else ''} ago",
            "days_since": days_since,
            "days_until": (next_due_date - today).days if next_due_date else None,
        }

    if days_since <= 30:
        return {
            "status": "due",
            "label": "Due",
            "days_since": days_since,
            "days_until": (next_due_date - today).days if next_due_date else None,
        }

    return {
        "status": "overdue",
        "label": f"{days_since} day{'s' if days_since != 1 else ''} overdue",
        "days_since": days_since,
        "days_until": (next_due_date - today).days if next_due_date else None,
    }


@inventory_bp.route("/stock-counts")
@login_required
def stock_counts():
    return render_template("stock_count/stock_counts.html")

@inventory_bp.route("/stock-counts/overview")
@login_required
def stock_counts_overview():
    """Returns warehouse and shelf overview with the latest count status for each shelf."""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        warehouse_ids = [int(w) for w in (current_user.warehouses or []) if w is not None]
        if not warehouse_ids:
            return jsonify({"success": True, "warehouses": [], "incomplete": []})

        placeholder_sql = ','.join(['?'] * len(warehouse_ids))

        cursor.execute(f"""
            SELECT
                W.WhseLink AS warehouse_id,
                W.WhseCode AS warehouse_code,
                W.WhseDescription AS warehouse_description,
                CAT.ItemCategoryID AS category_id,
                CAT.cCategoryName AS category_name,
                MAX(H.InvCountTimeFinalised) AS last_count_date
            FROM [stk].[_uvWarehouseCategories] CAT
            JOIN cmn._uvWarehouses W ON W.WhseLink = CAT.WhseID
            LEFT JOIN [stk].InventoryCountHeaders H
                ON H.InvCountWhseId = CAT.WhseID
               AND H.InvCountCatId = CAT.ItemCategoryID
               AND H.InvCountStatus = 'FINALISED'
            WHERE W.WhseLink IN ({placeholder_sql})
            GROUP BY W.WhseLink, W.WhseCode, W.WhseDescription, CAT.ItemCategoryID, CAT.cCategoryName
            ORDER BY W.WhseCode, CAT.cCategoryName
        """, warehouse_ids)

        warehouse_rows = cursor.fetchall()

        product_counts = {}
        cursor.execute("""
            SELECT WhseLink, idStockCategories, COUNT(StockLink) AS product_count
            FROM [stk]._uvInventoryQty
            GROUP BY WhseLink, idStockCategories
        """)
        for row in cursor.fetchall():
            product_counts[(row.WhseLink, row.idStockCategories)] = int(row.product_count or 0)

        warehouses = {}
        for r in warehouse_rows:
            warehouse_id = r.warehouse_id
            warehouse_code = r.warehouse_code
            warehouse_desc = r.warehouse_description or warehouse_code
            warehouse = warehouses.setdefault(warehouse_id, {
                "id": warehouse_id,
                "code": warehouse_code,
                "description": warehouse_desc,
                "shelves": []
            })

            last_count = _normalize_date(r.last_count_date)
            product_count = product_counts.get((warehouse_id, r.category_id), 0)

            warehouse["shelves"].append({
                "id": r.category_id,
                "name": r.category_name,
                "lastCount": last_count.strftime("%Y-%m-%d") if last_count else None,
                "productCount": product_count,
                "nextDue": None,
                "status": evaluate_count_status(last_count)["status"],
                "statusLabel": evaluate_count_status(last_count)["label"],
                "daysSince": (datetime.now().date() - last_count).days if last_count else None,
                "daysUntil": None,
                "frequency": None,
            })

        cursor.execute(f"""
            SELECT
                h.InvCountHeaderId,
                                COALESCE(W.WhseDescription, h.InvCountWhseCode) AS warehouse_name,
                h.InvCountCatName,
                COUNT(l.InvCountLineHeaderId) AS TotalProducts,
                SUM(CASE WHEN l.InvCountLineQtyCounted IS NOT NULL THEN 1 ELSE 0 END) AS ProductsCounted
            FROM [stk].InventoryCountHeaders h
            LEFT JOIN [stk].InventoryCountLines l ON l.InvCountLineHeaderId = h.InvCountHeaderId
                        LEFT JOIN cmn._uvWarehouses W ON W.WhseLink = h.InvCountWhseId
            WHERE h.InvCountStatus = 'DRAFT'
              AND h.InvCountWhseId IN ({placeholder_sql})
                        GROUP BY h.InvCountHeaderId, W.WhseDescription, h.InvCountWhseCode, h.InvCountCatName, h.InvCountTimeCreated
            ORDER BY h.InvCountTimeCreated DESC
        """, warehouse_ids)

        incomplete = []
        for r in cursor.fetchall():
            total_products = int(r.TotalProducts or 0)
            counted = int(r.ProductsCounted or 0)
            incomplete.append({
                "headerId": r.InvCountHeaderId,
                "warehouse": r.warehouse_name,
                "shelf": r.InvCountCatName,
                "totalProducts": total_products,
                "countedProducts": counted,
                "progressPercent": 0 if total_products == 0 else min(100, round((counted / total_products) * 100)),
            })

        return jsonify({
            "success": True,
            "warehouses": list(warehouses.values()),
            "incomplete": incomplete,
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@inventory_bp.route("/stock-counts/history")
@login_required
def stock_counts_history():
    """Returns all stock count history"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
        SELECT
            h.InvCountHeaderId,
            CONVERT(date, h.InvCountTimeCreated) AS CountDate,
            h.InvCountWhseCode,
            h.InvCountCatName,
            h.InvCountStatus,
            h.InvCountTimeFinalised,
            h.InvCountUserName,
            AVG(
                CASE
                    WHEN l.InvCountLineQtyOnHand = 0 THEN NULL
                    WHEN l.InvCountLineQtyCounted IS NULL THEN NULL
                    ELSE (l.InvCountLineQtyCounted - l.InvCountLineQtyOnHand)
                         * 100.0
                         / l.InvCountLineQtyOnHand
                END
            ) AS AvgVariancePct,
            COUNT(l.InvCountLineHeaderId) AS TotalProducts,
            COUNT(l.InvCountLineQtyCounted) AS ProductsCounted
        FROM [stk].InventoryCountHeaders h
        LEFT JOIN [stk].InventoryCountLines l
            ON l.InvCountLineHeaderId = h.InvCountHeaderId
        WHERE INVCountStatus IN ('FINALISED', 'DRAFT')
        AND InvCountWhseId IN ({','.join(['?'] * len(current_user.warehouses))}) 

        GROUP BY
            h.InvCountHeaderId,
            h.InvCountTimeCreated,
            h.InvCountWhseCode,
            h.InvCountCatName,
            h.InvCountStatus,
            h.InvCountTimeFinalised,
            h.InvCountUserName
        ORDER BY h.InvCountTimeCreated DESC;

        """, current_user.warehouses)

        rows = []
        for r in cursor.fetchall():
            count_date = r.CountDate
            if getattr(count_date, "strftime", None):
                date_str = count_date.strftime("%Y-%m-%d")
            else:
                date_str = str(count_date) if count_date else "N/A"

            rows.append({
                "headerId": r.InvCountHeaderId,
                "date": date_str,
                "warehouse": r.InvCountWhseCode,
                "shelf": r.InvCountCatName,
                "username": r.InvCountUserName,
                "avgVariancePct": float(r.AvgVariancePct) if r.AvgVariancePct is not None else None,
                "countedProducts": r.ProductsCounted,
                "totalProducts": r.TotalProducts,
                "status": r.InvCountStatus,
                "canContinue": r.InvCountTimeFinalised is None
            })

        return jsonify({"success": True, "schedules": rows})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@inventory_bp.route("/stock-counts/shelf/<int:warehouse_id>/<int:category_id>")
@login_required
def stock_count_shelf_detail(warehouse_id, category_id):
    """Renders a full-page shelf overview with current products and historical counts."""
    data = get_shelf_detail_data(warehouse_id, category_id)
    return render_template("stock_count/shelf_detail.html", **data)

@inventory_bp.route("/stock_count_details/<int:header_id>")
@login_required
def stock_count_detail(header_id):
    """Returns detail lines for a specific stock count"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                InvCountWhseCode,
                InvCountCatName,
                InvCountUserName,
                InvCountTimeCreated,
                InvCountTimeFinalised
            FROM [stk].InventoryCountHeaders
            WHERE InvCountHeaderId = ?
        """, (header_id,))

        h = cursor.fetchone()
        if not h:
            return jsonify({"success": False, "message": "Stock count not found"}), 404

        cursor.execute("""
            SELECT
                l.InvCountLineStockId,
                STK.StockDescription,
                l.InvCountLineQtyOnHand,
                l.InvCountLineQtyCounted,
                UOM.cUnitCode
            FROM [stk].InventoryCountLines l
            LEFT JOIN [cmn]._uvStockItems STK ON STK.StockLink = l.InvCountLineStockId
            LEFT JOIN [cmn]._uvUOM UOM ON UOM.idUnits = l.InvCountUoMId
            WHERE l.InvCountLineHeaderId = ?
            ORDER BY STK.StockDescription
        """, (header_id,))

        lines = [{
            "stock": l[0],
            "description": l[1],
            "system": l[2],
            "counted": l[3],
            "unit": l[4],
            "variance": (l[3] - l[2]) if l[3] is not None else None
        } for l in cursor.fetchall()]

        def format_datetime(value):
            return value.strftime("%Y-%m-%d %H:%M:%S") if value else "N/A"

        return jsonify({
            "success": True,
            "warehouse": h[0],
            "shelf": h[1],
            "counted_by": h[2],
            "start_time": format_datetime(h[3]),
            "end_time": format_datetime(h[4]),
            "lines": lines
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@inventory_bp.route("/stock-counts/filters")
@login_required
def stock_counts_filters():
    """Returns available filter options"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT DISTINCT InvCountWhseCode FROM [stk].InventoryCountHeaders ORDER BY InvCountWhseCode")
        warehouses = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT InvCountCatName FROM [stk].InventoryCountHeaders WHERE InvCountCatName IS NOT NULL ORDER BY InvCountCatName")
        shelves = [r[0] for r in cursor.fetchall()]

        return jsonify({
            "success": True,
            "warehouses": warehouses,
            "shelves": shelves
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@inventory_bp.route("stock-counts/discard/<int:header_id>", methods=["POST"])
@login_required
def discard_stock_count(header_id):
    """Discards a draft stock count session"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # Verify the stock count is in DRAFT status
        cursor.execute("""
            SELECT InvCountStatus
            FROM [stk].InventoryCountHeaders
            WHERE InvCountHeaderId = ?
        """, (header_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Stock count session not found"}), 404
        if row.InvCountStatus != "DRAFT":
            return jsonify({"success": False, "message": "Only DRAFT stock counts can be discarded"}), 400

        # Delete header
        cursor.execute("""
            UPDATE [stk].InventoryCountHeaders
                SET InvCountTimeFinalised = GETDATE(),
                    InvCountStatus = 'DISCARDED'
            WHERE InvCountHeaderId = ?
        """, (header_id,))

        conn.commit()
        return jsonify({"success": True, "message": "Stock count session discarded successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()