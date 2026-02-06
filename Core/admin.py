from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from Core.auth import create_db_connection, close_db_connection

admin_bp = Blueprint('admin', __name__, template_folder='Inventory/templates', static_folder='Inventory/static')


# -----------------------------
# Load User Permissions (AJAX)
# -----------------------------
@admin_bp.route("/admin/get_user_settings/<int:user_id>")
@login_required
def get_user_settings(user_id):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        # Permissions
        cursor.execute(
            "SELECT PermissionId FROM users.UserPermissions WHERE UserId = ?",
            (user_id,)
        )
        perms = [row[0] for row in cursor.fetchall()]

        # Notification preferences
        cursor.execute(
            "SELECT NotificationTypeId FROM users.UserNotificationPreference WHERE UserId = ?",
            (user_id,)
        )
        not_prefs = [row[0] for row in cursor.fetchall()]

        # Warehouses
        cursor.execute(
            "SELECT WarehouseId FROM users.WarehouseToUserLink WHERE UserId = ?",
            (user_id,)
        )
        whs = [row[0] for row in cursor.fetchall()]

        # Project Groups (NEW)
        cursor.execute(
            "SELECT ProjectGroupId FROM users.UserProjectGroupLink WHERE UserId = ?",
            (user_id,)
        )
        proj_groups = [row[0] for row in cursor.fetchall()]

        return jsonify({
            "permissions": perms,
            "warehouses": whs,
            "not_prefs": not_prefs,
            "project_groups": proj_groups
        })

    finally:
        close_db_connection(conn, cursor)


# -----------------------------
# Users Permissions Page (GET + POST)
# -----------------------------
@admin_bp.route("/admin/users", methods=["GET", "POST"])
@login_required
def manage_users():
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        # Users
        cursor.execute("SELECT id, username FROM users.Users ORDER BY username")
        users = cursor.fetchall()

        # Permissions
        cursor.execute("SELECT PermissionId, PermissionCode FROM users.Permission ORDER BY PermissionCode")
        permissions = cursor.fetchall()

        # Warehouses
        cursor.execute("SELECT WhseLink, Name FROM common._uvWhseMst ORDER BY Name")
        warehouses = cursor.fetchall()

        # Notification Types
        cursor.execute("""
            SELECT NotificationTypeId, ModuleCode, Name
            FROM users.NotificationType
            WHERE IsActive = 1 AND IsSystem = 0
            ORDER BY ModuleCode, Name
        """)
        notification_types = cursor.fetchall()

        # Project Groups (NEW)
        cursor.execute("""
        Select DISTINCT MainProjectLink, MainProjectCode, MainProjectName 
        from common._uvProject 
        ORDER BY MainProjectCode
        """)
        project_groups = cursor.fetchall()

        if request.method == "POST":
            user_id = request.form.get("user_id")

            # -----------------
            # Permissions
            # -----------------
            cursor.execute("DELETE FROM users.UserPermissions WHERE UserId = ?", (user_id,))
            for perm_id in request.form.getlist("permissions"):
                cursor.execute(
                    "INSERT INTO users.UserPermissions (UserId, PermissionId) VALUES (?, ?)",
                    (user_id, perm_id)
                )

            # -----------------
            # Warehouses
            # -----------------
            cursor.execute("DELETE FROM users.WarehouseToUserLink WHERE UserId = ?", (user_id,))
            for wh_id in request.form.getlist("warehouses"):
                cursor.execute(
                    "INSERT INTO users.WarehouseToUserLink (UserId, WarehouseId) VALUES (?, ?)",
                    (user_id, wh_id)
                )

            # -----------------
            # Notification Preferences
            # -----------------
            cursor.execute(
                "DELETE FROM users.UserNotificationPreference WHERE UserId = ?",
                (user_id,)
            )
            for nt_id in request.form.getlist("not_prefs"):
                cursor.execute(
                    """
                    INSERT INTO users.UserNotificationPreference
                    (UserId, NotificationTypeId)
                    VALUES (?, ?)
                    """,
                    (user_id, nt_id)
                )

            # -----------------
            # Project Groups (NEW)
            # -----------------
            cursor.execute(
                "DELETE FROM users.UserProjectGroupLink WHERE UserId = ?",
                (user_id,)
            )
            for pg_id in request.form.getlist("project_groups"):
                cursor.execute(
                    """
                    INSERT INTO users.UserProjectGroupLink
                    (UserId, ProjectGroupId)
                    VALUES (?, ?)
                    """,
                    (user_id, pg_id)
                )

            conn.commit()
            return redirect(url_for("admin.manage_users"))

        return render_template(
            "permissions.html",
            users=users,
            permissions=permissions,
            warehouses=warehouses,
            notification_types=notification_types,
            project_groups=project_groups,
            user=current_user
        )

    finally:
        close_db_connection(conn, cursor)
