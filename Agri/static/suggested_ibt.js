function initIbt(container = document) {
    const weekSel = container.querySelector('#ibt_week');
    const loadBtn = container.querySelector('#ibt_load');
    const contentDiv = container.querySelector('#ibt_content');

    if (!weekSel || !loadBtn || !contentDiv) return;

    const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

    // no external warehouse list required; backend returns from/to per item

    async function loadWeeks() {
        try {
            const res = await fetch('/agri/ibt/weeks');
            const payload = await res.json();
            if (payload.status !== 'ok') return;
            weekSel.innerHTML = '';
            for (const w of payload.weeks) {
                const o = document.createElement('option');
                o.value = w;
                o.textContent = w;
                weekSel.appendChild(o);
            }
        } catch (e) {
            console.error('Unable to load weeks', e);
        }
    }

    async function loadSuggested() {
        const week = weekSel.value;
        if (!week) return alert('Please select a week');
        
        contentDiv.innerHTML = '<div style="padding:2rem;text-align:center;color:#6b7280">Loading suggestions...</div>';
        try {
            const res = await fetch(`/agri/ibt/suggested?week=${encodeURIComponent(week)}`);
            const payload = await res.json();
            if (payload.status !== 'ok') return (contentDiv.innerHTML = '<div style="padding:2rem;text-align:center;color:#c2410c">Error loading data</div>');
            
            if (!payload.warehouses || payload.warehouses.length === 0) {
                contentDiv.innerHTML = '<div style="padding:2rem;text-align:center;color:#6b7280">No suggestions for this week</div>';
                return;
            }

            let html = '';
            for (const whse of payload.warehouses) {
                html += `<div class="ibt-warehouse-group">
                    <div class="ibt-whse-header">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                            <div>${whse.whse_description}</div>
                            <div>
                                <span class="sd-hint">From: <strong class="group-from" data-whse="${whse.whse_id}"></strong></span>
                                <button class="generate-ibt-btn" data-whse="${whse.whse_id}" style="background:#059669;color:#fff;padding:6px 10px;border-radius:6px;border:none;cursor:pointer;margin-left:10px">Generate IBT</button>
                            </div>
                        </div>
                    </div>
                    <table class="ibt-table">
                        <thead>
                            <tr>
                                <th><input type="checkbox" class="whse-check-all" data-whse="${whse.whse_id}"></th>
                                <th class="col-product">Product</th>
                                <th class="col-num">Needed</th>
                                <th class="col-num">On Hand</th>
                                <th class="col-num">Suggested IBT</th>
                                <th>Unit</th>
                            </tr>
                        </thead>
                        <tbody>`;
                
                for (const item of whse.items) {
                    // include optional from/to attributes if provided by backend
                    const fromAttr = item.from_whse || item.FromWhseId || item.fromWhse || '';
                    const toAttr = item.to_whse || item.ToWhseId || item.toWhse || '';
                    // render qty as plain text and default checkbox checked
                    html += `<tr data-whse-id="${whse.whse_id}" data-stock-link="${item.stock_link}" data-units-suggested="${item.units_suggested}" data-from-whse="${fromAttr}" data-from-whse-description="${(item.from_whse_description||'') }" data-to-whse="${toAttr}">
                        <td><input type="checkbox" class="ibt-item-check" checked></td>
                        <td class="col-product">${item.stock_description}</td>
                        <td class="col-num">${nf.format(item.units_needed)}</td>
                        <td class="col-num">${nf.format(item.units_on_hand)}</td>
                        <td class="col-num">${nf.format(item.units_suggested)}</td>
                        <td>${item.uom || ''}</td>
                    </tr>`;
                }
                html += `</tbody></table></div>`;
            }
            contentDiv.innerHTML = html;

            // Apply disabled state to rows with 0 qty and disable warehouse groups if all products have 0 qty
            contentDiv.querySelectorAll('.ibt-warehouse-group').forEach(group => {
                const table = group.querySelector('.ibt-table');
                const rows = Array.from(table.querySelectorAll('tbody tr[data-whse-id]'));
                let allZeroQty = true;
                rows.forEach(row => {
                    const qty = Number(row.getAttribute('data-units-suggested') || 0);
                    if (qty === 0) {
                        row.style.opacity = '0.5';
                        row.style.pointerEvents = 'none';
                        const chk = row.querySelector('.ibt-item-check');
                        if (chk) chk.disabled = true;
                    } else {
                        allZeroQty = false;
                    }
                });
                if (allZeroQty) {
                    const btn = group.querySelector('.generate-ibt-btn');
                    if (btn) {
                        btn.disabled = true;
                        btn.style.opacity = '0.5';
                        btn.style.cursor = 'not-allowed';
                    }
                }
            });

            // populate the displayed 'From' label for each warehouse group
            contentDiv.querySelectorAll('.ibt-warehouse-group').forEach(group => {
                const fromLabel = group.querySelector('.group-from');
                // collect distinct from_whse descriptions from rows
                const rows = group.querySelectorAll('tr[data-from-whse]');
                const map = new Map();
                rows.forEach(r => {
                    const id = r.getAttribute('data-from-whse');
                    const desc = r.getAttribute('data-from-whse-description') || r.getAttribute('data-from-whse-desc') || '';
                    if (id) map.set(String(id), desc || id);
                });
                if (map.size === 1) {
                    const onlyDesc = Array.from(map.values())[0];
                    fromLabel.textContent = onlyDesc || Array.from(map.keys())[0];
                    fromLabel.setAttribute('data-from', Array.from(map.keys())[0]);
                } else if (map.size > 1) {
                    fromLabel.textContent = Array.from(map.values()).join(', ');
                    fromLabel.setAttribute('data-from', Array.from(map.keys()).join(','));
                } else {
                    // fallback if rows didn't carry from descriptions: use first row's data-from-whse
                    const anyRow = group.querySelector('tr[data-from-whse]');
                    if (anyRow) {
                        const id = anyRow.getAttribute('data-from-whse');
                        fromLabel.textContent = id || '';
                        fromLabel.setAttribute('data-from', id || '');
                    } else {
                        fromLabel.textContent = '';
                        fromLabel.setAttribute('data-from', '');
                    }
                }
            });

            // Attach warehouse check-all handlers
            contentDiv.querySelectorAll('.whse-check-all').forEach(chk => {
                chk.addEventListener('change', function () {
                    const whseId = this.getAttribute('data-whse');
                    contentDiv.querySelectorAll(`tr[data-whse-id="${whseId}"] .ibt-item-check`).forEach(c => (c.checked = this.checked));
                });
                // default check-all to checked
                chk.checked = true;
            });

            // Attach Generate IBT handlers (use backend-provided from_whse)
            contentDiv.querySelectorAll('.generate-ibt-btn').forEach(btn => {
                btn.addEventListener('click', function () {
                    const whseId = Number(this.getAttribute('data-whse'));
                    const parent = btn.closest('.ibt-warehouse-group');
                    const fromLabel = parent.querySelector('.group-from');
                    let fromWh = fromLabel ? fromLabel.getAttribute('data-from') : null;
                    // fallback to first row's data-from-whse if label missing
                    if (!fromWh) {
                        const anyRow = parent.querySelector('tr[data-from-whse]');
                        fromWh = anyRow ? anyRow.getAttribute('data-from-whse') : null;
                    }
                    const toWh = whseId;
                    if (!fromWh) return alert('No source warehouse provided by backend for this group');

                    const lines = [];
                    parent.querySelectorAll('tr[data-whse-id][data-stock-link]').forEach(tr => {
                        const chk = tr.querySelector('.ibt-item-check');
                        if (!chk) return;
                        if (!chk.checked) return;
                        const stock = tr.getAttribute('data-stock-link');
                        const qty = Number(tr.getAttribute('data-units-suggested') || 0);
                        if (qty > 0) lines.push({ stock_link: stock, qty: qty });
                    });

                    if (!lines.length) return alert('No items selected for IBT');

                    const payload = { from_whse: Number(fromWh), to_whse: Number(toWh), lines: lines };
                    // Redirect to the IBT page with the payload encoded as a prefill parameter.
                    // Also send a return_to so the IBT flow can redirect back to the qty page and re-open suggestions.
                    try {
                        // Use sessionStorage to pass large prefill payloads (avoids URL length limits)
                        sessionStorage.setItem('ibt_prefill', JSON.stringify(payload));
                        const returnTo = encodeURIComponent('/inventory/qty?openSuggestedIbt=1');
                        window.location.href = `/inventory/SDK/IBT_issue?return_to=${returnTo}`;
                    } catch (e) {
                        console.error('Failed to redirect to IBT page', e);
                        alert('Failed to start IBT transfer. See console for details.');
                    }
                });
            });
        } catch (e) {
            contentDiv.innerHTML = '<div style="padding:2rem;text-align:center;color:#c2410c">Error loading suggestions</div>';
        }
    }

    loadBtn.addEventListener('click', loadSuggested);

    // load supporting data
    Promise.all([loadWeeks()]).catch(() => {});
}

window.openIbtModal = async function () {
    const modal = document.getElementById('ibtModal');
    const modalBody = document.getElementById('ibtModalBody');
    if (!modal || !modalBody) return;

    modalBody.innerHTML = '<div style="padding: 2rem; text-align: center; color: #6b7280;">Loading IBT...</div>';
    modal.classList.remove('hidden');

    try {
        const res = await fetch('/agri/ibt/popup');
        if (!res.ok) throw new Error('Unable to load IBT content');
        const html = await res.text();
        modalBody.innerHTML = html;
        initIbt(modalBody);
    } catch (err) {
        modalBody.innerHTML = `<div style="padding: 2rem; text-align: center; color: #c2410c;">${err.message}</div>`;
    }
};

window.closeIbtModal = function () {
    const modal = document.getElementById('ibtModal');
    if (!modal) return;
    modal.classList.add('hidden');
};

if (typeof window !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        // optional: init any inline IBT content on page
        initIbt(document);
    });
}
