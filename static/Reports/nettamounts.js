// Cache to store grouped data and DOM fragment for unchanged window.data
window.nettAmountsReportCache = null;

async function loadNettAmountsReport() {
    try {
        const tbody = document.querySelector("#nettAmountsTable tbody");
        tbody.innerHTML = ""; // Clear existing content

        const data = window.data; // Pre-filtered data

        // Use cached result if window.data hasn't changed and fragment is valid
        if (window.nettAmountsReportCache && window.nettAmountsReportCache.data === data && window.nettAmountsReportCache.fragment.hasChildNodes()) {
            tbody.appendChild(window.nettAmountsReportCache.fragment.cloneNode(true)); // Clone to preserve original
            return;
        }

        // Group data and calculate totals in one pass
        const grouped = groupNettAmountData(data);

        // Build DOM fragment for batched rendering
        const fragment = makeNettAmountRows(grouped);
        tbody.appendChild(fragment);

        // Cache the result
        window.nettAmountsReportCache = { data, fragment };
    } catch (err) {
        console.error("Error in loadNettAmountsReport:", err);
        throw err; // Re-throw to allow caller to handle
    }
}

// Group data in a single pass and compute totals
function groupNettAmountData(data) {
    const grouped = {};
    for (const row of data) {
        const date = row.deldate || "Unknown";
        const noteNo = row.delnoteno || "Unknown";
        const prodDesc = row.productdescription || "Unknown";

        // Initialize nested structure with totals
        if (!grouped[date]) {
            grouped[date] = {
                rows: [],
                totals: {
                    estimatedNett: 0,
                    soldNett: 0,
                    invoicedNett: 0,
                    totalQtySold: 0,
                    deliveredTransport: 0,
                    invoicedAfterTransport: 0
                },
                notes: {}
            };
        }
        if (!grouped[date].notes[noteNo]) {
            grouped[date].notes[noteNo] = {
                rows: [],
                totals: {
                    estimatedNett: 0,
                    soldNett: 0,
                    invoicedNett: 0,
                    totalQtySold: 0,
                    deliveredTransport: 0,
                    invoicedAfterTransport: 0
                },
                products: {}
            };
        }
        if (!grouped[date].notes[noteNo].products[prodDesc]) {
            grouped[date].notes[noteNo].products[prodDesc] = {
                rows: [],
                totals: {
                    estimatedNett: 0,
                    soldNett: 0,
                    invoicedNett: 0,
                    totalQtySold: 0,
                    deliveredTransport: 0,
                    invoicedAfterTransport: 0
                }
            };
        }

        // Update rows and totals
        const rowTotals = {
            estimatedNett: row.estimatednett || 0,
            soldNett: row.salesnettamnt || 0,
            invoicedNett: row.invoicednettamnt || 0,
            totalQtySold: row.totalqtysold || 0,
            deliveredTransport: row.deliveredtransportcost || 0,
            invoicedTransport: row.invoicedtransportcost || 0
        };
        grouped[date].rows.push(row);
        grouped[date].totals.estimatedNett += rowTotals.estimatedNett;
        grouped[date].totals.soldNett += rowTotals.soldNett;
        grouped[date].totals.invoicedNett += rowTotals.invoicedNett;
        grouped[date].totals.totalQtySold += rowTotals.totalQtySold;
        grouped[date].totals.deliveredTransport += rowTotals.deliveredTransport;
        grouped[date].totals.invoicedAfterTransport += rowTotals.invoicedNett - rowTotals.invoicedTransport;

        grouped[date].notes[noteNo].rows.push(row);
        grouped[date].notes[noteNo].totals.estimatedNett += rowTotals.estimatedNett;
        grouped[date].notes[noteNo].totals.soldNett += rowTotals.soldNett;
        grouped[date].notes[noteNo].totals.invoicedNett += rowTotals.invoicedNett;
        grouped[date].notes[noteNo].totals.totalQtySold += rowTotals.totalQtySold;
        grouped[date].notes[noteNo].totals.deliveredTransport += rowTotals.deliveredTransport;
        grouped[date].notes[noteNo].totals.invoicedAfterTransport += rowTotals.invoicedNett - rowTotals.invoicedTransport;

        grouped[date].notes[noteNo].products[prodDesc].rows.push(row);
        grouped[date].notes[noteNo].products[prodDesc].totals.estimatedNett += rowTotals.estimatedNett;
        grouped[date].notes[noteNo].products[prodDesc].totals.soldNett += rowTotals.soldNett;
        grouped[date].notes[noteNo].products[prodDesc].totals.invoicedNett += rowTotals.invoicedNett;
        grouped[date].notes[noteNo].products[prodDesc].totals.totalQtySold += rowTotals.totalQtySold;
        grouped[date].notes[noteNo].products[prodDesc].totals.deliveredTransport += rowTotals.deliveredTransport;
        grouped[date].notes[noteNo].products[prodDesc].totals.invoicedAfterTransport += rowTotals.invoicedNett - rowTotals.invoicedTransport;
    }

    // Compute avgPriceSold for each level
    Object.values(grouped).forEach(dateData => {
        dateData.totals.avgPriceSold = dateData.totals.totalQtySold > 0 ? dateData.totals.soldNett / dateData.totals.totalQtySold : 0;
        Object.values(dateData.notes).forEach(noteData => {
            noteData.totals.avgPriceSold = noteData.totals.totalQtySold > 0 ? noteData.totals.soldNett / noteData.totals.totalQtySold : 0;
            Object.values(noteData.products).forEach(prodData => {
                prodData.totals.avgPriceSold = prodData.totals.totalQtySold > 0 ? prodData.totals.soldNett / prodData.totals.totalQtySold : 0;
            });
        });
    });

    return grouped;
}

// Build DOM fragment for batched rendering
function makeNettAmountRows(grouped) {
    const fragment = document.createDocumentFragment();
    const rowMap = new Map(); // Track rows for parent-child relationships

    Object.entries(grouped).forEach(([date, dateData]) => {
        const dateRow = makeNettRow(date, dateData.totals, "date");
        dateRow.classList.add("hover");
        rowMap.set(date, dateRow);
        fragment.appendChild(dateRow);

        Object.entries(dateData.notes).forEach(([noteNo, noteData]) => {
            const noteRow = makeNettRow("↳ " + noteNo, noteData.totals, "note", dateRow);
            noteRow.classList.add("hover");
            rowMap.set(`${date}-${noteNo}`, noteRow);
            fragment.appendChild(noteRow);

            Object.entries(noteData.products).forEach(([prodDesc, prodData]) => {
                const prodRow = makeNettRow("   ↳ " + prodDesc, prodData.totals, "product", noteRow);
                rowMap.set(`${date}-${noteNo}-${prodDesc}`, prodRow); // Track product rows
                fragment.appendChild(prodRow);
            });
        });
    });

    return fragment;
}

// Helper: Create a table row for nett amounts
function makeNettRow(label, totals, level, parentRow = null) {
    const tr = document.createElement("tr");
    tr.classList.add(level);

    // Hide child rows by default (note and product levels)
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

    // Only add toggle listener to parent rows (date and note levels)
    if (level === "date" || level === "note") {
        tr.addEventListener("click", () => toggleNettAmountsChildren(tr.dataset.rowId));
    } else {
        console.log(`No toggle for ${level} row: ${label}`);
    }

    return tr;
}

// Show/hide child rows
function toggleNettAmountsChildren(rowId) {
    const children = document.querySelectorAll(`[data-parent-id="${rowId}"]`);
    children.forEach(child => {
        child.classList.toggle("hidden");
    });
}