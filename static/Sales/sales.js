let consignmentMap = {};

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

function renderDocketsTable(dockets) {
  if (!dockets.length) return '<em>No import sales</em>';
  
  // Calculate totals
  const totals = dockets.reduce((acc, d) => {
    acc.qtySold += parseFloat(d.qtysold) || 0;
    acc.salesValue += parseFloat(d.salesvalue) || 0;
    return acc;
  }, { qtySold: 0, salesValue: 0 });

  return `<table class="fs-table" style="margin:0;">
    <thead style="filter:brightness(0.93);">
    <th colspan="6" style="background:var(--table-header-bg);text-align:center;">Imported Sales Lines</th>
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
      <tr style="background-color: var(--table-totals-row-bg); border-top: 2px solid var(--table-border);">
        <td colspan="2" style="text-align: right; font-weight: 600; color: var(-table-totals-row-text); padding: 12px 16px;">Totals:</td>
        <td style="font-weight: 700; color: var(-table-totals-row-text); padding: 12px 16px;">${formatNumber(totals.qtySold)}</td>
        <td></td>
        <td style="font-weight: 700; color: var(-table-totals-row-text); padding: 12px 16px;">R${formatNumber(totals.salesValue)}</td>
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
        if (aHasDel && !aHasTrn && !(bHasDel && !aHasTrn)) return -1;
        if (!(aHasDel && !aHasTrn) && (bHasDel && !bHasTrn)) return 1;
        // Then only Trn lines
        if (!aHasDel && aHasTrn && (bHasDel || !bHasTrn)) return -1;
        if ((aHasDel || !aHasTrn) && !bHasDel && bHasTrn) return 1;
        return 0;
      });

      let html = `
        <div class="table-responsive">
          <table class="fs-table" style="margin-bottom:0;">
            <thead>
              <tr>
                <th colspan="6" style="background:var(--table-header-bg);text-align:center;">Delivery Note</th>
                <th></th>
                <th colspan="9" style="background:var(--table-header-bg);text-align:center;">Imported</th>
                <th></th>
              </tr>
              <tr>
                <th></th>
                <th>DelNoteNo</th>
                <th>ProductDescription</th>
                <th>Qty Sent</th>
                <th>Sales Qty</th>
                <th>Invoiced Qty</th>
                <th></th>
                <th>ConsignmentID</th>
                <th>DelNoteNo</th>
                <th>Product</th>
                <th>Mass</th>
                <th>Class</th>
                <th>Size</th>
                <th>Variety</th>
                <th>Brand</th>
                <th>Qty Sent</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${sortedLines.map(line => {
                const hasDel = line.delnoteno || line.delproductdescription || line.delqtysent;
                const hasTrn = line.trnconsignmentid || line.trndelnoteno || line.trnproduct || line.trnmass || line.trnclass || line.trnsize || line.trnvariety || line.trnbrand || line.trnqtysent;
                const canUnlink = hasDel && hasTrn && (!line.totalinvoicedqty || line.totalinvoicedqty === 0);
                return `
                  <tr>
                    <td style="background:var(--container-bg);border-right:2px solid var(--table-border);">
                      ${hasDel || hasTrn ? `<button class="icon-btn" onclick="toggleExpandedData('${line.dellineindex}', '${line.trnconsignmentid}', this); event.stopPropagation();">+</button>` : ''}
                    </td>
                    <td style="background:var(--table-row-even);border-right:2px solid var(--table-border);">${escapeHtml(line.delnoteno)}</td>
                    <td style="background:var(--table-row-even);border-right:2px solid var(--table-border);">${escapeHtml(line.delproductdescription)}</td>
                    <td style="background:var(--table-row-even);border-right:2px solid var(--table-border);">${escapeHtml(line.delqtysent)}</td>
                    <td style="background:var(--table-row-even);border-right:2px solid var(--table-border);">${escapeHtml(line.totalsalesqty)}</td>
                    <td style="background:var(--table-row-even);border-right:2px solid var(--table-border);">${escapeHtml(line.totalinvoicedqty)}</td>
                    <td style="background:var(--table-row-even);text-align:center;">
                      ${hasDel && hasTrn ? linkedImg : ''}
                    </td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnconsignmentid)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trndelnoteno)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnproduct)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnmass)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnclass)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnsize)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnvariety)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnbrand)}</td>
                    <td style="background:var(--table-row-even);filter:brightness(0.93);border-right:2px solid var(--table-border);">${escapeHtml(line.trnqtysent)}</td>
                    <td style="background:var(--table-row-even);text-align:center;">
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
        width: '85%',
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
              ${renderDeliveryNoteLinesTable(deliveryLines)}
            </div>
            <div style="flex: 1;">
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

// Cancel edit: revert row back to display mode
window.cancelEdit = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;

  // Restore original HTML from data attributes
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  const salesAmountCell = row.querySelector('.sales-amount-cell');

  if (row.dataset.originalPriceHtml) {
    priceCell.innerHTML = row.dataset.originalPriceHtml;
  }
  if (row.dataset.originalQtyHtml) {
    qtyCell.innerHTML = row.dataset.originalQtyHtml;
  }
  if (row.dataset.originalDiscountHtml) {
    discountCell.innerHTML = row.dataset.originalDiscountHtml;
  }
  if (row.dataset.originalSalesAmountHtml) {
    salesAmountCell.innerHTML = row.dataset.originalSalesAmountHtml;
  }

  // Clean up data attributes
  delete row.dataset.originalPriceHtml;
  delete row.dataset.originalQtyHtml;
  delete row.dataset.originalDiscountHtml;
  delete row.dataset.originalSalesAmountHtml;

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
            
            load_delivery_lines_table(delnoteNo)
            load_sales_lines_table(delnoteNo)
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
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
  const salesAmountCell = row.querySelector('.sales-amount-cell');
  
  // Store original HTML to revert on cancel
  row.dataset.originalPriceHtml = priceCell.innerHTML;
  row.dataset.originalQtyHtml = qtyCell.innerHTML;
  row.dataset.originalDiscountHtml = discountCell.innerHTML;
  row.dataset.originalSalesAmountHtml = salesAmountCell.innerHTML;

  const price = parseFloat(priceCell.innerText.replace('R', '').replace(/,/g, ''));
  const qty = parseFloat(qtyCell.innerText.replace(/,/g, ''));
  const discountPercent = parseFloat(discountCell.innerText.replace('%', '').replace(/,/g, '')) || 0;
  
  priceCell.innerHTML = `<input type="number" step="0.01" value="${price}" class="form-control">`;
  qtyCell.innerHTML = `<input type="number" step="1" value="${qty}" class="form-control">`;
  discountCell.innerHTML = `<div class="input-group"><input type="number" step="0.01" value="${discountPercent.toFixed(2)}" class="form-control"><span class="input-group-text">%</span></div>`;
  
  // Add event listeners for live calculation
  const priceInput = priceCell.querySelector('input');
  const qtyInput = qtyCell.querySelector('input');
  const discountInput = discountCell.querySelector('input');

  function updateSalesAmount() {
    const newPrice = parseFloat(priceInput.value) || 0;
    const newQty = parseFloat(qtyInput.value) || 0;
    const newDiscount = parseFloat(discountInput.value) || 0;
    const newSalesAmount = newPrice * newQty * (1 - newDiscount / 100);
    salesAmountCell.innerHTML = `R${formatNumber(newSalesAmount.toFixed(2))}`;
  }

  priceInput.addEventListener('input', updateSalesAmount);
  qtyInput.addEventListener('input', updateSalesAmount);
  discountInput.addEventListener('input', updateSalesAmount);

  // Replace edit button with submit button
  const actionsCell = row.querySelector('.sales-row-actions');
  actionsCell.innerHTML = `
    <button class="icon-btn icon-btn-edit" onclick="submitRow('${delnoteNo}', ${idx}, this, '${salesId}', '${lineId}')">
      <img src="/static/Image/check.png" alt="Submit">
    </button>
    <button class="icon-btn icon-btn-edit" onclick="cancelEdit('${delnoteNo}', ${idx}, this)">
      <img src="/static/Image/cancel.png" alt="Cancel">
    </button>
  `;
  
  // Mark row as being edited
  row.dataset.editing = 'true';
}

window.submitRow = function(delnoteNo, idx, btn, salesId, lineId) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) return;
  
  const priceCell = row.querySelector('.price-cell');
  const qtyCell = row.querySelector('.qty-cell');
  const discountCell = row.querySelector('.discount-cell');
    
  const price = parseFloat(priceCell.querySelector('input').value);
  const qty = parseFloat(qtyCell.querySelector('input').value);
  const discount = parseFloat(discountCell.querySelector('input').value);
  
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
  
  // Validate quantity before submitting
  // Get all sales rows for this specific delivery line (excluding the current sale being edited)
  const salesTable = document.querySelector('.sales-table');
  if (!salesTable) {
    Swal.fire({
      title: 'Error',
      text: 'Could not find sales table. Please try refreshing the page.',
      icon: 'error'
    });
    return;
  }
  
  const salesRows = salesTable.querySelectorAll('tbody tr');
  let totalCurrentSales = 0;
  
  salesRows.forEach(saleRow => {
    const saleLineId = saleRow.dataset.lineId;
    const saleSalesId = saleRow.dataset.salesId;
    
    // Only count sales for this line, excluding the current sale being edited
    if (saleLineId == finalLineId && saleSalesId != salesId) {
      const saleQty = parseInt(saleRow.querySelector('.qty-cell').textContent.replace(/,/g, '')) || 0;
      totalCurrentSales += saleQty;
    }
  });
  
  // Get the delivery line quantity from the delivery lines table
  const deliveryLineRow = document.querySelector(`tr[data-line-id="${finalLineId}"]`);
  if (!deliveryLineRow) {
    Swal.fire({
      title: 'Error',
      text: 'Could not find delivery line information. Please try refreshing the page.',
      icon: 'error'
    });
    return;
  }
  
  const quantitySent = parseInt(deliveryLineRow.querySelector('td:nth-child(4) .quantity-display').textContent.replace(/,/g, ''));
  const totalSalesAfterEdit = totalCurrentSales + qty;
  
  if (totalSalesAfterEdit > quantitySent) {
    Swal.fire({
      title: 'Validation Error',
      text: `Total sales quantity (${totalSalesAfterEdit}) cannot exceed quantity sent (${quantitySent}). Please reduce the quantity.`,
      icon: 'error'
    });
    return;
  }
  
  // If validation passes, proceed with submission
  const saleData = {
    lineId: finalLineId,  // This matches the backend's expected field name
    salesId: salesId,
    date: row.querySelector('td:first-child').innerText,
    price: price,
    quantity: qty,
    discount: discount,
    destroyed: false
  };
  console.log(saleData)
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

// Function to handle product change
window.changeProduct = function(lineId, currentProduct, delNoteNo) {
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
            allowClear: true,
            matcher: productMatcher
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
                load_sales_lines_table(delNoteNo)
                load_delivery_lines_table(delNoteNo)
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

// Function to handle Production Unit change
window.changeProductionUnit = function(lineId, currentProdUnit, delNoteNo) {
  // Fetch production units from the server
  fetch('/api/production_units')
    .then(response => response.json())
    .then(units => {
      // Create the modal HTML with searchable dropdown
      const modalHtml = `
        <div style="text-align: left;">
          <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155;">Current Production Unit</label>
            <div style="padding: 0.8em; background: #f8fafc; border-radius: 8px; color: #64748b;">
              ${currentProdUnit}
            </div>
          </div>
          <div style="margin-bottom: 1rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155;">New Production Unit</label>
            <select id="prodUnitSelect" class="form-select" style="width: 100%;">
              <option value="">Select a production unit...</option>
              ${units.map(u => `<option value="${u.UnitId}">${u.UnitName}</option>`).join('')}
            </select>
          </div>
        </div>
      `;

      // Initialize Select2 on the dropdown
      Swal.fire({
        title: 'Change Production Unit',
        html: modalHtml,
        showCancelButton: true,
        confirmButtonText: 'Save',
        cancelButtonText: 'Cancel',
        width: 600,
        didOpen: () => {
          // Initialize Select2
          $('#prodUnitSelect').select2({
            dropdownParent: $('.swal2-container'),
            width: '100%',
            placeholder: 'Search for a production unit...',
            allowClear: true
          });
        },
        preConfirm: () => {
          const selectedUnit = document.getElementById('prodUnitSelect').value;
          if (!selectedUnit) {
            Swal.showValidationMessage('Please select a production unit');
            return false;
          }
          return selectedUnit;
        }
      }).then((result) => {
        if (result.isConfirmed) {
          // Save the new production unit
          fetch('/api/save_production_unit', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              line_id: lineId,
              unit_id: result.value
            })
          })
          .then(response => response.json())
          .then(data => {
            if (data.message) {
              Swal.fire({
                title: 'Success!',
                text: 'Production unit has been updated successfully.',
                icon: 'success',
                timer: 1500,
                showConfirmButton: false
              }).then(() => {
                // Refresh the delivery table
                load_delivery_lines_table(delNoteNo)
              });
            } else {
              throw new Error(data.error || 'Failed to update production unit');
            }
          })
          .catch(error => {
            Swal.fire({
              title: 'Error',
              text: error.message || 'Failed to update production unit',
              icon: 'error'
            });
          });
        }
      });
    })
    .catch(error => {
      console.error('Error fetching production units:', error);
      Swal.fire({
        title: 'Error',
        text: 'Failed to load production units',
        icon: 'error'
      });
    });
};


// Placeholder for delete (implement backend as needed)
window.deleteRow = function(delnoteNo, idx, btn) {
  const row = document.getElementById(`row-${delnoteNo}-${idx}`);
  if (!row) {
    console.error('Row not found');
    return;
  }

  // Get the sales ID from the row data attribute
  const salesId = row.getAttribute('data-sales-id');
  if (!salesId) {
    console.error('Sales ID not found');
    return;
  }

  // Show confirmation dialog
  Swal.fire({
    title: 'Delete Sale',
    text: 'Are you sure you want to delete this sale? This action cannot be undone.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'Yes, delete it',
    cancelButtonText: 'Cancel',
    confirmButtonColor: '#dc2626',
    cancelButtonColor: '#6b7280'
  }).then((result) => {
    if (result.isConfirmed) {
      // Call the backend delete endpoint
      fetch(`/delete_sales_entry/${salesId}`, {
        method: 'DELETE'
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Remove the row from the DOM
          row.remove();
          
          // Show success message
          Swal.fire({
            title: 'Success!',
            text: 'Sale has been deleted successfully.',
            icon: 'success',
            timer: 1500,
            showConfirmButton: false
          }).then(() => {
            load_delivery_lines_table(delnoteNo)
          });
        } else {
          throw new Error(data.message || 'Failed to delete sale');
        }
      })
      .catch(error => {
        console.error('Error deleting sale:', error);
        Swal.fire({
          title: 'Error',
          text: error.message || 'An error occurred while deleting the sale.',
          icon: 'error'
        });
      });
    }
  });
}

