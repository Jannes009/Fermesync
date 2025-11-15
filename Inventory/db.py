import pypyodbc as odbc
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_db_connection(user=None):
    """Creates a database connection using a user dict or current_user."""
    if not user:
        from flask_login import current_user
        user = current_user
        if not user.is_authenticated:
            logger.warning("No user is logged in.")
            return None
        get_pwd = user.get_db_password
    else:
        # We're in a background thread using a user snapshot (dict)
        class BackgroundUser:
            def __init__(self, data):
                self.username = data["username"]
                self.server_name = data["server_name"]
                self.database_name = data["database_name"]
                self.db_username = data["db_username"]
                self.db_password = data["db_password"]

            def get_db_password(self):
                return self.db_password

        user = BackgroundUser(user)
        get_pwd = user.get_db_password

    # Build connection string
    connection_string = f"""
        DRIVER={{SQL SERVER}};
        SERVER={user.server_name};
        DATABASE={user.database_name};
        Trust_Connection=no;
        UID={user.db_username};
        PWD={get_pwd()};
    """

    try:
        connection = odbc.connect(connection_string)
        logger.info(f"Connected to {user.database_name} on {user.server_name} as {user.username}")
        return connection
    except odbc.DatabaseError as db_err:
        logger.error(f"Database error: {db_err}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

    return None



def close_db_connection(cursor, connection):
    """Closes the database connection."""
    cursor.close()
    connection.close()

logging.basicConfig(level=logging.INFO)

# ---------------------------
# Download FreshLinq Report using Playwright with Yielding and Temporary File
# ---------------------------
