import pandas as pd
from pandas.errors import OutOfBoundsDatetime
from db import create_db_connection


def safe_value(value, default=""):
    """Return a valid value if it's not NaN; otherwise, return the default."""
    return default if pd.isna(value) else value


def process_excel(file_path, output_file):
    # Read the Excel file into a DataFrame
    xl = pd.ExcelFile(file_path)
    df = xl.parse(xl.sheet_names[0])

    # List to store combined data
    combined_data = []

    # Loop through the rows and extract parent + sales data
    for idx, row in df.iterrows():
        if row.values[0] == 'Lot No.:':
            lot_no = safe_value(row.iloc[1])  
            brand = safe_value(row.iloc[9])  
            commodity = safe_value(row.iloc[18])  

            # Extract Delivery Note No., Packaging, Variety, Created At from the next row
            delivery_note_no = packaging = variety = created_at = None
            if idx + 1 < len(df):
                next_row = df.iloc[idx + 1]
                delivery_note_no = safe_value(next_row.iloc[1])  
                packaging = safe_value(next_row.iloc[9])  
                variety = safe_value(next_row.iloc[18])  
                created_at = safe_value(next_row.iloc[25])  

            # Extract from the second-next row (idx + 2)
            delivery_date = weight = size = lot_status = None
            if idx + 2 < len(df):
                second_next_row = df.iloc[idx + 2]
                delivery_date = safe_value(second_next_row.iloc[1])
                weight = safe_value(second_next_row.iloc[9], default=0)  # Default weight to 0 if NaN
                size = safe_value(second_next_row.iloc[18], default=0)  # Default size to 0 if NaN
                lot_status = safe_value(second_next_row.iloc[25])

            # Extract from the third-next row (idx + 3)
            branch = lot_notes = quality = agent = None
            if idx + 3 < len(df):
                third_next_row = df.iloc[idx + 3]
                branch = safe_value(third_next_row.iloc[1])
                lot_notes = safe_value(third_next_row.iloc[9])
                quality = safe_value(third_next_row.iloc[18])
                agent = safe_value(third_next_row.iloc[25])

            # Extract from the sixth-next row (idx + 6)
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


            # Get sales data starting from idx + 11
            sales_data = get_sales_info(df, idx + 11)

            # Combine parent details with sales data
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

    # Insert extracted data into the database
    insert_into_database(combined_data)


def get_sales_info(df, start_line):
    sales_data = []

    # Loop through rows starting from the given line
    for idx, row in df.iterrows():
        if idx >= start_line:
            if not pd.isna(row.iloc[5]):  # Check if 'Date' is not NaN
                try:
                    date = pd.to_datetime(row.iloc[5], errors='raise').normalize()

                    # Extract other details
                    quantity = safe_value(row.iloc[11])
                    price = safe_value(row.iloc[17])
                    value = safe_value(row.iloc[22])

                    sales_data.append({
                        "Date": date.strftime('%Y-%m-%d'),  
                        "Quantity": quantity,
                        "Price": price,
                        "Value": value
                    })
                except (ValueError, TypeError, OutOfBoundsDatetime):
                    break  # Stop processing sales data if an error occurs
            else:
                break  # Stop if the first NaN is found

    return sales_data


# Function to insert data into the SQL Server table
def insert_into_database(data):
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("Truncate table ZZFreshLinqImport")

 # SQL INSERT statement
    sql = """
    INSERT INTO ZZFreshLinqImport (
        lot_no, brand, commodity, delivery_note_no, packaging, variety, created_at,
        delivery_date, weight, size, lot_status, branch, lot_notes, quality, agent,
        movement, weighted_average, qty_delivered, qty_sold, remaining, lot_depletions,
        reclassifications, sale_date, quantity, price, value
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for row in data:
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
        conn.commit()

    conn.commit()
    conn.close()
    print("Data successfully inserted into the database.")
