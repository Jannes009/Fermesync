let ibtLines = [];
let lineIndex = 0;  
let products = [];

document.addEventListener("DOMContentLoaded", async () => {
    const whFrom = document.getElementById("wh-from");
    const whTo = document.getElementById("wh-to");

    // Fetch and populate warehouses
    const res = await fetch("/inventory/SDK/fetch_warehouses");
    const data = await res.json();
    const warehouses = data.suppliers;
    whFrom.innerHTML = '<option disabled selected>Select warehouse</option>';
    whTo.innerHTML = '<option disabled selected>Select warehouse</option>';

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
        const fromWh = document.getElementById("wh-from").value;
        const toWh = document.getElementById("wh-to").value;

        const requestedBy = document.getElementById("requested-by").value.trim();
        const dispatcher = document.getElementById("dispatcher").value.trim();
        const driver = document.getElementById("driver").value.trim();

        if (!fromWh || !toWh || !requestedBy || !dispatcher || !driver) {
            return Swal.fire("Missing Info", "Please fill in all fields", "warning");
        }

        const res = await fetch("/inventory/fetch_products_in_both_whses", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ whse_from_code: fromWh, whse_to_code: toWh })
        });

        const data = await res.json();
        products = data.products || [];

        if (products.length === 0) {
            document.getElementById("ibt-lines-container").innerHTML =
                "<p>No products found for both warehouses.</p>";
            return;
        }

        // Switch to Step 2
        document.getElementById("ibt-step-1").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");

        // Add the initial line
        addIbtLine();
    });

    // --- Add Product Button ---
    document.getElementById("add-line-btn").addEventListener("click", addIbtLine);

    //--------------------------------------------------
    // Next Button → Validate & Collect All Lines
    //--------------------------------------------------
    document.getElementById("step-2-next-btn").addEventListener("click", () => {
        const lines = document.querySelectorAll(".ibt-line");
        ibtLines.length = 0;

        for (let line of lines) {
            const select = line.querySelector(".product-select");
            const qtyInput = line.querySelector(".qty-input");

            const productId = select.value;
            const qtyToSend = Number(qtyInput.value);

            if (!productId) {
                return Swal.fire("Missing Product", "Each line must have a product selected.", "warning");
            }

            if (qtyToSend <= 0) {
                return Swal.fire("Invalid Quantity", "Quantity must be greater than 0.", "warning");
            }

            const productData = $(select).find(":selected").data();
            const availableQty = Number(productData.qty);

            if (qtyToSend > availableQty) {
                return Swal.fire(
                    "Not Enough Stock",
                    `Product: ${select.options[select.selectedIndex].text}\nAvailable: ${availableQty}`,
                    "error"
                );
            }

            ibtLines.push({
                product_id: productId,
                qty: qtyToSend,
                productText: select.options[select.selectedIndex].text,
                availableQty: availableQty
            });
        }

        console.log("✔ Valid lines:", ibtLines);

        renderSummaryUltraCompact();
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
                ProductId: line.product_id,
                QtyIssued: line.qty
            }))
        };

        const res = await fetch("/inventory/submit_ibt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (!data.success) {
            Swal.fire({
                icon: "error",
                title: "Error creating IBT",
                text: data.message
            });
            return;
        }

        Swal.fire({
            icon: "success",
            title: "IBT Created",
            text: "IBT Number: " + data.ibtNumber
        }).then(() => { 
            document.getElementById("ibt-step-3").classList.add("hidden");
            // Show step 1
            document.getElementById("ibt-step-1").classList.remove("hidden");

            // Reset form fields
            document.getElementById("wh-from").value = "";
            document.getElementById("wh-to").value = "";
            document.getElementById("requested-by").value = "";
            document.getElementById("dispatcher").value = "";
            document.getElementById("driver").value = "";
            $('#wh-from, #wh-to').trigger('change'); // refresh Select2
            document.getElementById("ibt-lines-container").innerHTML = "";
            ibtLines = [];
            lineIndex = 0;;
        });
    });

    // --- Back Button from Step 2 to Step 1 ---
    document.getElementById("step-2-back-btn").addEventListener("click", () => {
        document.getElementById("ibt-step-2").classList.add("hidden");
        document.getElementById("ibt-step-1").classList.remove("hidden");
    });

    // --- Back Button from Step 3 to Step 2 ---
    document.getElementById("step-3-back-btn").addEventListener("click", () => {
        document.getElementById("ibt-step-3").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");
    });
});

function addIbtLine() {
    lineIndex++;

    const lineId = `ibt-line-${lineIndex}`;
    const selectId = `product-select-${lineIndex}`;

    const lineDiv = document.createElement("div");
    lineDiv.className = "ibt-line";
    lineDiv.id = lineId;

    lineDiv.innerHTML = `
        <div class="ibt-line-row">
            <!-- Product select -->
            <select id="${selectId}" class="product-select">
                <option></option>
            </select>

            <!-- Qty input -->
            <input type="number" class="qty-input" min="0" placeholder="Qty" />

            <!-- Stock unit -->
            <span class="stock-unit">Unit</span>
        </div>

        <!-- Remove button outside the row -->
        <button type="button" class="ibt-remove-btn btn-danger" title="Remove line">✕</button>
    `;

    document.getElementById("ibt-lines-container").appendChild(lineDiv);

    // ---------------------------------------------------
    // REMOVE LINE BUTTON
    // ---------------------------------------------------
    const removeBtn = lineDiv.querySelector('.ibt-remove-btn');
    removeBtn.addEventListener('click', () => {
        lineDiv.remove();
    });

    // ---------------------------------------------------
    // Populate dropdown
    // ---------------------------------------------------
    populateSelect(selectId, lineDiv);
}

function populateSelect(selectId, lineDiv) {
    const select = document.getElementById(selectId);

    products.forEach(p => {
        const opt = new Option(`${p.product_desc} (In: ${p.qty_in_whse})`, p.product_id, false, false);
        $(opt).data("unit", p.stocking_unit);
        $(opt).data("qty", p.qty_in_whse);

        // Disable the option if it is already in ibtLines
        if (ibtLines.some(line => line.product_id == p.product_id)) {
            opt.disabled = true;
            opt.text += " (Already added)";
        }

        select.appendChild(opt);
    });

    $(`#${selectId}`).select2({
        placeholder: "Select product",
        allowClear: true,
        width: "100%"
    });

    // When a product is chosen → update the stocking unit
    $(`#${selectId}`).on("select2:select", function (e) {
        const selected = $(this).find(":selected").data();
        lineDiv.querySelector(".stock-unit").textContent = selected.unit || "";

        // Disable the selected product in other dropdowns
        document.querySelectorAll(".product-select").forEach(otherSelect => {
            if (otherSelect.id !== selectId) {
                $(otherSelect).find(`option[value="${this.value}"]`).prop("disabled", true);
                $(otherSelect).trigger('change.select2'); // refresh select2
            }
        });
    });

    // When a product is cleared → re-enable in other dropdowns
    $(`#${selectId}`).on("select2:clear", function () {
        lineDiv.querySelector(".stock-unit").textContent = "";
        document.querySelectorAll(".product-select").forEach(otherSelect => {
            if (otherSelect.id !== selectId) {
                $(otherSelect).find("option").prop("disabled", false);
                // Re-disable options that are already selected in other lines
                $(".product-select").each(function() {
                    const val = $(this).val();
                    if (val) $(otherSelect).find(`option[value="${val}"]`).prop("disabled", true);
                });
                $(otherSelect).trigger('change.select2');
            }
        });
    });
}

function renderSummaryUltraCompact() {
    const summaryDiv = document.getElementById("ibt-summary");
    if (!summaryDiv) return;
    
    summaryDiv.innerHTML = "";

    // Create compact summary section
    const compactSection = document.createElement("div");
    compactSection.className = "compact-summary";
    
    const header = document.createElement("div");
    header.className = "compact-header";
    header.textContent = "Transfer Summary";
    compactSection.appendChild(header);
    
    // Ultra-compact 2-column layout
    const gridDiv = document.createElement("div");
    gridDiv.className = "compact-grid-inline";
    gridDiv.style.padding = "12px 15px";
    gridDiv.style.gap = "10px 20px";
    
    const summaryData = [
        { label: "From", value: $('#wh-from').find(':selected').text() },
        { label: "To", value: $('#wh-to').find(':selected').text() },
        { label: "Requested By", value: document.getElementById("requested-by").value.trim() },
        { label: "Dispatcher", value: document.getElementById("dispatcher").value.trim() },
        { label: "Driver", value: document.getElementById("driver").value.trim() }
    ];
    
    summaryData.forEach(item => {
        const itemDiv = document.createElement("div");
        itemDiv.className = "compact-item-inline";
        itemDiv.style.minHeight = "auto";
        itemDiv.innerHTML = `
            <strong style="min-width: 75px; font-size: 0.75rem;">${item.label}</strong>
            <span style="font-size: 0.85rem;">${item.value}</span>
        `;
        gridDiv.appendChild(itemDiv);
    });
    
    compactSection.appendChild(gridDiv);
    summaryDiv.appendChild(compactSection);

    renderCompactProducts(summaryDiv);
}

function renderCompactProducts(summaryDiv) {
    if (!summaryDiv) return;
    
    const productsSection = document.createElement("div");
    productsSection.className = "compact-products";
    
    const header = document.createElement("div");
    header.className = "compact-header";
    header.textContent = `Products (${ibtLines.length})`;
    productsSection.appendChild(header);
    
    if (ibtLines.length === 0) {
        const emptyMsg = document.createElement("div");
        emptyMsg.className = "compact-product-item";
        emptyMsg.textContent = "No products added";
        emptyMsg.style.textAlign = "center";
        emptyMsg.style.color = "var(--secondary-text)";
        productsSection.appendChild(emptyMsg);
    } else {
        ibtLines.forEach((line, index) => {
            const productItem = document.createElement("div");
            productItem.className = "compact-product-item";
            
            productItem.innerHTML = `
                <div class="product-details">
                    <div class="product-name">${line.productText}</div>
                    <div class="product-meta">Available: ${line.availableQty} | ID: ${line.productId}</div>
                </div>
                <div class="product-qty">
                    <span class="qty-badge">${line.qty} units</span>
                </div>
            `;
            
            productsSection.appendChild(productItem);
        });
    }
    
    summaryDiv.appendChild(productsSection);
}

function updateLineQty(index, newQty) {
    const qty = Number(newQty);
    if (qty > 0 && qty <= ibtLines[index].availableQty) {
        ibtLines[index].qty = qty;
        // Re-render summary to reflect changes
        renderSummaryUltraCompact();
    } else {
        // Revert to previous value if invalid
        renderSummaryUltraCompact();
    }
}

function removeLine(index) {
    ibtLines.splice(index, 1);
    if (ibtLines.length === 0) {
        // If no products left, go back to step 2
        document.getElementById("ibt-step-3").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");
    } else {
        // Re-render the summary with updated data
        renderSummaryUltraCompact();
    }
}