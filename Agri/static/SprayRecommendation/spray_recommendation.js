
$('.select2').each(function() {
    const placeholder = $(this).data('placeholder');
    $(this).select2({
        width: '100%',
        placeholder: placeholder || undefined,
        allowClear: !!placeholder
    });
});

// Ensure any Select2 opened anywhere on the page focuses its search input immediately
$(document).on('select2:open', function () {
    setTimeout(() => {
        const search = document.querySelector('.select2-container--open .select2-search__field');
        if (search) search.focus();
    }, 0);
});

// Ensure any Select2 dropdown opened has a minimum width at least as wide
// as its closed/select container so opened dropdowns don't shrink smaller
// than the visible select. Applies globally to all Select2 instances.
$(document).on('select2:opening', function(e) {
    try {
        const $el = $(e.target);
        const s2 = $el.data('select2');
        if (s2) {
            const $container = s2.$container;
            const closedWidth = $container ? $container.outerWidth() : null;
            const $dropdown = s2.$dropdown;
            if ($dropdown && closedWidth) {
                $dropdown.css('min-width', closedWidth + 'px');
            }
        }
    } catch (err) {
        // swallow errors to avoid breaking other Select2 behavior
        console.error('Select2 opening width-sync error', err);
    }
});

// Custom initialization for product selects with better width control
function initProductSelects() {
    $('.product-select').each(function() {
        if (!$(this).data('select2')) {
            $(this).select2({
                width: '100%',
                dropdownAutoWidth: true,
                dropdownCssClass: 'product-dropdown',
                containerCssClass: 'product-select-container'
            });
        }
        
        // Sync closed select width to opened dropdown min-width
        $(this).on('select2:opening', function() {
            const $container = $(this).data('select2').$container;
            const closedWidth = $container.outerWidth();
            const $dropdown = $(this).data('select2').$dropdown;
            if ($dropdown && closedWidth) {
                $dropdown.css('min-width', closedWidth + 'px');
            }
        });
    });
}

let PRODUCT_OPTIONS = "";
let PRODUCTS_DATA = {}; // Store product data for modal editing: {stock_id: {reg_number, witholding_period, function}}

// Function to fetch products when warehouse or projects change
async function updateProductsByWarehouse(warehouseId, projectIds) {
    // Only fetch when both a warehouse and at least one project are selected
    if (!warehouseId || !projectIds || !projectIds.length) {
        PRODUCT_OPTIONS = '<option value="">Select warehouse and project(s)</option>';
        $('.product-select').each(function() {
            $(this).html(PRODUCT_OPTIONS).trigger('change');
        });
        return;
    }

    try {
        const pidParam = encodeURIComponent(projectIds.join(','));
        const response = await fetch(`/agri/fetch_products_linked_with_warehouse?warehouse_id=${warehouseId}&project_ids=${pidParam}`);
        const data = await response.json();

        if (data.products && data.products.length > 0) {
            // Build options HTML with useful data-* attributes
            let options = '<option value="">Select product</option>';
            PRODUCTS_DATA = {}; // Reset products data
            
            data.products.forEach(product => {
                const qtyFormatted = parseFloat(product.qty_in_whse).toFixed(2);
                options += `<option value="${product.product_link}" data-uom-id="${product.stocking_uom_id || ''}" data-purchase-uom-id="${product.purchase_uom_id || ''}" data-uom-cat="${product.uom_cat_id || ''}" data-reg-number="${product.reg_number || ''}" data-witholding-period="${product.witholding_period || ''}" data-function="${product.function || ''}">` +
                    `${product.active_ingredient} - ${product.product_desc}(${qtyFormatted} ${product.stocking_uom_code})` +
                    `</option>`;
                
                // Store product data for later reference
                PRODUCTS_DATA[product.product_link] = {
                    reg_number: product.reg_number || '',
                    witholding_period: product.witholding_period || '',
                    function: product.function || ''
                };
            });
            PRODUCT_OPTIONS = options;

            // Update all existing product dropdowns: destroy/rebuild to apply new options and Select2 settings
            $('.product-select').each(function() {
                const $sel = $(this);
                const currentVal = $sel.val();
                if ($sel.data('select2')) {
                    $sel.select2('destroy');
                }
                $sel.html(PRODUCT_OPTIONS);
                if (currentVal) $sel.val(currentVal);
                // Re-initialize select2 with product-specific options
                $sel.select2({
                    width: '100%',
                    dropdownAutoWidth: true,
                    dropdownCssClass: 'product-dropdown',
                    containerCssClass: 'product-select-container'
                });
                
                // Sync closed select width to opened dropdown min-width
                $sel.on('select2:opening', function() {
                    const $container = $(this).data('select2').$container;
                    const closedWidth = $container.outerWidth();
                    const $dropdown = $(this).data('select2').$dropdown;
                    if ($dropdown && closedWidth) {
                        $dropdown.css('min-width', closedWidth + 'px');
                    }
                });
                
                $sel.trigger('change');
            });

            // If products returned and there are no product lines, add one automatically
            if (data.products.length > 0 && document.querySelectorAll('.product-card').length === 0) {
                addLine();
                // set first select to first product
                setTimeout(() => {
                    const firstSelect = document.querySelector('.product-select');
                    if (firstSelect) {
                        firstSelect.value = data.products[0].product_link;
                        $(firstSelect).trigger('change');
                    }
                    recalcEverything();
                }, 50);
            }

        } else {
            // show reason from server if provided
            const message = data.message || 'No products available for the selected warehouse and projects.';
            PRODUCT_OPTIONS = `<option value="">${message}</option>`;
            $('.product-select').each(function() {
                $(this).html(PRODUCT_OPTIONS).trigger('change');
            });
            Swal.fire({ icon: 'info', title: 'No products', text: message });
        }
    } catch (error) {
        console.error('Error fetching products:', error);
        PRODUCT_OPTIONS = '<option value="">Error loading products</option>';
        $('.product-select').each(function() {
            $(this).html(PRODUCT_OPTIONS).trigger('change');
        });
        Swal.fire({ icon: 'error', title: 'Error', text: 'Error fetching products' });
    }
}

async function updateProjectsForWarehouse(warehouseId) {
    const $projectSelect = $('#project_ids');
    $projectSelect.empty();
    if (!warehouseId) {
        $projectSelect.prop('disabled', true).trigger('change');
        return;
    }

    try {
        const response = await fetch(`/agri/fetch_projects_for_warehouse?warehouse_id=${warehouseId}`);
        const data = await response.json();

        if (data.status === 'ok' && data.projects && data.projects.length > 0) {
            data.projects.forEach(project => {
                const option = document.createElement('option');
                option.value = project.project_id;
                option.text = `${project.project_code}`;
                option.setAttribute('data-ha', project.proj_attr_ha);
                option.setAttribute('data-crop-id', project.proj_attr_crop_id);
                $projectSelect.append(option);
            });
            $projectSelect.prop('disabled', false).trigger('change');
        } else {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.disabled = true;
            placeholder.text = data.message || 'No projects available for this warehouse';
            $projectSelect.append(placeholder);
            $projectSelect.prop('disabled', true).trigger('change');
        }

        // Clear selected projects and product options until a project is chosen
        $projectSelect.val(null).trigger('change');
        updateProductsByWarehouse(warehouseId, []);
    } catch (error) {
        console.error('Error fetching projects:', error);
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.disabled = true;
        placeholder.text = 'Error loading projects';
        $projectSelect.append(placeholder);
        $projectSelect.prop('disabled', true).trigger('change');
        Swal.fire({ icon: 'error', title: 'Error', text: 'Error fetching projects' });
    }
}

// Function to get week number and year from a date
function getWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return {
        week: weekNo,
        year: d.getUTCFullYear()
    };
}

// Function to update the spray week display when date is selected
function updateSprayWeek() {
    const dateInput = document.getElementById('spray_date');
    const weekDisplay = document.getElementById('spray_week');
    
    if (!dateInput.value) {
        weekDisplay.textContent = 'Week: -';
        return;
    }
    
    const selectedDate = new Date(dateInput.value);
    const { week, year } = getWeekNumber(selectedDate);
    
    weekDisplay.textContent = `Week: ${week} (${year})`;
}

// Alternative: If you want to display as "Week 42 (2024)"
function updateSprayWeekFormatted() {
    const dateInput = document.getElementById('spray_date');
    const weekDisplay = document.getElementById('spray_week');
    
    if (!dateInput.value) {
        weekDisplay.textContent = 'Week: -';
        return;
    }
    
    const selectedDate = new Date(dateInput.value);
    const { week, year } = getWeekNumber(selectedDate);
    
    weekDisplay.textContent = `Week ${week} (${year})`;
}

// Alternative: Using ISO week date format (more standard)
function getISOWeekNumber(date) {
    const tempDate = new Date(date.getTime());
    tempDate.setHours(0, 0, 0, 0);
    tempDate.setDate(tempDate.getDate() + 3 - (tempDate.getDay() + 6) % 7);
    const week1 = new Date(tempDate.getFullYear(), 0, 4);
    return {
        week: 1 + Math.round(((tempDate - week1) / 86400000 - 3 + (week1.getDay() + 6) % 7) / 7),
        year: tempDate.getFullYear()
    };
}

function updateSprayWeekISO() {
    const dateInput = document.getElementById('spray_date');
    const weekDisplay = document.getElementById('spray_week');
    
    if (!dateInput.value) {
        weekDisplay.textContent = 'Week: -';
        return;
    }
    
    const selectedDate = new Date(dateInput.value);
    const { week, year } = getISOWeekNumber(selectedDate);
    
    weekDisplay.textContent = `Week: ${week} (${year})`;
}

function getMode() {
    return document.querySelector('input[name="dose_mode"]:checked').value;
}

function renderModeUI() {
    const mode = getMode();

    document.getElementById('tank-fields').classList.add('hidden');
    document.getElementById('direct-fields').classList.add('hidden');
    // tank plan removed; updates now appear in the sticky bar

    document.querySelectorAll('.per-100l-field').forEach(i => i.classList.add('hidden'));
    document.querySelectorAll('.per-ha-tank-field').forEach(i => i.classList.add('hidden'));

    // Disable all inputs in hidden sections first
    document.querySelectorAll('#tank-fields input, #tank-fields select, .per-100l-field input, .per-ha-tank-field input').forEach(el => {
        el.disabled = true;
    });

    if (mode === "per_100l") {
        document.getElementById('tank-fields').classList.remove('hidden');
        document.querySelectorAll('.per-100l-field').forEach(i => i.classList.remove('hidden'));
        // Enable visible inputs
        document.querySelectorAll('.per-100l-field input').forEach(i => i.disabled = false);
        document.querySelectorAll('#tank-fields select, #tank-fields input:not(.per-ha-tank-field input)').forEach(el => el.disabled = false);
    }

    if (mode === "per_ha_tank") {
        document.getElementById('tank-fields').classList.remove('hidden');
        document.querySelectorAll('.per-ha-tank-field').forEach(i => i.classList.remove('hidden'));
        // Enable visible inputs
        document.querySelectorAll('.per-ha-tank-field input').forEach(i => i.disabled = false);
        document.querySelectorAll('#tank-fields select, #tank-fields input:not(.per-100l-field input)').forEach(el => el.disabled = false);
    }

    if (mode === "per_ha_direct") {
        document.getElementById('direct-fields').classList.remove('hidden');
        // tank plan removed
        // All tank fields remain disabled
    }

    document.querySelectorAll('.mode-card').forEach(c => {
        c.classList.remove('active');
        if (c.dataset.mode === mode) {
            c.classList.add('active');
        }
    });

    updateLineLabels();
    recalcEverything();
}

function updateProjectConfigs() {
    const ids = $('#project_ids').val() || [];
    const container = document.getElementById('project-configs');

    container.innerHTML = '';

    if (!ids.length) {
        recalcEverything();
        return;
    }

    let head = document.createElement('div');
    head.className = 'project-row project-head';
    head.innerHTML = `
        <div>Project</div>
        <div>Ha</div>
        <div class="per-100l-field">Water/Ha</div>
        <div class="per-100l-field">Total Water</div>
    `;
    container.appendChild(head);

    ids.forEach(id => {
        const o = document.querySelector(`#project_ids option[value="${id}"]`);
        const ha = parseFloat(o.dataset.ha || 0);

        let row = document.createElement('div');
        row.className = 'project-row';

        row.innerHTML = `
            <div>${o.textContent}</div>
            <div>${ha}</div>
            <div>
                <input class="project-water-input per-100l-field" type="number" step="0.1">
            </div>
            <div class="per-100l-field">
                <input class="project-water-total per-100l-field" type="number" step="0.1">
            </div>
        `;

        container.appendChild(row);
    });

    renderModeUI();
    recalcEverything();
    // After rendering projects, refetch products for the selected warehouse + projects
    const warehouseId = document.getElementById('warehouse_id')?.value;
    const projectIds = $('#project_ids').val() || [];
    updateProductsByWarehouse(warehouseId, projectIds);
}

function updateLineLabels() {
    const mode = getMode();

    document.querySelectorAll('.rate-label').forEach(el => {
        el.textContent = (mode === 'per_100l') ? 'Rate /100L' : 'Rate /Ha';
    });
}

function addLine() {
    let row = document.createElement('div');
    row.className = 'product-card';
    const lineId = 'product-line-' + Date.now(); // Unique ID for this line

    row.innerHTML = `
        <div class="product-grid">
            <div>
                <select class="product-select">
                    ${PRODUCT_OPTIONS || '<option value="">Select product</option>'}
                </select>
                <input type="hidden" class="line-reg-number" value="">
                <input type="hidden" class="line-witholding-period" value="">
                <input type="hidden" class="line-function" value="">
            </div>

            <div>
                <label class="rate-label">Rate /100L</label>
                <input class="qty-input" type="number" step="0.01">
            </div>

            <div>
                <label>Total Qty</label>
                <div class="readonly-box total-qty">-</div>
            </div>

            <div>
                <label>Per Tank</label>
                <div class="readonly-box per-tank">-</div>
            </div>

            <div style="display: flex; gap: 8px;">
                <button type="button" class="edit-defaults-btn icon-btn" title="Edit defaults">
                    ⚙️
                </button>
                <button type="button" class="delete-line-btn icon-btn delete" title="Delete line">
                    ✕
                </button>
            </div>
        </div>
    `;

    document.getElementById('lines').appendChild(row);
    const $row = $(row);
    // initialize select2 for product selects (uses dropdownCssClass and width control)
    initProductSelects();
    const selectEl = $row.find('.product-select');
    
    // Update hidden fields when product is selected
    selectEl.on('change', function() {
        const productId = $(this).val();
        const card = $(this).closest('.product-card');
        
        // Check for duplicate product selection
        if (productId) {
            let isDuplicate = false;
            document.querySelectorAll('.product-select').forEach(sel => {
                if (sel !== this && sel.value === productId) isDuplicate = true;
            });
            if (isDuplicate) {
                $(this).val('').trigger('change');
                const productName = this.options[this.selectedIndex]?.text || 'Product';
                Swal.fire({
                    icon: 'warning',
                    title: 'Duplicate Product',
                    text: `"${productName}" is already selected in another line.`,
                    confirmButtonText: 'OK'
                });
                return;
            }
        }
        
        if (productId && PRODUCTS_DATA[productId]) {
            card.find('.line-reg-number').val(PRODUCTS_DATA[productId].reg_number || '');
            card.find('.line-witholding-period').val(PRODUCTS_DATA[productId].witholding_period || '');
            card.find('.line-function').val(PRODUCTS_DATA[productId].function || '');
        }
        recalcEverything();
    });
    
    // Edit defaults button
    $(row).find('.edit-defaults-btn').on('click', function(e) {
        e.preventDefault();
        const card = $(this).closest('.product-card');
        const regNumber = card.find('.line-reg-number').val();
        const witholdingPeriod = card.find('.line-witholding-period').val();
        const func = card.find('.line-function').val();
        
        openEditDefaultsModal(card, regNumber, witholdingPeriod, func);
    });
    
    // Delete line button
    $(row).find('.delete-line-btn').on('click', function(e) {
        e.preventDefault();
        $(this).closest('.product-card').remove();
        recalcEverything();
    });
    
    updateLineLabels();
    recalcEverything();
}

function clearLines() {
    document.getElementById('lines').innerHTML = '';
    recalcEverything();
}

/* ====================== FRONTEND CALCULATION ENGINE ====================== */
function recalcEverything() {
    const mode = getMode();

    let totalHa = 0;
    let totalWater = 0;

    // PROJECT TOTALS
    const rows = document.querySelectorAll('.project-row:not(.project-head)');
    let rowIndex = 0;

    document.querySelectorAll('#project_ids option:checked').forEach((o, idx) => {
        const ha = parseFloat(o.dataset.ha || 0);
        totalHa += ha;
        rowIndex = idx;

        if (mode === "per_100l") {
            if (rows[rowIndex]) {
                // Use total water input if available, otherwise calculate from water per ha
                const totalWaterInput = rows[rowIndex].querySelector('.project-water-total');
                const waterPerHaInput = rows[rowIndex].querySelector('.project-water-input');
                
                let projWater = parseFloat(totalWaterInput?.value || 0);
                if (!projWater && waterPerHaInput) {
                    const waterPerHa = parseFloat(waterPerHaInput.value || 0);
                    projWater = ha * waterPerHa;
                }
                
                totalWater += projWater;
            }
        }
    });

    // Update total area
    document.getElementById('total-ha').textContent = totalHa.toFixed(2);
    document.getElementById('sticky-ha').textContent = totalHa.toFixed(2);

    if (mode === "per_ha_direct") {
        // Direct mode: no water/tanks
        const stickyWaterEl = document.getElementById('sticky-water'); if (stickyWaterEl) stickyWaterEl.textContent = '-';
        const stickyTanksEl = document.getElementById('sticky-tanks'); if (stickyTanksEl) stickyTanksEl.textContent = '-';
        const sumWaterElDirect = document.getElementById('sum-water'); if (sumWaterElDirect) sumWaterElDirect.textContent = '-';
        const sumTanksElDirect = document.getElementById('sum-tanks'); if (sumTanksElDirect) sumTanksElDirect.textContent = '-';
        const sumPartialElDirect = document.getElementById('sum-partial'); if (sumPartialElDirect) sumPartialElDirect.textContent = '-';
        updateProductTotals(totalHa, null, null);
        return;
    }

    // WATER & TANK CALCULATION
    const methodInput = document.getElementById('method_id');
    const methodId = methodInput?.value || '';
    let waterPerTank = parseFloat(document.getElementById('global_water_per_tank').value) || 0;

    if (mode === "per_ha_tank") {
        // Use total_water field if available, otherwise calculate from water_per_ha
        const totalWaterInput = parseFloat(document.getElementById('global_total_water').value) || 0;
        if (totalWaterInput > 0) {
            totalWater = totalWaterInput;
        } else {
            const waterPerHa = parseFloat(document.getElementById('global_water_per_ha').value) || 0;
            totalWater = totalHa * waterPerHa;
        }
    }

    // Update water display (sticky bar is primary; update legacy ids only if present)
    const sumWaterEl = document.getElementById('sum-water');
    if (sumWaterEl) sumWaterEl.textContent = totalWater.toFixed(1) + ' L';
    const stickyWaterEl2 = document.getElementById('sticky-water'); if (stickyWaterEl2) stickyWaterEl2.textContent = totalWater.toFixed(1);

    if (!waterPerTank || totalWater <= 0) {
        const sumTanksEl = document.getElementById('sum-tanks'); if (sumTanksEl) sumTanksEl.textContent = '-';
        const stickyTanksEl2 = document.getElementById('sticky-tanks'); if (stickyTanksEl2) stickyTanksEl2.textContent = '-';
        const sumPartialEl = document.getElementById('sum-partial'); if (sumPartialEl) sumPartialEl.textContent = '-';
        updateProductTotals(totalHa, totalWater, null);
        return;
    }

    let totalTanks = Math.ceil(totalWater / waterPerTank);
    let partial = totalWater - (Math.floor(totalWater / waterPerTank) * waterPerTank);

    const sumTanksEl2 = document.getElementById('sum-tanks'); if (sumTanksEl2) sumTanksEl2.textContent = totalTanks;
    const stickyTanksEl3 = document.getElementById('sticky-tanks'); if (stickyTanksEl3) stickyTanksEl3.textContent = totalTanks;
    const sumPartialEl2 = document.getElementById('sum-partial'); if (sumPartialEl2) sumPartialEl2.textContent = partial > 0 ? partial.toFixed(1) + ' L' : '0 L';

    updateProductTotals(totalHa, totalWater, waterPerTank);
    renderTankBreakdown(totalWater, waterPerTank);
}

function updateProductTotals(totalHa, totalWater, waterPerTank) {
    const mode = getMode();
    let productCount = 0;

    document.querySelectorAll('.product-card').forEach(card => {
        const rate = parseFloat(card.querySelector('.qty-input').value || 0);
        if (!rate) {
            card.querySelector('.total-qty').textContent = '-';
            card.querySelector('.per-tank').textContent = '-';
            return;
        }

        productCount++;

        let totalQty = 0;
        let perTank = '-';

        if (mode === "per_100l") {
            totalQty = (totalWater / 100) * rate;
            if (waterPerTank) {
                perTank = ((waterPerTank / 100) * rate).toFixed(1);
            }
        }
        else if (mode === "per_ha_tank") {
            totalQty = totalHa * rate;
            if (waterPerTank && totalWater > 0) {
                perTank = ((waterPerTank / (totalWater / totalHa)) * rate).toFixed(1);
            }
        }
        else if (mode === "per_ha_direct") {
            totalQty = totalHa * rate;
            perTank = '-';
        }

        card.querySelector('.total-qty').textContent = totalQty > 0 ? totalQty.toFixed(1) : '-';
        card.querySelector('.per-tank').textContent = perTank;
    });

    const sumProductsEl = document.getElementById('sum-products'); if (sumProductsEl) sumProductsEl.textContent = productCount;
    const stickyProductsEl = document.getElementById('sticky-products'); if (stickyProductsEl) stickyProductsEl.textContent = productCount;
}

function renderTankBreakdown(totalWater, waterPerTank) {
    // Tank breakdown UI removed; sticky bar contains summary values.
    return;
}

function validateSprayForm(mode, projects, lines) {
    const errors = [];
    const sprayDate = document.getElementById('spray_date').value;
    const sprayDescription = (document.getElementById('spray_description').value || '').trim();
    const warehouseId = document.getElementById('warehouse_id').value;
    const methodId = document.getElementById('method_id')?.value;
    const waterPerTank = parseFloat(document.getElementById('global_water_per_tank').value) || 0;
    const waterPerHa = parseFloat(document.getElementById('global_water_per_ha').value) || 0;

    if (!sprayDate) {
        errors.push('Please select a spray date.');
    }
    if (!sprayDescription) {
        errors.push('Please enter a description.');
    }
    if (new Date(sprayDate) < new Date().setHours(0, 0, 0, 0)) {
        errors.push('Spray date cannot be in the past.');
    }
    if (!warehouseId) {
        errors.push('Please select a warehouse.');
    }
    if (!projects.length) {
        errors.push('Please select at least one project.');
    }
    if (!lines.length) {
        errors.push('Please add at least one product line.');
    }
    if (mode !== 'per_ha_direct' && !methodId) {
        errors.push('Please select an application method.');
    }
    if (mode === 'per_100l') {
        if (!waterPerTank || waterPerTank <= 0) {
            errors.push('Please enter the water per tank.');
        }
        document.querySelectorAll('#project_ids option:checked').forEach((o, idx) => {
            const rows = document.querySelectorAll('.project-row:not(.project-head)');
            const row = rows[idx];
            const totalWaterInput = row?.querySelector('.project-water-total');
            const waterPerHaInput = row?.querySelector('.project-water-input');
            
            const totalWater = parseFloat(totalWaterInput?.value || 0);
            const waterPerHa = parseFloat(waterPerHaInput?.value || 0);
            
            if (!totalWater && !waterPerHa) {
                errors.push(`Enter water per hectare or total water for project ${o.textContent}.`);
            }
        });
    }
    if (mode === 'per_ha_tank') {
        const totalWaterInput = parseFloat(document.getElementById('global_total_water').value) || 0;
        const waterPerHaInput = parseFloat(document.getElementById('global_water_per_ha').value) || 0;
        if (!totalWaterInput && !waterPerHaInput) {
            errors.push('Please enter spray volume per hectare or total water.');
        }
        if (!waterPerTank || waterPerTank <= 0) {
            errors.push('Please enter the water per tank.');
        }
    }

    document.querySelectorAll('.product-card').forEach((card, idx) => {
        const select = card.querySelector('.product-select');
        const rate = parseFloat(card.querySelector('.qty-input').value || 0);
        if (!select.value) {
            errors.push(`Select a product for line ${idx + 1}.`);
        }
        if (!rate || rate <= 0) {
            errors.push(`Enter a valid rate for product line ${idx + 1}.`);
        }
    });

    // Check for duplicate products
    const selectedProducts = new Map();
    document.querySelectorAll('.product-card').forEach((card, idx) => {
        const select = card.querySelector('.product-select');
        if (select.value) {
            if (selectedProducts.has(select.value)) {
                const productName = select.options[select.selectedIndex].text;
                errors.push(`Product "${productName}" is selected more than once.`);
            } else {
                selectedProducts.set(select.value, idx);
            }
        }
    });

    return errors;
}

// Bidirectional water calculation for per_ha_tank mode (global fields)
function syncWaterFields() {
    const totalHa = parseFloat(document.getElementById('total-ha').textContent) || 0;
    const waterPerHa = parseFloat(document.getElementById('global_water_per_ha').value) || 0;
    const totalWater = parseFloat(document.getElementById('global_total_water').value) || 0;

    if (totalHa <= 0) return;

    // If user just edited water_per_ha, update total_water
    if (event && event.target.id === 'global_water_per_ha' && waterPerHa > 0) {
        const calculated = totalHa * waterPerHa;
        document.getElementById('global_total_water').value = calculated.toFixed(1);
    }
    // If user just edited total_water, update water_per_ha
    else if (event && event.target.id === 'global_total_water' && totalWater > 0) {
        const calculated = totalWater / totalHa;
        document.getElementById('global_water_per_ha').value = calculated.toFixed(1);
    }
}

// Bidirectional water calculation for per_100l mode (per-project fields)
function syncProjectWaterFields(row) {
    if (!row || !event) return;

    const ha = parseFloat(row.querySelector('div:nth-child(2)').textContent) || 0;
    const waterPerHaInput = row.querySelector('.project-water-input');
    const totalWaterInput = row.querySelector('.project-water-total');

    if (ha <= 0) return;

    const waterPerHa = parseFloat(waterPerHaInput.value) || 0;
    const totalWater = parseFloat(totalWaterInput.value) || 0;

    // If user just edited water_per_ha, update total_water
    if (event.target === waterPerHaInput && waterPerHa > 0) {
        const calculated = ha * waterPerHa;
        totalWaterInput.value = calculated.toFixed(1);
    }
    // If user just edited total_water, update water_per_ha
    else if (event.target === totalWaterInput && totalWater > 0) {
        const calculated = totalWater / ha;
        waterPerHaInput.value = calculated.toFixed(1);
    }
}

// Modal management for editing defaults
let currentEditingCard = null;

function openEditDefaultsModal(card, regNumber, witholdingPeriod, func) {
    currentEditingCard = card;
    document.getElementById('modal-reg-number').value = regNumber || '';
    document.getElementById('modal-witholding-period').value = witholdingPeriod || '';
    document.getElementById('modal-function').value = func || '';
    document.getElementById('edit-defaults-modal').style.display = 'flex';
}

function closeEditDefaultsModal() {
    document.getElementById('edit-defaults-modal').style.display = 'none';
    currentEditingCard = null;
}

function saveEditDefaults() {
    if (!currentEditingCard) return;
    
    currentEditingCard.find('.line-reg-number').val(document.getElementById('modal-reg-number').value);
    currentEditingCard.find('.line-witholding-period').val(document.getElementById('modal-witholding-period').value);
    currentEditingCard.find('.line-function').val(document.getElementById('modal-function').value);
    
    closeEditDefaultsModal();
}

// Event Listeners
document.querySelectorAll('input[name="dose_mode"]').forEach(r => {
    r.addEventListener('change', renderModeUI);
});

// Validate crop consistency when projects change
$('#project_ids').on('change', function() {
    const selectedIds = $(this).val() || [];
    
    if (selectedIds.length <= 1) {
        // Single or no project: always ok
        updateProjectConfigs();
        return;
    }

    // Get crop IDs for all selected projects
    const cropIds = new Set();
    selectedIds.forEach(id => {
        const option = $(`#project_ids option[value="${id}"]`);
        const cropId = option.data('crop-id');
        if (cropId) cropIds.add(cropId);
    });

    // Check if all projects have the same crop
    if (cropIds.size > 1) {
        // Different crops selected - unselect the last one
        const lastId = selectedIds[selectedIds.length - 1];
        $(this).val(selectedIds.slice(0, -1)).trigger('change');
        
        Swal.fire({
            icon: 'warning',
            title: 'Different Crops',
            text: 'All selected projects must belong to the same crop. The last selection has been removed.',
            confirmButtonText: 'OK'
        });
        return;
    }

    // All projects have same crop: proceed
    updateProjectConfigs();
});

// Live recalculation
document.addEventListener('input', function (e) {
    if (e.target.matches('.project-water-input')) {
        const row = e.target.closest('.project-row');
        syncProjectWaterFields(row);
        recalcEverything();
    }
    if (e.target.matches('.project-water-total')) {
        const row = e.target.closest('.project-row');
        syncProjectWaterFields(row);
        recalcEverything();
    }
    if (e.target.matches('.qty-input')) {
        recalcEverything();
    }
    if (e.target.matches('#global_water_per_ha')) {
        syncWaterFields();
        recalcEverything();
    }
    if (e.target.matches('#global_total_water')) {
        syncWaterFields();
        recalcEverything();
    }
    if (e.target.matches('#global_water_per_tank')) {
        recalcEverything();
    }
});



document.addEventListener('change', function (e) {
    if (e.target.matches('#method_id')) {
        recalcEverything();
    }
});

// Event listener for warehouse change
$('#warehouse_id').on('change', function() {
    const warehouseId = $(this).val();
    updateProjectsForWarehouse(warehouseId);
    recalcEverything(); // Recalculate if needed
});

// Event listener for date change
document.getElementById('spray_date').addEventListener('change', updateSprayWeek);


// Close modal when clicking outside of it
document.getElementById('edit-defaults-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeEditDefaultsModal();
    }
});

// ensure context updates when warehouse/projects change
$('#warehouse_id').on('change', function() {
    const warehouseId = $(this).val();
    updateProjectsForWarehouse(warehouseId);
    recalcEverything();
});