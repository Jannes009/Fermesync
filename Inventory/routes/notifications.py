
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
        WHERE UserId = ?
        ORDER BY CreatedAt DESC
    """, (current_user.id,))
    notifications = cursor.fetchall()

    cursor.execute("""
        UPDATE Notifications
        SET IsRead = 1
        WHERE UserId = ? AND IsRead = 0
    """, (current_user.id,))
    conn.commit()

    close_connection(conn, cursor)
    return render_template("notifications.html", notifications=notifications)


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
from jinja2 import Template

def send_notification(
    *,
    user_id: int,
    title: str,
    message: str,
    notification_type_id: int = None,
    entity_id: int = None,
    relative_url: str = None,
    push_mode: str = "none"  # none | immediate | batched
):
    conn, cursor = get_common_db_connection()
    print(user_id, title, message, notification_type_id, entity_id, relative_url, push_mode)
    # 1️⃣ Create in-app notification
    cursor.execute("""
        INSERT INTO Notifications
            (UserId, EntityType, Title, Message,
             EntityId, ActionURL, CreatedAt, IsRead)
        OUTPUT INSERTED.Id
        VALUES (?, ?, ?, ?, ?, ?, GETDATE(), 0)
    """, (
        user_id,
        notification_type_id,
        title,
        message,
        entity_id,
        relative_url
    ))

    notification_id = cursor.fetchone()[0]
    conn.commit()

    # 2️⃣ Push handling
    if push_mode == "immediate":
        send_immediate_push(user_id, title, message, relative_url)

    elif push_mode == "batched":
        send_batched_push(user_id)

    close_connection(conn, cursor)

    return notification_id

def send_immediate_push(user_id: int, title: str, message: str, relative_url: str = None):
    conn, cursor = get_common_db_connection()

    cursor.execute("""
        SELECT OnesignalId FROM PushSubscriptions
        WHERE UserId = ?
    """, (user_id,))
    subs = [r[0] for r in cursor.fetchall()]

    close_connection(conn, cursor)

    if not subs:
        return

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_subscription_ids": subs,
        "headings": {"en": title},
        "contents": {"en": message},
        "url": f"{BASE_URL}{relative_url}" if relative_url else None,
        "priority": 10,
        "ios_priority": 10
    }

    requests.post(
        "https://onesignal.com/api/v1/notifications",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {ONESIGNAL_REST_API_KEY}"
        },
        timeout=5
    )

def send_batched_push(user_id: int):
    conn, cursor = get_common_db_connection()

    cursor.execute("""
        SELECT COUNT(*) FROM Notifications
        WHERE UserId = ? AND IsRead = 0
    """, (user_id,))
    unread_count = cursor.fetchone()[0]

    if unread_count == 0:
        close_connection(conn, cursor)
        return

    cursor.execute("""
        SELECT TOP 3 Title
        FROM Notifications
        WHERE UserId = ? AND IsRead = 0
        ORDER BY CreatedAt DESC
    """, (user_id,))
    titles = [r[0] for r in cursor.fetchall()]

    cursor.execute("""
        SELECT OnesignalId FROM PushSubscriptions
        WHERE UserId = ?
    """, (user_id,))
    subs = [r[0] for r in cursor.fetchall()]

    close_connection(conn, cursor)

    if not subs:
        return

    summary = ", ".join(titles)
    if unread_count > len(titles):
        summary += f" and {unread_count - len(titles)} more"

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_subscription_ids": subs,
        "headings": {"en": f"{unread_count} new notifications"},
        "contents": {"en": summary},
        "url": f"{BASE_URL}/inventory/notifications",
        "priority": 10,
        "ios_priority": 10
    }

    requests.post(
        "https://onesignal.com/api/v1/notifications",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {ONESIGNAL_REST_API_KEY}"
        },
        timeout=5
    )

def emit_event(
    *,
    event_code: str,
    entity_id: int,
    entity_desc: str = ""
):
    print("Emitting event:", event_code, entity_id, entity_desc)

    conn, cursor = get_common_db_connection()
    actor_user_id = current_user.id

    # 1️⃣ Load notification type
    cursor.execute("""
        SELECT
            NotificationTypeId,
            DefaultTitle,
            DefaultTemplate,
            RedirectUrl,
            PushEnabled
        FROM NotificationType
        WHERE EventCode = ? AND IsActive = 1
    """, (event_code,))
    nt = cursor.fetchone()

    if not nt:
        close_connection(conn, cursor)
        return

    nt_id = nt.NotificationTypeId
    default_title = nt.DefaultTitle
    default_template = nt.DefaultTemplate
    redirect_template = nt.RedirectUrl
    push_enabled = nt.PushEnabled

    # 2️⃣ Resolve recipients (opted-in users)
    cursor.execute("""
        SELECT DISTINCT U.Id
        FROM Users U
        JOIN UserNotificationPreference UNP
            ON UNP.UserId = U.Id
        WHERE UNP.NotificationTypeId = ?
    """, (nt_id,))
    recipients = [r[0] for r in cursor.fetchall()]

    close_connection(conn, cursor)

    # 3️⃣ Send notifications
    for user_id in recipients:
        if user_id == actor_user_id:
            continue

        message = Template(default_template).render(
            entity_id=entity_id,
            entity_desc=entity_desc
        )

        # 🔑 Render redirect URL ONLY if template exists
        relative_url = (
            Template(redirect_template).render(entity_id=entity_id)
            if redirect_template
            else None
        )

        send_notification(
            user_id=user_id,
            title=default_title,
            message=message,
            notification_type_id=nt_id,
            entity_id=entity_id,
            relative_url=relative_url,
            push_mode="batched" if push_enabled else "none"
        )
