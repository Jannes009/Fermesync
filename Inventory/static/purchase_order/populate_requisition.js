async function fetchRequisitionData(requisitionId) {
    if (FORM_MODE != "view") return;
  const res = await fetch(`/inventory/api/po/requisition/${requisitionId}`);
    if (!res.ok) {
    throw new Error("Failed to fetch requisition data");
    }
    const result = await res.json();
    return {"header": result.header, "header_udfs": result.header_udfs, "lines": result.lines, "line_udfs": result.line_udfs};
}

async function fetchPurchaseOrderData(purchaseOrderId) {
  if (FORM_MODE != "view") return;
  const res = await fetch(`/inventory/api/po/${purchaseOrderId}`);
  if (!res.ok) {
  throw new Error("Failed to fetch purchase order data");
  }
  const result = await res.json();
  return {"header": result.header, "header_udfs": result.header_udfs, "lines": result.lines, "line_udfs": result.line_udfs};
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toISOString().split('T')[0];
}

async function loadRequisition(document_id) {
    let data;
    if (FORM_MODE != "view") return;
    if (STATUS === "POSTED") {
        data = await fetchPurchaseOrderData(document_id);
    } else if (STATUS === "PENDING APPROVAL" || STATUS === "DRAFT") {
        data = await fetchRequisitionData(document_id);
    }
    console.log(data);
    populateHeader(data.header);
    populateHeaderUdfs(data.header_udfs);
    await populateLines(data.lines, data.line_udfs);
}

function populateHeader(header) {
  document.getElementById("supplier").value = header.SupplierId;
  $("#supplier").trigger("change");
  console.log(header.OrderDate);
  document.getElementById("order-date").value =
    formatDate(header.OrderDate);

  document.getElementById("due-date").value =
    formatDate(header.DueDate);

  document.querySelector("input[name='description']").value =
    header.Description || "";
}

function populateHeaderUdfs(header_udfs) {
  for (const [key, value] of Object.entries(header_udfs)) {
    console.log(key, value);
    if (!key.includes("IDPOrd")) continue;

    const field = document.querySelector(`[name="${key}"]`);
    if (!field) continue;

    field.value = value ?? "";
  }
}

async function populateLines(lines, lineUdfs) {
  const tbody = document.querySelector("#po-lines tbody");
  tbody.innerHTML = "";
  for (const line of lines) {
    const tr = addLine();
    if (!tr) return;
    console.log(lineUdfs, lineUdfs[line.LineId])
    await hydrateLine(tr, line, lineUdfs[line.LineId]);

  }
}

async function hydrateLine(tr, line, lineUdfsForThisLine = {}) {
  const key = tr.dataset.index;

  const itemSelect = tr.querySelector(
    `select[name="lines[${key}][product_id]"]`
  );
  const qtyInput = tr.querySelector(
    `input[name="lines[${key}][qty]"]`
  );
  const priceInput = tr.querySelector(
    `input[name="lines[${key}][price]"]`
  );
  const projectSelect = tr.querySelector(
    `select[name="lines[${key}][project_id]"]`
  );
  const qtyProcessed = tr.querySelector(
    `td[name="lines[${key}][qty_processed]"]`
  );

  tr.dataset.hydrating = "1";

  itemSelect.value = line.ProductId;
  $(itemSelect).trigger("change.select2");

  await initiateWarehouseAndUOM(line.ProductId, tr, pricePopulated = true);

  delete tr.dataset.hydrating;

  qtyInput.value = line.Quantity;
  qtyProcessed.textContent = line.QtyProcessed > 0 ? line.QtyProcessed : "0";
  console.log(line.QtyProcessed, qtyProcessed.textContent);
  priceInput.value = line.Price;

  if (line.ProjectId) {
    projectSelect.value = line.ProjectId;
    $(projectSelect).trigger("change");
  }

  const uomSelect = tr.querySelector(
    `select[name="lines[${key}][uom_id]"]`
  );
  if (line.UomId && uomSelect) {
    tr.dataset.settingUom = "1";
    uomSelect.value = line.UomId;
    $(uomSelect).trigger("change");
    delete tr.dataset.settingUom;
  }

  const warehouseSelect = tr.querySelector(
    `select[name="lines[${key}][warehouse_id]"]`
  );
  if (line.WarehouseId && warehouseSelect) {
    warehouseSelect.value = line.WarehouseId;
    $(warehouseSelect).trigger("change");
  }

  hydrateLineUdfs(tr, lineUdfsForThisLine);
}


function hydrateLineUdfs(tr, udfMap = {}) {
  const key = tr.dataset.index;
  Object.entries(udfMap).forEach(([udfName, value]) => {
    const input = tr.querySelector(
      `[name="lines[${key}][udf][${udfName}]"]`
    );
    if (input) input.value = value ?? "";
  });
}
