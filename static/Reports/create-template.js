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
    { label: "Delivery Date", field: "deldate", totalType: "none" },
    { label: "DelNoteNo", field: "delnoteno", totalType: "none" },
    { label: "Transport Cost Exc", field: "deltransportcostexcl", totalType: "sum" },
    { label: "Agent", field: "agentname", totalType: "none" },
    { label: "Production Unit", field: "produnitname", totalType: "none" },
    { label: "Main Production Unit", field: "mainprodunitname", totalType: "none" },
    { label: "Transporter", field: "transportername", totalType: "none" },
    { label: "Transporter Type", field: "transporttype", totalType: "none" },
    { label: "Estimated Gross", field: "estimatedgross", totalType: "sum" },
    { label: "Estmtd Nett", field: "dellineestimatednett", totalType: "sum" },
    { label: "Total Qty Delivered", field: "dellinequantitybags", totalType: "sum" },
    { label: "Total Qty Sold", field: "totalqtysold", totalType: "sum" },
    { label: "Sold Gross", field: "salesgrossamnt", totalType: "sum" },
    { label: "Sold Nett", field: "salesnettamnt", totalType: "sum" },
    { label: "Qty Not Sold", field: "availableqtyforsale", totalType: "sum" },
    { label: "Total Qty Invoiced", field: "totalqtyinvoiced", totalType: "sum" },
    { label: "Invoiced Gross", field: "invoicedgrossamnt", totalType: "sum" },
    { label: "Invoiced Nett", field: "invoicednettamnt", totalType: "sum" },
    { label: "Destroyed Qty", field: "destroyedqty", totalType: "sum" },
    { label: "Destroyed Gross", field: "destroyedgrosssalesamnt", totalType: "sum" },
    { label: "Destroyed Nett", field: "destroyednettsalesamnt", totalType: "sum" },
    { label: "Weight Delivered", field: "weightkgdelivered", totalType: "sum" },
    { label: "Weight Sold", field: "weightkgsold", totalType: "sum" },
    { label: "Weight Invoiced", field: "weightkginvoiced", totalType: "sum" },
    { label: "Delivered Transport Cost", field: "deliveredtransportcost", totalType: "sum" },
    { label: "Delivered Packaging Cost", field: "deliveredpackagingcost", totalType: "sum" },
    { label: "Average Gross Sold", field: "salesgrossamnt / totalqtysold", totalType: "avg", weightField: "totalqtysold" },
    { label: "Average Nett Sold", field: "salesnettamnt / totalqtysold", totalType: "avg", weightField: "totalqtysold" },
    { label: "Gross Sold Price/10kg", field: "salesgrossamnt / weightkgsold * 10", totalType: "avg", weightField: "weightkgsold" },
    { label: "Nett Sold Price/10kg", field: "salesnettamnt / weightkgsold * 10", totalType: "avg", weightField: "weightkgsold * 10" },
    { label: "Sold After Transport", field: "salesnettamnt - soldtransportcost", totalType: "sum" },
    { label: "Sold After Transport/10kg", field: "(salesnettamnt - soldtransportcost) / weightkgsold * 10", totalType: "sum" },
    { label: "Invoiced After Transport", field: "invoicednettamnt - invoicedtransportcost", totalType: "sum" },
    { label: "Delivered/10kg", field: "weightkgdelivered / 10", totalType: "sum" },
    { label: "Sold/10kg", field: "weightkgsold / 10", totalType: "sum" },
    { label: "Not Sold/10kg", field: "(weightkgdelivered - weightkgsold) / 10", totalType: "sum" },
    { label: "Sold Transport", field: "soldtransportcost", totalType: "sum" },
    { label: "DeliveredTotalCost", field: "deliveredtransportcost + deliveredpackagingcost", totalType: "sum" }
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
            <select id="level-select" multiple style="width:100%; box-sizing:border-box;">
              ${LEVEL_OPTIONS.map(l => `<option value="${l.field}">${l.label}</option>`).join("")}
            </select>
          </div>
          <div class="container-card" style="padding:1rem;">
            <label style="font-weight:600; display:block; margin-bottom:0.5rem;">Fields (Columns)</label>
            <div id="field-list"></div>
            <button type="button" class="add-btn" style="margin-top:0.6rem; background:#007bff; color:white; border:none; padding:0.4rem 0.8rem; border-radius:4px; cursor:pointer; font-size:14px;">Add Field</button>
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
          placeholder: '-- Select Levels --',
          dropdownParent: document.querySelector('.swal2-container')
        });
        initializeSelect2('.field-select', {
          placeholder: '-- Select Field --',
          dropdownParent: document.querySelector('.swal2-container')
        });
        window.fieldList = document.getElementById("field-list");
        addFieldRow();
      },
      preConfirm: () => {
        const name = document.getElementById("template-name").value.trim();
        const levelValues = $('#level-select').val() || [];
        const levels = LEVEL_OPTIONS.filter(o => levelValues.includes(o.field));
        const fields = Array.from(document.querySelectorAll(".field-select"))
          .map(sel => FIELD_OPTIONS.find(o => o.field === $(sel).val()))
          .filter(Boolean);
  
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
  
  // Add Field Dropdown
  function addFieldRow() {
    const div = document.createElement("div");
    div.className = "field-item";
    div.style.marginBottom = "0.5rem";
    div.innerHTML = `
      <select class="field-select" style="width:100%; box-sizing:border-box;">
        <option value="">-- Select Field --</option>
        ${FIELD_OPTIONS.map(f => `<option value="${f.field}">${f.label}</option>`).join("")}
      </select>
    `;
    fieldList.appendChild(div);
    initializeSelect2(div.querySelector('.field-select'), {
      placeholder: '-- Select Field --',
      dropdownParent: document.querySelector('.swal2-container')
    });
  }