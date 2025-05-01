from models import ConnectedService
from setup import download_folder
from db import create_db_connection
import pandas as pd
import os
import time
import asyncio
from playwright.sync_api import sync_playwright
from datetime import datetime
import tempfile

def Technofresh(current_user, start_date, end_date):
    def status(message):
        yield f"data: {message}\n\n"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        if not hasattr(current_user, 'id'):
            yield from status("ERROR: Current user object is missing user ID.")
            return

        service = ConnectedService.query.filter_by(user_id=current_user.id, service_type="Technofresh").first()
        if not service:
            yield from status(f"ERROR: No Technofresh credentials found for user '{current_user.username}' (ID: {current_user.id}).")
            return

        technofresh_username = service.username
        technofresh_password = service.get_password()

        yield from status("Logging into Technofresh CRM...")
        try:
            page.goto("https://crm.technofresh.co.za/user/login", timeout=20000)
            page.fill('input[name="username"]', technofresh_username)
            page.fill('input[name="password"]', technofresh_password)
            page.click('input[name="submit"]')

            page.wait_for_timeout(3000)
            if "login" in page.url:
                yield from status("ERROR: Login failed.")
                return

            yield from status("Login successful. Navigating to reports...")
            existing_files = set(os.listdir(download_folder))

            page.goto("https://crm.technofresh.co.za/reports/view/8/xls")

            page.evaluate("""(fromDate) => {
                document.getElementsByName('from_date')[0].value = fromDate;
            }""", start_date)

            page.evaluate("""(toDate) => {
                document.getElementsByName('to_date')[0].value = toDate;
            }""", end_date)

            with page.expect_download() as download_info:
                page.click('input[name="submit"]')
            download = download_info.value

            # Create a NamedTemporaryFile so pandas can still read from a path
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                download.save_as(tmp_file.name)
                tmp_file_path = tmp_file.name

            yield from status("File downloaded to temporary file.")

        except Exception as e:
            yield from status(f"ERROR: {str(e)}")
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

    conn = create_db_connection(current_user)
    cursor = conn.cursor()

    df['DocketNumber'] = df['DocketNumber'].astype(str).str.replace('*', '-', regex=False)
    df['SupplierRef'] = df['SupplierRef'].astype(str).str.replace('*', '-', regex=False)
    df['PaymentReference'] = df['PaymentReference'].astype(str).str.replace('*', '-', regex=False)

    cursor.execute("TRUNCATE TABLE MarketData")

    count = 0
    for _, row in df.iterrows():
        count += 1
        row_data = {col: (None if pd.isna(val) else val) for col, val in row.items()}
        cursor.execute("""
            INSERT INTO MarketData (
                Market, Agent, Product, Variety, Size, Class, Container, Mass_kg, Count,
                DeliveryID, ConsignmentID, SupplierRef, QtySent, QtyAmendedTo, QtySold,
                DeliveryDate, DateSold, DatePaid, DocketNumber, PaymentReference,
                MarketAvg, Price, SalesValue
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(row_data.values()))

    cursor.execute("Exec [dbo].[SIGCopyImprtTrn]")
    cursor.execute("EXEC SIGCreateSalesFromTrn")

    conn.commit()
    cursor.close()
    conn.close()

    return count
