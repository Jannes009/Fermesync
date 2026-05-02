
document.addEventListener("DOMContentLoaded", async () => {
    const list = document.getElementById("incomplete-issues-list");
    if (list) {
        loadIncompleteIssues();
    }
});

async function loadIncompleteIssues() {
  const list = document.getElementById("incomplete-issues-list");
  if (!list) {
      return;
  }
  list.innerHTML = "<i>Loading...</i>";

  try {


      const serverIssues = await fetch("/inventory/SDK/incomplete_issues")
        .then(res => {
            if (!res.ok) {
                throw new Error(`Failed to fetch issues: ${res.status}`);
            }
            return res.json();
        })
        .then(data => data.issues || []);

    renderIssues(serverIssues);
  } catch (err) {
    console.error(err);
    list.innerHTML = "<i>Failed to load issues.</i>";
  }
}

function renderIssues(issues) {
  const list = document.getElementById("incomplete-issues-list");
  list.innerHTML = "";

  if (!issues.length) {
    list.innerHTML = "<i>No incomplete issues.</i>";
    return;
  }

  for (const issue of issues) {
    const div = document.createElement("div");
    div.classList.add("issue-card");

    div.innerHTML = `
      <h3>
        ${issue.IssueNo}
      </h3>
      <p><b>Date:</b> ${issue.IssueTimeStamp}</p>
      <p><b>Warehouse:</b> ${issue.WhseDescription}</p>
      <button class="btn-primary"
        onclick="startReturnWizard('${issue.IssueId}')">
        Process Return →
      </button>
    `;

    list.appendChild(div);
  }
}

// ============================================================================
//  RETURN WIZARD
// ============================================================================
async function fetchIssueLines(issueId) {
  try {

    let lines = await fetch(`/inventory/SDK/incomplete_issue_lines/${issueId}`)
      .then(async res => {
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Failed to fetch issue lines: ${res.status} ${text}`);
        }
        const data = await res.json();
        console.log("Raw lines data from server:", data);
        return data.issue_lines || [];
      });


    console.log(`Fetched ${lines.length} lines from server for issue ${issueId}`);
    return lines;
  } catch (error) {
    console.warn("Failed to fetch lines", error);
    return [];
  }
}

async function startReturnWizard(issueId) {
    // STEP 1: FETCH ISSUE LINES
    let products = await fetchIssueLines(issueId);
    if (!products.length) {
        Swal.fire("No Products", "No products found for this issue.", "warning");
        return;
    }

    // Build HTML list
    const prodHTML = products.map((p, i) => `
        <div class="input-card">
            <div class="input-header">
                <h4 class="input-product-name">${p.product_desc}</h4>
            </div>
            <div class="input-row">
                <div class="input-field-group">
                    <label class="input-label">Issued Quantity</label>
                    <div class="qty-display-box">
                        <span class="qty-display-value">${parseFloat(p.qty_issued).toFixed(2)}</span>
                        <span class="qty-display-unit">${p.uom_code || p.stocking_uom_code || ""}</span>
                    </div>
                </div>
                <div class="input-field-group input-active">
                    <label class="input-label">Quantity Returned</label>
                    <div class="input-wrapper">
                        <input id="ret_qty_${i}" 
                               type="number" 
                               class="return-qty-input" 
                               min="0" 
                               max="${p.qty_issued}"
                               placeholder="0"
                               step="0.01">
                        <span class="input-unit">${p.uom_code || p.stocking_uom_code || ""}</span>
                    </div>
                </div>
            </div>
        </div>
    `).join("");

    // STEP 2: ENTER RETURN QTY
    const qtyEntry = await Swal.fire({
        title: "Enter Quantities Returned",
        titleClass: "swal2-title-custom",
        width: 900,
        html: `
            <style>
                .swal2-html-container {
                    padding: 24px !important;
                }
                
                .input-cards-container {
                    display: grid;
                    gap: 16px;
                }
                
                .input-card {
                    padding: 16px;
                    border: 1px solid #e0e0e0;
                    border-radius: 10px;
                    background: #fafafa;
                    transition: all 0.2s ease;
                }
                
                .input-card:hover {
                    border-color: #b0bec5;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                    background: #ffffff;
                }
                
                .input-header {
                    margin-bottom: 12px;
                }
                
                .input-product-name {
                    margin: 0;
                    font-size: 1rem;
                    font-weight: 600;
                    color: #212121;
                }
                
                .input-row {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                }
                
                .input-field-group {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }
                
                .input-label {
                    font-size: 0.75rem;
                    color: #999;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    font-weight: 600;
                }
                
                .qty-display-box {
                    display: flex;
                    align-items: baseline;
                    gap: 8px;
                    padding: 12px;
                    background: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                }
                
                .qty-display-value {
                    font-size: 1.3rem;
                    font-weight: 700;
                    color: #212121;
                }
                
                .qty-display-unit {
                    font-size: 0.85rem;
                    color: #999;
                    font-weight: 500;
                }
                
                .input-active {
                    border-radius: 8px;
                    padding: 2px;
                }
                
                .input-wrapper {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 0 12px;
                    background: white;
                    border: 2px solid #1976d2;
                    border-radius: 8px;
                    transition: border-color 0.2s ease;
                }
                
                .input-wrapper:focus-within {
                    border-color: #1565c0;
                    box-shadow: 0 0 0 3px rgba(25, 118, 210, 0.1);
                }
                
                .return-qty-input {
                    flex: 1;
                    border: none;
                    outline: none;
                    font-size: 1.3rem;
                    font-weight: 700;
                    color: #212121;
                    padding: 10px 0;
                    background: transparent;
                }
                
                .return-qty-input::placeholder {
                    color: #ccc;
                }
                
                .input-unit {
                    font-size: 0.85rem;
                    color: #666;
                    font-weight: 500;
                    white-space: nowrap;
                }
            </style>
            <div class="input-cards-container">
                ${prodHTML}
            </div>
        `,
        confirmButtonText: "Next",
        confirmButtonClass: "swal2-confirm-custom",
        showCancelButton: true,
        cancelButtonText: "Cancel",
        cancelButtonClass: "swal2-cancel-custom",
        preConfirm: () => {
            const lines = [];

            for (let i = 0; i < products.length; i++) {
                const qty = Number(document.getElementById(`ret_qty_${i}`).value);

                if (qty < 0 || qty > products[i].qty_issued) {
                    Swal.showValidationMessage("Invalid qty for item #" + (i + 1));
                    return false;
                }
                lines.push({
                    product_link: products[i].product_link,
                    qty_issued: products[i].qty_issued,
                    qty_returned: qty
                });
            }
            return lines;
        }
    });
    
    if (!qtyEntry.value) return;
    const returnLines = qtyEntry.value;

    // STEP 3: CONFIRMATION
    const confirmHTML = returnLines.map(l => {
        const prod = products.find(p => p.product_link === l.product_link);
        const finalised = l.qty_issued - l.qty_returned;
        const hasNettIssued = prod.nett_issued !== null && prod.nett_issued !== undefined;
        const totalFinalised = hasNettIssued ? prod.nett_issued - l.qty_returned : null;
        const hasRecommended = prod.qty_recommended !== null && prod.qty_recommended !== undefined;
        const isOffByMoreThan10 = hasRecommended && hasNettIssued && Math.abs(totalFinalised - prod.qty_recommended) / prod.qty_recommended > 0.1;
        const warningClass = isOffByMoreThan10 ? 'product-card-warning' : '';
        const warningIcon = isOffByMoreThan10 ? '<span class="deviation-badge">⚠️ 10%+</span>' : '';
        
        // Build comparison section if we have nett_issued data
        const comparisonSection = hasNettIssued ? `
            <div class="qty-grid qty-grid-comparison">
                ${hasRecommended ? `
                    <div class="qty-item">
                        <span class="qty-label">Recommended</span>
                        <span class="qty-value">${parseFloat(prod.qty_recommended).toFixed(2)}</span>
                        <span class="qty-unit">${prod.uom_code}</span>
                    </div>
                ` : ''}
                <div class="qty-item highlight">
                    <span class="qty-label">Total Finalised</span>
                    <span class="qty-value">${parseFloat(totalFinalised).toFixed(2)}</span>
                    <span class="qty-unit">${prod.uom_code}</span>
                </div>
            </div>
        ` : '';
        
        return `
            <div class="product-card ${warningClass}">
                <div class="product-header">
                    <div class="product-name-section">
                        <h4 class="product-name">${prod.product_desc}</h4>
                    </div>
                    ${warningIcon}
                </div>
                <div class="qty-grid">
                    <div class="qty-item">
                        <span class="qty-label">Issued</span>
                        <span class="qty-value">${parseFloat(l.qty_issued).toFixed(2)}</span>
                        <span class="qty-unit">${prod.uom_code}</span>
                    </div>
                    <div class="qty-item">
                        <span class="qty-label">Returned</span>
                        <span class="qty-value">${parseFloat(l.qty_returned).toFixed(2)}</span>
                        <span class="qty-unit">${prod.uom_code}</span>
                    </div>
                    <div class="qty-item highlight">
                        <span class="qty-label">Finalised</span>
                        <span class="qty-value">${parseFloat(finalised).toFixed(2)}</span>
                        <span class="qty-unit">${prod.uom_code}</span>
                    </div>
                </div>
                ${comparisonSection}
            </div>
        `;
    }).join("");

    // Check for 10% deviation warnings
    let warningMessage = "";
    const deviations = returnLines.filter(l => {
        const prod = products.find(p => p.product_link === l.product_link);
        const hasNettIssued = prod.nett_issued !== null && prod.nett_issued !== undefined;
        if (!prod.qty_recommended || !hasNettIssued) return false;
        const totalFinalised = prod.nett_issued - l.qty_returned;
        return Math.abs(totalFinalised - prod.qty_recommended) / prod.qty_recommended > 0.1;
    });
    if (deviations.length > 0) {
        warningMessage = `<div class="return-warning-banner">
            <div class="warning-icon">⚠️</div>
            <div class="warning-content">
                <strong>Verification Required</strong>
                <p>${deviations.length} product(s) have finalised quantities that differ by more than 10% from the recommended amount.</p>
            </div>
        </div>`;
    }

    const confirmResult = await Swal.fire({
        title: "Confirm Return",
        titleClass: "swal2-title-custom",
        width: 900,
        html: `
            <style>
                .swal2-html-container {
                    padding: 24px !important;
                }
                
                .return-warning-banner {
                    display: flex;
                    gap: 16px;
                    padding: 16px;
                    background: linear-gradient(135deg, #fff5e6 0%, #fffbf0 100%);
                    border: 2px solid #ff9800;
                    border-radius: 12px;
                    margin-bottom: 24px;
                    align-items: flex-start;
                }
                
                .warning-icon {
                    font-size: 24px;
                    flex-shrink: 0;
                }
                
                .warning-content {
                    flex: 1;
                }
                
                .warning-content strong {
                    display: block;
                    color: #e65100;
                    font-size: 1rem;
                    margin-bottom: 4px;
                }
                
                .warning-content p {
                    margin: 0;
                    color: #bf360c;
                    font-size: 0.9rem;
                    line-height: 1.4;
                }
                
                .products-container {
                    display: grid;
                    gap: 16px;
                    max-height: 400px;
                    overflow-y: auto;
                    padding-right: 8px;
                }
                
                .products-container::-webkit-scrollbar {
                    width: 8px;
                }
                
                .products-container::-webkit-scrollbar-track {
                    background: #f1f1f1;
                    border-radius: 10px;
                }
                
                .products-container::-webkit-scrollbar-thumb {
                    background: #888;
                    border-radius: 10px;
                }
                
                .products-container::-webkit-scrollbar-thumb:hover {
                    background: #555;
                }
                
                .product-card {
                    padding: 12px;
                    border: 1px solid #e0e0e0;
                    border-radius: 10px;
                    background: #fafafa;
                    transition: all 0.2s ease;
                }
                
                .product-card:hover {
                    border-color: #b0bec5;
                    box-shadow: 0 3px 10px rgba(0,0,0,0.08);
                    background: #ffffff;
                }
                
                .product-card-warning {
                    border: 2px solid #ff9800;
                    background: linear-gradient(135deg, #fff9f5 0%, #fffef8 100%);
                }
                
                .product-card-warning:hover {
                    box-shadow: 0 3px 10px rgba(255,152,0,0.2);
                }
                
                .product-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 10px;
                    gap: 12px;
                }
                
                .product-name-section {
                    flex: 1;
                }
                
                .product-name {
                    margin: 0;
                    font-size: 0.98rem;
                    font-weight: 600;
                    color: #212121;
                }
                
                .deviation-badge {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
                    color: white;
                    padding: 5px 10px;
                    border-radius: 16px;
                    font-size: 0.72rem;
                    font-weight: 600;
                    white-space: nowrap;
                }
                
                .qty-grid {
                    display: grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap: 8px;
                }
                
                .qty-grid-comparison {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    margin-top: 10px;
                    padding-top: 10px;
                    border-top: 1px solid #e0e0e0;
                }
                
                .qty-item {
                    text-align: center;
                    padding: 10px;
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #e0e0e0;
                }
                
                .qty-item.highlight {
                    background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
                    border-color: #1976d2;
                    border-width: 2px;
                }
                
                .qty-label {
                    display: block;
                    font-size: 0.72rem;
                    color: #777;
                    text-transform: uppercase;
                    letter-spacing: 0.4px;
                    font-weight: 600;
                    margin-bottom: 4px;
                }
                
                .qty-value {
                    display: block;
                    font-size: 1.15rem;
                    font-weight: 700;
                    color: #212121;
                    margin-bottom: 2px;
                }
                
                .qty-unit {
                    display: block;
                    font-size: 0.75rem;
                    color: #666;
                    font-weight: 500;
                }
                
                .swal2-back-custom {
                    background-color: #757575;
                    border: 0;
                    color: white;
                    cursor: pointer;
                    font-size: 1rem;
                    font-weight: 600;
                    padding: 0.6rem 1.6rem;
                    border-radius: 0.25em;
                    transition: background-color 0.2s ease;
                    margin-right: auto;
                }
                
                .swal2-back-custom:hover {
                    background-color: #616161;
                }
            </style>
            ${warningMessage}
            <div class="products-container">
                ${confirmHTML}
            </div>
        `,
        confirmButtonText: "Submit Return",
        confirmButtonClass: "swal2-confirm-custom",
        showCancelButton: true,
        cancelButtonText: "Cancel",
        cancelButtonClass: "swal2-cancel-custom",
        didOpen: async () => {
            // Add back button to the confirm dialog
            const backBtn = document.createElement('button');
            backBtn.className = 'swal2-back-custom';
            backBtn.innerHTML = '← Back';
            backBtn.type = 'button';
            backBtn.onclick = async () => {
                // Close current modal and reopen the quantity entry step
                Swal.close();
                await startReturnWizard(issueId);
            };
            
            const footer = document.querySelector('.swal2-actions');
            if (footer) {
                footer.insertBefore(backBtn, footer.firstChild);
            }
        }
    });

    if (!confirmResult.isConfirmed) return;

    // STEP 4: SUBMIT TO BACKEND
    let loadingVisible = false;
    try {
        const payload = {
            issue_id: issueId,
            created_at: new Date().toISOString(),
            returns: returnLines
        };
        
        Swal.fire({
            title: "Processing return...",
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
                loadingVisible = true;
            }
        });
        
        const submit = await fetch("/inventory/process_return", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!submit.ok) {
            const text = await submit.text();
            throw new Error(`Server responded with ${submit.status}: ${text || "No details"}`);
        }

        const submitRes = await submit.json();

        if (loadingVisible) {
            Swal.close();
            loadingVisible = false;
        }

        if (submitRes.success) {
            Swal.fire("Success", "Return processed successfully!", "success");
            if (window.onStockIssueReturnSuccess) {
                window.onStockIssueReturnSuccess();
            } else {
                loadIncompleteIssues();
            }
        } else {
            Swal.fire("Error", submitRes.message || "Return failed with no message from server.", "error");
        }

    } catch (err) {
        if (loadingVisible) {
            Swal.close();
            loadingVisible = false;
        }
        console.error("Error while processing return:", err);
        Swal.fire("Error", `Failed to process return: ${err.message}`, "error");
    }
}

window.startReturnWizard = startReturnWizard;