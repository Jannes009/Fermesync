let ORIGINAL_STATE = null;

function snapshotForm() {
  const form = document.getElementById("po-form");

  const select2Values = {};
  form.querySelectorAll("select").forEach(sel => {
    if (sel.name) {
      select2Values[sel.name] = sel.value;
    }
  });

  ORIGINAL_STATE = {
    formData: Object.fromEntries(new FormData(form)),
    select2Values,
    linesHtml: document.querySelector("#po-lines tbody").innerHTML,
    udfsHtml: document.querySelector("#udf-container")?.innerHTML || ""
  };
}

async function restoreForm() {
  if (!ORIGINAL_STATE) return;

  const form = document.getElementById("po-form");

  // 1️⃣ Restore dynamic HTML
  document.querySelector("#po-lines tbody").innerHTML =
    ORIGINAL_STATE.linesHtml;

  if (document.querySelector("#udf-container")) {
    document.querySelector("#udf-container").innerHTML =
      ORIGINAL_STATE.udfsHtml;
  }

  // 2️⃣ Restore plain inputs
  Object.entries(ORIGINAL_STATE.formData).forEach(([name, value]) => {
    const el = form.elements[name];
    if (!el) return;

    if (el.type === "checkbox" || el.type === "radio") {
      el.checked = true;
    } else if (el.tagName !== "SELECT") {
      el.value = value;
    }
  });

  // 3️⃣ Re-init Select2
  $(".select2, .inventory-item-select, .project-select").each(function () {
    if ($(this).data("select2")) {
      $(this).select2("destroy");
    }
    $(this).select2({ width: "100%" });
  });

  // 4️⃣ Restore Select2 values AFTER init
  Object.entries(ORIGINAL_STATE.select2Values).forEach(([name, value]) => {
    const el = form.elements[name];
    if (!el || !value) return;

    $(el).val(value).trigger("change.select2");
  });
}

function lockForm() {
  document.querySelectorAll("input, select, textarea")
    .forEach(el => el.setAttribute("disabled", true));

  $(".select2-hidden-accessible").prop("disabled", true);

  document.querySelectorAll(
    "button[onclick='addLine()'], .btn-icon.danger"
  ).forEach(b => b.style.display = "none");
  let actions = "";
  if (STATUS === "PENDING APPROVAL" && PERMISSIONS.includes("PO_CREATE")) {
    actions = `<button class="btn btn-success" type="button" onclick="approve()">✔ Approve</button>
        <button class="btn btn-danger" type="button" onclick="reject()">✖ Reject</button>
        `;
  }
  if (STATUS === "PENDING APPROVAL" || STATUS === "POSTED" && PERMISSIONS.includes("PO_EDIT")) {
    actions += `<button class="btn btn-secondary" type="button" onclick="enableEdit()">✏ Edit</button>`;
  }

  document.querySelector(".actions").innerHTML = actions;
}

function unlockForm() {
  document.querySelectorAll("input, select, textarea")
    .forEach(el => el.removeAttribute("disabled"));

  $(".select2-hidden-accessible").prop("disabled", false);

  document.querySelectorAll(
    "button[onclick='addLine()'], .btn-icon.danger"
  ).forEach(b => b.style.display = "");

  document.querySelector(".actions").innerHTML = `
    <button class="btn btn-primary" type="button" onclick="saveRequisition()">💾 Save</button>
    <button class="btn btn-secondary" type="button" onclick="cancelEdit()">❌ Cancel</button>
  `;
}

async function approve() {
  if (!confirm("Approve this requisition and create the Purchase Order?")) {
    return;
  }

  try {
    const res = await fetch(
      `/inventory/po/requisition/${FORM_ID}/approve`,
      { method: "POST" }
    );

    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || "Approval failed");
    }

    alert(`Approved successfully.\nPO Number: ${data.order_no}`);
    location.reload();

  } catch (err) {
    console.error(err);
    alert(err.message || "Error approving requisition");
  }
}

async function reject() {
  const reason = prompt("Please provide a reason for rejection:");

  if (!reason || !reason.trim()) {
    alert("Rejection reason is required.");
    return;
  }

  try {
    const res = await fetch(
      `/inventory/api/po/requisition/${FORM_ID}/reject`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason })
      }
    );

    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || "Rejection failed");
    }

    alert("Requisition rejected.");
    location.reload();

  } catch (err) {
    console.error(err);
    alert(err.message || "Error rejecting requisition");
  }
}

async function returnForChanges() {
  const message = prompt(
    "Explain what changes are required before approval:"
  );

  if (!message || !message.trim()) {
    alert("A message is required.");
    return;
  }

  try {
    const res = await fetch(
      `/inventory/api/po/requisition/${FORM_ID}/return`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      }
    );

    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || "Return failed");
    }

    alert("Requisition returned to creator for changes.");
    location.reload();

  } catch (err) {
    console.error(err);
    alert(err.message || "Error returning requisition");
  }
}

async function processPurchaseOrder() {
  if (!confirm("Process this requisition into a Purchase Order?")) {
    return;
  }
  try {
    const res = await fetch(
      `/inventory/po/requisition/${FORM_ID}/process`,
      { method: "POST" }
    );
    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || "Processing failed");
    }
    alert(`Processed successfully.\nPO Number: ${data.po_number}`);
    location.reload();
  } catch (err) {
    console.error(err);
    alert(err.message || "Error processing requisition");
  }
}