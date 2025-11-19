/* ====== stock_count.js — FINAL & BULLETPROOF VERSION ====== */
let selectedWarehouse = null;
let selectedCategory = null;
let storemanName = null;
let products = [];
let countedProducts = [];
let discrepancies = [];
let recountedProducts = [];
let currentStockCountId = null;

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
        const { suppliers = [] } = await res.json();

        select.innerHTML = "<option value=''>Select warehouse</option>";
        suppliers.forEach(wh => {
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
        const res = await fetch("/inventory/create_inventory_count", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                whse_code: selectedWarehouse,
                category_name: selectedCategory,
                count_storeman: storemanName
            })
        });
        const data = await res.json();
        products = data.products || [];
        currentStockCountId = data.stock_count_id;

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
        submitFinalCount();
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

    // Apply recount values
    recountedProducts = countedProducts.map(p => ({ ...p }));
    discrepancies.forEach((d, i) => {
        const input = document.getElementById(`recount-${i}`);
        if (input && input.value !== "") {
            const idx = recountedProducts.findIndex(x => x.product_code === d.product_code);
            if (idx !== -1) recountedProducts[idx].counted_qty = Number(input.value);
        }
    });

    submitFinalCount();
}

async function submitFinalCount() {
    const payload = {
        stock_count_id: currentStockCountId,
        warehouse: selectedWarehouse,
        category: selectedCategory,
        products: recountedProducts.map(p => ({
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