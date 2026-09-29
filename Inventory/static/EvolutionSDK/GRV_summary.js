document.addEventListener("DOMContentLoaded", () => {
    loadPOTable();
    setupHistory();
});

let currentReceiverName = '';
let supplierRef = '';
let currentPoNumber = null;

// (supplier dropdown removed) POs load directly via loadPOTable()

function loadPOTable(supplierCode) {
    const wrapper = document.getElementById("poTableWrapper");
    const tbody = document.getElementById("poTableBody");

    wrapper.classList.remove("hidden");
    tbody.innerHTML = "<tr><td colspan='6'>Loading...</td></tr>";

    const body = supplierCode ? { supplier_code: supplierCode } : {};
    request("/inventory/get_po_numbers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                tbody.innerHTML = `<tr><td colspan="6">Error: ${data.error || 'Failed to load POs.'}</td></tr>`;
                return;
            }
            tbody.innerHTML = "";
            if (!data.po_list?.length) {
                tbody.innerHTML = `<tr><td colspan="6">No PO’s found</td></tr>`;
                return;
            }

            data.po_list.forEach(p => {
                const tr = document.createElement("tr");
                const hasZeroCost = p.has_zero_cost === true;
                tr.innerHTML = `
                    <td>${p.order_num}</td>
                    <td>${formatDate(p.order_date)}</td>
                    <td>${p.supplier_name || p.supplier_code || ''}</td>
                    <td>${p.order_desc}</td>
                    <td>${formatCurrency(p.order_total)}</td>
                    <td>${hasZeroCost ? '<span class="zero-cost-status">Zero cost</span>' : '<span class="status-badge status-ready">Ready</span>'}</td>
                `;
                tr.addEventListener("click", () => {
                    if (hasZeroCost) {
                        Swal.fire("Cannot process GRV", "This PO contains a line with zero cost.", "error");
                        return;
                    }
                    window.location.href = `/inventory/grv/${p.order_num}`;
                });
                tbody.appendChild(tr);
            });

        });
}

function setupHistory() {
    const receiveTab = document.getElementById('receiveTab');
    const historyTab = document.getElementById('historyTab');
    if (!historyTab) return;

    const receivePanel = document.getElementById('receivePanel');
    const historyPanel = document.getElementById('historyPanel');
    const search = document.getElementById('poSearch');
    const historySearch = document.getElementById('historySearch');
    const startDate = document.getElementById('historyStartDate');
    const endDate = document.getElementById('historyEndDate');
    const state = document.getElementById('historyState');
    let historyLoaded = false;

    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(today.getDate() - 6);
    startDate.value = toDateInputValue(weekAgo);
    endDate.value = toDateInputValue(today);

    function selectTab(tab) {
        const showingHistory = tab === historyTab;
        receiveTab.setAttribute('aria-selected', String(!showingHistory));
        historyTab.setAttribute('aria-selected', String(showingHistory));
        receivePanel.hidden = showingHistory;
        historyPanel.hidden = !showingHistory;
        if (showingHistory && !historyLoaded) {
            loadHistory();
            historyLoaded = true;
        }
    }

    receiveTab.addEventListener('click', () => selectTab(receiveTab));
    historyTab.addEventListener('click', () => selectTab(historyTab));
    [startDate, endDate, state].forEach(input => input.addEventListener('change', loadHistory));
    historySearch.addEventListener('input', filterHistoryRows);
    search.addEventListener('input', () => {
        const query = search.value.trim().toLowerCase();
        document.querySelectorAll('#poTableBody tr').forEach(row => {
            const text = Array.from(row.cells).map(cell => cell.textContent.trim().toLowerCase()).join(' ');
            row.style.display = !query || text.includes(query) ? '' : 'none';
        });
    });
}

function toDateInputValue(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

async function loadHistory() {
    const tbody = document.getElementById('historyTableBody');
    const params = new URLSearchParams();
    const startDate = document.getElementById('historyStartDate').value;
    const endDate = document.getElementById('historyEndDate').value;
    const state = document.getElementById('historyState').value;
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (state) params.set('state', state);

    tbody.innerHTML = '<tr><td class="history-empty" colspan="7">Loading purchase orders...</td></tr>';
    try {
        const response = await request(`/inventory/grv/history?${params}`);
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to load purchase orders.');
        tbody.innerHTML = '';
        if (!data.orders.length) {
            tbody.innerHTML = '<tr><td class="history-empty" colspan="7">No purchase orders found.</td></tr>';
            return;
        }

        data.orders.forEach(order => {
            const row = document.createElement('tr');
            row.tabIndex = 0;
            row.innerHTML = `
                <td>${escapeHtml(order.order_num)}</td>
                <td>${formatDate(order.order_date)}</td>
                <td>${escapeHtml(order.supplier_name || order.supplier_account || '')}</td>
                <td>${escapeHtml(order.warehouse_name || '')}</td>
                <td>${escapeHtml(order.description || '')}</td>
                <td>${formatCurrency(order.order_total)}</td>
                <td>${statusBadge(order.state, order.state_text)}</td>
            `;
            const openOrder = () => {
                tbody.querySelectorAll('tr').forEach(item => item.removeAttribute('aria-selected'));
                row.setAttribute('aria-selected', 'true');
                window.location.href = `/inventory/grv/history/${encodeURIComponent(order.order_num)}`;
            };
            row.addEventListener('click', openOrder);
            row.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openOrder();
                }
            });
            tbody.appendChild(row);
        });
        filterHistoryRows();
    } catch (error) {
        tbody.innerHTML = `<tr><td class="history-empty" colspan="7">${escapeHtml(error.message)}</td></tr>`;
    }
}

function filterHistoryRows() {
    const query = document.getElementById('historySearch').value.trim().toLowerCase();
    document.querySelectorAll('#historyTableBody tr').forEach(row => {
        const rowText = row.textContent.trim().toLowerCase();
        row.style.display = !query || rowText.includes(query) ? '' : 'none';
    });
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = String(value ?? '');
    return element.innerHTML;
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

function formatDate(d) {
    const date = new Date(d);
    if (isNaN(date)) return "Invalid Date";
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
