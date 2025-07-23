import time
import datetime
import tempfile
import subprocess
import pandas as pd
from db import create_db_connection
from playwright.sync_api import sync_playwright
from models import ConnectedService

def Freshlinq(current_user, start_date):
    def status(message):
        yield f"data: {message}\n\n"

    if not hasattr(current_user, 'id'):
        yield from status("ERROR: Current user object is missing user ID.")
        return

    service = ConnectedService.query.filter_by(user_id=current_user.id, service_type="FreshLinq").first()
    if not service:
        yield from status(f"ERROR: No Freshlinq credentials found for user '{current_user.username}' (ID: {current_user.id}).")
        return

    username = service.username
    password = service.get_password()

    yield from status("Attempting to connect to FreshLinq...")
    file_path = yield from download_freshlinq_report(username, password, start_date, status)
    if not file_path:
        yield from status("ERROR: Failed to download FreshLinq report.")
        return

    yield from process_excel(file_path, None)
    try:
        import os
        os.remove(file_path)
        yield from status("Temporary file removed.")
    except Exception as e:
        yield from status(f"WARNING: Could not remove temporary file - {str(e)}")

    yield from status("SUCCESS: Excel processing completed")

    yield "data: Attempting to connect to FreshLinq...\n\n"
    file_path = yield from download_freshlinq_report("uitdraai2@gmail.com", "Uitdraai123#", start_date, status)
    if not file_path:
        yield "data: ERROR: Failed to download FreshLinq report.\n\n"
        return
    yield from process_excel(file_path, current_user)
    # Remove the temporary file after processing
    try:
        import os
        os.remove(file_path)
        yield "data: Temporary file removed.\n\n"
    except Exception as e:
        yield f"data: WARNING: Could not remove temporary file - {str(e)}\n\n"
    yield "data: SUCCESS: Excel processing completed\n\n"

def download_freshlinq_report(username, password, report_date, status):
    ensure_playwright_browsers_installed()
    formatted_date = report_date.strftime("%Y-%m-%d") if isinstance(report_date, datetime.date) else report_date
    report_url = f"https://trade.freshlinq.com/Report/Render/ProducerSalesSummaryAllLots/17578?Date={formatted_date}&Time=0000"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            yield from status("Opening FreshLinq login page...")
            page.goto("https://freshlinq.com/", timeout=60000)
            page.fill("input#login-username", username)
            page.fill("input#Input_Password", password)
            page.click("button[name='selectedAction'][value='login']")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)

            if "login" in page.url.lower():
                yield from status("ERROR: Login failed. Still on login page.")
                return False

            yield from status("Login successful. Navigating to reports page...")
            page.goto(report_url)
            page.wait_for_load_state("load")
            yield from status("Report page loaded.")

            yield from status("Waiting for report processing to complete...")
            error_pane = page.locator("div.trv-error-pane").first
            start_time = time.time()
            timeout_seconds = 500

            while time.time() - start_time < timeout_seconds:
                text_content = error_pane.text_content()
                text = text_content.strip() if text_content else ""
                if 'done' in text.lower():
                    yield from status("File download in progress...")
                    break
                yield from status(f"Status: {text}")
                time.sleep(1)

            if 'done' not in text.lower():
                yield from status("ERROR: Timeout - report did not finish generating.")
                return False

            try:
                page.evaluate("document.querySelector('#trv-main-menu-export-command').classList.remove('k-disabled');")
            except Exception:
                pass

            page.locator('li#trv-main-menu-export-command').click()
            time.sleep(2)

            with page.expect_download(timeout=50000) as download_info:
                page.locator('ul#trv-main-menu-export-format-list li:nth-child(3)').click()
                download = download_info.value

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                download.save_as(tmp_file.name)
                yield from status("Download complete.")
                return tmp_file.name

        except Exception as e:
            yield from status(f"ERROR: Exception while downloading report - {str(e)}")
            return False

        finally:
            browser.close()


def ensure_playwright_browsers_installed():
    try:
        subprocess.run(["playwright", "install"], check=True)
    except Exception as e:
        print(f"Failed to install Playwright browsers: {e}")
# ---------------------------
# Helper function for safe value extraction
# ---------------------------
def safe_value(value, default=""):
    """Return a valid value if it's not NaN; otherwise, return the default."""
    return default if pd.isna(value) else value

# ---------------------------
# Process Excel and yield status messages
# ---------------------------
def process_excel(file_path, current_user):
    xl = pd.ExcelFile(file_path)
    df = xl.parse(xl.sheet_names[0])
    combined_data = []
    lot_count = 0

    # Loop through the rows to extract lot and sales information.
    for idx, row in df.iterrows():
        if row.values[0] == 'Lot No.:':
            lot_count += 1
            yield f"data: Processing row #{lot_count}...\n\n"

            # Extract parent lot data
            lot_no = safe_value(row.iloc[1])
            brand = safe_value(row.iloc[9])
            commodity = safe_value(row.iloc[18])

            delivery_note_no = packaging = variety = created_at = None
            if idx + 1 < len(df):
                next_row = df.iloc[idx + 1]
                if len(next_row) < 25:
                   return
                delivery_note_no = safe_value(next_row.iloc[1])
                packaging = safe_value(next_row.iloc[9])
                variety = safe_value(next_row.iloc[18])
                created_at = safe_value(next_row.iloc[25])

            delivery_date = weight = size = lot_status = None
            if idx + 2 < len(df):
                second_next_row = df.iloc[idx + 2]
                delivery_date = safe_value(second_next_row.iloc[1])
                weight = safe_value(second_next_row.iloc[9], default=0)
                size = safe_value(second_next_row.iloc[18], default=0)
                lot_status = safe_value(second_next_row.iloc[25])

            branch = lot_notes = quality = agent = None
            if idx + 3 < len(df):
                third_next_row = df.iloc[idx + 3]
                branch = safe_value(third_next_row.iloc[1])
                lot_notes = safe_value(third_next_row.iloc[9])
                quality = safe_value(third_next_row.iloc[18])
                agent = safe_value(third_next_row.iloc[25])

            movement = weighted_average = qty_delivered = qty_sold = remaining = lot_depletions = reclassifications = None
            if idx + 6 < len(df):
                sixth_next_row = df.iloc[idx + 6]
                movement = safe_value(sixth_next_row.iloc[1])
                weighted_average = safe_value(sixth_next_row.iloc[6], default=0)
                qty_delivered = safe_value(sixth_next_row.iloc[9], default=0)
                qty_sold = safe_value(sixth_next_row.iloc[14], default=0)
                remaining = safe_value(sixth_next_row.iloc[18], default=0)
                lot_depletions = safe_value(sixth_next_row.iloc[21], default=0)
                reclassifications = safe_value(sixth_next_row.iloc[25], default=0)

            # Extract sales data from rows starting at idx + 11
            sales_data, sales_messages = get_sales_info(df, idx + 10)
            for msg in sales_messages:
                yield f"data: {msg}\n\n"

            # Combine parent lot info with each sales record
            for sale in sales_data:
                combined_data.append({
                    "Lot No.": lot_no,
                    "Brand": brand,
                    "Commodity": commodity,
                    "Delivery Note No.": delivery_note_no,
                    "Packaging": packaging,
                    "Variety": variety,
                    "Created At": created_at,
                    "Delivery Date": delivery_date,
                    "Weight": weight,
                    "Size": size,
                    "Lot Status": lot_status,
                    "Branch": branch,
                    "Lot Notes": lot_notes,
                    "Quality": quality,
                    "Agent": agent,
                    "Movement": movement,
                    "Weighted Average": weighted_average,
                    "Qty Delivered": qty_delivered,
                    "Qty Sold": qty_sold,
                    "Remaining": remaining,
                    "Lot Depletions": lot_depletions,
                    "Reclassifications": reclassifications,
                    "Date": sale["Date"],
                    "Quantity": sale["Quantity"],
                    "Price": sale["Price"],
                    "Value": sale["Value"]
                })

            yield f"data:   ↳ Finished processing lot #{lot_count}.\n\n"

    yield "data: Inserting data into database...\n\n"
    yield from insert_into_database(combined_data, current_user)

def get_sales_info(df, start_line):
    sales_data = []
    messages = []
    for idx, row in df.iterrows():
        if idx >= start_line:
            if not pd.isna(row.iloc[5]):
                try:
                    date = pd.to_datetime(row.iloc[5], errors='raise').normalize()
                    quantity = safe_value(row.iloc[11])
                    price = safe_value(row.iloc[17])
                    value = safe_value(row.iloc[22])
                    sales_data.append({
                        "Date": date.strftime('%Y-%m-%d'),
                        "Quantity": quantity,
                        "Price": price,
                        "Value": value
                    })
                except Exception:
                    messages.append(f"Stopped reading sales at row {idx} due to invalid date.")
                    break
            else:
                break
    messages.append(f"  ↳ Found {len(sales_data)} sales records.")
    return sales_data, messages

def insert_into_database(data, current_user):
    conn = create_db_connection(current_user)
    cursor = conn.cursor()
    try:
        cursor.execute("TRUNCATE TABLE ZZFreshLinqImport")
        yield "data:  ↳ Table ZZFreshLinqImport truncated.\n\n"
        sql = """
        INSERT INTO ZZFreshLinqImport (
            lot_no, brand, commodity, delivery_note_no, packaging, variety, created_at,
            delivery_date, weight, size, lot_status, branch, lot_notes, quality, agent,
            movement, weighted_average, qty_delivered, qty_sold, remaining, lot_depletions,
            reclassifications, sale_date, quantity, price, value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for i, row in enumerate(data, 1):
            yield f"data: Inserting row {i}...\n\n"

            def parse_date(date_value):
                try:
                    return pd.to_datetime(date_value, errors='coerce').strftime('%Y-%m-%d') if pd.notna(date_value) else None
                except (ValueError, TypeError):
                    return None

            def parse_float(value):
                try:
                    return float(value) if pd.notna(value) else None
                except ValueError:
                    return None

            def parse_int(value):
                try:
                    return int(value) if pd.notna(value) else None
                except ValueError:
                    return None

            created_at = row["Created At"]
            delivery_date = parse_date(row["Delivery Date"])
            sale_date = parse_date(row["Date"])

            weight = row["Weight"]
            size = row["Size"]
            weighted_average = parse_float(row["Weighted Average"])
            qty_delivered = parse_int(row["Qty Delivered"])
            qty_sold = parse_int(row["Qty Sold"])
            remaining = parse_int(row["Remaining"])
            lot_depletions = parse_int(row["Lot Depletions"])
            reclassifications = parse_int(row["Reclassifications"])
            quantity = parse_int(row["Quantity"])
            price = parse_float(row["Price"])
            value = parse_float(row["Value"])

            cursor.execute(sql, (
                row["Lot No."], row["Brand"], row["Commodity"], row["Delivery Note No."],
                row["Packaging"], row["Variety"], created_at, delivery_date,
                weight, size, row["Lot Status"], row["Branch"], row["Lot Notes"],
                row["Quality"], row["Agent"], row["Movement"], weighted_average,
                qty_delivered, qty_sold, remaining, lot_depletions,
                reclassifications, sale_date, quantity, price, value
            ))

            if i % 50 == 0:
                yield f"data:   ↳ Inserted {i} rows...\n\n"
                conn.commit()
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    yield f"data:   ↳ Finished inserting {len(data)} rows.\n\n"