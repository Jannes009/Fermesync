document.addEventListener('DOMContentLoaded', loadPurchaseOrder);

async function loadPurchaseOrder() {
    const message = document.getElementById('orderMessage');
    const historyPoNumber = document.getElementById('historyDetailPage').dataset.poNumber;
    try {
        const response = await request(`/inventory/grv/history/${encodeURIComponent(historyPoNumber)}/data`);
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to load purchase order.');

        const order = data.order;
        document.getElementById('historyTitle').textContent = `Purchase Order ${order.order_num}`;
        message.hidden = true;
        renderOrderMeta(order);
        renderOrderLines(order.lines);
        renderTransactions(order.transactions);

        if ([1, 3].includes(order.state)) {
            const receiveButton = document.getElementById('receiveOrder');
            receiveButton.hidden = false;
            receiveButton.addEventListener('click', () => {
                window.location.href = `/inventory/grv/${encodeURIComponent(order.order_num)}`;
            });
        }
    } catch (error) {
        message.textContent = error.message;
        document.getElementById('orderLines').innerHTML = '<tr><td colspan="6">Unable to load lines.</td></tr>';
        document.getElementById('stockTransactions').innerHTML = '<tr><td colspan="9">Unable to load transaction history.</td></tr>';
    }
}

function renderOrderMeta(order) {
    const metadata = [
        ['Order date', formatDate(order.order_date)],
        ['Supplier', order.supplier_name || order.supplier_account || ''],
        ['Description', order.description || ''],
        ['Status', statusBadge(order.state, order.state_text)],
        ['Total incl', formatCurrency(order.order_total)]
    ];
    const target = document.getElementById('orderMeta');
    target.innerHTML = metadata.map(([label, value]) => `
        <div><dt>${escapeHtml(label)}</dt><dd>${label === 'Status' ? value : escapeHtml(value)}</dd></div>
    `).join('');
    target.hidden = false;
}

function renderOrderLines(lines) {
    const target = document.getElementById('orderLines');
    if (!lines.length) {
        target.innerHTML = '<tr><td colspan="6">No purchase order lines found.</td></tr>';
        return;
    }
    target.innerHTML = lines.map(line => `
        <tr>
            <td>${escapeHtml(line.description || '')}</td>
            <td>${formatQuantity(line.quantity, line.unit_code)}</td>
            <td>${formatQuantity(line.processed, line.unit_code)}</td>
            <td>${formatCurrency(line.unit_price)}</td>
            <td>${escapeHtml(line.warehouse_name || '')}</td>
        </tr>
    `).join('');
}

function renderTransactions(transactions) {
    const target = document.getElementById('stockTransactions');
    if (!transactions.length) {
        target.innerHTML = '<tr><td colspan="9">No stock transactions found for this purchase order.</td></tr>';
        return;
    }
    target.innerHTML = transactions.map(transaction => `
        <tr>
            <td>${escapeHtml(transaction.warehouse_name || '')}</td>
            <td>${escapeHtml(transaction.description || '')}</td>
            <td>${formatDate(transaction.tx_date)}</td>
            <td>${escapeHtml(formatTimestamp(transaction.timestamp))}</td>
            <td>${escapeHtml(transaction.reference || '')}</td>
            <td>${escapeHtml(transaction.user_name || '')}</td>
            <td>${formatQuantity(transaction.quantity, transaction.unit_code)}</td>
            <td>${formatCurrency(transaction.unit_cost)}</td>
            <td>${escapeHtml(transaction.project_code || '')}</td>
        </tr>
    `).join('');
}

function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function formatTimestamp(value) {
    if (!value) return '';
    return String(value).replace(/\.\d+(?=(?:[+-]\d{2}:\d{2})?$)/, '').replace('T', ' ');
}

function formatQuantity(value, unit) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '';
    const formatted = amount.toLocaleString('en-ZA', { maximumFractionDigits: 2 });
    const unitLabel = unit ? `<small class="quantity-unit">${escapeHtml(unit)}</small>` : '';
    return `<span class="quantity-display">${formatted}${unitLabel}</span>`;
}

function formatCurrency(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '';
    return new Intl.NumberFormat('en-ZA', {
        style: 'currency',
        currency: 'ZAR',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

function statusBadge(state, label) {
    const classByState = {
        0: 'status-unknown',
        1: 'status-unprocessed',
        2: 'status-quote',
        3: 'status-partial',
        4: 'status-archived',
        5: 'status-template',
        6: 'status-contract',
        7: 'status-cancelled'
    };
    const badgeClass = classByState[state] || classByState[0];
    return `<span class="status-badge ${badgeClass}">${escapeHtml(label || 'Unknown')}</span>`;
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = String(value ?? '');
    return element.innerHTML;
}