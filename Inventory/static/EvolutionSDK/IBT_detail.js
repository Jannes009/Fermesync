let ibtDetail = null;
let warehouseOptions = [];
let productOptions = [];
const query = new URLSearchParams(window.location.search);

function allowed(name) {
    const permissions = window.IBT_PERMISSIONS || [];
    if (Array.isArray(permissions)) return permissions.includes(`IBT_${name.toUpperCase()}`);
    return Boolean(permissions[name]);
}
function availableCreationModes() {
    const modes = [];
    if (allowed('request')) modes.push(['request', 'Create request']);
    if (allowed('request') && allowed('approve')) modes.push(['approve', 'Create and approve']);
    if (allowed('issue')) modes.push(['issue', 'Issue immediately']);
    return modes;
}
function esc(value) { return String(value ?? '').replace(/[&<>\"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[char])); }
function showMessage(message, error = false) { document.getElementById('message').innerHTML = `<p style="color:${error ? '#b42318' : '#176b3a'}">${esc(message)}</p>`; }

async function getJson(url, options) {
    const response = await request(url, options);
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.message || 'Request failed');
    return data;
}

async function loadWarehouses() {
    const data = await getJson('/inventory/fetch_warehouses');
    warehouseOptions = data.warehouses || [];
    const markup = '<option value="">Select warehouse</option>' + warehouseOptions.map(w => `<option value="${w.id}">${esc(w.name)}</option>`).join('');
    document.getElementById('warehouse-from').innerHTML = markup;
    document.getElementById('warehouse-to').innerHTML = markup;
}

async function loadProducts() {
    const from = document.getElementById('warehouse-from').value;
    const to = document.getElementById('warehouse-to').value;
    if (!from || !to || from === to) { productOptions = []; return; }
    const data = await getJson('/inventory/fetch_products_in_both_whses', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({whse_from_id:from, whse_to_id:to}) });
    productOptions = data.products || [];
    document.querySelectorAll('.product-select').forEach(select => refreshProductSelect(select));
}

function refreshProductSelect(select, selected) {
    const value = selected ?? select.value;
    select.innerHTML = '<option value="">Select product</option>' + productOptions.map(p => `<option value="${p.product_id}" data-factor="${p.conversion_factor || 1}" data-purchase="${p.purchasing_unit_code || ''}" data-stock="${p.stocking_unit_code || ''}">${esc(p.product_desc)} (${esc(p.qty_in_whse)} ${esc(p.purchasing_unit_code || '')})</option>`).join('');
    if (value) select.value = String(value);
}

function addLine(line = {}) {
    const row = document.createElement('div');
    row.className = 'ibt-line';
    row.innerHTML = `<div class="ibt-field product-field"><label>Product</label><select class="product-select"></select></div><div class="ibt-field"><label>Purchasing qty</label><input class="purchase-qty" type="number" min="0" step=".01" value="${line.qty_purchasing ?? ''}"></div><div class="ibt-field"><label>Stocking qty</label><input class="stocking-qty" type="number" min="0" step=".01" value="${line.qty_stocking ?? ''}"></div><button type="button" class="ibt-btn danger remove-line" title="Remove line">×</button>`;
    document.getElementById('lines').appendChild(row);
    refreshProductSelect(row.querySelector('.product-select'), line.product_id);
    row.querySelector('.product-select').addEventListener('change', () => updateUnits(row));
    row.querySelector('.purchase-qty').addEventListener('input', () => updateUnits(row, true));
    row.querySelector('.remove-line').addEventListener('click', () => row.remove());
}

function updateUnits(row, fromPurchase = false) {
    const select = row.querySelector('.product-select');
    const option = select.selectedOptions[0];
    if (!option) return;
    const factor = Number(option.dataset.factor) || 1;
    const purchase = row.querySelector('.purchase-qty');
    const stocking = row.querySelector('.stocking-qty');
    if (fromPurchase) stocking.value = (Number(purchase.value || 0) * factor).toFixed(2);
    else if (document.activeElement !== stocking) purchase.value = (Number(stocking.value || 0) / factor).toFixed(2);
}

function collectLines() {
    return [...document.querySelectorAll('.ibt-line')].map(row => {
        const select = row.querySelector('.product-select');
        return { product_id: select.value, qty_purchasing: Number(row.querySelector('.purchase-qty').value || 0), qty_stocking: Number(row.querySelector('.stocking-qty').value || 0) };
    });
}

function renderHistory(ibt) {
    const history = [['Requested', ibt.request_timestamp], ['Approved', ibt.approval_timestamp], ['Issued', ibt.dispatch_timestamp], ['Received', ibt.receive_timestamp]];
    document.getElementById('history').innerHTML = history.map(([label, date]) => `<div><small>${label}</small>${date ? new Date(date).toLocaleString() : '—'}</div>`).join('');
}

function configureActions() {
    const status = ibtDetail?.ibt.status;
    const editable = ibtDetail?.isNew ? availableCreationModes().length > 0 : status === 'REQUESTED' ? allowed('request') : status === 'APPROVED' ? allowed('approve') : false;
    document.getElementById('header-panel').classList.toggle('hidden', !editable);
    document.getElementById('add-line').classList.toggle('hidden', !editable);
    document.getElementById('save').classList.toggle('hidden', !editable);
    document.getElementById('creation-mode-field').classList.toggle('hidden', !ibtDetail?.isNew);
    document.getElementById('approve').classList.toggle('hidden', !(status === 'REQUESTED' && allowed('approve')));
    document.getElementById('reject').classList.toggle('hidden', !(status === 'REQUESTED' && allowed('reject')));
    document.getElementById('issue').classList.toggle('hidden', !(status === 'APPROVED' && allowed('issue')));
    document.getElementById('receive').classList.toggle('hidden', !(status === 'ISSUED' && allowed('receive')));
    document.querySelectorAll('.product-select,.purchase-qty,.stocking-qty').forEach(input => { input.disabled = !editable && !ibtDetail?.isNew; });
}

async function save() {
    const lines = collectLines();
    const payload = {'from_warehouse_id': document.getElementById('warehouse-from').value, 'to_warehouse_id': document.getElementById('warehouse-to').value, 'lines': lines };
    let url = '/inventory/ibt/create';
    if (ibtDetail?.isNew) payload.mode = document.getElementById('creation-mode').value;
    else url = `/inventory/ibt/${ibtDetail.ibt.id}/update`;
    const result = await getJson(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    showMessage('IBT saved.');
    if (ibtDetail?.isNew) window.location.href = `/inventory/SDK/IBT_detail?ibt_id=${result.ibt_id}`;
}

async function transition(action) {
    const payload = action === 'reject' ? { reason: prompt('Rejection reason') || '' } : undefined;
    const result = await getJson(`/inventory/ibt/${ibtDetail.ibt.id}/${action}`, { method:'POST', headers:{'Content-Type':'application/json'}, body: payload ? JSON.stringify(payload) : undefined });
    if (action === 'receive') window.location.href = `/inventory/SDK/IBT_receive?ibt_id=${encodeURIComponent(ibtDetail.ibt.number)}`;
    else window.location.reload();
}

async function loadDetail() {
    await loadWarehouses();
    const id = query.get('ibt_id');
    if (!id) {
        ibtDetail = { isNew:true, ibt:{ status:'REQUESTED' }, lines:[] };
        const modeSelect = document.getElementById('creation-mode');
        modeSelect.innerHTML = availableCreationModes().map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
        addLine();
        configureActions();
        return;
    }
    ibtDetail = await getJson(`/inventory/ibt/detail/${id}`);
    document.getElementById('page-title').textContent = `IBT ${ibtDetail.ibt.number}`;
    renderHistory(ibtDetail.ibt);
    const first = ibtDetail.lines[0];
    if (first) {
        document.getElementById('warehouse-from').value = first.warehouse_from_id;
        document.getElementById('warehouse-to').value = first.warehouse_to_id;
        await loadProducts();
    }
    ibtDetail.lines.forEach(addLine);
    if (!ibtDetail.lines.length) addLine();
    configureActions();
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('back-summary').addEventListener('click', () => { window.location.href = '/inventory/SDK/IBT'; });
    document.getElementById('add-line').addEventListener('click', () => addLine());
    document.getElementById('save').addEventListener('click', () => save().catch(e => showMessage(e.message, true)));
    ['approve','reject','issue','receive'].forEach(action => document.getElementById(action).addEventListener('click', () => transition(action).catch(e => showMessage(e.message, true))));
    document.getElementById('warehouse-from').addEventListener('change', () => loadProducts().catch(e => showMessage(e.message, true)));
    document.getElementById('warehouse-to').addEventListener('change', () => loadProducts().catch(e => showMessage(e.message, true)));
    loadDetail().catch(e => showMessage(e.message, true));
});
