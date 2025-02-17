import pypyodbc as odbc
from flask import session
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from models import User
import logging

def create_db_connection():
    """Creates a database connection using the stored user credentials."""
    username = session.get('username')
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            DRIVER_NAME = 'SQL SERVER'
            SERVER_NAME = user.server_name
            DATABASE_NAME = user.database_name
            PWD = user.get_db_password()  # Decrypt stored DB password

            connection_string = f"""
                DRIVER={{{DRIVER_NAME}}};
                SERVER={SERVER_NAME};
                DATABASE={DATABASE_NAME};
                Trust_Connection=yes;
                uid=sa;
                pwd={PWD};
            """
            try:
                connection = odbc.connect(connection_string)
                return connection
            except Exception as e:
                print(f"Error connecting to database: {e}")
                return None
        else:
            print("User not found in database.")
            return None
    else:
        print("No user logged in.")
        return None


def close_db_connection(cursor, connection):
    """Closes the database connection."""
    cursor.close()
    connection.close()

logging.basicConfig(level=logging.INFO)

def initialize_driver():
    """Initializes the Selenium WebDriver and logs into the CRM using stored credentials."""
    
    # Check if a user is logged in
    username = session.get('username')
    if not username:
        logging.warning("No user logged in.")
        return None

    user = User.query.filter_by(username=username).first()
    if not user or not user.technofresh_username or not user.technofresh_password:
        logging.warning("Technofresh credentials not found.")
        return None

    technofresh_username = user.technofresh_username
    technofresh_password = user.get_technofresh_password()  # Decrypt stored password

    # Set up Selenium WebDriver options
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://crm.technofresh.co.za/user/login")

        driver.find_element(By.NAME, "username").send_keys(technofresh_username)
        driver.find_element(By.NAME, "password").send_keys(technofresh_password)
        driver.find_element(By.NAME, "submit").click()

        time.sleep(3)  # Wait for login to complete

        logging.info("Successfully logged into CRM.")
        return driver

    except Exception as e:
        logging.error(f"Error initializing WebDriver: {e}")
        return None