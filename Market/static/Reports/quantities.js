// Cache to store grouped data and DOM fragment for unchanged window.data
window.quantityReportCache = null;

async function loadQuantitiesReport() {
    try {
        const tbody = document.querySelector("#quantitiesTable tbody");
        tbody.innerHTML = "";

        const data = window.data;

        // Use cached result if window.data hasn't changed and fragment is valid
        if (window.quantityReportCache && window.quantityReportCache.data === data && window.quantityReportCache.fragment.hasChildNodes()) {
            tbody.appendChild(window.quantityReportCache.fragment.cloneNode(true)); // Clone to preserve original
            return;
        }

        // Group data and calculate totals in one pass
        const grouped = groupQuantityData(data);
 
        // Build DOM fragment for batched rendering
        const fragment = makeQuantityRows(grouped);
        tbody.appendChild(fragment);

        // Cache the result
        window.quantityReportCache = { data, fragment };
    } catch (err) {
        console.error("Error:", err);
        throw err; // Re-throw to allow caller to handle
    }
}

// Group data in a single pass and compute totals
function groupQuantityData(data) {
  const grouped = {};
  for (const row of data) {
      const mainProdUnit = row.mainprodunitname || "Unknown";
      const date = row.deldate || "Unknown";
      const noteNo = row.delnoteno || "Unknown";
      const prodDesc = row.productdescription || "Unknown";

      // Initialize nested structure with totals
      if (!grouped[mainProdUnit]) {
          grouped[mainProdUnit] = {
              rows: [],
              totals: { delivered: 0, sold: 0, invoiced: 0, notSold: 0 },
              dates: {}
          };
      }
      if (!grouped[mainProdUnit].dates[date]) {
          grouped[mainProdUnit].dates[date] = {
              rows: [],
              totals: { delivered: 0, sold: 0, invoiced: 0, notSold: 0 },
              notes: {}
          };
      }
      if (!grouped[mainProdUnit].dates[date].notes[noteNo]) {
          grouped[mainProdUnit].dates[date].notes[noteNo] = {
              rows: [],
              totals: { delivered: 0, sold: 0, invoiced: 0, notSold: 0 },
              products: {}
          };
      }
      if (!grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc]) {
          grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc] = {
              rows: [],
              totals: { delivered: 0, sold: 0, invoiced: 0, notSold: 0 }
          };
      }

      // Update rows and totals
      const rowTotals = {
          delivered: row.dellinequantitybags || 0,
          sold: row.totalqtysold || 0,
          invoiced: row.totalqtyinvoiced || 0,
          notSold: row.totalnotinvoiced || 0
      };
      grouped[mainProdUnit].rows.push(row);
      grouped[mainProdUnit].totals.delivered += rowTotals.delivered;
      grouped[mainProdUnit].totals.sold += rowTotals.sold;
      grouped[mainProdUnit].totals.invoiced += rowTotals.invoiced;
      grouped[mainProdUnit].totals.notSold += rowTotals.notSold;

      grouped[mainProdUnit].dates[date].rows.push(row);
      grouped[mainProdUnit].dates[date].totals.delivered += rowTotals.delivered;
      grouped[mainProdUnit].dates[date].totals.sold += rowTotals.sold;
      grouped[mainProdUnit].dates[date].totals.invoiced += rowTotals.invoiced;
      grouped[mainProdUnit].dates[date].totals.notSold += rowTotals.notSold;

      grouped[mainProdUnit].dates[date].notes[noteNo].rows.push(row);
      grouped[mainProdUnit].dates[date].notes[noteNo].totals.delivered += rowTotals.delivered;
      grouped[mainProdUnit].dates[date].notes[noteNo].totals.sold += rowTotals.sold;
      grouped[mainProdUnit].dates[date].notes[noteNo].totals.invoiced += rowTotals.invoiced;
      grouped[mainProdUnit].dates[date].notes[noteNo].totals.notSold += rowTotals.notSold;

      grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc].rows.push(row);
      grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc].totals.delivered += rowTotals.delivered;
      grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc].totals.sold += rowTotals.sold;
      grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc].totals.invoiced += rowTotals.invoiced;
      grouped[mainProdUnit].dates[date].notes[noteNo].products[prodDesc].totals.notSold += rowTotals.notSold;
  }
  return grouped;
}

// Build DOM fragment for batched rendering
function makeQuantityRows(grouped) {
    const fragment = document.createDocumentFragment();
    const rowMap = new Map(); // Track rows for parent-child relationships

Object.entries(grouped).forEach(([mainProdUnitName, unitData]) => {
    const unitRow = makeRow(mainProdUnitName, unitData.totals, "market");
    unitRow.classList.add("hover");
    rowMap.set(mainProdUnitName, unitRow);
    fragment.appendChild(unitRow);

    Object.entries(unitData.dates).forEach(([date, dateData]) => {
        const dateRow = makeRow("↳ " + date, dateData.totals, "date", unitRow);
        dateRow.classList.add("hover");
        rowMap.set(`${mainProdUnitName}-${date}`, dateRow);
        fragment.appendChild(dateRow);

        Object.entries(dateData.notes).forEach(([noteNo, noteData]) => {
            const noteRow = makeRow("&nbsp;&nbsp;&nbsp;↳ " + noteNo, noteData.totals, "note", dateRow);
            noteRow.classList.add("hover");
            rowMap.set(`${mainProdUnitName}-${date}-${noteNo}`, noteRow);
            fragment.appendChild(noteRow);

            Object.entries(noteData.products).forEach(([prodDesc, prodData]) => {
                const prodRow = makeRow("      ↳ " + prodDesc, prodData.totals, "product", noteRow);
                fragment.appendChild(prodRow);
            });
        });
    });
});


    return fragment;
}

// Helper: Create a table row
function makeRow(label, totals, level, parentRow = null) {
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
        <td>${totals.delivered.toLocaleString()}</td>
        <td>${totals.sold.toLocaleString()}</td>
        <td>${totals.invoiced.toLocaleString()}</td>
        <td>${totals.notSold.toLocaleString()}</td>
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