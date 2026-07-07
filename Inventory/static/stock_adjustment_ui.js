function initStockAdjustment(container = document) {
    const root = container.querySelector ? container.querySelector('#stock-adjustment-root') : null;
    const productSel = (root || container).querySelector ? (root || container).querySelector('#sa_product') : null;
    const whSel = (root || container).querySelector ? (root || container).querySelector('#sa_warehouse') : null;
    const qtyInput = (root || container).querySelector ? (root || container).querySelector('#sa_quantity') : null;
    const submitBtn = (root || container).querySelector ? (root || container).querySelector('#sa_submit') : null;
    const resultDiv = (root || container).querySelector ? (root || container).querySelector('#sa_result') : null;
    const qtyInfoDiv = (root || container).querySelector ? (root || container).querySelector('#sa_qty_info') : null;
    const operationRadios = (root || container).querySelectorAll ? (root || container).querySelectorAll('input[name="sa_operation"]') : [];
    const unitStockingBtn = (root || container).querySelector ? (root || container).querySelector('#sa_unit_stocking') : null;
    const unitPurchasingBtn = (root || container).querySelector ? (root || container).querySelector('#sa_unit_purchasing') : null;
    const unitLabelSpan = (root || container).querySelector ? (root || container).querySelector('#sa_unit_label') : null;

    let currentQtyOnHand = null;
    let selectedUnit = 'stocking';  // Track which unit is selected for input
    let conversionFactor = 1.0;
    let purchasingUnitCode = '';
    let stockingUnitCode = '';

    const useSelect2 = (typeof window !== 'undefined') && window.jQuery && window.jQuery.fn && window.jQuery.fn.select2;
    let resultClearTimer = null;

    if (!productSel || !whSel || !qtyInput || !submitBtn || !resultDiv || !qtyInfoDiv) return;

    // Unit toggle buttons
    if (unitStockingBtn) {
        unitStockingBtn.addEventListener('click', function(e) {
            e.preventDefault();
            selectedUnit = 'stocking';
            updateUnitButtons();
            updateAdjustedDisplay();
        });
    }
    if (unitPurchasingBtn) {
        unitPurchasingBtn.addEventListener('click', function(e) {
            e.preventDefault();
            selectedUnit = 'purchasing';
            updateUnitButtons();
            updateAdjustedDisplay();
        });
    }

    function updateUnitButtons() {
        if (unitStockingBtn) unitStockingBtn.classList.toggle('active', selectedUnit === 'stocking');
        if (unitPurchasingBtn) unitPurchasingBtn.classList.toggle('active', selectedUnit === 'purchasing');
        
        if (unitLabelSpan) {
            const unit = selectedUnit === 'stocking' ? stockingUnitCode : purchasingUnitCode;
            unitLabelSpan.textContent = unit ? `(${unit})` : '(Stocking Units)';
        }
    }

    async function loadProducts() {
        productSel.innerHTML = '<option value="">Loading...</option>';
        try {
            const res = await fetch('/inventory/adjust_stock/products');
            const payload = await res.json();
            if (payload.status === 'ok') {
                if (useSelect2) {
                    window.jQuery(productSel).empty();
                    ensureEmptyOption(productSel);
                } else {
                    productSel.innerHTML = '<option value="">Select product</option>';
                }
                for (const p of payload.products) {
                    const opt = document.createElement('option');
                    opt.value = p.product_link;
                    opt.textContent = p.description;
                    // Store unit data in option
                    opt.dataset.purchasingUnit = p.purchasing_unit_code || '';
                    opt.dataset.stockingUnit = p.stocking_unit_code || '';
                    opt.dataset.conversionFactor = p.conversion_factor || 1.0;
                    productSel.appendChild(opt);
                }
                if (useSelect2) window.jQuery(productSel).trigger('change');
            } else {
                productSel.innerHTML = '<option value="">Error loading products</option>';
            }
        } catch (err) {
            productSel.innerHTML = '<option value="">Error</option>';
        }
    }

    // Ensure an empty option exists so Select2 can display the placeholder
    function ensureEmptyOption(sel) {
        if (!sel.querySelector('option[value=""]')) {
            const empty = document.createElement('option');
            empty.value = '';
            empty.textContent = '';
            sel.insertBefore(empty, sel.firstChild);
        }
    }

    // Initialize Select2 if available and wire autofocus on open
    if (useSelect2) {
        try {
            const parent = root || document.body;
            ensureEmptyOption(productSel);
            ensureEmptyOption(whSel);
            window.jQuery(productSel).select2({ placeholder: 'Select product', width: '100%', allowClear: true, dropdownParent: window.jQuery(parent), containerCssClass: 'sd-select2-container', dropdownCssClass: 'sd-select2-dropdown' });
            window.jQuery(whSel).select2({ placeholder: 'Select warehouse', width: '100%', allowClear: true, dropdownParent: window.jQuery(parent), containerCssClass: 'sd-select2-container', dropdownCssClass: 'sd-select2-dropdown' });
            // autofocus the search input when dropdown opens
            window.jQuery(productSel).on('select2:open', function () {
                setTimeout(() => { const f = document.querySelector('.select2-search__field'); if (f) f.focus(); }, 0);
            });
            window.jQuery(whSel).on('select2:open', function () {
                setTimeout(() => { const f = document.querySelector('.select2-search__field'); if (f) f.focus(); }, 0);
            });
            // Listen to Select2 change event (fires on both user selection and programmatic .val().trigger('change'))
            window.jQuery(productSel).on('select2:select select2:clear', function () {
                currentQtyOnHand = null;
                if (productSel.value) {
                    // Get unit info from selected option
                    const selectedOption = productSel.options[productSel.selectedIndex];
                    if (selectedOption) {
                        purchasingUnitCode = selectedOption.dataset.purchasingUnit || '';
                        stockingUnitCode = selectedOption.dataset.stockingUnit || '';
                        conversionFactor = parseFloat(selectedOption.dataset.conversionFactor) || 1.0;
                    }
                    loadWarehouses(productSel.value);
                } else {
                    whSel.innerHTML = '<option value="">Select a product first</option>';
                    if (useSelect2) window.jQuery(whSel).empty().append('<option value=""></option>').prop('disabled', true);
                    else whSel.disabled = true;
                    if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
                }
            });
            window.jQuery(whSel).on('select2:select select2:clear', function () {
                if (productSel.value && whSel.value) {
                    loadQtyOnHand(productSel.value, whSel.value);
                } else if (productSel.value) {
                    currentQtyOnHand = null;
                    if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
                }
            });
        } catch (e) {
            // fail silently - fall back to native selects
            console.warn('Select2 init failed', e);
        }
    }

    async function loadWarehouses(stockLink) {
        if (useSelect2) {
            window.jQuery(whSel).empty();
            ensureEmptyOption(whSel);
        } else whSel.innerHTML = '<option value="">Loading...</option>';
        whSel.disabled = true;
        try {
            const res = await fetch(`/inventory/adjust_stock/warehouses?stock_link=${encodeURIComponent(stockLink)}`);
            const payload = await res.json();
            if (payload.status === 'ok') {
                if (useSelect2) {
                    window.jQuery(whSel).empty();
                    ensureEmptyOption(whSel);
                } else whSel.innerHTML = '<option value="">Select warehouse</option>';
                for (const w of payload.warehouses) {
                    const opt = document.createElement('option');
                    opt.value = w.whse_link;
                    opt.textContent = w.whse_description || w.whse_link;
                    whSel.appendChild(opt);
                }
                if (useSelect2) {
                    window.jQuery(whSel).prop('disabled', false).trigger('change');
                } else {
                    whSel.disabled = false;
                }
                if (qtyInfoDiv) {
                    qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
                }
            } else {
                if (useSelect2) window.jQuery(whSel).empty(); else whSel.innerHTML = '<option value="">Error loading warehouses</option>';
                if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
            }
        } catch (err) {
            if (useSelect2) window.jQuery(whSel).empty(); else whSel.innerHTML = '<option value="">Error</option>';
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
        }
    }

    async function loadQtyOnHand(stockLink, warehouseLink) {
        if (!stockLink || !warehouseLink) {
            currentQtyOnHand = null;
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div>';
            return;
        }

        if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">Loading...</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
        try {
            const res = await fetch(`/inventory/adjust_stock/qty?stock_link=${encodeURIComponent(stockLink)}&warehouse_link=${encodeURIComponent(warehouseLink)}`);
            const payload = await res.json();
            if (payload.status === 'ok') {
                currentQtyOnHand = Number(payload.qty_on_hand);
                // Update unit info from backend
                purchasingUnitCode = payload.purchasing_unit_code || purchasingUnitCode || '';
                stockingUnitCode = payload.stocking_unit_code || stockingUnitCode || '';
                conversionFactor = payload.conversion_factor || conversionFactor || 1.0;
                updateUnitButtons();
                updateAdjustedDisplay();
            } else {
                currentQtyOnHand = null;
                if (qtyInfoDiv) qtyInfoDiv.innerHTML = `<div class="sd-summary-item"><span class="sd-summary-label">Error</span><span class="sd-summary-value">${payload.message || 'unknown error'}</span></div>`;
            }
        } catch (err) {
            currentQtyOnHand = null;
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = `<div class="sd-summary-item"><span class="sd-summary-label">Error</span><span class="sd-summary-value">${err.message}</span></div>`;
        }
    }

    function updateAdjustedDisplay() {
        if (currentQtyOnHand === null) {
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
            return;
        }

        const rawQty = qtyInput.value;
        const quantity = parseFloat(rawQty);
        const operation = Array.from(operationRadios).find(r => r.checked)?.value || 'set';

        // Display qty on hand in the current display unit
        let displayQty = currentQtyOnHand;
        let displayUnit = stockingUnitCode;
        if (selectedUnit === 'purchasing' && conversionFactor > 0) {
            displayQty = currentQtyOnHand / conversionFactor;
            displayUnit = purchasingUnitCode;
        }

        if (!rawQty || isNaN(quantity)) {
            const qtyDisplay = displayQty.toFixed(2).toLocaleString(undefined, { minimumFractionDigits: 2 });
            if (qtyInfoDiv) {
                qtyInfoDiv.innerHTML = `
                    <div class="sd-summary-item">
                        <span class="sd-summary-label">Qty On Hand</span>
                        <span class="sd-summary-value">${qtyDisplay} ${displayUnit || 'Stocking Units'}</span>
                    </div>
                `;
            }
            return;
        }

        let adjustedQty;
        let label = 'Adjusted qty';
        // Convert input quantity to stocking units for calculation
        let qtyInStockingUnits = quantity;
        if (selectedUnit === 'purchasing' && conversionFactor > 0) {
            qtyInStockingUnits = quantity * conversionFactor;
        }

        if (operation === 'set') {
            adjustedQty = qtyInStockingUnits;
        } else if (operation === 'subtract' || operation === 'decrease' || operation === 'remove') {
            adjustedQty = currentQtyOnHand - qtyInStockingUnits;
        } else {
            adjustedQty = currentQtyOnHand + qtyInStockingUnits;
        }

        let adjustedDisplayQty = adjustedQty;
        if (selectedUnit === 'purchasing' && conversionFactor > 0) {
            adjustedDisplayQty = adjustedQty / conversionFactor;
        }

        const qtyDisplay = displayQty.toFixed(2).toLocaleString(undefined, { minimumFractionDigits: 2 });
        const adjustedDisplay = adjustedDisplayQty.toFixed(2).toLocaleString(undefined, { minimumFractionDigits: 2 });

        const hasError = adjustedQty < 0;
        const errorClass = hasError ? ' sd-error' : '';
        const errorText = hasError ? ' — result would be negative; adjust values.' : '';

        if (qtyInfoDiv) {
            qtyInfoDiv.innerHTML = `
                <div class="sd-summary-item${errorClass}">
                    <span class="sd-summary-label">System Qty</span>
                    <span class="sd-summary-value">${qtyDisplay} ${displayUnit || 'Stocking Units'}</span>
                </div>
                <div class="sd-summary-item${errorClass}">
                    <span class="sd-summary-label">${label}</span>
                    <span class="sd-summary-value">${adjustedDisplay} ${displayUnit || 'Stocking Units'}${errorText}</span>
                </div>
            `;
        }
    }

    function showResult(message, type) {
        resultDiv.className = `sd-result ${type}`;
        resultDiv.textContent = message;
        // auto-clear success messages
        if (resultClearTimer) {
            clearTimeout(resultClearTimer);
            resultClearTimer = null;
        }
        if (type === 'success') {
            resultClearTimer = setTimeout(() => {
                resultDiv.className = 'sd-result';
                resultDiv.textContent = '';
                resultClearTimer = null;
            }, 4000);
        }
    }

    // Prefill product and warehouse from URL params if provided
    async function handlePrefill() {
        if (typeof window === 'undefined') return;
        const params = (window.location && new URLSearchParams(window.location.search)) || new URLSearchParams();
        const urlP = params.get('product') || params.get('product_link');
        const urlW = params.get('warehouse') || params.get('warehouse_link');
        const urlUnit = params.get('unit') || params.get('unit_type');
        // also allow container dataset overrides (useful when embedded in a modal)
        const attrP = container && container.dataset && (container.dataset.product || container.dataset.productLink || container.dataset.saProduct || container.dataset.sa_product);
        const attrW = container && container.dataset && (container.dataset.warehouse || container.dataset.warehouseLink || container.dataset.saWarehouse || container.dataset.sa_warehouse);
        const attrUnit = container && container.dataset && (container.dataset.unit || container.dataset.unitType || container.dataset.saUnit || container.dataset.sa_unit);
        const p = urlP || attrP;
        const w = urlW || attrW;
        const unitType = (urlUnit || attrUnit || '').toLowerCase();
        if (unitType === 'purchasing' || unitType === 'stocking') {
            selectedUnit = unitType;
        }

        if (!p) return;

        try {
            // Set product value without triggering events yet
            if (useSelect2) {
                window.jQuery(productSel).val(String(p)).trigger('change');
            } else {
                productSel.value = p;
            }

            // Manually load warehouses for this product
            await loadWarehouses(p);

            // Now set warehouse if provided
            if (w) {
                if (useSelect2) {
                    window.jQuery(whSel).val(w).trigger('change');
                } else {
                    whSel.value = w;
                }
                // Manually load qty for this product+warehouse
                await loadQtyOnHand(p, w);
            }

            updateUnitButtons();
            updateAdjustedDisplay();
        } catch (err) {
            console.warn('Prefill failed', err);
        }
    }

    submitBtn.addEventListener('click', async function () {
        const product = productSel.value;
        const warehouse = whSel.value;
        const quantity = qtyInput.value;
        const operation = Array.from(operationRadios).find(r => r.checked)?.value || 'set';
        resultDiv.className = 'sd-result';
        resultDiv.textContent = '';

        if (!product) {
            showResult('Please select a product before submitting.', 'error');
            return;
        }
        if (!warehouse) {
            showResult('Please select a warehouse before submitting.', 'error');
            return;
        }
        if (quantity === '' || isNaN(Number(quantity))) {
            showResult('Please enter a valid numeric quantity.', 'error');
            return;
        }

        // Prevent negative entries and negative resulting qtys
        const qtyNum = Number(quantity);
        if (qtyNum < 0) {
            showResult('Quantity must be zero or positive.', 'error');
            return;
        }

        // Convert user-entered quantity to stocking units for submission
        let qtyInStockingUnits = qtyNum;
        if (selectedUnit === 'purchasing' && conversionFactor > 0) {
            qtyInStockingUnits = qtyNum * conversionFactor;
        }

        if (currentQtyOnHand !== null) {
            let finalQty = currentQtyOnHand;
            if (operation === 'set') finalQty = qtyInStockingUnits;
            else if (operation === 'subtract' || operation === 'decrease' || operation === 'remove') finalQty = currentQtyOnHand - qtyInStockingUnits;
            else finalQty = currentQtyOnHand + qtyInStockingUnits;
            if (finalQty < 0) {
                showResult('Operation would result in negative stock — adjust quantity or operation.', 'error');
                return;
            }
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        try {
            const res = await fetch('/inventory/adjust_stock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_link: Number(product), warehouse_link: warehouse, operation: operation, quantity: qtyInStockingUnits })
            });
            const payload = await res.json();
            if (payload.success) {
                showResult(payload.message ? `✓ ${payload.message}` : '✓ Stock adjustment submitted successfully.', 'success');
                // clear inputs and reset state
                if (useSelect2) {
                    window.jQuery(productSel).val(null).trigger('change');
                    window.jQuery(whSel).empty().append('<option value=""></option>').prop('disabled', true).trigger('change');
                } else {
                    productSel.value = '';
                    whSel.innerHTML = '<option value="">Select a product first</option>';
                    whSel.disabled = true;
                }
                qtyInput.value = '';
                currentQtyOnHand = null;
                if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
                // reset operation radios to first (set)
                if (operationRadios && operationRadios.length) {
                    operationRadios.forEach((r, i) => r.checked = (i === 0));
                }
                selectedUnit = 'stocking';
                updateUnitButtons();
                productSel.focus();
                // notify other parts of the app that an adjustment succeeded
                try {
                    window.dispatchEvent(new CustomEvent('stockAdjustment:success', { detail: { product_link: Number(product), warehouse_link: warehouse } }));
                } catch (e) {
                    console.warn('Could not dispatch stockAdjustment event', e);
                }
            } else {
                showResult(`✗ ${payload.error || payload.message || 'Unknown error occurred.'}`, 'error');
            }
        } catch (err) {
            showResult(`✗ Network error: ${err.message}`, 'error');
        }

        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Adjustment';
    });

    productSel.addEventListener('change', function () {
        currentQtyOnHand = null;
        if (productSel.value) {
            // Get unit info from selected option
            const selectedOption = productSel.options[productSel.selectedIndex];
            if (selectedOption) {
                purchasingUnitCode = selectedOption.dataset.purchasingUnit || '';
                stockingUnitCode = selectedOption.dataset.stockingUnit || '';
                conversionFactor = parseFloat(selectedOption.dataset.conversionFactor) || 1.0;
            }
            loadWarehouses(productSel.value);
        } else {
            whSel.innerHTML = '<option value="">Select a product first</option>';
            whSel.disabled = true;
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
        }
    });

    whSel.addEventListener('change', function () {
        if (productSel.value && whSel.value) {
            loadQtyOnHand(productSel.value, whSel.value);
        } else if (productSel.value) {
            currentQtyOnHand = null;
            if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
        }
    });

    qtyInput.addEventListener('input', updateAdjustedDisplay);
    operationRadios.forEach(radio => radio.addEventListener('change', updateAdjustedDisplay));

    // initialize: load products first, then handle URL prefill (if any)
    whSel.innerHTML = '<option value="">Select a product first</option>';
    whSel.disabled = true;
    if (qtyInfoDiv) qtyInfoDiv.innerHTML = '<div class="sd-summary-item"><span class="sd-summary-label">Qty On Hand</span><span class="sd-summary-value">—</span></div><div class="sd-summary-item"><span class="sd-summary-label">Unit</span><span class="sd-summary-value">—</span></div>';
    loadProducts().then(() => {
        // attempt to prefill from URL after products are populated
        handlePrefill();
    });
}
window.initStockAdjustment = initStockAdjustment;
window.openStockAdjustmentModal = async function (options = {}) {
    if (typeof options !== 'object' || options === null) {
        options = { stockLink: options };
    }
    const { stockLink, warehouseLink, unit } = options;
    let modal = document.getElementById('stockAdjustmentModal');
    let modalBody = document.getElementById('stockAdjustmentModalBody');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'stockAdjustmentModal';
        Object.assign(modal.style, { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999 });
        const inner = document.createElement('div');
        inner.id = 'stockAdjustmentModalBody';
        Object.assign(inner.style, { background: '#fff', borderRadius: '12px', maxWidth: '920px', width: '100%', maxHeight: '90vh', overflow: 'auto', padding: '16px', boxSizing: 'border-box', position: 'relative' });
        modal.appendChild(inner);
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.remove();
            }
        });
        document.body.appendChild(modal);
    }
    if (!modalBody) {
        modalBody = document.getElementById('stockAdjustmentModalBody');
    }
    modalBody.innerHTML = '<div style="padding: 2rem; text-align: center; color: #6b7280;">Loading stock adjustment...</div>';

    try {
        const res = await fetch('/inventory/adjust_stock/popup');
        if (!res.ok) throw new Error('Unable to load content');
        const html = await res.text();

        modalBody.innerHTML = '';
        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.textContent = '×';
        Object.assign(closeButton.style, { position: 'absolute', top: '12px', right: '12px', width: '34px', height: '34px', border: 'none', borderRadius: '50%', background: '#f1f5f9', color: '#334155', fontSize: '20px', cursor: 'pointer', lineHeight: '0.9', boxShadow: '0 1px 3px rgba(0,0,0,0.12)' });
        closeButton.addEventListener('click', () => modal.remove());
        modalBody.appendChild(closeButton);

        const contentWrapper = document.createElement('div');
        Object.assign(contentWrapper.style, { paddingTop: '10px' });
        contentWrapper.innerHTML = html;
        modalBody.appendChild(contentWrapper);

        if (stockLink) modalBody.dataset.product = stockLink;
        if (warehouseLink) modalBody.dataset.warehouse = warehouseLink;
        if (unit) modalBody.dataset.unit = unit;

        if (typeof initStockAdjustment === 'function') {
            initStockAdjustment(modalBody);
        } else {
            console.warn('initStockAdjustment is not available when opening the modal');
        }
    } catch (err) {
        modalBody.innerHTML = `<div style="padding:2rem;color:#c2410c">${err.message}</div>`;
    }
};
