
let returnSubmissionInProgress = false;
let cancellationInProgress = false;

document.addEventListener("DOMContentLoaded", async () => {
        const tableBody = document.getElementById("stock-issues-body");
        if (tableBody) {
        if (document.getElementById("issue-from-filter")) setDefaultIssueDates();
        document.getElementById("apply-issue-filters")?.addEventListener("click", loadIncompleteIssues);
        document.getElementById("issue-status-filter")?.addEventListener("change", loadIncompleteIssues);
                loadIncompleteIssues();
    }
});

function setDefaultIssueDates() {
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - 6);
    const toInputDate = date => {
        const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 10);
    };
    document.getElementById("issue-from-filter").value = toInputDate(start);
    document.getElementById("issue-to-filter").value = toInputDate(today);
}

async function loadIncompleteIssues() {
    const tableBody = document.getElementById("stock-issues-body");
    if (!tableBody) {
      return;
  }
    tableBody.innerHTML = "<tr><td colspan=\"7\">Loading issues...</td></tr>";

  try {
            const params = new URLSearchParams();
            const statusFilter = document.getElementById("issue-status-filter");
            const fromFilter = document.getElementById("issue-from-filter");
            const toFilter = document.getElementById("issue-to-filter");
            if (statusFilter) params.set("status", statusFilter.value);
            if (fromFilter?.value) params.set("from", fromFilter.value);
            if (toFilter?.value) params.set("to", toFilter.value);
            const response = await request(`/inventory/SDK/incomplete_issues?${params}`);
            const result = await response.json();
            if (!response.ok || !result.success) {
                    throw new Error(result.message || "Failed to load issues.");
            }
            renderIssues(result.issues || []);
  } catch (err) {
    console.error(err);
        tableBody.innerHTML = `<tr><td colspan="7">${escapeIssueText(err.message || "Failed to load issues.")}</td></tr>`;
  }
}

function renderIssues(issues) {
    const tableBody = document.getElementById("stock-issues-body");
    tableBody.replaceChildren();

  if (!issues.length) {
        tableBody.innerHTML = '<tr><td colspan="7">No issues match these filters.</td></tr>';
    return;
  }

  for (const issue of issues) {
        const row = document.createElement("tr");
        const issueDate = issue.IssueTimeStamp ? new Date(issue.IssueTimeStamp).toLocaleString() : "—";
        const fields = [
                issue.IssueNo || `#${issue.IssueId}`,
                issueDate,
                issue.IsCancelled ? "Cancelled" : (issue.IsFinalised ? "Finalised" : "Outstanding"),
                issue.WhseDescription || "—",
                issue.ExecutionDescription || "—",
                issue.EvolutionReference || "—",
        ];
        for (const value of fields) {
                const cell = document.createElement("td");
                if (issue.IsCancelled && value === "Cancelled") {
                    const badge = document.createElement("span");
                    badge.className = "issue-status-badge cancelled";
                    badge.textContent = value;
                    cell.appendChild(badge);
                } else {
                    cell.textContent = value;
                }
                row.appendChild(cell);
        }
        row.cells[2].className = "issue-status";
        if (issue.IsCancelled) row.classList.add("issue-cancelled");

        const actions = document.createElement("td");
        actions.className = "issue-actions";
        const details = document.createElement("a");
        details.href = `/inventory/SDK/stock_issue_details/${issue.IssueId}`;
        details.textContent = "Details";
        actions.appendChild(details);
        const permissions = window.FERMESYNC?.permissions || [];
        if (permissions.includes("STOCK_ISSUE_CREATE") && !issue.IsFinalised && !issue.IsCancelled) {
                const receive = document.createElement("button");
                receive.type = "button";
                receive.className = "receive-issue";
                receive.textContent = "Receive";
                receive.addEventListener("click", () => startReturnWizard(issue.IssueId, receive));
                actions.appendChild(receive);
        }
            const canCancel = permissions.includes("STOCK_ISSUE_CANCEL") && !issue.IsCancelled && (
                issue.ExecutionId == null || issue.ExecutionFinalised === false
            );
            if (canCancel) {
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.textContent = "Cancel Issue";
                cancel.addEventListener("click", () => cancelStockIssue(
                    issue.IssueId,
                    cancel,
                    Boolean(issue.EvolutionReference)
                ));
                actions.appendChild(cancel);
            }
        row.appendChild(actions);
        tableBody.appendChild(row);
  }
}

function escapeIssueText(value) {
    const element = document.createElement("span");
    element.textContent = value;
    return element.innerHTML;
}

async function cancelStockIssue(issueId, sourceButton = null, hasEvolutionReference = true) {
    if (cancellationInProgress) return;
    const confirmation = await Swal.fire({
        icon: "warning",
        title: "Are you very sure?",
        text: hasEvolutionReference
            ? "This will create an Evolution credit note for the linked sales order."
            : "No Evolution sales order exists. This will cancel the issue in Fermesync only.",
        showCancelButton: true,
        confirmButtonText: hasEvolutionReference ? "Yes, create credit note" : "Yes, cancel issue",
        cancelButtonText: "Keep issue",
        confirmButtonColor: "#b42318",
    });
    if (!confirmation.isConfirmed) return;

    cancellationInProgress = true;
    if (sourceButton) {
        sourceButton.disabled = true;
        sourceButton.textContent = "Processing...";
    }
    try {
        Swal.fire({ title: "Creating credit note...", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
        const response = await request("/inventory/SDK/cancel_stock_issue", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ issue_id: issueId }),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "Issue cancellation failed.");
        }
        if (result.credited) {
            await Swal.fire("Credit note created", `Evolution reference: ${result.credit_note_number || "—"}`, "success");
        } else {
            await Swal.fire("Issue cancelled", result.message || "Issue cancelled in Fermesync.", "success");
        }
        if (window.onStockIssueCancelSuccess) {
            await window.onStockIssueCancelSuccess();
        } else {
            await loadIncompleteIssues();
        }
    } catch (error) {
        await Swal.fire("Cancellation failed", error.message || "Could not create the credit note.", "error");
    } finally {
        cancellationInProgress = false;
        if (sourceButton?.isConnected) {
            sourceButton.disabled = false;
            sourceButton.textContent = "Cancel Issue";
        }
    }
}

// ============================================================================
//  RETURN WIZARD
// ============================================================================
async function fetchIssueLines(issueId) {
  try {

    let lines = await request(`/inventory/SDK/incomplete_issue_lines/${issueId}`)
      .then(async res => {
        const data = await res.json();
        if (!data.success) {
            Swal.fire("Error", data.message || "Failed to fetch issue lines.", "error");
            return [];
        }
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

async function startReturnWizard(issueId, sourceButton = null) {
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
                                       placeholder="Return Qty"
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
                await startReturnWizard(issueId, sourceButton);
            };
            
            const footer = document.querySelector('.swal2-actions');
            if (footer) {
                footer.insertBefore(backBtn, footer.firstChild);
            }
        }
    });

    if (!confirmResult.isConfirmed) return;
    if (returnSubmissionInProgress) return;

    // STEP 4: SUBMIT TO BACKEND
    returnSubmissionInProgress = true;
    const originalButtonHtml = sourceButton?.innerHTML;
    if (sourceButton) {
        sourceButton.disabled = true;
        sourceButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Processing...';
    }
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
        
        const submit = await request("/inventory/process_return", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const submitRes = await submit.json();

        if (!submitRes.success) {
            await Swal.fire("Error", submitRes.message || "Return failed with no message from server.", "error");
            return;
        }


        if (loadingVisible) {
            Swal.close();
            loadingVisible = false;
        }

        await Swal.fire("Success", "Return processed successfully!", "success");
        if (window.onStockIssueReturnSuccess) {
            await window.onStockIssueReturnSuccess();
        } else {
            await loadIncompleteIssues();
        }

    } catch (err) {
        if (loadingVisible) {
            Swal.close();
            loadingVisible = false;
        }
        console.error("Error while processing return:", err);
        await Swal.fire("Error", `Failed to process return: ${err.message}`, "error");
    } finally {
        returnSubmissionInProgress = false;
        if (sourceButton?.isConnected) {
            sourceButton.disabled = false;
            sourceButton.innerHTML = originalButtonHtml;
        }
    }
}

window.startReturnWizard = startReturnWizard;
window.cancelStockIssue = cancelStockIssue;