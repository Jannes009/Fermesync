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

    function populateWeekSelect(before = 0, after = 5) {
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

        clear();
        const res = await fetch(`/agri/suggested-order/data?week=${encodeURIComponent(week)}`);
        const payload = await res.json();
        if (payload.status !== 'ok') return alert(payload.message || 'Error');

        for (const row of payload.data) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="col-action"><button class="expand" data-id="${row.stock_link}" aria-expanded="false">+</button></td>
                <td class="col-product">${row.stock_code} — ${row.stock_description}</td>
                <td class="col-num">${nf.format(row.purchase_unit_on_hand)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num">${nf.format(row.purchase_unit_on_po)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num">${nf.format(row.purchase_units_needed)}<span class="uom">${row.purchasing_uom}</span></td>
                <td class="col-num">${nf.format(row.purchase_units_to_order)}<span class="uom">${row.purchasing_uom}</span></td>
            `;
            tbody.appendChild(tr);

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
                    let html = '<table class="detail-table"><thead><tr><th></th><th>Warehouse</th><th>Stock Description</th><th class="col-num">Qty On Hand</th><th class="col-num">Qty On PO</th><th class="col-num">Qty to Order</th><th>Spray Week</th></tr></thead><tbody>';
                    for (const w of dpayload.warehouses) {
                        html += `<tr data-whse-id="${w.whse_id}" data-stock-link="${w.stock_link}"><td class="action-col"><button class="expand expand-spray" data-whse="${w.whse_id}" data-stock="${w.stock_link}" aria-expanded="false">+</button></td><td>${w.whse_name}</td><td>${w.stock_description}</td><td class="col-num">${nf.format(w.qty_on_hand)}<span class="uom"> ${w.stocking_uom}</span></td><td class="col-num">${nf.format(w.qty_on_po)}<span class="uom"> ${w.stocking_uom}</span></td><td class="col-num">${nf.format(w.purchase_units_needed)}<span class="uom"> ${w.purchasing_unit_code}</span></td><td>${w.spray_h_week}</td></tr>`;
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
    }

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
