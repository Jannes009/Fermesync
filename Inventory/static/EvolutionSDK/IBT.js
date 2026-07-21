let ibtLines = [];
let lineIndex = 0;  
let products = [];
let selectedProducts = new Set();
let currentUnitMode = "purchasing";

// Promise that resolves when warehouse selects are populated
window.__ibtWarehousesLoaded = new Promise((res) => { window.__resolveIbtWarehouses = res; });


document.addEventListener("DOMContentLoaded", async () => {
    const whFrom = document.getElementById("wh-from");
    const whTo = document.getElementById("wh-to");

    // Fetch and populate warehouses
    const res = await fetch("/inventory/fetch_warehouses");
    const data = await res.json();
    const warehouses = data.warehouses;
    whFrom.innerHTML = '<option disabled selected>Select warehouse</option>';

    // Initialize warehouse dropdowns with Select2
    warehouses.forEach(w => {
        whFrom.innerHTML += `<option value="${w.id}">${w.name}</option>`;
    });

    // Make warehouse dropdowns searchable
    $('#wh-from').select2({
        placeholder: "Select warehouse",
        allowClear: false,
        width: '100%'
    });

    const res2 = await fetch("/inventory/SDK/fetch_all_warehouses");
    const data2 = await res2.json();
    const warehouses2 = data2.warehouses;
    whTo.innerHTML = '<option disabled selected>Select warehouse</option>';

    // Initialize warehouse dropdowns with Select2
    warehouses2.forEach(w => {
        whTo.innerHTML += `<option value="${w.id}">${w.name}</option>`;
    });

    $('#wh-to').select2({
        placeholder: "Select warehouse", 
        allowClear: false,
        width: '100%'
    });

        // mark warehouse population complete so prefill logic can proceed
        if (typeof window.__resolveIbtWarehouses === 'function') {
            try { window.__resolveIbtWarehouses(); } catch (e) { /* ignore */ }
        }

    // --- Step 1 → Step 2 ---
    document.getElementById("ibt-step-1-next").addEventListener("click", async () => {
        const fromWh = document.getElementById("wh-from").value;
        const toWh = document.getElementById("wh-to").value;

        if (!fromWh || !toWh) {
            return Swal.fire("Missing Info", "Please select both warehouses", "warning");
        }

        if (fromWh === toWh) {
            return Swal.fire("Invalid Selection", "Source and destination warehouses must be different", "warning");
        }

        // Show loading indicator
        Swal.fire({
            title: "Loading products...",
            didOpen: () => {
                Swal.showLoading();
            },
            allowOutsideClick: false,
            allowEscapeKey: false
        });

        try {
            const res = await fetch("/inventory/fetch_products_in_both_whses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ whse_from_id: fromWh, whse_to_id: toWh })
            });

            if (!res.ok) {
                throw new Error(`Server error: ${res.status}`);
            }

            const data = await res.json();

            if (data.error) {
                Swal.close();
                return Swal.fire({
                    icon: "error",
                    title: "Error Loading Products",
                    text: data.error
                });
            }

            products = data.products || [];

            // No products found
            if (products.length === 0) {
                Swal.close();
                return Swal.fire({
                    icon: "info",
                    title: "No Products Available",
                    html: `
                        <p>No products were found that exist in both:</p>
                        <div style="margin: 15px 0; padding: 10px; background: #f8f9fa; border-radius: 6px;">
                            <strong>From:</strong> ${document.querySelector('#wh-from option:checked').text}<br>
                            <strong>To:</strong> ${document.querySelector('#wh-to option:checked').text}
                        </div>
                        <p style="font-size: 0.9rem; color: #666;">
                            Please select different warehouses or check your inventory.
                        </p>
                    `,
                    confirmButtonText: "Try Again"
                });
            }

            // Successfully loaded products
            Swal.close();

            // Switch to Step 2
            document.getElementById("ibt-step-1").classList.add("hidden");
            document.getElementById("ibt-step-2").classList.remove("hidden");

            // Add the initial line
            addIbtLine();

            // Show success toast
            const toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 2000,
                timerProgressBar: true
            });

            toast.fire({
                icon: 'success',
                title: `Loaded ${products.length} product(s)`
            });

        } catch (error) {
            console.error("Error fetching products:", error);
            Swal.close();
            Swal.fire({
                icon: "error",
                title: "Failed to Load Products",
                text: error.message || "An unexpected error occurred. Please try again.",
                confirmButtonText: "Close"
            });
        }
    });

    document.querySelectorAll(".unit-mode-btn[data-global-unit-mode]").forEach((btn) => {
        btn.addEventListener("click", () => setGlobalUnitMode(btn.dataset.globalUnitMode));
    });

    // --- Add Product Button ---
    document.getElementById("add-line-btn").addEventListener("click", addIbtLine);

    //--------------------------------------------------
    // Next Button → Validate & Collect All Lines
    //--------------------------------------------------
    document.getElementById("step-2-next-btn").addEventListener("click", async () => {
        const lines = document.querySelectorAll(".ibt-line");
        ibtLines.length = 0;

        for (let line of lines) {
            const select = line.querySelector(".product-select");
            const qtyInput = line.querySelector(".qty-input");
            const uomLabel = line.querySelector(".stock-unit");

            const productId = select.value;
            const qtyToSend = Math.round(Number(qtyInput.value) * 100) / 100;

            if (!productId) {
                return Swal.fire("Missing Product", "Each line must have a product selected.", "warning");
            }

            if (qtyToSend <= 0) {
                return Swal.fire("Invalid Quantity", "Quantity must be greater than 0.", "warning");
            }

            const productData = $(select).find(":selected").data();
            const availableQty = Math.round(Number(productData.qty) * 100) / 100;
            const uom_code = productData.purchasing_unit_code || "";
            const uom_id = productData.purchasing_unit_id || null;
            const stocking_uom_code = productData.stocking_unit_code || "";
            const stocking_uom_id = productData.stocking_unit_id || null;
            const conversion_factor = Number(productData.conversion_factor) || 1;
            const enteredQty = Math.round(Number(qtyInput.value) * 100) / 100;
            const selectedUnitMode = currentUnitMode;
            const availableQtyForMode = selectedUnitMode === "purchasing"
                ? availableQty
                : Math.round((availableQty * conversion_factor) * 100) / 100;
            const requestedQtyForMode = enteredQty;
            const stockQty = selectedUnitMode === "stocking"
                ? Math.round(enteredQty * 100) / 100
                : Math.round(enteredQty * conversion_factor * 100) / 100;

            if (requestedQtyForMode > availableQtyForMode) {
                const qtyNeeded = Math.round((requestedQtyForMode - availableQtyForMode) * 100) / 100;
                const adjusted = await promptStockAdjustment(productId, document.getElementById('wh-from')?.value || null, qtyNeeded);
                if (!adjusted) {
                    return;
                }

                const wh = document.getElementById('wh-from')?.value;
                if (productId && wh) {
                    const refreshRes = await fetch(`/inventory/adjust_stock/qty?stock_link=${encodeURIComponent(productId)}&warehouse_link=${encodeURIComponent(wh)}`);
                    const refreshJson = await refreshRes.json();
                    if (refreshJson.status === 'ok') {
                        const newAvailableQty = Math.round(Number(refreshJson.qty_on_hand) * 100) / 100;
                        const refreshedAvailableQtyForMode = selectedUnitMode === "purchasing"
                            ? newAvailableQty
                            : Math.round((newAvailableQty * conversion_factor) * 100) / 100;
                        const opt = $(select).find(`option[value="${productId}"]`);
                        $(opt).data('qty', newAvailableQty);
                        refreshProductOptionLabels();
                        if (refreshedAvailableQtyForMode < requestedQtyForMode) {
                            return Swal.fire(
                                "Not Enough Stock",
                                `Product: ${select.options[select.selectedIndex].text}\nAvailable: ${refreshedAvailableQtyForMode} ${selectedUnitMode === 'purchasing' ? uom_code : stocking_uom_code}\nRequested: ${requestedQtyForMode} ${selectedUnitMode === 'purchasing' ? uom_code : stocking_uom_code}`,
                                "error"
                            );
                        }
                    }
                }
            }

            ibtLines.push({
                product_id: productId,
                qty: enteredQty,
                productText: select.options[select.selectedIndex].text,
                availableQty: availableQty,
                uom_code: uom_code,
                uom_id: uom_id,
                stocking_uom_code: stocking_uom_code,
                stocking_uom_id: stocking_uom_id,
                conversion_factor: conversion_factor,
                stock_qty: stockQty,
                selected_unit_mode: selectedUnitMode,
                display_unit_code: selectedUnitMode === "purchasing" ? uom_code : stocking_uom_code
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
            Lines: ibtLines.map(line => ({
                ProductId: line.product_id,
                QtyIssued: line.stock_qty,
                UoMId: line.stocking_uom_id
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
            $('#wh-from, #wh-to').trigger('change'); // refresh Select2
            document.getElementById("ibt-lines-container").innerHTML = "";
            ibtLines = [];
            selectedProducts = new Set();
            lineIndex = 0;
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

// Helper: read query param
function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

// If a prefill payload is present in the URL, decode it and prefill step 2 (but do NOT auto-submit)
document.addEventListener('DOMContentLoaded', async () => {
    // Support both URL prefill (legacy) and sessionStorage (preferred for large payloads)
    const prefillRawUrl = getQueryParam('prefill');
    const returnTo = getQueryParam('return_to');
    const prefillRawSession = (!prefillRawUrl && returnTo) ? sessionStorage.getItem('ibt_prefill') : null;
    const prefillRaw = prefillRawUrl || prefillRawSession;
    if (!prefillRaw) {
        if (!prefillRawUrl && !returnTo) {
            sessionStorage.removeItem('ibt_prefill');
        }
        return;
    }

    try {
        const prefill = JSON.parse(decodeURIComponent(prefillRawUrl || prefillRawSession));
        if (prefillRawSession) {
            sessionStorage.removeItem('ibt_prefill');
        }

        // prefills expected: { from_whse, to_whse, lines: [{ stock_link, qty }...] }
        // Wait for warehouse selects to be populated (so Select2 has options)
        if (window.__ibtWarehousesLoaded) {
            try { await window.__ibtWarehousesLoaded; } catch (e) { /* ignore */ }
        }

        if (prefill.from_whse) {
            $('#wh-from').val(String(prefill.from_whse)).trigger('change');
        }
        if (prefill.to_whse) {
            $('#wh-to').val(String(prefill.to_whse)).trigger('change');
        }
        console.log("Prefilling IBT with:", prefill);

        // Fetch products for the selected warehouses (same as clicking Step 1 next)
        const fetchRes = await fetch('/inventory/fetch_products_in_both_whses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ whse_from_id: String(prefill.from_whse), whse_to_id: String(prefill.to_whse) })
        });
        const json = await fetchRes.json();
        products = json.products || [];

        // Clear any existing lines and selectedProducts
        document.getElementById('ibt-lines-container').innerHTML = '';
        selectedProducts = new Set();
        ibtLines = [];

        // Add a line for each prefill line
        for (const ln of (prefill.lines || [])) {
            addIbtLine();
            const thisIndex = lineIndex;
            const selectId = `product-select-${thisIndex}`;
            // wait a tick for select2 initialization
            await new Promise(r => setTimeout(r, 20));
            const selectVal = String(ln.product_id || ln.stock_link || ln.stockLink || ln.stock_link);
            try {
                $(`#${selectId}`).val(selectVal).trigger('change');
            } catch (e) {
                // ignore
            }
            const thisLineDiv = document.getElementById(`ibt-line-${thisIndex}`);
            if (thisLineDiv) {
                // Manually update UOM labels since select2:select event may not fire during prefill
                const selected = $(`#${selectId}`).find(':selected').data();
                const uomCode = selected.purchasing_unit_code || '';
                const stockUnitCode = selected.stocking_unit_code || '';
                thisLineDiv.querySelector('.stock-unit').textContent = uomCode;
                thisLineDiv.querySelector('.stock-unit-code').textContent = stockUnitCode;

                const qtyInput = thisLineDiv.querySelector('.qty-input');
                if (qtyInput) {
                    qtyInput.value = String(ln.qty || ln.Qty || ln.units_suggested || 0);
                    updateStockQtyDisplay(thisLineDiv);
                }
            }
        }

        // Move UI to step 2 and wait for user interaction
        document.getElementById('ibt-step-1').classList.add('hidden');
        document.getElementById('ibt-step-2').classList.remove('hidden');

    } catch (err) {
        console.error('Failed to prefill IBT:', err);
    }
});

function roundTo2(value) {
    return Math.round(Number(value) * 100) / 100;
}

function convertQtyBetweenUnits(qty, conversionFactor, fromMode, toMode) {
    const value = Number(qty) || 0;
    if (fromMode === toMode) {
        return roundTo2(value);
    }
    if (fromMode === "purchasing" && toMode === "stocking") {
        return roundTo2(value * conversionFactor);
    }
    if (fromMode === "stocking" && toMode === "purchasing") {
        return roundTo2(value / conversionFactor);
    }
    return roundTo2(value);
}

function syncSelectOptionsState() {
    document.querySelectorAll(".product-select").forEach((select) => {
        const currentValue = $(select).val();
        $(select).find("option").each(function () {
            const optionValue = $(this).val();
            if (!optionValue) {
                $(this).prop("disabled", false);
                return;
            }
            const isSelectedElsewhere = selectedProducts.has(String(optionValue)) && String(optionValue) !== String(currentValue);
            $(this).prop("disabled", isSelectedElsewhere);
        });
        $(select).trigger("change.select2");
    });
}

function refreshProductOptionLabels() {
    document.querySelectorAll(".product-select").forEach((select) => {
        $(select).find("option").each(function () {
            const option = $(this);
            if (!option.val()) {
                return;
            }
            const productDesc = option.data("product_desc") || option.text().split(" (In:")[0] || "";
            const qty = Number(option.data("qty")) || 0;
            const conversionFactor = Number(option.data("conversion_factor")) || 1;
            const displayQty = currentUnitMode === "purchasing"
                ? roundTo2(qty)
                : roundTo2(qty * conversionFactor);
            const unitCode = currentUnitMode === "purchasing"
                ? option.data("purchasing_unit_code") || ""
                : option.data("stocking_unit_code") || "";
            option.text(`${productDesc} (In: ${displayQty.toFixed(2)} ${unitCode})`);
        });

        const selectedOption = $(select).find("option:selected");
        if (selectedOption.length) {
            const productDesc = selectedOption.data("product_desc") || selectedOption.text().split(" (In:")[0] || "";
            const qty = Number(selectedOption.data("qty")) || 0;
            const conversionFactor = Number(selectedOption.data("conversion_factor")) || 1;
            const displayQty = currentUnitMode === "purchasing"
                ? roundTo2(qty)
                : roundTo2(qty * conversionFactor);
            const unitCode = currentUnitMode === "purchasing"
                ? selectedOption.data("purchasing_unit_code") || ""
                : selectedOption.data("stocking_unit_code") || "";
            const displayText = `${productDesc} (In: ${displayQty.toFixed(2)} ${unitCode})`;
            $(select).next('.select2-container').find('.select2-selection__rendered').text(displayText);
        }

        $(select).trigger("change.select2");
        $(select).trigger("change");
    });
}

function setGlobalUnitMode(newMode) {
    if (currentUnitMode === newMode) {
        return;
    }

    currentUnitMode = newMode;
    document.querySelectorAll(".unit-mode-btn[data-global-unit-mode]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.globalUnitMode === newMode);
    });

    document.querySelectorAll(".ibt-line").forEach((lineDiv) => {
        const qtyInput = lineDiv.querySelector(".qty-input");
        const currentQty = Number(qtyInput?.value) || 0;
        const currentMode = lineDiv.dataset.unitMode || "purchasing";
        const conversionFactor = Number(lineDiv.dataset.conversionFactor || 1);
        if (currentMode !== newMode) {
            qtyInput.value = convertQtyBetweenUnits(currentQty, conversionFactor, currentMode, newMode);
        }
        lineDiv.dataset.unitMode = newMode;
        updateStockQtyDisplay(lineDiv);
    });

    refreshProductOptionLabels();
}

function addIbtLine() {
    lineIndex++;

    const lineId = `ibt-line-${lineIndex}`;
    const selectId = `product-select-${lineIndex}`;

    const lineDiv = document.createElement("div");
    lineDiv.className = "ibt-line";
    lineDiv.id = lineId;
    lineDiv.dataset.unitMode = currentUnitMode;
    lineDiv.dataset.selectedProductId = "";

    lineDiv.innerHTML = `
        <div class="product-row">
            <div class="product-select-wrapper">
                <select id="${selectId}" class="product-select">
                    <option></option>
                </select>
            </div>
            <div class="product-row-bottom">
                <div class="qty-control">
                    <input type="number" class="qty-input" min="0" step="1" placeholder="Qty"/>
                </div>
                <div class="uom-label stock-unit">—</div>
                <button type="button" class="issue-remove-btn" title="Remove line">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
            <div class="stock-equivalent">
                <span class="stock-qty-value">0</span>
                <span class="stock-unit-code">—</span>
            </div>
        </div>
    `;

    document.getElementById("ibt-lines-container").appendChild(lineDiv);

    const removeBtn = lineDiv.querySelector('.issue-remove-btn');
    removeBtn.addEventListener('click', () => {
        const removedProduct = lineDiv.dataset.selectedProductId;
        if (removedProduct) {
            selectedProducts.delete(removedProduct);
        }
        lineDiv.remove();
        syncSelectOptionsState();
    });

    const qtyInput = lineDiv.querySelector('.qty-input');
    qtyInput.addEventListener('input', () => updateStockQtyDisplay(lineDiv));

    populateSelect(selectId, lineDiv);
}

function formatProductOption (state) {
    if (!state.id) return state.text;

    const $element = $(state.element);
    const productDesc = $element.data("product_desc") || state.text.split(" (In:")[0] || state.text;
    const qty = Number($element.data("qty")) || 0;
    const conversionFactor = Number($element.data("conversion_factor")) || 1;
    const displayQty = currentUnitMode === "purchasing"
        ? roundTo2(qty)
        : roundTo2(qty * conversionFactor);
    const unitCode = currentUnitMode === "purchasing"
        ? $element.data("purchasing_unit_code") || ""
        : $element.data("stocking_unit_code") || "";
    const displayText = `${productDesc} (In: ${displayQty.toFixed(2)} ${unitCode})`;

    const $elementDom = $(state.element);
    if ($elementDom.prop("disabled")) {
        return $(
            `<span style="
                color:#999 !important;
                opacity:0.6;
                text-decoration: line-through;
            ">
                ${displayText} (already used)
            </span>`
        );
    }

    return displayText;
}

function populateSelect(selectId, lineDiv) {
    const select = document.getElementById(selectId);

    products.forEach(p => {
        const displayQty = Number(p.qty_in_whse) || 0;
        const displayUnitCode = currentUnitMode === "purchasing" ? (p.purchasing_unit_code || "") : (p.stocking_unit_code || "");
        const displayQtyForMode = currentUnitMode === "purchasing"
            ? roundTo2(displayQty)
            : roundTo2(displayQty * Number(p.conversion_factor || 1));
        const opt = new Option(`${p.product_desc} (In: ${displayQtyForMode.toFixed(2)} ${displayUnitCode})`, p.product_id, false, false);
        opt.dataset.productDesc = p.product_desc || "";
        opt.dataset.purchasingUnitCode = p.purchasing_unit_code || "";
        opt.dataset.purchasingUnitId = p.purchasing_unit_id || "";
        opt.dataset.qty = Number(displayQty.toFixed(2));
        opt.dataset.stockingUnitCode = p.stocking_unit_code || "";
        opt.dataset.conversionFactor = Number(p.conversion_factor) || 1;
        $(opt).data("product_desc", p.product_desc || "");
        $(opt).data("purchasing_unit_code", p.purchasing_unit_code || "");
        $(opt).data("purchasing_unit_id", p.purchasing_unit_id || null);
        $(opt).data("qty", Number(displayQty.toFixed(2)));
        $(opt).data("stocking_unit_code", p.stocking_unit_code || "");
        $(opt).data("conversion_factor", Number(p.conversion_factor) || 1);

        if (selectedProducts.has(String(p.product_id))) {
            opt.disabled = true;
        }

        select.appendChild(opt);
    });

    $(`#${selectId}`).select2({
        placeholder: "Search and select a product...",
        allowClear: true,
        width: "100%",
        dropdownParent: document.body,
        templateResult: formatProductOption,
        templateSelection: formatProductOption
    });

    $(`#${selectId}`).on("select2:select", async function () {
        const selected = $(this).find(":selected").data();
        const val = this.value;
        const previousSelection = lineDiv.dataset.selectedProductId || "";
        const conversionFactor = Number(selected.conversion_factor) || 1;

        if (previousSelection && previousSelection !== val) {
            selectedProducts.delete(previousSelection);
        }

        const duplicateElsewhere = selectedProducts.has(val);
        if (duplicateElsewhere && previousSelection !== val) {
            const duplicateLine = Array.from(document.querySelectorAll('.ibt-line')).find((candidate) => candidate !== lineDiv && candidate.dataset.selectedProductId === val);
            if (duplicateLine) {
                const result = await Swal.fire({
                    title: "Duplicate Product",
                    text: "This product is already selected on another line. Merge the quantities into the existing line or cancel?",
                    icon: "warning",
                    showCancelButton: true,
                    confirmButtonText: "Merge",
                    cancelButtonText: "Cancel"
                });

                if (!result.isConfirmed) {
                    $(this).val(previousSelection || null).trigger("change.select2");
                    if (previousSelection) {
                        selectedProducts.add(previousSelection);
                    }
                    syncSelectOptionsState();
                    return;
                }

                const incomingQty = Number(lineDiv.querySelector('.qty-input').value) || 0;
                const targetQtyInput = duplicateLine.querySelector('.qty-input');
                const targetMode = duplicateLine.dataset.unitMode || 'purchasing';
                const currentMode = lineDiv.dataset.unitMode || 'purchasing';
                const convertedQty = convertQtyBetweenUnits(incomingQty, conversionFactor, currentMode, targetMode);
                targetQtyInput.value = roundTo2((Number(targetQtyInput.value) || 0) + convertedQty);
                updateStockQtyDisplay(duplicateLine);

                lineDiv.remove();
                syncSelectOptionsState();
                return;
            }
        }

        if (val) {
            selectedProducts.add(val);
        }
        lineDiv.dataset.selectedProductId = val;
        lineDiv.dataset.conversionFactor = conversionFactor;

        lineDiv.querySelector('.stock-unit').textContent = (lineDiv.dataset.unitMode === 'stocking' ? selected.stocking_unit_code : selected.purchasing_unit_code) || '—';
        updateStockQtyDisplay(lineDiv);
        syncSelectOptionsState();
    });

    $(`#${selectId}`).on("select2:clear", function () {
        const currentSelection = lineDiv.dataset.selectedProductId || "";
        if (currentSelection) {
            selectedProducts.delete(currentSelection);
        }
        lineDiv.dataset.selectedProductId = "";
        lineDiv.querySelector('.stock-unit').textContent = "—";
        lineDiv.querySelector('.stock-unit-code').textContent = "—";
        lineDiv.querySelector('.stock-qty-value').textContent = "0";
        syncSelectOptionsState();
    });
}

function updateStockQtyDisplay(lineDiv) {
    const select = lineDiv.querySelector('.product-select');
    const qtyInput = lineDiv.querySelector('.qty-input');
    const stockQtyValue = lineDiv.querySelector('.stock-qty-value');
    const stockUnitCode = lineDiv.querySelector('.stock-unit-code');

    if (!select.value) {
        stockQtyValue.textContent = '0';
        stockUnitCode.textContent = '—';
        return;
    }

    const selected = $(select).find(':selected').data();
    const conversionFactor = Number(selected.conversion_factor) || 1;
    const qty = Number(qtyInput.value) || 0;
    const unitMode = lineDiv.dataset.unitMode || currentUnitMode;
    const displayUnitCode = unitMode === 'purchasing' ? selected.purchasing_unit_code || '—' : selected.stocking_unit_code || '—';
    const equivalentQty = unitMode === 'purchasing' ? roundTo2(qty * conversionFactor) : roundTo2(qty);

    lineDiv.querySelector('.stock-unit').textContent = displayUnitCode;
    stockQtyValue.textContent = equivalentQty.toLocaleString(undefined, {maximumFractionDigits: 2});
    stockUnitCode.textContent = selected.stocking_unit_code || '—';
}

// Prompt user to open the stock adjustment modal if they have permission.
// Returns a Promise that resolves true if an adjustment occurred, false otherwise.
function promptStockAdjustment(stockLink, warehouseCode, qtyNeeded = 0) {
    return new Promise(async (resolve) => {
        try {
            // Probe permission by calling the products endpoint (it returns 403 if unauthorized)
            const probe = await fetch('/inventory/adjust_stock/products');
            if (probe.status === 403) {
                Swal.fire('Not enough stock', 'Requested quantity exceeds available and you do not have permission to adjust stock.', 'error');
                return resolve(false);
            }

            const overageText = qtyNeeded > 0 ? `You need ${qtyNeeded} more units to continue.` : 'Requested quantity is greater than available.';
            const resp = await Swal.fire({
                title: 'Quantity exceeds available',
                text: `${overageText} Open stock adjustment to add stock?`,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Open stock adjustment',
                cancelButtonText: 'Cancel'
            });

            if (!resp.isConfirmed) return resolve(false);

            // Load popup HTML, inject into modal and execute module script.
            const cssPath = '/inventory/static/css/stock_adjustment.css';
            const modulePath = '/inventory/static/stock_adjustment_ui.js';
            function ensureCss(href) {
                return new Promise((resolve, reject) => {
                    if (document.querySelector(`link[href^="${href}"]`)) return resolve();
                    const link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.href = href;
                    link.onload = () => resolve();
                    link.onerror = () => reject(new Error('Failed to load CSS: ' + href));
                    document.head.appendChild(link);
                });
            }
            function ensureModule(src) {
                return new Promise((resolve, reject) => {
                    if (document.querySelector(`script[src^="${src}"]`)) return resolve();
                    const script = document.createElement('script');
                    script.type = 'module';
                    script.src = src;
                    script.onload = () => resolve();
                    script.onerror = () => reject(new Error('Failed to load module: ' + src));
                    document.body.appendChild(script);
                });
            }
            await ensureCss(cssPath);
            if (typeof initStockAdjustment !== 'function') {
                await ensureModule(modulePath);
            }
            const htmlRes = await fetch('/inventory/adjust_stock/popup');
            if (!htmlRes.ok) throw new Error('Failed to load adjustment UI');
            const html = await htmlRes.text();

            // Create modal container
            let modal = document.getElementById('stockAdjustmentModal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'stockAdjustmentModal';
                Object.assign(modal.style, { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999 });
                const inner = document.createElement('div');
                inner.id = 'stockAdjustmentModalBody';
                Object.assign(inner.style, { background: '#fff', borderRadius: '12px', maxWidth: '920px', width: '100%', maxHeight: '90vh', overflow: 'auto', padding: '18px', boxSizing: 'border-box', position: 'relative' });
                modal.appendChild(inner);
                document.body.appendChild(modal);
            }
            const modalBody = document.getElementById('stockAdjustmentModalBody');
            if (!modalBody) {
                return resolve(false);
            }
            let closeModal = () => {
                try { modal.remove(); } catch (e) {}
                resolve(false);
            };
            const overlayHandler = (event) => {
                if (event.target === modal) {
                    closeModal();
                }
            };
            modal.addEventListener('click', overlayHandler);
            modalBody.innerHTML = '';
            const closeButton = document.createElement('button');
            closeButton.type = 'button';
            closeButton.textContent = '×';
            Object.assign(closeButton.style, { position: 'absolute', top: '14px', right: '14px', width: '34px', height: '34px', border: 'none', borderRadius: '50%', background: '#f8fafc', color: '#0f172a', fontSize: '20px', cursor: 'pointer', lineHeight: '1', boxShadow: '0 2px 6px rgba(0,0,0,0.12)' });
            closeButton.addEventListener('click', closeModal);
            modalBody.appendChild(closeButton);
            const contentWrapper = document.createElement('div');
            Object.assign(contentWrapper.style, { paddingTop: '10px' });
            contentWrapper.innerHTML = html;
            modalBody.appendChild(contentWrapper);
            if (stockLink) modalBody.dataset.product = stockLink;
            if (warehouseCode) modalBody.dataset.warehouse = warehouseCode;
            modalBody.dataset.unit = 'purchasing';

            if (typeof initStockAdjustment === 'function') {
                initStockAdjustment(modalBody);
            }

            // Listen for success event, then resolve true
            let resolved = false;
            const cleanup = () => {
                if (resolved) return;
                resolved = true;
                window.removeEventListener('stockAdjustment:success', handler);
                modal.removeEventListener('click', overlayHandler);
            };
            const handler = (ev) => {
                cleanup();
                try { modal.remove(); } catch (e) {}
                resolve(true);
            };
            closeModal = () => {
                cleanup();
                try { modal.remove(); } catch (e) {}
                resolve(false);
            };
            window.addEventListener('stockAdjustment:success', handler);

        } catch (err) {
            console.warn('promptStockAdjustment error', err);
            Swal.fire('Error', err.message || 'Failed to open adjustment UI', 'error');
            return resolve(false);
        }
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
        ibtLines.forEach((line) => {
            const productItem = document.createElement("div");
            productItem.className = "compact-product-item";
            
            const qtyDisplay = Number(line.qty).toLocaleString(undefined, {maximumFractionDigits:2});
            const stockDisplay = Number(line.stock_qty).toLocaleString(undefined, {maximumFractionDigits:2});
            const displayUnit = line.display_unit_code || line.uom_code;

            productItem.innerHTML = `
                <div class="product-details">
                    <div class="product-name">${line.productText}</div>
                    <div class="product-meta">
                        ${qtyDisplay} ${displayUnit} → ${stockDisplay} ${line.stocking_uom_code}
                    </div>
                </div>
                <div class="product-qty">
                    <span class="qty-badge">${qtyDisplay} ${displayUnit}</span>
                </div>
            `;
            
            productsSection.appendChild(productItem);
        });
    }
    
    summaryDiv.appendChild(productsSection);
}

function updateLineQty(index, newQty) {
    const qty = Math.round(Number(newQty) * 100) / 100;
    if (qty > 0 && qty <= ibtLines[index].availableQty) {
        ibtLines[index].qty = qty;
        // Re-render summary to reflect changes
        renderSummaryUltraCompact();
    } else {
        // Re-render (previous value remains)
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