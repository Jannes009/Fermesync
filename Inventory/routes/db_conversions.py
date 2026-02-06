def warehouse_code_to_link(whse_code, cursor):
    """Convert a warehouse code to its corresponding warehouse link."""
    cursor.execute("SELECT WhseLink FROM common.[_uvWarehouses] WHERE WhseCode = ?", (whse_code,))
    result = cursor.fetchone()
    return result[0] if result else None

def warehouse_link_to_code(whse_link, cursor):
    """Convert a warehouse link to its corresponding warehouse code."""
    cursor.execute("SELECT WhseCode FROM common.[_uvWarehouses] WHERE WhseLink = ?", (whse_link,))
    result = cursor.fetchone()
    return result[0] if result else None

def project_code_to_link(project_code, cursor):
    """Convert a project code to its corresponding project link."""
    cursor.execute("SELECT ProjectLink FROM common.[_uvProject] WHERE ProjectCode = ?", (project_code,))
    result = cursor.fetchone()
    return result[0] if result else None

def stock_link_to_code(stock_link, cursor):
    """Convert a stock link to its corresponding stock code."""
    cursor.execute("SELECT StockCode FROM common.[_uvStockItems] WHERE StockLink = ?", (stock_link,))
    result = cursor.fetchone()
    return result[0] if result else None

def supplier_link_to_code(supplier_link, cursor):
    """Convert a supplier link to its corresponding supplier code."""
    cursor.execute("SELECT Account FROM common.[_uvSuppliers] WHERE DCLink = ?", (supplier_link,))
    result = cursor.fetchone()
    return result[0] if result else None

def unit_link_to_code(unit_link, cursor):
    """Convert a unit link to its corresponding unit code."""
    cursor.execute("SELECT cUnitCode FROM common.[_uvUOM] WHERE idUnits = ?", (unit_link,))
    result = cursor.fetchone()
    return result[0] if result else None

def category_link_to_name(category_link, cursor):
    """Convert a category link to its corresponding category name."""
    cursor.execute("SELECT cCategoryName FROM common.[_uvCategories] WHERE idStockCategories = ?", (category_link,))
    result = cursor.fetchone()
    return result[0] if result else None