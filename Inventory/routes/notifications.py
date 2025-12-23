
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from auth import get_common_db_connection, close_connection
from Inventory.routes import inventory_bp

# Return notifications count for current user
@inventory_bp.route("/notifications/count")
@login_required
def notifications_count():
    conn, cursor = get_common_db_connection()
    cursor.execute("""
        SELECT COUNT(*) 
        FROM Notifications
        WHERE UserID = ? AND IsRead = 0
    """, (current_user.id,))
    count = cursor.fetchone()[0]
    close_connection(conn, cursor)
    return jsonify({"count": count})

# Notifications page
@inventory_bp.route("/notifications")
@login_required
def notifications_page():
    conn, cursor = get_common_db_connection()
    cursor.execute("""
        SELECT Id, Title, Message, ActionURL, CreatedAt 
        FROM Notifications
        WHERE UserID = ? AND IsRead = 0
        ORDER BY CreatedAt DESC
        UPDATE Notifications
        SET IsRead = 1
        WHERE UserID = ? AND IsRead = 0
    """, (current_user.id, current_user.id))
    notifications = cursor.fetchall()
    print(notifications)
    cursor.commit()
    close_connection(conn, cursor)
    return render_template("notifications.html", notifications=notifications)
