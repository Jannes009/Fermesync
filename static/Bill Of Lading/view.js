function refreshSalesTable(delNoteNo) {
    fetch(`/api/refresh-sales/${delNoteNo}`)
        .then(response => response.text())
        .then(html => {
            document.getElementById('salesTableContainer').innerHTML = html;
        })
        .catch(error => {
            console.error('Error refreshing sales table:', error);
        });
}

function deleteRow(delNoteNo, index, button) {
    const row = button.closest('tr');
    const salesId = row.dataset.salesId;

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
            fetch(`/delete_sales_entry/${salesId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        title: 'Deleted!',
                        text: 'The sale has been deleted successfully.',
                        icon: 'success',
                        timer: 1500,
                        showConfirmButton: false
                    }).then(() => {
                        refreshSalesTable(delNoteNo);
                    });
                } else {
                    Swal.fire({
                        title: 'Error',
                        text: data.message || 'Failed to delete the sale.',
                        icon: 'error'
                    });
                }
            })
            .catch(error => {
                Swal.fire({
                    title: 'Error',
                    text: 'An error occurred while deleting the sale.',
                    icon: 'error'
                });
            });
        }
    });
}

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
                    refreshSalesTable(delNoteNo);
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
                console.error('Error submitting sales:', error);
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
    document.getElementById('totalSalesAmount').textContent = `R${totalAmount.toFixed(2)}`;
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
