document.addEventListener("DOMContentLoaded", () => {


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
            // Allow the programmatic submission to proceed without triggering the handler
            return;
        }

        const totalQuantity = calculateTotalQuantity();
        const headerTotalQuantity = parseFloat($("#ZZTotalQty").val());

        if (totalQuantity !== headerTotalQuantity) {
            alert("Quantities don't match.");
            e.preventDefault(); // Prevent form submission if quantities don't match
        } else {
            e.preventDefault(); // Prevent default submission initially

            // Start the fetch to clear the saved data
            fetch("/api/clear-saved-form", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ clear: true })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error("Failed to clear saved form data.");
                }
                return response.json();
            })
            .then(data => {
                alert("Saved data cleared: " + data.message); // Display the success message
                // Set the flag and submit the form programmatically
                isProgrammaticSubmit = true;
                $("form")[0].submit(); // Programmatically submit the form
            })
            .catch(error => {
                console.error("Error:", error);
                alert("An error occurred. Please try again.");
            });
        }
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

let deliveryNoteStatus = null; // Global variable to store status

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
        console.log("Dropdown opened");
        setTimeout(() => {
            let searchField = document.querySelector('.select2-container--open .select2-search__field');
            if (searchField) {
                searchField.focus();
            }
        }, 10); // Short delay to ensure the field is available
    });


    // // Detect if the Tab key was pressed and store that information
    // $(document).on('keydown', '.searchable-dropdown', function (e) {
    //     console.log('Key pressed:', e.key);  // Log the key that was pressed
    //     if (e.key === 'Tab' || e.keyCode === 9) {
    //         lastKeyPressed = 'Tab'; // Store Tab key press
    //     }
    // });


    // Log the key (name) and selected value or Tab when the dropdown closes
    $('.searchable-dropdown').on('select2:close', function () {
        const fieldName = $(this).attr('name'); // Get the name of the dropdown
        const selectedValue = $(this).val();   // Get the selected value (or null if no selection)
        
        if (lastKeyPressed === 'Tab') {
            console.log(`Dropdown with name "${fieldName}" closed with TAB key.`);
        } else {
            console.log(`Dropdown with name "${fieldName}" closed with selected value: "${selectedValue}"`);
        }
        
        // Reset lastKeyPressed after handling
        lastKeyPressed = null;
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
            <td><input type="number" name="ZZEstimatedPrice[]" placeholder="Estimated Price" step="any" required></td>
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