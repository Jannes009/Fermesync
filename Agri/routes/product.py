import os
import hmac
import secrets
from decimal import Decimal, InvalidOperation
from flask import current_app, render_template, request, url_for, jsonify, session
from flask_login import login_required
from Core.auth import create_db_connection, close_db_connection
from . import agri_bp

LABELS_DATABASE_NAME = os.getenv('FERMESYNC_LABELS_DB_NAME', 'FER_AGRI_LABELS')


def _product_csrf_token():
    token = session.get('_agri_product_csrf')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_agri_product_csrf'] = token
    return token


def _valid_product_csrf(data=None):
    expected = session.get('_agri_product_csrf')
    provided = request.headers.get('X-CSRF-Token') or (data or {}).get('csrf_token')
    return bool(expected and provided and hmac.compare_digest(str(expected), str(provided)))


def _positive_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError()
    parsed = int(value)
    if parsed <= 0:
        raise ValueError()
    return parsed


@agri_bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict(flat=False)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Invalid product details."}), 400
        if not _valid_product_csrf(data):
            return jsonify({"success": False, "message": "Your session token has expired. Reload the page and try again."}), 400

        text_fields = ('brand_name', 'product_code', 'registration_number', 'new_colour_code')
        if any(data.get(field) not in (None, '') and not isinstance(data.get(field), str) for field in text_fields):
            return jsonify({"success": False, "message": "Product name, code, and registration number must be text."}), 400
        brand_name = (data.get('brand_name') or '').strip()
        product_code = (data.get('product_code') or '').strip()
        registration_number = (data.get('registration_number') or '').strip()
        active_ing_values = data.get('active_ing') or []
        if not isinstance(active_ing_values, (list, tuple)):
            active_ing_values = [active_ing_values]
        active_ing_ids = []
        invalid_active_ing = False
        for value in active_ing_values:
            if value in (None, ''):
                continue
            try:
                active_ing_id = _positive_id(value)
            except (TypeError, ValueError):
                invalid_active_ing = True
                break
            if active_ing_id <= 0:
                invalid_active_ing = True
                break
            if active_ing_id not in active_ing_ids:
                active_ing_ids.append(active_ing_id)
        new_active_ingredient_values = data.get('new_active_ingredients') or []
        if not isinstance(new_active_ingredient_values, (list, tuple)):
            new_active_ingredient_values = [new_active_ingredient_values]
        new_active_ingredient_names = []
        for value in new_active_ingredient_values:
            if not isinstance(value, str):
                invalid_active_ing = True
                continue
            name = value.strip()
            if name and name.casefold() not in {item.casefold() for item in new_active_ingredient_names}:
                new_active_ingredient_names.append(name)

        errors = []
        if data.get('reviewed') is not True:
            errors.append('Review the product details before creating the product.')
        if not brand_name:
            errors.append('Trade name is required.')
        elif len(brand_name) > 50:
            errors.append('Trade name cannot be longer than 50 characters.')

        if not product_code:
            errors.append('Product code is required.')
        elif len(product_code) > 20:
            errors.append('Product code cannot be longer than 20 characters.')

        if invalid_active_ing:
            errors.append('Active ingredients must be valid names or positive IDs.')
        elif not active_ing_ids and not new_active_ingredient_names:
            errors.append('Choose or add at least one active ingredient.')

        warehouses_payload = data.get('warehouses') or []
        suppliers_payload = data.get('suppliers') or []
        chemstockcrop_payload = data.get('chemstockcrop') or []
        if not isinstance(warehouses_payload, list):
            errors.append('Warehouse selections are invalid.')
            warehouses_payload = []
        elif not warehouses_payload:
            errors.append('Choose at least one warehouse.')
        if not isinstance(suppliers_payload, list):
            errors.append('Supplier selections are invalid.')
            suppliers_payload = []
        if not isinstance(chemstockcrop_payload, list):
            errors.append('Crop/use selections are invalid.')
            chemstockcrop_payload = []
        if not chemstockcrop_payload:
            errors.append('Add at least one crop and use.')

        crop_ids = []
        for crop_entry in chemstockcrop_payload:
            if not isinstance(crop_entry, dict):
                errors.append('Crop/use entries are invalid.')
                break
            if any(
                crop_entry.get(field) not in (None, '') and not isinstance(crop_entry.get(field), str)
                for field in ('func', 'type', 'withholding_period')
            ):
                errors.append('Target, type, and withholding period values must be text.')
                break
            try:
                crop_id = _positive_id(crop_entry.get('crop'))
            except (TypeError, ValueError):
                errors.append('Choose a valid crop for every crop/use entry.')
                break
            if crop_id <= 0:
                errors.append('Choose a valid crop for every crop/use entry.')
                break
            crop_ids.append(crop_id)
        if len(set(crop_ids)) != len(crop_ids):
            errors.append('Each crop can only have one target/use.')

        selected_suppliers = []
        for supplier in suppliers_payload:
            if not isinstance(supplier, dict):
                errors.append('Supplier selections are invalid.')
                break
            if supplier.get('id') in (None, ''):
                continue
            try:
                supplier_id = _positive_id(supplier['id'])
            except (TypeError, ValueError):
                errors.append('Choose valid suppliers.')
                break
            if supplier_id <= 0:
                errors.append('Choose valid suppliers.')
                break
            selected_suppliers.append(supplier)
        preferred_count = sum(
            1 for supplier in selected_suppliers
            if supplier.get('is_default') is True or str(supplier.get('is_default')).casefold() in ('1', 'true', 'yes')
        )
        if not selected_suppliers:
            errors.append('Choose at least one supplier.')
        elif preferred_count != 1:
            errors.append('Choose exactly one preferred supplier.')

        parsed_prices = {}
        for supplier in selected_suppliers:
            value = supplier.get('price')
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append('Enter a price for every selected supplier.')
                break
            try:
                price = Decimal(str(value))
                if not price.is_finite() or price < 0:
                    raise InvalidOperation()
            except (InvalidOperation, ValueError):
                errors.append('Supplier prices must be valid non-negative numbers.')
                break
            parsed_prices[id(supplier)] = price

        if errors:
            return jsonify({"success": False, "message": errors[0], "errors": errors}), 400

        def extract_value(value):
            if isinstance(value, list):
                return value[0] if value else None
            return value

        try:
            group_id = _positive_id(extract_value(data.get('group')))
            colour_value = extract_value(data.get('colour_code'))
            colour_code_id = _positive_id(colour_value) if colour_value not in (None, '') else None
            new_colour_code = (data.get('new_colour_code') or '').strip()
            stocking_unit_id = _positive_id(extract_value(data.get('stocking_unit')))
            purchasing_unit_id = _positive_id(extract_value(data.get('purchasing_unit')))
            if not colour_code_id and not new_colour_code:
                raise ValueError()
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Choose a product group, colour code, and valid units."}), 400

        conn = create_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT TOP 1 StockCode
                FROM cmn._uvStockItems
                WHERE LOWER(StockCode) = ?
            """, (product_code.casefold(),))
            if cur.fetchone():
                close_db_connection(conn, cur)
                return jsonify({
                    "success": False,
                    "message": "That product code is already in use. Choose a different code."
                }), 409

            if not colour_code_id:
                cur.execute("""
                    SELECT TOP 1 IdChemCol
                    FROM agr.ChemColour
                    WHERE LOWER(ChemColCode) = ?
                """, (new_colour_code.casefold(),))
                existing_colour = cur.fetchone()
                if existing_colour:
                    colour_code_id = existing_colour[0]
                else:
                    cur.execute("""
                        INSERT INTO agr.ChemColour (ChemColCode)
                        OUTPUT INSERTED.IdChemCol
                        VALUES (?)
                    """, (new_colour_code,))
                    colour_code_id = cur.fetchone()[0]

            def validate_ids(query, values):
                if not values:
                    return True
                placeholders = ','.join('?' for _ in values)
                cur.execute(query.format(placeholders=placeholders), values)
                return {int(row[0]) for row in cur.fetchall()} == set(values)

            warehouse_ids = []
            shelf_ids = []
            for entry in warehouses_payload:
                if not isinstance(entry, dict):
                    raise ValueError('Warehouse selections are invalid.')
                try:
                    warehouse_id = _positive_id(entry.get('id'))
                except ValueError:
                    raise ValueError('Choose valid warehouses.')
                warehouse_ids.append(warehouse_id)
                if entry.get('shelf') in (None, ''):
                    raise ValueError('Choose a shelf for each selected warehouse.')
                try:
                    shelf_id = _positive_id(entry['shelf'])
                except ValueError:
                    raise ValueError('Choose valid shelf locations.')
                shelf_ids.append(shelf_id)

            supplier_ids = [_positive_id(entry['id']) for entry in selected_suppliers]
            if len(set(warehouse_ids)) != len(warehouse_ids):
                raise ValueError('A warehouse can only be selected once.')
            if len(set(supplier_ids)) != len(supplier_ids):
                raise ValueError('A supplier can only be selected once.')
            if not validate_ids("""
                SELECT idGrpTbl FROM cmn._uvStockGroups WHERE idGrpTbl IN ({placeholders})
            """, [group_id]):
                raise ValueError('Choose a valid product group.')
            if not validate_ids("""
                SELECT IdChemCol FROM agr.ChemColour WHERE IdChemCol IN ({placeholders})
            """, [colour_code_id]):
                raise ValueError('Choose a valid colour code.')
            if not validate_ids("""
                SELECT idUnits FROM cmn._uvUOM WHERE idUnits IN ({placeholders})
            """, list(dict.fromkeys([stocking_unit_id, purchasing_unit_id]))):
                raise ValueError('Choose valid stocking and purchasing units.')
            if not validate_ids("""
                SELECT IdChemAct FROM agr.ChemActiveIngredient WHERE IdChemAct IN ({placeholders})
            """, active_ing_ids):
                raise ValueError('One or more selected active ingredients are no longer available.')
            if not validate_ids("""
                SELECT IdCrop FROM agr.Crop WHERE IdCrop IN ({placeholders})
            """, crop_ids):
                raise ValueError('One or more selected crops are no longer available.')
            if not validate_ids("""
                SELECT WHSE.WhseLink
                FROM cmn._uvWarehouses WHSE
                JOIN agr.WarehouseAttributes ATTR ON ATTR.WhAttrWhseId = WHSE.WhseLink
                WHERE ATTR.WhAttrWhseType = 'Chemical'
                  AND WHSE.WhseLink IN ({placeholders})
            """, warehouse_ids):
                raise ValueError('One or more selected warehouses are not available for chemical products.')
            if not validate_ids("""
                SELECT idStockCategories FROM cmn._uvCategories
                WHERE idStockCategories IN ({placeholders})
            """, shelf_ids):
                raise ValueError('One or more selected shelf locations are no longer available.')
            if not validate_ids("""
                SELECT DCLink FROM cmn._uvSuppliers WHERE DCLink IN ({placeholders})
            """, supplier_ids):
                raise ValueError('One or more selected suppliers are no longer available.')
            cur.execute("""
                SELECT idUnits, iUnitCategoryID
                FROM cmn._uvUOM
                WHERE idUnits IN (?, ?)
            """, (stocking_unit_id, purchasing_unit_id))
            unit_categories = {int(row[0]): row[1] for row in cur.fetchall()}
            if (
                stocking_unit_id not in unit_categories
                or purchasing_unit_id not in unit_categories
                or unit_categories[stocking_unit_id] != unit_categories[purchasing_unit_id]
            ):
                raise ValueError('The selected purchasing unit is not compatible with the stocking unit.')

            cur.execute("""
                INSERT INTO agr.ChemStock
                    (ChemStockCode, ChemStockName, ChemStockRegNumber,
                     ChemStockGroupId, ChemStockColourCodeId, ChemStockStockingUnitId,
                     ChemStockPurchasingUnitId)
                OUTPUT INSERTED.IdChemStock
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                product_code,
                brand_name,
                registration_number,
                group_id,
                colour_code_id,
                stocking_unit_id,
                purchasing_unit_id
            ))
            chem_stock_id = cur.fetchone()[0]

            resolved_active_ing_ids = list(active_ing_ids)
            for ingredient_name in new_active_ingredient_names:
                cur.execute("""
                    SELECT IdChemAct, ChemActIngredient
                    FROM agr.ChemActiveIngredient
                    WHERE ChemActIngredient = ?
                    ORDER BY IdChemAct
                """, (ingredient_name,))
                matching_ingredient = next(
                    (row for row in cur.fetchall() if (row[1] or '').casefold() == ingredient_name.casefold()),
                    None
                )
                if matching_ingredient:
                    active_ing_id = matching_ingredient[0]
                else:
                    cur.execute("""
                        INSERT INTO agr.ChemActiveIngredient (ChemActIngredient)
                        OUTPUT INSERTED.IdChemAct
                        VALUES (?)
                    """, (ingredient_name,))
                    active_ing_id = cur.fetchone()[0]
                if active_ing_id not in resolved_active_ing_ids:
                    resolved_active_ing_ids.append(active_ing_id)

            for active_ing_id in resolved_active_ing_ids:
                cur.execute("""
                    INSERT INTO agr.ChemStockActiveIngredient
                        (CSAIChemStockId, CSAIActiveIngredientId)
                    VALUES (?, ?)
                """, (chem_stock_id, active_ing_id))

            for crop_entry in chemstockcrop_payload:
                crop_id = _positive_id(crop_entry.get('crop'))
                withh_period = str(crop_entry.get('withholding_period') or '').strip()
                reg_type = str(crop_entry.get('type') or '').strip()
                func = str(crop_entry.get('func') or '').strip()

                cur.execute("""
                    INSERT INTO agr.ChemStockCrop
                        (StkCrpChemStockId, StkCrpCropId,
                         StkCrpType, StkCrpWitholdingPeriodDef, StkCrpFunctionDef)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    chem_stock_id,
                    crop_id,
                    reg_type,
                    withh_period,
                    func
                ))

            cur.execute("EXEC agr.sp_CreateStockItem")
            cur.execute("""
            SELECT ChemStockLink
            FROM agr.ChemStock
            WHERE IdChemStock = ?
            """, chem_stock_id)

            stock_link_row = cur.fetchone()
            if not stock_link_row or not stock_link_row[0]:
                raise RuntimeError('Stock item creation did not return a product link.')
            stock_id = stock_link_row[0]

            for warehouse_entry in warehouses_payload:
                whse_id = _positive_id(warehouse_entry.get('id'))
                category_id = _positive_id(warehouse_entry['shelf']) if warehouse_entry.get('shelf') not in (None, '') else None
                cur.execute("""
                    EXEC [stk].[sp_UpdateCategoryAndReordering] 
                        @StockId = ?, 
                        @WarehouseId = ?, 
                        @Category = ?;
                """, (stock_id, whse_id, category_id))

            cur.execute("""
                SELECT ConversionFactor
                FROM cmn._uvStockUnitConversion
                WHERE iUOMStockingUnitID = ? AND iUOMDefPurchaseUnitID = ?
            """, (stocking_unit_id, purchasing_unit_id))
            conversion_row = cur.fetchone()
            conversion_factor = conversion_row[0] if conversion_row else None

            for supplier_entry in suppliers_payload:
                if not isinstance(supplier_entry, dict) or not supplier_entry.get('id'):
                    continue
                supplier_id = _positive_id(supplier_entry['id'])
                price_purchasing = parsed_prices[id(supplier_entry)]
                if conversion_factor:
                    price_stocking = float(price_purchasing / Decimal(str(conversion_factor)))
                else:
                    price_stocking = float(price_purchasing)
                is_default = supplier_entry.get('is_default') is True or str(supplier_entry.get('is_default')).casefold() in ('1', 'true', 'yes')
                cur.execute("""
                    EXEC [cmn].[sp_StockSupplier_Save]
                                @StockId = ?, 
                                @SupplierID = ?, 
                                @IsDefaultSupplier = ?,
                                @LastGRVCost = ?;
                """, (stock_id, supplier_id, is_default, price_stocking))
            conn.commit()
        except ValueError as e:
            conn.rollback()
            close_db_connection(conn, cur)
            return jsonify({"success": False, "message": str(e)}), 400
        except Exception:
            conn.rollback()
            current_app.logger.exception("Unable to create chemical product")
            close_db_connection(conn, cur)
            return jsonify({
                "success": False,
                "message": "Failed to save chemical product details."
            }), 500

        close_db_connection(conn, cur)

        product_url = url_for('inventory.product_detail', stock_link=stock_id) if stock_id else None
        return jsonify({"success": True, "product_code": product_code, "stock_link": stock_id, "product_url": product_url})

    # GET: fetch reference data for the wizard
    conn = create_db_connection()
    cur = conn.cursor()

    # Warehouses
    cur.execute("""
        SELECT WhseLink, WhseDescription
        FROM [cmn]._uvWarehouses WHSE
		JOIN [agr].[WarehouseAttributes] ATTR on ATTR.WhAttrWhseId = WHSE.WhseLink
		WHERE ATTR.WhAttrWhseType = 'Chemical'
        ORDER BY WhseDescription
    """)
    warehouses = cur.fetchall()

    # Suppliers
    cur.execute("""
        SELECT DCLink SupplierLink, Name SupplierName
        FROM cmn._uvSuppliers
        ORDER BY SupplierName
    """)
    suppliers = cur.fetchall()

    # Units of measure (stocking units only)
    cur.execute("""
        SELECT DISTINCT UOM.idUnits, UOM.cUnitCode, UOM.iUnitCategoryID
        FROM cmn._uvUOM UOM
        WHERE UOM.cUnitCode IN ('L','Kg')
        ORDER BY UOM.cUnitCode
    """)
    uoms = cur.fetchall()

    # Crops
    cur.execute("""
        SELECT IdCrop, CropCode, CropDescription
        FROM agr.Crop
        ORDER BY CropCode
    """)
    crops = cur.fetchall()

    # Active ingredients
    cur.execute("""
        SELECT IdChemAct, ChemActIngredient
        FROM agr.ChemActiveIngredient
        ORDER BY ChemActIngredient
    """)
    active_ings = cur.fetchall()

    cur.execute("""
        Select Distinct idGrpTbl, Description
        from [agr].[ChemStock] STK
        JOIN cmn._uvStockGroups GRP on GRP.idGrpTbl = ChemStockGroupId
        ORDER BY Description
    """)
    groups = cur.fetchall()

    # categories
    cur.execute("""
    Select idStockCategories, cCategoryName
    from [cmn].[_uvCategories]
    ORDER BY cCategoryName
    """)
    categories = cur.fetchall()

    # colour codes
    cur.execute("""
        SELECT IdChemCol, ChemColCode
        FROM agr.ChemColour
        ORDER BY ChemColCode
    """)
    colour_codes = cur.fetchall()

    # types
    cur.execute("""
        Select Distinct StkCrpType
        from agr.ChemStockCrop
    """)
    types = cur.fetchall()
    close_db_connection(conn, cur)


    return render_template(
        'new_product.html',
        warehouses=warehouses,
        suppliers=suppliers,
        uoms=uoms,
        crops=crops,
        active_ings=active_ings,
        groups=groups,
        categories=categories,
        colour_codes=colour_codes,
        types=types,
        csrf_token=_product_csrf_token()
    )


@agri_bp.route('/product/labels/search', methods=['GET'])
@login_required
def search_standardized_labels():
    search_term = (request.args.get('q') or '').strip()
    if len(search_term) < 2:
        return jsonify({'success': True, 'labels': []})

    conn = None
    cur = None
    try:
        conn = create_db_connection(database_name=LABELS_DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("""
            SELECT TOP (25) IdLabel, TradeName, RegNumber
            FROM dbo.Labels
            WHERE TradeName LIKE ? OR RegNumber LIKE ?
            ORDER BY TradeName, IdLabel
        """, (f'%{search_term}%', f'%{search_term}%'))
        labels = [
            {'id': row[0], 'trade_name': row[1], 'registration_number': row[2]}
            for row in cur.fetchall()
        ]
        return jsonify({'success': True, 'labels': labels})
    except Exception:
        current_app.logger.exception('Unable to search standardized labels')
        return jsonify({'success': False, 'message': 'Unable to search standardized products.'}), 500
    finally:
        close_db_connection(conn, cur)


@agri_bp.route('/product/labels/<int:label_id>', methods=['GET'])
@login_required
def get_standardized_label(label_id):
    conn = None
    cur = None
    try:
        conn = create_db_connection(database_name=LABELS_DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("""
            SELECT L.IdLabel, L.TradeName, L.RegNumber, C.ColCode
            FROM dbo.Labels L
            LEFT JOIN dbo.Colour C ON C.IdColour = L.ColourCodeId
            WHERE L.IdLabel = ?
        """, (label_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Standardized product not found.'}), 404

        label = {
            'id': row[0],
            'trade_name': row[1],
            'registration_number': row[2],
            'colour_code': row[3],
        }

        cur.execute("""
            SELECT AI.ActiveIngredientName
            FROM dbo.LabelActiveIngredients LAI
            JOIN dbo.ActiveIngredients AI ON AI.IdActiveIngredient = LAI.ActiveIngredientId
            WHERE LAI.LabelId = ?
            ORDER BY AI.ActiveIngredientName
        """, (label_id,))
        active_ingredients = [ingredient[0] for ingredient in cur.fetchall()]

        cur.execute("""
            SELECT IdLabelCrops, [Crop], [Target], Category, [Type],
                   PHISA, PHIEU, PHIGB, PHIUSA, PHIRussia, PHICodex,
                   PHICanada, PHIJapan, PHIKorea, PHIIndo, PHIChina, PHIMalaysia
            FROM dbo.LabelCrops
            WHERE LabelId = ?
            ORDER BY [Crop], IdLabelCrops
        """, (label_id,))
        crop_columns = [column[0] for column in cur.description]
        crops = [dict(zip(crop_columns, crop)) for crop in cur.fetchall()]

        return jsonify({
            'success': True,
            'label': label,
            'active_ingredients': active_ingredients,
            'crops': crops,
        })
    except Exception:
        current_app.logger.exception('Unable to load standardized label %s', label_id)
        return jsonify({'success': False, 'message': 'Unable to load standardized product details.'}), 500
    finally:
        close_db_connection(conn, cur)


@agri_bp.route('/product/purchasing-units', methods=['GET'])
@login_required
def purchasing_units():
    stocking_unit_id = request.args.get('stocking_unit_id')
    if not stocking_unit_id:
        return jsonify({'units': []})

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT iUnitCategoryID
        FROM cmn._uvUOM
        WHERE idUnits = ?
    """, (stocking_unit_id,))
    row = cur.fetchone()
    if not row:
        close_db_connection(conn)
        return jsonify({'units': []})

    unit_category_id = row[0]
    cur.execute("""
        SELECT idUnits, cUnitCode
        FROM cmn._uvUOM
        WHERE iUnitCategoryID = ?
        ORDER BY cUnitCode
    """, (unit_category_id,))
    units = [{'id': r[0], 'code': r[1]} for r in cur.fetchall()]
    close_db_connection(conn)
    return jsonify({'units': units})


@agri_bp.route('/product/active-ingredients', methods=['GET'])
@login_required
def list_active_ingredients():
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdChemAct, ChemActIngredient
        FROM agr.ChemActiveIngredient
        ORDER BY ChemActIngredient
    """)
    options = [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]
    close_db_connection(conn)
    return jsonify({'active_ingredients': options})


@agri_bp.route('/product/colour-codes', methods=['GET'])
@login_required
def list_colour_codes():
    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdChemCol, ChemColCode
        FROM agr.ChemColour
        ORDER BY ChemColCode
    """)
    options = [{'id': r[0], 'code': r[1]} for r in cur.fetchall()]
    close_db_connection(conn)
    return jsonify({'colour_codes': options})


@agri_bp.route('/product/active-ingredient', methods=['POST'])
@login_required
def create_active_ingredient():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Invalid active ingredient details.'}), 400
    if not _valid_product_csrf(data):
        return jsonify({'success': False, 'message': 'Your session token has expired. Reload the page and try again.'}), 400
    value = data.get('value')
    if not isinstance(value, str):
        value = ''
    value = value.strip()
    if not value:
        return jsonify({'success': False, 'message': 'Active ingredient name is required.'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdChemAct
        FROM agr.ChemActiveIngredient
        WHERE ChemActIngredient = ?
    """, (value,))
    existing = cur.fetchone()
    if existing:
        active_id = existing[0]
    else:
        cur.execute("""
            INSERT INTO agr.ChemActiveIngredient (ChemActIngredient)
            VALUES (?)
        """, (value,))
        conn.commit()
        cur.execute("""
            SELECT IdChemAct
            FROM agr.ChemActiveIngredient
            WHERE ChemActIngredient = ?
        """, (value,))
        active_id = cur.fetchone()[0]
    close_db_connection(conn)
    return jsonify({'success': True, 'id': active_id, 'name': value})


@agri_bp.route('/product/colour-code', methods=['POST'])
@login_required
def create_colour_code():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Invalid colour code details.'}), 400
    if not _valid_product_csrf(data):
        return jsonify({'success': False, 'message': 'Your session token has expired. Reload the page and try again.'}), 400
    value = data.get('value')
    if not isinstance(value, str):
        value = ''
    value = value.strip()
    if not value:
        return jsonify({'success': False, 'message': 'Colour code is required.'}), 400

    conn = create_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT IdChemCol
        FROM agr.ChemColour
        WHERE ChemColCode = ?
    """, (value,))
    existing = cur.fetchone()
    if existing:
        colour_id = existing[0]
    else:
        cur.execute("""
            INSERT INTO agr.ChemColour (ChemColCode)
            VALUES (?)
        """, (value,))
        conn.commit()
        cur.execute("""
            SELECT IdChemCol
            FROM agr.ChemColour
            WHERE ChemColCode = ?
        """, (value,))
        colour_id = cur.fetchone()[0]
    close_db_connection(conn)
    return jsonify({'success': True, 'id': colour_id, 'code': value})


@agri_bp.route('/product/check-duplicate', methods=['GET'])
@login_required
def check_duplicate_product():
    product_code = (request.args.get('product_code') or '').strip()
    brand_name = (request.args.get('brand_name') or '').strip()
    registration_number = (request.args.get('registration_number') or '').strip()
    if not product_code and not brand_name and not registration_number:
        return jsonify({"exists_code": False, "exists_brand": False, "exists_registration": False})

    conn = create_db_connection()
    cur = conn.cursor()
    conditions = []
    params = []
    if product_code:
        conditions.append('LOWER(StockCode) = ?')
        params.append(product_code.lower())
    if brand_name:
        conditions.append('LOWER(StockDescription) = ?')
        params.append(brand_name.lower())

    exists_code = False
    exists_brand = False
    if conditions:
        cur.execute(f"SELECT StockCode, StockDescription FROM cmn._uvStockItems WHERE {' OR '.join(conditions)}", params)
        for row in cur.fetchall():
            if product_code and (row[0] or '').casefold() == product_code.casefold():
                exists_code = True
            if brand_name and (row[1] or '').casefold() == brand_name.casefold():
                exists_brand = True

    exists_registration = False
    if registration_number:
        cur.execute("""
            SELECT TOP 1 IdChemStock
            FROM agr.ChemStock
            WHERE LOWER(ChemStockRegNumber) = ?
        """, (registration_number.casefold(),))
        exists_registration = cur.fetchone() is not None

    close_db_connection(conn, cur)
    return jsonify({
        "exists_code": exists_code,
        "exists_brand": exists_brand,
        "exists_registration": exists_registration
    })


@agri_bp.route('/product/duplicate-search', methods=['GET'])
@login_required
def duplicate_search():
    """Return aggregated product similarity suggestions (one row per product).
    Produces supplier/warehouse/crop counts and a simple similarity score/classification.
    """
    brand = (request.args.get('brand_name') or '').strip()
    product_code = (request.args.get('product_code') or '').strip()
    active_ing_values = request.args.getlist('active_ing')
    try:
        active_ing_ids = list(dict.fromkeys(int(value) for value in active_ing_values if value))
    except ValueError:
        return jsonify({'error': 'active_ing must contain ingredient IDs'}), 400
    registration = (request.args.get('registration') or '').strip()

    lower_brand = brand.lower()
    search_term = f"%{lower_brand.replace(' ', '%')}%" if lower_brand else None

    conn = create_db_connection()
    cur = conn.cursor()

    candidates = []

    if search_term:
        cur.execute("""
            SELECT DISTINCT TOP 50
                s.StockLink,
                s.StockCode,
                s.StockDescription,
        act.ChemActIngredient,
                MIN(st.ChemStockRegNumber) as SampleReg
            FROM cmn._uvStockItems s
            JOIN agr.ChemStock st ON st.ChemStockLink = s.StockLink
            LEFT JOIN (
                SELECT CSAI.CSAIChemStockId,
                       STRING_AGG(ACT.ChemActIngredient, ' + ') WITHIN GROUP (ORDER BY ACT.ChemActIngredient) AS ChemActIngredient
                FROM agr.ChemStockActiveIngredient CSAI
                JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = CSAI.CSAIActiveIngredientId
                GROUP BY CSAI.CSAIChemStockId
            ) act ON act.CSAIChemStockId = st.IdChemStock
            LEFT JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
            WHERE LOWER(s.StockDescription) LIKE ?
               OR LOWER(s.StockCode) LIKE ?
               OR LOWER(act.ChemActIngredient) LIKE ?
               OR LOWER(st.ChemStockRegNumber) LIKE ?
            GROUP BY s.StockLink, s.StockCode, s.StockDescription, act.ChemActIngredient
            ORDER BY s.StockDescription
        """, (search_term, search_term, search_term, search_term))
        cols = [c[0] for c in cur.description]
        for r in cur.fetchall():
            rd = dict(zip(cols, r))
            candidates.append({
                'stock_link': rd['StockLink'],
                'product_code': rd['StockCode'],
                'product_description': rd['StockDescription'],
                'active_ingredient': rd.get('ChemActIngredient'),
                'sample_registration': rd.get('SampleReg'),
                'active_ingredient_match': False
            })

    code_registration_conditions = []
    code_registration_params = []
    if product_code:
        code_registration_conditions.append('LOWER(s.StockCode) LIKE ?')
        code_registration_params.append(f"%{product_code.casefold()}%")
    if registration:
        code_registration_conditions.append('LOWER(st.ChemStockRegNumber) LIKE ?')
        code_registration_params.append(f"%{registration.casefold()}%")
    if code_registration_conditions:
        cur.execute(f"""
            SELECT DISTINCT TOP 50
                s.StockLink,
                s.StockCode,
                s.StockDescription,
                act.ChemActIngredient,
                MIN(st.ChemStockRegNumber) as SampleReg
            FROM cmn._uvStockItems s
            JOIN agr.ChemStock st ON st.ChemStockLink = s.StockLink
            LEFT JOIN (
                SELECT CSAI.CSAIChemStockId,
                       STRING_AGG(ACT.ChemActIngredient, ' + ') WITHIN GROUP (ORDER BY ACT.ChemActIngredient) AS ChemActIngredient
                FROM agr.ChemStockActiveIngredient CSAI
                JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = CSAI.CSAIActiveIngredientId
                GROUP BY CSAI.CSAIChemStockId
            ) act ON act.CSAIChemStockId = st.IdChemStock
            WHERE {' OR '.join(code_registration_conditions)}
            GROUP BY s.StockLink, s.StockCode, s.StockDescription, act.ChemActIngredient
            ORDER BY s.StockDescription
        """, code_registration_params)
        cols = [c[0] for c in cur.description]
        for r in cur.fetchall():
            rd = dict(zip(cols, r))
            candidates.append({
                'stock_link': rd['StockLink'],
                'product_code': rd['StockCode'],
                'product_description': rd['StockDescription'],
                'active_ingredient': rd.get('ChemActIngredient'),
                'sample_registration': rd.get('SampleReg'),
                'active_ingredient_match': False
            })

    # Search by any selected active ingredient.
    if active_ing_ids:
        active_ing_placeholders = ','.join('?' for _ in active_ing_ids)
        cur.execute(f"""
            SELECT DISTINCT TOP 50
                s.StockLink,
                s.StockCode,
                s.StockDescription,
                act.ChemActIngredient,
                MIN(st.ChemStockRegNumber) as SampleReg
            FROM cmn._uvStockItems s
            JOIN agr.ChemStock st ON st.ChemStockLink = s.StockLink
            LEFT JOIN (
                SELECT CSAI.CSAIChemStockId,
                       STRING_AGG(ACT.ChemActIngredient, ' + ') WITHIN GROUP (ORDER BY ACT.ChemActIngredient) AS ChemActIngredient
                FROM agr.ChemStockActiveIngredient CSAI
                JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = CSAI.CSAIActiveIngredientId
                GROUP BY CSAI.CSAIChemStockId
            ) act ON act.CSAIChemStockId = st.IdChemStock
            LEFT JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
            WHERE EXISTS (
                SELECT 1
                FROM agr.ChemStockActiveIngredient CSAI
                WHERE CSAI.CSAIChemStockId = st.IdChemStock
                  AND CSAI.CSAIActiveIngredientId IN ({active_ing_placeholders})
            )
            GROUP BY s.StockLink, s.StockCode, s.StockDescription, act.ChemActIngredient
            ORDER BY s.StockDescription
        """, active_ing_ids)
        cols = [c[0] for c in cur.description]
        for r in cur.fetchall():
            rd = dict(zip(cols, r))
            candidates.append({
                'stock_link': rd['StockLink'],
                'product_code': rd['StockCode'],
                'product_description': rd['StockDescription'],
                'active_ingredient': rd.get('ChemActIngredient'),
                'sample_registration': rd.get('SampleReg'),
                'active_ingredient_match': True
            })

    unique_candidates = {}
    for candidate in candidates:
        stock_link = candidate['stock_link']
        if stock_link not in unique_candidates:
            unique_candidates[stock_link] = candidate
        else:
            unique_candidates[stock_link]['active_ingredient_match'] = (
                unique_candidates[stock_link]['active_ingredient_match'] or candidate['active_ingredient_match']
            )

    # For each candidate, fetch counts and compute a simple similarity score
    results = []
    for c in unique_candidates.values():
        sid = c['stock_link']
        # supplier count
        cur.execute("SELECT COUNT(DISTINCT iDCLink) FROM [stk].[_uvStockLinks] WHERE iStockID = ?", (sid,))
        supplier_count = cur.fetchone()[0] or 0
        # warehouse count
        cur.execute("SELECT COUNT(DISTINCT WhseID) FROM cmn._uvStockWarehouse WHERE StockID = ?", (sid,))
        warehouse_count = cur.fetchone()[0] or 0
        # crop/registration count
        cur.execute("SELECT COUNT(DISTINCT StkCrpCropId) FROM agr.ChemStockCrop crp JOIN agr.ChemStock st ON st.IdChemStock = crp.StkCrpChemStockId WHERE st.ChemStockLink = ?", (sid,))
        crop_count = cur.fetchone()[0] or 0

        # similarity scoring (simple rule-based)
        score = 0
        desc = (c.get('product_description') or '').lower()
        pcode = (c.get('product_code') or '').lower()
        a_ing = (c.get('active_ingredient') or '')
        sample_reg = (c.get('sample_registration') or '')

        if product_code and pcode == product_code.casefold():
            score += 60
        if brand and pcode == brand.lower():
            score += 50
        if c.get('active_ingredient_match') and a_ing:
            score += 25
        if brand and brand.lower() in desc:
            score += 20
        if registration and sample_reg and registration.lower() == sample_reg.lower():
            score += 50

        # small bonus for having registrations/suppliers/warehouses
        if sample_reg:
            score += 5
        score += min(supplier_count, 5)  # small weight

        if product_code and pcode == product_code.casefold():
            classification = 'exact'
        elif pcode == brand.lower():
            classification = 'exact'
        elif score >= 70:
            classification = 'probable'
        elif score >= 40:
            classification = 'similar'
        else:
            classification = 'other'

        results.append({
            'stock_link': sid,
            'product_code': c.get('product_code'),
            'product_description': c.get('product_description'),
            'active_ingredient': c.get('active_ingredient'),
            'sample_registration': c.get('sample_registration'),
            'supplier_count': supplier_count,
            'warehouse_count': warehouse_count,
            'crop_count': crop_count,
            'score': int(score),
            'classification': classification
        })

    # sort by score desc
    results.sort(key=lambda x: x.get('score', 0), reverse=True)

    close_db_connection(conn)
    return jsonify({'results': results})


@agri_bp.route('/product/details', methods=['GET'])
@login_required
def product_details():
    stock_link_value = request.args.get('stock_link')
    if not stock_link_value:
        return jsonify({'error': 'stock_link required'}), 400
    try:
        stock_link = int(stock_link_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'stock_link must be an integer'}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT st.ChemStockLink, st.ChemStockCode, st.ChemStockName, st.ChemStockRegNumber,
        act.ChemActIngredient,
        st.ChemStockGroupId, st.ChemStockColourCodeId,
		st.ChemStockStockingUnitId, st.ChemStockPurchasingUnitId, clr.ChemColCode
        FROM agr.ChemStock st
        LEFT JOIN agr.ChemColour clr ON clr.IdChemCol = st.ChemStockColourCodeId
        LEFT JOIN (
            SELECT CSAI.CSAIChemStockId,
                   STRING_AGG(ACT.ChemActIngredient, ' + ') WITHIN GROUP (ORDER BY ACT.ChemActIngredient) AS ChemActIngredient
            FROM agr.ChemStockActiveIngredient CSAI
            JOIN agr.ChemActiveIngredient ACT ON ACT.IdChemAct = CSAI.CSAIActiveIngredientId
            GROUP BY CSAI.CSAIChemStockId
        ) act ON act.CSAIChemStockId = st.IdChemStock
        WHERE st.ChemStockLink = ?
    """, (stock_link,))
    row = cur.fetchone()
    if not row:
        close_db_connection(conn)
        return jsonify({'error': 'not found'}), 404

    cur.execute("""
        SELECT CSAIActiveIngredientId
        FROM agr.ChemStockActiveIngredient
        WHERE CSAIChemStockId = (
            SELECT IdChemStock FROM agr.ChemStock WHERE ChemStockLink = ?
        )
        ORDER BY CSAIActiveIngredientId
    """, (stock_link,))
    active_ing_ids = [r[0] for r in cur.fetchall()]

    product = {
        'stock_link': row[0],
        'product_code': row[1],
        'product_description': row[2],
        'registration_number': row[3],
        'active_ingredient_id': active_ing_ids[0] if active_ing_ids else None,
        'active_ingredient_ids': active_ing_ids,
        'active_ingredient': row[4],
        'group_id': row[5],
        'colour_code_id': row[6],
        'stocking_unit_id': row[7],
        'purchasing_unit_id': row[8],
        'colour_code': row[9]
    }

    # suppliers
    cur.execute("""
        SELECT DISTINCT
            sup.DCLink,
            sup.Name,
            COALESCE(LST.fUnitPriceExcl, GRV.PurchaseUnitLastGRVCost) AS Price,
            COALESCE(LST.iUnitsOfMeasureID, GRV.iUOMDefPurchaseUnitID) AS PriceUnitId,
            sp.bDefaultSupplier
        FROM stk._uvStockLinks sp
        LEFT JOIN stk._uvLastSupplierInvoicePrice LST
            ON LST.AccountID = sp.iDCLink
           AND LST.iStockCodeID = sp.iStockID
        LEFT JOIN cmn._uvLastGRVCost GRV
            ON GRV.iDCLink = sp.iDCLink
           AND GRV.StockLink = sp.iStockID
        JOIN cmn._uvSuppliers sup ON sup.DCLink = sp.iDCLink
        WHERE sp.iStockID = ?
        ORDER BY sp.bDefaultSupplier DESC, sup.Name
    """, (stock_link,))
    suppliers = [{
        'id': r[0],
        'name': r[1],
        'price': float(r[2]) if r[2] is not None else None,
        'price_unit_id': r[3],
        'is_default': bool(r[4])
    } for r in cur.fetchall()]

    # warehouses
    cur.execute("""
		Select Distinct QTY.WhseLink, QTY.WhseName, cCategoryName, idStockCategories
		from stk._uvInventoryQty QTY
		Where StockLink = ?
    """, (stock_link,))
    warehouses = [{'id': r[0], 'description': r[1], 'category_name': r[2], 'category_id': r[3]} for r in cur.fetchall()]

    # crop registrations
    cur.execute("""
        SELECT crp.StkCrpCropId, crp.StkCrpType, crp.StkCrpWitholdingPeriodDef, crp.StkCrpFunctionDef, c.IdCrop, c.CropCode, c.CropDescription
        FROM agr.ChemStock st
        JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
        LEFT JOIN agr.Crop c ON c.IdCrop = crp.StkCrpCropId
        WHERE st.ChemStockLink = ?
    """, (stock_link,))
    regs = []
    for r in cur.fetchall():
        regs.append({
            'id': r[0],
            'type': r[1],
            'withholding_period': r[2],
            'function': r[3],
            'crop_id': r[4],
            'crop_code': r[5],
            'crop_description': r[6]
        })

    close_db_connection(conn)
    return jsonify({'product': product, 'suppliers': suppliers, 'warehouses': warehouses, 'registrations': regs})
