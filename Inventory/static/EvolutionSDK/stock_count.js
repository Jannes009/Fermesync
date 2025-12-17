/* ====== stock_count.js — UPDATED VERSION ====== */
let selectedWarehouse = null;
let selectedCategory = null;
let storemanName = null;
let products = [];
let countedProducts = [];
let discrepancies = [];
let recountedProducts = [];
let countStartTimestamp = null; // Add this to track when counting started

document.addEventListener("DOMContentLoaded", init);

function init() {
    loadWarehouses();

    document.getElementById("step-1-next").addEventListener("click", onStartCounting);
    document.getElementById("step-2-next").addEventListener("click", onCompleteCount);
    document.getElementById("storeman-name").addEventListener("input", e => {
        storemanName = e.target.value.trim();
        updateStep1NextButton();
    });

    const finalizeBtn = document.getElementById("step-3-next");
    if (finalizeBtn) finalizeBtn.addEventListener("click", onFinalizeClicked);
}

/* ---------------- Load Warehouses (Safe Select2 Init) ---------------- */
async function loadWarehouses() {
    const select = document.getElementById("warehouse-select");
    select.innerHTML = "<option>Loading warehouses...</option>";

    try {
        const res = await fetch("/inventory/SDK/fetch_warehouses");
        const { warehouses = [] } = await res.json();

        select.innerHTML = "<option value=''>Select warehouse</option>";
        warehouses.forEach(wh => {
            select.innerHTML += `<option value="${wh.code}">${wh.name}</option>`;
        });

        // Safe init: destroy only if already initialized
        if ($.fn.select2) {
            $('#warehouse-select').off('change'); // remove old handlers
            if ($('#warehouse-select').data('select2')) {
                $('#warehouse-select').select2('destroy');
            }
            $('#warehouse-select').select2({
                placeholder: "Select warehouse",
                allowClear: false,
                width: '100%'
            }).on('change', onWarehouseChanged);
        }

    } catch (err) {
        select.innerHTML = "<option>Error loading</option>";
        Swal.fire("Error", "Failed to load warehouses", "error");
    }
}

async function onWarehouseChanged() {
    selectedWarehouse = $('#warehouse-select').val();
    const catSelect = document.getElementById("category-select");
    catSelect.disabled = true;
    catSelect.innerHTML = "<option>Loading categories...</option>";
    updateStep1NextButton();

    if (!selectedWarehouse) {
        catSelect.innerHTML = "<option>Select warehouse first</option>";
        return;
    }

    try {
        const res = await fetch("/inventory/fetch_categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ whse_code: selectedWarehouse })
        });
        const { products: cats = [] } = await res.json();

        catSelect.innerHTML = "<option value=''>Select category</option>";
        cats.forEach(c => {
            catSelect.innerHTML += `<option value="${c.category_name}">${c.category_name}</option>`;
        });

        // Safe re-init of category Select2
        $('#category-select').off('change');
        if ($('#category-select').data('select2')) {
            $('#category-select').select2('destroy');
        }
        $('#category-select').select2({
            placeholder: "Select category",
            allowClear: false,
            width: '100%'
        }).on('change', () => {
            selectedCategory = $('#category-select').val();
            updateStep1NextButton();
        });

        catSelect.disabled = false;
    } catch (err) {
        catSelect.innerHTML = "<option>Error loading</option>";
    }
}

function updateStep1NextButton() {
    const enabled = selectedWarehouse && selectedCategory && storemanName;
    document.getElementById("step-1-next").disabled = !enabled;
}

/* ---------------- Start Counting ---------------- */
async function onStartCounting() {
    try {
        const res = await fetch("/inventory/fetch_inventory_count_products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                whse_code: selectedWarehouse,
                category_name: selectedCategory
            })
        });
        const data = await res.json();
        products = data.products || [];
        
        // Capture the timestamp from the backend response
        countStartTimestamp = data.opening_timestamp || new Date().toISOString();

        if (!products.length) {
            Swal.fire("No Products", "No items in this category", "info");
            return;
        }

        displayProducts();
        showStep(2);
    } catch (err) {
        Swal.fire("Error", "Failed to load products", "error");
    }
}

function displayProducts() {
    const container = document.getElementById("products-container");
    container.innerHTML = "";
    products.forEach((p, i) => {
        container.innerHTML += `
            <div class="product-row">
                <div class="product-desc" title="${p.product_desc || p.product_code}">
                    ${p.product_desc || p.product_code}
                </div>
                <input type="number" id="qty-${i}" class="qty-input" min="0" step="1" placeholder="0">
                <div class="uom-label">${p.stock_unit || "EA"}</div>
            </div>`;
    });

    container.addEventListener("input", e => {
        if (e.target.matches(".qty-input")) updateProgress();
    });
    updateProgress();
}

function updateProgress() {
    const inputs = document.querySelectorAll(".qty-input");
    const filled = Array.from(inputs).filter(i => i.value !== "").length;
    document.getElementById("progress-text").textContent = `${filled}/${products.length}`;
    const info = document.getElementById("progress-info");
    info.className = filled === products.length ? "completed-info" : "progress-info";
}

/* ---------------- Complete Count ---------------- */
function onCompleteCount() {
    if (!validateAllProductsCounted()) {
        Swal.fire("Missing", "Please count all items", "warning");
        return;
    }
    findDiscrepancies();
    if (discrepancies.length === 0) {
        // Pass countedProducts when there are no discrepancies
        submitFinalCount(countedProducts);
    } else {
        displayRecounts();
        showStep(3);
    }
}

function validateAllProductsCounted() {
    countedProducts = [];
    for (let i = 0; i < products.length; i++) {
        const input = document.getElementById(`qty-${i}`);
        const val = input.value.trim();
        if (val === "" || isNaN(val)) {
            input.focus();
            return false;
        }
        countedProducts.push({ ...products[i], counted_qty: Number(val) });
    }
    return true;
}

function findDiscrepancies() {
    discrepancies = countedProducts
        .filter(p => Math.abs(p.counted_qty - Number(p.qty_in_whse || 0)) > 0.001)
        .map(p => ({ ...p, original_count: p.counted_qty }));
}

/* ---------------- Recounts ---------------- */
function displayRecounts() {
    const container = document.getElementById("recount-container");
    const info = document.getElementById("recount-info");
    container.innerHTML = "";
    
    info.className = "progress-info";
    info.textContent = `Please recount ${discrepancies.length} item(s)`;

    discrepancies.forEach((item, i) => {
        const row = document.createElement("div");
        row.className = "product-row"; // Same class as normal products!
        row.style.border = "2px solid #f39c12";
        row.style.background = "#fff9e6";
        row.innerHTML = `
            <div class="product-desc" title="${item.product_desc || ''}">
                <strong>${item.product_code}</strong><br>
                <small style="color:#856404;">${item.product_desc || ''}</small>
            </div>
            <input type="number" 
                   id="recount-${i}" 
                   class="qty-input recount-input" 
                   min="0" 
                   step="1" 
                   placeholder="0"
                   style="border-color:#f39c12; font-size:1.2rem;">
            <div class="uom-label">${item.stock_unit || "EA"}</div>
        `;

        container.appendChild(row);
    });

    // Live update when user types
    container.addEventListener("input", e => {
        if (e.target.classList.contains("recount-input")) {
            const allFilled = [...container.querySelectorAll(".recount-input")]
                .every(input => input.value.trim() !== "");
            
            if (allFilled) {
                info.className = "completed-info";
                info.textContent = "All recounted! Ready to finalize.";
                document.getElementById("step-3-next").disabled = false;
            } else {
                info.className = "progress-info";
                info.textContent = `Please recount ${discrepancies.length} item(s)`;
            }
        }
    });
}
/* ---------------- Finalize & Submit ---------------- */
function onFinalizeClicked() {
    if (discrepancies.length > 0) {
        const missing = Array.from(document.querySelectorAll("#recount-container .recount-input"))
            .some(i => i.value === "");
        if (missing) {
            Swal.fire("Incomplete", "Please enter all recount values", "warning");
            return;
        }
    }

    // Create final products array with all products
    const finalProducts = countedProducts.map(product => {
        // Check if this product was recounted
        const discrepancy = discrepancies.find(d => d.product_code === product.product_code);
        if (discrepancy) {
            // Find the input by index (since we used id="recount-${i}")
            const index = discrepancies.findIndex(d => d.product_code === product.product_code);
            const input = document.getElementById(`recount-${index}`);
            if (input && input.value !== "") {
                return { ...product, counted_qty: Number(input.value) };
            }
        }
        return product;
    });

    submitFinalCount(finalProducts);
}
async function submitFinalCount(finalProducts) {
    // Add safety check to ensure finalProducts is defined
    if (!finalProducts || !Array.isArray(finalProducts)) {
        console.error('finalProducts is undefined or not an array:', finalProducts);
        Swal.fire("Error", "Unable to submit count data", "error");
        return;
    }

    const payload = {
        warehouse: selectedWarehouse,
        category: selectedCategory,
        counted_by: storemanName,
        count_start_timestamp: countStartTimestamp,
        products: finalProducts.map(p => ({
            product_code: p.product_code,
            system_qty: Number(p.qty_in_whse || 0),
            counted_qty: Number(p.counted_qty)
        }))
    };

    const btn = document.getElementById("step-3-next");
    btn.disabled = true;
    btn.textContent = "Submitting...";

    try {
        const res = await fetch("/inventory/submit_stock_count", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            Swal.fire("Success!", data.message || "Stock count completed", "success")
                .then(() => location.reload());
        } else {
            throw new Error(data.error || "Server error");
        }
    } catch (err) {
        Swal.fire("Failed", err.message || "Submission failed", "error");
        btn.disabled = false;
        btn.textContent = "Finalize Count";
    }
}

function showStep(n) {
    document.querySelectorAll("#step-1, #step-2, #step-3").forEach((el, i) => {
        el.classList.toggle("hidden", i + 1 !== n);
    });
}