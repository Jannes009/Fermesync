


document.addEventListener("DOMContentLoaded", async () => {
  await loadFormStructure();
  await applyMode();
});
function extractFormData() {
  const form = document.getElementById("po-form");

  // --------------------------------------------------
  // HEADER (non-UDF)
  // --------------------------------------------------
  const header = {
    supplier: form.supplier.value,
    order_date: form.order_date.value,
    due_date: form.due_date.value,
    description: form.description.value
  };

  // --------------------------------------------------
  // HEADER UDFS
  // --------------------------------------------------
  const header_udfs = {};

  form.querySelectorAll("[data-udf='1'][data-udf-scope='HEADER']").forEach(el => {
    if (!el.value) return;

    header_udfs[el.dataset.udfName] = el.value;
  });

  // --------------------------------------------------
  // LINES
  // --------------------------------------------------
  const lines = [];

  document.querySelectorAll("#po-lines tbody tr[data-index]").forEach(tr => {
    const idx = tr.dataset.index;

    const line = {
      product_id: tr.querySelector(`[name='lines[${idx}][product_id]']`)?.value || "",
      qty: tr.querySelector(`[name='lines[${idx}][qty]']`)?.value || "",
      price: tr.querySelector(`[name='lines[${idx}][price]']`)?.value || "",
      uom_id: tr.querySelector(`[name='lines[${idx}][uom_id]']`)?.value || "",
      warehouse_id: tr.querySelector(`[name='lines[${idx}][warehouse_id]']`)?.value || "",
      project_id: tr.querySelector(`[name='lines[${idx}][project_id]']`)?.value || "",
      udf: {}
    };

    // --------------------------------------------------
    // LINE UDFS (scoped to this row)
    // --------------------------------------------------
    tr.querySelectorAll("[data-udf='1'][data-udf-scope='LINE']").forEach(el => {
      if (!el.value) return;

      line.udf[el.dataset.udfName] = el.value;
    });

    lines.push(line);
  });

  return {
    header,
    header_udfs,
    lines
  };
}


async function saveRequisition(process = false) {
  const form = document.getElementById("po-form");

  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  if (!validateLines()) return;

  if (!warnZeroPrices()) return;

  if (!form.supplier.value) {
    alert("Supplier is required");
    return;
  }

  if (!document.querySelector("#po-lines tbody tr")) {
    alert("At least one line is required");
    return;
  }

  if (!validateAllUdfs()) {
    alert("Please complete all required User Defined Fields.");
    return;
  }

  const data = extractFormData();
  console.log(data);

  const isEdit = FORM_MODE === "edit";
  let url = "";
  if (STATUS === "POSTED") {
    url = `/inventory/po/purchase_order/${FORM_ID}/update`;
  } else if (isEdit) {
    url = `/inventory/po/requisition/${FORM_ID}/update`
  } else {
    url = `/inventory/po/requisition/save`;
  }
  try {
    const payload = {
      ...data,
      process: process
    };

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const result = await res.json();

    if (!result.success) {
      throw new Error(result.error || "Failed to save requisition");
    }

    alert(
      isEdit
        ? "Requisition updated successfully"
        : `Requisition saved (ID: ${result.id})`
    );

    window.location.href =
      `/inventory/po/requisition/${result.id || FORM_ID}`;

  } catch (err) {
    console.error(err);
    alert(err.message || "Error saving requisition");
  }
}

async function applyMode() {
  if (FORM_MODE === "create") return;

  await loadRequisition(FORM_ID);
  snapshotForm();

  lockForm();
}

function enableEdit() {
  FORM_MODE = "edit";
  unlockForm();
}

async function cancelEdit() {
  FORM_MODE = "view";
  location.reload();
  lockForm();
}

