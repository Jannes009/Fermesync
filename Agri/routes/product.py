from flask import render_template, request, redirect, url_for, jsonify
from flask_login import login_required
from Core.auth import create_db_connection, close_db_connection
from . import agri_bp
import json


@agri_bp.route('/product/new', methods=['GET', 'POST'])
@login_required
def new_product():
    # POST: accept JSON or form and simply print posted data for now
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            # fallback to form data
            data = request.form.to_dict(flat=False)

        brand_name = (data.get('brand_name') or '').strip()
        product_code = (data.get('product_code') or '').strip()
        group_name = (data.get('group_name') or data.get('group') or '').strip()

        if not product_code and group_name and brand_name:
            prefix = group_name[:3].upper()
            safe_brand = '_'.join(brand_name.split())
            product_code = f"{prefix}-{safe_brand}"
            data['product_code'] = product_code

        errors = []
        if not brand_name:
            errors.append('Brand name is required.')
        elif len(brand_name) > 50:
            errors.append('Brand name cannot be longer than 50 characters.')

        if not product_code:
            errors.append('Product code is required.')
        elif len(product_code) > 20:
            errors.append('Product code cannot be longer than 20 characters.')

        if not data.get('group'):
            errors.append('Group is required.')
        if not data.get('active_ing'):
            errors.append('Active ingredient is required.')
        if not data.get('colour_code'):
            errors.append('Colour code is required.')
        if not data.get('stocking_unit'):
            errors.append('Stocking unit is required.')
        if not data.get('purchasing_unit'):
            errors.append('Purchasing unit is required.')

        warehouses_payload = data.get('warehouses') or []
        for warehouse in warehouses_payload:
            if warehouse.get('id') and not str(warehouse.get('shelf') or '').strip():
                errors.append('Each linked warehouse must have a selected shelf.')
                break

        suppliers_payload = data.get('suppliers') or []
        for supplier in suppliers_payload:
            if supplier.get('id') and not str(supplier.get('price') or '').strip():
                errors.append('Each selected supplier must have a price.')
                break

        chemstockcrop_payload = data.get('chemstockcrop') or []
        if not chemstockcrop_payload:
            errors.append('At least one stock crop must be added.')

        if errors:
            return jsonify({"success": False, "message": errors[0], "errors": errors}), 400

        conn = create_db_connection()
        cur = conn.cursor()
        duplicate_exists = False
        duplicate_brand_exists = False
        if product_code or brand_name:
            query = []
            params = []
            if product_code:
                query.append('LOWER(StockCode) = ?')
                params.append(product_code.lower())
            if brand_name:
                query.append('LOWER(StockDescription) = ?')
                params.append(brand_name.lower())
            cur.execute(f"SELECT StockCode, StockDescription FROM cmn._uvStockItems WHERE {' OR '.join(query)}", params)
            for row in cur.fetchall():
                if product_code and row[0] and row[0].lower() == product_code.lower():
                    duplicate_exists = True
                if brand_name and row[1] and row[1].lower() == brand_name.lower():
                    duplicate_brand_exists = True
                if duplicate_exists and duplicate_brand_exists:
                    break

        if duplicate_exists or duplicate_brand_exists:
            close_db_connection(conn)
            message = 'A product with that '
            if duplicate_exists and duplicate_brand_exists:
                message += 'brand name and code already exists.'
            elif duplicate_exists:
                message += 'code already exists.'
            else:
                message += 'brand name already exists.'
            return jsonify({
                "success": False,
                "message": message
            }), 400

        if duplicate_exists:
            close_db_connection(conn)
            return jsonify({
                "success": False,
                "message": "A product with that code already exists. Please choose a different code."
            }), 400

        def extract_value(value):
            if isinstance(value, list):
                return value[0] if value else None
            return value

        group_id = extract_value(data.get('group'))
        active_ing_id = extract_value(data.get('active_ing'))
        colour_code_id = extract_value(data.get('colour_code'))
        stocking_unit_id = extract_value(data.get('stocking_unit'))
        purchasing_unit_id = extract_value(data.get('purchasing_unit'))

        try:
            cur.execute("""
                INSERT INTO agr.ChemStock
                    (ChemStockCode, ChemStockName,
                     ChemStockActiveIngrId, ChemStockGroupId,
                     ChemStockColourCodeId, ChemStockStockingUnitId,
                     ChemStockPurchasingUnitId)
                OUTPUT INSERTED.IdChemStock
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                product_code,
                brand_name,
                active_ing_id,
                group_id,
                colour_code_id,
                stocking_unit_id,
                purchasing_unit_id
            ))
            chem_stock_id = cur.fetchone()[0]

            for crop_entry in chemstockcrop_payload:
                crop_id = extract_value(crop_entry.get('crop'))
                reg_number = (extract_value(crop_entry.get('registration_number')) or '').strip()
                withh_period = (extract_value(crop_entry.get('withholding_period')) or '').strip()
                reg_type = (extract_value(crop_entry.get('type')) or '').strip()
                func = (extract_value(crop_entry.get('func')) or '').strip()

                cur.execute("""
                    INSERT INTO agr.ChemStockCrop
                        (StkCrpChemStockId, StkCrpCropId, StkCrpRegNumber,
                         StkCrpType, StkCrpWitholdingPeriodDef, StkCrpFunctionDef)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    chem_stock_id,
                    crop_id,
                    reg_number,
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

            stock_id = cur.fetchone()[0]

            for warehouse_entry in warehouses_payload:
                whse_id = extract_value(warehouse_entry.get('id'))
                category_id = extract_value(warehouse_entry.get('shelf'))
                print(whse_id, category_id)
                cur.execute("""
                    EXEC [stk].[sp_UpdateCategoryAndReordering] 
                        @StockId = ?, 
                        @WarehouseId = ?, 
                        @Category = ?;
                """, (stock_id, whse_id, category_id))

            for supplier_entry in suppliers_payload:
                supplier_id = extract_value(supplier_entry.get('id'))
                price = extract_value(supplier_entry.get('price'))
                is_default = extract_value(supplier_entry.get('is_default'))
                print(supplier_id, price, is_default)
                cur.execute("""
                    EXEC [cmn].[sp_StockSupplier_Save]
                                @StockId = ?, 
                                @SupplierID = ?, 
                                @IsDefaultSupplier = ?,
                                @LastGRVCost = ?;
                """, (stock_id, supplier_id, is_default, price))
            conn.commit()
        except Exception as e:
            conn.rollback()
            close_db_connection(conn)
            print("Error inserting ChemStock/ChemStockCrop:", e)
            return jsonify({
                "success": False,
                "message": "Failed to save chemical product details."
            }), 500

        close_db_connection(conn)

        try:
            print("--- New product posted data ---")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error printing posted product data:", e)

        # Return JSON so AJAX flows get a friendly response
        return jsonify({"success": True, "product_code": product_code})

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
    conn.close()


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
        types=types
    )


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
    data = request.get_json(silent=True) or {}
    value = (data.get('value') or '').strip()
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
    data = request.get_json(silent=True) or {}
    value = (data.get('value') or '').strip()
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
    if not product_code and not brand_name:
        return jsonify({"exists_code": False, "exists_brand": False})

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

    cur.execute(f"SELECT StockCode, StockDescription FROM cmn._uvStockItems WHERE {' OR '.join(conditions)}", params)
    row = cur.fetchone()
    exists_code = False
    exists_brand = False
    if row:
        if product_code and row[0].lower() == product_code.lower():
            exists_code = True
        if brand_name and row[1].lower() == brand_name.lower():
            exists_brand = True

    close_db_connection(conn)
    return jsonify({"exists_code": exists_code, "exists_brand": exists_brand})


@agri_bp.route('/product/duplicate-search', methods=['GET'])
@login_required
def duplicate_search():
    """Return aggregated product similarity suggestions (one row per product).
    Produces supplier/warehouse/crop counts and a simple similarity score/classification.
    """
    brand = (request.args.get('brand_name') or '').strip()
    active_ing = (request.args.get('active_ing') or '').strip()
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
                MIN(crp.StkCrpRegNumber) as SampleReg
            FROM cmn._uvStockItems s
            JOIN agr.ChemStock st ON st.ChemStockLink = s.StockLink
            LEFT JOIN agr.ChemActiveIngredient act ON act.IdChemAct = st.ChemStockActiveIngrId
            LEFT JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
            WHERE LOWER(s.StockDescription) LIKE ?
               OR LOWER(s.StockCode) LIKE ?
               OR LOWER(act.ChemActIngredient) LIKE ?
               OR LOWER(crp.StkCrpRegNumber) LIKE ?
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
                'sample_registration': rd.get('SampleReg')
            })

    # If active ingredient filter provided but no brand, search by active ingredient
    if active_ing:
        cur.execute("""
            SELECT DISTINCT TOP 50
                s.StockLink,
                s.StockCode,
                s.StockDescription,
                act.ChemActIngredient,
                MIN(crp.StkCrpRegNumber) as SampleReg
            FROM cmn._uvStockItems s
            JOIN agr.ChemStock st ON st.ChemStockLink = s.StockLink
            JOIN agr.ChemActiveIngredient act ON act.IdChemAct = st.ChemStockActiveIngrId
            LEFT JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
            WHERE st.ChemStockActiveIngrId = ?
            GROUP BY s.StockLink, s.StockCode, s.StockDescription, act.ChemActIngredient
            ORDER BY s.StockDescription
        """, (active_ing,))
        cols = [c[0] for c in cur.description]
        for r in cur.fetchall():
            rd = dict(zip(cols, r))
            candidates.append({
                'stock_link': rd['StockLink'],
                'product_code': rd['StockCode'],
                'product_description': rd['StockDescription'],
                'active_ingredient': rd.get('ChemActIngredient'),
                'sample_registration': rd.get('SampleReg')
            })

    # For each candidate, fetch counts and compute a simple similarity score
    results = []
    for c in candidates:
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

        if brand and pcode == brand.lower():
            score += 50
        if active_ing and a_ing and active_ing.lower() == a_ing.lower():
            score += 25
        if brand and brand.lower() in desc:
            score += 20
        if registration and sample_reg and registration.lower() == sample_reg.lower():
            score += 50

        # small bonus for having registrations/suppliers/warehouses
        if sample_reg:
            score += 5
        score += min(supplier_count, 5)  # small weight

        if pcode == brand.lower():
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
    stock_link = request.args.get('stock_link')
    if not stock_link:
        return jsonify({'error': 'stock_link required'}), 400

    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT st.ChemStockLink, st.ChemStockCode, st.ChemStockName, 
		act.IdChemAct AS active_ing_id, act.ChemActIngredient, 
		st.ChemStockGroupId, st.ChemStockColourCodeId,
		st.ChemStockStockingUnitId, st.ChemStockPurchasingUnitId
        FROM agr.ChemStock st
        LEFT JOIN agr.ChemActiveIngredient act ON act.IdChemAct = st.ChemStockActiveIngrId
        WHERE st.ChemStockLink = ?
    """, (stock_link,))
    row = cur.fetchone()
    if not row:
        close_db_connection(conn)
        return jsonify({'error': 'not found'}), 404

    product = {
        'stock_link': row[0],
        'product_code': row[1],
        'product_description': row[2],
        'active_ingredient_id': row[3],
        'active_ingredient': row[4],
        'group_id': row[5],
        'colour_code_id': row[6],
        'stocking_unit_id': row[7],
        'purchasing_unit_id': row[8]
    }

    # suppliers
    cur.execute("""
        SELECT DISTINCT sup.DCLink, sup.Name
        FROM [stk].[_uvStockLinks] sp
        JOIN cmn._uvSuppliers sup ON sup.DCLink = sp.iDCLink
        WHERE sp.iStockID = ?
    """, (stock_link,))
    suppliers = [{'id': r[0], 'name': r[1]} for r in cur.fetchall()]

    # warehouses
    cur.execute("""
		Select Distinct QTY.WhseLink, QTY.WhseName, cCategoryName, idStockCategories
		from stk._uvInventoryQty QTY
		Where StockLink = ?
    """, (stock_link,))
    warehouses = [{'id': r[0], 'description': r[1], 'category_name': r[2], 'category_id': r[3]} for r in cur.fetchall()]

    # crop registrations
    cur.execute("""
        SELECT crp.StkCrpCropId, crp.StkCrpRegNumber, crp.StkCrpType, crp.StkCrpWitholdingPeriodDef, crp.StkCrpFunctionDef, c.IdCrop, c.CropCode, c.CropDescription
        FROM agr.ChemStock st
        JOIN agr.ChemStockCrop crp ON crp.StkCrpChemStockId = st.IdChemStock
        LEFT JOIN agr.Crop c ON c.IdCrop = crp.StkCrpCropId
        WHERE st.ChemStockLink = ?
    """, (stock_link,))
    regs = []
    for r in cur.fetchall():
        regs.append({
            'id': r[0],
            'registration_number': r[1],
            'type': r[2],
            'withholding_period': r[3],
            'function': r[4],
            'crop_id': r[5],
            'crop_code': r[6],
            'crop_description': r[7]
        })

    close_db_connection(conn)
    return jsonify({'product': product, 'suppliers': suppliers, 'warehouses': warehouses, 'registrations': regs})
