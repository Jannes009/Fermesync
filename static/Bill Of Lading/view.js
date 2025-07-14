
function addSale(delNoteNo) {
    // First modal - Select line
    fetch(`/api/available-lines/${delNoteNo}`)
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
            title: '<span style="font-size:1.3em;font-weight:700;color:#2563eb;">Select Product Line</span>',
            html: `
                <div style="text-align: left;">
                    <div class="line-selection" style="max-height: 400px; overflow-y: auto; margin-top: 1rem;">
                        ${linesHtml}
                    </div>
                </div>
            `,
            width: 600,
            showCancelButton: true,
            confirmButtonText: 'Next',
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
                        window.selectedLine = {
                            lineId: line.dataset.lineId,
                            product: line.dataset.product,
                            available: parseInt(line.dataset.available)
                        };
                    });
                });
            },
            preConfirm: () => {
                if (!window.selectedLine) {
                    Swal.showValidationMessage('Please select a product line');
                    return false;
                }
                return window.selectedLine;
            }
        }).then((result) => {
            if (result.isConfirmed) {
                showSaleDetailsModal(result.value, delNoteNo);
            }
        });
    });
}

function showSaleDetailsModal(selectedLine, delNoteNo) {
    Swal.fire({
        title: '<span style="font-size:1.3em;font-weight:700;color:#2563eb;">Enter Sale Details</span>',
        html: `
            <div style="text-align: left;">
                <div style="margin-bottom: 1.5rem;">
                    <div style="font-weight: 600; color: #334155; margin-bottom: 0.5em;">Product</div>
                    <div style="padding: 0.8em; background: #f8fafc; border-radius: 8px; color: #2563eb;">
                        ${selectedLine.product}
                    </div>
                </div>
                <div style="margin-bottom: 1.5rem;">
                    <div style="font-weight: 600; color: #334155; margin-bottom: 0.5em;">Available Quantity</div>
                    <div style="padding: 0.8em; background: #f8fafc; border-radius: 8px; color: #2563eb;">
                        ${selectedLine.available} bags
                    </div>
                </div>
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
                                <td><input type="number" class="form-control" id="saleAmount" step="0.01"></td>
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
        width: 1400,
        showCancelButton: true,
        confirmButtonText: 'Submit',
        cancelButtonText: 'Back',
        showCloseButton: true,
        didOpen: () => {
            // Live calculation
            const qtyInput = document.getElementById('saleQty');
            const priceInput = document.getElementById('salePrice');
            const discountInput = document.getElementById('saleDiscount');
            const amountInput = document.getElementById('saleAmount');
            
            function updateAmount() {
                const qty = parseFloat(qtyInput.value) || 0;
                const price = parseFloat(priceInput.value) || 0;
                const discount = parseFloat(discountInput.value) || 0;
                const amount = qty * price * (1 - discount / 100);
                amountInput.value = amount.toFixed(2);
            }
            
            function updatePrice() {
                const qty = parseFloat(qtyInput.value) || 0;
                const amount = parseFloat(amountInput.value) || 0;
                const discount = parseFloat(discountInput.value) || 0;
                if (qty > 0) {
                    const price = amount / (qty * (1 - discount / 100));
                    priceInput.value = price.toFixed(2);
                }
            }
            
            qtyInput.addEventListener('input', updateAmount);
            priceInput.addEventListener('input', updateAmount);
            discountInput.addEventListener('input', updateAmount);
            amountInput.addEventListener('input', updatePrice);
        },
        preConfirm: () => {
            const entries = document.querySelectorAll('.sales-entries-list tr');
            if (entries.length === 0) {
                Swal.showValidationMessage('Please add at least one sale entry');
                return false;
            }

            let totalQty = 0;
            const salesEntries = Array.from(entries).map(entry => {
                const cells = entry.cells;
                const qty = parseInt(cells[1].textContent);
                totalQty += qty;
                
                return {
                    lineId: selectedLine.lineId,
                    date: cells[0].textContent,
                    quantity: qty,
                    price: parseFloat(cells[2].textContent.replace('R', '')),
                    discount: parseFloat(cells[3].textContent),
                    discountAmnt: parseFloat(cells[4].textContent.replace('R', '')) * parseFloat(cells[3].textContent) / 100,
                    amount: parseFloat(cells[4].textContent.replace('R', '')),
                    destroyed: cells[5].textContent === 'Yes',
                    salesId: null
                };
            });

            if (totalQty > selectedLine.available) {
                Swal.showValidationMessage(`Total quantity (${totalQty}) cannot exceed available quantity (${selectedLine.available})`);
                return false;
            }

            return salesEntries;
        }
    }).then((result) => {
        if (result.isConfirmed) {
            // Submit the sales
            fetch('/submit_sales_entries', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    salesEntries: result.value
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh the sales table and counts
                    load_delivery_lines_table(delNoteNo);
                    load_sales_lines_table(delNoteNo)
                    updateCountsDisplay(delNoteNo);
                    const Toast = Swal.mixin({
                        toast: true,
                        position: 'top-end',
                        showConfirmButton: false,
                        timer: 3000,
                        timerProgressBar: true,
                        didOpen: (toast) => {
                            toast.addEventListener('mouseenter', Swal.stopTimer)
                            toast.addEventListener('mouseleave', Swal.resumeTimer)
                        }
                    });

                    Toast.fire({
                        icon: 'success',
                        title: 'Sales added successfully'
                    })
                } else {
                    Swal.fire({
                        title: 'Error',
                        text: data.message || 'Failed to add sales.',
                        icon: 'error'
                    });
                }
            })
            .catch(error => {
                Swal.fire({
                    title: 'Error',
                    text: 'An error occurred while submitting the sales.',
                    icon: 'error'
                });
            });
        } else if (result.dismiss === Swal.DismissReason.cancel) {
            // Go back to line selection
            addSale(delNoteNo);
        }
    });
}

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
    const amount = parseFloat(document.getElementById('saleAmount').value);
    const destroy = document.getElementById('saleDestroy').checked;

    if (!date || !qty || (!price && !amount)) {
        Swal.showValidationMessage('Please fill in all required fields');
        return;
    }

    // Calculate final amount if price was entered, or final price if amount was entered
    const finalAmount = amount || (qty * price * (1 - discount / 100));
    const finalPrice = price || (finalAmount / (qty * (1 - discount / 100)));

    const entryHtml = `
        <tr>
            <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${date}</td>
            <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${qty}</td>
            <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">R${finalPrice.toFixed(2)}</td>
            <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">${discount}%</td>
            <td style="padding: 0.8em 1em; border-bottom: 1px solid #f0f4f8;">R${finalAmount.toFixed(2)}</td>
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
    document.getElementById('saleAmount').value = '';
    document.getElementById('saleDestroy').checked = false;
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
    document.getElementById('totalSalesAmount').textContent = `R${totalAmount.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

// Function to update the counts display
function updateCountsDisplay(delnoteNo) {
    fetch(`/api/update-counts/${delnoteNo}`)
        .then(response => response.json())
        .then(data => {
            // Update the badges
            const linkedBadge = document.querySelector(`[onclick="showLinkedModal('${delnoteNo}')"]`);
            const matchedBadge = document.querySelector(`[onclick="showMatchedModal('${delnoteNo}')"]`);

            if (linkedBadge) {
                linkedBadge.textContent = `Linked: ${data.linked_count}`;
            }
            if (matchedBadge) {
                matchedBadge.textContent = `Matched: ${data.matched_count}`;
            }
        })
        .catch(error => {
            console.error('Error updating counts:', error);
        });
}

// Function to handle delivery line selection and sales filtering
window.selectDeliveryLine = function(row, lineId) {
    const btn = document.getElementById('editQuantitiesBtn');
    if (btn && btn.classList.contains('editing')) {
        // In edit mode, do nothing
        return;
    }
    // Remove selected class from all rows
    document.querySelectorAll('.delivery-line').forEach(r => {
        r.classList.remove('selected');
    });
    
    // Add selected class to clicked row
    row.classList.add('selected');
    
    // Show clear filter button
    const clearFilterBtn = document.getElementById('clearFilterBtn');
    if (clearFilterBtn) {
        clearFilterBtn.style.display = '';
    }
    
    // Filter sales table
    const salesTable = document.querySelector('.sales-table');
    if (!salesTable) return;
    
    const rows = salesTable.querySelectorAll('tbody tr');
    let hasVisibleRows = false;
    
    rows.forEach(saleRow => {
        const saleLineId = saleRow.dataset.lineId;
        if (saleLineId === lineId) {
            saleRow.style.display = '';
            hasVisibleRows = true;
        } else {
            saleRow.style.display = 'none';
        }
    });
    
    // Show/hide totals row based on visibility
    const totalsRow = salesTable.querySelector('tfoot tr');
    if (totalsRow) {
        totalsRow.style.display = hasVisibleRows ? '' : 'none';
    }
    
    // Update totals for visible rows only
    if (hasVisibleRows) {
        updateFilteredTotals();
    }
};

// Function to update totals for filtered rows
function updateFilteredTotals() {
    const salesTable = document.querySelector('.sales-table');
    if (!salesTable) return;
    
    const visibleRows = Array.from(salesTable.querySelectorAll('tbody tr')).filter(row => row.style.display !== 'none');
    
    // Calculate totals
    const totals = visibleRows.reduce((acc, row) => {
        const cells = row.cells;
        acc.qty += parseInt(cells[2].textContent.replace(/,/g, '')) || 0;
        acc.discount += parseFloat(cells[4].textContent.replace('R', '').replace(/,/g, '')) || 0;
        acc.gross += parseFloat(cells[5].textContent.replace('R', '').replace(/,/g, '')) || 0;
        acc.net += parseFloat(cells[7].textContent.replace('R', '').replace(/,/g, '')) || 0;
        return acc;
    }, { qty: 0, discount: 0, gross: 0, net: 0 });
    
    // Update totals row
    const totalsRow = salesTable.querySelector('tfoot tr');
    if (totalsRow) {
        totalsRow.querySelector('.total-qty').textContent = totals.qty.toLocaleString('en-ZA');
        totalsRow.querySelector('.total-discount').textContent = `R${totals.discount.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        totalsRow.querySelector('.total-gross').textContent = `R${totals.gross.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        totalsRow.querySelector('.total-net').textContent = `R${totals.net.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
}

// Update clearSalesFilter to hide the clear filter button
window.clearSalesFilter = function() {
    // Remove selected class from all rows
    document.querySelectorAll('.delivery-line').forEach(r => {
        r.classList.remove('selected');
    });
    
    // Hide clear filter button
    const clearFilterBtn = document.getElementById('clearFilterBtn');
    if (clearFilterBtn) {
        clearFilterBtn.style.display = 'none';
    }
    
    // Show all sales rows
    const salesTable = document.querySelector('.sales-table');
    if (!salesTable) return;
    
    const rows = salesTable.querySelectorAll('tbody tr');
    rows.forEach(row => {
        row.style.display = '';
    });
    
    // Show totals row
    const totalsRow = salesTable.querySelector('tfoot tr');
    if (totalsRow) {
        totalsRow.style.display = '';
    }
    
    // Update totals for all rows
    updateFilteredTotals();
};

// Function to handle delivery header editing
window.editDeliveryHeader = function(delnoteNo) {
    // First check Transport PO status
    fetch(`/api/transport-po-status/${delnoteNo}`)
        .then(response => response.json())
        .then(poStatus => {
            // Fetch current header data
            fetch(`/api/delivery-header/${delnoteNo}`)
                .then(response => response.json())
                .then(header => {
                    // Fetch dropdown options
                    Promise.all([
                        fetch('/api/agents').then(r => r.json()),
                        fetch('/api/markets').then(r => r.json()),
                        fetch('/api/transporters').then(r => r.json())
                    ]).then(([agents, markets, transporters]) => {
                // Create the modal HTML with improved styling
                const isProcessed = poStatus.isProcessed;
                const transportDisabled = isProcessed ? 'disabled' : '';
                const transportStyle = isProcessed ? 'padding: 0.6rem; border-radius: 6px; border: 1px solid #e2e8f0; width: 100%; background-color: #f3f4f6; color: #6b7280;' : 'padding: 0.6rem; border-radius: 6px; border: 1px solid #e2e8f0; width: 100%;';
                
                const modalHtml = `
                    <div style="text-align: left; padding: 1rem;">
                        ${isProcessed ? `
                        <div style="margin-bottom: 1.5rem; padding: 1rem; background-color: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px;">
                            <div style="display: flex; align-items: center; gap: 0.5rem;">
                                <span style="color: #d97706; font-size: 1.2em;">⚠️</span>
                                <span style="color: #92400e; font-weight: 600;">Transport PO Processed</span>
                            </div>
                            <p style="color: #92400e; margin: 0.5rem 0 0 0; font-size: 0.9rem;">
                                The Transport PO has been processed. Transporter and Transport Cost cannot be modified.
                            </p>
                        </div>
                        ` : ''}
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Delivery Note No</label>
                            <input type="text" id="deliveryNoteNo" class="form-control" value="${header.delnoteno}" 
                                   style="padding: 0.6rem; border-radius: 6px; border: 1px solid #e2e8f0; width: 100%;">
                        </div>
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Delivery Date</label>
                            <input type="date" id="deliveryDate" class="form-control" value="${header.deldate}" 
                                   style="padding: 0.6rem; border-radius: 6px; border: 1px solid #e2e8f0; width: 100%;">
                        </div>
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Agent</label>
                            <select id="agentSelect" class="form-select" style="width: 100%;">
                                <option value="">Select an agent...</option>
                                ${agents.map(a => `<option value="${a.DCLink}" ${a.DCLink === header.deliclientid ? 'selected' : ''}>${a.display_name}</option>`).join('')}
                            </select>
                        </div>
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Packhouse</label>
                            <select id="marketSelect" class="form-select" style="width: 100%;">
                                <option value="">Select a packhouse...</option>
                                ${markets.map(m => `<option value="${m.WhseLink}" ${m.WhseLink === header.delmarketid ? 'selected' : ''}>${m.display_name}</option>`).join('')}
                            </select>
                        </div>
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Total Quantity (Bags)</label>
                            <input type="number" id="totalQuantity" class="form-control" value="${header.delquantitybags || 0}"
                                   style="padding: 0.6rem; border-radius: 6px; border: 1px solid #e2e8f0; width: 100%;">
                        </div>
                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Transporter</label>
                            ${isProcessed ? `
                                <div style="padding: 0.8em; background: #f8fafc; border-radius: 8px; color: #2563eb; border: 1px solid #e2e8f0;">
                                    ${transporters.find(t => t.TransporterAccount === header.deltransporter)?.display_name || 'Unknown Transporter'}
                                </div>
                            ` : `
                                <select id="transporterSelect" class="form-select" style="width: 100%;">
                                    <option value="">Select a transporter...</option>
                                    ${transporters.map(t => `<option value="${t.TransporterAccount}" ${t.TransporterAccount === header.deltransporter ? 'selected' : ''}>${t.display_name}</option>`).join('')}
                                </select>
                            `}
                        </div>

                        <div style="margin-bottom: 1.5rem;">
                            <label style="display: block; margin-bottom: 0.5rem; font-weight: 600; color: #334155; font-size: 0.95rem;">Transport Cost</label>
                            <input type="number" id="transportCost" class="form-control" value="${header.deltransportcostexcl || 0}"
                                   style="${transportStyle}" ${transportDisabled}>
                        </div>
                    </div>
                `;

                // Show the modal with improved styling
                Swal.fire({
                    title: '<span style="font-size:1.3em;font-weight:700;color:#2563eb;">Edit Delivery Note Header</span>',
                    html: modalHtml,
                    showCancelButton: true,
                    confirmButtonText: 'Save Changes',
                    cancelButtonText: 'Cancel',
                    width: 600,
                    customClass: {
                        container: 'delivery-header-modal',
                        popup: 'delivery-header-modal-popup',
                        title: 'delivery-header-modal-title',
                        confirmButton: 'btn btn-primary',
                        cancelButton: 'btn btn-secondary'
                    },
                    didOpen: () => {
                        // Initialize Select2 for dropdowns with improved styling
                        const selectElements = isProcessed ? 
                            $('#agentSelect, #marketSelect') : 
                            $('#agentSelect, #marketSelect, #transporterSelect');
                        
                        selectElements.select2({
                            dropdownParent: $('.swal2-container'),
                            width: '100%',
                            placeholder: 'Select an option...',
                            allowClear: true,
                            theme: 'bootstrap-5'
                        }).on('select2:open', () => {
                            document.querySelector('.select2-container--open').style.zIndex = 9999;
                        });
                    },
                    preConfirm: () => {
                        return {
                            delnoteno: document.getElementById('deliveryNoteNo').value,
                            deldate: document.getElementById('deliveryDate').value,
                            deliclientid: document.getElementById('agentSelect').value,
                            delmarketid: document.getElementById('marketSelect').value,
                            deltransporter: isProcessed ? header.deltransporter : document.getElementById('transporterSelect').value,
                            delquantitybags: parseInt(document.getElementById('totalQuantity').value) || 0,
                            deltransportcostexcl: parseFloat(document.getElementById('transportCost').value) || 0
                        };
                    }
                }).then((result) => {
                    if (result.isConfirmed) {
                        // Save the changes
                        fetch(`/api/save-delivery-header/${delnoteNo}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify(result.value)
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                const newDelNoteNo = result.value.delnoteno;
                                if (newDelNoteNo && newDelNoteNo !== delnoteNo) {
                                    window.location.href = `/delivery-note/${newDelNoteNo}`;
                                } else {
                                    window.location.reload();
                                }
                            } else {
                                throw new Error(data.message || 'Failed to update delivery note header');
                            }
                        })
                        .catch(error => {
                            Swal.fire({
                                title: 'Error',
                                text: error.message || 'Failed to update delivery note header',
                                icon: 'error'
                            });
                        });
                    }
                });
            });
        })
                                .catch(error => {
                            console.error('Error fetching header data:', error);
                            Swal.fire({
                                title: 'Error',
                                text: 'Failed to load delivery note header data',
                                icon: 'error'
                            });
                        });
                })
                .catch(error => {
                    console.error('Error fetching Transport PO status:', error);
                    Swal.fire({
                        title: 'Error',
                        text: 'Failed to load Transport PO status',
                        icon: 'error'
                    });
                });
};

// Function to save quantity changes
window.saveQuantityChanges = function() {
    const quantities = {};
    let total = 0;
    let validationErrors = [];
    let new_line_info = null;

    // Get all quantity inputs
    document.querySelectorAll('.quantity-input').forEach(input => {
        const lineId = input.dataset.lineId;
        const newQty = parseInt(input.value) || 0;
        const minQty = parseInt(input.dataset.sold);
        const productDesc = input.closest('tr').querySelector('td:nth-child(2)').textContent.trim();
        
        if (newQty < minQty) {
            validationErrors.push(`Line ${lineId} (${productDesc}): Minimum quantity is ${minQty} bags (${input.dataset.sold} sold)`);
        }
        
        quantities[lineId] = newQty;
        total += newQty;
    });
    
    // If a new line exists, collect its info
    const newLine = document.querySelector('tr[data-line-id="new"]');
    if (newLine) {
        const productSelect = newLine.querySelector('.product-select');
        const product_id = productSelect ? productSelect.value : null;
        const prod_unit = newLine.querySelector('td:nth-child(3)')?.textContent?.trim() || '';
        const qtyInput = newLine.querySelector('.quantity-input');
        const quantity = qtyInput ? parseInt(qtyInput.value) || 0 : 0;

        // Get the delivery note number from the header
        let del_note_no = null;
        const header = document.querySelector('.delivery-header h1');
        if (header) {
            const match = header.textContent.match(/#(\d+)/);
            if (match) del_note_no = match[1];
        }

        new_line_info = {
            product_id,
            prod_unit,
            quantity,
            del_note_no
        };
    }
    
    if (validationErrors.length > 0) {
        Swal.fire({
            title: 'Validation Error',
            html: `
                <div style="text-align: left;">
                    <p style="margin-bottom: 1rem;">The following lines have quantities below their minimum allowed values:</p>
                    <ul style="list-style-type: none; padding-left: 0;">
                        ${validationErrors.map(error => `<li style="margin-bottom: 0.5rem; color: #dc2626;">• ${error}</li>`).join('')}
                    </ul>
                </div>
            `,
            icon: 'error',
            confirmButtonText: 'OK'
        });
        return;
    }
    
    const headerQty = parseInt(document.querySelector('.delivery-header .delivery-grid div:nth-child(3) p').textContent) || 0;
    
    if (total !== headerQty) {
        Swal.fire({
            title: 'Validation Error',
            html: `
                <div style="text-align: left;">
                    <p>The total quantity of all lines (${total} bags) must equal the delivery note total (${headerQty} bags).</p>
                    <p style="margin-top: 0.5rem;">Please adjust the quantities to match the total.</p>
                </div>
            `,
            icon: 'error',
            confirmButtonText: 'OK'
        });
        return;
    }
    
    // Save the changes
    fetch('/api/update-line-quantities', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            quantities: quantities,
            new_line_info: new_line_info
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload the delivery lines table to reflect new/updated lines
            const header = document.querySelector('.delivery-header h1');
            let delNoteNo = null;
            if (header) {
                const match = header.textContent.match(/#(\d+)/);
                if (match) delNoteNo = match[1];
            }
            if (delNoteNo) {
                load_delivery_lines_table(delNoteNo);
            }

            // Switch back to display mode
            const btn = document.getElementById('editQuantitiesBtn');
            btn.innerHTML = '<i class="fas fa-edit"></i> Edit Quantities';
            btn.classList.remove('editing');
            document.querySelectorAll('.quantity-display').forEach(display => {
                display.style.display = '';
            });
            document.querySelectorAll('.quantity-input').forEach(input => {
                input.style.display = 'none';
            });

            // Remove the button container and restore edit button to original position
            const buttonContainer = document.querySelector('.quantity-edit-buttons');
            if (buttonContainer) {
                buttonContainer.parentNode.replaceChild(btn, buttonContainer);
            }
            // Show Add Line button again
            const addLineBtn = document.getElementById('addLineBtn');
            if (addLineBtn) addLineBtn.style.display = '';
        } else {
            throw new Error(data.message || 'Failed to update line quantities');
        }
    })
    .catch(error => {
        Swal.fire({
            title: 'Error',
            text: error.message || 'Failed to update line quantities',
            icon: 'error'
        });
    });
};


// Add Delivery Line function for adding a new delivery note line
window.addDeliveryLine = function() {
    // Switch to edit mode if not already
    const btn = document.getElementById('editQuantitiesBtn');
    if (!btn.classList.contains('editing')) {
        window.toggleQuantityEdit();
    }

    // Fetch products for dropdown
    fetch('/api/products')
        .then(response => response.json())
        .then(products => {
            // Find the delivery lines table body
            const table = document.querySelector('.delivery-table table');
            if (!table) return;
            const tbody = table.querySelector('tbody');
            if (!tbody) return;

            // Get production unit from last line
            let lastProdUnit = '';
            const lastRow = tbody.querySelector('tr:last-child');
            if (lastRow) {
                lastProdUnit = lastRow.querySelector('td:nth-child(3)')?.textContent?.trim() || '';
            }

            // Create product dropdown HTML
            const productOptions = products.map(p => `<option value="${p.StockLink}">${p.display_name}</option>`).join('');

            // Create new row HTML
            const newRow = document.createElement('tr');
            newRow.className = 'delivery-line new-delivery-line';
            newRow.dataset.lineId = 'new';
            newRow.innerHTML = `
                <td>New</td>
                <td>
                    <select class="form-control product-select searchable-dropdown" style="width: 180px;">
                        <option value="">Select product...</option>
                        ${productOptions}
                    </select>
                </td>
                <td>${lastProdUnit}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="quantity-display" style="display:none"></span>
                        <input type="number" class="form-control quantity-input" style="width: 100px;" min="0" value="" data-line-id="new" data-sold="0" data-invoiced="0">
                    </div>
                </td>
                <td>0</td>
                <td>0</td>
            `;
            tbody.appendChild(newRow);

            // Initialize select2 for the new product dropdown with custom matcher
            $(newRow).find('.product-select').select2({
                width: '100%',
                dropdownParent: $(newRow),
                matcher: productMatcher
            });
        });
};

// --- Custom matcher for Select2 product dropdowns ---
function productMatcher(params, data) {
    if ($.trim(params.term) === '') {
        return data;
    }

    let searchTerms = params.term.toLowerCase().split(/\s+|-/); // Split by space or dash
    let optionText = data.text.toLowerCase();
    let optionWords = optionText.split(/\s+|-/); // Normalize the option text

    let matches = searchTerms.every(term =>
        optionWords.some(word => word.includes(term))
    );

    return matches ? data : null;
}

// Helper to add delete buttons in their own column in edit mode
function addDeleteButtonsToLines() {
    document.querySelectorAll('.delivery-line').forEach(row => {
        if (row.dataset.lineId === 'new') return;
        // check for sales
        const fourthColumnValue = parseFloat(row.cells[4]?.textContent || '0');

        if (fourthColumnValue > 0) return;
        // Only add if not already present
        if (!row.querySelector('.delete-line-btn')) {
            // Create a new td for the delete button
            const td = document.createElement('td');
            td.className = 'delete-line-td';
            td.style.textAlign = 'center';
            const btn = document.createElement('button');
            btn.className = 'delete-line-btn';
            btn.style.background = 'none';
            btn.style.border = 'none';
            btn.style.cursor = 'pointer';
            btn.title = 'Delete Line';
            btn.innerHTML = '<img src="/static/Image/recycle-bin.png" alt="Delete" style="width:22px;">';
            btn.onclick = function(e) {
                e.stopPropagation();
                const lineId = row.dataset.lineId;
                Swal.fire({
                    title: 'Delete Line',
                    text: 'Are you sure you want to delete this delivery line? This action cannot be undone.',
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonText: 'Yes, delete it',
                    cancelButtonText: 'Cancel',
                    confirmButtonColor: '#dc2626',
                    cancelButtonColor: '#6b7280'
                }).then((result) => {
                    if (result.isConfirmed) {
                        fetch(`/api/delete-delivery-line/${lineId}`, {
                            method: 'DELETE'
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                Swal.fire({
                                    title: 'Deleted!',
                                    text: 'The line has been deleted successfully.',
                                    icon: 'success',
                                    timer: 1200,
                                    showConfirmButton: false
                                });
                                row.remove();
                            } else {
                                Swal.fire({
                                    title: 'Error',
                                    text: data.message || 'Failed to delete the line.',
                                    icon: 'error'
                                });
                            }
                        })
                        .catch(error => {
                            Swal.fire({
                                title: 'Error',
                                text: 'An error occurred while deleting the line.',
                                icon: 'error'
                            });
                        });
                    }
                });
            };
            td.appendChild(btn);
            row.appendChild(td);
        }
    });

    // Add a header cell for the delete column if not present
    const table = document.querySelector('.delivery-table table');
    if (table) {
        const ths = table.querySelectorAll('thead tr th');
        const lastTh = ths[ths.length - 1];
        if (!table.querySelector('th.delete-line-header')) {
            const th = document.createElement('th');
            th.className = 'delete-line-header';
            th.style.textAlign = 'center';
            th.textContent = '';
            lastTh.parentNode.appendChild(th);
        }
    }
}

// Helper to remove delete buttons and their column
function removeDeleteButtonsFromLines() {
    // Remove the delete button column from each row
    document.querySelectorAll('.delivery-line .delete-line-td').forEach(td => td.remove());
    // Remove the delete column header
    document.querySelectorAll('th.delete-line-header').forEach(th => th.remove());
}

// Update toggleQuantityEdit to add/remove delete buttons
window.toggleQuantityEdit = function() {
    const btn = document.getElementById('editQuantitiesBtn');
    const addLineBtn = document.getElementById('addLineBtn');
    const isEditing = btn.classList.contains('editing');
    
    if (isEditing) {
        saveQuantityChanges();
        if (addLineBtn) addLineBtn.style.display = '';
        removeDeleteButtonsFromLines();
    } else {
        // Switch to edit mode
        btn.innerHTML = '<i class="fas fa-check"></i> Save Changes';
        btn.classList.add('editing');
        document.querySelectorAll('.quantity-display').forEach(display => {
            display.style.display = 'none';
        });
        document.querySelectorAll('.quantity-input').forEach(input => {
            input.style.display = '';
        });
        if (addLineBtn) addLineBtn.style.display = 'none';
        addDeleteButtonsToLines();

        // Create button container if it doesn't exist
        if (!document.querySelector('.quantity-edit-buttons')) {
            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'quantity-edit-buttons';
            buttonContainer.style.display = 'flex';
            buttonContainer.style.gap = '0.5rem';
            buttonContainer.style.alignItems = 'center';

            // Create cancel button
            const cancelBtn = document.createElement('button');
            cancelBtn.id = 'cancelQuantityEditBtn';
            cancelBtn.className = 'sales-btn';
            cancelBtn.style.backgroundColor = '#dc2626';
            cancelBtn.style.color = '#fff';
            cancelBtn.innerHTML = '<i class="fas fa-times"></i> Cancel';
            cancelBtn.onclick = cancelQuantityEdit;

            // Replace edit button with container and add both buttons
            btn.parentNode.replaceChild(buttonContainer, btn);
            buttonContainer.appendChild(btn);
            buttonContainer.appendChild(cancelBtn);
        }
    }
};

// Update cancelQuantityEdit to remove delete buttons
window.cancelQuantityEdit = function() {
    // Restore original values and switch back to display mode
    document.querySelectorAll('.quantity-input').forEach(input => {
        const display = input.previousElementSibling;
        input.value = display.textContent.replace(/,/g, '');
    });

    // Remove any new line row
    const newLine = document.querySelector('tr[data-line-id="new"]');
    if (newLine) newLine.remove();

    // Get the button container and edit button
    const buttonContainer = document.querySelector('.quantity-edit-buttons');
    const editBtn = document.getElementById('editQuantitiesBtn');
    const addLineBtn = document.getElementById('addLineBtn');
    
    // Restore edit button to original state
    editBtn.innerHTML = '<i class="fas fa-edit"></i> Edit Quantities';
    editBtn.classList.remove('editing');
    
    // Show displays and hide inputs
    document.querySelectorAll('.quantity-display').forEach(display => {
        display.style.display = '';
    });
    document.querySelectorAll('.quantity-input').forEach(input => {
        input.style.display = 'none';
    });

    // Remove the button container and restore edit button to original position
    if (buttonContainer) {
        buttonContainer.parentNode.replaceChild(editBtn, buttonContainer);
    }
    // Show Add Line button again
    if (addLineBtn) addLineBtn.style.display = '';
    removeDeleteButtonsFromLines();
};
