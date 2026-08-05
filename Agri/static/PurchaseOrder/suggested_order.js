function initSuggestedOrder(container = document) {
    const weekInput = container.querySelector('#week');
    if (!weekInput) return;

    const tbody = container.querySelector('#results tbody');
    const detailTemplate = container.querySelector('#detail-row');
    let openDetail = null;
    const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

    function clear() { tbody.innerHTML = ''; openDetail = null; }

    function addDays(date, days) {
        const d = new Date(date.valueOf());
        d.setDate(d.getDate() + days);
        return d;
    }

    function isoWeekString(d) {
        const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
        const dayNum = date.getUTCDay() || 7;
        date.setUTCDate(date.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(date.getUTCFullYear(),0,1));
        const weekNo = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
        return `${date.getUTCFullYear()}-${String(weekNo).padStart(2,'0')}`;
    }

    function populateWeekSelect(before = 0, after = 2) {
        const select = weekInput;
        const today = new Date();
        select.innerHTML = '';
        let index = 0;
        for (let i = -before; i <= after; i++) {
            const dt = addDays(today, i * 7);
            const val = isoWeekString(dt);
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = val;
            select.appendChild(opt);
            if (i === 0) index = select.options.length - 1;
        }
        select.selectedIndex = index;
    }

    async function loadData() {
        const week = weekInput.value.trim();
        if (!week) return alert('Please enter week (YYYY-WW)');

        // clear old rows immediately and show loading placeholder
        clear();
        const loadingRow = document.createElement('tr');
        loadingRow.className = 'loading-row';
        loadingRow.innerHTML = `<td colspan="8" style="text-align:center; padding:1.25rem; color:#6b7280;">Loading suggested order data...</td>`;
        tbody.appendChild(loadingRow);

        const res = await fetch(`/agri/suggested-order/data?week=${encodeURIComponent(week)}`);
        const payload = await res.json();
        if (payload.status !== 'ok') {
            // remove loading row and show message
            loadingRow.remove();
            return alert(payload.message || 'Error');
        }

        // remove loading placeholder before rendering rows
        loadingRow.remove();

        for (const row of payload.data) {
            const tr = document.createElement('tr');

            function computeStatus(r) {
                const qty = Number(r.purchase_units_to_order || 0);
                if (!r.supplier_dc_link) return 'no-supplier';
                if (qty <= 0) return 'ok';
                return 'needs';
            }

            const status = computeStatus(row);

            // supplier select
            const supSelect = document.createElement('select');
            supSelect.className = 'sd-input';
            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = '—';
            supSelect.appendChild(emptyOpt);
            // fetch suppliers for this stock only
            let stockSuppliers = [];
            try {
                const ssres = await fetch(`/agri/suggested-order/stock-suppliers/${encodeURIComponent(row.stock_link)}`);
                const sspayload = await ssres.json();
                if (sspayload.status === 'ok') stockSuppliers = sspayload.suppliers || [];
            } catch (e) {
                stockSuppliers = [];
            }

            for (const s of stockSuppliers) {
                console.log(s)
                const opt = document.createElement('option');
                opt.value = s.dc_link;
                opt.textContent = `${s.name} — ${s.last_invoice_price ? 'R' + nf.format(s.last_invoice_price) + ' / ' + (s.unit_code || '') : 'No price'}`;
                opt.dataset.supplierName = s.name;
                opt.dataset.price = s.last_invoice_price || 0;
                opt.dataset.unitId = s.unit_id || '';
                if (row.supplier_dc_link && Number(row.supplier_dc_link) === Number(s.dc_link)) opt.selected = true;
                supSelect.appendChild(opt);
            }

            tr.dataset.stockLink = row.stock_link;
            tr.dataset.lastInvoicePrice = row.last_invoice_price || 0;
            tr.dataset.purchaseUnitsToOrder = row.purchase_units_to_order || 0;
            tr.dataset.purchasingUom = row.purchasing_uom || '';
            tr.dataset.purchaseUnitId = row.purchase_unit_id || '';
            console.log(row.purchase_unit_id)
            tr.dataset.productName = row.stock_description || '';

            tr.innerHTML = `
                <td class="col-action"><button class="expand" data-id="${row.stock_link}" aria-expanded="false">+</button></td>
                <td class="col-num"><span class="status" data-status="${status}">${status === 'ok' ? '✔' : status === 'needs' ? '⚠' : '🚫'}</span></td>
                <td class="col-product">${row.stock_description}</td>
                <td class="col-num supplier-cell"></td>
                <td class="col-num">${nf.format(row.purchase_unit_on_hand)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num">${nf.format(row.purchase_unit_on_po)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num">${nf.format(row.purchase_units_needed)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num qty-to-order">${nf.format(row.purchase_units_to_order)}<span class="uom">${row.purchasing_uom}</span></td>
            `;
            tbody.appendChild(tr);
            tr.querySelector('.supplier-cell').appendChild(supSelect);

            supSelect.addEventListener('change', function () {
                // update price metadata from selected option
                const opt = supSelect.selectedOptions && supSelect.selectedOptions[0];
                const price = opt && opt.dataset ? Number(opt.dataset.price || 0) : 0;
                tr.dataset.lastInvoicePrice = price;
                renderPreview();
                const st = (supSelect.value === '' ? 'no-supplier' : (Number(tr.dataset.purchaseUnitsToOrder) > 0 ? 'needs' : 'ok'));
                const span = tr.querySelector('.status');
                span.dataset.status = st;
                span.textContent = st === 'ok' ? '✔' : st === 'needs' ? '⚠' : '🚫';
            });

            const detailRow = detailTemplate.content.cloneNode(true);
            const detailTr = detailRow.querySelector('tr');
            const detailContent = detailRow.querySelector('.detail-content');
            detailTr.style.display = 'none';
            tbody.appendChild(detailTr);

            tr.querySelector('.expand').addEventListener('click', async function (e) {
                const btn = e.currentTarget;
                const id = btn.getAttribute('data-id');
                if (openDetail && openDetail !== detailTr) {
                    openDetail.style.display = 'none';
                    const prevBtn = openDetail.previousElementSibling && openDetail.previousElementSibling.querySelector('.expand');
                    if (prevBtn) prevBtn.textContent = '+';
                }

                if (detailTr.style.display === 'none') {
                    detailContent.innerHTML = 'Loading...';
                    detailTr.style.display = '';
                    btn.textContent = '-';
                    btn.setAttribute('aria-expanded', 'true');
                    openDetail = detailTr;
                    const dres = await fetch(`/agri/suggested-order/detail/${id}?week=${encodeURIComponent(week)}`);
                    const dpayload = await dres.json();
                    if (dpayload.status !== 'ok') {
                        detailContent.innerHTML = 'Error loading details';
                        return;
                    }
                    let html = '<table class="detail-table"><thead><tr><th></th><th>Warehouse</th><th>Stock Description</th><th class="col-num">Qty On Hand</th><th class="col-num">Qty On PO</th><th class="col-num">Qty to Order</th><th class="col-num">Qty On IBT</th></tr></thead><tbody>';
                    for (const w of dpayload.warehouses) {
                        html += `<tr data-whse-id="${w.whse_id}" data-stock-link="${w.stock_link}"><td class="action-col"><button class="expand expand-spray" data-whse="${w.whse_id}" data-stock="${w.stock_link}" aria-expanded="false">+</button></td><td>${w.whse_name}</td><td>${w.stock_description}</td><td class="col-num">${nf.format(w.qty_on_hand)}<span class="uom"> ${w.stocking_uom}</span></td><td class="col-num">${nf.format(w.qty_on_po)}<span class="uom"> ${w.stocking_uom}</span></td><td class="col-num">${nf.format(w.purchase_units_needed)}<span class="uom"> ${w.purchasing_unit_code}</span></td><td class="col-num">${nf.format(w.PurchaseQtyOnIBT)}<span class="uom"> ${w.purchasing_unit_code}</span></td></tr>`;
                    }
                    html += '</tbody></table>';
                    detailContent.innerHTML = html;

                    detailContent.querySelectorAll('.expand-spray').forEach(btn => {
                        btn.addEventListener('click', async function (e) {
                            const b = e.currentTarget;
                            const whseId = b.getAttribute('data-whse');
                            const stockLink = b.getAttribute('data-stock');
                            const parentTr = b.closest('tr');
                            const next = parentTr.nextElementSibling;
                            if (next && next.classList && next.classList.contains('spray-detail-row')) {
                                const isHidden = next.style.display === 'none';
                                if (isHidden) {
                                    next.style.display = '';
                                    b.textContent = '-';
                                    b.setAttribute('aria-expanded', 'true');
                                } else {
                                    next.style.display = 'none';
                                    b.textContent = '+';
                                    b.setAttribute('aria-expanded', 'false');
                                }
                                return;
                            }

                            const sres = await fetch(`/agri/suggested-order/detail/${encodeURIComponent(stockLink)}/warehouse/${encodeURIComponent(whseId)}?week=${encodeURIComponent(week)}`);
                            const spayload = await sres.json();
                            if (spayload.status !== 'ok') {
                                alert('Error loading spray details');
                                return;
                            }

                            let shtml = '<table class="detail-table"><thead><tr><th>Spray No</th><th>Description</th><th class="col-num">Recommended Qty</th><th class="col-num">Issue Finalised Qty</th></tr></thead><tbody>';
                            for (const s of spayload.sprays) {
                                shtml += `<tr class="clickable" title="View spray instruction" onclick="window.location.href='/agri/spray/${s.spray_id}'"><td>${s.spray_h_no}</td><td>${s.spray_h_description}</td><td class="col-num">${nf.format(s.recommended_qty)}<span class="uom"> ${s.stocking_uom}</span></td><td class="col-num">${nf.format(s.finalised_qty)}</td></tr>`;
                            }
                            shtml += '</tbody></table>';

                            const sprayRow = document.createElement('tr');
                            sprayRow.className = 'spray-detail-row';
                            sprayRow.innerHTML = `<td colspan="8" class="spray-detail-cell">${shtml}</td>`;
                            parentTr.parentNode.insertBefore(sprayRow, parentTr.nextSibling);
                            b.textContent = '-';
                            b.setAttribute('aria-expanded', 'true');
                        });
                    });
                } else {
                    detailTr.style.display = 'none';
                    btn.textContent = '+';
                    btn.setAttribute('aria-expanded', 'false');
                    openDetail = null;
                }
            });
        }
        renderPreview();
    }

    function updateRowVisibility(tr) {
        const filter = document.getElementById('filter_needs_only');
        if (!filter) return;
        const onlyNeeds = filter.checked;
        const qty = Number(tr.dataset.purchaseUnitsToOrder || 0);
        if (onlyNeeds && qty <= 0) tr.style.display = 'none';
        else tr.style.display = '';
    }

    const supplierOrderStatus = {};
    const supplierWarehouseSelection = {};
    const warehouseOptionsCache = {};
    const warehouseOptionsLoading = {};

    function getWarehouseCacheKey(stockIds) {
        return stockIds.slice().sort((a, b) => Number(a) - Number(b)).join(',');
    }

    async function ensureWarehouseOptions(stockIds) {
        const key = getWarehouseCacheKey(stockIds);
        if (warehouseOptionsCache[key]) return warehouseOptionsCache[key];
        if (warehouseOptionsLoading[key]) return warehouseOptionsLoading[key];

        warehouseOptionsLoading[key] = fetch('/agri/suggested-order/order-warehouses', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({stock_ids: stockIds})
        })
            .then(res => res.ok ? res.json() : Promise.reject(new Error('Unable to load warehouses')))
            .then(payload => {
                if (payload.status === 'ok') {
                    warehouseOptionsCache[key] = payload.warehouses || [];
                    return warehouseOptionsCache[key];
                }
                warehouseOptionsCache[key] = [];
                return [];
            })
            .catch(() => {
                warehouseOptionsCache[key] = [];
                return [];
            })
            .finally(() => { delete warehouseOptionsLoading[key]; });

        warehouseOptionsLoading[key].then(() => renderPreview());
        return warehouseOptionsLoading[key];
    }

    function renderPreview() {
        const preview = document.getElementById('poPreview');
        if (!preview) return;
        const groups = {};
        tbody.querySelectorAll('tr').forEach(tr => {
            if (tr.classList && (tr.classList.contains('detail-row') || tr.classList.contains('spray-detail-row'))) return;
            updateRowVisibility(tr);
            const qty = Number((tr.dataset.purchaseUnitsToOrder || 0));
            if (!qty || qty <= 0) return;
            const sel = tr.querySelector('select');
            const sup = sel ? sel.value || 'NO_SUP' : 'NO_SUP';
            if (!groups[sup]) groups[sup] = {lines: [], totalQty: 0, totalValue: 0, supplierName: '', stockIds: []};
            const price = Number(tr.dataset.lastInvoicePrice || 0);
            const desc = tr.dataset.productName || tr.querySelector('.col-product')?.textContent.trim() || '';
            const unit = tr.dataset.purchasingUom || '';
            groups[sup].lines.push({stock_link: tr.dataset.stockLink, product: desc, qty: qty, price: price, units: unit});
            groups[sup].stockIds.push(tr.dataset.stockLink);
            groups[sup].totalQty += qty;
            groups[sup].totalValue += qty * price;
            const opt = sel && sel.selectedOptions && sel.selectedOptions[0];
            groups[sup].supplierName = opt ? (opt.dataset.supplierName || opt.textContent || '') : groups[sup].supplierName;
        });

        let html = '<div class="po-preview">';
        html += '<div class="po-card-header" style="border:none;padding:0;margin-bottom:0"><div class="po-card-title">Purchase Orders Preview</div></div>';
        if (Object.keys(groups).length === 0) {
            html += '<div class="po-card"><div class="po-card-body open"><div class="sd-hint">No items selected for ordering.</div></div></div>';
        } else {
            for (const k of Object.keys(groups)) {
                const g = groups[k];
                const supplierLabel = g.supplierName || (k === 'NO_SUP' ? 'No Supplier' : k);
                const warehouseKey = getWarehouseCacheKey(g.stockIds);
                const warehouseOptions = warehouseOptionsCache[warehouseKey] || [];
                if (!warehouseOptions.length && !warehouseOptionsLoading[warehouseKey]) {
                    ensureWarehouseOptions(g.stockIds);
                }
                const selectedWarehouse = supplierWarehouseSelection[k] || '';
                const hasWarehouseSelection = !!(warehouseOptions.length && selectedWarehouse);
                html += `<div class="po-card" data-supplier="${k}">`;
                html += '<div class="po-card-header">';
                html += `<div><div class="po-card-title">${supplierLabel}</div><div class="po-card-summary">${g.lines.length} products · Qty ${nf.format(g.totalQty)} · R ${nf.format(g.totalValue)}</div></div>`;
                html += '<div class="po-card-actions">';
                if (k !== 'NO_SUP' && k !== '') {
                    html += '<div class="warehouse-picker-inline">';
                    if (warehouseOptionsLoading[warehouseKey]) {
                        html += '<span class="sd-hint">Loading warehouses...</span>';
                    } else if (!warehouseOptions.length) {
                        html += '<span class="sd-hint">No purchase warehouses available.</span>';
                    } else {
                        html += `<label class="sd-hint">Warehouse: <select class="sd-input warehouse-select" data-supplier="${k}">`;
                        html += `<option value="">Select warehouse</option>`;
                        for (const wh of warehouseOptions) {
                            const selected = String(selectedWarehouse) === String(wh.whse_id) ? 'selected' : '';
                            html += `<option value="${wh.whse_id}" ${selected}>${wh.whse_description}</option>`;
                        }
                        html += '</select></label>';
                    }
                    html += '</div>';
                }
                const status = supplierOrderStatus[k];
                if (status?.status === 'created') {
                    html += `<span class="order-created-pill">Order created · ${status.orderNumber || ''}</span>`;
                } else if (status?.status === 'error') {
                    html += `<span class="order-error-pill" title="${status.message || 'Order error'}">${status.message || 'Order error'}</span>`;
                    if (k !== 'NO_SUP' && k !== '' && hasWarehouseSelection) html += `<button class="sd-btn" data-supplier="${k}">Try again</button>`;
                } else if (k !== 'NO_SUP' && k !== '') {
                    const disabled = warehouseOptions.length && selectedWarehouse ? '' : 'disabled';
                    html += `<button class="sd-btn" data-supplier="${k}" ${disabled}>Create Order</button>`;
                }
                html += `<button class="collapse-toggle" type="button">Show details</button>`;
                html += '</div></div>';
                html += '<div class="po-card-body" aria-hidden="true">';
                html += '<table class="po-card-table"><thead><tr><th>Product</th><th>Qty</th><th>Units</th><th>Unit Price</th></tr></thead><tbody>';
                for (const line of g.lines) {
                    html += `<tr><td>${line.product}</td><td style="text-align:right">${nf.format(line.qty)}</td><td style="text-align:center">${line.units || ''}</td><td style="text-align:right">${nf.format(line.price)}</td></tr>`;
                }
                html += '</tbody></table>';
                html += '</div></div>';
            }
        }
        html += '</div>';
        preview.innerHTML = html;
        // attach create buttons and expand toggles
        preview.querySelectorAll('.warehouse-select').forEach(sel => {
            sel.addEventListener('change', function (e) {
                const supplier = e.currentTarget.getAttribute('data-supplier');
                supplierWarehouseSelection[supplier] = e.currentTarget.value;
                const createButton = preview.querySelector(`button.sd-btn[data-supplier="${supplier}"]`);
                if (createButton && createButton.textContent.trim().startsWith('Create Order')) {
                    createButton.disabled = !e.currentTarget.value;
                }
            });
        });
        preview.querySelectorAll('button[data-supplier]').forEach(b => {
            b.addEventListener('click', function (e) {
                const sup = e.currentTarget.getAttribute('data-supplier');
                handleCreateOrderForSupplier(sup);
            });
        });
        preview.querySelectorAll('.collapse-toggle').forEach(btn => {
            btn.addEventListener('click', function () {
                const card = btn.closest('.po-card');
                const body = card.querySelector('.po-card-body');
                const open = body.classList.toggle('open');
                body.setAttribute('aria-hidden', String(!open));
                btn.textContent = open ? 'Hide details' : 'Show details';
            });
        });
    }


    async function handleCreateOrderForSupplier(supplierId) {
        const lines = [];
        tbody.querySelectorAll('tr').forEach(tr => {
            if (tr.classList && (tr.classList.contains('detail-row') || tr.classList.contains('spray-detail-row'))) return;
            const qty = Number(tr.dataset.purchaseUnitsToOrder || 0);
            if (!qty || qty <= 0) return;
            const sel = tr.querySelector('select');
            const sup = sel ? (sel.value || '') : '';
            if (String(sup) !== String(supplierId)) return;
            const unitId = tr.dataset.purchaseUnitId || '';
            console.log(tr.dataset)
            lines.push({
                product_id: tr.dataset.stockLink,
                unit_id: unitId,
                qty: qty,
                unit_price: Number(tr.dataset.lastInvoicePrice || 0)
            });
        });

        if (!lines.length) {
            alert('No products selected for this supplier.');
            return;
        }

        const warehouseId = supplierWarehouseSelection[supplierId] || '';
        if (!warehouseId) {
            alert('Please select a warehouse for this order before creating it.');
            return;
        }

        try {
            const res = await fetch('/agri/suggested-order/create-order', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({supplier_id: supplierId, warehouse_id: warehouseId, lines: lines})
            });
            const payload = await res.json();
            if (payload.status === 'ok') {
                supplierOrderStatus[supplierId] = {status: 'created', orderNumber: payload.order_number || '', message: ''};
            } else {
                supplierOrderStatus[supplierId] = {status: 'error', orderNumber: '', message: payload.message || 'Error creating order'};
            }
        } catch (err) {
            supplierOrderStatus[supplierId] = {status: 'error', orderNumber: '', message: err.message || 'Network error'};
        }
        renderPreview();
    }

    document.getElementById('filter_needs_only')?.addEventListener('change', renderPreview);

    weekInput.addEventListener('change', loadData);
    populateWeekSelect(0, 5);
    loadData();
}

window.openSuggestedOrderModal = async function () {
    const modal = document.getElementById('suggestedOrderModal');
    const modalBody = document.getElementById('suggestedOrderModalBody');
    if (!modal || !modalBody) return;

    modalBody.innerHTML = '<div style="padding: 2rem; text-align: center; color: #6b7280;">Loading suggested order...</div>';
    modal.classList.remove('hidden');

    try {
        const res = await fetch('/agri/suggested-order/popup');
        if (!res.ok) throw new Error('Unable to load suggested order content');
        const html = await res.text();
        modalBody.innerHTML = html;
        initSuggestedOrder(modalBody);
    } catch (err) {
        modalBody.innerHTML = `<div style="padding: 2rem; text-align: center; color: #c2410c;">${err.message}</div>`;
    }
};

window.closeSuggestedOrderModal = function () {
    const modal = document.getElementById('suggestedOrderModal');
    if (!modal) return;
    modal.classList.add('hidden');
};

if (typeof window !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        initSuggestedOrder(document);
    });
}
