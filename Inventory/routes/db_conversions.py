def warehouse_code_to_link(whse_code, cursor):
    """Convert a warehouse code to its corresponding warehouse link."""
    cursor.execute("SELECT WhseLink FROM [_uvWarehouses] WHERE WhseCode = ?", (whse_code,))
    result = cursor.fetchone()
    return result[0] if result else None

def project_code_to_link(project_code, cursor):
    """Convert a project code to its corresponding project link."""
    cursor.execute("SELECT ProjectLink FROM [_uvProject] WHERE ProjectCode = ?", (project_code,))
    result = cursor.fetchone()
    return result[0] if result else None

def stock_link_to_code(stock_link, cursor):
    """Convert a stock link to its corresponding stock code."""
    cursor.execute("SELECT StockCode FROM [_uvStockItems] WHERE StockLink = ?", (stock_link,))
    result = cursor.fetchone()
    return result[0] if result else None