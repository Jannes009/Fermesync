async function loadNettAmountsReport() {
    console.log("Loading nett amounts report");
    try {
        const tbody = document.querySelector("#nettAmountsTable tbody");
        tbody.innerHTML = "";

        let data = applyGlobalFilters(window.data);

        // Group by Date
        const dates = groupBy(data, "deldate");
        Object.entries(dates).forEach(([date, dateRows]) => {
            const dateTotals = calcNettTotals(dateRows);
            const dateRow = makeNettRow(date, dateTotals, "date");
            tbody.appendChild(dateRow);

            // Group by Delivery Note inside Date
            const notes = groupBy(dateRows, "delnoteno");
            Object.entries(notes).forEach(([noteNo, noteRows]) => {
                const noteTotals = calcNettTotals(noteRows);
                const noteRow = makeNettRow("↳ " + noteNo, noteTotals, "note", dateRow);
                tbody.appendChild(noteRow);

                // Group by Product Description inside Note
                const products = groupBy(noteRows, "productdescription");
                Object.entries(products).forEach(([prodDesc, prodRows]) => {
                    const prodTotals = calcNettTotals(prodRows);
                    const prodRow = makeNettRow("   ↳ " + prodDesc, prodTotals, "product", noteRow);
                    tbody.appendChild(prodRow);
                });
            });
        });
    } catch (err) {
        console.error("Error:", err);
        throw err; // Re-throw to allow caller to handle
    }
}

// Helper: group array of objects by key
function groupBy(arr, key) {
    return arr.reduce((acc, row) => {
        const val = row[key];
        acc[val] = acc[val] || [];
        acc[val].push(row);
        return acc;
    }, {});
}

// Helper: calculate totals for nett amounts
function calcNettTotals(rows) {
    const estimatedNett = rows.reduce((s, r) => s + (r.estimatednett || 0), 0);
    const soldNett = rows.reduce((s, r) => s + (r.salesnettamnt || 0), 0);
    const invoicedNett = rows.reduce((s, r) => s + (r.invoicednettamnt || 0), 0);
    const totalQtySold = rows.reduce((s, r) => s + (r.totalqtysold || 0), 0);
    const deliveredTransport = rows.reduce((s, r) => s + (r.deliveredtransportcost || 0), 0);
    const invoicedTransport = rows.reduce((s, r) => s + (r.invoicedtransportcost || 0), 0);
    const avgPriceSold = totalQtySold > 0 ? soldNett / totalQtySold : 0;
    const invoicedAfterTransport = invoicedNett - invoicedTransport;

    return {
        estimatedNett,
        soldNett,
        invoicedNett,
        avgPriceSold,
        deliveredTransport,
        invoicedAfterTransport
    };
}

// Helper: make row for nett amounts
function makeNettRow(label, totals, level, parentRow = null) {
    const tr = document.createElement("tr");
    tr.classList.add(level);

    // Hide children by default
    if (parentRow) {
        tr.classList.add("hidden");
        tr.dataset.parentId = parentRow.dataset.rowId;
    }

    tr.dataset.rowId = Math.random().toString(36).slice(2);

    tr.innerHTML = `
        <td>${label}</td>
        <td>${totals.estimatedNett.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.soldNett.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.invoicedNett.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.avgPriceSold.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>${totals.deliveredTransport.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.invoicedAfterTransport.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
    `;

    // Only allow toggling if it has children
    if (level !== "product") {
        tr.addEventListener("click", () => toggleChildren(tr.dataset.rowId));
    }

    return tr;
}

// Show/hide child rows
function toggleChildren(rowId) {
    document.querySelectorAll(`[data-parent-id="${rowId}"]`).forEach(child => {
        child.classList.toggle("hidden");
    });
}