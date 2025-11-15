import pypyodbc as odbc
import logging
from models import UserDatabaseConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_db_connection(user=None, database_type="Inventory"):
    """
    Creates a database connection using:
    - current_user (interactive)
    - OR a supplied user snapshot dict (background thread)
    - Pulls DB credentials from UserDatabaseConfig table.
    """

    # -------------------------
    # INTERACTIVE MODE (Flask user)
    # -------------------------
    if not user:
        from flask_login import current_user
        if not current_user.is_authenticated:
            logger.warning("No user is logged in.")
            return None

        # Fetch DB config from DB
        config = UserDatabaseConfig.query.filter_by(
            user_id=current_user.id,
            database_type=database_type
        ).first()

        if not config:
            logger.error(f"No DB config found for user {current_user.username} and type '{database_type}'")
            return None

        server_name = config.server_name
        database_name = config.database_name
        db_username = config.db_username
        db_password = config.get_db_password()
        username = current_user.username

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

    # -------------------------
    # Build connection string
    # -------------------------
    connection_string = f"""
        DRIVER={{SQL SERVER}};
        SERVER={server_name};
        DATABASE={database_name};
        Trust_Connection=no;
        UID={db_username};
        PWD={db_password};
    """

    try:
        connection = odbc.connect(connection_string)
        logger.info(f"Connected to {database_name} on {server_name} as {username}")
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
