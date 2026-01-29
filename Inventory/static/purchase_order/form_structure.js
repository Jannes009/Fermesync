Warehouses = [];
Projects = [];
InventoryItems = [];

async function loadFormStructure() {
    populateSupplierDropdown();

  document.getElementById("order-date").valueAsDate = new Date();
  document.getElementById("due-date").valueAsDate = new Date();

  [Warehouses, Projects, InventoryItems] = await Promise.all([
    fetchWarehouses(),
    fetchProjects(),
    fetchInventoryItems()
  ]);
  renderHeaderUdfs();
  addLine();

  const first = document.querySelector(".udf-page");
  if (first) {
    first.style.display = "block";

    const firstTab = document.querySelector(".udf-tab");
    if (firstTab) firstTab.classList.add("active");
  }
}

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
// Line handling
// -------------------------
function addLine() {
  if (!Projects.length || !Warehouses.length) {
    throw new Error("Projects or Warehouses not loaded yet");
  }

  const tbody = document.querySelector("#po-lines tbody");
  const tr = document.createElement("tr");
  const idx = crypto.randomUUID(); 
  tr.dataset.index = idx

  tr.innerHTML = `
    <td>
      <select name="lines[${idx}][product_id]" class="inventory-item-select" required>
        <option value="" disabled selected>Select Inventory Item</option>
      </select>
    </td>
    <td>
      <select  name="lines[${idx}][uom_id]" class="uom-select" disabled>
        <option value="" disabled selected>Select UOM</option>
      </select>
    </td>
    <td>
      <select name="lines[${idx}][warehouse_id]" class="warehouse-select" disabled>
        <option value="" disabled selected>Select Warehouse</option>
      </select>
    </td>
    <td><input type="number" step="0.01" name="lines[${idx}][qty]" required></td>
    <td name="lines[${idx}][qty_processed]">0</td>
    <td><input type="number" step="0.01" name="lines[${idx}][price]" class="line-price-input" required></td>

    <td>
      <select  name="lines[${idx}][project_id]" class="project-select" required>
        <option value="" disabled selected>Select Project</option>
      </select>
    </td>

    ${LINE_UDFS.map(u =>
      `<td>${renderUdfInput(u, true, idx)}</td>`
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
  const inventoryItemSelect = tr.querySelector(".inventory-item-select");
  InventoryItems.forEach(i => {
    inventoryItemSelect.insertAdjacentHTML(
      "beforeend",
      `<option value="${i.product_link}">${i.product_code}-${i.product_desc}</option>`
    );
  });

  tbody.appendChild(tr);

  // Init Select2 AFTER adding to DOM
  $(projectSelect).select2({ width: '100%' });
  $(inventoryItemSelect).select2({ width: '100%' })
    .on('select2:select', e => {
      if (!tr.dataset.hydrating) {
        initiateWarehouseAndUOM(e.params.data.id, tr);
      }
  });

  // $(warehouseSelect).select2({ width: '100%' });
  return tr;
}


function renderHeaderUdfs() {
  Object.entries(HEADER_UDFS).forEach(([page, fields]) => {
    const container = document.querySelector(
      `.udf-page[data-page="${page}"] .form-grid`
    );

    fields.forEach(f => {
      container.insertAdjacentHTML("beforeend", `
        <label>${f.label}${f.required ? " *" : ""}</label>
        ${renderUdfInput(f, false)}
      `);
    });
  });
}

function renderUdfInput(udf, isLine = false, idx = "") {
  const name = isLine
    ? `lines[${idx}][udf][${udf.name}]`
    : udf.name;

  const dataRequired = udf.required ? `data-required="1"` : "";
  const def = udf.default ?? "";

  const dataAttrs = `
    data-udf="1"
    data-udf-scope="${isLine ? "LINE" : "HEADER"}"
    data-udf-name="${udf.name}"
    ${isLine ? `data-line-key="${idx}"` : ""}
  `;

  switch (udf.type) {
    case 0: // String
      return `
        <input
          type="text"
          name="${name}"
          value="${def}"
          ${dataRequired}
          ${dataAttrs}
        >
      `;

    case 1: // Integer
      return `
        <input
          type="number"
          step="1"
          name="${name}"
          value="${def}"
          ${dataRequired}
          ${dataAttrs}
        >
      `;

    case 2: // Double
      return `
        <input
          type="number"
          step="0.01"
          name="${name}"
          value="${def}"
          ${dataRequired}
          ${dataAttrs}
        >
      `;

    case 3: // Date
      return `
        <input
          type="date"
          name="${name}"
          value="${def}"
          ${dataRequired}
          ${dataAttrs}
        >
      `;

    case 4: // Boolean
      return `
        <select
          name="${name}"
          ${dataRequired}
          ${dataAttrs}
        >
          <option value="">Select</option>
          <option value="1" ${def == 1 ? "selected" : ""}>Yes</option>
          <option value="0" ${def == 0 ? "selected" : ""}>No</option>
        </select>
      `;

    case 5: // Lookup
      const options = (udf.lookup || "")
        .split(";")
        .map(o => o.trim())
        .filter(Boolean);

      return `
        <select
          name="${name}"
          ${dataRequired}
          ${dataAttrs}
        >
          <option value="">Select</option>
          ${options.map(o =>
            `<option value="${o}" ${o === def ? "selected" : ""}>${o}</option>`
          ).join("")}
        </select>
      `;

    default:
      return `
        <input
          type="text"
          name="${name}"
          ${dataAttrs}
        >
      `;
  }
}
