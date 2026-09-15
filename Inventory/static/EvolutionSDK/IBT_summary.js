const ibtStatusLabels = { REQUESTED: 'Request', APPROVED: 'Approved', ISSUED: 'Issued', RECEIVED: 'Received', REJECTED: 'Rejected' };

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
    const rows = data.ibts.filter(ibt => !filter || ibt.status === filter);
    if (!rows.length) {
        target.textContent = 'No IBTs found.';
        return;
    }
    target.innerHTML = `<table class="ibt-table"><thead><tr><th>IBT</th><th>Status</th><th>Route</th><th>Lines</th><th>Requested</th></tr></thead><tbody>${rows.map(ibt => `
        <tr class="ibt-row" data-id="${ibt.id}"><td>${ibt.number}</td><td><span class="ibt-status status-${ibt.status}">${ibtStatusLabels[ibt.status] || ibt.status}</span></td><td>${ibt.warehouse_from || '—'} → ${ibt.warehouse_to || '—'}</td><td>${ibt.line_count}</td><td>${formatIbtDate(ibt.request_timestamp)}</td></tr>`).join('')}</tbody></table>`;
    target.querySelectorAll('.ibt-row').forEach(row => row.addEventListener('click', () => {
        window.location.href = `/inventory/SDK/IBT_detail?ibt_id=${row.dataset.id}`;
    }));
}

function formatIbtDate(value) {
    return value ? new Date(value).toLocaleString() : '—';
}

document.addEventListener('DOMContentLoaded', () => {
    const newIbtButton = document.getElementById('new-ibt');
    if (newIbtButton) newIbtButton.addEventListener('click', () => {
        window.location.href = '/inventory/SDK/IBT_detail?new=1';
    });
    document.getElementById('refresh-ibt').addEventListener('click', loadIbtSummary);
    document.getElementById('status-filter').addEventListener('change', loadIbtSummary);
    loadIbtSummary().catch(error => { document.getElementById('ibt-list').textContent = error.message; });
});
