function initCostAdjustment(container = document) {
    const root = container.querySelector ? container.querySelector('#cost-adjustment-root') : null;
    const scope = root || container;
    const productSel = scope.querySelector ? scope.querySelector('#ca_product') : null;
    const costInput = scope.querySelector ? scope.querySelector('#ca_cost') : null;
    const currentCost = scope.querySelector ? scope.querySelector('#ca_current_cost') : null;
    const currentCostLabel = scope.querySelector ? scope.querySelector('#ca_current_cost_label') : null;
    const newCostLabel = scope.querySelector ? scope.querySelector('#ca_new_cost_label') : null;
    const submitBtn = scope.querySelector ? scope.querySelector('#ca_submit') : null;
    const resultDiv = scope.querySelector ? scope.querySelector('#ca_result') : null;
    const useSelect2 = typeof window !== 'undefined' && window.jQuery && window.jQuery.fn && window.jQuery.fn.select2;

    if (!productSel || !costInput || !currentCost || !submitBtn || !resultDiv) return;

    function ensureEmptyOption(select) {
        if (!select.querySelector('option[value=""]')) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '';
            select.insertBefore(option, select.firstChild);
        }
    }

    function showResult(message, type) {
        resultDiv.className = `sd-result ${type}`;
        resultDiv.textContent = message;
    }

    function resetCostFields() {
        currentCost.textContent = '—';
        setStockingUnit('');
        costInput.value = '';
        costInput.disabled = true;
        submitBtn.disabled = true;
    }

    function setStockingUnit(unit) {
        const suffix = unit ? ` (per ${unit})` : '';
        if (currentCostLabel) currentCostLabel.textContent = `Current Cost${suffix}`;
        if (newCostLabel) newCostLabel.textContent = `New Cost${suffix}`;
    }

    async function loadProducts() {
        productSel.innerHTML = '<option value="">Loading...</option>';
        try {
            const response = await request('/inventory/adjust_cost/products');
            const payload = await response.json();
            if (!payload.success) throw new Error(payload.message || 'Error loading products');

            if (useSelect2) {
                window.jQuery(productSel).empty();
                ensureEmptyOption(productSel);
            } else {
                productSel.innerHTML = '<option value="">Select product</option>';
            }
            payload.products.forEach(product => {
                const option = document.createElement('option');
                option.value = product.product_link;
                option.textContent = product.description;
                productSel.appendChild(option);
            });
            if (useSelect2) window.jQuery(productSel).trigger('change');
        } catch (error) {
            productSel.innerHTML = `<option value="">${error.message}</option>`;
        }
    }

    async function loadCurrentCost(productLink) {
        resetCostFields();
        if (!productLink) return;
        currentCost.textContent = 'Loading...';
        try {
            const response = await request(`/inventory/adjust_cost/current?product_link=${encodeURIComponent(productLink)}`);
            const payload = await response.json();
            if (!payload.success) throw new Error(payload.message || 'Error loading cost');

            setStockingUnit(payload.stocking_unit_code || '');
            currentCost.textContent = payload.average_cost === null ? 'Not set' : Number(payload.average_cost).toFixed(4);
            costInput.value = payload.average_cost === null ? '' : payload.average_cost;
            costInput.disabled = false;
            submitBtn.disabled = false;
        } catch (error) {
            currentCost.textContent = error.message;
        }
    }

    async function submitCost() {
        const product = productSel.value;
        const cost = Number(costInput.value);
        if (!product) {
            showResult('Please select a product before submitting.', 'error');
            return;
        }
        if (costInput.value === '' || !Number.isFinite(cost) || cost < 0) {
            showResult('Please enter a valid cost of zero or greater.', 'error');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Updating...';
        try {
            const response = await request('/inventory/adjust_cost', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_link: Number(product), cost: cost })
            });
            const payload = await response.json();
            if (!payload.success) throw new Error(payload.message || 'Cost update failed');

            currentCost.textContent = Number(payload.new_cost).toFixed(4);
            showResult(payload.message || 'Cost updated successfully.', 'success');
            window.dispatchEvent(new CustomEvent('costAdjustment:success', {
                detail: { product_link: Number(product), cost: payload.new_cost }
            }));
        } catch (error) {
            showResult(error.message, 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Update Cost';
        }
    }

    function productChanged() {
        loadCurrentCost(productSel.value);
    }

    if (useSelect2) {
        ensureEmptyOption(productSel);
        window.jQuery(productSel).select2({
            placeholder: 'Select product',
            width: '100%',
            allowClear: true,
            dropdownParent: window.jQuery(root || document.body),
            containerCssClass: 'sd-select2-container',
            dropdownCssClass: 'sd-select2-dropdown'
        });
        window.jQuery(productSel).on('select2:select select2:clear', productChanged);
    }

    productSel.addEventListener('change', productChanged);
    costInput.addEventListener('input', () => { submitBtn.disabled = !productSel.value || costInput.value === ''; });
    submitBtn.addEventListener('click', submitCost);
    resetCostFields();
    loadProducts();
}

window.initCostAdjustment = initCostAdjustment;
