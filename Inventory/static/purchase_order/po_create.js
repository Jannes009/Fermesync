
Warehouses = [];
Projects = [];
InventoryItems = [];


document.addEventListener("DOMContentLoaded", async () => {
  populateSupplierDropdown();

  document.getElementById("order-date").valueAsDate = new Date();
  document.getElementById("due-date").valueAsDate = new Date();

  [Warehouses, Projects, InventoryItems] = await Promise.all([
    fetchWarehouses(),
    fetchProjects(),
    fetchInventoryItems()
  ]);

  addLine();

  const first = document.querySelector(".udf-page");
  if (first) {
    first.style.display = "block";

    const firstTab = document.querySelector(".udf-tab");
    if (firstTab) firstTab.classList.add("active");
  }
});

async function fetchWarehouses() {
    return fetch("/inventory/fetch_warehouses")
        .then(res => res.json())
        .then(data => data.warehouses);
}

async function fetchProjects() {
    return fetch("/inventory/fetch_projects")
        .then(res => res.json())
        .then(data => data.prod_projects);
}

async function fetchInventoryItems() {
    return fetch("/inventory/fetch_distinct_products")
        .then(res => res.json())
        .then(data => data.products);
}
    // ---------------- SUPPLIERS ----------------
function populateSupplierDropdown() {
    const $supplier = $('#supplier');

    $supplier.select2({
        placeholder: "Loading suppliers...",
        allowClear: false,
        width: '100%'
    });

    fetch("/inventory/fetch_suppliers")
        .then(res => res.json())
        .then(data => {
            const sup = document.getElementById("supplier");
            sup.innerHTML = `<option value="" disabled selected>Select Supplier</option>`;
            data.suppliers.forEach(s => {
                sup.innerHTML += `<option value="${s.id}">${s.name}</option>`;
            });

            if ($(sup).data('select2')) $(sup).select2('destroy');
            $(sup).select2({
              width: '100%'
            });
        });
}
// -------------------------
// UDF Page Switching
// -------------------------
function showUdfPage(page) {
  // Hide ALL pages
  document.querySelectorAll(".udf-page").forEach(p => {
    p.style.display = "none";
  });

  // Show selected page
  const el = document.getElementById("udf-page-" + page);
  if (el) {
    el.style.display = "block";
  }

  // Tabs UI
  document.querySelectorAll(".udf-tab").forEach(t => t.classList.remove("active"));
  const activeTab = document.querySelector(`.udf-tab[onclick*="${page}"]`);
  if (activeTab) activeTab.classList.add("active");
}


// -------------------------
// Line handling
// -------------------------
function addLine() {
  if (!Projects.length || !Warehouses.length) {
    alert("Projects or Warehouses not loaded yet");
    return;
  }

  const tbody = document.querySelector("#po-lines tbody");
  const tr = document.createElement("tr");

  tr.innerHTML = `
    <td>
      <select name="inventory-item[]" class="inventory-item-select" required>
        <option value="" disabled selected>Select Inventory Item</option>
      </select>
    </td>
    <td>
      <select name="uom[]" class="uom-select" disabled>
        <option value="" disabled selected>Select UOM</option>
      </select>
    </td>
    <td>
      <select name="warehouse[]" class="warehouse-select" disabled>
        <option value="" disabled selected>Select Warehouse</option>
      </select>
    </td>
    <td><input type="number" step="0.01" name="qty[]" required></td>
    <td><input type="number" step="0.01" name="price[]" required></td>

    <td>
      <select name="project[]" class="project-select" required>
        <option value="" disabled selected>Select Project</option>
      </select>
    </td>

    ${LINE_UDFS.map(u =>
      `<td>${renderUdfInput(u, true)}</td>`
    ).join("")}

    <td>
      <button type="button"
              onclick="removeLine(this)"
              class="btn-icon danger">✖</button>
    </td>
  `;

  // Populate projects
  const projectSelect = tr.querySelector(".project-select");
  Projects.forEach(p => {
    projectSelect.insertAdjacentHTML(
      "beforeend",
      `<option value="${p.id}">${p.name}</option>`
    );
  });

    // Populate Invetory Items
  const inventroyItemSelect = tr.querySelector(".inventory-item-select");
  InventoryItems.forEach(i => {
    inventroyItemSelect.insertAdjacentHTML(
      "beforeend",
      `<option value="${i.product_link}">${i.product_code}-${i.product_desc}</option>`
    );
  });

  tbody.appendChild(tr);

  // Init Select2 AFTER adding to DOM
  $(projectSelect).select2({ width: '100%' });
  $(inventroyItemSelect).select2({ width: '100%' })
  .on('select2:select', e => initiateWarehouseAndUOM(e.params.data.id, tr));
  // $(warehouseSelect).select2({ width: '100%' });
}

async function initiateWarehouseAndUOM(product_link, tr) {

  const uomSelect = tr.querySelector(".uom-select");
  const warehouseSelect = tr.querySelector(".warehouse-select");

  // Reset
  uomSelect.innerHTML = `<option value="" disabled selected>Select UOM</option>`;
  warehouseSelect.innerHTML = `<option value="" disabled selected>Select Warehouse</option>`;
  uomSelect.disabled = true;
  warehouseSelect.disabled = true;

  if ($(uomSelect).data('select2')) $(uomSelect).select2('destroy');
  if ($(warehouseSelect).data('select2')) $(warehouseSelect).select2('destroy');

  const res = await fetch(
    `/inventory/fetch_item_uom_warehouse?product_link=${encodeURIComponent(product_link)}`
  );

  const data = await res.json();

  /* -------------------- UOM -------------------- */
  if (data.bUOMItem === 1 && data.uoms.length) {
    data.uoms.forEach(u => {
      uomSelect.insertAdjacentHTML(
        "beforeend",
        `<option value="${u.id}">${u.code}</option>`
      );
    });

    uomSelect.disabled = false;

    // Default Purchase UOM
    if (data.PurchaseUnitId) {
      uomSelect.value = data.PurchaseUnitId;
    }

    $(uomSelect).select2({ width: '100%' });
  }
  console.log(Warehouses)

  /* -------------------- WAREHOUSE -------------------- */
  if (data.WhseItem === 1) {
    Warehouses.forEach(w => {
      warehouseSelect.insertAdjacentHTML(
        "beforeend",
        `<option value="${w.id}">${w.name}</option>`
      );
    });

    warehouseSelect.disabled = false;
    $(warehouseSelect).select2({ width: '100%' });
  }
}

function removeLine(btn) {
  btn.closest("tr").remove();
}

async function saveRequisition() {
  const form = document.getElementById("po-form");

  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  if (!validateLines()) return;


  // Simple client-side validation
  if (!form.supplier.value) {
    alert("Supplier is required");
    return;
  }

  if (!document.querySelector("#po-lines tbody tr")) {
    alert("At least one line is required");
    return;
  }

  // 🔥 UDF validation (ALL pages)
  if (!validateAllUdfs()) {
    alert("Please complete all required User Defined Fields.");
    return;
  }

  const formData = new FormData(form);

  try {
    const res = await fetch("/inventory/po/requisition/save", {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || "Failed to save requisition");
    }

    alert(`Requisition saved (ID: ${data.id})`);

    // Optional: redirect to view page
    // window.location.href = `/inventory/po/requisition/${data.id}`;

  } catch (err) {
    console.error(err);
    alert("Error saving requisition");
  }
}

function validateLines() {
  const rows = document.querySelectorAll("#po-lines tbody tr");

  if (!rows.length) {
    alert("At least one line is required");
    return false;
  }

  for (const row of rows) {
    const item = row.querySelector(".inventory-item-select");
    const qty = row.querySelector("input[name='qty[]']");
    const price = row.querySelector("input[name='price[]']");

    const itemVal = $(item).val();
    const qtyVal = parseFloat(qty?.value);
    const priceVal = parseFloat(price?.value);

    if (!itemVal || !qtyVal || qtyVal <= 0 || !priceVal) {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      item?.focus();
      alert("All lines must have an item, price and quantity");
      return false;
    }
  }

  return true;
}

