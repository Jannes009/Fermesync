document.addEventListener('DOMContentLoaded', function() {
  fetchSalesData();
});

let consignmentMap = {};

function fetchSalesData() {
  fetch('/api/sales')
    .then(response => response.json())
    .then(data => {
      const container = document.getElementById('salesContainer');
      container.innerHTML = '';
      data.forEach(delnote => {
        const card = createSalesCard(delnote);
        container.appendChild(card);
      });
    })
    .catch(error => console.error('Error fetching sales data:', error));

  // Fetch consignments for all delivery notes for modal use
  fetch('/api/consignments')
    .then(response => response.json())
    .then(data => {
      consignmentMap = data; // { DelNoteNo: [consignment, ...] }
    });
}

function createSalesCard(delnote) {
  const card = document.createElement('div');
  card.className = 'sales-card';
  card.innerHTML = `
    <div class="sales-header">
      <div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.7em;">
        <span class="sales-header-title">Delivery Note <a href="/delivery-note/${delnote.delnote_no}" style="color:#1d4ed8;text-decoration:none;">#${delnote.delnote_no}</a></span>
        <span class="sales-header-meta">Agent: <strong>${delnote.agent}</strong> | Date: <span>${delnote.del_date}</span></span>
        <span class="sales-header-badge" style="margin-right:0.5rem;cursor:pointer;" onclick="showLinkedModal('${delnote.delnote_no}')">
            Linked: ${delnote.linked_count}
        </span>
        <span class="sales-header-badge matched-badge" style="cursor:pointer;" onclick="showMatchedModal('${delnote.delnote_no}')">Matched: ${delnote.matched_count} line${delnote.matched_count !== 1 ? 's' : ''}</span>
      </div>
      <div class="sales-header-actions">
        <button class="sales-btn" onclick="addSale('${delnote.delnote_no}')">Add Sale</button>
      </div>
    </div>
    <div class="table-responsive">
      <table class="sales-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Product</th>
            <th>Qty</th>
            <th>Price</th>
            <th>Discount</th>
            <th>Gross</th>
            <th>Auto Sale</th>
            <th>Net</th>
            <th>Invoice No</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${delnote.lines.map((line, idx) => `
            <tr id="row-${delnote.delnote_no}-${idx}">
              <td>${escapeHtml(line.sales_date)}</td>
              <td>${escapeHtml(line.product)}</td>
              <td class="qty-cell">${formatNumber(line.qty)}</td>
              <td class="price-cell">R${formatNumber(line.price)}</td>
              <td class="discount-cell">R${formatNumber(line.discount_amount || 0)}</td>
              <td>R${formatNumber(line.gross_amount)}</td>
              <td>${line.auto_sale ? 'Auto' : 'Manual'}</td>
              <td>R${formatNumber(line.net_amount || line.gross_amount)}</td>
              <td>${escapeHtml(line.invoice_no)}</td>
              <td class="sales-row-actions">
                ${!line.invoice_no ? `
                  <button class="icon-btn" onclick="editRow('${delnote.delnote_no}', ${idx}, this)"><img src="/static/Image/edit.png" alt="Edit"></button>
                  <button class="icon-btn" onclick="deleteRow('${delnote.delnote_no}', ${idx}, this)"><img src="/static/Image/recycle-bin.png" alt="Delete"></button>
                ` : ''}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  return card;
}

// Edit row: make qty, price, discount editable, change edit to submit
window.editRow = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row || row.getAttribute('data-editing') === 'true') return;
  row.setAttribute('data-editing', 'true');
  // Only make price, qty, discount editable
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  const priceVal = priceCell.innerText.replace(/^R/, '').replace(/,/g, '');
  const qtyVal = qtyCell.innerText.replace(/,/g, '');
  const discountVal = discountCell.innerText.replace(/^R/, '').replace(/,/g, '');
  priceCell.innerHTML = `<input type='number' class='form-control form-control-sm' value='${priceVal}' style='min-width:70px;'>`;
  qtyCell.innerHTML = `<input type='number' class='form-control form-control-sm' value='${qtyVal}' style='min-width:70px;'>`;
  discountCell.innerHTML = `<input type='number' class='form-control form-control-sm' value='${discountVal}' style='min-width:70px;'>`;
  // Change edit button to submit
  btn.innerHTML = '<img src="/static/Image/check.png" alt="Submit">';
  btn.onclick = function() { submitRow(delnoteNo, idx, btn); };
}

// Submit row: save new values, revert to display
window.submitRow = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;
  row.setAttribute('data-editing', 'false');
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  let priceVal = priceCell.querySelector('input').value;
  let qtyVal = qtyCell.querySelector('input').value;
  let discountVal = discountCell.querySelector('input').value;
  priceCell.innerText = 'R' + formatNumber(priceVal);
  qtyCell.innerText = formatNumber(qtyVal);
  discountCell.innerText = 'R' + formatNumber(discountVal);
  btn.innerHTML = '<img src="/static/Image/edit.png" alt="Edit">';
  btn.onclick = function() { editRow(delnoteNo, idx, btn); };
}

// Placeholder for delete (implement backend as needed)
window.deleteRow = function(delnoteNo, idx, btn) {
  if (confirm('Are you sure you want to delete this line?')) {
    // Implement backend call here
    const row = document.getElementById(`row-${delnoteNo}-${idx}`);
    if (row) row.remove();
  }
}

// Placeholder for add sale
window.addSale = function(delnoteNo) {
  alert('Add sale for Delivery Note #' + delnoteNo);
}

// Show SweetAlert2 modal for matched lines
window.showMatchedModal = function(delnoteNo) {
  const matchedLines = (consignmentMap[delnoteNo] || []).filter(
    c => Number(c.linconsignmentidexist) === 0 && Number(c.headelnotenoexist) === 1
  );
  if (!matchedLines.length) {
    Swal.fire('No matched lines found for this Delivery Note.');
    return;
  }
  let html = `
    <div class="table-responsive">
      <table class="sales-table" style="margin-bottom:0;">
        <thead>
          <tr>
            <th></th>
            <th>ConsignmentID</th>
            <th>Product</th>
            <th>Variety</th>
            <th>Size</th>
            <th>Class</th>
            <th>Mass</th>
            <th>Brand</th>
            <th>Qty Sent</th>
          </tr>
        </thead>
        <tbody>
          ${matchedLines.map((line, idx) => `
            <tr style="cursor:pointer;" onclick="showConsignmentDetails('${line.consignmentid}')">
              <td style="text-align:center;">
                <button class="icon-btn" onclick="toggleDockets('${delnoteNo}', '${line.consignmentid}', this, ${idx}); event.stopPropagation();">+</button>
              </td>
              <td>${escapeHtml(line.consignmentid)}</td>
              <td>${escapeHtml(line.product)}</td>
              <td>${escapeHtml(line.variety)}</td>
              <td>${escapeHtml(line.size)}</td>
              <td>${escapeHtml(line.class)}</td>
              <td>${escapeHtml(line.mass_kg)}</td>
              <td>${escapeHtml(line.brand)}</td>
              <td>${formatNumber(line.qtysent)}</td>
            </tr>
            <tr class="dockets-row" style="display:none;"><td colspan="9" id="dockets-${delnoteNo}-${line.consignmentid}"></td></tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
  Swal.fire({
    title: `Matched Lines for Delivery Note #${delnoteNo}`,
    html: html,
    width: 900,
    showConfirmButton: false
  });
}

// Placeholder for consignment details
window.showConsignmentDetails = function(consignmentId) {
  fetch(`/import/get_consignment_details?consignment_id=${consignmentId}`)
    .then(response => response.json())
    .then(data => {
      if (data.error) {
        throw new Error(data.error);
      }

      let { ImportProduct, ImportVariety, ImportClass, ImportMass, ImportSize, ImportQty, ImportBrand } = data.consignment_details;
      let matches = data.matches || [];

      // Function to check if values match (case-insensitive, ignores units)
      function isMatch(value1, value2) {
        if (value1 == null || value2 == null) return false;
        let v1 = String(value1).trim().toLowerCase();
        let v2 = String(value2).trim().toLowerCase();
        let num1 = parseFloat(v1.replace(/[^\d.-]/g, ""));
        let num2 = parseFloat(v2.replace(/[^\d.-]/g, ""));
        if (!isNaN(num1) && !isNaN(num2)) {
          return num1 === num2;
        }
        return v1 === v2;
      }

      let matchOptions = matches.map(match => {
        return `
          <tr>
            <td><input type="radio" name="match" value="${match.DelLineIndex}"></td>
            <td style="${isMatch(match.LineProduct, ImportProduct) ? 'background-color: #52eb34;' : ''}">${match.LineProduct}</td>
            <td style="${isMatch(match.LineVariety, ImportVariety) ? 'background-color: #52eb34;' : ''}">${match.LineVariety}</td>
            <td style="${isMatch(match.LineClass, ImportClass) ? 'background-color: #52eb34;' : ''}">${match.LineClass}</td>
            <td style="${isMatch(match.LineMass, ImportMass) ? 'background-color: #52eb34;' : ''}">${match.LineMass}</td>
            <td style="${isMatch(match.LineSize, ImportSize) ? 'background-color: #52eb34;' : ''}">${match.LineSize}</td>
            <td style="${isMatch(match.LineBrand, ImportBrand) ? 'background-color: #52eb34;' : ''}">${match.LineBrand}</td>
            <td style="${isMatch(match.LineQty, ImportQty) ? 'background-color: #52eb34;' : ''}">${match.LineQty}</td>
          </tr>
        `;
      }).join('');

      Swal.fire({
        title: `Consignment ID: ${consignmentId}`,
        html: `
          <b>Product:</b> ${ImportProduct} <br>
          <b>Variety:</b> ${ImportVariety} <br>
          <b>Class:</b> ${ImportClass} <br>
          <b>Mass:</b> ${ImportMass} kg <br>
          <b>Size:</b> ${ImportSize} <br>
          <b>Brand:</b> ${ImportBrand} <br>
          <b>Quantity:</b> ${ImportQty} <br>
          <br>
          <table class="table table-bordered">
            <thead>
              <tr>
                <th>Select</th>
                <th>Line Product</th>
                <th>Line Variety</th>
                <th>Line Class</th>
                <th>Line Mass</th>
                <th>Line Size</th>
                <th>Line Brand</th>
                <th>Line Quantity</th>
              </tr>
            </thead>
            <tbody>${matchOptions}</tbody>
          </table>
        `,
        showCancelButton: true,
        width: '80%',
        confirmButtonText: "Match",
        cancelButtonText: "Close",
        preConfirm: () => {
          let selectedMatch = document.querySelector('input[name=\"match\"]:checked');
          if (!selectedMatch) {
            Swal.showValidationMessage("Please select a match.");
          }
          return selectedMatch ? selectedMatch.value : null;
        }
      }).then(result => {
        if (result.isConfirmed) {
          let lineId = result.value;
          fetch(`/import/match_consignment/${consignmentId}/${lineId}`, { method: "POST" })
            .then(response => response.json())
            .then(data => {
              if (data.error) {
                Swal.fire("Error!", data.error, "error");
              } else {
                Swal.fire({
                  title: "Matched!",
                  text: data.message,
                  icon: "success",
                  timer: 1000,
                  showConfirmButton: false
                });
                // Optionally refresh data here
              }
            })
            .catch(error => {
              console.error("Match error:", error);
              Swal.fire("Error!", "Failed to match consignment.", "error");
            });
        }
      });
    })
    .catch(error => {
      console.error("Error fetching details:", error);
      Swal.fire("Error!", error.message || "Failed to load consignment details.", "error");
    });
};

// Utility: format numbers with thousands separator
function formatNumber(num) {
  if (num == null || num === '') return '';
  return Number(num).toLocaleString('en-ZA');
}
// Utility: escape HTML
function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text).replace(/[&<>"']|'/g, function(m) {
    return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m];
  });
}

window.toggleDockets = function(delnoteNo, consignmentId, btn, idx) {
  const docketsRow = document.getElementById(`dockets-${delnoteNo}-${consignmentId}`);
  const tr = btn.closest('tr').nextElementSibling;
  if (tr.style.display === 'none') {
    // Fetch dockets if not already loaded
    if (!docketsRow.innerHTML) {
      fetch(`/api/dockets?consignment_id=${encodeURIComponent(consignmentId)}`)
        .then(res => res.json())
        .then(dockets => {
          docketsRow.innerHTML = renderDocketsTable(dockets);
        });
    }
    tr.style.display = '';
    btn.textContent = '−';
  } else {
    tr.style.display = 'none';
    btn.textContent = '+';
  }
};

function renderDocketsTable(dockets) {
  if (!dockets.length) return '<em>No dockets found.</em>';
  return `<table class="sales-table" style="margin:0;">
    <thead>
      <tr>
        <th>Docket Number</th>
        <th>Date Sold</th>
        <th>Qty Sold</th>
        <th>Price</th>
        <th>Sales Value</th>
      </tr>
    </thead>
    <tbody>
      ${dockets.map(d => `
        <tr>
          <td>${escapeHtml(d.docketnumber)}</td>
          <td>${escapeHtml(d.datesold)}</td>
          <td>${formatNumber(d.qtysold)}</td>
          <td>R${formatNumber(d.price)}</td>
          <td>R${formatNumber(d.salesvalue)}</td>
        </tr>
      `).join('')}
    </tbody>
  </table>`;
} 

window.showLinkedModal = function(delnoteNo) {
  fetch(`/api/linked_lines?delnote_no=${encodeURIComponent(delnoteNo)}`)
    .then(res => res.json())
    .then(lines => {
      if (!lines.length) {
        Swal.fire('No linked lines found for this Delivery Note.');
        return;
      }
      let linkedImg = '<img src="/static/Image/link.png" alt="Linked" style="height:24px;">';

      // Sort lines: linked first, then only delivery, then only trn
      const sortedLines = [...lines].sort((a, b) => {
        const aHasDel = a.delnoteno || a.delproductdescription || a.delqtysent;
        const aHasTrn = a.trnconsignmentid || a.trndelnoteno || a.trnproduct || a.trnmass || a.trnclass || a.trnsize || a.trnvariety || a.trnbrand || a.trnqtysent;
        const bHasDel = b.delnoteno || b.delproductdescription || b.delqtysent;
        const bHasTrn = b.trnconsignmentid || b.trndelnoteno || b.trnproduct || b.trnmass || b.trnclass || b.trnsize || b.trnvariety || b.trnbrand || b.trnqtysent;

        // Linked lines first
        if (aHasDel && aHasTrn && !(bHasDel && bHasTrn)) return -1;
        if (!(aHasDel && aHasTrn) && (bHasDel && bHasTrn)) return 1;
        // Then only Delivery Note lines
        if (aHasDel && !aHasTrn && !(bHasDel && !bHasTrn)) return -1;
        if (!(aHasDel && !aHasTrn) && (bHasDel && !bHasTrn)) return 1;
        // Then only Trn lines
        if (!aHasDel && aHasTrn && (bHasDel || !bHasTrn)) return -1;
        if ((aHasDel || !aHasTrn) && !bHasDel && bHasTrn) return 1;
        return 0;
      });

      let html = `
        <div class="table-responsive">
          <table class="sales-table" style="margin-bottom:0;">
            <thead>
              <tr>
                <th colspan="6" style="background:#e0edff;text-align:center;border-right:2px solid #b6c6e6;">Delivery Note</th>
                <th style="background:#fff;"></th>
                <th colspan="9" style="background:#e0edff;text-align:center;">Imported</th>
              </tr>
              <tr>
                <th></th>
                <th>DelNoteNo</th>
                <th>ProductDescription</th>
                <th>Qty Sent</th>
                <th>Sales Qty</th>
                <th>Invoiced Qty</th>
                <th style="background:#fff;"></th>
                <th>ConsignmentID</th>
                <th>DelNoteNo</th>
                <th>Product</th>
                <th>Mass</th>
                <th>Class</th>
                <th>Size</th>
                <th>Variety</th>
                <th>Brand</th>
                <th>Qty Sent</th>
              </tr>
            </thead>
            <tbody>
              ${sortedLines.map(line => {
                const hasDel = line.delnoteno || line.delproductdescription || line.delqtysent;
                const hasTrn = line.trnconsignmentid || line.trndelnoteno || line.trnproduct || line.trnmass || line.trnclass || line.trnsize || line.trnvariety || line.trnbrand || line.trnqtysent;
                return `
                  <tr>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">
                      ${hasDel || hasTrn ? `<button class="icon-btn" onclick="toggleExpandedData('${line.dellineindex}', '${line.trnconsignmentid}', this); event.stopPropagation();">+</button>` : ''}
                    </td>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">${escapeHtml(line.delnoteno)}</td>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">${escapeHtml(line.delproductdescription)}</td>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">${escapeHtml(line.delqtysent)}</td>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">${escapeHtml(line.totalsalesqty)}</td>
                    <td style="background:#fafdff;border-right:2px solid #b6c6e6;">${escapeHtml(line.totalinvoicedqty)}</td>
                    <td style="background:#fff;text-align:center;">
                      ${hasDel && hasTrn ? linkedImg : ''}
                    </td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnconsignmentid)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trndelnoteno)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnproduct)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnmass)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnclass)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnsize)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnvariety)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnbrand)}</td>
                    <td style="background:#f0f7ff;">${escapeHtml(line.trnqtysent)}</td>
                  </tr>
                  ${hasDel || hasTrn ? `<tr class="expanded-data-row" style="display:none;"><td colspan="15" id="expanded-data-${line.dellineindex}-${line.trnconsignmentid}"></td></tr>` : ''}
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
      Swal.fire({
        title: `Linked Lines for Delivery Note #${delnoteNo}`,
        html: html,
        width: 1800,
        showConfirmButton: false,
        showCancelButton: true,
        cancelButtonText: '<i class="fa fa-times"></i>',
        cancelButtonAriaLabel: 'Close',
        cancelButtonColor: '#d33',
        customClass: {
          cancelButton: 'swal2-x-close-btn'
        },
        buttonsStyling: false,
        didOpen: () => {
          // Move the cancel button to the top right and style as an x
          const btn = document.querySelector('.swal2-x-close-btn');
          if (btn) {
            btn.style.position = 'absolute';
            btn.style.top = '10px';
            btn.style.right = '10px';
            btn.style.background = 'none';
            btn.style.border = 'none';
            btn.style.outline = 'none';
            btn.style.fontSize = '1.5rem';
            btn.style.color = '#888';
            btn.style.boxShadow = 'none';
            btn.style.zIndex = '1001';
            btn.style.padding = '0';
            btn.style.width = '32px';
            btn.style.height = '32px';
            btn.style.display = 'flex';
            btn.style.alignItems = 'center';
            btn.style.justifyContent = 'center';
            btn.onmouseover = () => btn.style.color = '#3b3d3b';
            btn.onmouseout = () => btn.style.color = '#888';
          }
        }
      });
    });
};

// Update toggleExpandedData to display Delivery Note sales and Trn data separately
window.toggleExpandedData = function(delLineIndex, trnConsignmentId, btn) {
  const row = btn.closest('tr').nextElementSibling;
  const expandedDataContainer = document.getElementById(`expanded-data-${delLineIndex}-${trnConsignmentId}`);
  if (!expandedDataContainer) {
    console.error(`Container for DelLineIndex ${delLineIndex} and TrnConsignmentId ${trnConsignmentId} not found.`);
    return;
  }
  if (row.style.display === 'none') {
    // Fetch delivery note lines if not already loaded
    if (!expandedDataContainer.innerHTML) {
      Promise.all([
        fetch(`/api/delivery_note_lines?del_line_index=${encodeURIComponent(delLineIndex)}`).then(res => res.json()),
        fetch(`/api/dockets?consignment_id=${encodeURIComponent(trnConsignmentId)}`).then(res => res.json())
      ]).then(([deliveryLines, dockets]) => {
        expandedDataContainer.innerHTML = `
          <div style="display: flex; gap: 20px;">
            <div style="flex: 1;">
              <h4>Delivery Note Lines</h4>
              ${renderDeliveryNoteLinesTable(deliveryLines)}
            </div>
            <div style="flex: 1;">
              <h4>Trn Data (Dockets)</h4>
              ${renderDocketsTable(dockets)}
            </div>
          </div>
        `;
      });
    }
    row.style.display = '';
    btn.textContent = '−';
  } else {
    row.style.display = 'none';
    btn.textContent = '+';
  }
};

// Update renderDeliveryNoteLinesTable to only show Date, Qty, Price, Amount, and AutoSale
function renderDeliveryNoteLinesTable(lines) {
  if (!lines.length) return '<em>No delivery note lines found.</em>';
  return `<table class="sales-table" style="margin:0;">
    <thead>
      <tr>
        <th>Date</th>
        <th>Qty</th>
        <th>Price</th>
        <th>Amount</th>
        <th>AutoSale</th>
        <th>Invoice No</th>
      </tr>
    </thead>
    <tbody>
      ${lines.map(line => `
        <tr>
          <td>${escapeHtml(line.salesdate)}</td>
          <td>${formatNumber(line.salesqty)}</td>
          <td>R${formatNumber(line.salesprice)}</td>
          <td>R${formatNumber(line.grosssalesamnt)}</td>
          <td>${line.autosale ? 'Auto' : 'Manual'}</td>
          <td>${escapeHtml(line.invoiceno)}</td>
        </tr>
      `).join('')}
    </tbody>
  </table>`;
}