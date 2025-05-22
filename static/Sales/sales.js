document.addEventListener('DOMContentLoaded', function() {
  // Only fetch sales data if we're on the sales page
  const salesContainer = document.getElementById('salesContainer');
  if (salesContainer) {
    fetchSalesData();
  }
});

let consignmentMap = {};

function fetchSalesData() {
  fetch('/api/sales')
    .then(response => response.json())
    .then(data => {
      const container = document.getElementById('salesContainer');
      if (!container) return; // Exit if container doesn't exist
      
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
            Linked: 
        </span>
        <span class="sales-header-badge matched-badge" style="cursor:pointer;" onclick="showMatchedModal('${delnote.delnote_no}')">Matched: </span>
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
          ${delnote.lines.map((line, idx) => {
            // Ensure we have valid values for the data attributes
            const salesId = line.sales_line_index || '';
            const lineId = line.del_line_id || line.sales_line_index || '';
            
            return `
              <tr id="row-${delnote.delnote_no}-${idx}" 
                  data-sales-id="${line.sales_line_index}"
                  data-line-id="${line.del_line_id}">
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
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
  return card;
}

// Edit row: make qty, price, discount editable, change edit to submit
window.editRow = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;
  
  // Get the data attributes
  const salesId = row.dataset.salesId;
  const lineId = row.dataset.lineId;
  
  if (!lineId) {
    Swal.fire({
      title: 'Error',
      text: 'Could not determine the line ID for this sale. Please try refreshing the page.',
      icon: 'error'
    });
    return;
  }
  
  // Convert cells to input fields
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  
  const price = parseFloat(priceCell.innerText.replace('R', '').replace(/,/g, ''));
  const qty = parseFloat(qtyCell.innerText.replace(/,/g, ''));
  const discount = parseFloat(discountCell.innerText.replace('R', '').replace(/,/g, '')) / price / qty * 100;
  
  priceCell.innerHTML = `<input type="number" step="0.01" value="${price}" class="form-control">`;
  qtyCell.innerHTML = `<input type="number" step="1" value="${qty}" class="form-control">`;
  discountCell.innerHTML = `<input type="number" step="0.01" value="${discount}" class="form-control">`;
  
  // Replace edit button with submit button
  const actionsCell = row.querySelector('.sales-row-actions');
  actionsCell.innerHTML = `
    <button class="icon-btn" onclick="submitRow('${delnoteNo}', ${idx}, this, '${salesId}', '${lineId}')">
      <img src="/static/Image/check.png" alt="Submit">
    </button>
    <button class="icon-btn" onclick="cancelEdit('${delnoteNo}', ${idx}, this)">
      <img src="/static/Image/cancel.png" alt="Cancel">
    </button>
  `;
  
  // Mark row as being edited
  row.dataset.editing = 'true';
}

// Submit row: save new values, revert to display
window.submitRow = function(delnoteNo, idx, btn, salesId, lineId) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;
  
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  
  const price = parseFloat(priceCell.querySelector('input').value);
  const qty = parseFloat(qtyCell.querySelector('input').value);
  const discount = parseFloat(discountCell.querySelector('input').value);
  
  // Calculate amounts
  const amount = price * qty;
  const discountAmount = (amount * discount) / 100;
  const grossAmount = amount;
  
  // Use the lineId passed as parameter, or fall back to dataset
  const finalLineId = lineId || row.dataset.lineId;
  
  if (!finalLineId) {
    Swal.fire({
      title: 'Error',
      text: 'Could not determine the line ID for this sale. Please try refreshing the page.',
      icon: 'error'
    });
    return;
  }
  
  // Prepare the sale data
  const saleData = {
    lineId: finalLineId,  // This matches the backend's expected field name
    salesId: salesId,
    date: row.querySelector('td:first-child').innerText,
    price: price,
    quantity: qty,
    discount: discount,
    discountAmnt: discountAmount,
    amount: amount,
    destroyed: false
  };
  
  // Submit the sale
  fetch('/submit_sales_entries', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      salesEntries: [saleData]
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      Swal.fire({
        title: 'Success!',
        text: 'Sale has been updated successfully.',
        icon: 'success'
      }).then(() => {
        // Use the refreshSalesTable function from view.js
        if (typeof refreshSalesTable === 'function') {
          refreshSalesTable(delnoteNo);
        } else {
          console.error('refreshSalesTable function not found');
          // Fallback to page reload if function not found
          window.location.reload();
        }
      });
    } else {
      Swal.fire({
        title: 'Error',
        text: data.message || 'Failed to update sale.',
        icon: 'error'
      });
    }
  })
  .catch(error => {
    console.error('Error submitting sale:', error);
    Swal.fire({
      title: 'Error',
      text: 'An error occurred while updating the sale.',
      icon: 'error'
    });
  });
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
  fetch(`/api/available-lines/${delnoteNo}`)
    .then(response => response.json())
    .then(data => {
      if (!data.lines || data.lines.length === 0) {
        Swal.fire({
          title: 'No Available Lines',
          text: 'All lines in this delivery note have been fully sold.',
          icon: 'info'
        });
        return;
      }

      // Product line selection
      const linesHtml = data.lines.map(line => `
        <div class="line-option" data-line-id="${line.dellineindex}" 
             data-product="${line.productdescription}"
             data-available="${line.available_qty}"
             style="padding: 12px; margin: 8px 0; border: 1.5px solid #e0e8f0; border-radius: 8px; cursor: pointer; transition: background 0.2s;">
          <div style="font-weight: 600; color: #2563eb; font-size: 1.1em;">${line.productdescription}</div>
          <div style="color: #64748b; font-size: 0.95em;">
            Available: <span style="font-weight:600">${line.available_qty}</span> bags
          </div>
        </div>
      `).join('');

      Swal.fire({
        title: '<span style="font-size:1.3em;font-weight:700;color:#2563eb;">Add Sale</span>',
        html: `
          <div style="text-align: left; margin-bottom: 1.5rem;">
            <div style="margin-bottom: 1.5rem;">
              <div style="font-weight: 600; color: #334155; margin-bottom: 0.5em;">1. Select Product Line</div>
              <div class="line-selection" style="max-height: 180px; overflow-y: auto; margin-top: 0.5rem;">
                ${linesHtml}
              </div>
            </div>
            <div style="margin-bottom: 1.5rem;">
              <span style="font-weight: 600; color: #334155;">Available for sale: </span>
              <span id="available-for-sale" style="color: #2563eb; font-weight: 600;">0</span>
            </div>
            <div style="font-weight: 600; color: #334155; margin-bottom: 0.5em;">2. Enter Sale Details</div>
            <div class="table-container" style="margin-bottom: 1rem;">
              <table class="sales-table" style="width: 100%; border-radius: 8px; overflow: hidden; background: #f8fafc;">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Discount (%)</th>
                    <th>Amount</th>
                    <th>Destroy</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody class="sales-entries-list" style="background: #fff;">
                  <!-- Sales entries will be added here -->
                </tbody>
                <tbody class="new-entry-row" style="background: #fff;">
                  <tr>
                    <td><input type="date" class="form-control" id="saleDate" required></td>
                    <td><input type="number" class="form-control" id="saleQty" min="1" required></td>
                    <td><input type="number" class="form-control" id="salePrice" step="0.01" required></td>
                    <td><input type="number" class="form-control" id="saleDiscount" value="0" min="0" max="100" step="0.01"></td>
                    <td><span id="saleAmount">R0.00</span></td>
                    <td><input type="checkbox" class="form-check-input" id="saleDestroy"></td>
                    <td><button class="btn btn-primary" onclick="addSaleEntry()">Add</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 1rem 0; border-top: 1px solid #e2e8f0;">
              <span style="font-weight: 600; color: #334155;">Total Quantity: <span id="totalSalesQuantity" style="color: #2563eb;">0</span></span>
              <span style="font-weight: 600; color: #334155;">Total Amount: <span id="totalSalesAmount" style="color: #2563eb;">R0.00</span></span>
            </div>
          </div>
        `,
        width: 700,
        showCancelButton: true,
        confirmButtonText: 'Submit',
        cancelButtonText: 'Cancel',
        showCloseButton: true,
        didOpen: () => {
          // Highlight selected line
          document.querySelectorAll('.line-option').forEach(line => {
            line.addEventListener('click', () => {
              document.querySelectorAll('.line-option').forEach(opt => {
                opt.style.background = '#fff';
                opt.style.borderColor = '#e0e8f0';
              });
              line.style.background = '#e0edff';
              line.style.borderColor = '#2563eb';
              document.getElementById('available-for-sale').textContent = line.dataset.available;
              window.selectedLine = {
                lineId: line.dataset.lineId,
                product: line.dataset.product,
                available: parseInt(line.dataset.available)
              };
            });
          });

          // Live calculation
          const qtyInput = document.getElementById('saleQty');
          const priceInput = document.getElementById('salePrice');
          const discountInput = document.getElementById('saleDiscount');
          function updateAmount() {
            const qty = parseFloat(qtyInput.value) || 0;
            const price = parseFloat(priceInput.value) || 0;
            const discount = parseFloat(discountInput.value) || 0;
            const amount = qty * price * (1 - discount / 100);
            document.getElementById('saleAmount').textContent = `R${amount.toFixed(2)}`;
          }
          qtyInput.addEventListener('input', updateAmount);
          priceInput.addEventListener('input', updateAmount);
          discountInput.addEventListener('input', updateAmount);
        }
      });
    });
};

// Function to add a sale entry to the list
window.addSaleEntry = function() {
  if (!window.selectedLine) {
    Swal.showValidationMessage('Please select a product line first');
    return;
  }

  const date = document.getElementById('saleDate').value;
  const qty = parseInt(document.getElementById('saleQty').value);
  const price = parseFloat(document.getElementById('salePrice').value);
  const discount = parseFloat(document.getElementById('saleDiscount').value);
  const destroy = document.getElementById('saleDestroy').checked;

  if (!date || !qty || !price) {
    Swal.showValidationMessage('Please fill in all required fields');
    return;
  }

  if (qty > window.selectedLine.available) {
    Swal.showValidationMessage(`Quantity cannot exceed available quantity (${window.selectedLine.available})`);
    return;
  }

  const amount = qty * price * (1 - discount / 100);
  const entryHtml = `
    <tr>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${date}</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${qty}</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">R${price.toFixed(2)}</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${discount}%</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">R${amount.toFixed(2)}</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${destroy ? 'Yes' : 'No'}</td>
      <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">
        <button class="btn btn-danger btn-sm" onclick="removeSaleEntry(this)">Remove</button>
      </td>
    </tr>
  `;

  document.querySelector('.sales-entries-list').insertAdjacentHTML('beforeend', entryHtml);
  
  // Update totals
  updateTotals();
  
  // Clear inputs
  document.getElementById('saleDate').value = '';
  document.getElementById('saleQty').value = '';
  document.getElementById('salePrice').value = '';
  document.getElementById('saleDiscount').value = '0';
  document.getElementById('saleDestroy').checked = false;
  document.getElementById('saleAmount').textContent = 'R0.00';
};

// Function to remove a sale entry
window.removeSaleEntry = function(button) {
  button.closest('tr').remove();
  updateTotals();
};

// Function to update totals
function updateTotals() {
  const entries = document.querySelectorAll('.sales-entries-list tr');
  let totalQty = 0;
  let totalAmount = 0;

  entries.forEach(entry => {
    const cells = entry.cells;
    totalQty += parseInt(cells[1].textContent);
    totalAmount += parseFloat(cells[4].textContent.replace('R', ''));
  });

  document.getElementById('totalSalesQuantity').textContent = totalQty;
  document.getElementById('totalSalesAmount').textContent = `R${totalAmount.toFixed(2)}`;
};

// Show SweetAlert2 modal for matched lines
window.showMatchedModal = function(delnoteNo) {
  fetch(`/api/linked_lines?delnote_no=${encodeURIComponent(delnoteNo)}`)
    .then(res => res.json())
    .then(lines => {
      // Filter for matched lines (those that have TrnConsignmentID but no DelLineIndex)
      const matchedLines = lines.filter(line => 
        line.trnconsignmentid && 
        (!line.dellineindex || line.dellineindex === '') &&
        line.trndelnoteno === delnoteNo
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
                <tr style="cursor:pointer;" onclick="showConsignmentDetails('${line.trnconsignmentid}')">
                  <td style="text-align:center;">
                    <button class="icon-btn" onclick="toggleDockets('${delnoteNo}', '${line.trnconsignmentid}', this, ${idx}); event.stopPropagation();">+</button>
                  </td>
                  <td>${escapeHtml(line.trnconsignmentid)}</td>
                  <td>${escapeHtml(line.trnproduct)}</td>
                  <td>${escapeHtml(line.trnvariety)}</td>
                  <td>${escapeHtml(line.trnsize)}</td>
                  <td>${escapeHtml(line.trnclass)}</td>
                  <td>${escapeHtml(line.trnmass)}</td>
                  <td>${escapeHtml(line.trnbrand)}</td>
                  <td>${formatNumber(line.trnqtysent)}</td>
                </tr>
                <tr class="dockets-row" style="display:none;"><td colspan="9" id="dockets-${delnoteNo}-${line.trnconsignmentid}"></td></tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
      Swal.fire({
        title: `Matched Lines for Delivery Note #${delnoteNo}`,
        html: html,
        width: 2000,
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
                }).then(() => {
                  // Get the delivery note number from the current page
                  const delnoteNo = document.querySelector('.sales-header-title').textContent.split('#')[1];
                  if (delnoteNo) {
                    // Refresh everything
                    refreshSalesTable(delnoteNo);
                    // Close the matched modal if it's open
                    Swal.close();
                  }
                });
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
  
  // Calculate totals
  const totals = dockets.reduce((acc, d) => {
    acc.qtySold += parseFloat(d.qtysold) || 0;
    acc.salesValue += parseFloat(d.salesvalue) || 0;
    return acc;
  }, { qtySold: 0, salesValue: 0 });

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
    <tfoot>
      <tr style="background-color: #e0edff; border-top: 2px solid #b6c6e6;">
        <td colspan="2" style="text-align: right; font-weight: 600; color: #1e40af; padding: 12px 16px;">Totals:</td>
        <td style="font-weight: 700; color: #1e40af; padding: 12px 16px;">${formatNumber(totals.qtySold)}</td>
        <td></td>
        <td style="font-weight: 700; color: #1e40af; padding: 12px 16px;">R${formatNumber(totals.salesValue)}</td>
      </tr>
    </tfoot>
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
                <th colspan="9" style="background:#e0edff;text-align:center;border-right:2px solid #b6c6e6;">Imported</th>
                <th style="background:#fff;"></th>
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
                <th style="background:#fff;"></th>
              </tr>
            </thead>
            <tbody>
              ${sortedLines.map(line => {
                const hasDel = line.delnoteno || line.delproductdescription || line.delqtysent;
                const hasTrn = line.trnconsignmentid || line.trndelnoteno || line.trnproduct || line.trnmass || line.trnclass || line.trnsize || line.trnvariety || line.trnbrand || line.trnqtysent;
                const canUnlink = hasDel && hasTrn && (!line.totalinvoicedqty || line.totalinvoicedqty === 0);
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
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnconsignmentid)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trndelnoteno)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnproduct)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnmass)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnclass)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnsize)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnvariety)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnbrand)}</td>
                    <td style="background:#f0f7ff;border-right:2px solid #b6c6e6;">${escapeHtml(line.trnqtysent)}</td>
                    <td style="background:#fff;text-align:center;">
                      ${canUnlink ? `
                        <button class="icon-btn" onclick="unlinkConsignment('${line.trnconsignmentid}', '${delnoteNo}')" title="Remove Match">
                          <img src="/static/Image/unlink.png" alt="Remove Match">
                        </button>
                      ` : ''}
                    </td>
                  </tr>
                  ${hasDel || hasTrn ? `<tr class="expanded-data-row" style="display:none;"><td colspan="17" id="expanded-data-${line.dellineindex}-${line.trnconsignmentid}"></td></tr>` : ''}
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
      Swal.fire({
        title: `Linked Lines for Delivery Note #${delnoteNo}`,
        html: html,
        width: 2000,
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
  
  // Calculate totals
  const totals = lines.reduce((acc, line) => {
    acc.qty += parseFloat(line.salesqty) || 0;
    acc.amount += parseFloat(line.grosssalesamnt) || 0;
    return acc;
  }, { qty: 0, amount: 0 });

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
    <tfoot>
      <tr class="totals-row">
        <td class="totals-label">Totals:</td>
        <td class="totals-value">${formatNumber(totals.qty)}</td>
        <td></td>
        <td class="totals-value">R${formatNumber(totals.amount)}</td>
        <td colspan="2"></td>
      </tr>
    </tfoot>
  </table>`;
}

// Cancel edit: revert row back to display mode
window.cancelEdit = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;

  // Get the original values from data attributes
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');

  // Restore original values
  priceCell.innerHTML = `R${formatNumber(parseFloat(priceCell.querySelector('input').value))}`;
  qtyCell.innerHTML = formatNumber(parseFloat(qtyCell.querySelector('input').value));
  discountCell.innerHTML = `R${formatNumber(parseFloat(discountCell.querySelector('input').value))}`;

  // Restore edit and delete buttons
  const actionsCell = row.querySelector('.sales-row-actions');
  actionsCell.innerHTML = `
    <button class="icon-btn" onclick="editRow('${delnoteNo}', ${idx}, this)">
      <img src="/static/Image/edit.png" alt="Edit">
    </button>
    <button class="icon-btn" onclick="deleteRow('${delnoteNo}', ${idx}, this)">
      <img src="/static/Image/recycle-bin.png" alt="Delete">
    </button>
  `;

  // Remove editing state
  delete row.dataset.editing;
}

// Add function to handle unlinking consignment
window.unlinkConsignment = function(consignmentId, delnoteNo) {
  Swal.fire({
    title: 'Remove Match',
    text: 'Are you sure you want to remove this match? This action cannot be undone.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'Yes, remove it',
    cancelButtonText: 'Cancel',
    confirmButtonColor: '#dc2626',
    cancelButtonColor: '#6b7280'
  }).then((result) => {
    if (result.isConfirmed) {
      fetch(`/api/unlink-consignment/${consignmentId}`, {
        method: 'POST'
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          Swal.fire({
            title: 'Success!',
            text: 'Match has been removed successfully.',
            icon: 'success'
          }).then(() => {
            // Close the current modal
            Swal.close();
            
            // Refresh the sales table
            fetch(`/api/refresh-sales/${delnoteNo}`)
              .then(response => response.text())
              .then(html => {
                const container = document.getElementById('salesTableContainer');
                if (container) {
                  container.innerHTML = html;
                }
              })
              .catch(error => {
                console.error('Error refreshing sales table:', error);
              });

            // Show the updated linked lines modal
            showLinkedModal(delnoteNo);
          });
        } else {
          Swal.fire({
            title: 'Error',
            text: data.message || 'Failed to remove match.',
            icon: 'error'
          });
        }
      })
      .catch(error => {
        console.error('Error unlinking consignment:', error);
        Swal.fire({
          title: 'Error',
          text: 'An error occurred while removing the match.',
          icon: 'error'
        });
      });
    }
  });
};

// Update the refreshSalesTable function
function refreshSalesTable(delnoteNo) {
  fetch(`/api/refresh-sales/${delnoteNo}`)
    .then(response => response.text())
    .then(html => {
      const container = document.getElementById('salesTableContainer');
      if (container) {
        container.innerHTML = html;
      }
      // Update the counts after refreshing the table
      updateCountsDisplay(delnoteNo);
    })
    .catch(error => {
      console.error('Error refreshing sales table:', error);
    });
}

// Function to handle product change
window.changeProduct = function(lineId, currentProduct) {
  // Fetch products from the server
  fetch('/api/products')
    .then(response => response.json())
    .then(products => {
      // Create the modal HTML with searchable dropdown
      const modalHtml = `
        <div style="text-align: left;">
          <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155;">Current Product</label>
            <div style="padding: 0.8em; background: #f8fafc; border-radius: 8px; color: #64748b;">
              ${currentProduct}
            </div>
          </div>
          <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155;">New Product</label>
            <select id="productSelect" class="form-select" style="width: 100%;">
              <option value="">Select a product...</option>
              ${products.map(p => `<option value="${p.StockLink}">${p.display_name}</option>`).join('')}
            </select>
          </div>
        </div>
      `;

      // Initialize Select2 on the dropdown
      Swal.fire({
        title: 'Change Product',
        html: modalHtml,
        showCancelButton: true,
        confirmButtonText: 'Save',
        cancelButtonText: 'Cancel',
        width: 600,
        didOpen: () => {
          // Initialize Select2
          $('#productSelect').select2({
            dropdownParent: $('.swal2-container'),
            width: '100%',
            placeholder: 'Search for a product...',
            allowClear: true
          });
        },
        preConfirm: () => {
          const selectedProduct = document.getElementById('productSelect').value;
          if (!selectedProduct) {
            Swal.showValidationMessage('Please select a product');
            return false;
          }
          return selectedProduct;
        }
      }).then((result) => {
        if (result.isConfirmed) {
          // Save the new product
          fetch('/api/save_product', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              line_id: lineId,
              product_id: result.value
            })
          })
          .then(response => response.json())
          .then(data => {
            if (data.message) {
              Swal.fire({
                title: 'Success!',
                text: 'Product has been updated successfully.',
                icon: 'success',
                timer: 1500,
                showConfirmButton: false
              }).then(() => {
                // Refresh the sales table
                const delnoteNo = document.querySelector('.sales-header-title').textContent.split('#')[1];
                if (delnoteNo) {
                  refreshSalesTable(delnoteNo);
                }
              });
            } else {
              throw new Error(data.error || 'Failed to update product');
            }
          })
          .catch(error => {
            Swal.fire({
              title: 'Error',
              text: error.message || 'Failed to update product',
              icon: 'error'
            });
          });
        }
      });
    })
    .catch(error => {
      console.error('Error fetching products:', error);
      Swal.fire({
        title: 'Error',
        text: 'Failed to load products',
        icon: 'error'
      });
    });
};