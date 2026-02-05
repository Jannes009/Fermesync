from flask import render_template, request, jsonify, Blueprint
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from db_manager import ( get_user_by_id, get_services_for_user, get_databases_for_user,)
from auth import connect, close_connection
from key_manager import encrypt_password, decrypt_password

account_bp = Blueprint('account', __name__, url_prefix='/account')


# -------------------------
# View account
# -------------------------
@account_bp.route('/')
@login_required
def view_account():
    user = get_user_by_id(current_user.id)
    services = get_services_for_user(current_user.id)
    databases = get_databases_for_user(current_user.id)

    return render_template(
        'account.html',
        user=user,
        connected_services=services,
        database_configs=databases
    )


# -------------------------
# Add a connected service
# -------------------------
@account_bp.route('/add_service', methods=['POST'])
@login_required
def add_service():
    data = request.json

    account_password = data.get('account_password')
    service_type = data.get('service_type')
    username = data.get('service_username')
    password = data.get('service_password')

    user = get_user_by_id(current_user.id)
    if not check_password_hash(user["password_hash"], account_password):
        return jsonify(success=False, message="Account password is incorrect"), 400

    if not all([service_type, password]):
        return jsonify(success=False, message="Missing required fields"), 400

    try:
        encrypted = encrypt_password(password)

        conn, cursor = connect()
        cursor.execute("""
            INSERT INTO ConnectedServices (UserId, ServiceType, Username, EncryptedPassword)
            VALUES (?, ?, ?, ?)
        """, (current_user.id, service_type, username, encrypted))
        conn.commit()
        return jsonify(success=True, message=f"{service_type} service added successfully")

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


# -------------------------
# Remove connected service
# -------------------------
@account_bp.route('/remove_service', methods=['POST'])
@login_required
def remove_service():
    data = request.json
    service_id = data.get('service_id')
    conn, cursor = connect()
    try:
        cursor.execute("""
            DELETE FROM ConnectedServices
            WHERE Id = ? AND UserId = ?
        """, (service_id, current_user.id))
        deleted = cursor.rowcount
        conn.commit()
        result = deleted > 0

        if result:
            return jsonify(success=True, message="Service removed successfully")
        return jsonify(success=False, message="Service not found"), 404

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


# -------------------------
# Add database config
# -------------------------
@account_bp.route('/add_database', methods=['POST'])
@login_required
def add_database():
    data = request.json
    conn, cursor = connect()
    try:
        cursor.execute("""
                INSERT INTO UserDatabaseConfig
                (UserId, DatabaseType, ServerName, DatabaseName, SqlUsername, [EncryptedDbPassword])
                VALUES (?, ?, ?, ?,?, ?)
            """, (current_user.id, data.get("db_type"), data.get("server_name"), data.get("db_name"), data.get("db_username"), encrypt_password(data.get("db_password"))))
        conn.commit()

        return jsonify(success=True, message="Database configuration added")

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        close_connection(conn, cursor)


# -------------------------
# Remove DB configuration
# -------------------------
@account_bp.route('/remove_database', methods=['POST'])
@login_required
def remove_database():
    data = request.json
    db_user_id = data.get("db_id")
    db_type = data.get("db_type")
    print(db_user_id, db_type)
    conn, cursor = connect()
    try:
        cursor.execute("""
            DELETE FROM UserDatabaseConfig
            WHERE DatabaseType = ? AND UserId = ?
        """, (db_type, db_user_id))
        deleted = cursor.rowcount
        conn.commit()
        result = deleted > 0

        if result:
            return jsonify(success=True, message="Database configuration removed")
        return jsonify(success=False, message="Database not found"), 404

    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
