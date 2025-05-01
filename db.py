import pypyodbc as odbc
from flask import session
from flask_login import current_user
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from models import db, User, ConnectedService
import logging
import time, datetime, os

import tempfile, subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_db_connection(user=None):
    """Creates a database connection using the logged-in user's credentials or an explicitly provided user."""
    
    user = user or current_user

    if not user.is_authenticated:
        logger.warning("No user is logged in.")
        return None

    print(user)
    # Ensure the user has the required attributes
    if not hasattr(user, 'server_name') or not hasattr(user, 'database_name'):
        logger.error("User object is missing database credentials.")
        return None

    DRIVER_NAME = 'SQL SERVER'
    SERVER_NAME = user.server_name
    DATABASE_NAME = user.database_name
    UID = user.db_username
    PWD = user.get_db_password()  # Ensure `get_db_password` is implemented correctly

    if not PWD:
        logger.error("Database password is missing or could not be retrieved.")
        return None

    connection_string = f"""
        DRIVER={{{DRIVER_NAME}}};
        SERVER={SERVER_NAME};
        DATABASE={DATABASE_NAME};
        Trust_Connection=no;
        UID={UID};
        PWD={PWD};
    """

    try:
        connection = odbc.connect(connection_string)
        logger.info(f"Connected to {DATABASE_NAME} on {SERVER_NAME} as {user.username}")
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
