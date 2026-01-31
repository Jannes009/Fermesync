import { db, fetchWithOffline } from '/main_static/offline/db.js?v=43';
import { fetchProducts, fetchIncompleteIssues } from './offline.js';
import { ensureStockAvailable } from "../stock_adjustment.js?v=1";

console.log(window.FERMESYNC.userId);
let selectedWarehouse = null;
let selectedProject = null;
let productsInWhse = [];
let lines = [];
let lineIndex = 0;

document.addEventListener("DOMContentLoaded", async () => {
  await loadWarehouses();
  await loadProjects();

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
});

async function loadWarehouses() {
    const warehouses = await db.warehouses.toArray();
    const select = document.getElementById('warehouse-select');
    select.innerHTML = '<option></option>';
    warehouses.forEach(w => select.insertAdjacentHTML('beforeend', `<option value="${w.code}">${w.name}</option>`));
}

async function loadProjects() {
  const projects = await db.projects.toArray();

  const select = document.getElementById('project-select');
  select.innerHTML = '<option></option>';
  projects.forEach(p => select.insertAdjacentHTML('beforeend', `<option value="${p.code}">${p.name}</option>`));
}

async function step1Next() {
    selectedWarehouse = $("#warehouse-select").val();
    selectedProject = $("#project-select").val();

    if (!selectedWarehouse || !selectedProject) {
        Swal.fire("Missing Information", "Please complete all fields.", "warning");
        return;
    }

    productsInWhse = await db.products
    .where('whse')
    .equals(selectedWarehouse)
    .and(p => (p.qty_in_whse ?? 0) > 0)
    .toArray();

    if (!productsInWhse.length) {
        Swal.fire("No Products", "No products available in this warehouse.", "warning");
        return;
    }

    document.getElementById("ibt-lines").innerHTML = "";
    addLine();
    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
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
            <input type="number" class="qty-input" min="0" step="1" placeholder="0" />
            <div class="uom-label stock-unit">—</div>
            <button type="button" class="issue-remove-btn" title="Remove line">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `;

    document.getElementById("ibt-lines").appendChild(lineDiv);

    // Remove button handler
    const removeBtn = lineDiv.querySelector('.issue-remove-btn');
    removeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        lineDiv.remove();
    });

    // Populate select2 dropdown
    populateProductSelect(selectId, lineDiv);
}

function populateProductSelect(selectId, lineDiv) {
    const select = document.getElementById(selectId);

    productsInWhse.forEach(p => {
        console.log(p)
        const opt = new Option(p.product_desc, p.product_link, false, false);
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

async function step2Next() {
  lines = [];
  const allLines = document.querySelectorAll("#ibt-lines .product-row");
  if (!allLines.length) { Swal.fire("No Lines", "Add at least one product line.", "warning"); return; }

  for (let row of allLines) {
    const selectEl = row.querySelector(".product-select");
    const selectedValue = $(selectEl).val();
    const qtyInput = row.querySelector(".qty-input");

    if (!selectedValue || !qtyInput.value || parseFloat(qtyInput.value) <= 0) {
      Swal.fire("Missing Input", "Please select product and enter quantity for all lines.", "warning");
      return;
    }

    const product = productsInWhse.find(p => String(p.product_link) === String(selectedValue));
    console.log(product, selectedValue);
    if (!product) { Swal.fire("Product Error", "Selected product not found.", "error"); return; }

    const qtyRequested = parseFloat(qtyInput.value);

    const ok = await ensureStockAvailable({
        product_link: product.product_link,
        whse: selectedWarehouse,
        qtyNeeded: qtyRequested,
        onUpdated: async () => {
            productsInWhse = await db.products
                .where("whse")
                .equals(selectedWarehouse)
                .toArray();
        }
    });

    if (!ok) return;


    lines.push({
      product_link: product.product_link,
      product_code: product.product_code,
      product_desc: product.product_desc,
      qty_in_whse: product.qty_in_whse,
      uom_id: product.stocking_uom_id,
      uom_code: product.stocking_uom_code,
      qty_issued: parseFloat(qtyInput.value)
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
  const clientIssueId = crypto.randomUUID();
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

  if (!navigator.onLine) {
    await offlineSubmit(clientIssueId, orderFinal);
    Swal.fire("Queued", "Issue queued to sync when online.", "info").then(() => location.reload());
    return;
  }
    console.log(lines)
    const res = await fetch("/inventory/SDK/create_stock_issue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
        warehouse: selectedWarehouse,
        project: selectedProject,
        order_final: orderFinal,
        created_at: new Date().toISOString(),
        lines: lines.map(l => ({
        product_link: l.product_link,
        product_code: l.product_code,
        uom_id: l.uom_id,
        uom_code: l.uom_code,
        qty_to_issue: l.qty_issued
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
    fetchProducts(); // Refresh local products
    fetchIncompleteIssues(); // Refresh incomplete issues
    await Swal.fire("Success", "Stock issue created", "success");
    location.reload();

}

async function offlineSubmit(clientIssueId, orderFinal) {
  await db.transaction("rw", db.offlineIssues, db.offlineIssueLines, db.products, db.outbox, async () => {
    // Store offline issue
    await db.offlineIssues.add({
      client_issue_id: clientIssueId,
      server_issue_id: null, // Will be filled later
      created_by_user_id: window.FERMESYNC.userId,
      warehouse: selectedWarehouse,
      project: selectedProject,
      status: "queued",
      allow_returns: !orderFinal,
      created_at: new Date().toISOString(),
      isReturned: orderFinal // Mark as returned if final issue
    });

    // Store lines with client ID only
    await db.offlineIssueLines.bulkAdd(lines.map(l => ({
      client_issue_id: clientIssueId,
      client_issue_line_id: crypto.randomUUID(),
      server_issue_line_id: null,
      product_link: l.product_link,
      product_code: l.product_code,
      product_desc: l.product_desc,
      qty_issued: l.qty_issued,
      uom_id: l.uom_id,
      uom_code: l.uom_code,
      created_at: new Date().toISOString()
    })));

    // Optimistic stock update
    for (const line of lines) {
        await db.products
        .where('[product_link+whse]')
        .equals([line.product_link, selectedWarehouse])
        .modify(p => { p.qty_in_whse = (p.qty_in_whse ?? 0) - line.qty_issued; });
    }

    await db.outbox.add({
      url: "/inventory/SDK/create_stock_issue",
      method: "POST",
      body: { 
        client_issue_id: clientIssueId, 
        warehouse: selectedWarehouse, 
        project: selectedProject, 
        order_final: orderFinal, 
        created_at: new Date().toISOString(),
        lines: lines.map(l => ({ 
          product_link: l.product_link, 
          product_code: l.product_code, 
          uom_id: l.uom_id, 
          uom_code: l.uom_code, 
          qty_to_issue: l.qty_issued 
        }))
      },
      created_at: new Date().toISOString(),
      retry_count: 0
    });
  });
}