from datetime import datetime, timedelta
from Core.auth import create_db_connection, close_db_connection
from .qty import format_qty


def row_to_dict(cursor, row):
    if row is None:
        return None
    return {col[0]: getattr(row, col[0], None) for col in cursor.description}


class ProductService:
    def __init__(self, conn=None):
        self.conn = conn or create_db_connection()
        self.cursor = self.conn.cursor() if self.conn else None

    def close(self):
        if self.conn:
            close_db_connection(self.conn)
            self.conn = None
            self.cursor = None

    def load_product_base(self, stock_link):
        self.cursor.execute(
            """
            SELECT StockLink, StockCode, StockDescription, ReorderLevel, ReorderQty,
                   idStockCategories AS ItemCategoryID, cCategoryName
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
            """,
            (stock_link,),
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        return row_to_dict(self.cursor, row)

    def load_inventory_rows(self, stock_link):
        self.cursor.execute(
            """
            SELECT
                WhseLink,
                WhseCode,
                WhseName,
                COALESCE(QtyOnHand, 0) AS QtyOnHand,
                COALESCE(IncompleteIssuesQty, 0) AS QtyAllocated,
                COALESCE(QtyOnPo, 0) AS QtyOnPO,
                COALESCE(ReorderLevel, 0) AS ReorderLevel,
                COALESCE(ReorderQty, 0) AS ReorderQty,
                COALESCE(QtyOnIBT, 0) AS QtyOnIBT
            FROM stk._uvInventoryQty
            WHERE StockLink = ?
            ORDER BY WhseCode
            """,
            (stock_link,),
        )
        rows = [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]
        for row in rows:
            row['Available'] = max(float(row.get('QtyOnHand', 0) or 0) - float(row.get('QtyAllocated', 0) or 0), 0)
        return rows

    def load_selected_inventory(self, inventory_rows, warehouse_id):
        chosen = None
        for row in inventory_rows:
            if row.get('WhseLink') == warehouse_id:
                chosen = row
                break
        if not chosen and inventory_rows:
            chosen = inventory_rows[0]
        if not chosen:
            return None
        chosen['Available'] = max(float(chosen['QtyOnHand'] or 0) - float(chosen['QtyAllocated'] or 0), 0)
        return chosen

    def load_other_warehouses(self, inventory_rows, warehouse_id):
        return [
            {**row, 'Available': max(float(row['QtyOnHand'] or 0) - float(row['QtyAllocated'] or 0), 0)}
            for row in inventory_rows
            if row.get('WhseLink') != warehouse_id
        ]

    def load_warehouse_selector(self, stock_link):
        self.cursor.execute(
            """
            SELECT WHSE.WhseLink, WHSE.WhseCode, WHSE.WhseDescription WhseName
            FROM cmn._uvWarehouses WHSE
			JOIN [cmn].[_uvStockWarehouse] LINK on LINK.WhseID = WHSE.WhseLink
			WHERE LINK.StockID = ?
            ORDER BY WHSE.WhseCode
            """,
            (stock_link,)
        )
        return [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]

    def load_sprays(self, stock_link, warehouse_id=None, limit=20):
        query = """
            SELECT SprayId, SprayHNo, SprayHDate, StockId, TotalQty
            FROM [agr].[_uvSprayStockRequirements]
            WHERE StockId = ?
        """
        params = [stock_link]
        if warehouse_id is not None:
            query += " AND WhseId = ?"
            params.append(warehouse_id)
        query += " ORDER BY SprayHDate DESC"
        self.cursor.execute(query, tuple(params))
        rows = [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]
        return [
            {
                'spray_id': r['SprayId'],
                'spray_no': r['SprayHNo'],
                'spray_date': r['SprayHDate'],
                'spray_date_label': r['SprayHDate'].strftime('%d %b') if r['SprayHDate'] else None,
                'total_qty': float(r['TotalQty'] or 0),
            }
            for r in rows[:limit]
        ]

    def load_chemstock(self, stock_link):
        self.cursor.execute(
            """
            SELECT  STK.ChemStockLink, ACT.ChemActIngredient, CRP.CropDescription, STKCRP.StkCrpRegNumber,
                    CLR.ChemColCode, STKCRP.StkCrpType, STKCRP.StkCrpFunctionDef,
                    STKCRP.StkCrpWitholdingPeriodDef
            FROM agr.ChemStock STK
            LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = STK.ChemStockActiveIngrId
            LEFT JOIN agr.ChemStockCrop STKCRP on STKCRP.StkCrpChemStockId = STK.IdChemStock
            LEFT JOIN agr.ChemColour CLR on CLR.IdChemCol = StK.ChemStockColourCodeId
            LEFT JOIN agr.Crop CRP on CRP.IdCrop = STKCRP.StkCrpCropId
            WHERE STK.ChemStockLink = ?
            ORDER BY CRP.CropDescription
            """,
            (stock_link,),
        )
        rows = [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]
        if not rows:
            return {
                'chemstock_link': None,
                'active_ingredient': None,
                'colour_code': None,
                'crops': [],
            }
        first = rows[0]
        return {
            'chemstock_link': first['ChemStockLink'],
            'active_ingredient': first['ChemActIngredient'],
            'colour_code': first['ChemColCode'],
            'crops': [
                {
                    'crop_description': r['CropDescription'],
                    'reg_number': r['StkCrpRegNumber'],
                    'type': r['StkCrpType'],
                    'function': r['StkCrpFunctionDef'],
                    'withholding_period': r['StkCrpWitholdingPeriodDef'],
                }
                for r in rows
            ]
        }

    def load_supplier_info(self, stock_link):
        self.cursor.execute(
            """
            SELECT TOP 1
                SUP.Name AS SupplierName,
                ISNULL(LINK.LastInvoicePrice, ISNULL(GRV.PurchaseUnitLastGRVCost, 0)) AS LastInvoicePrice,
                LINK.bDefaultSupplier
            FROM stk._uvStockLinks LINK
            LEFT JOIN cmn._uvSuppliers SUP ON SUP.DCLink = LINK.iDCLink
            LEFT JOIN cmn._uvLastGRVCost GRV ON GRV.StockLink = LINK.iStockID
            WHERE LINK.iStockID = ?
            ORDER BY ISNULL(LINK.bDefaultSupplier, 0) DESC
            """,
            (stock_link,),
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        row = row_to_dict(self.cursor, row)
        return {
            'supplier_name': row['SupplierName'],
            'last_price': float(row['LastInvoicePrice'] or 0),
            'is_default': bool(row['bDefaultSupplier']),
        }

    def load_similar_products(self, stock_link):
        self.cursor.execute(
            """
            SELECT TOP 3
                STK.ChemStockLink AS StockLink,
                ITEM.StockCode,
                ITEM.StockDescription
            FROM agr.ChemStock STK
            JOIN cmn._uvStockItems ITEM ON ITEM.StockLink = STK.ChemStockLink
            WHERE STK.ChemStockActiveIngrId = (
                SELECT ChemStockActiveIngrId
                FROM agr.ChemStock
                WHERE ChemStockLink = ?
            )
              AND STK.ChemStockLink <> ?
            ORDER BY ITEM.StockCode
            """,
            (stock_link, stock_link),
        )
        return [
            {
                'stock_link': r.StockLink,
                'stock_code': r.StockCode,
                'stock_description': r.StockDescription,
            }
            for r in self.cursor.fetchall()
        ]

    def load_last_stock_count(self, stock_link, warehouse_id):
        if warehouse_id is None:
            return None
        self.cursor.execute(
            """
            SELECT TOP 1 InvCountTimeFinalised
            FROM stk.InventoryCountHeaders HEA
            JOIN stk.InventoryCountLines LIN on LIN.InvCountLineHeaderId = HEA.InvCountHeaderId
            WHERE LIN.InvCountLineStockId = ? AND HEA.InvCountWhseId = ?
            ORDER BY InvCountTimeFinalised DESC
            """,
            (stock_link, warehouse_id),
        )
        row = self.cursor.fetchone()
        if row and getattr(row, 'InvCountTimeFinalised', None):
            return row.InvCountTimeFinalised
        return None

    def load_transaction_rows(self, stock_link, warehouse_id=None, limit=8):
        params = [stock_link]
        where_clause = "StockLink = ?"
        if warehouse_id is not None:
            where_clause += " AND WhseLink = ?"
            params.append(warehouse_id)

        query = "SELECT "
        if limit is not None:
            limit = int(limit)
            query += f"TOP {limit} "
        query += "\n                TxDate, TrnType, Reference, cReference2, Id,\n                ProjectName, UserName, Qty, QtyOnHand, WhseLink, WhseCode\n            FROM cmn._uvStockTransactions\n            WHERE " + where_clause + "\n            ORDER BY TxDate DESC, AutoIdx DESC\n            "
        self.cursor.execute(query, tuple(params))
        return [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]

    def load_transaction_history(self, stock_link, warehouse_id=None, filters=None, page=1, page_size=25):
        filters = filters or {}
        conditions = ["StockLink = ?"]
        params = [stock_link]
        if warehouse_id is not None:
            conditions.append("WhseLink = ?")
            params.append(warehouse_id)
        if filters.get('transaction_type'):
            conditions.append("TrnType = ?")
            params.append(filters['transaction_type'])
        if filters.get('project'):
            conditions.append("ProjectName LIKE ?")
            params.append(f"%{filters['project']}%")
        if filters.get('reference'):
            conditions.append("(Reference LIKE ? OR cReference2 LIKE ?)")
            params.extend([f"%{filters['reference']}%", f"%{filters['reference']}%"])
        if filters.get('user'):
            conditions.append("UserName LIKE ?")
            params.append(f"%{filters['user']}%")
        if filters.get('date_from'):
            conditions.append("TxDate >= ?")
            params.append(filters['date_from'])
        if filters.get('date_to'):
            conditions.append("TxDate <= ?")
            params.append(filters['date_to'])

        where_clause = " AND ".join(conditions)
        count_query = f"SELECT COUNT(1) AS TotalCount FROM cmn._uvStockTransactions WHERE {where_clause}"
        self.cursor.execute(count_query, tuple(params))
        total = self.cursor.fetchone().TotalCount or 0

        offset = max(0, (page - 1) * page_size)
        query = f"""
            SELECT 
                TxDate, TrnType, Reference, cReference2, Id,
                ProjectName, UserName, Qty, QtyOnHand,
                WhseLink, WhseCode, cReference2 AS OrderReference
            FROM cmn._uvStockTransactions
            WHERE {where_clause}
            ORDER BY TxDate DESC, AutoIdx DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """
        params_with_paging = params + [offset, page_size]
        self.cursor.execute(query, tuple(params_with_paging))
        rows = [row_to_dict(self.cursor, row) for row in self.cursor.fetchall()]
        return {
            'transactions': rows,
            'page': page,
            'page_size': page_size,
            'total': total,
            'page_count': (total + page_size - 1) // page_size,
        }

    def load_consumption_stats(self, stock_link, warehouse_id=None):
        conditions = ["StockLink = ?", "Qty < 0"]
        params = [stock_link]
        if warehouse_id is not None:
            conditions.append("WhseLink = ?")
            params.append(warehouse_id)
        now = datetime.now()
        base_query = """
            SELECT SUM(CAST(-Qty AS FLOAT)) AS Consumption, COUNT(1) AS Moves
            FROM cmn._uvStockTransactions
            WHERE {where_clause} AND TxDate >= ?
        """
        result = {}
        for window in [30, 90, 180]:
            where_clause = " AND ".join(conditions)
            query = base_query.format(where_clause=where_clause)
            cutoff = now - timedelta(days=window)
            self.cursor.execute(query, tuple(params + [cutoff]))
            row = self.cursor.fetchone()
            result[f'consumption_{window}_days'] = float(getattr(row, 'Consumption', 0) or 0)
            result[f'moves_{window}_days'] = int(getattr(row, 'Moves', 0) or 0)
        return result

    def calculate_average_daily_consumption(self, consumption_stats):
        for window in [30, 90, 180]:
            total = consumption_stats.get(f'consumption_{window}_days', 0)
            if total > 0:
                return total / window
        return 0.0

    def estimate_days_until_empty(self, available, consumption_stats):
        if available <= 0:
            return None
        daily_use = self.calculate_average_daily_consumption(consumption_stats)
        if daily_use <= 0:
            return None
        return int(available / daily_use)

    def build_last_movement(self, transaction_rows):
        if not transaction_rows:
            return None
        latest = transaction_rows[0]
        return {
            'date': latest.get('TxDate').strftime('%d %b %Y') if latest.get('TxDate') else None,
            'type': latest.get('TrnType'),
            'reference': latest.get('Reference') or latest.get('cReference2') or None,
            'qty': latest.get('Qty'),
            'balance': latest.get('QtyOnHand'),
            'project': latest.get('ProjectName') or None,
        }

    def build_warnings(self, selected_inventory, chemstock, consumption_stats, next_spray):
        warnings = []
        if selected_inventory['QtyOnHand'] <= 0:
            warnings.append({'severity': 'error', 'message': 'No stock available in this warehouse'})
        if selected_inventory['QtyOnHand'] < selected_inventory['ReorderLevel']:
            warnings.append({'severity': 'warning', 'message': 'Below reorder level'})
        if next_spray and next_spray['spray_date'] and next_spray['spray_date'] <= datetime.now().date() + timedelta(days=1):
            warnings.append({'severity': 'warning', 'message': 'Needed for spray soon'})
        if not chemstock.get('active_ingredient'):
            warnings.append({'severity': 'warning', 'message': 'Agronomic registration details missing'})
        return warnings

    def build_warehouse_models(self, inventory_rows, consumption_stats=None):
        return [
            {
                'whse_link': row['WhseLink'],
                'whse_code': row['WhseCode'],
                'whse_name': row['WhseName'],
                'qty_on_hand': float(row['QtyOnHand'] or 0),
                'qty_allocated': float(row['QtyAllocated'] or 0),
                'qty_available': float(row.get('Available', max(float(row.get('QtyOnHand', 0) or 0) - float(row.get('QtyAllocated', 0) or 0), 0)) or 0),
                'qty_on_po': float(row['QtyOnPO'] or 0),
                'qty_on_ibt': float(row['QtyOnIBT'] or 0),
                'reorder_level': float(row['ReorderLevel'] or 0),
                'reorder_qty': float(row['ReorderQty'] or 0),
                'days_until_empty': None,
                'last_movement': None,
            }
            for row in inventory_rows
        ]

    def build_overview(self, base, selected_inventory, supplier_info, consumption_stats, last_stock_count, last_movement, days_until_empty):
        return {
            'stock_code': base['StockCode'],
            'stock_description': base['StockDescription'],
            'category_id': base['ItemCategoryID'],
            'category_name': base['cCategoryName'],
            'reorder_level': float(base['ReorderLevel'] or 0),
            'reorder_qty': float(base['ReorderQty'] or 0),
            'warehouse_name': selected_inventory['WhseName'],
            'qty_on_hand': float(selected_inventory['QtyOnHand'] or 0),
            'qty_allocated': float(selected_inventory['QtyAllocated'] or 0),
            'qty_available': float(selected_inventory['Available'] or 0),
            'qty_on_po': float(selected_inventory['QtyOnPO'] or 0),
            'qty_on_ibt': float(selected_inventory['QtyOnIBT'] or 0),
            'avg_monthly_usage': round(self.calculate_average_daily_consumption(consumption_stats) * 30, 2),
            'last_stock_count_date': last_stock_count,
            'last_movement': last_movement,
            'days_until_empty': days_until_empty,
            'supplier_name': supplier_info['supplier_name'] if supplier_info else None,
            'last_cost': supplier_info['last_price'] if supplier_info else None,
            'last_purchase_date': None,
        }

    def build_product_model(self, stock_link, warehouse_id):
        base = self.load_product_base(stock_link)
        if not base:
            return None
        inventory_rows = self.load_inventory_rows(stock_link)
        selected_inventory = self.load_selected_inventory(inventory_rows, warehouse_id)
        other_warehouses = self.load_other_warehouses(inventory_rows, warehouse_id)
        sprays = self.load_sprays(stock_link, warehouse_id)
        chemstock = self.load_chemstock(stock_link)
        supplier_info = self.load_supplier_info(stock_link)
        similar_products = self.load_similar_products(stock_link)
        recent_transactions = self.load_transaction_rows(stock_link, warehouse_id, limit=8)
        consumption_stats = self.load_consumption_stats(stock_link, warehouse_id)
        days_until_empty = self.estimate_days_until_empty(selected_inventory['Available'], consumption_stats)
        last_stock_count = self.load_last_stock_count(stock_link, warehouse_id)
        last_movement = self.build_last_movement(recent_transactions)
        warnings = self.build_warnings(selected_inventory, chemstock, consumption_stats, sprays[0] if sprays else None)

        return {
            'base': base,
            'overview': self.build_overview(base, selected_inventory, supplier_info, consumption_stats, last_stock_count, last_movement, days_until_empty),
            'history': {
                'recent_transactions': recent_transactions,
                'consumption_stats': consumption_stats,
                'last_movement': last_movement,
            },
            'warehouses': {
                'selected': selected_inventory,
                'others': other_warehouses,
                'all': self.build_warehouse_models(inventory_rows, consumption_stats),
            },
            'sprays': {
                'upcoming': [s for s in sprays if s['spray_date'] and s['spray_date'] >= datetime.now().date()],
                'recent': sprays,
            },
            'chemstock': chemstock,
            'supplier': supplier_info,
            'similar_products': similar_products,
            'warnings': warnings,
        }

    def format_for_template(self, product):
        overview = product['overview']
        history = product['history']
        spray_rows = [
            {
                'SprayId': s['spray_id'],
                'SprayNo': s['spray_no'],
                'SprayDate': s['spray_date_label'],
                'TotalQty': format_qty(s['total_qty']),
            }
            for s in product['sprays']['upcoming']
        ]
        recent_activity = [
            {
                **row,
                'Qty': format_qty(row['Qty']),
                'QtyOnHand': format_qty(row['QtyOnHand']),
            }
            for row in history['recent_transactions']
        ]
        return {
            **product,
            'StockLink': product['base']['StockLink'] if 'StockLink' in product['base'] else None,
            'StockCode': overview['stock_code'],
            'StockDescription': overview['stock_description'],
            'CategoryId': overview['category_id'],
            'Category': overview['category_name'],
            'ReorderLevel': format_qty(overview['reorder_level']),
            'ReorderQty': format_qty(overview['reorder_qty']),
            'WarehouseName': overview['warehouse_name'],
            'QtyOnHand': format_qty(overview['qty_on_hand']),
            'QtyOnPo': format_qty(overview['qty_on_po']),
            'QtyOnIssues': format_qty(overview['qty_allocated']),
            'QtyOnIBT': format_qty(overview['qty_on_ibt']),
            'Available': format_qty(overview['qty_available']),
            'DaysUntilEmpty': overview['days_until_empty'],
            'LastStockCountDate': overview['last_stock_count_date'],
            'LastMovement': {
                'date': overview['last_movement']['date'],
                'type': overview['last_movement']['type'],
                'reference': overview['last_movement']['reference'],
                'qty': format_qty(overview['last_movement']['qty']) if overview['last_movement'] else None,
                'balance': format_qty(overview['last_movement']['balance']) if overview['last_movement'] else None,
                'project': overview['last_movement']['project'] if overview['last_movement'] else None,
            } if overview['last_movement'] else None,
            'LastPurchaseInfo': {
                'supplier': product['supplier']['supplier_name'] if product['supplier'] else None,
                'purchase_date': None,
                'cost': format_qty(product['supplier']['last_price']) if product['supplier'] else None,
            } if product['supplier'] else None,
            'Sprays': spray_rows,
            'TransactionHistory': recent_activity,
            'Crops': [
                {
                    'CropDescription': c['crop_description'],
                    'RegNumber': c['reg_number'],
                    'Type': c['type'],
                    'Function': c['function'],
                    'WitholdingPeriod': c['withholding_period'],
                }
                for c in product['chemstock']['crops']
            ],
            'ChemStockActiveIngr': product['chemstock']['active_ingredient'],
            'ChemStockColourCode': product['chemstock']['colour_code'],
            'AllWarehouses': [
                {
                    **row,
                    'QtyOnHand': format_qty(row['qty_on_hand']),
                    'QtyAllocated': format_qty(row['qty_allocated']),
                    'QtyAvailable': format_qty(row['qty_available']),
                    'QtyOnPO': format_qty(row['qty_on_po']),
                    'QtyOnIBT': format_qty(row['qty_on_ibt']),
                    'ReorderLevel': format_qty(row['reorder_level']),
                    'ReorderQty': format_qty(row['reorder_qty']),
                }
                for row in product['warehouses']['all']
            ],
            'Warnings': [
                {'severity': w['severity'], 'message': w['message']}
                for w in product['warnings']
            ],
        }

    def get_transaction_history_page(self, stock_link, warehouse_id=None, filters=None, page=1, page_size=25):
        return self.load_transaction_history(stock_link, warehouse_id, filters, page, page_size)
