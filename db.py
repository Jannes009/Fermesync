import pypyodbc as odbc
from flask import session
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from models import User
import logging

import pypyodbc as odbc
from flask_login import current_user
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_db_connection():
    """Creates a database connection using the logged-in user's credentials."""
    
    if not current_user.is_authenticated:
        logger.warning("No user is logged in.")
        return None

    print(current_user)
    # Ensure the user has the required attributes
    if not hasattr(current_user, 'server_name') or not hasattr(current_user, 'database_name'):
        logger.error("Current user object is missing database credentials.")
        return None

    DRIVER_NAME = 'SQL SERVER'
    SERVER_NAME = current_user.server_name
    DATABASE_NAME = current_user.database_name
    PWD = current_user.get_db_password()  # Ensure `get_db_password` is implemented correctly

    if not PWD:
        logger.error("Database password is missing or could not be retrieved.")
        return None

    connection_string = f"""
        DRIVER={{{DRIVER_NAME}}};
        SERVER={SERVER_NAME};
        DATABASE={DATABASE_NAME};
        Trust_Connection=no;
        UID=sa;
        PWD={PWD};
    """

    try:
        connection = odbc.connect(connection_string)
        logger.info(f"Connected to {DATABASE_NAME} on {SERVER_NAME} as {current_user.username}")
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

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging
from flask import session
from models import db, User, ConnectedService  # Import models

def TechnofreshLogin():
    """Initializes the Selenium WebDriver and logs into the CRM using Technofresh credentials from ConnectedService."""

        # Check if a user is logged in
    if not current_user.is_authenticated:
        logging.warning("No user logged in.")
        return None

    # Ensure the user has the required attributes
    if not hasattr(current_user, 'id'):
        logging.error("Current user object is missing user ID.")
        return None

    # Fetch Technofresh credentials from the connected_service table using current_user's ID
    service = ConnectedService.query.filter_by(user_id=current_user.id, service_type="Technofresh").first()
    if not service:
        logging.warning(f"No Technofresh credentials found for user '{current_user.username}' (ID: {current_user.id}).")
        return None

    try:
        technofresh_username = service.username
        technofresh_password = service.get_password()  # Use class method to decrypt password

        # Set up Selenium WebDriver options
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://crm.technofresh.co.za/user/login")

        driver.find_element(By.NAME, "username").send_keys(technofresh_username)
        driver.find_element(By.NAME, "password").send_keys(technofresh_password)
        driver.find_element(By.NAME, "submit").click()

        time.sleep(3)  # Wait for login to complete

        logging.info(f"Successfully logged into CRM for user '{current_user.username}'.")
        return driver

    except Exception as e:
        logging.error(f"Error initializing WebDriver: {e}")
        return None