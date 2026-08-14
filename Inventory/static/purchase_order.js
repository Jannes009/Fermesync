const supplierFieldRoot = document.getElementById('supplier-field');
const warehouseFieldRoot = document.getElementById('warehouse-field');
const descriptionInput = document.getElementById('description');
const linesBody = document.getElementById('lines-body');
const addLineBtn = document.getElementById('add-line-btn');
const saveBtn = document.getElementById('save-btn');
const lineCount = document.getElementById('line-count');
const orderTax = document.getElementById('order-tax');
const orderTotal = document.getElementById('order-total');

let products = [];

const formatCurrency = value => {
    return 'R ' + Number(value || 0).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

const escapeHtml = string => {
    return String(string || '').replace(/[&<>\"]+/g, tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;'
    })[tag]);
};

const fetchJson = async url => {
    const response = await request(url);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'Request failed');
    }
    return response.json();
};

const closeAllDropdowns = () => {
    document.querySelectorAll('.searchable-field.open').forEach(field => {
        field.classList.remove('open');
        const dd = field._dropdownEl || field.querySelector('.dropdown-list');
        if (dd) dd.classList.add('hidden');
    });
};

document.addEventListener('click', event => {
    if (!event.target.closest('.searchable-field')) {
        closeAllDropdowns();
    }
});

const createSelect2Field = (selectEl, placeholder, onSelect = () => {}) => {
    const $sel = $(selectEl);
    let optionsCache = [];
    let currentPlaceholder = placeholder || '';
    let initialized = false;

    const optionMarkup = data => {
        if (!data.id || data.loading) {
            return escapeHtml(data.text || '');
        }
        return data.html || escapeHtml(data.text || '');
    };

    const initSelect2 = () => {
        if (initialized) {
            try {
                $sel.select2('destroy');
            } catch (e) {
                // ignore
            }
        }

        $sel.empty();
        $sel.select2({
            data: optionsCache,
            placeholder: currentPlaceholder,
            width: 'resolve',
            dropdownParent: $(document.body),
            allowClear: false,
            escapeMarkup: markup => markup,
            templateResult: optionMarkup,
            templateSelection: optionMarkup
        });

        $sel.off('.select2wrapper');
        $sel.on('select2:select.select2wrapper', function (e) {
            const data = e.params.data;
            onSelect({ value: data.id, label: data.text, data });
        });

        $sel.on('select2:open.select2wrapper', () => {
            const search = document.querySelector('.select2-container--open .select2-search__field');
            if (search) search.focus();
        });

        initialized = true;
    };

    const setOptions = newOptions => {
        optionsCache = Array.isArray(newOptions)
            ? newOptions.map(opt => ({
                ...opt,
                id: String(opt.id ?? opt.value ?? ''),
                text: opt.text ?? opt.label ?? ''
            }))
            : [];

        // Always re-initialize so Select2 receives the full rich objects
        if (initialized) {
            try {
                $sel.select2('destroy');
            } catch (e) {
                // ignore
            }
            initialized = false;
        }

        initSelect2();               // uses data: optionsCache
        $sel.val(null).trigger('change');
    };

    const setPlaceholder = ph => {
        currentPlaceholder = ph || '';
        if (!initialized) {
            currentPlaceholder = ph || '';
            return;
        }
        initSelect2();
        $sel.val(null).trigger('change');
    };

    initSelect2();

    return {
        setOptions: setOptions,
        clear: () => { $sel.val(null).trigger('change'); },
        setDisabled: disabled => { 
            $sel.prop('disabled', !!disabled); 
            $sel.trigger('change.select2');
         },
        getValue: () => $sel.val() || '',
        getSelected: () => {
            const d = $sel.select2('data')[0];
            return d ? { value: d.id, label: d.text, data: d } : null;
        },
        setValue: value => { $sel.val(value).trigger('change'); },
        open: () => { $sel.select2('open'); },
        setPlaceholder: setPlaceholder
    };
};

const productItems = () => products.map(product => ({
    id: product.StockLink,
    text: `${product.StockDescription || product.StockCode}${product.DefaultTaxRate ? ` — ${Number(product.DefaultTaxRate).toFixed(2)}% tax` : ''}`,
    data: product
}));

const unitItems = units => units.map(unit => {
    const plainText = `${unit.unit_code} — ${formatCurrency(unit.cost)}${unit.inv_date ? ` (${new Date(unit.inv_date).toLocaleDateString()})` : ''}`;
    const htmlText = unit.default_unit
        ? `<strong>${escapeHtml(plainText)}</strong>`
        : escapeHtml(plainText);
    return {
        id: unit.unit_id,
        text: plainText,
        html: htmlText,
        cost: unit.cost,
        unit_code: unit.unit_code,
        default_unit: unit.default_unit,
        original: unit
    };
});

const updateTotals = () => {
    const rows = Array.from(linesBody.querySelectorAll('.line-row'));
    let totalTax = 0;
    let totalAmount = 0;

    rows.forEach(row => {
        const qty = Number(row.querySelector('.line-qty').value) || 0;
        const price = Number(row.querySelector('.line-price').value) || 0;
        const taxRate = Number(row.dataset.taxRate || 0);
        const subtotal = qty * price;
        const lineTax = subtotal * taxRate / 100;
        const lineTotal = subtotal + lineTax;

        row.querySelector('.line-tax').textContent = formatCurrency(lineTax);
        row.querySelector('.line-total').textContent = formatCurrency(lineTotal);

        totalTax += lineTax;
        totalAmount += lineTotal;
    });

    lineCount.textContent = rows.length;
    orderTax.textContent = formatCurrency(totalTax);
    orderTotal.textContent = formatCurrency(totalAmount);
};

const resetRowFields = () => {
    Array.from(linesBody.querySelectorAll('.line-row')).forEach(row => {
        const itemField = row.itemField;
        const unitField = row.unitField;
        if (itemField) {
            itemField.setOptions(productItems());
            itemField.clear();
            itemField.setDisabled(products.length === 0); 
            row.dataset.taxRate = '0';
            row.dataset.taxTypeId = '';
        }
        if (unitField) {
            unitField.clear();
            unitField.setDisabled(true);
        }

        row.querySelector('.line-price').value = '0.00';
        const placeholder =
            !supplierField.getValue()
                ? 'Select supplier first'
                : !warehouseField.getValue()
                    ? 'Select warehouse first'
                    : 'Search product';

        if (itemField && itemField.setPlaceholder) {
            itemField.setPlaceholder(placeholder);
        }
    });
    updateTotals();
};

const loadSuppliers = async () => {
    const data = await fetchJson('/inventory/purchase_order/suppliers');
    if (!data.success) {
        throw new Error(data.message || 'Failed to load suppliers');
    }
    supplierField.setOptions(data.suppliers.map(supplier => ({
        value: supplier.DCLink,
        label: supplier.Name,
        data: supplier
    })));
};

const loadWarehouses = async () => {
    const data = await fetchJson('/inventory/fetch_warehouses');
    if (!data.success) {
        throw new Error(data.message || 'Failed to load warehouses');
    }
    warehouseField.setOptions(data.warehouses.map(warehouse => ({
        value: warehouse.id,
        label: `${warehouse.code} — ${warehouse.name}`,
        data: warehouse
    })));
};

const updateAddLineState = () => {
    addLineBtn.disabled = !supplierField.getValue() || !warehouseField.getValue();
};

const fetchUnitsForRow = async (row, stockId) => {
    const supplierId = supplierField.getValue();
    const url = `/inventory/purchase_order/stock_item_units/${encodeURIComponent(stockId)}?supplier_id=${encodeURIComponent(supplierId)}`;
    const data = await fetchJson(url);
    console.log('Fetched units for stockId', stockId, data);
    if (!data.success) {
        throw new Error(data.message || 'Failed to load units');
    }
    return data.units || [];
};

const lineTemplate = () => `
    <tr class="line-row" data-tax-rate="0">
        <td class="col-item" data-label="Item">
            <div class="searchable-field line-item-field">
                <select class="line-item-select searchable-select" style="width:100%"><option></option></select>
            </div>
        </td>
        <td class="col-unit" data-label="Unit">
            <div class="searchable-field line-unit-field">
                <select class="line-unit-select searchable-select" style="width:100%" disabled><option></option></select>
            </div>
        </td>
        <td class="col-qty" data-label="Qty">
            <input type="number" class="line-qty" min="1" step="1" placeholder="Enter qty" aria-label="Quantity">
        </td>
        <td class="col-price" data-label="Price">
            <input type="number" class="line-price" min="0.01" step="0.01" value="0.00" aria-label="Price">
        </td>
        <td class="col-tax" data-label="Tax">
            <div class="line-tax">R 0.00</div>
        </td>
        <td class="col-total" data-label="Total">
            <div class="line-total">R 0.00</div>
        </td>
        <td class="col-actions" data-label="">
            <button type="button" class="delete-line-btn" aria-label="Remove line">×</button>
        </td>
    </tr>
`;

const initializeRowFields = row => {
    const qtyInput = row.querySelector('.line-qty');
    const priceInput = row.querySelector('.line-price');
    const deleteBtn = row.querySelector('.delete-line-btn');
    const itemFieldRoot = row.querySelector('.line-item-field');
    const unitFieldRoot = row.querySelector('.line-unit-field');

    console.log(row)

    const itemSelectEl = itemFieldRoot.querySelector('.line-item-select');
    const unitSelectEl = unitFieldRoot.querySelector('.line-unit-select');
    const itemField = createSelect2Field(itemSelectEl, 'Search product', async option => {
        const selectedProduct = products.find(product => String(product.StockLink) === String(option.value));
        row.dataset.taxRate = String(selectedProduct?.DefaultTaxRate || 0);
        if (selectedProduct?.DefaultTaxTypeId !== undefined && selectedProduct?.DefaultTaxTypeId !== null) {
            row.dataset.taxTypeId = String(selectedProduct.DefaultTaxTypeId);
        } else {
            row.dataset.taxTypeId = '';
        }
        unitField.clear();
        unitField.setDisabled(true);
        priceInput.value = '0.00';

        try {
            const units = await fetchUnitsForRow(row, option.value);
            unitField.setOptions(unitItems(units));
            unitField.setDisabled(false);
            const defaultUnit = units.find(unit => unit.default_unit);
            if (defaultUnit) {
                unitField.setValue(defaultUnit.unit_id);
                priceInput.value = Number(defaultUnit.cost || 0).toFixed(2);
            }
        } catch (err) {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: err.message
            });
            unitField.clear();
            unitField.setDisabled(true);
        }

        updateTotals();
    });

    const unitField = createSelect2Field(unitSelectEl, 'Search unit', option => {
        // option.data is now the Select2 object that contains .cost
        const cost = option.data?.cost ?? 0;
        priceInput.value = Number(cost).toFixed(2);
        console.log('Unit selected:', option, 'Price set to:', priceInput.value);
        updateTotals();
    });

    itemField.setOptions(productItems());
    itemField.setDisabled(!products.length);
    unitField.setDisabled(true);

    qtyInput.addEventListener('input', updateTotals);
    priceInput.addEventListener('input', updateTotals);

    deleteBtn.addEventListener('click', () => {
        row.remove();
        updateTotals();
    });

    row.itemField = itemField;
    row.unitField = unitField;
};

const addLine = async (focus = true) => {
    linesBody.insertAdjacentHTML('beforeend', lineTemplate());
    const row = linesBody.lastElementChild;
    initializeRowFields(row);
    updateTotals();
};

const supplierSelectEl = document.getElementById('supplier-select');
const warehouseSelectEl = document.getElementById('warehouse-select');

const supplierField = createSelect2Field(
    supplierSelectEl,
    'Select supplier',
    async () => {
        try {
            await loadProducts();
            updateAddLineState();
        } catch (err) {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: err.message
            });
        }
    }
);

const warehouseField = createSelect2Field(
    warehouseSelectEl, 
    'Select warehouse', async () => {
    try {
        await loadProducts();
        updateAddLineState();
    } catch (err) {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: err.message
        });
    }
});

const loadProducts = async () => {
    const supplierId = supplierField.getValue();
    const warehouseId = warehouseField.getValue();

    if (!supplierId || !warehouseId) {
        products = [];
        resetRowFields();
        return;
    }

    const url = `/inventory/purchase_order/products?supplier_id=${encodeURIComponent(supplierId)}&warehouse_id=${encodeURIComponent(warehouseId)}`;
    const data = await fetchJson(url);
    if (!data.success) {
        throw new Error(data.message || 'Failed to load products');
    }

    products = data.products || [];
    resetRowFields();
    console.log('Loaded products', products);
};
addLineBtn.addEventListener('click', () => addLine());

saveBtn.addEventListener('click', () => {
    const supplierId = supplierField.getValue();
    const warehouseId = warehouseField.getValue();
    const description = descriptionInput.value.trim();
    const rows = Array.from(linesBody.querySelectorAll('.line-row'));

    if (!supplierId || !warehouseId) {
        Swal.fire({
            icon: 'error',
            title: 'Missing Information',
            text: 'Please select both a supplier and a warehouse before saving the purchase order.'
        });
        return;
    }
    if (!description) {
        Swal.fire({
            icon: 'error',
            title: 'Missing Information',
            text: 'Please provide a description for the purchase order (maximum 40 characters).'
        });
        return;
    }
    if (description.length > 40) {
        Swal.fire({
            icon: 'error',
            title: 'Invalid Input',
            text: 'Description must be 40 characters or fewer.'
        });
        return;
    }
    if (!rows.length) {
        Swal.fire({
            icon: 'error',
            title: 'Missing Information',
            text: 'Please add at least one order line.'
        });
        return;
    }

    const rawLines = rows.map(row => {
        const itemField = row.itemField;
        const unitField = row.unitField;
        const qty = Number(row.querySelector('.line-qty').value) || 0;
        const price = Number(row.querySelector('.line-price').value) || 0;
        return {
            item_id: itemField.getValue(),
            item_name: itemField.getSelected()?.label || '',
            unit_id: unitField.getValue(),
            unit_code: unitField.getSelected()?.label || '',
            qty,
            unit_price: price,
            tax_type_id: row.dataset.taxTypeId || null
        };
    });

    const invalidLine = rawLines.some(line => !line.item_id || !line.unit_id || line.qty <= 0 || line.unit_price <= 0 || !line.tax_type_id);
    if (invalidLine) {
        Swal.fire({
            icon: 'error',
            title: 'Invalid Line',
            text: 'Each order line must include an item, unit, quantity greater than 0, and price greater than 0.'
        });
        return;
    }

    const lines = rawLines.filter(line => line.item_id && line.unit_id && line.qty > 0 && line.unit_price > 0 && line.tax_type_id);

    if (!lines.length) {
        Swal.fire({
            icon: 'error',
            title: 'Missing Information',
            text: 'Please complete each line with item, unit, quantity, and price.'
        });
        return;
    }

    const order = {
        supplier_id: supplierId,
        supplier_name: supplierField.getSelected()?.label || '',
        warehouse_id: warehouseId,
        warehouse_name: warehouseField.getSelected()?.label || '',
        description,
        lines,
        total: orderTotal.textContent,
        tax: orderTax.textContent
    };

    request('/inventory/purchase_order/create-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(order)
    }).then(response => response.json())
      .then(data => {
          if (data.success) {
              Swal.fire({
                  icon: 'success',
                  title: 'Purchase Order Created',
                    text: `Purchase order ${data.order_number} has been created successfully.`,
                    confirmButtonText: 'OK'
                }).then(() => {
                    window.location.href = `/inventory/create_purchase_order`;
                });
          } else {
              Swal.fire({
                  icon: 'error',
                  title: 'Failed to Create Purchase Order',
                  text: data.message || 'An error occurred while creating the purchase order.'
              });
          }
      });
});

window.addEventListener('DOMContentLoaded', async () => {
    try {
        await Promise.all([loadSuppliers(), loadWarehouses()]);
        addLine(false);
        updateAddLineState();
    } catch (err) {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: err.message
        });
    }
});
