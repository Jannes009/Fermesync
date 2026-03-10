import pandas as pd
import pyodbc

# Load CSV
df = pd.read_csv("chem_import.csv")

# Connect to SQL Server
conn = pyodbc.connect(
    "DRIVER={SQL Server};"
    r"SERVER=SIGMAFIN-RDS\EVOLUTION;"
    "DATABASE=FERMESYNC;"
    "UID=sa;"
    "PWD=@Evolution;"
)
cursor = conn.cursor()
print(conn.getinfo(pyodbc.SQL_DRIVER_NAME))

def clean_str(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    return s

def clean_number(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = s.replace(",", ".")
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        return None

# -------------------------
# New: determine column max lengths and truncate long strings to avoid truncation errors
# -------------------------
def get_column_maxlen(cursor, schema, table, column):
    cursor.execute("""
        SELECT CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = ?
    """, (schema, table, column))
    row = cursor.fetchone()
    if not row:
        return None
    m = row[0]
    # SQL Server uses -1 for max (nvarchar(max)) -> treat as unlimited
    return None if m is None or m == -1 else int(m)

def truncate_str(val, maxlen):
    if val is None or maxlen is None:
        return val
    s = str(val)
    return s if len(s) <= maxlen else s[:maxlen]

# get lengths for the columns we insert into (schema 'agr', table 'ChemStock')
chem_active_len = get_column_maxlen(cursor, "agr", "ChemStock", "ChemActiveIngr")
chem_reg_len = get_column_maxlen(cursor, "agr", "ChemStock", "ChemRegNumber")
chem_reason_len = get_column_maxlen(cursor, "agr", "ChemStock", "ChemReason")

for _, row in df.iterrows():
    nr_disp = clean_str(row.get("NR")) or "None"
    print(f"Processing: {nr_disp} - {clean_str(row.get('KATEGORIE'))} - {clean_str(row.get('LABEL'))}")

    # Get ChemTypeId
    kateg = clean_str(row.get("KATEGORIE"))
    cursor.execute("""
        SELECT IdChemType 
        FROM agr.ChemType 
        WHERE ChemTypeName = ?
    """, (kateg,))
    type_result = cursor.fetchone()
    if not type_result:
        cursor.execute("""
            INSERT INTO agr.ChemType (ChemTypeName)
            OUTPUT inserted.IdChemType
            VALUES (?)
        """, (kateg,))
        type_result = cursor.fetchone()

    chem_type_id = type_result[0] if type_result else None

    # Get ChemColourCodeId
    label = clean_str(row.get("LABEL"))

    if label is None:
        colour_id = None
    else:
        cursor.execute("""
            SELECT IdChemCol
            FROM agr.ChemColour
            WHERE ChemColCode = ?
        """, (label,))
        colour_result = cursor.fetchone()
        if not colour_result:
            cursor.execute("""
                INSERT INTO agr.ChemColour (ChemColCode)
                OUTPUT inserted.IdChemCol
                VALUES (?)
            """, (label,))
            colour_result = cursor.fetchone()

        colour_id = colour_result[0] if colour_result else None

    # Clean fields
    aktief = clean_str(row.get("AKTIEF"))
    nr = clean_str(row.get("NR"))
    rede = clean_str(row.get("REDE"))
    withholding = clean_number(row.get("ONTHOUDING"))

    # Truncate long strings to column max lengths to avoid SQL error
    aktief = truncate_str(aktief, chem_active_len)
    nr = truncate_str(nr, chem_reg_len)
    rede = truncate_str(rede, chem_reason_len)

    cursor.execute("""
        INSERT INTO agr.ChemStock
        (ChemStockActiveIngr, ChemStockRegNumber, ChemStockColourCodeId,
        ChemStockTypeId, ChemStockReason, ChemStockWitholdingPeriod)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (aktief, nr, colour_id, chem_type_id, rede, withholding))

conn.commit()
cursor.close()
conn.close()

print("Import completed.")
