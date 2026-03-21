let selectedWarehouse = null;
let selectedProject = null;
let selectedSpray = null;
let issueMode = "project"; // "project" or "spray"
let productsInWhse = [];
let projects = [];
let sprays = [];
let lines = [];
let lineIndex = 0;

function getUrlParams() {
  const params = {};
  window.location.search.replace(/^[?]/, '').split('&').forEach(pair => {
    if (!pair) return;
    const [key, value] = pair.split('=');
    params[decodeURIComponent(key)] = value ? decodeURIComponent(value) : '';
  });
  return params;
}

async function initializeFromUrl() {
  const params = getUrlParams();
  if (!params.spray_id) return;

  // Set spray mode and reload spray list
  document.getElementById('mode-spray').checked = true;
  handleModeChange();

  // Set selected spray after load
  const spraySelect = document.getElementById('spray-select');
  if (spraySelect.querySelector(`option[value="${params.spray_id}"]`)) {
    $(spraySelect).val(params.spray_id).trigger('change');
    selectedSpray = params.spray_id;
  }

  if (params.step === '2' || params.step === '3') {
    await step1Next();
    if (params.step === '3') {
      // Immediately show step 3 summary after validating step 2 lines
      document.getElementById('step-2').classList.add('hidden');
      document.getElementById('step-3').classList.remove('hidden');
    }
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadWarehouses();
  await loadProjects();
  await loadSprayInstructions();
  handleModeChange(); // Set initial visibility based on default mode

  $("#warehouse-select").select2({ placeholder: "Select warehouse", allowClear: true, width: '100%' });
  $("#project-select").select2({ placeholder: "Select project", allowClear: true, width: '100%' });
  $("#spray-select").select2({ placeholder: "Select spray instruction", allowClear: true, width: '100%' });

  // Event listeners
  document.querySelectorAll('input[name="issue-mode"]').forEach(radio => {
    radio.addEventListener("change", handleModeChange);
  });
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

  await initializeFromUrl();
});

function handleModeChange() {
    issueMode = document.querySelector('input[name="issue-mode"]:checked').value;
    const warehouseContainer = document.getElementById("warehouse-select-container");
    const projectContainer = document.getElementById("project-select-container");
    const sprayContainer = document.getElementById("spray-select-container");

    if (issueMode === "project") {
        warehouseContainer.style.display = "flex";
        projectContainer.style.display = "flex";
        sprayContainer.style.display = "none";
        document.getElementById("warehouse-select").focus();
    } else {
        warehouseContainer.style.display = "none";
        projectContainer.style.display = "none";
        sprayContainer.style.display = "flex";
        document.getElementById("spray-select").focus();
    }
}

async function loadWarehouses() {
    const warehouses = await fetch(`/inventory/fetch_warehouses`)
    .then(r => r.json())
    .then(d => d.warehouses);
    const select = document.getElementById('warehouse-select');
    select.innerHTML = '<option></option>';
    warehouses.forEach(w => select.insertAdjacentHTML('beforeend', `<option value="${w.id}">${w.name}</option>`));
}

async function loadProjects() {
  projects = await fetch(`/inventory/fetch_projects`)
    .then(r => r.json())
    .then(d => d.prod_projects);

  const select = document.getElementById('project-select');
  select.innerHTML = '<option></option>';
  projects.forEach(p => select.insertAdjacentHTML('beforeend', `<option value="${p.id}">${p.name}</option>`));
}

async function loadSprayInstructions() {
  try {
    sprays = await fetch(`/agri/fetch_spray_for_issue`)
      .then(r => r.json())
      .then(d => d.sprays || []);

    const select = document.getElementById('spray-select');
    select.innerHTML = '<option></option>';
    sprays.forEach(s => select.insertAdjacentHTML('beforeend', `<option value="${s.spray_id}" data-warehouse="${s.warehouse_id}">${s.spray_no} - ${s.description}</option>`));
  } catch (error) {
    console.error("Error loading spray instructions:", error);
    sprays = [];
  }
}

async function step1Next() {
    if (issueMode === "project") {
        selectedWarehouse = Number($("#warehouse-select").val());
        
        if (!selectedWarehouse) {
            Swal.fire("Missing Information", "Please select a warehouse.", "warning");
            return;
        }

        selectedProject = $("#project-select").val();
        if (!selectedProject) {
            Swal.fire("Missing Information", "Please select a project.", "warning");
            return;
        }
        productsInWhse = await fetch(`/inventory/SDK/fetch_products_in_warehouse?warehouse_id=${selectedWarehouse}`)
            .then(res => res.json())
            .then(d => d.products);

        if (!productsInWhse.length) {
            Swal.fire("No Products", "No products available in this warehouse.", "warning");
            return;
        }
    } else if (issueMode === "spray") {
        selectedSpray = $("#spray-select").val();
        if (!selectedSpray) {
            Swal.fire("Missing Information", "Please select a spray instruction.", "warning");
            return;
        }
        
        // Get warehouse from spray instruction data attribute
        const sprayOption = document.querySelector(`#spray-select option[value="${selectedSpray}"]`);
        console.log(sprayOption);
        selectedWarehouse = Number(sprayOption.getAttribute("data-warehouse"));
        
        if (selectedWarehouse === undefined || isNaN(selectedWarehouse)) {
            Swal.fire("Error", "Could not retrieve warehouse from spray instruction.", "error");
            return;
        }
        
        productsInWhse = await fetch(`/agri/fetch_products_for_spray?spray_id=${selectedSpray}`)
            .then(res => res.json())
            .then(d => d.products);
        if (!productsInWhse || !productsInWhse.length) {
            Swal.fire("No Products", "No products available for this spray instruction.", "warning");
            return;
        }
    }

    document.getElementById("ibt-lines").innerHTML = "";
    console.log("Products in warehouse:", productsInWhse);
    
    // If spray mode, auto-populate lines from spray
    if (issueMode === "spray") {
        await populateSprayLines();
    } else {
        addLine(); // For project mode, start with one empty line
    }

    document.getElementById("step-1").classList.add("hidden");
    document.getElementById("step-2").classList.remove("hidden");
}

async function populateSprayLines() {
    try {
        const response = await fetch(`/agri/fetch_spray_products?spray_id=${selectedSpray}`);
        const data = await response.json();
        const sprayLines = data.spray_products || [];
        
        // Create lines from spray
        sprayLines.forEach(sprayLine => {
            addLine();
            const row = document.querySelector("#ibt-lines .issue-line:last-child");
            const select = row.querySelector(".product-select");
            const qty = row.querySelector(".qty-input");
            const uomLabel = row.querySelector(".stock-unit");
            
            // Find the product in warehouse by stock_id
            const product = productsInWhse.find(p => p.product_link === sprayLine.stock_id);
            if (product) {
                $(select).val(sprayLine.stock_id).trigger("change");
                qty.value = sprayLine.total_qty;
                uomLabel.textContent = product.stocking_uom_code || "EA";
            }
        });
    } catch (error) {
        console.error("Error populating spray lines:", error);
        Swal.fire("Error", "Failed to populate lines from spray instruction.", "error");
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
        const opt = new Option(`${p.product_desc} (${p.qty_in_whse} ${p.stocking_uom_code} available)`, p.product_link, false, false);
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
      project: issueMode === "project" ? selectedProject : null
    });
  }

  const box = document.getElementById("summary-box");
  const sourceLabel = issueMode === "spray" ? "Spray Instruction" : "Project";
  const sourceValue = issueMode === "spray" ? selectedSpray : selectedProject;
  
  box.innerHTML = `<p><strong>Warehouse:</strong> ${selectedWarehouse}</p>
                   <p><strong>${sourceLabel}:</strong> ${sourceValue}</p>
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
      issue_mode: issueMode,
      project: issueMode === "project" ? selectedProject : null,
      spray_id: issueMode === "spray" ? selectedSpray : null,
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
    const issueNo = data.issue_no ? `Issue ${data.issue_no}` : `Issue #${data.issue_id}`;
    await Swal.fire("Success", `${issueNo} created`, "success");
    if (window.nextUrl) {
        window.location.href = window.nextUrl;
    } else {
        window.location.href = '/inventory/SDK/stock_issue_summary';
    }

}
