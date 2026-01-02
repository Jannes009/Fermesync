window.addEventListener("DOMContentLoaded", () => {
  renderHeaderUdfs();
});

document.addEventListener("input", e => {
  if (e.target.classList.contains("udf-error")) {
    e.target.classList.remove("udf-error");
  }
});


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


function renderUdfInput(udf, isLine = false) {
  const name = isLine ? `${udf.name}[]` : udf.name;
  const dataRequired = udf.required ? `data-required="1"` : "";
  const def = udf.default ?? "";

  switch (udf.type) {
    case 0: // String
      return `<input type="text" name="${name}" value="${def}" ${dataRequired}>`;

    case 1: // Integer
      return `<input type="number" step="1" name="${name}" value="${def}" ${dataRequired}>`;

    case 2: // Double
      return `<input type="number" step="0.01" name="${name}" value="${def}" ${dataRequired}>`;

    case 3: // Date
      return `<input type="date" name="${name}" value="${def}" ${dataRequired}>`;

    case 4: // Boolean
      return `
        <select name="${name}" ${dataRequired}>
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
        <select name="${name}" ${dataRequired}>
          <option value="">Select</option>
          ${options.map(o =>
            `<option value="${o}" ${o === def ? "selected" : ""}>${o}</option>`
          ).join("")}
        </select>
      `;

    default:
      return `<input type="text" name="${name}">`;
  }
}

function validateAllUdfs() {
  const requiredFields = document.querySelectorAll("[data-required='1']");

  for (const field of requiredFields) {
    if (!field.value || field.value.trim() === "") {
      const udfPage = field.closest(".udf-page");
      if (!udfPage) continue;

      // Switch to correct page
      const page = udfPage.dataset.page;
      showUdfPage(page);

      // Scroll nicely
      setTimeout(() => {
        field.scrollIntoView({ behavior: "smooth", block: "center" });
        field.focus();
        field.classList.add("udf-error");
      }, 50);

      return false;
    }
  }

  return true;
}
