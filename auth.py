
import pyodbc as odbc
from werkzeug.security import check_password_hash
from flask_login import LoginManager, UserMixin
from config import build_connection_string  # function that builds a conn string from dict

login_manager = LoginManager()
login_manager.login_view = 'login'


# -------------------------
# User session class
# -------------------------
class UserLogin(UserMixin):
    def __init__(self, id, username, db_config=None):
        self.id = id
        self.username = username
        self.db_config = db_config  # per-user DB connection info

    def get_db_connection_string(self):
        """Return a connection string for this user (if db_config exists)."""
        if not self.db_config:
            return None
        return build_connection_string(self.db_config)


# -------------------------
# DB helper
# -------------------------
def connect(db_config=None):
    """
    Return a tuple (conn, cursor) for a given config.
    If db_config is None, defaults to common DB.
    """
    conn_str = build_connection_string(db_config)
    conn = odbc.connect(conn_str)
    cursor = conn.cursor()
    return conn, cursor


def close_connection(conn=None, cursor=None):
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
def get_common_db_connection():
    """Return (conn, cursor) for the common database."""
    return connect()  # defaults to config in config.py


# -------------------------
# Fetch per-user DB config
# -------------------------
def get_user_db_config(user_id):
    """Fetch database connection info from UserDatabaseConfig table."""
    conn, cursor = connect()
    try:
        cursor.execute("""
            SELECT ServerName, DatabaseName, SqlUsername, [EncryptedDbPassword]
            FROM UserDatabaseConfig
            WHERE UserId = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                "server": row[0],
                "database": row[1],
                "uid": row[2],
                "pwd": row[3],
                "driver": "SQL Server",
                "trust_connection": "no"
            }
        return None
    finally:
        close_connection(conn, cursor)


# -------------------------
# Authenticate user
# -------------------------
def authenticate_user(username, password):
    """Validate username/password against common Users table."""
    conn, cursor = connect()
    try:
        cursor.execute("SELECT id, username, PasswordHash FROM Users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row and check_password_hash(row[2], password):
            db_config = get_user_db_config(row[0])
            user = UserLogin(id=row[0], username=row[1], db_config=db_config)
            user.warehouses = get_user_warehouses(user.id)
            user.permissions = get_user_permissions(user.id)
            user.market_module = market_module(user.id)
            user.inventory_module = inventory_module(user.id)
            return user
        return None
    finally:
        close_connection(conn, cursor)


# -------------------------
# Flask-Login loader
# -------------------------
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login callback to load a user by ID."""
    conn, cursor = connect()
    try:
        cursor.execute("SELECT id, username FROM Users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            db_config = get_user_db_config(row[0])
            user = UserLogin(id=row[0], username=row[1], db_config=db_config)
            user.warehouses = get_user_warehouses(user.id)
            user.permissions = get_user_permissions(user.id)
            user.market_module = market_module(user.id)
            user.inventory_module = inventory_module(user.id)
            return user
        return None
    finally:
        close_connection(conn, cursor)

def get_connected_services(user_id):
    """Fetch connected services for a user from the common database."""
    conn, cursor = connect()  # common DB
    try:
        cursor.execute("""
            SELECT ServiceType
            FROM ConnectedService
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_connection(conn, cursor)

def get_user_warehouses(user_id):
    conn, cursor = connect()  # common DB
    try:
        cursor.execute("""
            SELECT WarehouseId 
            FROM [WarehouseToUserLink]
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_connection(conn, cursor)

def get_user_permissions(user_id):
    conn, cursor = connect()  # common DB
    try:
        cursor.execute("""
        Select Code
        from [dbo].[UserPermissions] LINK
        JOIN [dbo].[Permissions] PERM on PERM.Id = LINK.PermissionId
        Where UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else []
    finally:
        close_connection(conn, cursor)

def market_module(user_id):
    conn, cursor = connect()  # common DB
    try:
        cursor.execute("""
        Select Count(DatabaseName) from [dbo].[UserDatabaseConfig]
        Where UserId = ? and DatabaseType = 'Market'
        """, (user_id,))
        exists = cursor.fetchone()
        return exists[0] > 0
    finally:
        close_connection(conn, cursor)     

def inventory_module(user_id):
    conn, cursor = connect()  # common DB
    try:
        cursor.execute("""
        Select Count(DatabaseName) from [dbo].[UserDatabaseConfig]
        Where UserId = ? and DatabaseType = 'Inventory'
        """, (user_id,))
        exists = cursor.fetchone()
        return exists[0] > 0
    finally:
        close_connection(conn, cursor)     