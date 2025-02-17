
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
            ZZPalletsOut: document.querySelector('[name="ZZPalletsOut"]').value || '',
            ZZPalletsBack: document.querySelector('[name="ZZPalletsBack"]').value || '',
            products: Array.from(document.querySelectorAll('.product-row')).map(row => ({
                ZZProduct: row.querySelector('[name="ZZProduct[]"]').value || '',
                ZZEstimatedPrice: row.querySelector('[name="ZZEstimatedPrice[]"]').value || '',
                ZZQuantityBags: row.querySelector('[name="ZZQuantityBags[]"]').value || '',
                ZZComments: row.querySelector('[name="ZZComments[]"]').value || ''
            }))
        };
        console.log(formData)

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
    
    
    // Helper function to create a product row with product data
    function createProductRow(product) {
        const newRow = $(`
            <tr class="product-row">
                <td>
                    <select name="ZZProduct[]" class="searchable-dropdown product-select" required>
                        <option value="" disabled>Select a Product</option>
                    </select>
                </td>
                <td><input type="number" name="ZZEstimatedPrice[]" value="${product.ZZEstimatedPrice}" placeholder="Estimated Price" step="any" required></td>
                <td><input type="number" name="ZZQuantityBags[]" value="${product.ZZQuantityBags}" placeholder="Enter quantity" step="any" required></td>
                <td><input type="text" name="ZZComments[]" value="${product.ZZComments}" placeholder="Enter comments"></td>
                <td>
                    <button type="button" class="delete-row-btn">
                        <img src="/static/Image/recycle-bin.png" alt="Delete" class="bin-icon">
                    </button>
                </td>
            </tr>
        `);
    
        populateDropdownOptions(newRow.find("select.searchable-dropdown"), product.ZZProduct);
        return newRow;
    }
    
    function populateDropdownOptions(dropdown, selectedValue) {
        // Clear existing options
        dropdown.empty();
    
        // Add placeholder option first
        dropdown.append('<option value="" disabled selected>Select a Product</option>');
    
        // Append product options
        productOptions.forEach(([value, text]) => {
            dropdown.append(new Option(text, value, false, value === selectedValue && selectedValue !== ""));
        });
    
        // If selectedValue is not empty, set it
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

    // Function to check session status
    async function checkSession() {
        try {
            const response = await fetch('/check_session');
            const data = await response.json();

            if (!data.session_active) {
                // Redirect to login page if session expired
                saveFormData(); // Save form data before redirecting
                window.location.href = '/'; // Replace '/login' with your desired redirect URL
            }
        } catch (error) {
            console.error('Error checking session:', error);
        }
    }

    // Poll the session status every 60 seconds
    setInterval(checkSession, 60000);
    calculateTotalQuantity()
});

