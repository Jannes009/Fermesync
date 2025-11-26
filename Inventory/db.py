import pyodbc as odbc
import logging
from auth import connect, close_connection  # central DB helpers
from key_manager import decrypt_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_db_connection(user=None, database_type="Inventory"):
    """
    Creates a database connection using:
    - current_user (interactive)
    - OR a supplied user snapshot dict (background thread)
    - Pulls DB credentials from UserDatabaseConfig table in the Common database.
    """

    # -------------------------
    # INTERACTIVE MODE (Flask user)
    # -------------------------
    if not user:
        from flask_login import current_user
        if not current_user.is_authenticated:
            logger.warning("No user is logged in.")
            return None

        # Connect to Common DB to fetch user's DB config
        conn, cursor = connect()
        try:
            cursor.execute("""
                SELECT ServerName, DatabaseName, SqlUsername, [EncryptedDbPassword]
                FROM UserDatabaseConfig
                WHERE UserId = ? AND DatabaseType = ?
            """, (current_user.id, database_type))
            row = cursor.fetchone()
        finally:
            close_connection(conn, cursor)

        if not row:
            logger.error(f"No DB config found for user {current_user.username} and type '{database_type}'")
            return None

        # Ensure it's bytes for Fernet
        encrypted_password = row[3]
        if isinstance(encrypted_password, memoryview):  # pypyodbc can return memoryview for VARBINARY
            encrypted_password = encrypted_password.tobytes()
        elif isinstance(encrypted_password, str):
            encrypted_password = encrypted_password.encode()  # convert str -> bytes

        db_password = decrypt_password(encrypted_password)

        username = current_user.username
        server_name = row[0]
        database_name = row[1]
        db_username = row[2]


    # -------------------------
    # BACKGROUND THREAD MODE (dict snapshot)
    # -------------------------
    else:
        # Required keys from snapshot
        required_keys = ["server_name", "database_name", "db_username", "db_password", "username"]

        for key in required_keys:
            if key not in user:
                logger.error(f"Missing field '{key}' in background user snapshot")
                return None

        server_name = user["server_name"]
        database_name = user["database_name"]
        db_username = user["db_username"]
        db_password = user["db_password"]
        username = user["username"]
        print(server_name, database_name, db_username, db_password, username)
    # -------------------------
    # Build connection string
    # -------------------------
    connection_string = f"""
        DRIVER={{SQL Server}};
        SERVER={server_name};
        DATABASE={database_name};
        Trust_Connection=no;
        UID={db_username};
        PWD={db_password};
    """

    try:
        connection = odbc.connect(connection_string)
        logger.info(f"Connected to DB '{database_name}' as user '{username}'")
        return connection

    except odbc.DatabaseError as db_err:
        logger.error(f"Database error: {db_err}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")

    return None


def close_db_connection(cursor, connection):
    """Closes the database connection."""
    try:
        cursor.close()
    except:
        pass

    try:
        connection.close()
    except:
        pass
