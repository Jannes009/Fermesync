const ibtStatusLabels = { REQUESTED: 'Request', APPROVED: 'Approved', ISSUED: 'Issued', RECEIVED: 'Received', REJECTED: 'Rejected' };
const ibtPermissions = window.IBT_PERMISSIONS || [];
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

function actionMarkup(ibt) {
    const number = encodeURIComponent(ibt.number);
    const can = permission => ibtPermissions.includes(`IBT_${permission}`);
    const wizard = `/inventory/SDK/IBT_issue?ibt_no=${number}&step=3`;
    const actions = [];
    if ((ibt.status === 'REQUESTED' || ibt.status === 'REJECTED') && can('REQUEST')) actions.push(['Edit', wizard]);
    if (ibt.status === 'REQUESTED' && can('APPROVE')) actions.push(['Approve', wizard]);
    if (ibt.status === 'REQUESTED' && can('REJECT')) actions.push(['Reject', wizard]);
    if (ibt.status === 'APPROVED' && can('APPROVE')) actions.push(['Edit', wizard]);
    if (ibt.status === 'APPROVED' && can('ISSUE')) actions.push(['Issue stock', wizard]);
    if (ibt.status === 'ISSUED' && can('RECEIVE')) actions.push(['Receive', `/inventory/SDK/IBT_receive?ibt_no=${number}`]);
    if (!actions.length) return '—';
    const labels = actions.map(([label]) => label).join(' / ');
    return `<button type="button" class="ibt-action-button" data-href="${actions[0][1]}">${esc(labels)}</button>`;
}

async function loadIbtSummary() {
    const target = document.getElementById('ibt-list');
    target.textContent = 'Loading...';
    const response = await request('/inventory/ibt/list');
    const data = await response.json();
    if (!response.ok || !data.success) {
        target.textContent = data.message || 'Unable to load IBTs.';
        return;
    }
    const filter = document.getElementById('status-filter').value;
    const showReceived = document.getElementById('show-received').checked;
    const rows = data.ibts.filter(ibt => showReceived || ibt.status !== 'RECEIVED').filter(ibt => !filter || ibt.status === filter);
    if (!rows.length) {
        target.textContent = 'No IBTs found.';
        return;
    }
    target.innerHTML = `<table class="ibt-table">
    <thead>
        <tr>
        <th>IBT</th>
        <th>Status</th>
        <th>Route</th>
        <th>Lines</th>
        <th>Requested</th>
        <th>Action</th>
        </tr>
    </thead>
    <tbody>${rows.map(ibt => `
        <tr class="ibt-row" data-number="${esc(ibt.number)}">
        <td>${esc(ibt.number)}</td>
        <td><span class="ibt-status status-${esc(ibt.status)}">${esc(ibtStatusLabels[ibt.status] || ibt.status)}</span></td>
        <td>${esc(ibt.warehouse_from || '—')} → ${esc(ibt.warehouse_to || '—')}</td>
        <td>${ibt.line_count}</td><td>${formatIbtDate(ibt.request_timestamp)}</td>
        <td>${actionMarkup(ibt)}</td>
        </tr>`).join('')}
    </tbody>
    </table>`;
    target.querySelectorAll('.ibt-row').forEach(row => row.addEventListener('click', () => {
        window.location.href = `/inventory/SDK/IBT_detail?ibt_no=${encodeURIComponent(ibtNumberForRow(row))}`;
    }));
    target.querySelectorAll('.ibt-action-button').forEach(action => action.addEventListener('click', event => {
        event.stopPropagation();
        window.location.href = action.dataset.href;
    }));
}

function ibtNumberForRow(row) {
    return row.dataset.number;
}

function formatIbtDate(value) {
    return value ? new Date(value).toLocaleString() : '—';
}

document.addEventListener('DOMContentLoaded', () => {
    const newIbtButton = document.getElementById('new-ibt');
    if (newIbtButton) newIbtButton.addEventListener('click', () => {
        window.location.href = '/inventory/SDK/IBT_issue';
    });
    document.getElementById('refresh-ibt').addEventListener('click', loadIbtSummary);
    document.getElementById('status-filter').addEventListener('change', loadIbtSummary);
    document.getElementById('show-received').addEventListener('change', loadIbtSummary);
    loadIbtSummary().catch(error => { document.getElementById('ibt-list').textContent = error.message; });
});
