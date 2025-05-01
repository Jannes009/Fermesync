let qtySold = null
let currentLineId = null
let salesBefore = null;
let salesBeforeDefined = false;
let salesAdded = null;
let view_mode = false;

function openSalesModal(mode) {
    const template = document.getElementById("sales-modal-template");
    const contentClone = template.content.cloneNode(true);

    // Wrap the cloned content in a container element
    const wrapper = document.createElement("div");
    wrapper.appendChild(contentClone);

    view_mode = false;
    currentMode = mode;

    // Set modal title based on mode
    let modalTitle = "";
    if (mode === "add") modalTitle = "Add Sales";
    else if (mode === "edit") modalTitle = "Edit Sales";
    else if (mode === "view") modalTitle = "View Sales";

    Swal.fire({
        title: modalTitle,
        html: wrapper,
        width: "90%",
        showConfirmButton: mode !== 'view',
        showCancelButton: mode !== 'view',
        confirmButtonText: "Save",
        cancelButtonText: "Add Line",
        reverseButtons: true,
        showCloseButton: true,
        didOpen: () => {
            const container = Swal.getHtmlContainer();

            const totalSalesAmount = container.querySelector('#totalSalesAmount');
            const totalSalesQuantity = container.querySelector('#totalSalesQuantity');
            const salesEntriesList = container.querySelector('.sales-entries-list');
            const newEntryRow = container.querySelector('.new-entry-row');

            totalSalesAmount.textContent = "R0.00";
            totalSalesQuantity.textContent = "0";

            if (mode === "add") {
                salesEntriesList.innerHTML = '';
                newEntryRow.innerHTML = '';
                salesBefore = qtySold;
                fetchQtyAvailable(currentLineId);
                const newRow = addNewRow();
                newEntryRow.appendChild(newRow);
            } else if (mode === 'edit') {
                salesBefore = 0;
                fetchSalesEntries(currentLineId);
            } else if (mode === 'view') {
                view_mode = true;
                fetchSalesEntries(currentLineId, true);
            }

            // Save for use in event handlers
            window.salesModalRefs = {
                container,
                salesEntriesList,
                newEntryRow,
                totalSalesAmount,
                totalSalesQuantity,
            };
        },
        preConfirm: () => {
            return submitSales(); // Only triggered in 'add' and 'edit'
        },
        didRender: () => {
            // Add Line logic
            const addLineBtn = Swal.getCancelButton();
            if (addLineBtn) {
                addLineBtn.addEventListener('click', (e) => {
                    e.preventDefault(); // Prevent modal from closing
                    const newRow = addNewRow();
                    const { newEntryRow } = window.salesModalRefs;
                    newEntryRow.appendChild(newRow);
                });
            }
        }
    });
}


function submitSales(){
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
        const discount = row.querySelector('.discount-input').value || 0;
        const discountAmnt = price * quantity * (discount / 100);
        const destroyed = row.querySelector('.destroyed-checkbox').checked;

        console.log(destroyed)
        if (!date || !quantity) {
            Swal.fire({
                icon: 'error',
                title: 'Invalid input',
                text: 'Date and quantity values are required!',
                timer: 3000,
            });
            isValid = false; // Set the flag to false, preventing form submission
            return; // Stop the loop and function execution
        } else if (price == 0 && amount == 0) {
            Swal.fire({
                icon: 'error',
                title: 'Invalid input',
                text: 'Either Price or Amount are required',
                timer: 3000,
            });
            isValid = false;
            return;
        }

        salesData.push({
            lineId,
            salesId,
            date,
            quantity,
            price,
            discount,
            discountAmnt,
            amount,
            destroyed
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
            const discount = row.querySelector('input[placeholder="Discount"]').value || 0;
            const discountAmnt = price * amount * (discount / 100)
            const destroyed = row.querySelector('.destroyed-checkbox').checked;

            salesData.push({
                lineId: currentLineId,
                salesId: null,
                date,
                quantity,
                price,
                discount,
                discountAmnt,
                amount,
                destroyed
            });
        }

    });

    if (!isValid) {
        return; // If any validation failed, prevent submission
    }

    if (salesData.length === 0) {
        Swal.fire({
            icon: 'warning',
            title: 'No sales data',
            text: 'No sales data to submit!',
            timer: 3000,
        });
        return;
    }
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
            Toast.fire({
                title: 'Sales Created Succesfully',
                icon: 'success'
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Submission failed',
                text: 'Failed to submit data: ' + data['message'],
                timer: 3000,
            });
        }
    })
    .catch((error) => console.error('Error:', error));
}


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
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: `Error fetching quantity: ${data.error}`,
                timer: 3000,
            });
            return;
        }

        // Extract the quantity available
        const qtyAvailable = data.qtyAvailable;
  

        // Update the UI or perform further actions
        document.getElementById('available-for-sale').textContent = qtyAvailable;
    } catch (error) {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: `Failed to fetch quantity available: ${error.message}`,
            timer: 3000,
        });
    }
}


document.addEventListener('DOMContentLoaded', () => {
    const productModalOverlay = document.querySelector('.product-modal-overlay');
    const salesEntriesList = document.querySelector('.sales-entries-list');

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
                openSalesModal(action)
                currentLineId = button.getAttribute('data-id') || null;
                qtySold = row.querySelector('#qty-sold').textContent;
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

    document.addEventListener('triggerAddBtnListener', () => {
        addBtnEventlistener()
    });
       
});

function addNewRow() {
    const newRow = document.createElement('tr');
    newRow.innerHTML = `
        <td><input type="date" placeholder="Enter date" name="date" required></td>
        <td><input type="text" placeholder="Quantity" class="quantity-input" name="quantity" required></td>
        <td><input type="number" placeholder="Price" class="price-input name = "price"></td>
        <td><input type="number" placeholder="Discount" class="discount-input name="discount"></td>
        <td><input type="number" placeholder="Amount" class="amount-input" name="amount"></td>
        <td>
            <input type="checkbox" class="destroyed-checkbox" name="destroyed">
        </td>
        <td>
            <button class="remove-line-btn" onclick="removeRow(this)">
                <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
            </button>
        </td>
    `;
    createEventListener(newRow);
    return newRow
}

function createEventListener(row){
    const priceInput = row.querySelector('.price-input');
    const amountInput = row.querySelector('.amount-input');
    const quantityInput = row.querySelector('.quantity-input');
    const discountInput = row.querySelector('.discount-input');

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

    // Update amount when discount changes
    discountInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const discount = parseFloat(discountInput.value) || 0;  // Corrected this line
        const discountedPrice = price * (1 - discount / 100);
        amountInput.value = (quantity * discountedPrice).toFixed(2);
        console.log("Updating amount with value", (quantity * discountedPrice).toFixed(2));
        updateTotalSalesAmount();
    });

}

const Toast = Swal.mixin({
    toast: true,
    position: 'top-end',
    showConfirmButton: false,
    timer: 1800,
    timerProgressBar: true,
    didOpen: (toast) => {
        toast.addEventListener('mouseenter', Swal.stopTimer);
        toast.addEventListener('mouseleave', Swal.resumeTimer);
    },
    backdrop: false,
});


function removeRow(button) {
    const rowToDelete = button.closest('tr');
    if (!rowToDelete) return;

    const salesId = button.getAttribute('data-id');

    if (!salesId) {
        rowToDelete.remove();
        return;
    }

    fetch(`/delete_sales_entry/${salesId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then((response) => response.json())
    .then((data) => {
        if (data.success) {
            rowToDelete.remove();
            updateTotalSalesAmount();

            Toast.fire({
                icon: 'success',
                title: 'Entry deleted'
            });
        } else {
            Toast.fire({
                icon: 'error',
                title: 'Delete failed',
                text: data.message || 'Unable to delete entry.'
            });
        }
    })
    .catch((error) => {
        console.error('Error deleting entry:', error);
        Toast.fire({
            icon: 'error',
            title: 'Unexpected error',
            text: error.message || 'Something went wrong.'
        });
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
                    console.log(entry)
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><input type="date" value="${entry.date}" required></td>
                        <td><input type="number" value="${entry.quantity}" class="quantity-input" required></td>
                        <td><input type="number" placeholder="price" value="${entry.price}" class="price-input" required></td>
                        <td><input type="number" placeholder="discount" value="${entry.discount}" class="discount-input" required></td>
                        <td><input type="number" placeholder="amount" value="${entry.amount}" class="amount-input" required></td>
                        <td>
                            <input type="checkbox" class="destroyed-checkbox" name="destroyed" ${entry.destroyed ? 'checked' : ''}>
                        </td>
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
                Swal.fire({
                    icon: 'error',
                    title: 'Load Failed',
                    text: 'Failed to retrieve sales entries. Please try again later.',
                    confirmButtonText: 'OK'
                });                
            }
        })
        .catch((error) => {
            console.error('Error fetching sales entries:', error);
        });
}