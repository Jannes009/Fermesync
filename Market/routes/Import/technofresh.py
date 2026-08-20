
from Core.auth import create_db_connection
import pandas as pd
import os
from playwright.sync_api import sync_playwright
import tempfile
from Market.routes.Import.user_services import get_service_details

def Technofresh(current_user, start_date, end_date):
    def status(message):
        yield f"data: {message}\n\n"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        if not hasattr(current_user, 'id'):
            yield from status("ERROR: Current user object is missing user ID.")
            return

        service = get_service_details(current_user.id, "Technofresh")
        if not service:
            yield from status(f"ERROR: No FreshLinq credentials found for user '{current_user.username}'")
            return

        technofresh_username = service["username"]
        technofresh_password = service["password"]
        print(f"Technofresh credentials for user '{current_user.username}': {technofresh_username}, {technofresh_password}")

        yield from status("Logging into Technofresh CRM...")

        try:
            page.goto(
                "https://crm.technofresh.co.za/user/login",
                timeout=20000,
                wait_until="domcontentloaded"
            )

            page.locator('input[name="username"]').fill(technofresh_username)
            page.locator('input[name="password"]').fill(technofresh_password)

            login_button = page.locator('input[name="submit"]')
            login_button.wait_for(state="visible", timeout=10000)

            login_button.click(timeout=10000)

            # Wait for Technofresh to leave the login page
            page.wait_for_function(
                """() => window.location.pathname !== '/user/login'""",
                timeout=15000
            )

            yield from status("Login successful. Navigating to reports...")

            page.goto(
                "https://crm.technofresh.co.za/reports/view/8/xls",
                timeout=20000,
                wait_until="domcontentloaded"
            )

            # Make sure the report form exists
            from_date = page.locator('input[name="from_date"]')
            to_date = page.locator('input[name="to_date"]')

            from_date.wait_for(state="visible", timeout=10000)
            to_date.wait_for(state="visible", timeout=10000)

            from_date.fill(start_date)
            to_date.fill(end_date)

            yield from status("Generating report...")

            report_button = page.locator('input[name="submit"]')
            report_button.wait_for(state="visible", timeout=10000)
            yield from status("Waiting for report download...")

            with page.expect_download(timeout=30000) as download_info:
                report_button.click(timeout=1000000)

            download = download_info.value

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                download.save_as(tmp_file.name)
                tmp_file_path = tmp_file.name

            yield from status("File downloaded successfully.")

        except Exception as e:
            yield from status(f"ERROR: {type(e).__name__}: {e}")
            return
        try:
            yield from status("Inserting data into database...")
            docket_count = insert_data(tmp_file_path, current_user)
            print(docket_count)
            yield from status(f"SUCCESS: {docket_count} records added!")
        except Exception as e:
            yield from status(f"ERROR during insertion: {str(e)}")
        finally:
            context.close()
            browser.close()
            if 'tmp_file_path' in locals():
                os.remove(tmp_file_path)


def insert_data(file, current_user):
    df = pd.read_excel(file, skiprows=9)
    df.columns = [
        'Market', 'Agent', 'Product', 'Variety', 'Size', 'Class', 'Container',
        'Mass_kg', 'Count', 'DeliveryID', 'ConsignmentID', 'SupplierRef',
        'QtySent', 'QtyAmendedTo', 'QtySold', 'DeliveryDate', 'DateSold',
        'DatePaid', 'DocketNumber', 'PaymentReference', 'MarketAvg', 'Price', 'SalesValue'
    ]

    for col in ['DeliveryDate', 'DateSold', 'DatePaid']:
        df[col] = pd.to_datetime(df[col], format='%m-%d-%y', errors='coerce')

    conn = create_db_connection()
    cursor = conn.cursor()

    try:
        df['DocketNumber'] = df['DocketNumber'].astype(str).str.replace('*', '-', regex=False)
        df['SupplierRef'] = df['SupplierRef'].astype(str).str.replace('*', '-', regex=False)
        df['PaymentReference'] = df['PaymentReference'].astype(str).str.replace('*', '-', regex=False)

        cursor.execute("TRUNCATE TABLE [mkt].MarketData")

        count = 0
        for _, row in df.iterrows():
            count += 1
            row_data = {col: (None if pd.isna(val) else val) for col, val in row.items()}
            cursor.execute("""
                INSERT INTO [mkt].MarketData (
                    Market, Agent, Product, Variety, Size, Class, Container, Mass_kg, Count,
                    DeliveryID, ConsignmentID, SupplierRef, QtySent, QtyAmendedTo, QtySold,
                    DeliveryDate, DateSold, DatePaid, DocketNumber, PaymentReference,
                    MarketAvg, Price, SalesValue
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(row_data.values()))

        cursor.execute("Exec [mkt].[SIGCopyImprtTrn]")
        cursor.execute("EXEC mkt.SIGCreateSalesFromTrn")

        conn.commit()
        return count
    finally:
        cursor.close()
        conn.close()


