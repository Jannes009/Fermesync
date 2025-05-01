let qtyAvailable = 0;
let selectedProductId = null;

document.addEventListener("DOMContentLoaded", function () {
    const salesModal = document.getElementById("salesModal");
    const productTableBody = document.getElementById("productTableBody");
    const fetchProductsButton = document.getElementById("fetchProducts");
    const productSelection = document.getElementById("productSelection");
    const salesDetails = document.getElementById("salesDetails");
    const prevStepButton = document.getElementById("prevStep");
    const addLineButton = document.getElementById("addLine");
    const submitSalesButton = document.getElementById("submitSales");
    const salesTableBody = document.getElementById("salesTableBody");
    const modalOverlay = document.getElementById("modalOverlay");
    const closeButton = document.querySelector(".close-btn");

    function closeModal() {
        salesModal.style.display = "none";
        modalOverlay.style.display = "none";
        fetch_delivery_note_sales()
    }

    closeButton.addEventListener("click", closeModal);
    modalOverlay.addEventListener("click", closeModal);

    let salesBefore = 0;

    function addRow(){
        const row = document.createElement("tr");
        row.innerHTML = `
            <td><input type="date" name="date-input" required></td>
            <td><input type="number" class="quantity-input" name="quantity-input" placeholder="Quantity" required></td>
            <td><input type="number" class="price-input" placeholder="Price"></td>
            <td><input type="number" class="discount-input" value="0" placeholder="Discount"></td>
            <td><input type="number" class="amount-input" placeholder="Amount"></td>
            <td>
                <input type="checkbox" class="destroyed-checkbox" name="destroyed">
            </td>
            <td>
                <button class="remove-line-btn" onclick="removeRow(this)">
                    <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                </button>
            </td>
        `;
        createEventListener(row)
        row.querySelector(".remove-line-btn").addEventListener("click", function () {
            row.remove();
        });

        salesTableBody.appendChild(row);
    }

    // Add a new sale entry row
    addLineButton.addEventListener("click", function () {
        addRow()
    });

    // Back to product selection
    prevStepButton.addEventListener("click", function () {
        salesDetails.style.display = "none";
        productSelection.style.display = "block";
    });


    submitSalesButton.addEventListener("click", function () {
        const salesData = [];
        let isValid = true;  // Validation flag
        let salesAdded = 0;  // Track added sales quantity
        let errorMessage = ''; // Collect error messages for better UX
    
        // Loop through each row to collect sales data
        document.querySelectorAll("#salesTableBody tr").forEach(row => {
            const dateInput = row.querySelector('input[type="date"]');
            const quantityInput = row.querySelector('input[placeholder="Quantity"]');
            const priceInput = row.querySelector('input[placeholder="Price"]');
            const amountInput = row.querySelector('input[placeholder="Amount"]');
            const discountInput = row.querySelector('input[placeholder="Discount"]');
            const destroyed = row.querySelector('.destroyed-checkbox').checked;
    
            if (dateInput && quantityInput) {
                const date = dateInput.value;
                const quantity = Number(quantityInput.value);
                const price = Number(priceInput.value) || 0;
                const amount = Number(amountInput.value) || 0;
                const discount = Number(discountInput.value) || 0;
                salesAdded += quantity;
                const discountAmnt = price * quantity * (discount / 100);

                console.log(amount, discount, discount / 100, discountAmnt)
                
                if (!date || isNaN(new Date(date).getTime())) {
                    errorMessage = 'A valid date is required.';
                    isValid = false;
                    return; // Stop further execution if validation fails
                }
    
                // Validate if either price or amount is filled
                if (price === 0 && amount === 0) {
                    errorMessage = 'Price or amount is required for all entries.';
                    isValid = false;
                    return; // Stop further execution if validation fails
                }
    
                // Validate if quantity is valid
                if (quantity <= 0) {
                    errorMessage = 'Quantity must be greater than 0.';
                    isValid = false;
                    return;
                }
                // Add the sales entry to the array
                salesData.push({
                    lineId: selectedProductId,
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
    
        // Validate stock availability
        if (salesAdded > qtyAvailable) {
            isValid = false;
            errorMessage = 'Not enough stock available.';
        }
    
        // If any validation failed, show error and stop execution
        if (!isValid) {
            alert(errorMessage);
            return;
        }
    
        // Check if there's any data to submit
        if (salesData.length === 0) {
            alert('No sales data to submit!');
            return;
        }
        salesDetails.style.display = "none";
        productSelection.style.display = "block";
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
        .then(async (data) => {
            if (data.success) {
                const rowChanged = document.querySelector(`[row-id='${selectedProductId}']`);
                
                // Update the quantity sold
                const qtySold = Number(salesBefore) + salesAdded;
                // rowChanged.querySelector('#qty-sold').textContent = qtySold;
    
                // Remove the product change button if qty sold > 0
                if (qtySold < 0) {
                    const changeBtn = rowChanged.querySelector('.change-product-btn');
                    if (changeBtn) {
                        changeBtn.remove();
                    }
                }
                await fetchProducts()
            } else {
                alert('Failed to submit data: ' + data.message);
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            alert('An error occurred while submitting the data.');
        });
    });
    addRow()
});

// Function to fetch products based on the Delivery Note number
async function fetchProducts() {
    const deliveryNoteNumber = document.getElementById("delivery-note-number").value.trim();
    let noteNumberIconSrc = document.getElementById('del-note-number-icon').getAttribute('src');

    // Check if 'noteNumberIconSrc' contains 'neutral' or 'error'
    if (noteNumberIconSrc.includes('neutral') || noteNumberIconSrc.includes('error')) {
        alert("This delivery note doesn't exist")
        return false;  // Exit the function or stop further execution
    }      
    
    try {
        // Wait for the delivery note ID to be fetched before proceeding
        const deliveryNoteId = await fetchDeliveryNoteId(deliveryNoteNumber);
        console.log(deliveryNoteId);

        // Fetch the products using the fetched Delivery Note ID
        const response = await fetch(`/entry/details/${deliveryNoteId}`);
        const data = await response.json();

        if (data.success) {
            const productTableBody = document.getElementById("productTableBody");
            productTableBody.innerHTML = "";  // Clear previous results

            data.data.forEach(product => {
                const row = document.createElement("tr");
                row.classList.add("product-line");
                row.dataset.id = product.lineId;
                row.innerHTML = `
                    <td>${product.description}</td>
                    <td>${product.quantity}</td>
                    <td>${product.qty_sold}</td>
                    <td>${product.qty_invoiced}</td>
                `;
                row.addEventListener("click", function () {
                    document.querySelectorAll(".product-line").forEach(r => r.classList.remove("selected"));
                    row.classList.add("selected");
                    selectedProductId = product.lineId;
                    salesBefore = product.qty_sold;
                    qtyAvailable = product.quantity - product.qty_sold
                    console.log("Sales availbable:", qtyAvailable)
                    productSelection.style.display = "none";
                    salesDetails.style.display = "block";
                });
                productTableBody.appendChild(row);
            });

            productSelection.style.display = "block";
            return true;
        } else {
            alert("Failed to fetch products.");
            return false;
        }
    } catch (error) {
        console.error("Error fetching products:", error);
        alert("Error fetching products.");
        return false;
    }
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
        const discount = parseFloat(discountInput.value) || 0;
        amountInput.value = (quantity * (price * (1 - discount / 100))).toFixed(2);
        // updateTotalSalesAmount()
    });

    // Update price when amount changes
    amountInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const amount = parseFloat(amountInput.value) || 0;
        const price = quantity ? (amount / quantity).toFixed(2) : '0.00';
        priceInput.value = price;
        const discount = parseFloat(discountInput.value) || 0;
        amountInput.value = (quantity * (price * (1 - discount / 100))).toFixed(2);
        // updateTotalSalesAmount()
    });

    // Update both when quantity changes
    quantityInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const discount = parseFloat(discountInput.value) || 0;
        amountInput.value = (quantity * (price * (1 - discount / 100))).toFixed(2);
        // updateTotalSalesAmount()
    });
    // Update amount when discount changes
    discountInput.addEventListener('input', () => {
        const quantity = parseFloat(quantityInput.value) || 0;
        const price = parseFloat(priceInput.value) || 0;
        const discount = parseFloat(discountInput.value) || 0;
        amountInput.value = (quantity * (price * (1 - discount / 100))).toFixed(2);
        // updateTotalSalesAmount()
    });
}

function check_delivery_note(){
    let inputField = document.getElementById('delivery-note-number');
    let noteNumberIcon = document.getElementById('del-note-number-icon');
    
    let delNoteNo = inputField.value.trim();
    console.log("Checking DelNoteNo", delNoteNo);

    if (delNoteNo === '') {
        noteNumberIcon.src = "/static/image/neutral.png"; // Reset icon
        deliveryNoteStatus = null;
        return;
    }

    fetch('/check_delivery_note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ZZDelNoteNo: delNoteNo })
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            noteNumberIcon.src = "/static/image/check.png"; // Red cross
            deliveryNoteStatus = "Delivery Note already exists!";
            fetch_delivery_note_sales()
        } else {
            noteNumberIcon.src = "/static/image/incorrect.png"; // Green check
            deliveryNoteStatus = "Delivery Note is available!";
        }
    })
    .catch(error => console.error("Error:", error));
}

function check_invoice_number(){
    let inputField = document.getElementById('ZZInvoiceNo');
    let invoiceNumberIcon = document.getElementById('invoice-icon');
    
    let invoiceNo = inputField.value.trim();

    if (invoiceNo === '') {
        invoiceNumberIcon.src = "/static/image/neutral.png"; // Reset icon
        invoiceStatus = null;
        return;
    }

    fetch('/check_invoice_no', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invoiceNo: invoiceNo })
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            invoiceNumberIcon.src = "/static/image/incorrect.png"; 
            invoiceStatus = "Invoice already exists!";
        } else {
            invoiceNumberIcon.src = "/static/image/check.png";
            invoiceStatus = "This Invoice Number doesn't exist.";
        }
    })
    .catch(error => console.error("Error:", error));
}
    // Function to fetch the Delivery Note ID (asynchronous)
    async function fetchDeliveryNoteId(DelNoteNo) {
        console.log(DelNoteNo);  // Check the delivery note number passed in
        
        try {
            // Sending POST request to fetch the ID
            const response = await fetch("/get_delivery_note_id", {
                method: "POST",  // Changed to POST
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ delivery_note_header: DelNoteNo })  // Send the JSON body
            });
            const data = await response.json();
            
            console.log(data);
            if (data.id) {
                return data.id;  // Return the ID if found
            } else {
                throw new Error('Delivery Note ID not found');
            }
        } catch (error) {
            console.error("Error fetching Delivery Note ID:", error);
            alert("Error fetching Delivery Note ID.");
            throw error;  // Rethrow the error to handle it in fetchProducts
        }
    }