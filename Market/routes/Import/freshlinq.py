import time
import datetime
import tempfile
import pandas as pd
from Core.auth import create_db_connection
from playwright.sync_api import sync_playwright
import re
from Core.db_manager import get_service_details
import threading

freshlinq_lock = threading.Lock()


# ============================================================
# MAIN ENTRY POINT (SSE STREAMING)
# ============================================================
def Freshlinq(current_user, start_date):

    def status(message):
        yield f"data: {message}\n\n"

    if not hasattr(current_user, 'id'):
        yield from status("ERROR: Current user object is missing user ID.")
        return

    service = get_service_details(current_user.id, "FreshLinq")
    if not service:
        yield from status(
            f"ERROR: No FreshLinq credentials found for user '{current_user.username}'"
        )
        return

    username = service["username"]
    password = service["password"]

    yield from status("Attempting to connect to FreshLinq...")

    with freshlinq_lock:
        file_path = yield from download_freshlinq_report(
            username, password, start_date, status
        )

    if not file_path:
        yield from status("ERROR: Failed to download FreshLinq report.")
        return

    yield from process_excel(file_path, None)

    # Cleanup temp file
    try:
        import os
        os.remove(file_path)
        yield "data: Temporary file removed.\n\n"
    except Exception as e:
        yield f"data: WARNING: Could not remove temporary file - {str(e)}\n\n"

    yield "data: SUCCESS: Excel processing completed\n\n"


# ============================================================
# DOWNLOAD REPORT (STREAMING)
# ============================================================
def download_freshlinq_report(username, password, report_date, status):

    # --- Normalize date ---
    if isinstance(report_date, str):
        try:
            report_date = datetime.datetime.strptime(report_date, "%Y-%m-%d")
        except ValueError:
            try:
                report_date = datetime.datetime.fromisoformat(report_date)
            except ValueError:
                yield from status(f"ERROR: Invalid date format: {report_date}")
                return False

    elif isinstance(report_date, datetime.date) and not isinstance(report_date, datetime.datetime):
        report_date = datetime.datetime.combine(report_date, datetime.time.min)

    elif not isinstance(report_date, datetime.datetime):
        yield from status(f"ERROR: Unsupported date type: {type(report_date)}")
        return False

    from_date = report_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_date = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    report_url = (
        "https://trade.freshlinq.com/Report/Render/"
        "ProducerSalesSummaryAllLots/17578"
        f"?FromDate={from_date}&ToDate={to_date}"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            # LOGIN
            yield from status("Opening FreshLinq login page...")
            page.goto("https://freshlinq.com/", timeout=60000)

            page.fill("#login-username", username)
            page.fill("#Input_Password", password)
            page.click("button[name='selectedAction'][value='login']")

            page.wait_for_load_state("networkidle")

            if "login" in page.url.lower():
                yield from status("ERROR: Login failed.")
                return False

            yield from status("Login successful.")

            # LOAD REPORT
            yield from status("Navigating to report...")
            page.goto(report_url)
            page.wait_for_load_state("networkidle")
            yield from status("Report page loaded.")

            # WAIT FOR REPORT TO FINISH
            yield from status("Waiting for report to finish generating...")

            page.wait_for_selector(
                "#export-dropdown:not(.k-disabled)",
                timeout=600000
            )

            yield from status("Report finished generating.")

            # EXPORT XLSX
            page.locator("#export-dropdown").click()
            page.wait_for_selector("li#XLSX", state="visible")

            with page.expect_download(timeout=60000) as download_info:
                page.locator("li#XLSX").click()

            download = download_info.value

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                download.save_as(tmp_file.name)

            yield from status("Download complete.")
            return tmp_file.name

        except Exception as e:
            yield from status(f"ERROR: {str(e)}")
            return False

        finally:
            browser.close()


# ============================================================
# SAFE VALUE HELPER (NORMAL FUNCTION)
# ============================================================
def safe_value(value, default="", clean_special_characters=False):

    if pd.isna(value):
        return default

    value_str = str(value).strip()

    if clean_special_characters:
        value_str = re.sub(r'[^A-Za-z0-9\-]', '', value_str)
        return value_str if value_str else default

    return value_str


# ============================================================
# PROCESS EXCEL (STREAMING)
# ============================================================
def process_excel(file_path, current_user):
    try:
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
                lot_no = safe_value(row.iloc[1], clean_special_characters=True)
                brand = safe_value(row.iloc[10])
                commodity = safe_value(row.iloc[19])

                delivery_note_no = packaging = variety = created_at = None
                if idx + 1 < len(df):
                    next_row = df.iloc[idx + 1]
                    for i in range(len(next_row)):
                        print(f"Row {idx + 1}, Column {i}: {next_row.iloc[i]}")
                    if len(next_row) < 25:
                        return
                    
                    delivery_note_no = safe_value(next_row.iloc[1])
                    packaging = safe_value(next_row.iloc[10])
                    variety = safe_value(next_row.iloc[19])
                    created_at = safe_value(next_row.iloc[26])
                    print(delivery_note_no, packaging, variety, created_at)

                delivery_date = weight = size = lot_status = None
                if idx + 2 < len(df):
                    second_next_row = df.iloc[idx + 2]
                    delivery_date = safe_value(second_next_row.iloc[1])
                    weight = safe_value(second_next_row.iloc[10], default=0)
                    size = safe_value(second_next_row.iloc[19], default=0)
                    lot_status = safe_value(second_next_row.iloc[26])

                branch = lot_notes = quality = agent = None
                if idx + 3 < len(df):
                    third_next_row = df.iloc[idx + 3]
                    branch = safe_value(third_next_row.iloc[1])
                    lot_notes = safe_value(third_next_row.iloc[10])
                    quality = safe_value(third_next_row.iloc[19])
                    agent = safe_value(third_next_row.iloc[26])

                movement = weighted_average = qty_delivered = qty_sold = remaining = lot_depletions = reclassifications = None
                if idx + 6 < len(df):
                    sixth_next_row = df.iloc[idx + 6]
                    movement = safe_value(sixth_next_row.iloc[1])
                    weighted_average = safe_value(sixth_next_row.iloc[5], default=0)
                    qty_delivered = safe_value(sixth_next_row.iloc[10], default=0)
                    qty_sold = safe_value(sixth_next_row.iloc[16], default=0)
                    remaining = safe_value(sixth_next_row.iloc[19], default=0)
                    lot_depletions = safe_value(sixth_next_row.iloc[22], default=0)
                    reclassifications = safe_value(sixth_next_row.iloc[26], default=0)

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
    except Exception as e:
        yield f"data: ERROR processing Excel file - {str(e)}\n\n"



# ============================================================
# GET SALES INFO (FIXED — NORMAL FUNCTION)
# ============================================================
def get_sales_info(df, start_line):

    sales_data = []
    messages = []

    try:
        for idx, row in df.iterrows():

            if idx >= start_line:

                if not pd.isna(row.iloc[5]):

                    try:
                        date = pd.to_datetime(row.iloc[5], errors='raise').normalize()
                        quantity = safe_value(row.iloc[12])
                        price = safe_value(row.iloc[18])
                        value = safe_value(row.iloc[23])

                        sales_data.append({
                            "Date": date.strftime('%Y-%m-%d'),
                            "Quantity": quantity,
                            "Price": price,
                            "Value": value
                        })

                    except Exception:
                        messages.append(
                            f"Stopped reading sales at row {idx} due to invalid date."
                        )
                        break
                else:
                    break

        messages.append(f"↳ Found {len(sales_data)} sales records.")

    except Exception as e:
        messages.append(f"ERROR extracting sales info - {str(e)}")

    return sales_data, messages


# ============================================================
# INSERT INTO DATABASE (STREAMING)
# ============================================================
def insert_into_database(data, current_user):

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("TRUNCATE TABLE [mkt].ZZFreshLinqImport")
        yield "data:  ↳ Table ZZFreshLinqImport truncated.\n\n"

        sql = """ 
        INSERT INTO [mkt].ZZFreshLinqImport ( 
        lot_no, brand, 
        commodity, 
        delivery_note_no, 
        packaging, 
        variety, 
        created_at, 
        delivery_date, 
        weight, size, 
        lot_status, 
        branch, 
        lot_notes, 
        quality, 
        agent, 
        movement, 
        weighted_average, 
        qty_delivered, qty_sold, remaining, 
        lot_depletions, reclassifications, 
        sale_date, quantity, price, value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        for i, row in enumerate(data, 1):

            yield f"data: Inserting row {i}...\n\n"

            def parse_date(date_value):
                try:
                    return pd.to_datetime(date_value).strftime('%Y-%m-%d')
                except:
                    return None

            def parse_float(value):
                try:
                    return float(value)
                except:
                    return None

            def parse_int(value):
                try:
                    return int(value)
                except:
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
                row["Lot No."], 
                row["Brand"], 
                row["Commodity"], 
                row["Delivery Note No."], 
                row["Packaging"], 
                row["Variety"], 
                created_at, 
                delivery_date, 
                weight, 
                size, 
                row["Lot Status"], 
                row["Branch"], 
                row["Lot Notes"], 
                row["Quality"], 
                row["Agent"], 
                row["Movement"], 
                weighted_average, 
                qty_delivered, 
                qty_sold, 
                remaining, 
                lot_depletions, 
                reclassifications, 
                sale_date, 
                quantity, 
                price, 
                value ))

        conn.commit()
        cursor.execute("EXEC [mkt].SIGCopyImprtFreshlinqTrn")
        conn.commit()

    finally:
        cursor.close()
        conn.close()

    yield f"data:   ↳ Finished inserting {len(data)} rows.\n\n"
