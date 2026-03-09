/* ====== stock_count.js — ENHANCED WITH COMMAND BAR ====== */
let selectedWarehouse = null;
let selectedCategory = null;
let products = [];
let countedProducts = [];
let discrepancies = [];
let recountedProducts = [];
let countStartTimestamp = null;
let sessionId = window.location.pathname.match(/stock-counts\/(\d+)/)?.[1] || null;
let focusedProductIndex = -1;
let filteredProductIndices = [];
let isSearchMode = false;

document.addEventListener("DOMContentLoaded", init);

window.addEventListener("popstate", e => {
  if (e.state?.sessionId) {
    sessionId = e.state.sessionId;
    loadProductsForSession(sessionId);
    showStep(2);
  } else {
    showStep(1);
  }
});

function clearFocusedRows() {
    document.querySelectorAll(".product-row.focused")
        .forEach(r => r.classList.remove("focused"));
}


/* ====== COMMAND BAR SETUP ====== */
function setupCommandBar() {
    const commandBar = document.getElementById("commandBar");
    const commandSearch = document.getElementById("commandSearch");
    const pauseBtn = document.getElementById("pauseBtn");
    const container = document.getElementById("products-container");

    // Show/hide command bar based on step
    function updateCommandBarVisibility() {
        const step = getActiveStep();
        if (step === 2) {
            commandBar.classList.remove("hidden");
            requestAnimationFrame(() => {
                commandSearch.focus();
            });
        } else {
            commandBar.classList.add("hidden");
        }
    }

    // Input-aware search with auto-focus & auto-advance
    commandSearch.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();

        isSearchMode = query.length > 0;   // 🔥 THIS
        filterAndFocusProducts(query);
    });


    // Handle Enter key to move to next product
    commandSearch.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();

            if (focusedProductIndex >= 0) {
                const idx = filteredProductIndices[focusedProductIndex];
                const input = document.getElementById(`qty-${idx}`);
                if (input) {
                    input.focus();
                    input.select();
                }
            }
        }

        if (e.key === "ArrowDown") {
            e.preventDefault();
            advanceFocus(1);
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            advanceFocus(-1);
        }
    });


    // Auto-advance on qty input
    document.addEventListener("keydown", (e) => {
        if (!e.target.classList.contains("qty-input")) return;
        if (e.key !== "Enter") return;

        e.preventDefault();

        const inputs = Array.from(document.querySelectorAll(".qty-input"));
        const currentIndex = inputs.indexOf(e.target);

        // 🔍 SEARCH MODE → return to search bar
        const commandSearch = document.getElementById("commandSearch");

        if (commandSearch.value.trim() !== "") {
            exitSearchMode();
            return;
        }



        // ⬇️ LINEAR MODE → go to next qty
        const next = inputs[currentIndex + 1];
        if (next) {
            next.focus();
            next.select();

            focusedProductIndex = currentIndex + 1;
            filteredProductIndices = inputs.map((_, i) => i);
            updateFocusedProduct();
        }
    });

    container.addEventListener("blur", e => {
        if (!e.target.matches(".qty-input")) return;

        // Mobile-safe submit behavior
        if (isSearchMode) {
            const commandSearch = document.getElementById("commandSearch");

            commandSearch.value = "";
            isSearchMode = false;

            requestAnimationFrame(() => {
                commandSearch.focus();
            });

        }
    }, true);



    // Pause/Exit button
    pauseBtn.addEventListener("click", (e) => {
        e.preventDefault();
        Swal.fire({
            title: "Pause Count?",
            text: "Your progress will be saved as a draft.",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Exit to Dashboard",
            cancelButtonText: "Continue Counting"
        }).then((result) => {
            if (result.isConfirmed) {
                window.location.href = "/inventory/stock-counts";
            }
        });
    });

    // Update visibility on step change
    const originalShowStep = window.showStep;
    window.showStep = function(n) {
        originalShowStep(n);
        updateCommandBarVisibility();
    };

    // Initial visibility
    updateCommandBarVisibility();
}

/* ====== SEARCH & FILTER LOGIC ====== */
function filterAndFocusProducts(query = "", preserveFocus = false) {
    const rows = document.querySelectorAll(".product-row");
    filteredProductIndices = [];
    if (!preserveFocus) {
        focusedProductIndex = -1;
    }

    rows.forEach((row, idx) => {
        const matches = !query || row.textContent.toLowerCase().includes(query);

        row.classList.toggle("hidden-by-search", !matches);
        row.classList.remove("focused");

        if (matches) filteredProductIndices.push(idx);
    });

    if (filteredProductIndices.length) {
        if (!preserveFocus) {
            focusedProductIndex = 0;
        }

        if (focusedProductIndex >= 0) {
            rows[filteredProductIndices[focusedProductIndex]]
                ?.classList.add("focused");
        }
    }

    updateCounterBadge();
}


function advanceFocus(direction) {
    if (filteredProductIndices.length === 0) return;

    focusedProductIndex += direction;

    // Wrap around
    if (focusedProductIndex < 0) {
        focusedProductIndex = filteredProductIndices.length - 1;
    } else if (focusedProductIndex >= filteredProductIndices.length) {
        focusedProductIndex = 0;
    }

    updateFocusedProduct();
}

function updateFocusedProduct() {
    document.querySelectorAll(".product-row").forEach((row, idx) => {
        row.classList.remove("focused");
    });

    if (focusedProductIndex >= 0 && focusedProductIndex < filteredProductIndices.length) {
        const focusedIdx = filteredProductIndices[focusedProductIndex];
        const row = document.querySelectorAll(".product-row")[focusedIdx];
        if (row) {
            row.classList.add("focused");
            row.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }
}

function updateCounterBadge() {
    const filled = Array.from(document.querySelectorAll(".qty-input")).filter(i => i.value !== "").length;
    const total = products.length;
    document.getElementById("counterBadge").textContent = `${filled}/${total}`;
}

function getActiveStep() {
    const step1 = document.getElementById("step-1");
    const step2 = document.getElementById("step-2");
    const step3 = document.getElementById("step-3");

    if (!step1.classList.contains("hidden")) return 1;
    if (!step2.classList.contains("hidden")) return 2;
    if (!step3.classList.contains("hidden")) return 3;
    return 0;
}

/* ====== Load Warehouses (Safe Select2 Init) ====== */
async function loadWarehouses() {
    const select = document.getElementById("warehouse-select");
    select.innerHTML = "<option>Loading warehouses...</option>";

    try {
        const res = await fetch("/inventory/fetch_warehouses");
        const { warehouses = [] } = await res.json();

        select.innerHTML = "<option value=''>Select warehouse</option>";
        warehouses.forEach(wh => {
            select.innerHTML += `<option value="${wh.id}">${wh.name}</option>`;
        });

        if ($.fn.select2) {
            $('#warehouse-select').off('change');
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
            body: JSON.stringify({ whse_id: selectedWarehouse })
        });
        const { categories: cats = [] } = await res.json();

        catSelect.innerHTML = "<option value=''>Select category</option>";
        cats.forEach(c => {
            catSelect.innerHTML += `<option value="${c.category_id}">${c.category_name}</option>`;
        });

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

async function loadProductsForSession(sessionId) {
    const res = await fetch(`/inventory/stock-counts/${sessionId}/products`);
    const data = await res.json();
    products = data.products || [];
    displayProducts();
    updateCounterBadge();
}

function updateStep1NextButton() {
    const enabled = selectedWarehouse && selectedCategory;
    document.getElementById("step-1-next").disabled = !enabled;
}

/* ====== Start Counting ====== */
async function onStartCounting() {
  const res = await fetch("/inventory/create_stock_count", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      warehouse: selectedWarehouse,
      category: selectedCategory
    })
  });

  const { session_id } = await res.json();
  sessionId = session_id;

  history.pushState(
    { sessionId },
    "",
    `/inventory/stock-counts/${session_id}`
  );

  await loadProductsForSession(session_id);
  showStep(2);
}

function displayProducts() {
    const container = document.getElementById("products-container");
    container.innerHTML = "";
    products.forEach((p, i) => {
        console.log("Displaying product:", p);
        container.innerHTML += `
            <div class="product-row">
                <div class="product-desc" title="${p.product_desc || p.product_code}">
                    ${p.product_desc || p.product_code}
                </div>
                <input
                type="number"
                id="qty-${i}"
                class="qty-input"
                min="0"
                step="1"
                placeholder="0"
                value="${p.counted_qty !== null ? p.counted_qty : ""}"
                >

            </div>`;
    });

    container.addEventListener("input", e => {
        if (e.target.matches(".qty-input")) {
            updateProgress();
            updateCounterBadge();
        }
    });
    
    // Save draft with debounce
    let saveTimer = null;
    container.addEventListener("input", e => {
        if (!e.target.matches(".qty-input")) return;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, 600);
    });

    container.addEventListener("blur", e => {
        if (e.target.matches(".qty-input")) {
            saveDraft();
        }
    }, true);

    async function saveDraft() {
        const lines = [];
        document.querySelectorAll(".qty-input").forEach((input, i) => {
            if (input.value !== "") {
                lines.push({
                    product_code: products[i].product_code,
                    counted_qty: Number(input.value)
                });
            }
        });

        await fetch(`/inventory/stock-counts/${sessionId}/lines`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lines })
        });
    }

    updateProgress();
}

function exitSearchMode({ focusSearch = true } = {}) {
    const commandSearch = document.getElementById("commandSearch");

    isSearchMode = false;
    commandSearch.value = "";

    const focusedRow = document.querySelector(".product-row.focused");
    const prevTop = focusedRow?.getBoundingClientRect().top;

    filterAndFocusProducts("", true);

    if (focusedRow && prevTop !== undefined) {
        requestAnimationFrame(() => {
            const newTop = focusedRow.getBoundingClientRect().top;
            window.scrollBy({
                top: newTop - prevTop,
                behavior: "instant"
            });
        });
    }


    if (focusSearch) {
        requestAnimationFrame(() => commandSearch.focus());
    }
}


function updateProgress() {
    const inputs = document.querySelectorAll(".qty-input");
    const filled = Array.from(inputs).filter(i => i.value !== "").length;
    document.getElementById("progress-text").textContent = `${filled}/${products.length}`;
    const info = document.getElementById("progress-info");
    info.className = filled === products.length ? "completed-info" : "progress-info";
}

/* ====== Complete Count ====== */
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
        .filter(p => Math.abs(p.counted_qty - Number(p.system_qty || 0)) > 0.001)
        .map(p => ({ ...p, original_count: p.counted_qty }));
    console.log("Discrepancies:", discrepancies);
}

/* ====== Recounts ====== */
function displayRecounts() {
    const container = document.getElementById("recount-container");
    const info = document.getElementById("recount-info");
    container.innerHTML = "";

    let saveTimer = null;

    container.addEventListener("input", e => {
        if (!e.target.classList.contains("recount-input")) return;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveRecountDraft, 500);
    });

    async function saveRecountDraft() {
        const lines = [];
        discrepancies.forEach((item, i) => {
            const input = document.getElementById(`recount-${i}`);
            if (input && input.value !== "") {
                lines.push({
                    product_code: item.product_code,
                    counted_qty: Number(input.value)
                });
            }
        });

        if (!lines.length) return;

        await fetch(`/inventory/stock-counts/${sessionId}/lines`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lines })
        });
    }

    info.className = "progress-info";
    info.textContent = `Please recount ${discrepancies.length} item(s)`;

    discrepancies.forEach((item, i) => {
        const row = document.createElement("div");
        row.className = "product-row";
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

    container.addEventListener("input", e => {
        if (!e.target.classList.contains("recount-input")) return;

        const index = Number(e.target.id.split("-")[1]);
        const value = Number(e.target.value);

        if (!isNaN(value)) {
            const productCode = discrepancies[index].product_code;
            const prod = products.find(p => p.product_code === productCode);
            if (prod) {
                prod.counted_qty = value;
            }
        }

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
    });
}

/* ====== Finalize & Submit ====== */
async function onFinalizeClicked() {
  if (discrepancies.length > 0) {
    const missing = Array.from(
      document.querySelectorAll("#recount-container .recount-input")
    ).some(i => i.value === "");

    if (missing) {
      Swal.fire("Incomplete", "Please enter all recount values", "warning");
      return;
    }
  }

  const btn = document.getElementById("step-3-next");
  btn.disabled = true;
  btn.textContent = "Finalising...";

  try {
    const res = await fetch(`/inventory/stock-counts/${sessionId}/finalise`, {
      method: "POST"
    });

    const data = await res.json();

    if (data.success) {
      Swal.fire("Success!", data.message || "Stock count completed", "success")
        .then(() => window.Location.href = "/inventory/stock-counts");
    } else {
      throw new Error(data.error || "Server error");
    }
  } catch (err) {
    Swal.fire("Failed", err.message || "Submission failed", "error");
    btn.disabled = false;
    btn.textContent = "Finalize Count";
  }
}

async function submitFinalCount() {
    const btn = document.getElementById("step-2-next");
    btn.disabled = true;
    btn.textContent = "Submitting...";

    try {
        const res = await fetch(`/inventory/stock-counts/${sessionId}/finalise`, {
            method: "POST"
        });

        const data = await res.json();

        if (data.success) {
            Swal.fire("Success!", data.message || "Stock count completed", "success")
                .then(() => {
                    location.href = "/inventory/stock-counts";
                });
        } else {
            throw new Error(data.error || "Server error");
        }
    } catch (err) {
        Swal.fire("Failed", err.message || "Submission failed", "error");
        btn.disabled = false;
        btn.textContent = "Complete Count";
    }
}

function showStep(n) {
    document.querySelectorAll("#step-1, #step-2, #step-3").forEach((el, i) => {
        el.classList.toggle("hidden", i + 1 !== n);
    });
}

function handleKeyboard() {
  if (!window.visualViewport) return;

  const bar = document.getElementById("commandBar");

  const offset =
    window.innerHeight -
    visualViewport.height -
    visualViewport.offsetTop;

  bar.style.bottom = `${Math.max(offset, 0)}px`;
}

window.visualViewport?.addEventListener("resize", handleKeyboard);
window.visualViewport?.addEventListener("scroll", handleKeyboard);
