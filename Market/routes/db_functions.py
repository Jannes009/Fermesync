def get_header_by_id(entry_id, cursor):
    # Fetch the entry data from the header table
    cursor.execute("SELECT * FROM [dbo].[ZZDeliveryNoteHeader] WHERE [DelIndex] = ?", (entry_id,))
    entry = cursor.fetchone()
    return entry

def del_note_number_to_del_id(header_number, cursor):
    # Fetch the entry data from the header table
    cursor.execute("SELECT DelIndex FROM [dbo].[ZZDeliveryNoteHeader] WHERE [DelNoteNo] = ?", (header_number,))
    entry = cursor.fetchone()
    return entry

def get_lines_by_foreign_key(foreign_key, cursor):
    cursor.execute("SELECT * FROM [dbo].[ZZDeliveryNoteLines] WHERE [ZZIDelNoteId] = ?", (foreign_key,))
    products = cursor.fetchall()
    return products

def get_agent_codes(cursor):
    query = """
    SELECT DCLink, [Account] + '-' + [Name] AS display_name FROM [dbo].[_uvMarketAgent]
    ORDER BY display_name 
    """
    cursor.execute(query)
    agent_codes = cursor.fetchall()
    return agent_codes


def get_transporter_codes(cursor):
    query = """
    SELECT [TransporterAccount], [TransporterAccount] + '-' + [TransporterName] AS display_name FROM [_uvMarketTransporter]
    ORDER BY display_name 
    """
    cursor.execute(query)
    transporter_codes = cursor.fetchall()
    return transporter_codes

def get_market_codes(cursor):
    query = """
    SELECT WhseLink, [MarketCode] + '-' + [MarketName] AS display_name FROM [dbo].[_uvMarkets]
    ORDER BY display_name 
    """
    cursor.execute(query)
    market_codes = cursor.fetchall()
    return market_codes


def get_destinations(cursor):
    query = """
    SELECT idDestination, DestinationCode FROM _uvDestination
    ORDER BY DestinationCode
    """
    cursor.execute(query)
    destinations = cursor.fetchall()
    return destinations

def get_production_unit_codes(cursor):
    query = """
    SELECT ProjectLink, [ProdUnitCode] + '-' + [ProdUnitName] AS display_name FROM [dbo].[_uvMarketProdUnit]
    ORDER BY display_name 
    """
    cursor.execute(query)
    production_unit_codes = cursor.fetchall()
    return production_unit_codes


def get_products(cursor):
    query = """
    SELECT StockLink, [ProductCode] + '-' + [ProductDescription] AS display_name FROM [dbo].[_uvMarketProduct]
    ORDER BY display_name
    """
    cursor.execute(query)
    products = cursor.fetchall()
    return products

def agent_code_to_agent_name(agent_code,cursor):
    query = "SELECT DCLink, [Account] + '-' + [Name] AS display_name, [Name] FROM [dbo].[_uvMarketAgent] WHERE [DCLink] = ?"
    cursor.execute(query,(agent_code,))
    agent_name = cursor.fetchone()
    return agent_name

def market_Id_to_market_name(marketId,cursor):
    query = "SELECT WhseLink, [MarketCode] + '-' + [MarketName] AS display_name FROM [dbo].[_uvMarkets] WHERE [WhseLink] = ?"
    cursor.execute(query,(marketId,))
    market_name = cursor.fetchone()
    return market_name

def transporter_account_to_transporter_name(transporterAccount,cursor):
    query = "SELECT [TransporterAccount], [TransporterAccount] + '-' + [TransporterName] AS display_name FROM [_uvMarketTransporter] WHERE [TransporterAccount] = ?"
    cursor.execute(query,(transporterAccount,))
    transporter_name = cursor.fetchone()
    return transporter_name

def project_link_to_production_unit_name(projectLink,cursor):
    query = "SELECT ProjectLink, [ProdUnitCode] + '-' + [ProdUnitName] AS display_name FROM [dbo].[_uvMarketProdUnit] WHERE [ProjectLink] = ?"
    cursor.execute(query,(projectLink,))
    production_unit_name = cursor.fetchone()
    return production_unit_name

def get_stock_id(lineId, cursor):
    query = "SELECT [DelLineStockId] FROM [dbo].[ZZDeliveryNoteLines] WHERE [DelLineIndex] = ?"
    cursor.execute(query, (lineId,))
    row = cursor.fetchone()
    
    if row:
        return row[0]  # Extract the first column value (DelLineStockId)
    return None  # Return None if no matching row is found

def get_stock_name(stockId, cursor):
    query = "Select ProductDescription from [dbo].[_uvMarketProduct] Where StockLink = ?"
    cursor.execute(query,(stockId,))
    name = cursor.fetchone()
    return name

def get_invoice_id(invoiceNumber, cursor):
    query = "Select InvoiceIndex from [dbo].[ZZInvoiceHeader] Where InvoiceNo = ?"
    cursor.execute(query,(invoiceNumber,))
    invoice_id = cursor.fetchone()
    return int(invoice_id[0])

def production_unit_name_to_production_unit_id(productionUnitName, cursor):
    query = "Select ProjectLink from [dbo].[_uvMarketProdUnit] Where ProdUnitName = ?"
    cursor.execute(query,(productionUnitName,))
    production_unit_id = cursor.fetchone()
    return int(production_unit_id[0])