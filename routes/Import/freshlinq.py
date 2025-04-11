import time
import datetime
import tempfile
import subprocess
import pandas as pd
from pandas.errors import OutOfBoundsDatetime
from db import create_db_connection

# ---------------------------
# Helper function for safe value extraction
# ---------------------------
def safe_value(value, default=""):
    """Return a valid value if it's not NaN; otherwise, return the default."""
    return default if pd.isna(value) else value

# ---------------------------
# Process Excel and yield status messages
# ---------------------------
def process_excel(file_path, output_file):
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
            sales_data, sales_messages = get_sales_info(df, idx + 11)
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
    yield from insert_into_database(combined_data)

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

def insert_into_database(data):
    conn = create_db_connection()
    cursor = conn.cursor()
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

    cursor.execute("EXEC SIGCopyImprtFreshlinqTrn")
    conn.commit()
    conn.close()
    yield f"data:   ↳ Finished inserting {len(data)} rows.\n\n"