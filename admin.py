from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from auth import get_common_db_connection, close_connection

admin_bp = Blueprint('admin', __name__, template_folder='Inventory/templates', static_folder='Inventory/static')


# -----------------------------
# Load User Permissions (AJAX)
# -----------------------------
@admin_bp.route("/admin/get_user_settings/<int:user_id>")
@login_required
def get_user_settings(user_id):
    conn, cursor = get_common_db_connection()
    try:
        # Permissions
        cursor.execute(
            "SELECT PermissionId FROM UserPermissions WHERE UserId = ?",
            (user_id,)
        )
        perms = [row[0] for row in cursor.fetchall()]

        # Notification preferences (NEW)
        cursor.execute(
            "SELECT NotificationTypeId FROM UserNotificationPreference WHERE UserId = ?",
            (user_id,)
        )
        not_prefs = [row[0] for row in cursor.fetchall()]

        # Warehouses
        cursor.execute(
            "SELECT WarehouseId FROM WarehouseToUserLink WHERE UserId = ?",
            (user_id,)
        )
        whs = [row[0] for row in cursor.fetchall()]

        return jsonify({
            "permissions": perms,
            "warehouses": whs,
            "not_prefs": not_prefs
        })

    finally:
        close_connection(conn, cursor)


# -----------------------------
# Users Permissions Page (GET + POST)
# -----------------------------
@admin_bp.route("/admin/users", methods=["GET", "POST"])
@login_required
def manage_users():
    conn, cursor = get_common_db_connection()
    try:
        # Users
        cursor.execute("SELECT id, username FROM Users")
        users = cursor.fetchall()

        # Permissions (unchanged)
        cursor.execute("SELECT PermissionId, PermissionCode FROM Permission ORDER BY PermissionCode")
        permissions = cursor.fetchall()

        # Warehouses
        cursor.execute("SELECT WhseLink, Name FROM _uvWhseMst ORDER BY Name")
        warehouses = cursor.fetchall()

        # Notification Types (NEW)
        cursor.execute("""
            SELECT NotificationTypeId, ModuleCode, Name
            FROM NotificationType
            WHERE IsActive = 1 AND IsSystem = 0
            ORDER BY ModuleCode, Name
        """)
        notification_types = cursor.fetchall()

        if request.method == "POST":
            user_id = request.form.get("user_id")

            # -----------------
            # Permissions
            # -----------------
            cursor.execute("DELETE FROM UserPermissions WHERE UserId = ?", (user_id,))
            for perm_id in request.form.getlist("permissions"):
                cursor.execute(
                    "INSERT INTO UserPermissions (UserId, PermissionId) VALUES (?, ?)",
                    (user_id, perm_id)
                )

            # -----------------
            # Warehouses
            # -----------------
            cursor.execute("DELETE FROM WarehouseToUserLink WHERE UserId = ?", (user_id,))
            for wh_id in request.form.getlist("warehouses"):
                cursor.execute(
                    "INSERT INTO WarehouseToUserLink (UserId, WarehouseId) VALUES (?, ?)",
                    (user_id, wh_id)
                )

            # -----------------
            # Notification Preferences (NEW)
            # -----------------
            cursor.execute(
                "DELETE FROM UserNotificationPreference WHERE UserId = ?",
                (user_id,)
            )
            for nt_id in request.form.getlist("not_prefs"):
                cursor.execute(
                    """
                    INSERT INTO UserNotificationPreference
                    (UserId, NotificationTypeId)
                    VALUES (?, ?)
                    """,
                    (user_id, nt_id)
                )

            conn.commit()
            return redirect(url_for("admin.manage_users"))

        return render_template(
            "permissions.html",
            users=users,
            permissions=permissions,
            warehouses=warehouses,
            notification_types=notification_types,
            user=current_user
        )

    finally:
        close_connection(conn, cursor)
