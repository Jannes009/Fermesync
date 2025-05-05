document.addEventListener("DOMContentLoaded", () => {
    const rows = document.querySelectorAll(".main-row");

    rows.forEach(row => {
        const button = row.querySelector(".expand-btn");
        button.addEventListener("click", (event) => {
            event.stopPropagation(); // Prevent row click
            const entryId = row.getAttribute("data-entry-id");
            const detailsRow = document.querySelector(`#details-${entryId}`);
            const isHidden = detailsRow.classList.contains("hidden");
    
            // Toggle the button rotation and row visibility
            button.classList.toggle("rotate", isHidden);
            detailsRow.classList.toggle("hidden");
    
            if (isHidden) {
                // Fetch additional data via AJAX (replace with your API endpoint)
                fetch(`/entry/details/${entryId}`)
                    .then(response => response.json())
                    .then(response => {
                        if (response.success) {
                            const detailsTable = `
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Description</th>
                                            <th>Qty Delivered</th>
                                            <th>Qty Sold</th>
                                            <th>Qty Invoiced</th>
                                            <th>Sales</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${response.data.map(line => {
                                            const fullyInvoiced = line.fullyInvoiced;
                                            const isQtySoldZero = line.qty_sold === 0; // Check if salesQty is 0
                    
                                            return `
                                                <tr row-id="${line.lineId}">
                                                    <td>
                                                        ${
                                                            isQtySoldZero
                                                                ? `
                                                                <div class="description-container">
                                                                    <div id="description" data-value="${line.product_id}">${line.description}</div>
                                                                    <button type="button" class="change-product-btn" data-action="change" data-id="${line.lineId}">
                                                                        <img src="../static/Image/change.png" alt="Change Product" class="action-icon">
                                                                    </button>
                                                                </div>

                                                                `
                                                                : `${line.description}`
                                                        }
                                                    </td>
                                                    <td>${line.quantity}</td>
                                                    <td id="qty-sold">${line.qty_sold}</td>
                                                    <td>${line.qty_invoiced}</td>
                                                    <td class="button-row">
                                                        ${
                                                            fullyInvoiced
                                                                ? `<button type="button" class="view-sales-btn" data-action="view" data-id="${line.lineId}">
                                                                    <img src="../static/Image/view.png" alt="View Sales" class="action-icon">
                                                                  </button>`
                                                                : `
                                                                    <button type="button" class="add-sales-btn" data-action="add" data-id="${line.lineId}">
                                                                        <img src="../static/Image/add.png" alt="Add Sales" class="action-icon">
                                                                    </button>
                                                                    <button type="button" class="edit-sales-btn" data-action="edit" data-id="${line.lineId}">
                                                                        <img src="../static/Image/edit.png" alt="Edit Sales" class="action-icon">
                                                                    </button>
                                                                `
                                                        }
                                                    </td>
                                                </tr>
                                            `;
                                        }).join('')}
                                    </tbody>
                                </table>
                            `;
                            detailsRow.querySelector("div").innerHTML = detailsTable;
                    
                            // Populate dropdowns for rows where salesQty = 0
                            const dropdowns = detailsRow.querySelectorAll(".searchable-dropdown");
                            const productOptions = response.product_options; // Assuming product_options is an array of [value, text]

                            dropdowns.forEach((dropdown, index) => {
                                const productId = response.data[index].product_id; // Get product_id for the current row
                                
                                productOptions.forEach(([value, text]) => {
                                    const option = new Option(text, value);
                                    dropdown.appendChild(option);
                                });

                                // Set the dropdown value to the product_id of the current row
                                dropdown.value = productId;

                                // Optionally initialize Select2 for enhanced dropdowns
                                // $(dropdown).select2(); // Uncomment if Select2 is properly loaded
                            });

                    
                            document.dispatchEvent(new Event('triggerAddBtnListener'));
                        } else {
                            detailsRow.querySelector("div").innerHTML = "No details available.";
                        }
                    })                   
                    .catch(error => {
                        detailsRow.querySelector("div").innerHTML = "Failed to load details.";
                        console.error("Error fetching details:", error);
                    });
            }
        });
    });
});

document.getElementById('clear-filters').addEventListener('click', function() {
    // Reset the form fields
    const form = document.querySelector('.filter-section');
    form.reset();

    // Submit the form to the '/view_entries' route with no filters applied
    form.action = '/view_entries';  // Ensure it submits to the correct route
    form.method = 'GET';  // Ensure it's a GET request for fetching the data
    form.submit();  // Submit the form
});

document.querySelectorAll('.edit-sales-btn').forEach(button => {
    console.log(button);
    button.addEventListener('click', (event) => {
        const entryId = button.getAttribute('data-id');
        console.log(entryId);
        window.location.href = `/edit_entry/${entryId}`;
    });
});
