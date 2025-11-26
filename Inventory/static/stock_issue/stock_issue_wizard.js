let selectedWarehouse = null;
let selectedProject = null;
let issuedTo = null;
let productsInWhse = [];
let lines = [];

document.addEventListener("DOMContentLoaded", async () => {
    await loadWarehouses();
    await loadProjects();

    // Initialize selects AFTER options loaded
    $("#warehouse-select").select2({ placeholder: "Select warehouse", allowClear: true, width: '100%' });
    $("#project-select").select2({ placeholder: "Select project", allowClear: true, width: '100%' });

    document.getElementById("step1-next").onclick = step1Next;
    document.getElementById("add-line").onclick = addLine;
    document.getElementById("step2-next").onclick = step2Next;
    document.getElementById("create-issue").onclick = submitIssue;
    document.getElementById("back-to-step-1").onclick = () => {
        document.getElementById("step-2").classList.add("hidden");
        document.getElementById("step-1").classList.remove("hidden");
    };
    // Back button from step 3 to step 2
    document.getElementById("back-to-step-2").onclick = () => {
        document.getElementById("step-3").classList.add("hidden");
        document.getElementById("step-2").classList.remove("hidden");
    };
});

async function loadWarehouses() {
    const res = await fetch("/inventory/SDK/fetch_warehouses");
    const data = await res.json();
    const whSelect = document.getElementById("warehouse-select");
    whSelect.innerHTML = `<option></option>`;
    (data.warehouses || []).forEach(wh => {
        // keep id as Stock/WhseLink etc (int or string)
        whSelect.innerHTML += `<option value="${wh.id}">${wh.name}</option>`;
    });
}

async function loadProjects() {
    // Match backend route (POST)
    const res = await fetch("/inventory/fetch_projects", { method: "POST", headers: {"Content-Type": "application/json"} });
    const data = await res.json();
    const projSelect = document.getElementById("project-select");
    projSelect.innerHTML = `<option></option>`;
    (data.prod_projects || []).forEach(p => {
        projSelect.innerHTML += `<option value="${p.id}">${p.name}</option>`;
    });
}

async function step1Next() {
    selectedWarehouse = $("#warehouse-select").val();
    selectedProject = $("#project-select").val();
    issuedTo = document.getElementById("issued-to").value.trim();

    if (!selectedWarehouse || !selectedProject || !issuedTo) {
        Swal.fire("Missing Information", "Please complete all fields.", "warning");
        return;
    }

    const res = await fetch("/inventory/fetch_products_in_whse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ whse_link: selectedWarehouse })
    });
    const data = await res.json();
    productsInWhse = data.products || [];

    if (!productsInWhse || productsInWhse.length === 0) {
        Swal.fire("No Products", "No products available in this warehouse.", "warning");
        return;
    }

    // Reset lines area and add one blank line
    document.getElementById("ibt-lines").innerHTML = "";
    addLine();

    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
}

function addLine() {
    if (!productsInWhse || productsInWhse.length === 0) return;

    const container = document.getElementById("ibt-lines");

    // Build options using product_link as value (consistent)
    let optionsHtml = '<option></option>';
    productsInWhse.forEach(p => {
        // note: we store both product_link (id) and product_code in data attributes for later use
        optionsHtml += `<option value="${p.product_link}" data-uom="${p.uom_code}" data-available="${p.qty_in_whse}" data-code="${p.product_code}">${p.product_desc} — Available: ${p.qty_in_whse} ${p.uom_code}</option>`;
    });

    const lineHtml = `
        <div class="product-row">
            <div class="product-main">
                <label class="field-label">Product</label>
                <select class="product-select">${optionsHtml}</select>
            </div>
            <div class="qty-wrapper">
                <label>Quantity</label>
                <input type="number" class="qty-input" min="1" placeholder="Qty">
                <span class="uom-label">Unit</span>
            </div>
            <div class="row-actions">
                <button type="button" class="icon-btn scan-btn" title="Optional: scan barcode">📷</button>
                <button type="button" class="icon-btn remove-line" title="Remove line">✕</button>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', lineHtml);
    const newLine = container.lastElementChild;
    const selectEl = newLine.querySelector('.product-select');
    const uomLabel = newLine.querySelector('.uom-label');

    // Use document.body as dropdown parent for better mobile behavior
    $(selectEl).select2({ 
        placeholder: "Select product", 
        allowClear: true, 
        width: '100%', 
        dropdownParent: document.body
    });

    // Update UOM label on selection (use data attributes)
    $(selectEl).on("select2:select", function () {
        const $sel = $(this).find(":selected");
        const uom = $sel.data("uom") || "";
        const uomCode = $sel.data("uomcode") || $sel.attr("data-uomcode") || ""; // fallback
        uomLabel.textContent = uom || uomCode || "";
    });
    $(selectEl).on("select2:clear", function () { uomLabel.textContent = ""; });

    newLine.querySelector(".remove-line").onclick = () => { $(selectEl).select2('destroy'); newLine.remove(); };
    newLine.querySelector(".scan-btn").onclick = () => scanProductIntoSelect(selectEl);
}

function step2Next() {
    lines = [];
    const allLines = document.querySelectorAll("#ibt-lines .product-row");
    if (allLines.length === 0) { Swal.fire("No Lines", "Add at least one product line.", "warning"); return; }

    for (let row of allLines) {
        const selectEl = row.querySelector(".product-select");
        const qtyInput = row.querySelector(".qty-input");
        if (!selectEl.value || !qtyInput.value || parseFloat(qtyInput.value) <= 0) {
            Swal.fire("Missing Input", "Please select product and enter quantity for all lines.", "warning"); return;
        }
        // product_link is stored as option.value; find in productsInWhse by product_link
        const product = productsInWhse.find(p => String(p.product_link) === String(selectEl.value));
        if (!product) {
            Swal.fire("Product Error", "Selected product not found in loaded warehouse list.", "error");
            return;
        }
        // push product_code too (frontend needs it for backend insert & for UI)
        lines.push({
            product_link: product.product_link,
            product_code: product.product_code,
            desc: product.product_desc,
            qty_in_whse: product.qty_in_whse,
            uom_id: product.uom_id,
            uom_code: product.uom_code,
            qty_to_issue: parseFloat(qtyInput.value)
        });
    }

    const box = document.getElementById("summary-box");
    box.innerHTML = `<p><strong>Warehouse:</strong> ${selectedWarehouse}</p><p><strong>Project:</strong> ${selectedProject}</p><p><strong>Issued To:</strong> ${issuedTo}</p><hr><h4>Products</h4>`;
    lines.forEach(l => { box.innerHTML += `<div class="line-row"><div>${l.desc}</div><div>Issue: ${l.qty_to_issue} ${l.uom_code}</div></div>`; });

    document.getElementById("step-2").classList.add("hidden");
    document.getElementById("step-3").classList.remove("hidden");
}

async function submitIssue() {
    if (lines.length === 0) { 
        Swal.fire("No Lines", "No product lines to submit.", "warning"); 
        return; 
    }

    // Ask about returns — use isConfirmed/isDenied pattern
    const result = await Swal.fire({
        title: 'Finalize Order',
        text: 'Could products be returned at a later time?',
        icon: 'question',
        showDenyButton: true,
        confirmButtonText: 'Yes, returns possible',
        denyButtonText: 'No, final issue only',
        reverseButtons: true,
        customClass: {
            confirmButton: 'btn-success',
            denyButton: 'btn-danger'
        }
    });

    // If user dismissed
    if (result.isDismissed) return;

    // backend expects order_final = true when final (no returns)
    const orderFinal = result.isDenied === true;

    const payload = { 
        warehouse: selectedWarehouse, 
        project: selectedProject, 
        issued_to: issuedTo, 
        order_final: orderFinal,            // correct field name
        lines: lines.map(l => ({ 
            product_link: l.product_link, 
            product_code: l.product_code,
            uom_id: l.uom_id,
            uom_code: l.uom_code,
            qty_to_issue: l.qty_to_issue 
        })) 
    };

    Swal.fire({ 
        title: "Submitting...", 
        text: "Please wait.", 
        allowOutsideClick: false, 
        didOpen: () => Swal.showLoading() 
    });
    
    try {
        const res = await fetch("/inventory/SDK/create_stock_issue", { 
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify(payload) 
        });
        const data = await res.json();

        if (res.ok && data.status === "success") {
            const message = orderFinal
                ? "Stock issue created! This is a final issue."
                : "Stock issue created! Returns are allowed.";
            Swal.fire("Success", message, "success").then(() => location.reload());
        } else {
            Swal.fire("Error", data.message || "Unknown error", "error");
        }
    } catch (err) {
        console.error("Submit error", err);
        Swal.fire("Error", "Failed to submit stock issue.", "error");
    }
}

async function scanProductIntoSelect(selectEl) {
    const scanner = document.getElementById("barcodeScanner");
    try {
        // This depends on your scanner implementation; keep as-is but handle returned structure
        const barcode = await scanner.open();
        if (!barcode) { Swal.fire("Scan Failed", "No barcode detected.", "warning"); return; }

        const res = await fetch("/inventory/SDK/fetch_product_by_barcode", { 
            method: "POST", 
            headers: { "Content-Type": "application/json" }, 
            body: JSON.stringify({ barcode: barcode, whse_link: selectedWarehouse }) 
        });
        const data = await res.json();
        // backend will return { product_code, product_link, uom_id, uom_code }
        if (!data || !data.product_code) { Swal.fire("Not Found", "No product found for this barcode.", "error"); return; }

        // find product in productsInWhse by product_link OR product_code
        const product = productsInWhse.find(p => String(p.product_code) === String(data.product_code) || String(p.product_link) === String(data.product_link));
        if (!product) { Swal.fire("Wrong Warehouse", "Product exists but not in this warehouse.", "error"); return; }

        // set select value to product_link (value is product_link in our options)
        $(selectEl).val(product.product_link).trigger("change");
        Swal.fire("Success", `Product selected: ${product.product_desc}`, "success");
    } catch (err) { 
        console.warn("Scan cancelled or failed:", err); 
    }
}
