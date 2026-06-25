
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

    // Build compact table HTML list
    const prodHTML = `
        <div class="compact-table-container">
            <table class="returns-table">
                <thead>
                    <tr>
                        <th style="text-align:left">Product</th>
                        <th>Issued</th>
                        <th style="width:160px">Return</th>
                        <th>UOM</th>
                    </tr>
                </thead>
                <tbody>
                    ${products.map((p, i) => `
                        <tr>
                            <td class="prod-name">${p.product_desc}</td>
                            <td class="prod-issued">${parseFloat(p.qty_issued).toFixed(2)}</td>
                            <td class="prod-return">
                                <input id="ret_qty_${i}" 
                                       type="number" 
                                       class="return-qty-input" 
                                       min="0" 
                                       max="${p.qty_issued}"
                                       placeholder="0"
                                       step="0.01">
                            </td>
                            <td class="prod-uom">${p.uom_code || p.stocking_uom_code || ""}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;

    // STEP 2: ENTER RETURN QTY
    const qtyEntry = await Swal.fire({
        title: "Enter Quantities Returned",
        titleClass: "swal2-title-custom",
        width: 900,
        html: `
            <style>
                .swal2-html-container { padding: 16px !important; }
                .compact-table-container { max-height: 420px; overflow:auto; }
                .returns-table { width:100%; border-collapse:collapse; font-size:0.95rem; }
                .returns-table thead th { position:sticky; top:0; background:#fff; z-index:1; padding:8px; border-bottom:1px solid #e0e0e0; }
                .returns-table td { padding:8px; border-bottom:1px dashed #eee; }
                .returns-table .prod-name { font-weight:600; }
                .return-qty-input { width:100%; box-sizing:border-box; padding:6px 8px; border:1px solid #cfd8dc; border-radius:6px; }
                @media (max-width:720px) { .returns-table thead th:nth-child(4), .returns-table td.prod-uom { display:none; } }
            </style>
            <div class="compact-table-wrapper">
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
    // Build a compact confirmation table for the summary
    const confirmRows = returnLines.map(l => {
        const prod = products.find(p => p.product_link === l.product_link);
        const finalised = l.qty_issued - l.qty_returned;
        const hasNettIssued = prod.nett_issued !== null && prod.nett_issued !== undefined;
        const totalFinalised = hasNettIssued ? prod.nett_issued - l.qty_returned : null;
        const hasRecommended = prod.qty_recommended !== null && prod.qty_recommended !== undefined;
        const isOffByMoreThan10 = hasRecommended && hasNettIssued && Math.abs(totalFinalised - prod.qty_recommended) / prod.qty_recommended > 0.1;
        const warningClass = isOffByMoreThan10 ? 'row-warning' : '';
        const recommendedCell = hasRecommended ? `<td class="num">${parseFloat(prod.qty_recommended).toFixed(2)}</td>` : '<td class="num">—</td>';
        return `
            <tr class="${warningClass}">
                <td class="prod-name">${prod.product_desc}</td>
                <td class="num">${parseFloat(l.qty_issued).toFixed(2)}</td>
                <td class="num">${parseFloat(l.qty_returned).toFixed(2)}</td>
                <td class="num">${parseFloat(finalised).toFixed(2)}</td>
                ${recommendedCell}
            </tr>
        `;
    }).join("");

    const confirmHTML = `
        <div class="confirm-table-container">
            <table class="confirm-table">
                <thead>
                    <tr>
                        <th style="text-align:left">Product</th>
                        <th>Issued</th>
                        <th>Returned</th>
                        <th>Finalised</th>
                        <th>Recommended</th>
                    </tr>
                </thead>
                <tbody>
                    ${confirmRows}
                </tbody>
            </table>
        </div>
    `;

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
                .swal2-html-container { padding: 16px !important; }
                .return-warning-banner { display:flex; gap:12px; padding:12px; background:#fff8e1; border:1px solid #ffb300; border-radius:8px; margin-bottom:12px; }
                .confirm-table-container { max-height:420px; overflow:auto; }
                .confirm-table { width:100%; border-collapse:collapse; font-size:0.95rem; }
                .confirm-table thead th { position:sticky; top:0; background:#fff; z-index:1; padding:8px; border-bottom:1px solid #e0e0e0; }
                .confirm-table td { padding:8px; border-bottom:1px dashed #eee; }
                .confirm-table td.num { text-align:right; font-weight:700; }
                .row-warning { background: linear-gradient(90deg, #fff8e6, #fffef6); }
                .swal2-back-custom { background-color:#757575; border:0; color:white; cursor:pointer; font-size:1rem; font-weight:600; padding:0.6rem 1.2rem; border-radius:0.25em; margin-right:auto; }
            </style>
            ${warningMessage}
            <div class="confirm-table-wrapper">
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