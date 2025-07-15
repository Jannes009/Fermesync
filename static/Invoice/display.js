window.marketComm = 0;
window.agentComm = 0;

function fetch_delivery_note_sales() {
    const noteNumber = document.getElementById("delivery-note-number").value;
    const tableContainer = document.getElementById("pivot-table-container");

    fetch("/get_delivery_note_lines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_number: noteNumber }),
    })
    .then(response => response.json())
    .then(data => {
        if (data) {
            window.marketComm = data.market_comm;
            window.agentComm = data.agent_comm;
            
            tableContainer.innerHTML = ""; // Clear previous data

            // Create parent table
            const parentTable = document.createElement("table");
            parentTable.classList.add("parent-table");
            parentTable.innerHTML = `
                <thead>
                    <tr>
                        <th></th>
                        <th>Delivery Note</th>
                        <th>Market Agent</th>
                        <th>Quantity</th>
                        <th>Amount</th>
                        <th><button type="button" id="open-modal" class="button">+</button></th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="main-row" id="row-${data.note_number}" style="font-size: smaller;">
                        <td class="expand-icon" onclick="toggleRows('${data.note_number}')">▶</td>
                        <td><a href="/delivery-note/${data.note_number}" class="delivery-note-link" target="_blank">${data.note_number}</a></td>
                        <td>${data.market_id}</td>
                        <td id="quantity-${data.note_number}"></td>
                        <td id="amount-${data.note_number}"></td>
                        <td><input type="checkbox" class="main-checkbox" data-id="${data.note_number}" /></td>
                    </tr>
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="2" style="text-align: right;">Total Quantity:</td>
                        <td id="total-quantity">0</td>
                        <td colspan="2" style="text-align: right;">Total Amount:</td>
                        <td id="total-selected">R0.00</td>
                    </tr>
                </tfoot>
            `;
            tableContainer.appendChild(parentTable);

            const childContainer = document.createElement("div");
            childContainer.id = `children-${data.note_number}`;
            childContainer.classList.add("hidden");
            tableContainer.appendChild(childContainer);

            let total_amount = 0;
            let total_quantity = 0;

            data.lines.forEach(line => {
                const row = document.createElement("tr");
                row.setAttribute("id", `row-${line.line_id}`)
                row.classList.add("nested-row", "hidden")
                row.innerHTML = `
                    <td class="child-expand-icon" onclick="toggleChildRows('${line.line_id}')">▶</td>
                    <td>${line.stock_id}</td>
                    <td></td>
                    <td id="quantity-${line.line_id}"></td>
                    <td id="amount-${line.line_id}"></td>
                    <td><input type="checkbox" class="line-checkbox" data-id="${data.note_number}-${line.line_id}" /></td>
                `;
                parentTable.appendChild(row);

                let line_amount = 0;
                let line_quantity = 0;

                if (line.sales_lines) {
                    const grandChildRow = document.createElement("td");
                    grandChildRow.id = `grandchildren-${line.line_id}`;
                    grandChildRow.setAttribute("colspan", "6");
                    grandChildRow.classList.add("hidden", "grandchild");
                    parentTable.appendChild(grandChildRow);

                    const grandChildTable = document.createElement("table");
                    grandChildTable.classList.add("grandchild-table");
                    
                    grandChildTable.innerHTML = `
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Amount</th>
                                <th>Select</th>
                            </tr>
                        </thead>
                        <tbody id="grandchild-body-${line.line_id}"></tbody>
                    `;
                    grandChildRow.appendChild(grandChildTable);

                    line.sales_lines.forEach(grandchild => {
                        line_amount += grandchild.amount;
                        line_quantity += grandchild.quantity;
                        
                        const grandchildRow = document.createElement("tr");
                        grandchildRow.classList.add("nested-child-row");
                        grandchildRow.innerHTML = `
                            <td>${grandchild.date}</td>
                            <td>${grandchild.quantity}</td>
                            <td>${grandchild.price}</td>
                            <td>${grandchild.amount}</td>
                            <td><input type="checkbox" class="child-line-checkbox" data-id="${data.note_number}-${line.line_id}-${grandchild.sales_line_id}" /></td>
                        `;
                        grandChildTable.querySelector("tbody").appendChild(grandchildRow);
                    });
                }

                document.getElementById(`amount-${line.line_id}`).innerText = line_amount;
                document.getElementById(`quantity-${line.line_id}`).innerText = line_quantity;
                total_amount += line_amount;
                total_quantity += line_quantity;
            });

            document.getElementById(`amount-${data.note_number}`).innerText = total_amount;
            document.getElementById(`quantity-${data.note_number}`).innerText = total_quantity;
        }
        const openModalButton = document.getElementById("open-modal");

        openModalButton.addEventListener("click", openModal)
    })
    .catch(error => console.error("Error:", error));
}

async function openModal(){
    // Modal open functionality
    const modal = document.getElementById("salesModal");
    salesDetails.style.display = "none";
    const result = await fetchProducts();
    console.log(result); // Will log true/false based on success
    if(result){
        modal.style.display = "block"; // Show the modal
        modalOverlay.style.display = 'block';  // Show the overlay
    }
}



function toggleRows(rowId) {
    const icon = document.querySelector(`#row-${rowId} .expand-icon`);

    if (!icon) return; // Safety check

    const isCollapsed = icon.textContent === "▶";
    const grandChildContainers = document.querySelectorAll(`.grandchild`);

    // Loop through the NodeList and add "hidden" class to each element
    grandChildContainers.forEach(container => {
        container.classList.add("hidden");
    });


    // Update icon
    icon.textContent = isCollapsed ? "▼" : "▶";

    // Find all child rows and toggle them
    const childRows = document.querySelectorAll(".nested-row");
    childRows.forEach(row => {
        row.classList.toggle("hidden", !isCollapsed); // Show if expanding, hide if collapsing
        const childIcon = row.querySelector(`.child-expand-icon`);
        childIcon.textContent = "▶";
    });

}


function toggleChildRows(rowId) {
    const grandChildContainer = document.getElementById(`grandchildren-${rowId}`);
    console.log(grandChildContainer.classList, (grandChildContainer))
    if (grandChildContainer) {
        grandChildContainer.classList.toggle("hidden");
    }
    
    const icon = document.querySelector(`#row-${rowId} .child-expand-icon`);
    if (icon) {
        icon.textContent = icon.textContent === "▶" ? "▼" : "▶";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    // Attach event listener to the parent container for dynamic checkboxes
    const tableContainer = document.getElementById("pivot-table-container");

    tableContainer.addEventListener("change", function(event) {
        const target = event.target;

        // If the changed target is a parent checkbox
        if (target.classList.contains("main-checkbox")) {
            const noteNumber = target.dataset.id;
            const checked = target.checked;
            toggleChildCheckboxes(noteNumber, checked);
            updateTotal()
        }
        
        // If the changed target is a child/grandchild checkbox
        if (target.classList.contains("line-checkbox")) {
            const lineId = target.dataset.id.split("-")[1];
            const checked = target.checked;
            updateParentCheckboxState(lineId, checked);
            updateTotal()
        }
        if( target.classList.contains("child-line-checkbox")){
            const lineId = target.dataset.id.split("-")[1];
            updateParentAndGrandparentCheckboxState(lineId)
            updateTotal()
        }
    });
});

function toggleChildCheckboxes(noteNumber, checked) {
    // Find all child checkboxes for this noteNumber and check/uncheck them
    const childCheckboxes = document.querySelectorAll(`input[data-id^="${noteNumber}-"]`);
    childCheckboxes.forEach(childCheckbox => {
        childCheckbox.checked = checked;
        const grandChildCheckboxes = childCheckbox.querySelectorAll(`.grandchild`)
        grandChildCheckboxes.forEach(grandChildCheckbox => {
            grandChildCheckbox.checked = checked;
        });
    });
}

function updateParentCheckboxState(line_id, checked) {
    const parentCheckbox = document.querySelector(`.main-checkbox`);
    if (!parentCheckbox) return;

    const grandChildCheckboxes = document.querySelectorAll(`#grandchildren-${line_id} .child-line-checkbox`);
    console.log(grandChildCheckboxes)
    grandChildCheckboxes.forEach(grandChildCheckbox => {
        grandChildCheckbox.checked = checked;
    });
    // Select all the checkboxes within the nested rows
    const childCheckboxes = document.querySelectorAll(".nested-row .line-checkbox");

    // Count all checkboxes
    const totalCheckboxes = childCheckboxes.length;

    // Count how many checkboxes are ticked (checked)
    const checkedCheckboxes = Array.from(childCheckboxes).filter(checkbox => checkbox.checked).length;

    if (checkedCheckboxes === totalCheckboxes) {
        parentCheckbox.checked = true;
        parentCheckbox.indeterminate = false; // No dash
    } else if (checkedCheckboxes=== 0) {
        parentCheckbox.checked = false;
        parentCheckbox.indeterminate = false; // No dash
    } else {
        parentCheckbox.checked = false;
        parentCheckbox.indeterminate = true; // Dash
    }
}

function updateParentAndGrandparentCheckboxState(line_id) {
    const parentCheckbox = document.querySelector(`#row-${line_id} .line-checkbox`);
    const grandparentCheckbox = document.querySelector(` .main-checkbox`);

    if (!parentCheckbox || !grandparentCheckbox) {
        alert("not found")
        return;
    }
    // Get all the grandchild checkboxes (checkboxes under this line's grandchildren)
    const grandChildCheckboxes = document.querySelectorAll(`#grandchildren-${line_id} .child-line-checkbox`);
    const totalGrandChildCheckboxes = grandChildCheckboxes.length;
    const checkedGrandChildCheckboxes = Array.from(grandChildCheckboxes).filter(checkbox => checkbox.checked).length;

    // Get all the child checkboxes for the parent (checkboxes within this line)
    const childCheckboxes = document.querySelectorAll(`#row-${line_id} .line-checkbox`);
    const totalChildCheckboxes = childCheckboxes.length;
    const checkedChildCheckboxes = Array.from(childCheckboxes).filter(checkbox => checkbox.checked).length;

    // Check the state of the grandparent (parent) checkbox
    const totalCheckboxes = totalChildCheckboxes + totalGrandChildCheckboxes;
    const checkedCheckboxes = checkedChildCheckboxes + checkedGrandChildCheckboxes;

    // Update the parent checkbox (child line checkbox)
    if (checkedGrandChildCheckboxes === totalGrandChildCheckboxes) {
        parentCheckbox.checked = true;
        parentCheckbox.indeterminate = false;
    } else if (checkedGrandChildCheckboxes === 0) {
        parentCheckbox.checked = false;
        parentCheckbox.indeterminate = false;
    } else {
        parentCheckbox.checked = false;
        parentCheckbox.indeterminate = true;
    }

    // Update the grandparent checkbox
    if (checkedCheckboxes === totalCheckboxes) {
        grandparentCheckbox.checked = true;
        grandparentCheckbox.indeterminate = false;
    } else if (checkedCheckboxes === 0) {
        grandparentCheckbox.checked = false;
        grandparentCheckbox.indeterminate = false;
    } else {
        grandparentCheckbox.checked = false;
        grandparentCheckbox.indeterminate = true;
    }
}

function updateTotal() {
    let total_amount = 0;
    let total_quantity = 0;

    document.querySelectorAll("input[type='checkbox']:checked").forEach(checkbox => {
        const checkboxId = checkbox.getAttribute("data-id");
        const row = checkbox.closest("tr");

        // Check if the row contains a class "main-row" or "nested-row"
        if (!row.classList.contains("main-row") && !row.classList.contains("nested-row")) {

            // Only add the amount for leaf nodes
            const amountCell = row.querySelector("td:nth-child(4)");
            const amount = parseFloat(amountCell.textContent.replace(/[$,]/g, "")) || 0;
            total_amount += amount;

            const quantityCell = row.querySelector("td:nth-child(2)");
            const quantity = parseFloat(quantityCell.textContent.replace(/[$,]/g, "")) || 0;
            total_quantity += quantity;

        }
    });

    // Update the total fields with the final calculations
    document.getElementById("total-selected").textContent = `R${total_amount.toFixed(2)}`;
    document.getElementById("total-quantity").textContent = total_quantity;
}
