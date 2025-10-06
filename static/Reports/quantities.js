async function loadQuantitiesReport() {
  console.log("Loading quantities report");
  try {
      const tbody = document.querySelector("#quantitiesTable tbody");
      tbody.innerHTML = "";

      let data = applyGlobalFilters(window.data);

      // Group by Main Product Unit Name
      const mainProdUnits = groupBy(data, "mainprodunitname");
      Object.entries(mainProdUnits).forEach(([mainProdUnitName, unitRows]) => {
          const unitTotals = calcTotals(unitRows);
          const unitRow = makeRow(mainProdUnitName, unitTotals, "market");
          tbody.appendChild(unitRow);
          console.log(unitRow);

          // Group by Date inside Main Product Unit
          const dates = groupBy(unitRows, "deldate");
          Object.entries(dates).forEach(([date, dateRows]) => {
              const dateTotals = calcTotals(dateRows);
              const dateRow = makeRow("↳ " + date, dateTotals, "date", unitRow);
              tbody.appendChild(dateRow);
              console.log(dateRow);

              // Group by Delivery Note inside Date
              const notes = groupBy(dateRows, "delnoteno");
              Object.entries(notes).forEach(([noteNo, noteRows]) => {
                  const noteTotals = calcTotals(noteRows);
                  const noteRow = makeRow("   ↳ " + noteNo, noteTotals, "note", dateRow);
                  tbody.appendChild(noteRow);

                  // Group by Product Description inside Note
                  const products = groupBy(noteRows, "productdescription");
                  Object.entries(products).forEach(([prodDesc, prodRows]) => {
                      const prodTotals = calcTotals(prodRows);
                      const prodRow = makeRow("      ↳ " + prodDesc, prodTotals, "product", noteRow);
                      tbody.appendChild(prodRow);
                  });
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

// Helper: totals
function calcTotals(rows) {
  return {
      delivered: rows.reduce((s, r) => s + (r.dellinequantitybags || 0), 0),
      sold: rows.reduce((s, r) => s + (r.totalqtysold || 0), 0),
      invoiced: rows.reduce((s, r) => s + (r.totalqtyinvoiced || 0), 0),
      notSold: rows.reduce((s, r) => s + (r.totalnotinvoiced || 0), 0)
  };
}

// Helper: make row
function makeRow(label, totals, level, parentRow = null) {
  const tr = document.createElement("tr");
  tr.classList.add(level);

  // hide children by default
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

  // only allow toggling if it has children
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