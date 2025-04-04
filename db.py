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
from playwright.sync_api import sync_playwright

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


def TechnofreshLogin():
    """Initializes the Selenium WebDriver and logs into the CRM using Technofresh credentials from ConnectedService."""
    logging.info("Trying to log in")

    # Check if a user is logged in
    if not current_user.is_authenticated:
        logging.warning("No user logged in.")
        return None

    # Ensure the user has the required attributes
    if not hasattr(current_user, 'id'):
        logging.error("Current user object is missing user ID.")
        return None

    # Fetch Technofresh credentials from the connected_service table
    service = ConnectedService.query.filter_by(user_id=current_user.id, service_type="Technofresh").first()
    if not service:
        logging.warning(f"No Technofresh credentials found for user '{current_user.username}' (ID: {current_user.id}).")
        return None

    try:
        technofresh_username = service.username
        technofresh_password = service.get_password()  # Use class method to decrypt password

        # Set up Selenium WebDriver options
        options = webdriver.ChromeOptions()
        # REMOVE HEADLESS MODE TO SEE THE BROWSER
        # options.add_argument("--headless")  # Keep commented out for now
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")

        # Initialize WebDriver
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://crm.technofresh.co.za/user/login")

        # Wait for login fields and enter credentials
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(technofresh_username)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(technofresh_password)
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "submit"))).click()

        # Wait for page to load after login
        time.sleep(3)  

        # CHECK IF LOGIN WAS SUCCESSFUL (URL SHOULD NOT CONTAIN 'login')
        if "login" in driver.current_url.lower():
            logging.error("Login failed: Still on login page.")
            driver.quit()
            return None

        logging.info(f"Successfully logged into CRM for user '{current_user.username}'.")
        return driver

    except Exception as e:
        logging.error(f"Error initializing WebDriver: {e}")
        return None
  

def download_freshlinq_report(username, password, report_date):
    """Downloads the FreshLinq report for the given date using Playwright."""
    
    formatted_date = report_date.strftime("%Y-%m-%d") if isinstance(report_date, datetime.date) else report_date
    report_url = f"https://trade.freshlinq.com/Report/Render/ProducerSalesSummaryAllLots/17578?Date={formatted_date}&Time=0000"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set to True for silent execution
        context = browser.new_context(accept_downloads=True)  # Enable download handling
        page = context.new_page()
        
        try:
            # Open FreshLinq login page
            page.goto("https://freshlinq.com/", timeout=60000)
            
            # Fill in login details
            page.fill("input#login-username", username)
            page.fill("input#Input_Password", password)
            page.click("button[name='selectedAction'][value='login']")
            
            # Wait for navigation after login
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)  # Small delay to ensure page stability
            
            # Check if login failed
            if "login" in page.url.lower():
                logger.error("Login failed: Still on login page.")
                return False
            
            # Navigate to reports page
            try:
                page.goto(report_url)
                page.wait_for_load_state("load")  # Ensure the page is fully loaded
                print(f"Navigated to {report_url}")
            except Exception as e:
                logger.error(f"Error navigating to report page: {e}")
                return False

            # Locate the error pane element
            error_pane = page.locator("div.trv-error-pane").first

            # Loop to check the text content every second until the condition is met
            start_time = time.time()
            timeout = 20  # Timeout after 20 seconds

            while time.time() - start_time < timeout:
                # Get the text content of the element
                text_content = error_pane.text_content().strip()

                # Print the current text content
                print(f"Current text content: {text_content}")

                # Check if 'done' is in the text content
                if 'done' in text_content.lower():
                    print("Found 'done' in the text content!")
                    break

                time.sleep(1)  # Wait for 1 second before checking again

            # If the loop ends and 'done' wasn't found, print a message
            if 'done' not in text_content.lower():
                print("Timeout: 'done' not found within the time frame.")
                return False
            
            # Enable the export button if it's disabled
            try:
                page.evaluate("""document.querySelector('#trv-main-menu-export-command').classList.remove('k-disabled');""")
            except Exception:
                pass  # Ignore errors in case the element isn't found

            page.locator('li#trv-main-menu-export-command').click()
            time.sleep(2)

            # Handle file download properly
            with page.expect_download() as download_info:
                page.locator('ul#trv-main-menu-export-format-list li:nth-child(3)').click()  # Click the correct download button
            
            download = download_info.value
            file_path = os.path.join("C:\\Users\\kapok\\Downloads", "report.xlsx")
            download.save_as(file_path)  # Save the file
            
            logger.info("Report downloaded successfully.")
            return file_path
        
        except Exception as e:
            logger.error(f"Error downloading report: {e}")
            return False
        
        finally:
            browser.close()
