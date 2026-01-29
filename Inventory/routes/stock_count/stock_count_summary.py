import requests
from flask import request, jsonify, render_template, abort
from .. import inventory_bp
from Inventory.db import create_db_connection
from flask_login import current_user
from flask_login import login_required
from datetime import datetime, timedelta

@inventory_bp.route("/stock-counts")
@login_required
def stock_counts():
    return render_template("stock_count/stock_counts.html")

@inventory_bp.route("/stock-counts/overview")
@login_required
def stock_counts_overview():
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                COUNT(DISTINCT h.InvCountHeaderId) AS completed,
                SUM(CASE WHEN ABS(l.InvCountLineQtyCounted - l.InvCountLineQtyOnHand) > 0 THEN 1 ELSE 0 END) AS withVariance
            FROM InventoryCountHeaders h
            LEFT JOIN InventoryCountLines l ON l.InvCountLineHeaderId = h.InvCountHeaderId
        """)

        r = cursor.fetchone()
        completed = r[0] or 0
        withVariance = r[1] or 0

        return jsonify({
            "completed": completed,
            "withVariance": withVariance,
            "overdue": 0,
            "dueSoon": 0
        })
    finally:
        conn.close()

@inventory_bp.route("/stock-counts/due")
@login_required
def stock_counts_due():
    """Returns shelves that are due or overdue for stock counting"""
    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                ICS.InvCountScheduleId,
                WH.WhseCode,
                WH.WhseDescription,
                ICS.CategoryId,
                ICS.CategoryName,
                ICS.Frequency,
                ICS.LastCountDate,
                ICS.NextDueDate
            FROM InventoryCountSchedule ICS
            JOIN _uvWarehouses WH ON WH.WhseLink = ICS.WhseId
            WHERE ICS.IsActive = 1
            ORDER BY ICS.NextDueDate ASC
        """)

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
        cursor.execute("""
        SELECT
            h.InvCountHeaderId,
            CONVERT(date, h.InvCountTimeCreated) AS CountDate,
            h.InvCountWhseCode,
            h.InvCountCatName,
            h.InvCountStatus,
            h.InvCountTimeFinalised,
            SUM(l.InvCountLineQtyOnHand) AS SystemQty,
            SUM(ISNULL(l.InvCountLineQtyCounted, 0)) AS CountedQty
        FROM InventoryCountHeaders h
        LEFT JOIN InventoryCountLines l
            ON l.InvCountLineHeaderId = h.InvCountHeaderId
        GROUP BY
            h.InvCountHeaderId,
            h.InvCountTimeCreated,
            h.InvCountWhseCode,
            h.InvCountCatName,
            h.InvCountStatus,
            h.InvCountTimeFinalised
        ORDER BY h.InvCountTimeCreated DESC
        """)

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
                "variance": variance,
                "status": r.InvCountStatus,
                "canContinue": r.InvCountTimeFinalised is None
            })

        return jsonify(rows)
    finally:
        conn.close()

@inventory_bp.route("/stock-counts/<int:header_id>")
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
                InvCountTimeFinalised
            FROM InventoryCountHeaders
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
            FROM InventoryCountLines l
            LEFT JOIN _uvStockItems STK ON STK.StockCode = l.InvCountLineStockCode
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
            "date": h[2].strftime("%Y-%m-%d") if h[2] else "N/A",
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
        cursor.execute("SELECT DISTINCT InvCountWhseCode FROM InventoryCountHeaders ORDER BY InvCountWhseCode")
        warehouses = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT InvCountCatName FROM InventoryCountHeaders WHERE InvCountCatName IS NOT NULL ORDER BY InvCountCatName")
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
    category = data.get("category")
    frequency = data.get("frequency")

    if not warehouse_id or not category or not frequency:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        # Convert inputs to correct types
        try:
            warehouse_id = int(warehouse_id)
            frequency = int(frequency)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid warehouse or frequency"}), 400

        # Get the most recent count date for this category
        cursor.execute("""
            SELECT TOP 1 InvCountTimeFinalised 
            FROM [dbo].[InventoryCountHeaders]
            WHERE InvCountCatName = ?
            ORDER BY InvCountTimeFinalised DESC
        """, (category,))
        
        last_count_row = cursor.fetchone()
        last_count_date = last_count_row[0] if last_count_row else None
        
        # Convert to date if it's datetime
        if last_count_date and isinstance(last_count_date, datetime):
            last_count_date = last_count_date.date()
        
        now = datetime.now()

        if last_count_date:
            next_due_date = last_count_date + timedelta(days=frequency)
        else:
            next_due_date = now + timedelta(days=frequency)

        print(f"Last count date: {last_count_date}, Next due date: {next_due_date}")

        # Insert the schedule
        cursor.execute("""
            INSERT INTO InventoryCountSchedule (
                WhseId,
                CategoryName,
                Frequency,
                LastCountDate,
                NextDueDate,
                IsActive,
                CreatedByUserId,
                CreatedAt
            )
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            warehouse_id,
            category,
            frequency,
            last_count_date,
            next_due_date,
            current_user.id,
            datetime.now()
        ))
        
        conn.commit()

        return jsonify({
            "success": True,
            "message": "Stock count schedule created successfully"
        }), 201

    except Exception as e:
        print(f"Error creating schedule: {str(e)}")
        conn.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()