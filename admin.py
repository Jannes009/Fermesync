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
        # Get permissions
        cursor.execute("SELECT EventId FROM UserPermissions WHERE UserId = ?", (user_id,))
        perms = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT EventId FROM [NotificationPreferences] WHERE UserId = ?", (user_id,))
        not_prefs = [row[0] for row in cursor.fetchall()]

        # Get warehouses
        cursor.execute("SELECT WarehouseId FROM WarehouseToUserLink WHERE UserId = ?", (user_id,))
        whs = [row[0] for row in cursor.fetchall()]

        return jsonify({"permissions": perms, "warehouses": whs, "not_prefs": not_prefs})

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
        # Fetch all users
        cursor.execute("SELECT id, username FROM Users")
        users = cursor.fetchall()

        # Fetch all events
        cursor.execute("SELECT Id, Code FROM Events ORDER BY Code")
        events = cursor.fetchall()

        # Fetch all warehouses
        cursor.execute("SELECT WhseLink, Name FROM _uvWhseMst Order BY Name")
        warehouses = cursor.fetchall()

        if request.method == "POST":
            user_id = request.form.get("user_id")

            # Update PERMISSIONS
            selected_permissions = request.form.getlist("permissions")
            cursor.execute("DELETE FROM UserPermissions WHERE UserId = ?", (user_id,))
            for perm_id in selected_permissions:
                cursor.execute(
                    "INSERT INTO UserPermissions (UserId, EventId) VALUES (?, ?)",
                    (user_id, perm_id)
                )

            # Update WAREHOUSES
            selected_warehouses = request.form.getlist("warehouses")
            cursor.execute("DELETE FROM WarehouseToUserLink WHERE UserId = ?", (user_id,))
            for wh_id in selected_warehouses:
                cursor.execute(
                    "INSERT INTO WarehouseToUserLink (UserId, WarehouseId) VALUES (?, ?)",
                    (user_id, wh_id)
                )

            # Update WAREHOUSES
            selected_not_prefs = request.form.getlist("not_prefs")
            cursor.execute("DELETE FROM [NotificationPreferences] WHERE UserId = ?", (user_id,))
            for event_id in selected_not_prefs:
                cursor.execute(
                    "INSERT INTO [NotificationPreferences] (UserId, EventId) VALUES (?, ?)",
                    (user_id, event_id)
                )


            conn.commit()
            print("User permissions and warehouses updated!")

            return redirect(url_for("admin.manage_users"))

        return render_template(
            "permissions.html",
            users=users,
            events=events,
            warehouses=warehouses,
            user=current_user
        )

    except Exception as e:
        print("Error:", str(e))
        return redirect(url_for("admin.manage_users"))

    finally:
        close_connection(conn, cursor)
