function load_delivery_lines_table(delnoteno) {
    console.log(delnoteno)
    fetch(`/api/fetch_delivery_note_lines/${encodeURIComponent(delnoteno)}`)
        .then(response => response.json())
        .then(data => {
            const lines = data.lines;
            let tableHtml = `
                <table id="delivery-lines-table-table" class="fs-table fs-hover">
                <thead>
                    <tr>
                    <th>Line</th>
                    <th>Product</th>
                    <th>Production Unit</th>
                    <th>Qty (Bags)</th>
                    <th>Sold Qty</th>
                    <th>Invoiced Qty</th>
                    </tr>
                </thead>
                <tbody>
            `;
            lines.forEach(line => {
                const invoicedQty = line.totalqtyinvoiced || 0;

                tableHtml += `
                  <tr class="delivery-line" data-line-id="${line.dellineindex}" onclick="selectDeliveryLine(this, '${line.dellineindex}')" style="cursor: pointer;">
                    <td>${line.dellineindex}</td>
                    <td>
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span>${line.productdescription}</span>
                            <button class="icon-btn" onclick="changeProduct('${line.dellineindex}', '${line.productdescription}', '${delnoteno}', '${line.totalqtyinvoiced}'); event.stopPropagation();">
                                <img src="/static/Image/change.png" alt="Change Product">
                            </button>
                      </div>
                    </td>
                    <td>
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span>${line.produnitname}</span>
                            <button class="icon-btn" onclick="changeProductionUnit('${line.dellineindex}', '${line.produnitname}', '${delnoteno}', '${line.totalqtyinvoiced}'); event.stopPropagation();">
                                <img src="/static/Image/change.png" alt="Change Production Unit">
                            </button>  
                      </div>
                    </td>
                    <td>
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="quantity-display">${line.dellinequantitybags || 0}</span>
                        <input type="number" 
                               class="form-control quantity-input" 
                               value="${line.dellinequantitybags || 0}"
                               min="${(line.totalqtysold || 0) + (line.totalqtyinvoiced || 0)}"
                               style="display: none; width: 100px;"
                               data-line-id="${line.dellineindex}"
                               data-sold="${line.totalqtysold || 0}"
                               data-invoiced="${line.totalqtyinvoiced || 0}">
                      </div>
                    </td>
                    <td>${line.totalqtysold || 0}</td>
                    <td>${invoicedQty}</td>
                  </tr>
                `;
            });
            tableHtml += `
                    </tbody>
                  </table>
            `;
            document.getElementById('delivery-lines-table').innerHTML = tableHtml;
        })
        .catch(error => {
            console.error('Error loading delivery lines:', error);
            document.getElementById('delivery-lines-table').innerHTML = '<div style="color:red;">Failed to load delivery lines.</div>';
        });
}

function load_sales_lines_table(delnoteno) {
    console.log(delnoteno)
    fetch(`/api/fetch_sales_note_lines/${encodeURIComponent(delnoteno)}`)
        .then(response => response.json())
        .then(data => {
            const lines = data.lines;
            let tableHtml = `
                <div class="table-responsive">
                <table class="fs-table sales-table">
                    <thead>
                    <tr>
                        <th>Date</th>
                        <th>Product</th>
                        <th>Qty</th>
                        <th>Price</th>
                        <th>Discount %</th>
                        <th>Sales Amount</th>
                        <th>Auto Sale</th>
                        <th>Invoice No</th>
                        <th></th>
                    </tr>
                    </thead>
                    <tbody>
            `;
            lines.forEach((sale, idx) => {
                tableHtml += `
                <tr id="row-${delnoteno}-${idx}" 
                        data-sales-id="${sale.sales_line_index || ''}"
                        data-line-id="${sale.del_line_id || sale.sales_line_index || ''}">
                        <td>${sale.sales_date || ''}</td>
                        <td>${sale.product || ''}</td>
                        <td class="qty-cell">${sale.qty != null ? sale.qty.toLocaleString('en-ZA') : ''}</td>
                        <td class="price-cell">R${sale.price != null ? Number(sale.price).toLocaleString('en-ZA', {minimumFractionDigits:2, maximumFractionDigits:2}) : ''}</td>
                        <td class="discount-cell">${sale.discount_percent != null ? Number(sale.discount_percent).toLocaleString('en-ZA', {minimumFractionDigits:2, maximumFractionDigits:2}) : '0.00'}%</td>
                        <td class="sales-amount-cell">R${sale.sales_amount != null ? Number(sale.sales_amount).toLocaleString('en-ZA', {minimumFractionDigits:2, maximumFractionDigits:2}) : ''}</td>
                        <td>${sale.auto_sale ? 'Auto' : 'Manual'}</td>
                        <td>${sale.invoice_no || ''}</td>
                        <td class="sales-row-actions">
                        ${!sale.invoice_no ? `
                        <button class="icon-btn" onclick="editRow('${delnoteno}', ${idx}, this)">
                            <img src="/static/Image/edit.png" alt="Edit">
                        </button>
                        <button class="icon-btn" onclick="deleteRow('${delnoteno}', ${idx}, this)">
                            <img src="/static/Image/recycle-bin.png" alt="Delete">
                        </button>
                        ` : ''}
                        </td>
                    </tr>
                `;
            });
            tableHtml += `
                    </tbody>
                  </table>
                </div>
            `;
            // Use the correct container selector
            const container = document.getElementById('salesTableContainer') || document.querySelector('.salesTableContainer');
            if (container) {
                container.innerHTML = tableHtml;
            }
        })
        .catch(error => {
            console.error('Error loading sales lines:', error);
            const container = document.getElementById('salesTableContainer') || document.querySelector('.salesTableContainer');
            if (container) {
                container.innerHTML = '<div style="color:red;">Failed to load sales lines.</div>';
            }
        });
}

document.addEventListener('DOMContentLoaded', function() {
    load_delivery_lines_table(window.delNoteNo);
    load_sales_lines_table(window.delNoteNo)
});


function renderInvoicesTable(invoices) {
    if (!invoices.length) return '<div style="background: var(--container-bg); color: var(--primary-text); padding: 1em; border-radius: 8px;">No invoices found for this delivery note.</div>';
    let rows = invoices.map(inv => `
        <tr class="invoice-summary-row invoice-line" data-invoice-no="${inv.invoiceno}" style="cursor:pointer;">
            <td><a href="/sales-order/${inv.invoiceindex}" class="invoice-link" onclick="event.stopPropagation();">${inv.invoiceno}</a></td>
            <td class="invoice-date">${inv.invoicedate || ''}</td>
            <td class="invoice-gross">${formatCurrency(inv.invoicegross)}</td>
            <td class="invoice-nett">${formatCurrency(inv.invoicenett)}</td>
            <td class="invoice-status">${inv.status}</td>
        </tr>
    `).join('');
    return `
        <div class="overflow-auto">
        <table class="fs-table fs-hover">
            <thead>
                <tr>
                    <th>Invoice No</th>
                    <th>Date</th>
                    <th>Gross</th>
                    <th>Nett</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
        </div>
    `;
}