let ibtLines = [];
let lineIndex = 0;  
let products = [];
let selectedProducts = new Set();
let currentUnitMode = "stocking";
let editIbtId = null;
let currentIbtStatus = null;
let ibtWarehousesRequest = Promise.resolve();

// Promise that resolves when warehouse selects are populated
window.__ibtWarehousesLoaded = new Promise((res) => { window.__resolveIbtWarehouses = res; });


document.addEventListener("DOMContentLoaded", async () => {
    const whFrom = document.getElementById("wh-from");
    const whTo = document.getElementById("wh-to");

    // Fetch and populate warehouses
    const res = await request("/inventory/fetch_warehouses");
    const data = await res.json();
    console.log("Fetched warehouses:", data);
    if (!data.success) {
        return Swal.fire("Error Loading Warehouses", data.message || "Failed to fetch warehouses.", "error");
    }
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

    // When a 'From' warehouse is chosen, limit 'To' warehouses to the same type
    $('#wh-from').on('change', async function () {
        const fromId = $(this).val();
        const $whTo = $('#wh-to');

        if (!fromId) {
            // Reset To select to default state
            $whTo.empty().append('<option disabled selected>Select warehouse</option>').trigger('change');
            return;
        }

        ibtWarehousesRequest = (async () => {
            const res = await request(`/inventory/fetch_whses_with_same_type?whse_id=${encodeURIComponent(fromId)}`);
            const data = await res.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to fetch matching warehouses.');
            }

            const warehousesSameType = data.warehouses || [];

            // Rebuild the To select options while keeping Select2 intact
            const previous = $whTo.val();
            $whTo.empty();
            $whTo.append('<option disabled selected>Select warehouse</option>');
            warehousesSameType.forEach(w => {
                $whTo.append(`<option value="${w.id}">${w.name}</option>`);
            });
            // Try to restore previous selection if still present
            if (previous && $whTo.find(`option[value="${previous}"]`).length) {
                $whTo.val(previous);
            } else {
                $whTo.val(null);
            }
            $whTo.trigger('change.select2');
            $('#wh-to').select2({
                placeholder: "Select warehouse",
                allowClear: false,
                width: '100%'
            });
        })().catch(err => {
            console.error('Error fetching same-type warehouses', err);
            Swal.fire('Error', 'Failed to fetch matching warehouses.', 'error');
            throw err;
        });
        await ibtWarehousesRequest;
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
            const res = await request("/inventory/fetch_products_in_both_whses", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ whse_from_id: fromWh, whse_to_id: toWh })
            });

            const data = await res.json();

            if (!data.success) {
                Swal.close();
                return Swal.fire({
                    icon: "error",
                    title: "Error Loading Products",
                    text: data.message
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

            const productData = ($(select).select2("data") || [])[0] || {};

            if (!productData.id) {
                return Swal.fire("Product Error", "Could not read selected product data.", "error");
            }
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
                    const refreshRes = await request(`/inventory/adjust_stock/qty?stock_link=${encodeURIComponent(productId)}&warehouse_link=${encodeURIComponent(wh)}`);
                    const refreshJson = await refreshRes.json();
                    if (refreshJson.success) {
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
                    } else {
                        return Swal.fire(
                            "Error Refreshing Stock",
                            refreshJson.message || "Failed to refresh stock information.",
                            "error"
                        );
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
            console.log(uom_code, stocking_uom_code);
        }

        console.log("✔ Valid lines:", ibtLines);

        renderSummaryUltraCompact();
        document.getElementById("ibt-step-2").classList.add("hidden");
        document.getElementById("ibt-step-3").classList.remove("hidden");
    });

    // --- Submit IBT ---
    const submitIbt = async (action = "request") => {
        if (editIbtId && action !== "request") {
            return transitionExistingIbt(action);
        }
        const fromWarehouseId = $('#wh-from').val();
        const toWarehouseId = $('#wh-to').val();
        if (!fromWarehouseId || !toWarehouseId) {
            Swal.fire("Missing Warehouses", "Please select both the source and destination warehouses before submitting the IBT.", "warning");
            return;
        }
        if (fromWarehouseId === toWarehouseId) {
            Swal.fire("Invalid Warehouses", "The source and destination warehouses must be different.", "warning");
            return;
        }
        if (!(await confirmWholePurchasingQuantities())) {
            return;
        }
        const payload = {
            from_warehouse_id: fromWarehouseId,
            to_warehouse_id: toWarehouseId,
            lines: ibtLines.map(line => ({
                product_id: line.product_id,
                qty: line.stock_qty ?? line.qty
            }))
        };
        if (!editIbtId) payload.action = action;

        const endpoint = editIbtId ? `/inventory/ibt/${encodeURIComponent(editIbtId)}/update` : "/inventory/ibt/create";
        showWorkflowBusy("Submitting IBT...");
        try {
            const res = await request(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.message || "Unable to save the IBT.");
            Swal.close();
            const ibtNumber = data.ibt_number || editIbtId;
            const updateApprovedIbt = editIbtId && currentIbtStatus === "APPROVED";
            const successTitle = action === "approve_issue"
                ? "IBT Approved and Issued"
                : action === "approve" || updateApprovedIbt
                    ? "IBT Approved"
                    : "IBT Request Submitted";
            await Swal.fire({
                icon: "success",
                title: successTitle,
                text: "IBT Number: " + ibtNumber
            });
            window.location.href = `/inventory/SDK/IBT_detail?ibt_no=${encodeURIComponent(ibtNumber)}`;
        } finally {
            Swal.close();
        }
    };

    document.getElementById("ibt-submit").addEventListener("click", () => submitIbt("request").catch(showWorkflowError));

    const transitionExistingIbt = async (action) => {
        if (!editIbtId) return;
        if (!(await confirmWholePurchasingQuantities())) {
            return;
        }
        const body = action === "reject"
            ? { reason: window.prompt("Rejection reason") || "" }
            : undefined;
        showWorkflowBusy(`${action[0].toUpperCase()}${action.slice(1)} IBT...`);
        try {
            const res = await request(`/inventory/ibt/${encodeURIComponent(editIbtId)}/${action}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: body ? JSON.stringify(body) : undefined
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.message || `Unable to ${action} IBT.`);
            window.location.href = `/inventory/SDK/IBT_detail?ibt_no=${encodeURIComponent(editIbtId)}`;
        } finally {
            Swal.close();
        }
    };

    document.getElementById("ibt-approve").addEventListener("click", () => {
        const action = editIbtId ? transitionExistingIbt("approve") : submitIbt("approve");
        action.catch(showWorkflowError);
    });
    document.getElementById("ibt-reject").addEventListener("click", () => transitionExistingIbt("reject").catch(showWorkflowError));
    document.getElementById("ibt-issue").addEventListener("click", () => transitionExistingIbt("issue").catch(showWorkflowError));
    document.getElementById("ibt-approve-issue").addEventListener("click", () => {
        if (editIbtId) return;
        submitIbt("approve_issue").catch(showWorkflowError);
    });

    configureExistingActions();

    // --- Back Button from Step 2 to Step 1 ---
    document.getElementById("step-2-back-btn").addEventListener("click", () => {
        document.getElementById("ibt-step-2").classList.add("hidden");
        document.getElementById("ibt-step-1").classList.remove("hidden");
    });

    // --- Edit or return from Step 3 ---
    document.getElementById("step-3-back-btn").addEventListener("click", async () => {
        if (editIbtId && !isExistingEditable()) {
            return;
        }
        if (editIbtId && !document.querySelector('.ibt-line')) {
            try {
                await loadExistingLinesForEdit();
            } catch (error) {
                return showWorkflowError(error);
            }
        }
        document.getElementById("ibt-step-3").classList.add("hidden");
        document.getElementById("ibt-step-2").classList.remove("hidden");
    });
});

function showWorkflowError(error) {
    Swal.fire("IBT action failed", error.message || "Unable to complete the action.", "error");
}

function showWorkflowBusy(title = "Working...") {
    Swal.fire({
        title,
        text: "Please wait while the IBT is processed.",
        allowOutsideClick: false,
        allowEscapeKey: false,
        didOpen: () => Swal.showLoading()
    });
}

async function confirmWholePurchasingQuantities() {
    const fractionalLines = ibtLines.filter(line => {
        const purchasingQty = line.selected_unit_mode === "stocking"
            ? Number(line.stock_qty ?? line.qty) / (Number(line.conversion_factor) || 1)
            : Number(line.qty);
        return Math.abs(purchasingQty - Math.round(purchasingQty)) > 0.000001;
    });

    if (!fractionalLines.length) return true;

    const details = fractionalLines.map(line => {
        const purchasingQty = line.selected_unit_mode === "stocking"
            ? Number(line.stock_qty ?? line.qty) / (Number(line.conversion_factor) || 1)
            : Number(line.qty);
        const productName = line.product_desc || (line.productText || "").split(" (In:")[0];
        return `<li>${productName}: ${purchasingQty.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${line.uom_code || "purchasing units"}</li>`;
    }).join("");

    const result = await Swal.fire({
        icon: "warning",
        title: "Fractional purchasing quantities",
        html: `<p>These quantities are not whole purchasing units:</p><ul style="text-align:left; margin:0; padding-left:1.2rem;">${details}</ul><p>Half a purchasing unit may mean sending part of a can or bag. Continue anyway?</p>`,
        showCancelButton: true,
        confirmButtonText: "Continue",
        cancelButtonText: "Go back",
        confirmButtonColor: "#d97706"
    });

    return result.isConfirmed;
}

function configureExistingActions() {
    const permissions = window.IBT_PERMISSIONS || [];
    const allowed = permission => permissions.includes(`IBT_${permission}`);
    const isExisting = Boolean(editIbtId);
    const editable = isExistingEditable();
    const canRequest = !isExisting && allowed("REQUEST");
    const canApprove = allowed("APPROVE") && (!isExisting || currentIbtStatus === "REQUESTED");
    const canReject = isExisting && currentIbtStatus === "REQUESTED" && allowed("REJECT");
    const canIssue = isExisting && currentIbtStatus === "APPROVED" && allowed("ISSUE");
    const canApproveIssue = !isExisting && allowed("APPROVE") && allowed("ISSUE");
    const submit = document.getElementById("ibt-submit");
    submit.classList.toggle("hidden", isExisting ? !editable : !canRequest);
    submit.textContent = currentIbtStatus === "APPROVED"
        ? "Approve IBT"
        : currentIbtStatus === "REJECTED"
            ? "Resubmit Request"
            : "Submit Request";
    console.log("Existing:", isExisting, "Editable:", editable, "Can Request:", canRequest, "Can Approve:", canApprove, "Can Reject:", canReject, "Can Issue:", canIssue, "Can Approve & Issue:", canApproveIssue);
    document.getElementById("ibt-approve").classList.toggle("hidden", !canApprove);
    document.getElementById("ibt-reject").classList.toggle("hidden", !canReject);
    document.getElementById("ibt-issue").classList.toggle("hidden", !canIssue);
    document.getElementById("ibt-approve-issue").classList.toggle("hidden", !canApproveIssue);
    const editButton = document.getElementById("step-3-back-btn");
    editButton.textContent = isExisting ? "Edit" : "Back to Products";
    editButton.classList.toggle("hidden", isExisting && !editable);
}

function syncUnitModeButtons() {
    document.querySelectorAll(".unit-mode-btn[data-global-unit-mode]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.globalUnitMode === currentUnitMode);
    });
}

function isExistingEditable() {
    const permissions = window.IBT_PERMISSIONS || [];
    const allowed = permission => permissions.includes(`IBT_${permission}`);
    if (!editIbtId) return false;
    if (["REQUESTED", "REJECTED"].includes(currentIbtStatus)) {
        return allowed("REQUEST");
    }
    return currentIbtStatus === "APPROVED" && allowed("APPROVE");
}

async function loadExistingLinesForEdit() {
    const detailRes = await request(`/inventory/ibt/detail/${encodeURIComponent(editIbtId)}`);
    const detailData = await detailRes.json();
    if (!detailRes.ok || !detailData.success) {
        throw new Error(detailData.message || "Unable to load IBT lines.");
    }
    const productsRes = await request('/inventory/fetch_products_in_both_whses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            whse_from_id: String(detailData.ibt.warehouse_from.id),
            whse_to_id: String(detailData.ibt.warehouse_to.id)
        })
    });
    const productsData = await productsRes.json();
    if (!productsRes.ok || !productsData.success) {
        throw new Error(productsData.message || "Unable to load products.");
    }
    products = productsData.products || [];
    document.getElementById('ibt-lines-container').innerHTML = '';
    lineIndex = 0;
    selectedProducts = new Set();
    ibtLines = [];
    currentUnitMode = "stocking";
    syncUnitModeButtons();
    for (const line of detailData.lines) {
        addIbtLine();
        const selectId = `product-select-${lineIndex}`;
        const select = document.getElementById(selectId);
        $(select).val(String(line.product_id)).trigger('change');
        const lineDiv = document.getElementById(`ibt-line-${lineIndex}`);
        lineDiv.dataset.selectedProductId = String(line.product_id);
        lineDiv.dataset.unitMode = "stocking";
        lineDiv.dataset.conversionFactor = getLineConversionFactor(lineDiv);
        lineDiv.querySelector('.qty-input').value = String(line.qty || 0);
        selectedProducts.add(String(line.product_id));
        updateStockQtyDisplay(lineDiv);
    }
}

// Helper: read query param
function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

// If a prefill payload is present in the URL, decode it and prefill step 2 (but do NOT auto-submit)
document.addEventListener('DOMContentLoaded', async () => {
    // Support both URL prefill (legacy) and sessionStorage (preferred for large payloads)
    const prefillRawUrl = getQueryParam('prefill');
    editIbtId = getQueryParam('ibt_no') || getQueryParam('ibt_id');
    const returnTo = getQueryParam('return_to');
    const prefillRawSession = (!prefillRawUrl && returnTo) ? sessionStorage.getItem('ibt_prefill') : null;
    const prefillRaw = prefillRawUrl || prefillRawSession;
    const reviewStep = getQueryParam('step') === '3';
    if (editIbtId && !prefillRaw) {
        try {
            if (window.__ibtWarehousesLoaded) await window.__ibtWarehousesLoaded;
            const detailRes = await request(`/inventory/ibt/detail/${encodeURIComponent(editIbtId)}`);
            const detailData = await detailRes.json();
            console.log(detailData)
            if (!detailRes.ok || !detailData.success) throw new Error(detailData.message || 'Unable to load IBT.');
            currentIbtStatus = detailData.ibt.status;
            $('#wh-from').val(String(detailData.ibt.warehouse_from.id)).trigger('change');
            await ibtWarehousesRequest;
            const destinationId = String(detailData.ibt.warehouse_to.id);
            if (!$('#wh-to').find(`option[value="${destinationId}"]`).length) {
                throw new Error('The destination warehouse is not available for the selected source warehouse.');
            }
            $('#wh-to').val(destinationId).trigger('change.select2');
            const productsRes = await request('/inventory/fetch_products_in_both_whses', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({whse_from_id:String(detailData.ibt.warehouse_from.id), whse_to_id:String(detailData.ibt.warehouse_to.id)}) });
            const productsData = await productsRes.json();
            if (!productsRes.ok || !productsData.success) throw new Error(productsData.message || 'Unable to load products.');
            products = productsData.products || [];
            document.getElementById('ibt-lines-container').innerHTML = '';
            lineIndex = 0;
            selectedProducts = new Set();
            ibtLines = [];
            currentUnitMode = "stocking";
            syncUnitModeButtons();
            for (const line of detailData.lines) {
                addIbtLine();
                const selectId = `product-select-${lineIndex}`;
                $(`#${selectId}`).val(String(line.product_id)).trigger('change');
                const lineDiv = document.getElementById(`ibt-line-${lineIndex}`);
                lineDiv.dataset.selectedProductId = String(line.product_id);
                lineDiv.dataset.unitMode = "stocking";
                lineDiv.dataset.conversionFactor = getLineConversionFactor(lineDiv);
                lineDiv.querySelector('.qty-input').value = String(line.qty || 0);
                selectedProducts.add(String(line.product_id));
                updateStockQtyDisplay(lineDiv);
            }
            document.getElementById('ibt-step-1').classList.add('hidden');
            if (reviewStep) {
                ibtLines = detailData.lines.map(line => ({
                    product_id: String(line.product_id),
                    product_desc: line.product_desc || String(line.product_id),
                    qty: Number(line.qty) || 0,
                    stock_qty: Number(line.qty) || 0,
                    productText: line.product_desc || String(line.product_id),
                    display_unit_code: line.stocking_unit_code || ''
                }));
                renderSummaryUltraCompact();
                document.getElementById('ibt-step-2').classList.add('hidden');
                document.getElementById('ibt-step-3').classList.remove('hidden');
            } else {
                document.getElementById('ibt-step-2').classList.remove('hidden');
            }
            configureExistingActions();
        } catch (error) {
            console.error('Failed to load IBT for editing:', error);
            Swal.fire('Unable to edit IBT', error.message, 'error');
        }
        return;
    }
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
        await ibtWarehousesRequest;
        if (prefill.to_whse) {
            $('#wh-to').val(String(prefill.to_whse)).trigger('change');
        }
        console.log("Prefilling IBT with:", prefill);

        // Fetch products for the selected warehouses (same as clicking Step 1 next)
        const fetchRes = await request('/inventory/fetch_products_in_both_whses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ whse_from_id: String(prefill.from_whse), whse_to_id: String(prefill.to_whse) })
        });
        const data = await fetchRes.json();
        if (!data.success) {
            Swal.fire({ title: "Error Loading Products", text: data.message || "Failed to fetch products for the selected warehouses.", icon: "error" });
        }
        products = data.products || [];

        // Clear any existing lines and selectedProducts
        document.getElementById('ibt-lines-container').innerHTML = '';
        selectedProducts = new Set();
        ibtLines = [];
        currentUnitMode = "stocking";
        syncUnitModeButtons();

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
                console.log(`Prefilling line ${thisIndex} with product ${selectVal} and qty ${ln.qty || ln.Qty || ln.units_suggested || 0}`);
                // Manually update UOM labels since select2:select event may not fire during prefill
                const selected = $(`#${selectId}`).find(':selected').data();
                const stockUnitCode = selected.stocking_unit_code || '';
                thisLineDiv.dataset.conversionFactor = Number(selected.conversion_factor) || getLineConversionFactor(thisLineDiv);
                thisLineDiv.querySelector('.stock-unit').textContent = stockUnitCode;
                thisLineDiv.querySelector('.stock-unit-code').textContent = stockUnitCode;

                const qtyInput = thisLineDiv.querySelector('.qty-input');
                if (qtyInput) {
                    const purchasingQty = Number(ln.qty || ln.Qty || ln.units_suggested || 0);
                    const conversionFactor = Number(selected.conversion_factor) || 1;
                    qtyInput.value = String(roundTo2(purchasingQty * conversionFactor));
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
            // Do not disable options when selected elsewhere; allow duplicates
            $(this).prop("disabled", false);
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

function getLineProductData(lineDiv) {
    const select = lineDiv?.querySelector(".product-select");
    if (!select) return null;

    const selectedData = ($(select).select2("data") || [])[0];
    if (selectedData && selectedData.id) {
        return selectedData;
    }

    const $selected = $(select).find("option:selected");
    if ($selected.length && $selected.val()) {
        return {
            id: $selected.val(),
            product_desc: $selected.data("product_desc"),
            qty: $selected.data("qty"),
            purchasing_unit_code: $selected.data("purchasing_unit_code"),
            purchasing_unit_id: $selected.data("purchasing_unit_id"),
            stocking_unit_code: $selected.data("stocking_unit_code"),
            stocking_unit_id: $selected.data("stocking_unit_id"),
            conversion_factor: $selected.data("conversion_factor")
        };
    }

    const productId = lineDiv.dataset.selectedProductId;
    if (!productId) return null;
    return products.find(p => String(p.product_id) === String(productId)) || null;
}

function getLineConversionFactor(lineDiv) {
    const productData = getLineProductData(lineDiv);
    const factor = Number(
        productData?.conversion_factor ??
        lineDiv?.dataset?.conversionFactor ??
        1
    );
    return factor > 0 ? factor : 1;
}

function setGlobalUnitMode(newMode) {
    if (newMode !== "purchasing" && newMode !== "stocking") {
        return;
    }

    if (currentUnitMode === newMode) {
        syncUnitModeButtons();
        return;
    }

    const previousMode = currentUnitMode;
    currentUnitMode = newMode;
    syncUnitModeButtons();

    document.querySelectorAll(".ibt-line").forEach((lineDiv) => {
        const qtyInput = lineDiv.querySelector(".qty-input");
        const currentQty = Number(qtyInput?.value) || 0;
        const currentMode = lineDiv.dataset.unitMode || previousMode || "purchasing";
        const conversionFactor = getLineConversionFactor(lineDiv);

        // Convert the typed qty into the new unit so the stocking-unit total stays unchanged.
        if (qtyInput && currentMode !== newMode) {
            qtyInput.value = convertQtyBetweenUnits(
                currentQty,
                conversionFactor,
                currentMode,
                newMode
            );
        }

        lineDiv.dataset.unitMode = newMode;
        lineDiv.dataset.conversionFactor = conversionFactor;
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

    // Always show the product display text; do not render as disabled/greyed-out
    return displayText;
}

function populateSelect(selectId, lineDiv) {
    const $sel = $(`#${selectId}`);

    // Build rich data objects (exactly like PO)
    const options = products.map(p => {
        const qty = Number(p.qty_in_whse) || 0;
        const conversionFactor = Number(p.conversion_factor) || 1;
        const displayQty = currentUnitMode === "purchasing"
            ? roundTo2(qty)
            : roundTo2(qty * conversionFactor);
        const unitCode = currentUnitMode === "purchasing"
            ? (p.purchasing_unit_code || "")
            : (p.stocking_unit_code || "");

        const text = `${p.product_desc} (In: ${displayQty.toFixed(2)} ${unitCode})`;

        return {
            id: String(p.product_id),
            text: text,
            // keep everything you need on the object
            product_desc: p.product_desc || "",
            qty: qty,
            purchasing_unit_code: p.purchasing_unit_code || "",
            purchasing_unit_id: p.purchasing_unit_id || null,
            stocking_unit_code: p.stocking_unit_code || "",
            stocking_unit_id: p.stocking_unit_id || null,
            conversion_factor: conversionFactor
        };
    });

    // Destroy previous instance if any
    if ($sel.hasClass("select2-hidden-accessible")) {
        try { $sel.select2("destroy"); } catch (e) {}
    }

    $sel.empty().select2({
        data: options,
        placeholder: "Search and select a product...",
        allowClear: false,
        width: "100%",
        dropdownParent: $(document.body),
        escapeMarkup: m => m,
        templateResult: state => state.id ? state.text : state.text,
        templateSelection: state => state.id ? state.text : state.text
    });

    options.forEach((opt) => {
        $sel.find(`option[value="${opt.id}"]`).data({
            product_desc: opt.product_desc,
            qty: opt.qty,
            purchasing_unit_code: opt.purchasing_unit_code,
            purchasing_unit_id: opt.purchasing_unit_id,
            stocking_unit_code: opt.stocking_unit_code,
            stocking_unit_id: opt.stocking_unit_id,
            conversion_factor: opt.conversion_factor
        });
    });

    $sel.on("select2:open", function () {
    const $container = $sel.next(".select2-container");
    const controlWidth = $container.outerWidth();   // width when closed
    const $dropdown = $(".select2-container--open .select2-dropdown");

    $dropdown.css({
        width: controlWidth + "px",
        "min-width": controlWidth + "px",           // never narrower than closed
        "max-width": "calc(100vw - 24px)",          // never wider than screen
        "box-sizing": "border-box"
    });
});

    const applySelectedProduct = (data) => {
        if (!data || !data.id) return;

        const val = String(data.id);
        const previousSelection = lineDiv.dataset.selectedProductId || "";
        const conversionFactor = Number(data.conversion_factor) || 1;

        if (previousSelection && previousSelection !== val) {
            selectedProducts.delete(previousSelection);
        }

        if (val) selectedProducts.add(val);
        lineDiv.dataset.selectedProductId = val;
        lineDiv.dataset.conversionFactor = conversionFactor;

        const unitCode = (lineDiv.dataset.unitMode === "stocking"
            ? data.stocking_unit_code
            : data.purchasing_unit_code) || "—";

        const unitLabel = lineDiv.querySelector(".stock-unit");
        if (unitLabel) unitLabel.textContent = unitCode || "—";
        updateStockQtyDisplay(lineDiv);
        syncSelectOptionsState();
    };

    $sel.off("select2:select").on("select2:select", function (e) {
        applySelectedProduct(e.params.data);
    });

    $sel.off("change.ibtUnit").on("change.ibtUnit", function () {
        applySelectedProduct(($(this).select2("data") || [])[0]);
    });
}

function updateStockQtyDisplay(lineDiv) {
    const qtyInput = lineDiv.querySelector(".qty-input");
    const stockQtyValue = lineDiv.querySelector(".stock-qty-value");
    const stockUnitCode = lineDiv.querySelector(".stock-unit-code");

    const selectedData = getLineProductData(lineDiv);
    if (!selectedData || !selectedData.id) {
        if (stockQtyValue) stockQtyValue.textContent = "0";
        if (stockUnitCode) stockUnitCode.textContent = "—";
        return;
    }

    const conversionFactor = getLineConversionFactor(lineDiv);
    const qty = Number(qtyInput?.value) || 0;
    const unitMode = lineDiv.dataset.unitMode || currentUnitMode;
    const displayUnitCode = unitMode === "purchasing"
        ? (selectedData.purchasing_unit_code || "—")
        : (selectedData.stocking_unit_code || "—");

    // The "total" is always the stocking-unit quantity. Switching unit mode
    // converts the entered qty so this total stays the same.
    const stockingTotal = unitMode === "purchasing"
        ? roundTo2(qty * conversionFactor)
        : roundTo2(qty);

    const unitLabel = lineDiv.querySelector(".stock-unit");
    if (unitLabel) unitLabel.textContent = displayUnitCode;
    if (stockQtyValue) {
        stockQtyValue.textContent = stockingTotal.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    if (stockUnitCode) stockUnitCode.textContent = selectedData.stocking_unit_code || "—";
}

// Prompt user to open the stock adjustment modal if they have permission.
// Returns a Promise that resolves true if an adjustment occurred, false otherwise.
function promptStockAdjustment(stockLink, warehouseCode, qtyNeeded = 0) {
    return new Promise(async (resolve) => {
        try {
            // Probe permission by calling the products endpoint (it returns 403 if unauthorized)
            const probe = await request('/inventory/adjust_stock/products');
            if (probe.status === 403) {
                Swal.fire('Not enough stock', 'Requested quantity exceeds available and you do not have permission to adjust stock.', 'error');
                return resolve(false);
            }
            if (probe.success === false) {
                Swal.fire('Error', probe.message || 'Failed to check stock adjustment permission.', 'error');
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

    const compactSection = document.createElement("div");
    compactSection.className = "compact-summary";

    const header = document.createElement("div");
    header.className = "compact-header";
    header.textContent = "Transfer Summary";
    compactSection.appendChild(header);

    const fromText = $('#wh-from').find(':selected').text() || "—";
    const toText = $('#wh-to').find(':selected').text() || "—";

    const whRow = document.createElement("div");
    whRow.className = "summary-wh-row";
    whRow.innerHTML = `
        <div class="summary-wh">
            <span class="label">From</span>
            <span class="value">${fromText}</span>
        </div>
        <div class="summary-wh">
            <span class="label">To</span>
            <span class="value">${toText}</span>
        </div>
    `;
    compactSection.appendChild(whRow);
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

            const qtyDisplay = Number(line.qty).toLocaleString(undefined, {
                maximumFractionDigits: 2
            });
            const displayUnit = line.display_unit_code || line.uom_code || "";

            // Prefer clean product name if you stored it; fall back to productText
            const name = line.product_desc || (line.productText || "").split(" (In:")[0];

            productItem.innerHTML = `
                <div class="product-details">
                    <div class="product-name">${name}</div>
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