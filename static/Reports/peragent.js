// Cache to store grouped data and DOM fragment for unchanged window.data
window.perAgentReportCache = null;

async function loadPerAgentReport() {
    console.log("Loading per agent report");
    try {
        const tbody = document.querySelector("#perAgentTable tbody");
        if (!tbody) {
            console.error("Error: #perAgentTable tbody not found");
            throw new Error("Per Agent table not found");
        }
        tbody.innerHTML = ""; // Clear existing content

        const data = applyGlobalFilters(window.data); // Apply filters

        // Use cached result if window.data hasn't changed and fragment is valid
        if (window.perAgentReportCache && window.perAgentReportCache.data === data && window.perAgentReportCache.fragment.hasChildNodes()) {
            console.log("Cache hit for Per Agent");
            tbody.appendChild(window.perAgentReportCache.fragment.cloneNode(true)); // Clone to preserve original
            console.log(`Per Agent table rows: ${tbody.children.length}`);
            return;
        }

        // Group data and calculate totals in one pass
        const grouped = groupPerAgentData(data);
        // Build DOM fragment for batched rendering
        const fragment = makePerAgentRows(grouped);
        tbody.appendChild(fragment); // Clone before appending

        // Cache the result
        window.perAgentReportCache = { data, fragment };
        console.log(`Per Agent table rows: ${tbody.children.length}`);
    } catch (err) {
        console.error("Error in loadPerAgentReport:", err);
        throw err; // Re-throw to allow caller to handle
    }
}

// Group data in a single pass and compute totals
function groupPerAgentData(data) {
    const grouped = {};
    for (const row of data) {
        const agentName = row.agentname || "Unknown";
        const prodDesc = row.productdescription || "Unknown";

        // Initialize nested structure with totals
        if (!grouped[agentName]) {
            grouped[agentName] = {
                rows: [],
                totals: {
                    sold10kg: 0,
                    grossSales: 0,
                    totalCost: 0,
                    nettSales: 0,
                    nettPricePer10kg: 0,
                    soldTransport: 0,
                    salesAfterTrans: 0,
                    afterTransPer10kg: 0
                },
                products: {}
            };
        }
        if (!grouped[agentName].products[prodDesc]) {
            grouped[agentName].products[prodDesc] = {
                rows: [],
                totals: {
                    sold10kg: 0,
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
            sold10kg: (row.totalqtysold || 0) * (weightPerUnit / 10),
            grossSales: row.salesgrossamnt || 0,
            totalCost: row.deliveredtransportcost || 0, // Assuming total cost is transport cost
            nettSales: row.salesnettamnt || 0,
            soldTransport: row.soldtransportcost || 0
        };
        rowTotals.salesAfterTrans = rowTotals.nettSales - rowTotals.soldTransport;
        rowTotals.nettPricePer10kg = rowTotals.sold10kg > 0 ? rowTotals.nettSales / rowTotals.sold10kg : 0;
        rowTotals.afterTransPer10kg = rowTotals.sold10kg > 0 ? rowTotals.salesAfterTrans / rowTotals.sold10kg : 0;

        // Update rows and totals
        grouped[agentName].rows.push(row);
        grouped[agentName].totals.sold10kg += rowTotals.sold10kg;
        grouped[agentName].totals.grossSales += rowTotals.grossSales;
        grouped[agentName].totals.totalCost += rowTotals.totalCost;
        grouped[agentName].totals.nettSales += rowTotals.nettSales;
        grouped[agentName].totals.soldTransport += rowTotals.soldTransport;
        grouped[agentName].totals.salesAfterTrans += rowTotals.salesAfterTrans;

        grouped[agentName].products[prodDesc].rows.push(row);
        grouped[agentName].products[prodDesc].totals.sold10kg += rowTotals.sold10kg;
        grouped[agentName].products[prodDesc].totals.grossSales += rowTotals.grossSales;
        grouped[agentName].products[prodDesc].totals.totalCost += rowTotals.totalCost;
        grouped[agentName].products[prodDesc].totals.nettSales += rowTotals.nettSales;
        grouped[agentName].products[prodDesc].totals.soldTransport += rowTotals.soldTransport;
        grouped[agentName].products[prodDesc].totals.salesAfterTrans += rowTotals.salesAfterTrans;
    }

    // Compute derived metrics for each level
    Object.values(grouped).forEach(agentData => {
        agentData.totals.nettPricePer10kg = agentData.totals.sold10kg > 0 ? agentData.totals.nettSales / agentData.totals.sold10kg : 0;
        agentData.totals.afterTransPer10kg = agentData.totals.sold10kg > 0 ? agentData.totals.salesAfterTrans / agentData.totals.sold10kg : 0;
        Object.values(agentData.products).forEach(prodData => {
            prodData.totals.nettPricePer10kg = prodData.totals.sold10kg > 0 ? prodData.totals.nettSales / prodData.totals.sold10kg : 0;
            prodData.totals.afterTransPer10kg = prodData.totals.sold10kg > 0 ? prodData.totals.salesAfterTrans / prodData.totals.sold10kg : 0;
        });
    });

    return grouped;
}

// Build DOM fragment for batched rendering
function makePerAgentRows(grouped) {
    const fragment = document.createDocumentFragment();
    const rowMap = new Map(); // Track rows for parent-child relationships

    Object.entries(grouped).forEach(([agentName, agentData]) => {
        const agentRow = makePerAgentRow(agentName, agentData.totals, "agent");
        agentRow.classList.add("hover");
        rowMap.set(agentName, agentRow);
        fragment.appendChild(agentRow);

        Object.entries(agentData.products).forEach(([prodDesc, prodData]) => {
            const prodRow = makePerAgentRow("↳ " + prodDesc, prodData.totals, "product", agentRow);
            rowMap.set(`${agentName}-${prodDesc}`, prodRow);
            fragment.appendChild(prodRow);
        });
    });

    return fragment;
}

// Helper: Create a table row for per agent
function makePerAgentRow(label, totals, level, parentRow = null) {
    const tr = document.createElement("tr");
    tr.classList.add(level);

    // Hide children by default
    if (parentRow) {
        tr.classList.add("hidden");
        tr.dataset.parentId = parentRow.dataset.rowId;
    }

    tr.dataset.rowId = Math.random().toString(36).slice(2);

    // Validate row structure
    console.log(`Per Agent row: ${label}, columns: 9, totals:`, totals);

    tr.innerHTML = `
        <td>${label}</td>
        <td>${totals.sold10kg.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.grossSales.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.totalCost.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.nettSales.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.nettPricePer10kg.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>${totals.soldTransport.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td>${totals.salesAfterTrans.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
        <td>${totals.afterTransPer10kg.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
    `;

    // Only allow toggling for agent level
    if (level === "agent") {
        tr.addEventListener("click", () => togglePerAgentChildren(tr.dataset.rowId));
    }

    return tr;
}

// Show/hide child rows
function togglePerAgentChildren(rowId) {
    document.querySelectorAll(`[data-parent-id="${rowId}"]`).forEach(child => {
        child.classList.toggle("hidden");
    });
}