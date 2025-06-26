let deliveryNoteStatus = null; // Global variable to store status
document.addEventListener("DOMContentLoaded", () => {
    let preventSave = false;

    function saveFormData() {
        const formData = {
            ZZDelNoteNo: document.querySelector('[name="ZZDelNoteNo"]').value || '',
            ZZDelDate: document.querySelector('[name="ZZDelDate"]').value || '',
            ZZTotalQty: document.querySelector('[name="ZZTotalQty"]').value || '',
            ZZAgentName: document.querySelector('[name="ZZAgentName"]').value || '',
            ZZMarket: document.querySelector('[name="ZZMarket"]').value || '',
            ZZProductionUnitCode: document.querySelector('[name="ZZProductionUnitCode"]').value || '',
            ZZTransporterCode: document.querySelector('[name="ZZTransporterCode"]').value || '',
            ZZTransporterCost: document.querySelector('[name="ZZTransporterCost"]').value || '',
            products: Array.from(document.querySelectorAll('.product-row')).map(row => ({
                ZZProduct: row.querySelector('[name="ZZProduct[]"]').value || '',
                ZZEstimatedPrice: row.querySelector('[name="ZZEstimatedPrice[]"]').value || '',
                ZZQuantityBags: row.querySelector('[name="ZZQuantityBags[]"]').value || '',
                ZZProductionUnitLine: row.querySelector('[name="ZZProductionUnitLine[]"]').value || ''
            }))
        };


        // Send data to the backend
        fetch('/api/save-form', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData),
        })
            .then(response => response.json())
            .then(data => console.log("Server Response:", data.message))
            .catch(error => console.error("Error saving form data:", error));
    }

    function loadSavedFormData() {
        // Fetch the saved form data from the backend
        fetch('/api/load-form')
            .then(response => {
                if (!response.ok) {
                    throw new Error("Failed to load saved form data");
                }
                return response.json();
            })
            .then(formData => {
                // Populate form fields with saved data
                populateFormFields(formData);
    
                const productTableBody = $("tbody.product-table");
                productTableBody.empty();
    
                if (formData.products && formData.products.length > 0) {
                    // Populate product rows if they exist
                    formData.products.forEach(product => {
                        console.log(product)
                        const newRow = createProductRow(product);
                        productTableBody.append(newRow);
                    });
                    initializeDropdowns();
                } else {
                    // Add one empty row if no products exist
                    addCleanLine()
                }
                check_delivery_note();
                calculateTotalQuantity()
            })
            .catch(error => {
                console.error("Error loading saved form data:", error)
                initializeDropdowns();
                check_delivery_note();
                calculateTotalQuantity();
            });
    }
    
    // Helper function to populate form fields
    function populateFormFields(formData) {
        Object.keys(formData).forEach(key => {
            const field = document.querySelector(`[name="${key}"]`);
            if (field) {
                const value = formData[key];
    
                // If the field is a searchable-dropdown and the value is empty, do not set it
                if (field.classList.contains('searchable-dropdown') && (!value || value.trim() === "")) {
                    return;
                }
    
                field.value = value; // Set the value
                
                // If it's a searchable-dropdown, trigger Select2 change
                if (field.classList.contains('searchable-dropdown')) {
                    $(field).trigger('change'); 
                }
            }
        });
    }
    
    
    function createProductRow(product) {
        const newRow = $(`
            <tr class="product-row">
                <td>
                    <select name="ZZProduct[]" class="searchable-dropdown product-select" required>
                        <option value="" disabled>Select a Product</option>
                    </select>
                </td>
                <td><input type="number" name="ZZEstimatedPrice[]" value="${product.ZZEstimatedPrice}" placeholder="Estimated Price" step="any" required></td>
                <td><input type="number" name="ZZQuantityBags[]" value="${product.ZZQuantityBags}" placeholder="Qty" step="any" required></td>
                <td>
                    <select name="ZZProductionUnitLine[]" class="searchable-dropdown production-unit-select" required>
                        <option value="" disabled>Select a Production Unit</option>
                    </select>
                </td>
                <td>
                    <button type="button" class="delete-row-btn">
                        <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                    </button>
                </td>
            </tr>
        `);
    
        // Populate product dropdown with selected product
        populateDropdownOptions(newRow.find("select.product-select"), product.ZZProduct, productOptions);
    
        // Populate production unit dropdown with selected production unit
        populateDropdownOptions(newRow.find("select.production-unit-select"), product.ZZProductionUnitLine, unitOptions);
    
        return newRow;
    }
    
    // Generic helper for dropdowns
    function populateDropdownOptions(dropdown, selectedValue, optionsArray) {
        dropdown.empty(); // Clear existing options
    
        // Add default placeholder
        dropdown.append('<option value="" disabled>Select an option</option>');
    
        // Add new options
        optionsArray.forEach(([value, text]) => {
            dropdown.append(new Option(text, value, false, value === selectedValue));
        });
    
        if (selectedValue) {
            dropdown.val(selectedValue);
        }
    }
    
    
    
    // Redirect to create stock form
    document.getElementById("openStockFormBtn").addEventListener("click", () => {
        saveFormData();
        window.location.href = "/create-product";
    });

    // When clearing form data, set the flag to prevent saving
    document.querySelector("form").addEventListener("submit", (e) => {
        preventSave = true; // Prevent save during and after clearing the form
    });

    // On page unload, save form data only if the URL contains 'create_entry' and saving is not explicitly prevented
    window.addEventListener('beforeunload', () => {
        if (window.location.href.includes('create_entry') && !preventSave) {
            saveFormData();
        }
    });


    // Handle back/forward navigation (if history management is in place)
    window.addEventListener('popstate', saveFormData);

    // Check if the current page is /create_entry
    if (window.location.pathname.includes("/create_entry")) {
        loadSavedFormData();
    }
    calculateTotalQuantity()
});

// document.addEventListener("DOMContentLoaded", function () {
//     const headers = document.querySelectorAll(".resizable");

//     headers.forEach((header) => {
//         const resizer = document.createElement("div");
//         resizer.classList.add("resizer");
//         header.appendChild(resizer);

//         resizer.addEventListener("mousedown", onMouseDown);

//         function onMouseDown(event) {
            
//             event.preventDefault();

//             const startX = event.clientX;
//             const startWidth = header.offsetWidth;

//             function onMouseMove(e) {
//                 const newWidth = startWidth + (e.clientX - startX);
                
//                 header.style.width = `${newWidth}px`;
//             }

//             function onMouseUp() {
//                 document.removeEventListener("mousemove", onMouseMove);
//                 document.removeEventListener("mouseup", onMouseUp);
//             }

//             document.addEventListener("mousemove", onMouseMove);
//             document.addEventListener("mouseup", onMouseUp);
//         }
//     });
// });