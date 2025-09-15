window.marketComm = 0;
window.agentComm = 0;

function fetch_delivery_note_sales() {
    const noteNumber = document.getElementById("delivery-note-number").value;
    const tableContainer = document.getElementById("pivot-table-container");
    console.log("Running")
    fetch("/get_delivery_note_lines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_number: noteNumber }),
    })
    .then(response => response.json())
    .then(data => {
        if (!data) return;

        window.marketComm = data.market_comm;
        window.agentComm = data.agent_comm;

        tableContainer.innerHTML = ""; // Clear previous data
        // ---- DELIVERY NOTE HEADER ----
        const headerCard = document.createElement("div");
        headerCard.classList.add("container-card");

        headerCard.innerHTML = `
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <h3 style="margin:0;">
                    Delivery Note:
                    <a href="/delivery-note/${data.note_number}" target="_blank">
                        ${data.note_number}
                    </a>
                </h3>
            </div>

            <div style="display:flex; flex-wrap:wrap; gap:2rem; margin-top:0.75rem;">
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <strong>Market Agent:</strong>
                    <span>${data.market_id}</span>
                    <label class="switch">
                        <input type="checkbox" id="confirm-agent">
                        <span class="slider round"></span>
                    </label>
                </div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <strong>Production Unit(s):</strong>
                    <span>
                        ${Array.isArray(data.production_units) ? data.production_units.join(", ") : (data.production_units || "N/A")}
                    </span>
                    <label class="switch">
                        <input type="checkbox" id="confirm-units">
                        <span class="slider round"></span>
                    </label>
                </div>
            </div>
        `;
        tableContainer.appendChild(headerCard);


        // ---- PARENT TABLE (LINES) ----
        const parentCard = document.createElement("div");
        parentCard.classList.add("container-card");

        const parentTable = document.createElement("table");
        parentTable.classList.add("fs-table");

        parentTable.innerHTML = `
            <thead>
                <tr>
                    <th></th>
                    <th>Stock</th>
                    <th>Quantity</th>
                    <th>Amount</th>
                    <th>Select</th>
                </tr>
            </thead>
            <tbody id="line-body-${data.note_number}"></tbody>
            <tfoot>
                <tr>
                    <td colspan="2" style="text-align:right;">Total Quantity:</td>
                    <td id="total-quantity">0</td>
                    <td style="text-align:right;">Total Amount:</td>
                    <td id="total-selected">R0.00</td>
                </tr>
            </tfoot>
        `;

        parentCard.appendChild(parentTable);
        tableContainer.appendChild(parentCard);


        const lineBody = parentTable.querySelector("tbody");

        // Build rows and attach listeners inline
        data.lines.forEach(line => {
            let line_amount = 0;
            let line_quantity = 0;

            // ---- LINE ROW ----
            const row = document.createElement("tr");
            row.id = `row-${line.line_id}`;
            row.classList.add("line-row");
            row.innerHTML = `
                <td class="expand-icon" onclick="toggleRow('${line.line_id}')">▶</td>
                <td>${line.stock}</td>
                <td id="quantity-${line.line_id}"></td>
                <td id="amount-${line.line_id}"></td>
                <td><input type="checkbox" class="line-checkbox" data-id="${data.note_number}-${line.line_id}" /></td>
            `;
            lineBody.appendChild(row);

            const lineCheckbox = row.querySelector('.line-checkbox');

            // ---- GRANDCHILD TABLE ----
            let grandChildRow = null;
            if (line.sales_lines && line.sales_lines.length > 0) {
                grandChildRow = document.createElement("tr");
                grandChildRow.id = `grandchildren-${line.line_id}`;
                grandChildRow.classList.add("grandchild", "hidden");

                const grandChildCell = document.createElement("td");
                grandChildCell.colSpan = 5;

                const grandChildTable = document.createElement("table");
                grandChildTable.classList.add("fs-table");
                grandChildTable.innerHTML = `
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Discount</th>
                            <th>Amount</th>
                            <th>Select</th>
                        </tr>
                    </thead>
                    <tbody id="grandchild-body-${line.line_id}"></tbody>
                `;

                grandChildCell.appendChild(grandChildTable);
                grandChildRow.appendChild(grandChildCell);
                lineBody.appendChild(grandChildRow);

                const grandBody = grandChildTable.querySelector("tbody");

                line.sales_lines.forEach(grandchild => {
                    // accumulate
                    line_amount += Number(grandchild.amount) || 0;
                    line_quantity += Number(grandchild.quantity) || 0;

                    const gRow = document.createElement("tr");
                    gRow.innerHTML = `
                        <td>${grandchild.date}</td>
                        <td>${grandchild.quantity}</td>
                        <td>${grandchild.price}</td>
                        <td>${grandchild.discount || "0%"}</td>
                        <td>${grandchild.amount}</td>
                        <td><input type="checkbox" class="child-line-checkbox" data-id="${data.note_number}-${line.line_id}-${grandchild.sales_line_id}" /></td>
                    `;
                    grandBody.appendChild(gRow);

                    // attach listener for this grandchild checkbox
                    const childCheckbox = gRow.querySelector('.child-line-checkbox');
                    if (childCheckbox) {
                        childCheckbox.addEventListener('change', () => {
                            // when a sales-line checkbox changes, update the line's checkbox state and main checkbox, then totals
                            updateLineAndMainState(line.line_id);
                            updateTotals();
                        });
                    }
                });
            } else {
                // No grandchildren -> maybe aggregated values at line-level (if your backend sets them)
                // If the backend provided line-level totals, those should have already been set into the elements below.
                // Attach event listener so line-level selection counts as a leaf selection
                if (lineCheckbox) {
                    lineCheckbox.addEventListener('change', () => {
                        updateLineAndMainState(line.line_id);
                        updateTotals();
                    });
                }
            }

            // If grandchildren exist, make line checkbox toggle them
            if (lineCheckbox) {
                lineCheckbox.addEventListener('change', (e) => {
                    const checked = e.target.checked;
                    const gc = document.getElementById(`grandchildren-${line.line_id}`);
                    if (gc) {
                        gc.querySelectorAll('.child-line-checkbox').forEach(cb => {
                            cb.checked = checked;
                        });
                    }
                    // line checkbox should never be indeterminate when clicked directly
                    lineCheckbox.indeterminate = false;

                    // update main checkbox state and totals
                    updateLineAndMainState(line.line_id);
                    updateTotals();
                });
            }

            // fill line-level quantity/amount cells (if sales_lines exist we already calculated above)
            document.getElementById(`amount-${line.line_id}`).innerText = line_amount;
            document.getElementById(`quantity-${line.line_id}`).innerText = line_quantity;
        });

        // initial totals (zero)
        updateTotals();
    })
    .catch(error => console.error("Error:", error));
}


async function openModal(){
    // Modal open functionality
    const modal = document.getElementById("salesModal");
    const salesDetails = document.getElementById("salesDetails"); // ensure exists
    if (salesDetails) salesDetails.style.display = "none";
    const result = await fetchProducts();
    console.log(result); // Will log true/false based on success
    if(result){
        modal.style.display = "block"; // Show the modal
        const modalOverlay = document.getElementById("modal-overlay");
        if (modalOverlay) modalOverlay.style.display = 'block';  // Show the overlay
    }
}


function toggleRow(lineId) {
    // Find the grandchild row by id
    const grandChildRow = document.getElementById(`grandchildren-${lineId}`);

    // Try to find the main row by id; if missing, assume it's the previous sibling of the grandchild row
    let mainRow = document.getElementById(`row-${lineId}`);
    if (!mainRow && grandChildRow) mainRow = grandChildRow.previousElementSibling;

    // Fallback: look for a cell.expand-icon that contains the lineId (covers older markup)
    if (!mainRow) {
        const iconTd = document.querySelector(`td.expand-icon[onclick*="${lineId}"]`);
        mainRow = iconTd ? iconTd.closest('tr') : null;
    }

    // If still nothing or no grandchildren, nothing to toggle
    if (!mainRow || !grandChildRow) return;

    // Collapse all other grandchild containers (so only one opens at a time)
    document.querySelectorAll('[id^="grandchildren-"]').forEach(el => {
        if (el.id !== `grandchildren-${lineId}`) el.classList.add('hidden');
    });

    // Reset all expand icons to collapsed state
    document.querySelectorAll('td.expand-icon').forEach(td => td.textContent = '▶');

    // Toggle the requested grandchild
    const isCurrentlyHidden = grandChildRow.classList.contains('hidden');
    grandChildRow.classList.toggle('hidden', !isCurrentlyHidden);

    // Update the icon in the main row
    const iconCell = mainRow.querySelector('td.expand-icon');
    if (iconCell) iconCell.textContent = isCurrentlyHidden ? '▼' : '▶';
}


/* ---------------------------
   Checkbox / state utilities
   --------------------------- */

function updateLineAndMainState(lineId) {
    // Update the given line checkbox state based on its child (grandchild) checkboxes,
    // then update the main (select-all) checkbox state.
    const lineCheckbox = document.querySelector(`#row-${lineId} .line-checkbox`);
    const childCheckboxes = document.querySelectorAll(`#grandchildren-${lineId} .child-line-checkbox`);

    if (childCheckboxes.length > 0) {
        const checkedCount = Array.from(childCheckboxes).filter(cb => cb.checked).length;
        if (checkedCount === childCheckboxes.length) {
            if (lineCheckbox) { lineCheckbox.checked = true; lineCheckbox.indeterminate = false; }
        } else if (checkedCount === 0) {
            if (lineCheckbox) { lineCheckbox.checked = false; lineCheckbox.indeterminate = false; }
        } else {
            if (lineCheckbox) { lineCheckbox.checked = false; lineCheckbox.indeterminate = true; }
        }
    }
    // Recalculate overall main checkbox state
    updateMainCheckboxState();
}

function updateMainCheckboxState() {
    const mainCheckbox = document.querySelector('.main-checkbox');
    if (!mainCheckbox) return;

    const lineCheckboxes = Array.from(document.querySelectorAll('.line-checkbox'));
    let totalSelectable = 0;
    let checkedSelectable = 0;

    lineCheckboxes.forEach(cb => {
        const datasetId = cb.dataset.id || "";
        const parts = datasetId.split("-");
        const lineId = parts[1];
        const childCBs = document.querySelectorAll(`#grandchildren-${lineId} .child-line-checkbox`);
        if (childCBs.length === 0) {
            totalSelectable += 1;
            if (cb.checked) checkedSelectable += 1;
        } else {
            totalSelectable += childCBs.length;
            checkedSelectable += Array.from(childCBs).filter(c => c.checked).length;
        }
    });

    if (checkedSelectable === 0) {
        mainCheckbox.checked = false;
        mainCheckbox.indeterminate = false;
    } else if (checkedSelectable === totalSelectable) {
        mainCheckbox.checked = true;
        mainCheckbox.indeterminate = false;
    } else {
        mainCheckbox.checked = false;
        mainCheckbox.indeterminate = true;
    }
}

function parseNumberFromCellText(text) {
    if (!text) return 0;
    // Remove currency and thousands separators but keep dot and minus
    const cleaned = String(text).replace(/[^\d.\-]/g, '');
    return parseFloat(cleaned) || 0;
}

function updateTotals() {
    let total_amount = 0;
    let total_quantity = 0;

    // Sum all checked child-line (sales) checkboxes
    document.querySelectorAll('.child-line-checkbox:checked').forEach(checkbox => {
        const row = checkbox.closest('tr');
        if (!row) return;
        const qtyText = row.cells[1]?.textContent || '';
        const amountText = row.cells[4]?.textContent || '';
        const qty = parseNumberFromCellText(qtyText);
        const amt = parseNumberFromCellText(amountText);
        total_amount += amt;
        total_quantity += qty;
    });

    // Add checked line-checkboxes that have no grandchildren (treat them as leaf rows)
    document.querySelectorAll('.line-checkbox:checked').forEach(cb => {
        const datasetId = cb.dataset.id || "";
        const parts = datasetId.split("-");
        const lineId = parts[1];
        const childCBs = document.querySelectorAll(`#grandchildren-${lineId} .child-line-checkbox`);
        if (childCBs.length === 0) {
            // leaf line row; grab its amount/quantity cells by id
            const qtyEl = document.getElementById(`quantity-${lineId}`);
            const amtEl = document.getElementById(`amount-${lineId}`);
            const qty = qtyEl ? parseNumberFromCellText(qtyEl.textContent) : 0;
            const amt = amtEl ? parseNumberFromCellText(amtEl.textContent) : 0;
            total_amount += amt;
            total_quantity += qty;
        }
    });

    // Update the total fields with the final calculations
    const totalSelectedEl = document.getElementById("total-selected");
    if (totalSelectedEl) totalSelectedEl.textContent = `R${total_amount.toFixed(2)}`;
    const totalQtyEl = document.getElementById("total-quantity");
    if (totalQtyEl) totalQtyEl.textContent = total_quantity;
}
