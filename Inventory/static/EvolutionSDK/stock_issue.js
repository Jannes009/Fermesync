let selectedWarehouse = null;
let selectedProject = null;
let issuedBy = null;
let productsInWhse = [];
let lines = [];

document.addEventListener("DOMContentLoaded", async () => {
    await loadWarehouses();
    await loadProjects();

    $("#warehouse-select").select2({ placeholder: "Select warehouse" });
    $("#project-select").select2({ placeholder: "Select project" });

    document.getElementById("step1-next").onclick = step1Next;
    document.getElementById("add-line").onclick = addLine;
    document.getElementById("step2-next").onclick = step2Next;
    document.getElementById("submit-issue").onclick = submitIssue;
    document.getElementById("back-to-step-1").onclick = () => {
        document.getElementById("step-2").classList.add("hidden");
        document.getElementById("step-1").classList.remove("hidden");
    }
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
    data.suppliers.forEach(wh => {
        whSelect.innerHTML += `<option value="${wh.code}">${wh.name}</option>`;
    });
}

async function loadProjects() {
    const res = await fetch("/inventory/fetch_projects", { method: "POST", headers: {"Content-Type": "application/json"} });
    const data = await res.json();
    const projSelect = document.getElementById("project-select");
    projSelect.innerHTML = `<option></option>`;
    data.prod_projects.forEach(p => {
        projSelect.innerHTML += `<option value="${p.code}">${p.name}</option>`;
    });
}

async function step1Next() {
    selectedWarehouse = $("#warehouse-select").val();
    selectedProject = $("#project-select").val();
    issuedBy = document.getElementById("issued-by").value.trim();

    if (!selectedWarehouse || !selectedProject || !issuedBy) {
        Swal.fire("Missing Information", "Please complete all fields.", "warning");
        return;
    }

    const res = await fetch("/inventory/fetch_products_in_whse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ whse_code: selectedWarehouse })
    });
    const data = await res.json();
    productsInWhse = data.products;

    if (!productsInWhse || productsInWhse.length === 0) {
        Swal.fire("No Products", "No products available in this warehouse.", "warning");
        return;
    }

    addLine();
    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
}

function addLine() {
    if (!productsInWhse || productsInWhse.length === 0) return;

    const container = document.getElementById("ibt-lines");
    let optionsHtml = '<option></option>';
    productsInWhse.forEach(p => {
        optionsHtml += `<option value="${p.product_id}" data-uom="${p.uom}" data-available="${p.qty_in_whse}">${p.product_desc} — Available: ${p.qty_in_whse} ${p.uom}</option>`;
    });

    const lineHtml = `
        <div class="product-row">
            <select class="product-select">${optionsHtml}</select>
            <div class="qty-wrapper">
                <input type="number" class="qty-input" min="1" placeholder="Qty">
                <span class="uom-label">Unit</span>
            </div>
            <button type="button" class="scan-btn" title="Optional: scan barcode">📷</button>
            <button type="button" class="remove-line" title="Remove line">✕</button>
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
        dropdownParent: document.body // Changed from container to document.body
    });

    $(selectEl).on("select2:select", function () {
        const uom = $(this).find(":selected").data("uom") || "";
        uomLabel.textContent = uom;
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
        const product = productsInWhse.find(p => p.product_id === selectEl.value);
        lines.push({ product_id: product.product_id, desc: product.product_desc, qty_in_whse: product.qty_in_whse, uom: product.uom, qty_to_issue: parseFloat(qtyInput.value) });
    }

    const box = document.getElementById("summary-box");
    box.innerHTML = `<p><strong>Warehouse:</strong> ${selectedWarehouse}</p><p><strong>Project:</strong> ${selectedProject}</p><p><strong>Issued By:</strong> ${issuedBy}</p><hr><h4>Products</h4>`;
    lines.forEach(l => { box.innerHTML += `<div class="line-row"><div>${l.desc}</div><div>Issue: ${l.qty_to_issue} ${l.uom}</div></div>`; });

    document.getElementById("step-2").classList.add("hidden");
    document.getElementById("step-3").classList.remove("hidden");
}

async function submitIssue() {
    if (lines.length === 0) { Swal.fire("No Lines", "No product lines to submit.", "warning"); return; }
    const payload = { warehouse: selectedWarehouse, project: selectedProject, issued_by: issuedBy, lines: lines.map(l => ({ product_id: l.product_id, qty_to_issue: l.qty_to_issue })) };

    Swal.fire({ title: "Submitting...", text: "Please wait.", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const res = await fetch("/inventory/SDK/submit_stock_issue", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload) });
    const data = await res.json();
    if (data.status === "success") Swal.fire("Success", "Stock issue submitted!", "success").then(() => location.reload());
    else Swal.fire("Error", data.message, "error");
}

async function scanProductIntoSelect(selectEl) {
    const scanner = document.getElementById("barcodeScanner");
    try {
        const barcode = await scanner.open();
        if (!barcode) { Swal.fire("Scan Failed", "No barcode detected.", "warning"); return; }
        const res = await fetch("/inventory/SDK/fetch_product_by_barcode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ barcode: barcode }) });
        const data = await res.json();
        if (!data || !data.product_id) { Swal.fire("Not Found", "No product found for this barcode.", "error"); return; }
        const product = productsInWhse.find(p => p.product_id == data.product_id);
        if (!product) { Swal.fire("Wrong Warehouse", "Product exists but not in this warehouse.", "error"); return; }
        $(selectEl).val(product.product_id).trigger("change");
        Swal.fire("Success", `Product selected: ${product.product_desc}`, "success");
    } catch (err) { console.warn("Scan cancelled or failed:", err); }
}
