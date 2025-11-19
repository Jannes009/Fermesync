/* ============================================================
   GLOBALS
============================================================ */
let selectedWarehouse = null;
let selectedProject = null;
let issuedBy = null;
let productsInWhse = [];
let lines = []; // multiple lines support

/* ============================================================
   STEP 1 – LOAD WAREHOUSES + PROJECTS
============================================================ */
document.addEventListener("DOMContentLoaded", async () => {
    await loadWarehouses();
    await loadProjects();

    $("#warehouse-select").select2({ placeholder: "Select warehouse" });
    $("#project-select").select2({ placeholder: "Select project" });

    document.getElementById("step1-next").onclick = step1Next;
    document.getElementById("add-line").onclick = addLine;
    document.getElementById("step2-next").onclick = step2Next;
    document.getElementById("submit-issue").onclick = submitIssue;
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
    const res = await fetch("/inventory/fetch_projects", {
        method: "POST",
        headers: {"Content-Type": "application/json"}
    });
    const data = await res.json();
    const projSelect = document.getElementById("project-select");
    projSelect.innerHTML = `<option></option>`;
    data.prod_projects.forEach(p => {
        projSelect.innerHTML += `<option value="${p.code}">${p.name}</option>`;
    });
}

/* ============================================================
   STEP 1 → STEP 2
============================================================ */
async function step1Next() {
    selectedWarehouse = $("#warehouse-select").val();
    selectedProject = $("#project-select").val();
    issuedBy = document.getElementById("issued-by").value.trim();

    if (!selectedWarehouse || !selectedProject || !issuedBy) {
        Swal.fire("Missing Information", "Please complete all fields.", "warning");
        return;
    }

    // Load products for warehouse
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

    addLine(); // Add first line automatically
    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
}
/* ============================================================
   ADD LINE USING HTML STRING
============================================================ */
function addLine() {
    if (!productsInWhse || productsInWhse.length === 0) {
        Swal.fire("No Products", "No products available in this warehouse.", "warning");
        return;
    }

    const container = document.getElementById("ibt-lines");

    // Build options for select
    let optionsHtml = '<option></option>'; // placeholder
    productsInWhse.forEach(p => {
        optionsHtml += `<option value="${p.product_id}">${p.product_desc} — Available: ${p.qty_in_whse} ${p.uom}</option>`;
    });

    // Build line HTML
    const lineHtml = `
        <div class="line-row">
            <select class="product-select" style="width:300px;">${optionsHtml}</select>
            <input type="number" class="issue-qty" min="1" placeholder="Qty">
            <button type="button" class="btn-secondary remove-line">Remove</button>
        </div>
    `;

    // Append line to container
    container.insertAdjacentHTML('beforeend', lineHtml);

    // Initialize Select2 for the new select
    const newLine = container.lastElementChild;
    const selectEl = newLine.querySelector('.product-select');
    $(selectEl).select2({
        placeholder: "Select a product",
        allowClear: true,
        width: '300px',
        dropdownParent: container
    });

    // Add remove functionality
    const removeBtn = newLine.querySelector(".remove-line");
    removeBtn.onclick = () => {
        $(selectEl).select2('destroy'); // destroy Select2 before removing
        newLine.remove();
    };
}


/* ============================================================
   STEP 2 → STEP 3
============================================================ */
function step2Next() {
    lines = []; // reset lines
    const allLines = document.querySelectorAll("#ibt-lines .line-row:not(.template-line)");
    if (allLines.length === 0) {
        Swal.fire("No Lines", "Add at least one product line.", "warning");
        return;
    }

    for (let row of allLines) {
        const selectEl = row.querySelector(".product-select");
        const qtyInput = row.querySelector(".issue-qty");
        if (!selectEl.value || !qtyInput.value || parseFloat(qtyInput.value) <= 0) {
            Swal.fire("Missing Input", "Please select product and enter quantity for all lines.", "warning");
            return;
        }
        const product = productsInWhse.find(p => p.product_id === selectEl.value);
        lines.push({
            product_id: product.product_id,
            desc: product.product_desc,
            qty_in_whse: product.qty_in_whse,
            uom: product.uom,
            qty_to_issue: parseFloat(qtyInput.value)
        });
    }

    // Render summary
    const box = document.getElementById("summary-box");
    box.innerHTML = `
        <p><strong>Warehouse:</strong> ${selectedWarehouse}</p>
        <p><strong>Project:</strong> ${selectedProject}</p>
        <p><strong>Issued By:</strong> ${issuedBy}</p>
        <hr><h4>Products</h4>
    `;
    lines.forEach(l => {
        box.innerHTML += `
            <div class="line-row">
                <div>${l.desc}</div>
                <div>Issue: ${l.qty_to_issue} ${l.uom}</div>
            </div>
        `;
    });

    document.getElementById("step-2").classList.add("hidden");
    document.getElementById("step-3").classList.remove("hidden");
}

/* ============================================================
   SUBMIT
============================================================ */
async function submitIssue() {
    if (lines.length === 0) {
        Swal.fire("No Lines", "No product lines to submit.", "warning");
        return;
    }

    const payload = {
        warehouse: selectedWarehouse,
        project: selectedProject,
        issued_by: issuedBy,
        lines: lines.map(l => ({
            product_id: l.product_id,
            qty_to_issue: l.qty_to_issue
        }))
    };

    Swal.fire({
        title: "Submitting...",
        text: "Please wait.",
        allowOutsideClick: false,
        didOpen: () => Swal.showLoading()
    });

    const res = await fetch("/inventory/SDK/submit_stock_issue", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status === "success") {
        Swal.fire("Success", "Stock issue submitted!", "success").then(() => location.reload());
    } else {
        Swal.fire("Error", data.message, "error");
    }
}
