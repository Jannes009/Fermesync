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

document.addEventListener("DOMContentLoaded", () => {
    
    $(document).on('select2:select', '.searchable-dropdown', function (e) {
        // Only proceed if this specific dropdown has name="ZZProduct[]"
        if ($(this).attr('name') === 'ZZProduct[]') {
            const selectedValue = $(this).val();
            handleProductSelection(selectedValue, this);
        }
    });
    
    async function handleProductSelection(value, selectElement) {
        const market = document.querySelector("select[name='ZZMarket']").value;
        if (!market) {
            console.warn("Market not selected");
            return;
        }
    
        const stockLink = value;
        const whseLink = market;
    
        try {
            const response = await fetch("/get-last-sales-price", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    stockLink: stockLink,
                    whseLink: whseLink
                })
            });
    
            const data = await response.json();
    
            const row = selectElement.closest("tr");
            const priceInput = row.querySelector("input[name='ZZEstimatedPrice[]']");
    
            if (data.lastSalesPrice !== null && priceInput) {
                console.log("Fetched price:", data.lastSalesPrice);
                priceInput.value = data.lastSalesPrice;
            } else if (priceInput) {
                console.warn("No price found for this product & market.");
                priceInput.value = 0;
            }
    
        } catch (err) {
            console.error("Error fetching price:", err);
        }
    }
    
    
    
    const addLineBtn = document.getElementById("add-line-btn");
    const productTable = $(".product-table");
    const openStockFormBtn = document.getElementById("openStockFormBtn");

    openStockFormBtn.addEventListener("click", () => {
        window.location.href = "/create-product";
    });


    // Handle quantity input changes
    productTable.on("input", "input[name='ZZQuantityBags[]']", calculateTotalQuantity);

    let isProgrammaticSubmit = false; // Flag to indicate if the submission is programmatic

    $("form").on("submit", function (e) {
        console.log("Submit clicked");
    
        if (isProgrammaticSubmit) {
            return; // Allow programmatic submission without checking
        }
    
        e.preventDefault(); // Always prevent default initially

        // Step 5: Continue with total quantity validation
        const totalQuantity = calculateTotalQuantity();
        const headerTotalQuantity = parseFloat($("#ZZTotalQty").val());
    
        if (totalQuantity !== headerTotalQuantity) {
            Swal.fire("Quantities don't match!", "", "error");
            return;
        }
    
        // Step 1: Detect duplicate products
        const productRows = $(".product-row");
        const productMap = new Map();
    
        productRows.each(function () {
            const productSelect = $(this).find(".product-select");
            const productID = productSelect.val();
            const productText = productSelect.find("option:selected").text();
            const quantityInput = $(this).find("input[name='ZZQuantityBags[]']");
            const quantity = parseFloat(quantityInput.val()) || 0;
    
            if (productID) {
                if (productMap.has(productID)) {
                    productMap.get(productID).quantity += quantity;
                    productMap.get(productID).rows.push($(this));
                } else {
                    productMap.set(productID, { name: productText, quantity, rows: [$(this)] });
                }
            }
        });
    
        // Step 2: Find duplicates and prepare a message
        let duplicatesFound = false;
        let mergeMessage = "<b>The following products will be merged:</b><br><br>";
    
        productMap.forEach((productData) => {
            if (productData.rows.length > 1) {
                duplicatesFound = true;
                mergeMessage += `✅ <b>${productData.name}</b>: <i>${productData.quantity} bags</i><br>`;
            }
        });
    
        if (duplicatesFound) {
            Swal.fire({
                title: "Duplicate Products Found",
                html: mergeMessage,
                icon: "warning",
                showCancelButton: true,
                confirmButtonText: "Yes, Merge",
                cancelButtonText: "No, Cancel"
            }).then((result) => {
                if (result.isConfirmed) {
                    // Step 3: Merge duplicate quantities
                    productMap.forEach((productData) => {
                        if (productData.rows.length > 1) {
                            let totalQuantity = productData.quantity;
                            let firstRow = productData.rows[0];
                            let quantityInput = firstRow.find("input[name='ZZQuantityBags[]']");
                            quantityInput.val(totalQuantity); // Update quantity in first row
    
                            // Remove all other duplicate rows
                            for (let i = 1; i < productData.rows.length; i++) {
                                productData.rows[i].remove();
                            }
                        }
                    });
    
                    // Step 4: Show success message and proceed with form submission
                    Swal.fire({
                        title: "Merged Successfully",
                        text: "Duplicate products have been merged.",
                        timer: 1,
                        icon: "success"
                    }).then(() => {
                        $("form").trigger("submit"); // Resubmit form after merging
                    });
                }
            });
    
            return; // Stop further execution until user decides
        }
    
        // Step 6: Proceed with API call to clear saved data before final submission
        fetch("/api/clear-saved-form", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clear: true })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error("Failed to clear saved form data.");
            }
            return response.json();
        })
        .then(data => {
            Toast.fire({
                title: "Entry submitted",
                icon: "success",
            });
            
            isProgrammaticSubmit = true;
            $("form")[0].submit(); // Programmatically submit the form
            
        })
        .catch(error => {
            console.error("Error:", error);
            Swal.fire("An error occurred", "Please try again.", "error");
        });
    });    

    // Add new row
    $("#add-line-btn").on("click", function () {
        addCleanLine()
    });

    // Delete row handler
    productTable.on("click", ".delete-row-btn", async function () {
        const rowToDelete = $(this).closest("tr");
        const id = rowToDelete.data("id");

        if (!id) {
            rowToDelete.remove();
            calculateTotalQuantity();
            return;
        }

        if (!confirm("Are you sure you want to delete this row?")) return;

        try {
            const response = await fetch('/delete-row', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id }),
            });

            if (!response.ok) {
                alert("An error occurred while trying to delete the row.");
                return;
            }

            rowToDelete.remove();
            calculateTotalQuantity();
            alert("Row deleted successfully!");
        } catch (error) {
            alert("An error occurred while trying to delete the row.");
        }
    });

    initializeDropdowns();
});

function check_delivery_note(){
    let inputField = document.getElementById('ZZDelNoteNo');
    let verifyIcon = document.getElementById('verify-icon');
    
    let delNoteNo = inputField.value.trim();
    console.log("Checking DelNoteNo", delNoteNo);

    if (delNoteNo === '') {
        verifyIcon.src = "/static/image/neutral.png"; // Reset icon
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
            verifyIcon.src = "/static/image/incorrect.png"; // Red cross
            deliveryNoteStatus = "Delivery Note already exists!";
        } else {
            verifyIcon.src = "/static/image/check.png"; // Green check
            deliveryNoteStatus = "Delivery Note is available!";
        }
    })
    .catch(error => console.error("Error:", error));
}

document.addEventListener("DOMContentLoaded", function () {
    let inputField = document.getElementById('ZZDelNoteNo');
    let verifyIcon = document.getElementById('verify-icon');

    inputField.addEventListener('input', function () {
        check_delivery_note();
    });

    verifyIcon.addEventListener('click', function () {
        if (deliveryNoteStatus) {
            alert(deliveryNoteStatus);
        } else {
            alert("Enter a Delivery Note Number first.");
        }
    });
});



// Custom matcher function (define this once)
function customMatcher(params, data) {
    if ($.trim(params.term) === '') {
        return data;
    }

    let searchTerms = params.term.toLowerCase().split(/\s+|-/); // Split by space or dash
    let optionText = data.text.toLowerCase();
    let optionWords = optionText.split(/\s+|-/); // Normalize the option text

    let matches = searchTerms.every(term =>
        optionWords.some(word => word.includes(term))
    );

    return matches ? data : null;
}

// Function to initialize Select2 on all searchable dropdowns
function initializeDropdowns() {
    let lastKeyPressed = null; // Variable to store the last key pressed (for detecting Tab)
    $('.searchable-dropdown').select2({
        width: '100%',
        matcher: customMatcher, // Use the reusable function
    });

    // Ensure search box is focused when dropdown opens
    $('.searchable-dropdown').on('select2:open', function () {
        setTimeout(() => {
            let searchField = document.querySelector('.select2-container--open .select2-search__field');
            if (searchField) {
                searchField.focus();
            }
        }, 10); // Short delay to ensure the field is available
    });
}


function addCleanLine() {
    const productTableBody = $(".product-table");
    const newRow = $(`
        <tr class='product-row'>
            <td>
                <select name="ZZProduct[]" class="searchable-dropdown product-select" required>
                    <option value="" disabled selected>Select a Product</option>
                </select>
            </td>
            <td><input type="number" name="ZZEstimatedPrice[]" placeholder="Estimated Price" step="any" value="0" required></td>
            <td><input type="number" name="ZZQuantityBags[]" placeholder="Enter quantity" step="any" required></td>
            <td><input type="text" name="ZZComments[]" placeholder="Enter comments"></td>
            <td><button type="button" class="delete-row-btn"><img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon"></button></td>
        </tr>
    `);

    const dropdown = newRow.find("select.searchable-dropdown");
    productOptions.forEach(([value, text]) => {
        dropdown.append(new Option(text, value));
    });

    productTableBody.append(newRow);
    initializeDropdowns();
    calculateTotalQuantity();

    return newRow;  // Return reference to the new row
}

// Calculate total quantity
function calculateTotalQuantity() {
    let totalQuantity = 0;
    const totalQuantityDisplay = $("#total-quantity");
    $(".product-row").each(function () {
        const quantity = $(this).find("input[name='ZZQuantityBags[]']").val();
        totalQuantity += parseFloat(quantity) || 0;
    });
    totalQuantityDisplay.text(`Total Quantity: ${totalQuantity.toFixed(0)}`);
    return totalQuantity;
}

