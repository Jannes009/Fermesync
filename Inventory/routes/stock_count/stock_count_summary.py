import requests
from flask import request, jsonify, render_template, abort
from .. import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import current_user
from flask_login import login_required
from datetime import datetime, timedelta, date
from Inventory.routes.db_conversions import category_link_to_name, warehouse_link_to_code

@inventory_bp.route("/stock-counts")
@login_required
def stock_counts():
    return render_template("stock_count/stock_counts.html")

@inventory_bp.route("/stock-counts/due")
@login_required
def stock_counts_due():
    """Returns shelves that are due or overdue for stock counting"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            SELECT
                ICS.InvCountScheduleId,
                WH.WhseCode,
                WH.WhseDescription,
                ICS.CategoryId,
                ICS.CategoryName,
                ICS.Frequency,
                ICS.LastCountDate,
                ICS.NextDueDate
            FROM [stk].InventoryCountSchedule ICS
            JOIN cmn._uvWarehouses WH ON WH.WhseLink = ICS.WhseId
            WHERE ICS.IsActive = 1 AND WH.WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
            ORDER BY ICS.NextDueDate ASC
        """, current_user.warehouses)

        rows = []
        today = datetime.now().date()

        for r in cursor.fetchall():
            schedule_id = r.InvCountScheduleId
            warehouse = r.WhseCode
            warehouse_desc = r.WhseDescription
            category = r.CategoryName
            frequency = r.Frequency
            last_count = r.LastCountDate
            next_due = r.NextDueDate

            # Convert datetime to date if needed
            if last_count and isinstance(last_count, datetime):
                last_count = last_count.date()
            
            if next_due and isinstance(next_due, datetime):
                next_due = next_due.date()

            # Determine status
            if next_due and next_due < today:
                status = "Overdue"
                days_overdue = (today - next_due).days
                status_text = f"Overdue by {days_overdue} days"
            elif next_due and (next_due - today).days <= 7:
                status = "DueSoon"
                days_until = (next_due - today).days
                status_text = f"Due in {days_until} days"
            else:
                status = "OnSchedule"
                days_until = (next_due - today).days if next_due else 0
                status_text = f"Due in {days_until} days"

            rows.append({
                "scheduleId": schedule_id,
                "warehouse": warehouse,
                "warehouseDesc": warehouse_desc,
                "shelf": category,
                "frequency": frequency,
                "lastCount": last_count.strftime("%Y-%m-%d") if last_count else "Never",
                "nextDue": next_due.strftime("%Y-%m-%d") if next_due else "N/A",
                "status": status,
                "statusText": status_text
            })

        return jsonify(rows)
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

            -- Totals
            SUM(l.InvCountLineQtyOnHand) AS SystemQty,
            SUM(ISNULL(l.InvCountLineQtyCounted, 0)) AS CountedQty,

            -- New counts
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
            h.InvCountTimeFinalised
        ORDER BY h.InvCountTimeCreated DESC;

        """, current_user.warehouses)

        rows = []
        for r in cursor.fetchall():
            # normalize date value (could be datetime/date or string)
            count_date = r.CountDate
            if getattr(count_date, "strftime", None):
                date_str = count_date.strftime("%Y-%m-%d")
            else:
                date_str = str(count_date) if count_date else "N/A"

            system_qty = float(r.SystemQty or 0)
            counted_qty = float(r.CountedQty or 0)
            variance = counted_qty - system_qty

            rows.append({
                "headerId": r.InvCountHeaderId,
                "date": date_str,
                "warehouse": r.InvCountWhseCode,
                "shelf": r.InvCountCatName,
                "systemQty": system_qty,
                "countedQty": counted_qty,
                "countedProducts": r.ProductsCounted,
                "totalProducts": r.TotalProducts,
                "variance": variance,
                "status": r.InvCountStatus,
                "canContinue": r.InvCountTimeFinalised is None
            })

        return jsonify(rows)
    finally:
        conn.close()

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
                InvCountUsername,
                InvCountTimeFinalised
            FROM [stk].InventoryCountHeaders
            WHERE InvCountHeaderId = ?
        """, (header_id,))

        h = cursor.fetchone()
        if not h:
            return jsonify({"error": "Stock count not found"}), 404

        cursor.execute("""
            SELECT
                l.InvCountLineStockCode,
                STK.StockDescription,
                l.InvCountLineQtyOnHand,
                l.InvCountLineQtyCounted
            FROM [stk].InventoryCountLines l
            LEFT JOIN [cmn]._uvStockItems STK ON STK.StockCode = l.InvCountLineStockCode
            WHERE l.InvCountLineHeaderId = ?
            ORDER BY l.InvCountLineStockCode
        """, (header_id,))

        lines = [{
            "stock": l[0],
            "description": l[1],
            "system": l[2],
            "counted": l[3],
            "variance": l[3] - l[2]
        } for l in cursor.fetchall()]

        return jsonify({
            "warehouse": h[0],
            "shelf": h[1],
            "counted_by": h[2],
            "date": h[3].strftime("%Y-%m-%d") if h[2] else "N/A",
            "lines": lines
        })
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
            "warehouses": warehouses,
            "shelves": shelves
        })
    finally:
        conn.close()

@inventory_bp.route("/stock-counts/create_schedule", methods=["POST"])
@login_required
def create_stock_count_schedule():
    """Creates a new stock count schedule"""
    data = request.get_json()
    warehouse_id = data.get("warehouse")
    category_id = data.get("category")
    frequency = data.get("frequency")

    if not warehouse_id or not category_id or not frequency:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    # Convert inputs to correct types
    try:
        category_name = category_link_to_name(category_id, cursor)

        warehouse_id = int(warehouse_id)
        category_id = int(category_id)
        frequency = int(frequency)
    except (ValueError, TypeError):
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": "Invalid warehouse or frequency"}), 400

    # Get the most recent count date for this category
    cursor.execute("""
        SELECT TOP 1 InvCountTimeFinalised 
        FROM [stk].[InventoryCountHeaders]
        WHERE InvCountCatId = ? AND InvCountWhseId = ?
        ORDER BY InvCountTimeFinalised DESC
    """, (category_id, warehouse_id))
    
    last_count_row = cursor.fetchone()
    last_count_date = last_count_row[0] if last_count_row else None
    
    # Normalize dates to datetime (pyodbc expects datetime.datetime for DATETIME parameters)
    def to_datetime(dt):
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt
        if isinstance(dt, date):
            return datetime.combine(dt, datetime.min.time())
        try:
            # fallback for strings like '2026-01-31'
            return datetime.fromisoformat(str(dt))
        except Exception:
            return None

    last_count_dt = to_datetime(last_count_date)
    
    now = datetime.now()

    if last_count_dt:
        next_due_dt = last_count_dt + timedelta(days=frequency)
    else:
        next_due_dt = now + timedelta(days=frequency)

    try:
        # Insert the schedule — pass datetime objects (or None) not date
        cursor.execute("""
            INSERT INTO [stk].InventoryCountSchedule (
                WhseId,
                CategoryId,
                CategoryName,
                Frequency,
                LastCountDate,
                NextDueDate,
                IsActive,
                CreatedByUserId,
                CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, GETDATE())
        """, (
            warehouse_id,
            category_id,
            category_name,
            frequency,
            last_count_dt,
            next_due_dt,
            current_user.id
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "success": True,
        "message": "Stock count schedule created successfully"
    }), 201

    # except Exception as e:
    #     print(f"Error creating schedule: {str(e)}")
    #     conn.rollback()
    #     return jsonify({
    #         "success": False,
    #         "error": str(e)
    #     }), 500
    # finally:
    #     cursor.close()
    #     conn.close()

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
            return jsonify({"success": False, "error": "Stock count session not found"}), 404
        if row.InvCountStatus != "DRAFT":
            return jsonify({"success": False, "error": "Only DRAFT stock counts can be discarded"}), 400

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
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()