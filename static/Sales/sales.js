

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
  if (!dockets.length) return '<em>No import sales</em>';
  
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
              <h4>Sales Lines</h4>
              ${renderDeliveryNoteLinesTable(deliveryLines)}
            </div>
            <div style="flex: 1;">
              <h4>Imported Sales</h4>
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