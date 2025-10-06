async function loadSummaryReport() {
    console.log("Loading summary report");
    try {
        const tbody = document.querySelector("#summaryTable tbody");
        tbody.innerHTML = "";

        let data = applyGlobalFilters(window.data);

        // Group by Product Description
        const products = groupBy(data, "productdescription");
        Object.entries(products).forEach(([prodDesc, prodRows]) => {
            const prodTotals = calcSummaryTotals(prodRows);
            const prodRow = makeSummaryRow(prodDesc, prodTotals, "product");
            tbody.appendChild(prodRow);

            // Group by Agent Name inside Product
            const agents = groupBy(prodRows, "agentname");
            Object.entries(agents).forEach(([agentName, agentRows]) => {
                const agentTotals = calcSummaryTotals(agentRows);
                const agentRow = makeSummaryRow("↳ " + agentName, agentTotals, "agent", prodRow);
                tbody.appendChild(agentRow);
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

// Helper: calculate totals for summary
function calcSummaryTotals(rows) {
    const weightPerUnit = rows[0]?.weightkgperunit || 10; // Default to 10kg if not specified
    const del10kg = rows.reduce((s, r) => s + (r.dellinequantitybags || 0) * (r.weightkgperunit / 10), 0);
    const sold10kg = rows.reduce((s, r) => s + (r.totalqtysold || 0) * (r.weightkgperunit / 10), 0);
    const destr10kg = rows.reduce((s, r) => s + (r.destroyedqty || 0) * (r.weightkgperunit / 10), 0);
    const notSold10kg = rows.reduce((s, r) => s + (r.totalnotinvoiced || 0) * (r.weightkgperunit / 10), 0);
    const grossSales = rows.reduce((s, r) => s + (r.salesgrossamnt || 0), 0);
    const totalCost = rows.reduce((s, r) => s + (r.deliveredtransportcost || 0), 0); // Assuming total cost is transport cost
    const nettSales = rows.reduce((s, r) => s + (r.salesnettamnt || 0), 0);
    const nettPricePer10kg = sold10kg > 0 ? nettSales / sold10kg : 0;
    const soldTransport = rows.reduce((s, r) => s + (r.soldtransportcost || 0), 0);
    const salesAfterTrans = nettSales - soldTransport;
    const afterTransPer10kg = sold10kg > 0 ? salesAfterTrans / sold10kg : 0;

    return {
        del10kg,
        sold10kg,
        destr10kg,
        notSold10kg,
        grossSales,
        totalCost,
        nettSales,
        nettPricePer10kg,
        soldTransport,
        salesAfterTrans,
        afterTransPer10kg
    };
}

// Helper: make row for summary
function makeSummaryRow(label, totals, level, parentRow = null) {
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
        <td>${totals.del10kg.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.sold10kg.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.destr10kg.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.notSold10kg.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.grossSales.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.totalCost.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.nettSales.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.nettPricePer10kg.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>${totals.soldTransport.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>${totals.salesAfterTrans.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.afterTransPer10kg.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
    `;

    // Only allow toggling if it has children
    if (level === "product") {
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