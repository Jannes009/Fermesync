function updateTotalSalesAmount() {
    let total_amount = 0;
    let total_quantity = 0;

    const amountInputs = document.querySelectorAll('.amount-input');
    const quantityInputs = document.querySelectorAll('.quantity-input');
    // Do something with amountInputs and quantityInputs for each row

    // Calculate the sum of all amounts
    amountInputs.forEach((input) => {
        const value = parseFloat(input.value) || 0;
        total_amount += value;
    });

    // Calculate the sum of all quantities
    quantityInputs.forEach((input) => {
        const value = parseFloat(input.value) || 0;
        total_quantity += value;
    });


    // // Update the total sales amount display
    document.getElementById('totalSalesAmount').textContent = `R${total_amount.toFixed(2)}`;
    document.getElementById('totalSalesQuantity').textContent = total_quantity.toFixed(0);
    return total_quantity;
}

async function fetchQtyAvailable(saleId) {
    try {
        // Make a GET request to the backend with the sale ID
        const response = await fetch(`/get_qty_available?saleId=${saleId}`);
        
        if (!response.ok) {
            throw new Error(`Error: ${response.status} ${response.statusText}`);
        }

        // Parse the JSON response
        const data = await response.json();

        if (data.error) {
            console.error(`Backend error: ${data.error}`);
            alert(`Error fetching quantity: ${data.error}`);
            return;
        }

        // Extract the quantity available
        const qtyAvailable = data.qtyAvailable;
  

        // Update the UI or perform further actions
        document.getElementById('available-for-sale').textContent = qtyAvailable;
    } catch (error) {
        console.error(`Failed to fetch quantity available: ${error.message}`);
        alert(`Failed to fetch quantity available: ${error.message}`);
    }
}


document.addEventListener('DOMContentLoaded', () => {
    const modalOverlay = document.querySelector('.modal-overlay');
    const productModalOverlay = document.querySelector('.product-modal-overlay');
    const closeModalButton = document.querySelector('.close-btn');
    const defaultDateInput = document.getElementById('default-date');
    const defaultDateContainer = document.getElementById('default-date-container');
    const dateFilterContainer = document.getElementById('date-filter-container');
    const salesEntriesList = document.querySelector('.sales-entries-list');
    const newEntryRow = document.querySelector('.new-entry-row');
    let currentLineId = null;
    let salesBefore = null;
    let salesBeforeDefined = false;
    let salesAdded = null;
    let qtySold = null;
    let view_mode = false;
    // Open modal for Add or Edit
    function addBtnEventlistener(){
        document.querySelectorAll('.change-product-btn').forEach((button) => {
            const row = button.closest('tr');
            button.addEventListener('click',() => {
                currentLineId = button.getAttribute('data-id') || null;
                const currentLine = document.querySelector(`tr[row-id="${currentLineId}"]`);
                const descriptionDiv = currentLine.querySelector('#description'); // Use querySelector here
                const value = descriptionDiv ? descriptionDiv.getAttribute('data-value') : null; // Check if descriptionDiv exists                

                console.log(currentLine, descriptionDiv, value)
                changeProductModal(currentLineId, value)
                productModalOverlay.style.display = 'block';
            })
        })
        document.querySelectorAll('.add-sales-btn, .edit-sales-btn, .view-sales-btn').forEach((button) => {
            const row = button.closest('tr');
            button.addEventListener('click', (event) => {
                
                const action = button.getAttribute('data-action');
                view_mode = false;
                currentMode = action;
                currentLineId = button.getAttribute('data-id') || null;
                modalOverlay.style.display = 'block';
        
                qtySold = row.querySelector('#qty-sold').textContent;

                document.querySelector('.add-line-btn').style.display = 'flex';
                document.querySelector('.save-btn').style.display = 'flex';
        
                // Update the total sales amount display
                document.getElementById('totalSalesAmount').textContent = "R0.00";
                document.getElementById('totalSalesQuantity').textContent = "0";
        
                // Toggle modal content based on mode
                if (action === 'add') {
                    document.getElementById('modal-title').textContent = 'Add Sales';
                    defaultDateContainer.style.display = 'block';
                    dateFilterContainer.style.display = 'none';
                    salesEntriesList.innerHTML = ''; // Clear existing rows
                    newEntryRow.innerHTML = ''; // Clear new entry rows
                    salesBefore = qtySold;
                    fetchQtyAvailable(currentLineId);
                    addNewRow(); // Add a clean row
                } else if (action === 'edit') {
                    document.getElementById('modal-title').textContent = 'Edit Sales';
                    defaultDateContainer.style.display = 'none';
                    dateFilterContainer.style.display = 'block';
                    fetchSalesEntries(currentLineId); // Fetch past entries
                } else if (action === 'view') {
                    view_mode = true;
                    document.getElementById('modal-title').textContent = 'View Sales';
                    defaultDateContainer.style.display = 'none';
                    dateFilterContainer.style.display = 'block';
                    fetchSalesEntries(currentLineId, true); // Fetch past entries
        
                    // Hide Save and Add Line buttons
                    document.querySelector('.add-line-btn').style.display = 'none';
                    document.querySelector('.save-btn').style.display = 'none';
                }
            });
        });         
    }


    // MutationObserver to monitor when new rows are added to the table
    const observer = new MutationObserver(() => {
        console.log("Viewmode: ", view_mode);
        
        if (!salesBeforeDefined) {
            // Assuming qtySold is defined somewhere and is a string
            let qtySold = 10;  // Example qtySold value
            salesBefore = parseFloat(qtySold) - parseFloat(updateTotalSalesAmount());
            console.log(salesBefore);
        } else {
            updateTotalSalesAmount(); // Recalculate totals after DOM changes
        }

        if (view_mode) {
            // Make all input fields in the modal read-only
            document.querySelectorAll('.modal-content input, #salesModal select, #salesModal textarea')
            .forEach((input) => {
                console.log(input);
                if (input.tagName.toLowerCase() === 'input') {
                    input.setAttribute('readonly', true); // For input elements
                } else {
                    input.setAttribute('disabled', true); // For select and other elements
                }
            });

            console.log(document.querySelectorAll('.remove-line-btn'));

            // Remove all delete buttons in the modal
            document.querySelectorAll('.sales-entries-list .remove-line-btn').forEach((button) => {
                button.remove();
            });
        }
    });

    // Observe changes in the salesEntriesList and newEntryRow containers
    observer.observe(salesEntriesList, { childList: true });
    observer.observe(newEntryRow, { childList: true });

    // Close modal
    closeModalButton.addEventListener('click', () => {
        modalOverlay.style.display = 'none';
    });

    // Add new line
    document.querySelector('.add-line-btn').addEventListener('click', () => {
        addNewRow();
    });

    function addNewRow() {
        const dateValue = defaultDateInput.value || ''; // Use default date if set
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td><input type="date" placeholder="Enter date" value="${dateValue}" name="date" required></td>
            <td><input type="text" placeholder="Quantity" class="quantity-input" name="quantity" required></td>
            <td><input type="number" placeholder="Price" class="price-input name = "price"></td>
            <td><input type="number" placeholder="Amount" class="amount-input" name="amount"></td>
            <td>
                <button class="remove-line-btn" onclick="removeRow(this)">
                    <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                </button>
            </td>
        `;
        newEntryRow.appendChild(newRow);
        createEventListener(newRow);
        return newRow
    }

    function filterSalesEntries(lineId, startDate, endDate) {
        fetch(`/filter_sales_entries?startDate=${startDate}&endDate=${endDate}&lineId=${lineId}`)
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    console.log(data)
                    salesEntriesList.innerHTML = ''; // Clear existing entries
                    data.sales_entries.forEach((entry) => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td><input type="date" value="${entry.sale_date}" name="date" required></td>
                            <td><input type="number" value="${entry.quantity}" class="quantity-input" name="quantity" required></td>
                            <td><input type="number" value="${entry.price}" class="price-input" name="price" required></td>
                            <td><input type="number" value="${entry.amount}" class="amount-input" name="amount" required></td>
                            <td>
                                <button class="remove-line-btn" data-id="${entry.salesLineIndex}" onclick="removeRow(this)">
                                    <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                                </button>
                            </td>
                        `;
                        salesEntriesList.appendChild(row);
                        salesBeforeDefined = false;
                        createEventListener(row);
                    });
                } else {
                    alert('No sales entries found for the specified dates.');
                }
            })
            .catch((error) => {
                console.error('Error fetching filtered sales entries:', error);
            });

    }
    
    document.getElementById('filter-sales-btn').addEventListener('click', () => {
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;

        if (!startDate || !endDate) {
            alert('Please select both start and end dates.');
            return;
        }

        filterSalesEntries(currentLineId, startDate, endDate)
    });
    document.addEventListener('triggerAddBtnListener', () => {
        addBtnEventlistener()
    });
    // Submit sales data
    document.querySelector('.modal-footer button[type="submit"]').addEventListener('click', () => {
        const salesData = [];
        let isValid = true; // Flag to track if submission should continue
        salesAdded = document.getElementById('totalSalesQuantity').textContent;


        // Collect data from existing entries
        const existingRows = document.querySelectorAll('.sales-entries-list tr');
        existingRows.forEach(row => {
            const lineId = currentLineId;
            const salesId = row.querySelector('button').getAttribute('data-id');  // Get the data-id attribute value;
            const date = row.querySelector('input[type="date"]').value;
            const quantity = row.querySelector('.quantity-input').value;
            const price = row.querySelector('.price-input').value || 0;
            const amount = row.querySelector('.amount-input').value || 0;

            if (!date || !quantity) {
                alert('Date and quantity values are required!');
                isValid = false; // Set the flag to false, preventing form submission
                return; // Stop the loop and function execution
            } else if (price == 0 && amount == 0) {
                alert('Either Price or Amount are required');
                isValid = false;
                return;
            }

            salesData.push({
                lineId,
                salesId,
                date,
                quantity,
                price,
                amount,
            });
        });

        // Collect data from new entries
        const newRows = document.querySelectorAll('.new-entry-row tr');
        newRows.forEach(row => {
            if(row.querySelector('input[type="date"]')){
                const date = row.querySelector('input[type="date"]').value;
                const quantity = row.querySelector('.quantity-input').value;
    
                const price = row.querySelector('input[placeholder="Price"]').value || 0;
                const amount = row.querySelector('input[placeholder="Amount"]').value || 0;
    
                if (price == 0 && amount == 0) {
                    alert("Price or amount is required");
                    isValid = false;
                    return; // Stop further execution if data is invalid
                }
    
                salesData.push({
                    lineId: currentLineId,
                    salesId: null,
                    date,
                    quantity,
                    price,
                    amount,
                });
            }

        });

        if (!isValid) {
            return; // If any validation failed, prevent submission
        }

        if (salesData.length === 0) {
            alert('No sales data to submit!');
            return;
        }
        console.log(salesData)
        // Send data to the backend
        fetch('/submit_sales_entries', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                salesEntries: salesData,
            }),
        })
        .then((response) => response.json())
        .then((data) => {
            if (data.success) {
                const rowChanged = document.querySelector(`[row-id='${currentLineId}']`);
                
                // update quantity sold
                const qtySold = parseInt(salesBefore) + parseInt(salesAdded);
                rowChanged.querySelector('#qty-sold').textContent = qtySold;

                // remove product change button if qty sold > 0
                if(qtySold > 0){
                    const changeBtn = rowChanged.querySelector('.change-product-btn')
                    if(changeBtn){
                        changeBtn.remove()
                    }
                }

                alert('Data submitted successfully!');
                document.querySelector('.modal-overlay').style.display = 'none';
            } else {
                alert('Failed to submit data: ' + data['message']);
            }
        })
        .catch((error) => console.error('Error:', error));
    });
    $(document).on('keydown', 'input[name="date"], input[name="quantity"], input[name="price"], input[name="amount"]', function (e) {
        if (e.key === 'Tab' || e.keyCode === 9) {
            e.preventDefault(); // Prevent default tabbing behavior
    
            let currentInput = $(this);
            let currentRow = currentInput.closest('tr');
            let nextRow = currentRow.next(); // Get the next row
            let inputName = currentInput.attr('name');
    
            let nextInput = nextRow.find(`input[name="${inputName}"]`);
    
            if (nextRow.length === 0) {
                let newRow = $(addNewRow()); // Convert returned plain DOM element to a jQuery object
                nextInput = newRow.find(`input[name="${inputName}"]`);
            }
    
            if (nextInput.length) {
                nextInput.focus();
            }
        }
    });
       
});



function createEventListener(row){
    const priceInput = row.querySelector('.price-input');
    const amountInput = row.querySelector('.amount-input');
    const quantityInput = row.querySelector('.quantity-input');

    // Update amount when price changes
    priceInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const amount = parseFloat(quantityInput.value) || 0;
        amountInput.value = (quantity * price).toFixed(2);
        updateTotalSalesAmount()
    });

    // Update price when amount changes
    amountInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const amount = parseFloat(amountInput.value) || 0;
        priceInput.value = quantity ? (amount / quantity).toFixed(2) : '0.00';
        updateTotalSalesAmount()
    });

    // Update both when quantity changes
    quantityInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        amountInput.value = (quantity * price).toFixed(2);
        updateTotalSalesAmount()
    });
}

function removeRow(button) {
    const rowToDelete = button.closest('tr');
    if (!rowToDelete) return;

    const salesId = button.getAttribute('data-id');

    if (!salesId) {
        rowToDelete.remove();
        return;
    }

    // Send delete request to the backend
    fetch(`/delete_sales_entry/${salesId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then((response) => response.json())
    .then((data) => {
        if (data.success) {
            // Remove the row only if the backend deletion is successful
            rowToDelete.remove();
            alert('Entry deleted successfully!');
            updateTotalSalesAmount();
        } else {
            alert('Failed to delete entry!');
        }
    })
    .catch((error) => {
        console.error('Error deleting entry:', error);
        alert('An error occurred while deleting the entry.');
    });
}

function fetchSalesEntries(lineId, viewMode=false) {
    const salesEntriesList = document.querySelector('.sales-entries-list');
    console.log(viewMode)
    
    // Build the URL with the `viewMode` parameter
    const url = `/get_sales_entries/${lineId}?viewMode=${viewMode}`;
    fetch(url)
        .then((response) => response.json())
        .then((data) => {
            if (data.success) {
                salesEntriesList.innerHTML = ''; // Clear existing entries

                data.sales_entries.forEach((entry) => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><input type="date" value="${entry.date}" required></td>
                        <td><input type="number" value="${entry.quantity}" class="quantity-input" required></td>
                        <td><input type="number" placeholder="price" value="${entry.price}" class="price-input" required></td>
                        <td><input type="number" placeholder="amount" value="${entry.amount}" class="amount-input" required></td>
                        <td>
                            <button class="remove-line-btn" onclick="removeRow(this)" data-id="${entry.salesLineIndex}">
                                <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                            </button>
                        </td>
                    `;

                    // Append the new row
                    salesEntriesList.appendChild(row);
                    createEventListener(row);
                });
                document.querySelector('.new-entry-row').innerHTML = '';
                document.getElementById('available-for-sale').innerText = data.available_for_sale

            } else {
                alert('Failed to retrieve sales entries');
            }
        })
        .catch((error) => {
            console.error('Error fetching sales entries:', error);
        });
}

document.getElementById('default-date').addEventListener('change', function(event) {
    // Get the changed value of the default date
    const selectedDate = event.target.value;

    // Select all input elements with type="date"
    const dateInputs = document.querySelectorAll('input[type="date"]');

    // Set the value of each input[type="date"] to the selected value
    dateInputs.forEach(input => {
        input.value = selectedDate;
    });
});