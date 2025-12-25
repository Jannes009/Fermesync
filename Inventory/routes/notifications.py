
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

@inventory_bp.route("/notifications/create_notification", methods=["POST"])
def create_notification():
    data = request.get_json()
    user_id = data.get("UserId")
    title = data.get("Title")
    message = data.get("Message")
    entity_id = data.get("EntityId", None)
    action_url = data.get("action_url", "")
    
    if not user_id or not title or not message:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    conn, cursor = get_common_db_connection()
    cursor.execute("""
        INSERT INTO Notifications (UserID, Title, Message, EntityId, ActionURL, CreatedAt, IsRead)
        VALUES (?, ?, ?, ?, ?, GETDATE(), 0)
    """, (user_id, title, message, entity_id, action_url))
    conn.commit()
    close_connection(conn, cursor)
    
    return jsonify({"success": True})