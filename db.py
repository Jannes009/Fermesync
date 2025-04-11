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
import tempfile, subprocess

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
def TechnofreshLogin(yield_status):
    """Initializes the Selenium WebDriver and logs into the CRM using Technofresh credentials from ConnectedService."""
    yield_status("Starting Technofresh login process...")

    if not current_user.is_authenticated:
        yield_status("ERROR: No user is logged in.")
        return None

    if not hasattr(current_user, 'id'):
        yield_status("ERROR: Current user object is missing user ID.")
        return None

    service = ConnectedService.query.filter_by(user_id=current_user.id, service_type="Technofresh").first()
    if not service:
        yield_status(f"ERROR: No Technofresh credentials found for user '{current_user.username}' (ID: {current_user.id}).")
        return None

    try:
        technofresh_username = service.username
        technofresh_password = service.get_password()
        yield_status("Credentials fetched. Setting up browser...")

        options = webdriver.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://crm.technofresh.co.za/user/login")
        yield_status("Navigated to login page.")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(technofresh_username)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(technofresh_password)
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "submit"))).click()
        yield_status("Submitted login form. Waiting for response...")

        time.sleep(3)

        if "login" in driver.current_url.lower():
            driver.quit()
            yield_status("ERROR: Login failed. Still on login page.")
            return None

        yield_status(f"Successfully logged into CRM as '{current_user.username}'.")
        return driver

    except Exception as e:
        yield_status(f"ERROR: Login exception - {str(e)}")
        return None

# ---------------------------
# Download FreshLinq Report using Playwright with Yielding and Temporary File
# ---------------------------

def download_freshlinq_report(username, password, report_date, yield_status):
    """Downloads the FreshLinq report for the given date using Playwright."""
    ensure_playwright_browsers_installed()
    formatted_date = report_date.strftime("%Y-%m-%d") if isinstance(report_date, datetime.date) else report_date
    report_url = f"https://trade.freshlinq.com/Report/Render/ProducerSalesSummaryAllLots/17578?Date={formatted_date}&Time=0000"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            yield "data: Opening FreshLinq login page...\n\n"
            page.goto("https://freshlinq.com/", timeout=60000)

            page.fill("input#login-username", username)
            page.fill("input#Input_Password", password)
            page.click("button[name='selectedAction'][value='login']")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)

            if "login" in page.url.lower():
                yield "data: ERROR: Login failed. Still on login page.\n\n"
                return False

            yield "data: Login successful. Navigating to reports page...\n\n"
            try:
                page.goto(report_url)
                page.wait_for_load_state("load")
                yield "data: Report page loaded.\n\n"
            except Exception as e:
                yield f"data: ERROR: Failed to navigate to report page - {str(e)}\n\n"
                return False

            yield "data: Waiting for report processing to complete...\n\n"
            error_pane = page.locator("div.trv-error-pane").first
            start_time = time.time()
            timeout_seconds = 1000

            while time.time() - start_time < timeout_seconds:
                text_content = error_pane.text_content().strip()
                yield f"data: Status: {text_content}\n\n"

                if 'done' in text_content.lower():
                    yield "data: File download in progress...\n\n"
                    break

                time.sleep(1)

            if 'done' not in text_content.lower():
                yield "data: ERROR: Timeout - report did not finish generating.\n\n"
                return False

            try:
                page.evaluate("document.querySelector('#trv-main-menu-export-command').classList.remove('k-disabled');")
            except Exception:
                pass

            page.locator('li#trv-main-menu-export-command').click()
            time.sleep(2)

            with page.expect_download(timeout=500000) as download_info:
                page.locator('ul#trv-main-menu-export-format-list li:nth-child(3)').click(timeout=500000)
                download = download_info.value

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                download.save_as(tmp_file.name)
                yield "data: Download complete.\n\n"
                return tmp_file.name

        except Exception as e:
            yield f"data: ERROR: Exception while downloading report - {str(e)}\n\n"
            return False

        finally:
            browser.close()

def ensure_playwright_browsers_installed():
    try:
        subprocess.run(["playwright", "install"], check=True)
    except Exception as e:
        print(f"Failed to install Playwright browsers: {e}")