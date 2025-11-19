let ibtLines = [];

document.addEventListener("DOMContentLoaded", async () => {
    const whFrom = document.getElementById("wh-from");
    const whTo = document.getElementById("wh-to");
    const productSelect = document.getElementById("product-select");

    // Fetch and populate warehouses
    const res = await fetch("/inventory/SDK/fetch_warehouses");
    const data = await res.json();
    const warehouses = data.suppliers;

    // Initialize warehouse dropdowns with Select2
    warehouses.forEach(w => {
        whFrom.innerHTML += `<option value="${w.code}">${w.name}</option>`;
        whTo.innerHTML += `<option value="${w.code}">${w.name}</option>`;
    });

    // Make warehouse dropdowns searchable
    $('#wh-from').select2({
        placeholder: "Select warehouse",
        allowClear: false,
        width: '100%'
    });

    $('#wh-to').select2({
        placeholder: "Select warehouse", 
        allowClear: false,
        width: '100%'
    });

    // --- Step 1 → Step 2 ---
    document.getElementById("ibt-step-1-next").addEventListener("click", async () => {
        const fromWh = $('#wh-from').val();
        const toWh = $('#wh-to').val();
        const requestedBy = document.getElementById("requested-by").value.trim();
        const dispatcher = document.getElementById("dispatcher").value.trim();
        const driver = document.getElementById("driver").value.trim();

        if (!fromWh || !toWh || !requestedBy || !dispatcher || !driver) {
            return Swal.fire("Missing Info", "Please fill in all fields", "warning");
        }

        // Reset product lines when moving to step 2
        ibtLines = [];

        // Fetch products
        const res = await fetch("/inventory/fetch_products_in_both_whses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ whse_from_code: fromWh, whse_to_code: toWh })
        });
        const data = await res.json();
        const products = data.products;
        console.log("Products fetched:", products);
        
        // Clear previous options and add placeholder
        productSelect.innerHTML = '<option></option>';

        // Destroy previous Select2 instance if exists
        if ($.fn.select2 && $('#product-select').hasClass('select2-hidden-accessible')) {
            $('#product-select').select2('destroy');
        }

        if (!products || products.length === 0) {
            document.getElementById("ibt-lines").innerHTML = "<p>No products found.</p>";
        } else {
            // Add product options
            products.forEach(p => {
                const option = new Option(`${p.product_id} — ${p.product_desc}`, p.product_id, false, false);
                $(option).data('qty', p.qty_in_whse);
                $(option).data('desc', p.product_desc);
                productSelect.appendChild(option);
            });

            // Initialize Select2 with proper formatting
            $('#product-select').select2({
                placeholder: "Select a product",
                allowClear: true,
                templateResult: formatProductOption,
                templateSelection: formatProductSelection,
                width: '100%',
                dropdownParent: document.getElementById('ibt-step-2')
            });
        }

        // Clear quantity input
        document.getElementById("qty-input").value = "";

        document.getElementById("ibt-step-1").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");
    });

    // --- Add Product Button ---
    document.getElementById("ibt-add-product").addEventListener("click", addProductToLines);

    // --- Step 2 → Step 3 ---
    document.getElementById("ibt-step-2-next").addEventListener("click", () => {
        // Add current product before moving to summary
        addProductToLines();
        
        // Only proceed if we have at least one product
        if (ibtLines.length === 0) {
            return Swal.fire("Missing Products", "Please add at least one product", "warning");
        }

        renderSummary();
        document.getElementById("ibt-step-2").classList.add("hidden");
        document.getElementById("ibt-step-3").classList.remove("hidden");
    });

    // --- Submit IBT ---
    document.getElementById("ibt-submit").addEventListener("click", async () => {
        const payload = {
            WarehouseFrom: $('#wh-from').val(),
            WarehouseTo: $('#wh-to').val(),
            RequestedBy: document.getElementById("requested-by").value.trim(),
            Dispatcher: document.getElementById("dispatcher").value.trim(),
            Driver: document.getElementById("driver").value.trim(),
            Lines: ibtLines.map(line => ({
                ProductId: line.productId,
                QtyIssued: line.qty
            }))
        };

        console.log("Submitting IBT:", payload);

        const res = await fetch("/inventory/submit_ibt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        if (result.success) {
            Swal.fire("Success", "IBT Submitted", "success");
            // Reset form
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            Swal.fire("Error", result.message, "error");
        }
    });

    // --- Select2 custom templates ---
    function formatProductOption(option) {
        if (!option.id) return option.text;
        const data = $(option.element).data();
        return $(`<div><strong>${option.text}</strong><br><small>Available: ${data.qty}</small></div>`);
    }

    function formatProductSelection(option) {
        if (!option.id) return option.text;
        // Fix alignment issue by returning just the text
        return option.text;
    }

    function addProductToLines() {
        const productId = $('#product-select').val();
        const selectedOption = $('#product-select').find(':selected');
        const qtyInput = Number(document.getElementById("qty-input").value);

        if (!productId || qtyInput <= 0) {
            return Swal.fire("Missing Info", "Select a product and enter a valid quantity", "warning");
        }

        const availableQty = Number(selectedOption.data('qty'));
        if (qtyInput > availableQty) {
            return Swal.fire("Exceeds Stock", `Available quantity: ${availableQty}`, "warning");
        }

        // Check if product already exists in lines
        const existingIndex = ibtLines.findIndex(line => line.productId === productId);
        if (existingIndex > -1) {
            // Update existing line
            ibtLines[existingIndex].qty += qtyInput;
            if (ibtLines[existingIndex].qty > availableQty) {
                ibtLines[existingIndex].qty = availableQty;
                Swal.fire("Quantity Adjusted", `Total quantity cannot exceed available stock of ${availableQty}`, "info");
            }
        } else {
            // Add new line
            ibtLines.push({
                productId: productId,
                productText: selectedOption.text(),
                qty: qtyInput,
                availableQty: availableQty
            });
        }

        // Clear selection and quantity
        $('#product-select').val(null).trigger('change');
        document.getElementById("qty-input").value = "";

        Swal.fire("Product Added", "Product added to IBT. Add more products or click 'Next' to review.", "success");
    }
});

function renderSummary() {
    const summaryDiv = document.getElementById("ibt-summary");
    summaryDiv.innerHTML = "";

    // Step 1 info in grid layout
    const step1Info = {
        "Warehouse From": $('#wh-from').find(':selected').text(),
        "Warehouse To": $('#wh-to').find(':selected').text(),
        "Requested By": document.getElementById("requested-by").value.trim(),
        "Dispatcher": document.getElementById("dispatcher").value.trim(),
        "Driver": document.getElementById("driver").value.trim()
    };

    summaryDiv.innerHTML += `<h4 style="margin:10px 0; border-bottom:2px solid var(--button-bg); padding-bottom: 8px;">IBT Information</h4>`;
    
    const gridDiv = document.createElement("div");
    gridDiv.className = "summary-grid";
    
    Object.keys(step1Info).forEach(key => {
        const itemDiv = document.createElement("div");
        itemDiv.className = "summary-item";
        itemDiv.innerHTML = `<strong>${key}</strong><span>${step1Info[key]}</span>`;
        gridDiv.appendChild(itemDiv);
    });
    
    summaryDiv.appendChild(gridDiv);

    // Products section
    summaryDiv.innerHTML += `<h4 style="margin:20px 0 10px 0; border-bottom:2px solid var(--button-bg); padding-bottom: 8px;">Products (${ibtLines.length})</h4>`;
    
    const productsContainer = document.createElement("div");
    productsContainer.id = "ibt-lines-container";
    summaryDiv.appendChild(productsContainer);

    renderIbtLines();
}

function renderIbtLines() {
    const container = document.getElementById("ibt-lines-container");
    if (!container) return;

    container.innerHTML = "";

    if (ibtLines.length === 0) {
        container.innerHTML = "<p>No products added.</p>";
        return;
    }

    ibtLines.forEach((line, index) => {
        const lineDiv = document.createElement("div");
        lineDiv.className = "product-line";

        lineDiv.innerHTML = `
            <div class="product-info">
                <strong>${line.productText}</strong>
                <small>Available: ${line.availableQty} | Product ID: ${line.productId}</small>
            </div>
            <div class="product-actions">
                <input type="number" 
                       class="qty-send" 
                       value="${line.qty}" 
                       min="1" 
                       max="${line.availableQty}" 
                       onchange="updateLineQty(${index}, this.value)">
                <button type="button" onclick="removeLine(${index})" class="btn-danger">
                    ×
                </button>
            </div>
        `;

        container.appendChild(lineDiv);
    });
}

function updateLineQty(index, newQty) {
    const qty = Number(newQty);
    if (qty > 0 && qty <= ibtLines[index].availableQty) {
        ibtLines[index].qty = qty;
    } else {
        // Revert to previous value if invalid
        renderIbtLines();
    }
}

function removeLine(index) {
    ibtLines.splice(index, 1);
    if (ibtLines.length === 0) {
        // If no products left, go back to step 2
        document.getElementById("ibt-step-3").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");
    } else {
        renderIbtLines();
        // Update the products count in the header
        document.querySelector("#ibt-summary h4:nth-child(3)").textContent = `Products (${ibtLines.length})`;
    }
}