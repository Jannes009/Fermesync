from Inventory.routes import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from flask import request, render_template, abort, jsonify
from datetime import datetime, timedelta
from .qty import format_qty


def parse_date_param(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None


def row_to_dict(cursor, row):
    if row is None:
        return None
    return {col[0]: getattr(row, col[0], None) for col in cursor.description}


def serialize_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]


def warehouse_placeholders():
    warehouses = list(current_user.warehouses or [])
    if not warehouses:
        return '', ()
    return ','.join(['?'] * len(warehouses)), tuple(warehouses)


def load_inventory_rows(stock_link):
    conn = create_db_connection()
    if not conn:
        return None

    wh_clause, wh_params = warehouse_placeholders()
    if not wh_clause:
        close_db_connection(conn)
        return []

    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                QTY.StockLink,
                QTY.StockCode,
                QTY.StockDescription,
                QTY.WhseLink,
                QTY.WhseCode,
                QTY.WhseName,
                COALESCE(QTY.QtyOnHand, 0) AS QtyOnHand,
                COALESCE(QTY.IncompleteIssuesQty, 0) AS QtyOnIssues,
                COALESCE(QTY.QtyOnPO, 0) AS QtyOnPO,
                COALESCE(QTY.QtyOnIBT, 0) AS QtyOnIBT,
                COALESCE(QTY.ReorderLevel, 0) AS ReorderLevel,
                COALESCE(QTY.ReorderQty, 0) AS ReorderQty,
                QTY.idStockCategories,
                QTY.cCategoryName,
                FN.SprayHWeek AS FirstNegativeWeek,
                FN.ProjectedBalance,
                CASE
                    WHEN FN.SprayHWeek IS NULL THEN NULL
                    ELSE
                        ((CAST(LEFT(FN.SprayHWeek, 4) AS int) - YEAR(GETDATE())) * 52)
                        + (CAST(RIGHT(FN.SprayHWeek, 2) AS int) - DATEPART(ISO_WEEK, GETDATE()))
                END AS WeeksUntilNegative,
                IC.LastStockCount
            FROM stk._uvInventoryQty QTY
            OUTER APPLY (
                SELECT TOP (1)
                    SprayHWeek,
                    ProjectedBalance
                FROM agr._uvStockProjection P
                WHERE P.SprayLineStkId = QTY.StockLink
                  AND P.SprayHWhseId = QTY.WhseLink
                  AND P.ProjectedBalance < 0
                ORDER BY P.SprayHWeek
            ) FN
            OUTER APPLY (
                SELECT TOP (1)
                    HEA.InvCountTimeFinalised AS LastStockCount
                FROM stk.InventoryCountHeaders HEA
                INNER JOIN stk.InventoryCountLines LIN
                    ON LIN.InvCountLineHeaderId = HEA.InvCountHeaderId
                WHERE LIN.InvCountLineStockId = QTY.StockLink
                  AND HEA.InvCountWhseId = QTY.WhseLink
                ORDER BY HEA.InvCountTimeFinalised DESC
            ) IC
            WHERE QTY.StockLink = ?
              AND QTY.WhseLink IN ({wh_clause})
            ORDER BY QTY.WhseCode
        """, (stock_link,) + wh_params)
        return [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)


def format_inventory_row(row):
    qty_on_hand = float(row.get('QtyOnHand') or 0)
    qty_on_issues = float(row.get('QtyOnIssues') or 0)
    weeks = row.get('WeeksUntilNegative')
    return {
        'WhseLink': row['WhseLink'],
        'WhseCode': row['WhseCode'],
        'WhseName': row['WhseName'],
        'QtyOnHand': format_qty(qty_on_hand),
        'QtyOnIssues': format_qty(qty_on_issues),
        'QtyOnPO': format_qty(row.get('QtyOnPO')),
        'QtyOnIBT': format_qty(row.get('QtyOnIBT')),
        'ReorderLevel': format_qty(row.get('ReorderLevel')),
        'ReorderQty': format_qty(row.get('ReorderQty')),
        'CategoryId': row.get('idStockCategories'),
        'CategoryName': row.get('cCategoryName'),
        'LastStockCount': serialize_date(row.get('LastStockCount')),
        'WeeksUntilNegative': weeks if weeks is None else int(weeks),
        'FirstNegativeWeek': row.get('FirstNegativeWeek'),
    }


def load_suppliers(stock_link):
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cur = conn.cursor()
        cur.execute("""
        SELECT
            SUP.Name AS SupplierName,
            COALESCE(LINK.LastInvoicePrice, GRV.PurchaseUnitLastGRVCost) AS Price,
            LINK.InvDate,
            COALESCE(LINK.iUnitsOfMeasureID, GRV.iUOMDefPurchaseUnitID) AS iUnitsOfMeasureID,
            UOM.cUnitCode,
            LINK.bDefaultSupplier
        FROM stk._uvStockLinks LINK
        LEFT JOIN cmn._uvSuppliers SUP
            ON SUP.DCLink = LINK.iDCLink
        LEFT JOIN cmn._uvLastGRVCost GRV
            ON GRV.iDCLink = LINK.iDCLink
        AND GRV.StockLink = LINK.iStockID
        LEFT JOIN cmn._uvUOM UOM
            ON UOM.idUnits = COALESCE(LINK.iUnitsOfMeasureID, GRV.iUOMDefPurchaseUnitID)
        WHERE LINK.iStockID = ?
        ORDER BY ISNULL(LINK.bDefaultSupplier, 0) DESC,
         SUP.Name;
        """, (stock_link,))
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)

    return [
        {
            'SupplierName': row.get('SupplierName') or 'Unknown',
            'IsDefault': bool(row.get('bDefaultSupplier')),
            'LastPrice': format_qty(row.get('Price')),
            'InvoiceDate': serialize_date(row.get('InvDate')),
            'Unit': row.get('cUnitCode') or '',
        }
        for row in rows
    ]


def load_outstanding_orders(stock_link):
    conn = create_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
        SELECT
            SupplierName,
            OrderNum,
            OrderDate,
            OrderDesc,
            iLineID AS LineId,
            WhName AS WarehouseName,
            fQuantity AS Quantity,
            fQtyProcessed AS QtyProcessed,
            QtyOutstanding,
            UnitCode,
            fUnitPriceExcl AS UnitPrice
        FROM stk._uvPO_Outstanding
        WHERE iStockCodeID = ?
        ORDER BY OrderDate DESC, OrderNum, LineId
        """, (stock_link,))
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)

    return [
        {
            'supplier_name': row.get('SupplierName') or 'Unknown',
            'order_number': row.get('OrderNum') or '—',
            'order_date': serialize_date(row.get('OrderDate')),
            'order_desc': row.get('OrderDesc') or '—',
            'line_id': row.get('LineId'),
            'warehouse_name': row.get('WarehouseName') or '—',
            'quantity': float(row.get('Quantity') or 0),
            'qty_processed': float(row.get('QtyProcessed') or 0),
            'qty_outstanding': float(row.get('QtyOutstanding') or 0),
            'unit_code': row.get('UnitCode') or '—',
            'unit_price': float(row.get('UnitPrice') or 0),
            'total_outstanding': float(row.get('QtyOutstanding') or 0) * float(row.get('UnitPrice') or 0),
        }
        for row in rows
    ]


def load_registrations(stock_link):
    conn = create_db_connection()
    if not conn:
        return {
            'ActiveIngredient': None,
            'ColourCode': None,
            'Crops': [],
            'IsChemProduct': False,
        }

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                STK.ChemStockLink,
                ACT.ChemActIngredient,
                CRP.CropDescription,
                STKCRP.StkCrpRegNumber,
                CLR.ChemColCode,
                STKCRP.StkCrpType,
                STKCRP.StkCrpFunctionDef,
                STKCRP.StkCrpWitholdingPeriodDef
            FROM agr.ChemStock STK
            LEFT JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = STK.ChemStockActiveIngrId
            LEFT JOIN agr.ChemStockCrop STKCRP ON STKCRP.StkCrpChemStockId = STK.IdChemStock
            LEFT JOIN agr.ChemColour CLR ON CLR.IdChemCol = STK.ChemStockColourCodeId
            LEFT JOIN agr.Crop CRP ON CRP.IdCrop = STKCRP.StkCrpCropId
            WHERE STK.ChemStockLink = ?
            ORDER BY CRP.CropDescription
        """, (stock_link,))
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)

    if not rows:
        return {
            'ActiveIngredient': None,
            'ColourCode': None,
            'Crops': [],
            'IsChemProduct': False,
        }

    first = rows[0]
    crops = [
        {
            'CropDescription': row.get('CropDescription') or '-',
            'RegNumber': row.get('StkCrpRegNumber') or '-',
            'Type': row.get('StkCrpType') or '-',
            'Function': row.get('StkCrpFunctionDef') or '-',
            'WithholdingPeriod': row.get('StkCrpWitholdingPeriodDef') or '-',
        }
        for row in rows
        if row.get('CropDescription') or row.get('StkCrpRegNumber')
    ]

    return {
        'ActiveIngredient': first.get('ChemActIngredient'),
        'ColourCode': first.get('ChemColCode'),
        'Crops': crops,
        'IsChemProduct': first.get('ChemStockLink') is not None,
    }


def build_notices(selected_warehouse, suppliers, registrations):
    notices = []

    has_default = any(s.get('IsDefault') for s in suppliers)
    if suppliers and not has_default:
        notices.append({'severity': 'warning', 'message': 'No default supplier'})

    weeks = selected_warehouse.get('WeeksUntilNegative')
    if weeks is not None and weeks <= 4:
        notices.append({
            'severity': 'warning',
            'message': 'Product will become negative soon',
        })

    if registrations.get('IsChemProduct'):
        if not registrations.get('ActiveIngredient'):
            notices.append({'severity': 'warning', 'message': 'Missing active ingredient registration'})
        if not registrations.get('ColourCode'):
            notices.append({'severity': 'warning', 'message': 'Missing colour code'})
        if not registrations.get('Crops'):
            notices.append({'severity': 'warning', 'message': 'Missing crop registrations'})

    return notices


def load_warehouse_selector(stock_link):
    conn = create_db_connection()
    if not conn:
        return []

    wh_clause, wh_params = warehouse_placeholders()
    if not wh_clause:
        close_db_connection(conn)
        return []

    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT WHSE.WhseLink, WHSE.WhseCode, WHSE.WhseDescription AS WhseName
            FROM cmn._uvWarehouses WHSE
            JOIN cmn._uvStockWarehouse LINK ON LINK.WhseID = WHSE.WhseLink
            WHERE LINK.StockID = ?
              AND WHSE.WhseLink IN ({wh_clause})
            ORDER BY WHSE.WhseCode
        """, (stock_link,) + wh_params)
        return [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)


def load_transaction_history(stock_link, start_date, end_date):
    conn = create_db_connection()
    if not conn:
        return None

    wh_clause, wh_params = warehouse_placeholders()
    if not wh_clause:
        close_db_connection(conn)
        return []

    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                TxDate,
                TrnType,
                Reference,
                cReference2,
                ProjectName,
                UserName,
                Qty,
                UnitCost,
                TotalCost,
                QtyOnHand,
                WhseLink,
                WhseName
            FROM cmn._uvStockTransactions
            WHERE StockLink = ?
              AND WhseLink IN ({wh_clause})
              AND TxDate >= ?
              AND TxDate <= ?
            ORDER BY TxDate DESC, AutoIdx DESC
        """, (stock_link,) + wh_params + (start_date, end_date))
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)

    transactions = []
    for row in rows:
        transactions.append({
            'TxDate': serialize_date(row.get('TxDate')),
            'TrnType': row.get('TrnType') or '',
            'Reference': (row.get('Reference') or '').strip(),
            'SecondaryReference': (row.get('cReference2') or '').strip(),
            'OrderNumber': (row.get('cReference2') or row.get('Reference') or '').strip(),
            'ProjectName': (row.get('ProjectName') or '').strip(),
            'UserName': (row.get('UserName') or '').strip(),
            'Qty': format_qty(row.get('Qty')),
            'UnitCost': format_qty(row.get('UnitCost')),
            'TotalCost': format_qty(row.get('TotalCost')),
            'QtyOnHand': format_qty(row.get('QtyOnHand')),
            'WhseLink': row.get('WhseLink'),
            'WhseName': row.get('WhseName') or '',
        })
    return transactions


def load_sprays(stock_link):
    conn = create_db_connection()
    if not conn:
        return []

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                HEA.SprayHDescription,
                HEA.SprayHStatus,
                EXE.SprExecDate,
                LIN.SprayLineTotalQty,
                UOM.cUnitCode,
                HEA.SprayHWeek
            FROM agr.SprayLines LIN
            JOIN agr.SprayHeader HEA ON HEA.IdSprayH = LIN.SprayLineHeaderId
            JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
            LEFT JOIN agr.SprayExecution EXE ON EXE.IdSprExec = HEA.SprayHExecutionId
            WHERE LIN.SprayLineStkId = ?
              AND ISNULL(HEA.SprayHCancelled, 0) = 0
            ORDER BY
                CASE WHEN EXE.SprExecDate IS NULL THEN 1 ELSE 0 END,
                EXE.SprExecDate DESC,
                HEA.SprayHWeek DESC
        """, (stock_link,))
        rows = [row_to_dict(cur, row) for row in cur.fetchall()]
    finally:
        close_db_connection(conn)

    return [
        {
            'Description': row.get('SprayHDescription') or row.get('SprayHWeek') or '-',
            'Status': row.get('SprayHStatus') or '-',
            'ExecutionDate': serialize_date(row.get('SprExecDate')),
            'QtyUom': f"{format_qty(row.get('SprayLineTotalQty'))} {row.get('cUnitCode') or ''}".strip(),
        }
        for row in rows
    ]


@inventory_bp.route('/product/<int:stock_link>')
@login_required
def product_detail(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    warehouse_id = request.args.get('whse', type=int)
    if warehouse_id is None:
        return 'Warehouse ID is required', 400

    inventory_rows = load_inventory_rows(stock_link)
    if not inventory_rows:
        abort(404)

    formatted_rows = [format_inventory_row(row) for row in inventory_rows]
    selected = next((row for row in formatted_rows if row['WhseLink'] == warehouse_id), None)
    if not selected:
        abort(404)

    suppliers = load_suppliers(stock_link)
    registrations = load_registrations(stock_link)
    notices = build_notices(selected, suppliers, registrations)
    warehouses = load_warehouse_selector(stock_link)

    product = {
        'StockLink': stock_link,
        'StockCode': inventory_rows[0]['StockCode'],
        'StockDescription': inventory_rows[0]['StockDescription'],
    }

    return render_template(
        'product_detail.html',
        product=product,
        warehouse_id=warehouse_id,
        warehouses=warehouses,
        selected_warehouse=selected,
        all_warehouses=formatted_rows,
        suppliers=suppliers,
        registrations=registrations,
        notices=notices,
    )


@inventory_bp.route('/product/<int:stock_link>/outstanding-orders')
@login_required
def product_outstanding_orders(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    orders = load_outstanding_orders(stock_link)
    if orders is None:
        return jsonify({'error': 'Database connection failed'}), 500

    return jsonify({
        'outstanding_orders': orders
    })


@inventory_bp.route('/product/<int:stock_link>/history')
@login_required
def product_history(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    end_date = parse_date_param(request.args.get('end_date')) or datetime.now()
    start_date = parse_date_param(request.args.get('start_date'))
    if start_date is None:
        start_date = end_date - timedelta(days=183)

    end_inclusive = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    transactions = load_transaction_history(stock_link, start_date, end_inclusive)
    if transactions is None:
        return jsonify({'error': 'Database connection failed'}), 500

    types = sorted({t['TrnType'] for t in transactions if t.get('TrnType')})
    projects = sorted({t['ProjectName'] for t in transactions if t.get('ProjectName')})
    users = sorted({t['UserName'] for t in transactions if t.get('UserName')})
    warehouse_list = sorted(
        {(t['WhseLink'], t['WhseName']) for t in transactions if t.get('WhseLink')},
        key=lambda wh: wh[1] or '',
    )

    return jsonify({
        'transactions': transactions,
        'types': types,
        'projects': projects,
        'users': users,
        'warehouses': [
            {'warehouse_id': wh[0], 'warehouse_code': wh[1]}
            for wh in warehouse_list
        ],
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
    })


@inventory_bp.route('/product/<int:stock_link>/sprays')
@login_required
def product_sprays(stock_link):
    if 'WHSE_QTYS' not in current_user.permissions:
        abort(403)

    sprays = load_sprays(stock_link)
    return jsonify({'sprays': sprays})


@inventory_bp.route('/update-reordering/<int:stock_link>', methods=['POST'])
@login_required
def update_reordering(stock_link):
    conn = create_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        data = request.get_json() or {}
        warehouse_id = data.get('warehouseId')
        cursor = conn.cursor()
        cursor.execute("""
            EXEC [stk].[sp_UpdateCategoryAndReordering]
                @StockId = ?,
                @Category = ?,
                @ReorderLevel = ?,
                @ReorderQty = ?,
                @WarehouseId = ?;
        """, (
            stock_link,
            data.get('categoryId'),
            data.get('reorderLevel'),
            data.get('reorderQty'),
            warehouse_id,
        ))
        conn.commit()
        return jsonify({'success': True, 'message': 'Inventory settings updated successfully'})
    except Exception as e:
        conn.rollback()
        print(f'Error updating reordering data: {e}')
        return jsonify({'error': 'Failed to update inventory settings'}), 500
    finally:
        close_db_connection(conn)


@inventory_bp.route('/categories')
@login_required
def get_categories():
    conn = create_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        warehouse_id = request.args.get('whse', type=int)
        if not warehouse_id:
            return jsonify({'error': 'Warehouse ID is required'}), 400

        cursor = conn.cursor()
        cursor.execute("""
            SELECT ItemCategoryID, cCategoryName
            FROM stk._uvWarehouseCategories
            WHERE WhseID = ?
        """, (warehouse_id,))
        rows = cursor.fetchall()
        categories = [
            {'category_id': r.ItemCategoryID, 'category_name': r.cCategoryName}
            for r in rows
        ]
        return jsonify({'status': 'ok', 'categories': categories})
    except Exception as e:
        print(f'Error fetching categories: {e}')
        return jsonify({'error': 'Failed to fetch categories'}), 500
    finally:
        close_db_connection(conn)
