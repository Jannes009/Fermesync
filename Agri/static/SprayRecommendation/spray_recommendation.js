let isRestoringDraft = false;

$('.select2').each(function() {
    const placeholder = $(this).data('placeholder');
    $(this).select2({
        width: '100%',
        placeholder: placeholder || undefined,
        allowClear: false
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

$('#spray_date').on('change', defaultDescription);

// Custom initialization for product selects with better width control
function initProductSelects() {
    $('.product-select').each(function() {
        const $select = $(this);
        
        if (!$select.data('select2')) {
            const placeholder = $select.data('placeholder') || 'Select product';
            $select.select2({
                width: '100%',
                placeholder: placeholder || undefined,
                allowClear: false,
                dropdownAutoWidth: true,
                dropdownCssClass: 'product-dropdown',
                containerCssClass: 'product-select-container'
            });

            // FIX: Force immediate open on mobile touch devices
            $select.data('select2').$container.on('touchstart', function(e) {
                // Check if it's already open to prevent unnecessary toggles
                if (!$select.data('select2').isOpen()) {
                    e.preventDefault(); // Prevents the browser's delayed click emulation
                    $select.select2('open');
                }
            });
        }
        
        // Sync closed select width to opened dropdown min-width
        $select.on('select2:opening', function() {
            const $container = $select.data('select2').$container;
            const closedWidth = $container.outerWidth();
            const $dropdown = $select.data('select2').$dropdown;
            if ($dropdown && closedWidth) {
                $dropdown.css('min-width', closedWidth + 'px');
            }
        });
    });
}


let PRODUCT_OPTIONS = "";
let PRODUCTS_DATA = {}; // Store product data for modal editing: {stock_id: {reg_number, witholding_period, function}}

async function updateMethods(projectId) {
    const methodSelect = $('#method_id');
    methodSelect.empty().append('<option value="">Loading methods...</option>');
    methodSelect.prop('disabled', true).trigger('change');

    if (!projectId) {
        methodSelect.empty().append('<option value="">Select a project first</option>');
        methodSelect.val('').trigger('change');
        return;
    }

    try {
        const response = await request(`/agri/spray-recommendation/methods/${encodeURIComponent(projectId)}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Failed to fetch spray methods');
        }
        console.log('Fetched methods for project', projectId, data.methods);
        methodSelect.empty().append('<option value="">Select method</option>');
        data.methods.forEach(method => {
            methodSelect.append(new Option(method.name, method.id));
        });
        methodSelect.prop('disabled', false).trigger('change');
        
        // Return the methods data for the caller
        return data.methods;
    } catch (error) {
        methodSelect.empty().append('<option value="">Unable to load methods</option>');
        methodSelect.prop('disabled', true).trigger('change');
        Swal.fire({ icon: 'error', title: 'Error fetching methods', text: error.message });
        // Return empty array on error
        return [];
    }
}

// Function to fetch products when warehouse or projects change
async function updateProducts(projectIds) {
    // Only fetch when both a warehouse and at least one project are selected
    if (!projectIds || !projectIds.length) {
        PRODUCT_OPTIONS = '<option value=""></option>';
        $('.product-select').each(function() {
            $(this).html(PRODUCT_OPTIONS).trigger('change');
        });
        return;
    }

    const pidParam = encodeURIComponent(projectIds.join(','));
    const response = await request(`/agri/fetch_products_linked_with_projects?project_ids=${pidParam}`);
    const data = await response.json();

    if (!data.success) {
        Swal.fire({ icon: 'error', title: 'Error fetching products', text: data.message || 'Failed to fetch products' });
    } else {
        if (data.products && data.products.length > 0) {
            // Build options HTML with useful data-* attributes
            let options = '<option value=""></option>';
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
                // Re-initialize select2 with product-specific options and placeholder
                const placeholder = $sel.data('placeholder') || 'Select product';
                $sel.select2({
                    width: '100%',
                    placeholder: placeholder || undefined,
                    allowClear: false,
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
            if (data.products.length > 0 
                && document.querySelectorAll('.product-card').length === 0
                && !isRestoringDraft) {
                addLine();
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
    }
}


async function updateProjects() {
    const $projectSelect = $('#project_ids');
    $projectSelect.empty();

    try {
        // Fetch projects for current user (server will scope by user's warehouses when warehouse_id omitted)
        const response = await request(`/agri/fetch_projects_for_warehouse`);
        const data = await response.json();
        console.log(data)
        if (data.success === true && data.projects && data.projects.length > 0) {
            data.projects.forEach(project => {
                const option = document.createElement('option');
                option.value = project.project_id;
                option.text = `${project.project_code}`;
                option.setAttribute('data-ha', project.proj_attr_ha);
                option.setAttribute('data-crop-id', project.proj_attr_crop_id);
                option.setAttribute('data-crop-theme-color', project.crop_theme_color || '');
                if (project.proj_attr_block_no) option.setAttribute('data-block-no', project.proj_attr_block_no);
                if (project.proj_attr_whse_id) option.setAttribute('data-whse-id', project.proj_attr_whse_id);
                $projectSelect.append(option);
            });
            $projectSelect.prop('disabled', false).trigger('change');
        } else {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.disabled = true;
            placeholder.text = data.message || 'No projects available';
            $projectSelect.append(placeholder);
            $projectSelect.prop('disabled', true).trigger('change');
        }

        // Clear selected projects and product options until a project is chosen
        $projectSelect.val(null).trigger('change');
        updateProducts([]);
        // Ensure submit availability reflects current state (no product lines initially)
        updateSubmitAvailability();
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

// Function to apply crop theme color to page background
function applyPageThemeColor(colorHex) {
    const body = document.querySelector('.with-fixed-taskbar');
    if (!colorHex) {
        // Reset to default: white background
        if (body) body.style.backgroundColor = '';
    } else {
        // Validate hex color format and apply with transparency
        if (/^#[0-9A-F]{6}$/i.test(colorHex)) {
            // Convert hex to RGB with alpha for soft background effect
            const rgb = parseInt(colorHex.slice(1), 16);
            const r = (rgb >> 16) & 255;
            const g = (rgb >> 8) & 255;
            const b = rgb & 255;
            const rgba = `rgba(${r}, ${g}, ${b}, 0.7)`;
            
            if (body) body.style.backgroundColor = rgba;
        }
    }
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
    // tank plan removed; updates now appear in the sticky bar

    document.querySelectorAll('.per-100l-field').forEach(i => i.classList.add('hidden'));
    document.querySelectorAll('.per-ha-tank-field').forEach(i => i.classList.add('hidden'));
    document.querySelectorAll('.water-per-tank-field').forEach(i => i.classList.add('hidden'));

    // Disable all inputs in hidden sections first
    document.querySelectorAll('#tank-fields input, #tank-fields select, .per-100l-field input, .per-ha-tank-field input').forEach(el => {
        el.disabled = true;
    });

    if (mode === "per_100l") {
        document.getElementById('tank-fields').classList.remove('hidden');
        document.querySelectorAll('.water-per-tank-field').forEach(i => i.classList.remove('hidden'));
        document.querySelectorAll('.per-100l-field').forEach(i => i.classList.remove('hidden'));
        // Enable visible inputs
        document.querySelectorAll('.per-100l-field input').forEach(i => i.disabled = false);
        document.querySelectorAll('#tank-fields select, #tank-fields input:not(.per-ha-tank-field input)').forEach(el => el.disabled = false);
    }

    if (mode === "per_ha_tank") {
        document.getElementById('tank-fields').classList.remove('hidden');
        document.querySelectorAll('.water-per-tank-field').forEach(i => i.classList.remove('hidden'));
        document.querySelectorAll('.per-ha-tank-field').forEach(i => i.classList.remove('hidden'));
        // Enable visible inputs
        document.querySelectorAll('.per-ha-tank-field input').forEach(i => i.disabled = false);
        document.querySelectorAll('#tank-fields select, #tank-fields input:not(.per-100l-field input)').forEach(el => el.disabled = false);
    }

    if (mode === "per_ha_direct") {
        document.getElementById('tank-fields').classList.remove('hidden');
        document.getElementById('method_id').disabled = false;
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
        // Expose project id and ha on the row so defaults can be applied later
        row.setAttribute('data-project-id', id);
        row.setAttribute('data-ha', ha);

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
    const projectIds = $('#project_ids').val() || [];
    updateProducts(projectIds);
    FormStateManager.scheduleSave();
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
            <div class="product-select-field">
            <label class="product-select-label">Product</label>
                <select class="product-select" data-placeholder="Select product">
                    ${PRODUCT_OPTIONS || '<option value=""></option>'}
                </select>
                <input type="hidden" class="line-reg-number" value="">
                <input type="hidden" class="line-witholding-period" value="">
                <input type="hidden" class="line-function" value="">
            </div>

            <div class="rate-field">
                <label class="rate-label">Rate /100L</label>
                <input class="qty-input" type="number" step="0.01" placeholder="Qty">
            </div>

            <div class="total-field">
                <label>Total Qty</label>
                <div class="readonly-box total-qty">-</div>
            </div>

            <div class="per-tank-field">
                <label>Per Tank</label>
                <div class="readonly-box per-tank">-</div>
            </div>

            <div class="actions-field" style="display: flex; gap: 8px;">
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
            if (isDuplicate && !isRestoringDraft) {
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
        FormStateManager.scheduleSave();
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
        updateSubmitAvailability();
        FormStateManager.scheduleSave();
    });
    
    updateLineLabels();
    recalcEverything();
    updateSubmitAvailability();
    FormStateManager.scheduleSave();
}

function clearLines() {
    document.getElementById('lines').innerHTML = '';
    recalcEverything();
    updateSubmitAvailability();
    FormStateManager.scheduleSave();
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
    if (sumWaterEl) sumWaterEl.textContent = totalWater.toFixed(2) + ' L';
    const stickyWaterEl2 = document.getElementById('sticky-water'); if (stickyWaterEl2) stickyWaterEl2.textContent = totalWater.toFixed(2);

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
    const sumPartialEl2 = document.getElementById('sum-partial'); if (sumPartialEl2) sumPartialEl2.textContent = partial > 0 ? partial.toFixed(2) + ' L' : '0 L';

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
                perTank = ((waterPerTank / 100) * rate).toFixed(2);
            }
        }
        else if (mode === "per_ha_tank") {
            totalQty = totalHa * rate;
            if (waterPerTank && totalWater > 0) {
                perTank = ((waterPerTank / (totalWater / totalHa)) * rate).toFixed(2);
            }
        }
        else if (mode === "per_ha_direct") {
            totalQty = totalHa * rate;
            perTank = '-';
        }

        card.querySelector('.total-qty').textContent = totalQty > 0 ? totalQty.toFixed(2) : '-';
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
    const methodId = document.getElementById('method_id')?.value;
    const waterPerTank = parseFloat(document.getElementById('global_water_per_tank').value) || 0;
    const waterPerHa = parseFloat(document.getElementById('global_water_per_ha').value) || 0;

    if (!sprayDate) {
        errors.push('Please select a spray date.');
    }
    if (!sprayDescription) {
        errors.push('Please enter a description.');
    }
    if (!projects.length) {
        errors.push('Please select at least one project.');
    }
    if (!lines.length) {
        errors.push('Please add at least one product line.');
    }
    if (!methodId) {
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

    // product line validation handled below (supports jQuery/DOM `lines` parameter)
    // Validate product lines: accept `lines` param (DOM nodes or jQuery objects) or fall back to `.product-card`
    const cards = (lines && lines.length) ? Array.from(lines) : Array.from(document.querySelectorAll('.product-card'));
    const selectedProducts = new Map();
    cards.forEach((line, idx) => {
        console.log(line);

        if (!line.stock_id) {
            errors.push(`Select a product for line ${idx + 1}.`);
        }
        if (line.total_qty <= 0) {
            errors.push(`Enter a valid rate for product line ${idx + 1}.`);
        }

        // duplicate check
        if (line.stock_id) {
            if (selectedProducts.has(line.stock_id)) {
                errors.push(`Product "${line.product_name}" is selected more than once.`);
            } else {
                selectedProducts.set(line.stock_id, idx);
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
        document.getElementById('global_total_water').value = calculated.toFixed(2);
    }
    // If user just edited total_water, update water_per_ha
    else if (event && event.target.id === 'global_total_water' && totalWater > 0) {
        const calculated = totalWater / totalHa;
        document.getElementById('global_water_per_ha').value = calculated.toFixed(2);
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
        totalWaterInput.value = calculated.toFixed(2);
    }
    // If user just edited total_water, update water_per_ha
    else if (event.target === totalWaterInput && totalWater > 0) {
        const calculated = totalWater / ha;
        waterPerHaInput.value = calculated.toFixed(2);
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
    FormStateManager.scheduleSave();
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
        if (selectedIds.length === 0) {
            // No projects selected: reset page background to default
            applyPageThemeColor(null);
        }
        const color = $(`#project_ids option[value="${selectedIds[0]}"]`).attr('data-crop-theme-color');
        applyPageThemeColor(color);
        updateProjectConfigs();
        if (!window.isRestoringDraft) {
            updateMethods(selectedIds[0]).then(() => fetchAndApplyProjectDefaults(selectedIds[0]));
        } else {
            fetchAndApplyProjectDefaults(selectedIds[0]);
        }
        defaultDescription();
        updateContextDataset();
        return;
    }

    // Get crop IDs and theme color for all selected projects
    const cropIds = new Set();
    let themeColor = null;
    selectedIds.forEach(id => {
        const option = $(`#project_ids option[value="${id}"]`);
        const cropId = option.attr('data-crop-id');
        const color = option.attr('data-crop-theme-color');
        if (cropId) cropIds.add(cropId);
        if (color) themeColor = color;
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

    // Ensure all selected projects belong to the same warehouse
    const whseIds = new Set();
    selectedIds.forEach(id => {
        const option = $(`#project_ids option[value="${id}"]`);
        const whseId = option.attr('data-whse-id');
        if (whseId) whseIds.add(String(whseId));
    });
    if (whseIds.size > 1) {
        const lastId = selectedIds[selectedIds.length - 1];
        $(this).val(selectedIds.slice(0, -1)).trigger('change');
        Swal.fire({
            icon: 'warning',
            title: 'Multiple Warehouses',
            text: 'All selected projects must belong to the same warehouse. The last selection has been removed.',
            confirmButtonText: 'OK'
        });
        return;
    }

    // Apply theme color if available
    if (themeColor) {
        console.log('Applying theme color:', themeColor);
        applyPageThemeColor(themeColor);
    }

    // Generate default description: "week WW - block1, block2"
    defaultDescription();

    // All projects validated: proceed
    updateProjectConfigs();
    // After rows are rendered, fetch and apply per-project defaults for each selected project
    const methodsReady = window.isRestoringDraft
        ? Promise.resolve()
        : updateMethods(selectedIds[0]);
    methodsReady.then(() => {
        selectedIds.forEach(id => fetchAndApplyProjectDefaults(id));
    });
    // Update products for selected projects using the common warehouse id
    const selectedProjectIds = selectedIds.map(x => Number(x));
    updateProducts(selectedProjectIds);
    updateContextDataset();
    FormStateManager.scheduleSave();
});

async function fetchAndApplyProjectDefaults(projectId) {
    if (!projectId) return;
    try {
        const res = await request(`/agri/spray-recommendation/project_defaults/${encodeURIComponent(projectId)}`);
        const json = await res.json();
        if (!json.success) {
            console.warn('No defaults returned for project', projectId, json);
            return;
        }
        const defs = json.defaults || json; // support either { success, defaults:{...} } or direct object
        console.log(defs)
        // 1) Set spray method (if present)
        if (defs.default_spray_method_id && !window.isRestoringDraft) {
            const methodEl = document.getElementById('method_id');
            console.log('Setting default spray method to', defs.default_spray_method_id);
            if (methodEl) {
                methodEl.value = defs.default_spray_method_id;
                // trigger change if other code listens
                methodEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        // 2) Select dose mode and re-render UI
        if (defs.default_dose) {
            const radio = document.querySelector(`input[name="dose_mode"][value="${defs.default_dose}"]`);
            if (radio) {
                radio.checked = true;
                renderModeUI(); // update UI to match the mode
            }
        }

        // 3) Prefill global tank/ha fields so both per_100l and per_ha_tank flows are seeded
        if (defs.default_water_per_ha !== undefined && defs.default_water_per_ha !== null) {
            const gHa = document.getElementById('global_water_per_ha');
            if (gHa) gHa.value = defs.default_water_per_ha;
        }
        if (defs.default_water_per_tank !== undefined && defs.default_water_per_tank !== null) {
            const gTank = document.getElementById('global_water_per_tank');
            if (gTank) gTank.value = defs.default_water_per_tank;
        } 

        // 4) Prefill per-project water inputs for project
        const opt = $(`#project_ids option[value="${projectId}"]`);
        // read per-project override attributes if present
        const projDefHa = defs.default_water_per_ha;
        const projDefTank = defs.default_water_per_tank;

        // find matching project row rendered under #project-configs
        const row = document.querySelector(`#project-configs .project-row[data-project-id="${projectId}"]`);
        console.log('Applying defaults to project row:', row, 'per-ha:', projDefHa, 'per-tank:', projDefTank);
        if (!row) return;

        const perHaInput = row.querySelector('.project-water-input');
        const totalInput = row.querySelector('.project-water-total');

        // prefer setting per-ha, also set total (ha * per-ha) if ha available
        const ha = parseFloat(opt.attr('data-ha') || row.dataset.ha || 0);

        if (perHaInput && projDefHa !== undefined && projDefHa !== null) {
            perHaInput.value = projDefHa;
        }
        if (totalInput && projDefHa !== undefined && projDefHa !== null && ha > 0) {
            totalInput.value = (parseFloat(projDefHa) * ha).toFixed(2);
        }

        // if you want to seed any project-specific 'per-tank' UI fields, add here (e.g. per-project tank inputs)
        // if (projDefTank !== undefined && projDefTank !== null) {
        //     // global fields already set; if there are per-row tank inputs, set them similarly:
        //     const perTankInput = row.querySelector('.project-water-per-tank');
        //     if (perTankInput) perTankInput.value = projDefTank;
        // }
        // 5) Recalculate totals/UI after applying defaults
        syncWaterFields();
        recalcEverything();

        // 6) update global total water
        if (defs.default_water_per_ha !== undefined && defs.default_water_per_ha !== null && defs.default_water_per_tank !== undefined && defs.default_water_per_tank !== null) {
            const totalHa = parseFloat(document.getElementById('total-ha').textContent) || 0;
            const totalWater = totalHa * parseFloat(defs.default_water_per_ha);
            document.getElementById('global_total_water').value = totalWater.toFixed(2);
        }
        
    } catch (err) {
        console.error('Failed to fetch or apply project defaults', err);
        Swal.fire({ icon: 'error', title: 'Error', text: 'Failed to load project defaults' });
    }
}

function defaultDescription() {
    try {
        const selectedIds = $('#project_ids').val() || [];
        const dateVal = document.getElementById('spray_date')?.value;
        if (!dateVal) return;
        const d = new Date(dateVal);
        const { week } = getISOWeekNumber(d);
        const blocks = [];
        selectedIds.forEach(id => {
            const option = $(`#project_ids option[value="${id}"]`);
            const b = option.attr('data-block-no');
            if (b) blocks.push(b);
        });
        const descEl = document.getElementById('spray_description');
        if (descEl) {
            // Deduplicate and clean block numbers while preserving order
            const cleaned = blocks.map(x => (x || '').toString().trim()).filter(x => x !== '');
            const unique = cleaned.filter((v, i, a) => a.indexOf(v) === i);
            const blockPart = unique.length ? ` - ${unique.join(', ')}` : '';
            descEl.value = `Week ${String(week).padStart(2,'0')}${blockPart}`;
        }
    } catch (err) {
        console.log('Failed to auto-generate description:', err);
    }
}

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

// Load projects for current user on page load
updateProjects();

// Disable form submission on Enter for most inputs to avoid accidental submits
document.getElementById('spray-form').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    const t = e.target;
    if (!t) return;
    const tag = t.tagName;
    // allow Enter in textarea and allow buttons/submit types to function
    if (tag === 'TEXTAREA') return;
    if (t.type === 'submit' || t.type === 'button') return;
    // allow Search fields inside Select2 to work (they have select2-search__field class)
    if (t.classList && t.classList.contains('select2-search__field')) return;
    e.preventDefault();
});

// Disable submit button when no product lines exist
function updateSubmitAvailability() {
    const submit = document.querySelector('form#spray-form button[type="submit"]');
    if (!submit) return;
    const hasLines = document.querySelectorAll('.product-card').length > 0;
    submit.disabled = !hasLines;
}

// Ensure submit availability reflects initial state
updateSubmitAvailability();

// Event listener for date change
document.getElementById('spray_date').addEventListener('change', updateSprayWeek);


// Close modal when clicking outside of it
document.getElementById('edit-defaults-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeEditDefaultsModal();
    }
});

