// Cache to store grouped data and DOM fragment for unchanged window.data
window.summaryReportCache = null;

async function loadSummaryReport() {
    console.log("Loading summary report");
    try {
        const tbody = document.querySelector("#summaryTable tbody");
        if (!tbody) {
            console.error("Error: #summaryTable tbody not found");
            throw new Error("Summary table not found");
        }
        tbody.innerHTML = ""; // Clear existing content

        const data = applyGlobalFilters(window.data); // Apply filters

        // Use cached result if window.data hasn't changed and fragment is valid
        if (window.summaryReportCache && window.summaryReportCache.data === data && window.summaryReportCache.fragment.hasChildNodes()) {
            console.log("Cache hit for Summary");
            tbody.appendChild(window.summaryReportCache.fragment.cloneNode(true)); // Clone to preserve original
            console.log(`Summary table rows: ${tbody.children.length}`);
            return;
        }

        // Group data and calculate totals in one pass
        const grouped = groupSummaryData(data);
        // Build DOM fragment for batched rendering
        const fragment = makeSummaryRows(grouped);
        tbody.appendChild(fragment); // Clone before appending

        // Cache the result
        window.summaryReportCache = { data, fragment };
        console.log(`Summary table rows: ${tbody.children.length}`);
    } catch (err) {
        console.error("Error in loadSummaryReport:", err);
        throw err; // Re-throw to allow caller to handle
    }
}

// Group data in a single pass and compute totals
function groupSummaryData(data) {
    const grouped = {};
    for (const row of data) {
        const prodDesc = row.productdescription || "Unknown";
        const agentName = row.agentname || "Unknown";

        // Initialize nested structure with totals
        if (!grouped[prodDesc]) {
            grouped[prodDesc] = {
                rows: [],
                totals: {
                    del10kg: 0,
                    sold10kg: 0,
                    destr10kg: 0,
                    notSold10kg: 0,
                    grossSales: 0,
                    totalCost: 0,
                    nettSales: 0,
                    nettPricePer10kg: 0,
                    soldTransport: 0,
                    salesAfterTrans: 0,
                    afterTransPer10kg: 0
                },
                agents: {}
            };
        }
        if (!grouped[prodDesc].agents[agentName]) {
            grouped[prodDesc].agents[agentName] = {
                rows: [],
                totals: {
                    del10kg: 0,
                    sold10kg: 0,
                    destr10kg: 0,
                    notSold10kg: 0,
                    grossSales: 0,
                    totalCost: 0,
                    nettSales: 0,
                    nettPricePer10kg: 0,
                    soldTransport: 0,
                    salesAfterTrans: 0,
                    afterTransPer10kg: 0
                }
            };
        }

        // Calculate row totals
        const weightPerUnit = row.weightkgperunit || 10; // Default to 10kg
        const rowTotals = {
            del10kg: (row.dellinequantitybags || 0) * (weightPerUnit / 10),
            sold10kg: (row.totalqtysold || 0) * (weightPerUnit / 10),
            destr10kg: (row.destroyedqty || 0) * (weightPerUnit / 10),
            notSold10kg: (row.totalnotinvoiced || 0) * (weightPerUnit / 10),
            grossSales: row.salesgrossamnt || 0,
            totalCost: row.deliveredtransportcost || 0, // Assuming total cost is transport cost
            nettSales: row.salesnettamnt || 0,
            soldTransport: row.soldtransportcost || 0
        };
        rowTotals.salesAfterTrans = rowTotals.nettSales - rowTotals.soldTransport;
        rowTotals.nettPricePer10kg = rowTotals.sold10kg > 0 ? rowTotals.nettSales / rowTotals.sold10kg : 0;
        rowTotals.afterTransPer10kg = rowTotals.sold10kg > 0 ? rowTotals.salesAfterTrans / rowTotals.sold10kg : 0;

        // Update rows and totals
        grouped[prodDesc].rows.push(row);
        grouped[prodDesc].totals.del10kg += rowTotals.del10kg;
        grouped[prodDesc].totals.sold10kg += rowTotals.sold10kg;
        grouped[prodDesc].totals.destr10kg += rowTotals.destr10kg;
        grouped[prodDesc].totals.notSold10kg += rowTotals.notSold10kg;
        grouped[prodDesc].totals.grossSales += rowTotals.grossSales;
        grouped[prodDesc].totals.totalCost += rowTotals.totalCost;
        grouped[prodDesc].totals.nettSales += rowTotals.nettSales;
        grouped[prodDesc].totals.soldTransport += rowTotals.soldTransport;
        grouped[prodDesc].totals.salesAfterTrans += rowTotals.salesAfterTrans;

        grouped[prodDesc].agents[agentName].rows.push(row);
        grouped[prodDesc].agents[agentName].totals.del10kg += rowTotals.del10kg;
        grouped[prodDesc].agents[agentName].totals.sold10kg += rowTotals.sold10kg;
        grouped[prodDesc].agents[agentName].totals.destr10kg += rowTotals.destr10kg;
        grouped[prodDesc].agents[agentName].totals.notSold10kg += rowTotals.notSold10kg;
        grouped[prodDesc].agents[agentName].totals.grossSales += rowTotals.grossSales;
        grouped[prodDesc].agents[agentName].totals.totalCost += rowTotals.totalCost;
        grouped[prodDesc].agents[agentName].totals.nettSales += rowTotals.nettSales;
        grouped[prodDesc].agents[agentName].totals.soldTransport += rowTotals.soldTransport;
        grouped[prodDesc].agents[agentName].totals.salesAfterTrans += rowTotals.salesAfterTrans;
    }

    // Compute derived metrics for each level
    Object.values(grouped).forEach(prodData => {
        prodData.totals.nettPricePer10kg = prodData.totals.sold10kg > 0 ? prodData.totals.nettSales / prodData.totals.sold10kg : 0;
        prodData.totals.afterTransPer10kg = prodData.totals.sold10kg > 0 ? prodData.totals.salesAfterTrans / prodData.totals.sold10kg : 0;
        Object.values(prodData.agents).forEach(agentData => {
            agentData.totals.nettPricePer10kg = agentData.totals.sold10kg > 0 ? agentData.totals.nettSales / agentData.totals.sold10kg : 0;
            agentData.totals.afterTransPer10kg = agentData.totals.sold10kg > 0 ? agentData.totals.salesAfterTrans / agentData.totals.sold10kg : 0;
        });
    });

    return grouped;
}

// Build DOM fragment for batched rendering
function makeSummaryRows(grouped) {
    const fragment = document.createDocumentFragment();
    const rowMap = new Map(); // Track rows for parent-child relationships

    Object.entries(grouped).forEach(([prodDesc, prodData]) => {
        const prodRow = makeSummaryRow(prodDesc, prodData.totals, "product");
        prodRow.classList.add("hover");
        rowMap.set(prodDesc, prodRow);
        fragment.appendChild(prodRow);

        Object.entries(prodData.agents).forEach(([agentName, agentData]) => {
            const agentRow = makeSummaryRow("↳ " + agentName, agentData.totals, "agent", prodRow);
            rowMap.set(`${prodDesc}-${agentName}`, agentRow);
            fragment.appendChild(agentRow);
        });
    });

    return fragment;
}

// Helper: Create a table row for summary
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

    // Only allow toggling for product level
    if (level === "product") {
        tr.addEventListener("click", () => toggleSummaryChildren(tr.dataset.rowId));
    }

    return tr;
}

// Show/hide child rows
function toggleSummaryChildren(rowId) {
    document.querySelectorAll(`[data-parent-id="${rowId}"]`).forEach(child => {
        child.classList.toggle("hidden");
    });
}