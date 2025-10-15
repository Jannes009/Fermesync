// ==========================
// Template Wizard (Single Modal)
// ==========================

const LEVEL_OPTIONS = [
  { label: "Delivery Date", field: "deldate" },
  { label: "DelNoteNo", field: "delnoteno" },
  { label: "Agent", field: "agentname" },
  { label: "Packhouse", field: "packhousename" },
  { label: "Production Unit", field: "produnitname" },
  { label: "Main Production Unit", field: "mainprodunitname" },
  { label: "Transporter", field: "transportername" },
  { label: "Product", field: "productdescription" }
];

const FIELD_OPTIONS = [
  // { label: "Delivery Date", field: "deldate", totalType: "none" },
  // { label: "DelNoteNo", field: "delnoteno", totalType: "none" },
  // { label: "Transport Cost Exc", field: "deltransportcostexcl", totalType: "sum" },
  // { label: "Agent", field: "agentname", totalType: "none" },
  // { label: "Production Unit", field: "produnitname", totalType: "none" },
  // { label: "Main Production Unit", field: "mainprodunitname", totalType: "none" },
  // { label: "Transporter", field: "transportername", totalType: "none" },
  // { label: "Transporter Type", field: "transporttype", totalType: "none" },
    { label: "Esttmtd Gross", field: "estimatedgross", totalType: "sum", valueType: "amount" },
    { label: "Estmtd Nett", field: "dellineestimatednett", totalType: "sum", valueType: "amount" },
    { label: "Qty Delivered", field: "dellinequantitybags", totalType: "sum", valueType: "quantity" },
    { label: "Qty Sold", field: "totalqtysold", totalType: "sum", valueType: "quantity" },
    { label: "Qty Not Sold", field: "availableqtyforsale", totalType: "sum", valueType: "quantity" },
    { label: "Qty Invoiced", field: "totalqtyinvoiced", totalType: "sum", valueType: "quantity" },
    { label: "Sold Gross", field: "salesgrossamnt", totalType: "sum", valueType: "amount" },
    { label: "Sold Nett", field: "salesnettamnt", totalType: "sum", valueType: "amount" },
    { label: "Invoiced Gross", field: "invoicedgrossamnt", totalType: "sum", valueType: "amount" },
    { label: "Invoiced Nett", field: "invoicednettamnt", totalType: "sum", valueType: "amount" },
    { label: "Destroyed Qty", field: "destroyedqty", totalType: "sum", valueType: "quantity" },
    { label: "Destroyed Gross", field: "destroyedgrosssalesamnt", totalType: "sum", valueType: "amount" },
    { label: "Destroyed Nett", field: "destroyednettsalesamnt", totalType: "sum", valueType: "amount" },
    { label: "Weight Delivered", field: "weightkgdelivered", totalType: "sum", valueType: "weight" },
    { label: "Weight Sold", field: "weightkgsold", totalType: "sum", valueType: "weight" },
    { label: "Weight Invoiced", field: "weightkginvoiced", totalType: "sum", valueType: "weight" },
    { label: "Delivered Transport Cost", field: "deliveredtransportcost", totalType: "sum", valueType: "amount" },
    { label: "Delivered Packaging Cost", field: "deliveredpackagingcost", totalType: "sum", valueType: "amount" },
    { label: "Average Gross Sold", field: "salesgrossamnt / totalqtysold", totalType: "avg", weightField: "totalqtysold", valueType: "amount" },
    { label: "Average Nett Sold", field: "salesnettamnt / totalqtysold", totalType: "avg", weightField: "totalqtysold", valueType: "amount" },
    { label: "Gross Sold Price/10kg", field: "salesgrossamnt / weightkgsold * 10", totalType: "avg", weightField: "weightkgsold", valueType: "amount" },
    { label: "Nett Sold Price/10kg", field: "salesnettamnt / weightkgsold * 10", totalType: "avg", weightField: "weightkgsold", valueType: "amount" },
    { label: "Sold After Transport", field: "salesnettamnt - soldtransportcost", totalType: "sum", valueType: "amount" },
    { label: "Sold After Transport/10kg", field: "(salesnettamnt - soldtransportcost) / weightkgsold * 10", totalType: "sum", valueType: "amount" },
    { label: "Invoiced After Transport", field: "invoicednettamnt - invoicedtransportcost", totalType: "sum", valueType: "amount" },
    { label: "Delivered/10kg", field: "weightkgdelivered / 10", totalType: "sum", valueType: "quantity" },
    { label: "Sold/10kg", field: "weightkgsold / 10", totalType: "sum", valueType: "quantity" },
    { label: "Not Sold/10kg", field: "(weightkgdelivered - weightkgsold) / 10", totalType: "sum", valueType: "quantity" },
    { label: "Sold Transport", field: "soldtransportcost", totalType: "sum", valueType: "amount" },
    { label: "DeliveredTotalCost", field: "deliveredtransportcost + deliveredpackagingcost", totalType: "sum", valueType: "amount" } 
];

// Initialize Select2
function initializeSelect2(selector, options = {}) {
  $(selector).select2({
    placeholder: options.placeholder || '-- Select --',
    allowClear: true,
    width: '100%',
    dropdownParent: options.dropdownParent || document.body,
    ...options
  });
}

// Template Wizard (Single Modal)
async function openTemplateWizard() {
  await Swal.fire({
    title: "Create Template",
    html: `
      <div class="swal-form" style="text-align:left; max-width:500px; margin:auto;">
        <div class="container-card" style="padding:1rem; margin-bottom:1rem;">
          <label style="font-weight:600; display:block; margin-bottom:0.5rem;">Template Name</label>
          <input id="template-name" class="swal2-input" placeholder="e.g. Products per Agent" style="width:100%; box-sizing:border-box; padding:0.5rem; margin:0;">
        </div>
        <div class="container-card" style="padding:1rem; margin-bottom:1rem;">
          <label style="font-weight:600; display:block; margin-bottom:0.5rem;">Levels (Rows)</label>
          <div id="selected-levels" style="margin-bottom:0.5rem;"></div>
          <select id="level-select" style="width:100%; box-sizing:border-box;">
            <option value="">-- Select Level --</option>
            ${LEVEL_OPTIONS.map(l => `<option value="${l.field}">${l.label}</option>`).join("")}
          </select>
        </div>
        <div class="container-card" style="padding:1rem;">
          <label style="font-weight:600; display:block; margin-bottom:0.5rem;">Fields (Columns)</label>
          <div id="selected-fields" style="margin-bottom:0.5rem;"></div>
          <select id="field-select" style="width:100%; box-sizing:border-box;">
            <option value="">-- Select Field --</option>
            ${FIELD_OPTIONS.map(f => `<option value="${f.field}">${f.label}</option>`).join("")}
          </select>
        </div>
      </div>
    `,
    showCancelButton: true,
    confirmButtonText: "Save Template",
    cancelButtonText: "Cancel",
    background: "var(--container-bg)",
    color: "var(--primary-text)",
    customClass: {
      popup: "container-card",
      confirmButton: "btn-primary"
    },
    didOpen: () => {
      initializeSelect2('#level-select', {
        placeholder: '-- Select Level --',
        dropdownParent: document.querySelector('.swal2-container')
      });
      initializeSelect2('#field-select', {
        placeholder: '-- Select Field --',
        dropdownParent: document.querySelector('.swal2-container')
      });

      const levelSelect = $('#level-select');
      const fieldSelect = $('#field-select');
      const selectedLevelsDiv = document.getElementById('selected-levels');
      const selectedFieldsDiv = document.getElementById('selected-fields');

      let selectedLevels = [];
      let selectedFields = [];

      // LEVELS SECTION
      levelSelect.on('change', function () {
        const selectedValue = this.value;
        if (!selectedValue) return;

        const option = LEVEL_OPTIONS.find(o => o.field === selectedValue);
        if (!option || selectedLevels.find(l => l.field === selectedValue)) {
          levelSelect.val('').trigger('change.select2');
          return;
        }

        selectedLevels.push(option);
        updateSelectedLevelsDisplay();
        levelSelect.val('').trigger('change.select2');
      });

      function updateSelectedLevelsDisplay() {
        selectedLevelsDiv.innerHTML = '';
        selectedLevels.forEach((level, index) => {
          const div = document.createElement('div');
          div.style.marginBottom = '0.3rem';
          div.style.fontWeight = '500';
          div.style.display = 'flex';
          div.style.alignItems = 'center';
          div.innerHTML = `
            <span>${index > 0 ? '↳ ' : ''}${level.label}</span>
            <button type="button" class="remove-level-btn" data-field="${level.field}" 
              style="margin-left:auto; background:none; border:none; color:#c00; cursor:pointer; font-size:14px;">
              ✖
            </button>
          `;
          selectedLevelsDiv.appendChild(div);
        });

        selectedLevelsDiv.querySelectorAll('.remove-level-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const field = btn.dataset.field;
            selectedLevels = selectedLevels.filter(l => l.field !== field);
            updateSelectedLevelsDisplay();
          });
        });
      }

      // FIELDS SECTION
      fieldSelect.on('change', function () {
        const selectedValue = this.value;
        if (!selectedValue) return;

        const option = FIELD_OPTIONS.find(o => o.field === selectedValue);
        if (!option || selectedFields.find(f => f.field === selectedValue)) {
          fieldSelect.val('').trigger('change.select2');
          return;
        }

        selectedFields.push(option);
        updateSelectedFieldsDisplay();
        fieldSelect.val('').trigger('change.select2');
      });

      function updateSelectedFieldsDisplay() {
        selectedFieldsDiv.innerHTML = '';
        selectedFields.forEach(field => {
          const div = document.createElement('div');
          div.style.marginBottom = '0.3rem';
          div.style.fontWeight = '500';
          div.style.display = 'flex';
          div.style.alignItems = 'center';
          div.innerHTML = `
            <span>${field.label}</span>
            <button type="button" class="remove-field-btn" data-field="${field.field}" 
              style="margin-left:auto; background:none; border:none; color:#c00; cursor:pointer; font-size:14px;">
              ✖
            </button>
          `;
          selectedFieldsDiv.appendChild(div);
        });

        selectedFieldsDiv.querySelectorAll('.remove-field-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const field = btn.dataset.field;
            selectedFields = selectedFields.filter(f => f.field !== field);
            updateSelectedFieldsDisplay();
          });
        });
      }

      window.getSelectedLevels = () => selectedLevels;
      window.getSelectedFields = () => selectedFields;
    },
    preConfirm: () => {
      const name = document.getElementById("template-name").value.trim();
      const levels = window.getSelectedLevels ? window.getSelectedLevels() : [];
      const fields = window.getSelectedFields ? window.getSelectedFields() : [];

      if (!name) {
        Swal.showValidationMessage("Please enter a template name.");
        return false;
      }
      if (!levels.length || !fields.length) {
        Swal.showValidationMessage("Please select at least one level and one field.");
        return false;
      }
      return { name, levels, fields };
    }
  }).then(async result => {
    if (result.value) {
      try {
        const response = await fetch('/save_template', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(result.value)
        });
        if (response.ok) {
          loadReportDropdownOptions();
          Swal.fire({
            title: "Template Saved",
            text: "Template stored on server.",
            icon: "success",
            background: "var(--container-bg)",
            customClass: { popup: "container-card" }
          });
        } else {
          Swal.fire({
            title: "Error",
            text: "Could not save template file.",
            icon: "error",
            background: "var(--container-bg)",
            customClass: { popup: "container-card" }
          });
        }
      } catch (err) {
        console.error(err);
        Swal.fire({
          title: "Error",
          text: "Failed to connect to backend.",
          icon: "error",
          background: "var(--container-bg)",
          customClass: { popup: "container-card" }
        });
      }
    }
  });
}
