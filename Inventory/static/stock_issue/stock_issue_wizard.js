let selectedWarehouse = null;
let selectedProject = null;
let productsInWhse = [];
let projects = [];
let lines = [];
let lineIndex = 0;

document.addEventListener("DOMContentLoaded", async () => {
  await loadWarehouses();
  await loadProjects();
  loadPrefill();

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
  document.getElementById("back-to-step-2").onclick = () => {
    document.getElementById("step-3").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
  };
  document.getElementById("project-per-line").addEventListener("change", function () {

    const enabled = this.checked;

    document.querySelectorAll(".line-project-wrapper").forEach(el => {
        el.classList.toggle("hidden", !enabled);
    });

});
});

function loadPrefill() {

    const params = new URLSearchParams(window.location.search);

    const warehouse = params.get("warehouse");
    const project = params.get("project");
    const lines = params.get("lines");

    if (warehouse) {
        selectedWarehouse = Number(warehouse);
        $("#warehouse-select").val(warehouse).trigger("change");
    }

    if (project) {
        selectedProject = project;
        $("#project-select").val(project).trigger("change");
    }

    if (lines) {
        window.prefillLines = JSON.parse(lines);
    }
    if (warehouse && project && lines) {
        step1Next();
    }

}

async function loadWarehouses() {
    const warehouses = await fetch(`/inventory/fetch_warehouses`)
    .then(r => r.json())
    .then(d => d.warehouses);
    console.log("Warehouses", warehouses);
    const select = document.getElementById('warehouse-select');
    select.innerHTML = '<option></option>';
    warehouses.forEach(w => select.insertAdjacentHTML('beforeend', `<option value="${w.id}">${w.name}</option>`));
}

async function loadProjects() {
  projects = await fetch(`/inventory/fetch_projects`)
    .then(r => r.json())
    .then(d => d.prod_projects);
    console.log("Projects", projects);

  const select = document.getElementById('project-select');
  select.innerHTML = '<option></option>';
  projects.forEach(p => select.insertAdjacentHTML('beforeend', `<option value="${p.id}">${p.name}</option>`));
}

async function step1Next() {
    selectedWarehouse = Number($("#warehouse-select").val());
    selectedProject = $("#project-select").val();

    if (!selectedWarehouse || !selectedProject) {
        Swal.fire("Missing Information", "Please complete all fields.", "warning");
        return;
    }

    productsInWhse = await fetch(`/inventory/SDK/fetch_products_in_warehouse?warehouse_id=${selectedWarehouse}`)
        .then(res => res.json())
        .then(d => d.products);
    console.log("Products in selected warehouse", productsInWhse);

    if (!productsInWhse.length) {
        Swal.fire("No Products", "No products available in this warehouse.", "warning");
        return;
    }

    document.getElementById("ibt-lines").innerHTML = "";
    addLine();
    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
    if (window.prefillLines) {

    document.getElementById("ibt-lines").innerHTML = "";

    window.prefillLines.forEach(l => {
        addLine();

        const row = document.querySelector("#ibt-lines .issue-line:last-child");

        const select = row.querySelector(".product-select");
        const qty = row.querySelector(".qty-input");

        $(select).val(l.product_link).trigger("change");
        qty.value = l.qty;
    });

}
}

function addLine() {
    lineIndex++;
    const lineId = `issue-line-${lineIndex}`;
    const selectId = `product-select-${lineIndex}`;


    const lineDiv = document.createElement("div");
    lineDiv.className = "issue-line";
    lineDiv.id = lineId;

    lineDiv.innerHTML = `
    <div class="product-row">

        <div class="product-select-wrapper">
            <select id="${selectId}" class="product-select">
                <option></option>
            </select>
        </div>

        <div class="product-row-bottom">

            <input type="number" class="qty-input" min="0" step="1" placeholder="Qty"/>

            <div class="uom-label stock-unit">—</div>

            <button type="button" class="issue-remove-btn" title="Remove line">
                <i class="fas fa-trash"></i>
            </button>

        </div>

        <div class="line-project-wrapper hidden">
            <select class="line-project-select">
                <option></option>
            </select>
        </div>

    </div>
    `;

    document.getElementById("ibt-lines").appendChild(lineDiv);

    const projectSelect = lineDiv.querySelector(".line-project-select");
    populateLineProjects(projectSelect);

    // Remove button handler
    const removeBtn = lineDiv.querySelector('.issue-remove-btn');
    removeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        lineDiv.remove();
    });

    // Populate select2 dropdown
    populateProductSelect(selectId, lineDiv);
    if (document.getElementById("project-per-line").checked) {
    lineDiv.querySelector(".line-project-wrapper").classList.remove("hidden");
}
}

function populateProductSelect(selectId, lineDiv) {
    const select = document.getElementById(selectId);

    productsInWhse.forEach(p => {
        console.log(p)
        const opt = new Option(`${p.product_desc} (${p.qty_in_whse} ${p.stocking_uom_code})`, p.product_link, false, false);
        const uom = p.stocking_uom_code || "EA";
        $(opt).data("unit", uom);
        $(opt).data("qty", p.qty_in_whse);
        select.appendChild(opt);
    });

    $(`#${selectId}`).select2({
        placeholder: "Search and select a product...",
        allowClear: true,
        width: "100%",
        dropdownParent: document.body
    });

    // When a product is chosen → update the stocking unit
    $(`#${selectId}`).on("select2:select", function (e) {
        const selected = $(this).find(":selected").data();
        const uom = selected.unit || "EA";
        lineDiv.querySelector(".stock-unit").textContent = uom;
    });

    // When a product is cleared
    $(`#${selectId}`).on("select2:clear", function () {
        lineDiv.querySelector(".stock-unit").textContent = "—";
    });
}

async function populateLineProjects(selectEl) {

    projects.forEach(p => {
        const opt = new Option(p.name, p.id, false, false);
        selectEl.appendChild(opt);
    });

    $(selectEl).select2({
        placeholder: "Project",
        allowClear: true,
        width: "100%",
        dropdownParent: document.body
    });

    // set default
    if (selectedProject) {
        $(selectEl).val(selectedProject).trigger("change");
    }
}

async function step2Next() {
  lines = [];
  const allLines = document.querySelectorAll("#ibt-lines .product-row");
  if (!allLines.length) { Swal.fire("No Lines", "Add at least one product line.", "warning"); return; }

  for (let row of allLines) {
    const selectEl = row.querySelector(".product-select");
    const selectedValue = $(selectEl).val();
    const qtyInput = row.querySelector(".qty-input");
    const lineProjectSelect = row.querySelector(".line-project-select");
    const lineProject = $(lineProjectSelect).val();

    if (!selectedValue || !qtyInput.value || parseFloat(qtyInput.value) <= 0) {
      Swal.fire("Missing Input", "Please select product and enter quantity for all lines.", "warning");
      return;
    }

    const product = productsInWhse.find(p => String(p.product_link) === String(selectedValue));
    console.log(product, selectedValue);
    if (!product) { Swal.fire("Product Error", "Selected product not found.", "error"); return; }

    const qtyRequested = parseFloat(qtyInput.value);

    if (qtyRequested > product.qty_in_whse) {
      Swal.fire("Insufficient Stock", `Requested quantity for ${product.product_desc} exceeds available stock (${product.qty_in_whse}).`, "error");
      return;
    }


    lines.push({
      product_link: product.product_link,
      product_code: product.product_code,
      product_desc: product.product_desc,
      qty_in_whse: product.qty_in_whse,
      uom_id: product.stocking_uom_id,
      uom_code: product.stocking_uom_code,
      qty_issued: qtyRequested,
      project: lineProject || selectedProject
    });
  }

  const box = document.getElementById("summary-box");
  box.innerHTML = `<p><strong>Warehouse:</strong> ${selectedWarehouse}</p>
                   <p><strong>Project:</strong> ${selectedProject}</p>
                   <hr><h4>Products</h4>`;
  lines.forEach(l => box.innerHTML += `<div class="line-row"><div>${l.product_desc}</div><div>Issue: ${l.qty_issued} ${l.uom_code}</div></div>`);

  document.getElementById("step-2").classList.add("hidden");
  document.getElementById("step-3").classList.remove("hidden");
}

async function submitIssue() {
  // const clientIssueId = crypto.randomUUID();
  const result = await Swal.fire({
    title: 'Finalize Order',
    text: 'Could products be returned later?',
    icon: 'question',
    showDenyButton: true,
    confirmButtonText: 'Yes, returns possible',
    denyButtonText: 'No, final issue only',
    reverseButtons: true,
    customClass: { confirmButton: 'btn-success', denyButton: 'btn-danger' }
  });
  if (result.isDismissed) return;
  const orderFinal = result.isDenied === true;

  const res = await fetch("/inventory/SDK/create_stock_issue", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
      warehouse: selectedWarehouse,
      order_final: orderFinal,
      created_at: new Date().toISOString(),
      lines: lines.map(l => ({
        product_link: l.product_link,
        product_code: l.product_code,
        uom_id: l.uom_id,
        uom_code: l.uom_code,
        qty_to_issue: l.qty_issued,
        project: l.project
      }))
    })
    });

    const data = await res.json();

    if (!res.ok || data.status !== "success") {
    await Swal.fire(
        "Error",
        data.message || "Stock issue failed",
        "error"
    );
    return;
    }
    // fetchProducts(); // Refresh local products
    // fetchIncompleteIssues(); // Refresh incomplete issues
    await Swal.fire("Success", "Stock issue created", "success");
    window.location.href = '/inventory/SDK/stock_issue_summary';

}
