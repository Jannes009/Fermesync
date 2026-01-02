
from flask_login import login_required, current_user
from flask import jsonify, request, render_template, abort
from auth import get_common_db_connection, close_connection
from Inventory.routes import inventory_bp
from auth import get_common_db_connection
import os, requests


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


@inventory_bp.route("/link_user_and_subscription", methods=["POST"])
def link_user_and_subscription():
    data = request.get_json()
    user_id = data.get("user_id")  # note: matches your JS key
    onesignal_id = data.get("subscription_id")

    if not user_id or not onesignal_id:
        return jsonify({"success": False, "error": "Missing user_id or onesignal_id"}), 400

    try:
        conn, cursor = get_common_db_connection()
       
        # Check if user already has a subscription
        cursor.execute("SELECT OnesignalId FROM PushSubscriptions WHERE OnesignalId = ? And UserId = ?", (onesignal_id, user_id))
        row = cursor.fetchone()

        if not row:
            # Insert new record
            cursor.execute(
                "INSERT INTO PushSubscriptions (UserId, OnesignalId) VALUES (?, ?)",
                user_id, onesignal_id
            )

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    except Exception as e:
        print("Error linking OneSignal ID:", e)
        return jsonify({"success": False, "error": str(e)}), 500


ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
ONESIGNAL_REST_API_KEY = os.getenv("REST_API_KEY")
BASE_URL = os.getenv("BASE_URL")
def notify_user(user_id, title, body, relative_url):
    if not user_id:
        return {"success": False, "error": "Missing user_id"}

    conn, cursor = get_common_db_connection()
    cursor.execute("SELECT OnesignalId FROM PushSubscriptions WHERE UserId = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"success": False, "error": "No subscriptions found for this user"}

    onesignal_ids = [row[0] for row in rows]

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_player_ids": onesignal_ids,          # ← FIXED: was include_subscription_ids

        "data": {"relative_url": relative_url},        # Good — helps Android background handling

        "headings": {"en": title},
        "contents": {"en": body},

        "url": f"{BASE_URL}{relative_url}",           # Click opens your site

        # Better Android reliability
        "visibility": 1,                              # ← FIXED: shows on lock screen (1 = public)
        "priority": 10,                             # Optional — remove if causing issues

        # apple configuration
        "ios_priority": 10,
        "apns_expiration": 86400

    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {ONESIGNAL_REST_API_KEY}"
    }

    try:
        response = requests.post(
            "https://onesignal.com/api/v1/notifications",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        print("Success:", response.json())
        # return {"success": True, "response": response.json()}
    except requests.exceptions.HTTPError as e:
        print("OneSignal error:", response.status_code, response.text)  # ← IMPORTANT: log this!
        # return {"success": False, "error": response.text}