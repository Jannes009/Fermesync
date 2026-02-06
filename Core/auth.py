
import pyodbc as odbc
from werkzeug.security import check_password_hash
from flask_login import LoginManager, UserMixin
import os
from Core.key_manager import decrypt_password

login_manager = LoginManager()
login_manager.login_view = 'login'


# -------------------------
# User session class
# -------------------------
class UserLogin(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

    def has_feature(self, code):
        return code in (self.features or [])


def close_db_connection(conn=None, cursor=None):
    """Safely close cursor and connection."""
    try:
        if cursor:
            cursor.close()
    except:
        pass
    try:
        if conn:
            conn.close()
    except:
        pass


# -------------------------
# Common DB connection
# -------------------------
def create_db_connection():
    """
    Return a tuple (conn, cursor) for a given config.
    If db_config is None, defaults to common DB.
    """
    conn_str = (
        f"DRIVER={{{os.getenv('DB_DRIVER')}}};"
        f"SERVER={os.getenv('DB_SERVER')};"
        "DATABASE=FERMESYNC;"
        f"UID={os.getenv('DB_USERNAME')};"
        f"PWD={decrypt_password(os.getenv('DB_PASSWORD'))};"
        f"Trust_Connection=no;"
    )
    conn = odbc.connect(conn_str)
    return conn


# -------------------------
# Authenticate user
# -------------------------
def authenticate_user(username, password):
    """Validate username/password against common Users table."""
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, username, PasswordHash FROM users.Users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row and check_password_hash(row[2], password):
            user = UserLogin(id=row[0], username=row[1])
            user.warehouses = get_user_warehouses(user.id)
            user.projects = get_user_projects(user.id)
            user.permissions = get_user_permissions(user.id)
            user.features = get_user_features(user.id)
            return user
        return None
    finally:
        close_db_connection(conn, cursor)


# -------------------------
# Flask-Login loader
# -------------------------
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback to load a user by ID."""
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, username FROM users.Users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            user = UserLogin(id=row[0], username=row[1])
            user.warehouses = get_user_warehouses(user.id)
            user.projects = get_user_projects(user.id)
            user.permissions = get_user_permissions(user.id)
            user.features = get_user_features(user.id)
            return user
        return None
    finally:
        close_db_connection(conn, cursor)

def get_connected_services(user_id):
    """Fetch connected services for a user from the common database."""
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ServiceType
            FROM users.ConnectedService
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_db_connection(conn, cursor)

def get_user_warehouses(user_id):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT WarehouseId 
            FROM users.[WarehouseToUserLink]
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_db_connection(conn, cursor)

def get_user_projects(user_id):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ProjectGroupId 
            FROM users.[UserProjectGroupLink]
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_db_connection(conn, cursor)

def get_user_permissions(user_id):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        Select PermissionCode
        from [users].[UserPermissions] LINK
        JOIN [users].[Permission] PERM on PERM.PermissionId = LINK.PermissionId
        Where UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_db_connection(conn, cursor)

def get_user_features(user_id):
    conn = create_db_connection()  # common DB
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT FeatureCode
        FROM users.UserFeatures
            WHERE UserId = ? AND IsEnabled = 1
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_db_connection(conn, cursor)

   