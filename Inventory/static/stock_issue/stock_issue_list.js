import {
  db, fetchWithOffline
} from '/main_static/offline/db.js?v=43';
import { fetchProducts } from './offline.js';

document.addEventListener("DOMContentLoaded", async () => {
    loadIncompleteIssues();
});

async function loadIncompleteIssues() {
  const list = document.getElementById("incomplete-issues-list");
  list.innerHTML = "<i>Loading...</i>";

  try {
    // 1️⃣ Fetch online issues
    const onlineIssues = await fetchWithOffline({
      url: "/inventory/SDK/incomplete_issues",
      store: "serverIssues",
      transform: d => d.issues
    });

    // Normalize into one shape
    const normalizedOnline = onlineIssues
      .filter(i => i.isReturned === false)
      .map(i => ({
        issue_id: i.IssueId,
        whse_id: i.WhseId,
        project: i.ProjectName,
        timestamp: i.IssueTimeStamp,
        isOffline: false
      }));

    // only fetch offline issues if we are offline
    if (!navigator.onLine) {
        const offlineIssues = await db.offlineIssues
          .filter(i => i.allow_returns === true && i.status === "queued" && !i.isReturned)
          .toArray();

        const normalizedOffline = offlineIssues.map(i => ({
          issue_id: i.client_issue_id,
          whse_id: i.warehouse,
          project: i.project,
          timestamp: i.created_at,
          isOffline: true
        }));

        // Merge without duplication
        const merged = [...normalizedOnline];

        for (const off of normalizedOffline) {
          const exists = normalizedOnline.some(
              on => on.issue_id === off.issue_id
          );
          if (!exists) merged.push(off);
        }

        renderIssues(merged);
    } else {
        renderIssues(normalizedOnline);
    }
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
        Issue #${issue.issue_id}
        ${issue.isOffline ? '<span class="badge badge-warning">Offline</span>' : ''}
      </h3>
      <p><b>Date:</b> ${issue.timestamp}</p>
      <p><b>Project:</b> ${issue.project}</p>
      <button class="btn-primary"
        onclick="startReturnWizard('${issue.issue_id}')">
        Process Return →
      </button>
    `;

    list.appendChild(div);
  }
}

function isClientId(issueId) {
  return (
    typeof issueId === "string" &&
    (
      issueId.startsWith("temp_") ||
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
        .test(issueId)
    )
  );
}

// ============================================================================
//  RETURN WIZARD
// ============================================================================
async function fetchIssueLines(issueId) {
  let is_client_id = isClientId(issueId);
  
  if (!is_client_id) {
    try {
      console.log(`Fetching lines for server issue ${issueId} from server`);
      let lines = await db.serverIssueLines
        .where("header_id").equals(parseInt(issueId))
        .toArray();
      
      // Handle different response formats
      if (!Array.isArray(lines)) {
        lines = lines.lines || lines.products || [];
      }

      console.log(`Fetched ${lines.length} lines from server for issue ${issueId}`);
      return lines;
    } catch (error) {
      console.warn("Failed to fetch lines", error);
    }
  }
  
  // Check offlineIssueLines directly (for client_issue_id)
  if (is_client_id) {
    try {
      const offlineLines = await db.offlineIssueLines
        .where("client_issue_id").equals(issueId)
        .toArray();
        
      if (offlineLines.length > 0) {
        console.log(`Found ${offlineLines.length} offline lines for client issue ${issueId}`);
        const normalizedLines = offlineLines.map(i => ({
            issue_id: i.client_issue_id,
            line_id: i.client_issue_line_id,
            product_link: i.product_link,
            product_desc: i.product_desc,
            uom_code: i.uom_code,
            qty_issued: i.qty_issued,
            is_client_id: true
        }));
        return normalizedLines;
      }
    } catch (error) {
      console.warn("Error accessing offlineIssueLines:", error);
    }
  }  
  
  console.warn(`No lines found for issue ID: ${issueId} (${is_client_id ? 'client' : 'server'} ID)`);
  return [];
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
        <tr>
            <td>${p.product_desc}</td>
            <td>${p.uom_code || p.stocking_uom_code || "—"}</td>
            <td>${p.qty_issued}</td>
            <td>
                <input id="ret_qty_${i}" 
                       type="number" 
                       class="swal2-input" 
                       style="width:90px" 
                       min="0" 
                       max="${p.qty_issued}">
            </td>
        </tr>
    `).join("");

    // STEP 2: ENTER RETURN QTY
    const qtyEntry = await Swal.fire({
        title: "Enter Quantities Returned",
        width: 800,
        html: `
            <table class="return-table">
                <tr>
                    <th>Description</th>
                    <th>UOM</th>
                    <th>Issued</th>
                    <th>Returned</th>
                </tr>
                ${prodHTML}
            </table>
        `,
        confirmButtonText: "Next",
        preConfirm: () => {
            const lines = [];

            for (let i = 0; i < products.length; i++) {
                const qty = Number(document.getElementById(`ret_qty_${i}`).value);

                if (qty < 0 || qty > products[i].qty_issued) {
                    Swal.showValidationMessage("Invalid qty for item #" + (i + 1));
                    return false;
                }
                lines.push({
                    line_id: products[i].line_id,
                    product_link: products[i].product_link,
                    qty_issued: products[i].qty_issued,
                    qty_returned: qty,
                    is_client_id: products[i].is_client_id || false
                });
            }
            return lines;
        }
    });
    
    if (!qtyEntry.value) return;
    const returnLines = qtyEntry.value;

    // STEP 3: CONFIRMATION
    const confirmHTML = returnLines.map(l => {
        const prod = products.find(p => p.line_id === l.line_id);
        return `
            <tr>
                <td>${prod.product_desc}</td>
                <td>${prod.uom_code || prod.stocking_uom_code || "—"}</td>
                <td>${l.qty_issued}</td>
                <td>${l.qty_returned}</td>
            </tr>
        `;
    }).join("");

    const confirmResult = await Swal.fire({
        title: "Confirm Return",
        width: 800,
        html: `
            <table class="return-table">
                <tr>
                    <th>Description</th>
                    <th>UOM</th>
                    <th>Issued</th>
                    <th>Returned</th>
                </tr>
                ${confirmHTML}
            </table>
        `,
        confirmButtonText: "Submit Return",
        showCancelButton: true,
        cancelButtonText: "Cancel"
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
        
        if (!navigator.onLine) {
            console.log("Offline - queuing return", payload);

            if (isClientId(issueId)) {
                await db.offlineReturns.add({
                    client_issue_id: issueId,
                    issue_id: issueId,
                    returns: returnLines,
                    status: "queued",
                    created_at: new Date().toISOString(),
                });

                const issue = await db.offlineIssues
                    .where("client_issue_id")
                    .equals(issueId)
                    .first();

                if (issue) {
                  await db.offlineIssues.update(issue.local_id, {
                      isReturned: true
                  });
                }
            } else {
                await db.offlineReturns.add({
                    server_issue_id: issueId,
                    issue_id: issueId,
                    created_by_user_id: window.FERMESYNC.userId,
                    returns: returnLines,
                    status: "queued",
                    created_at: new Date().toISOString(),
                });

                await db.serverIssues.update(parseInt(issueId), {
                    isReturned: true
                });
            }

            if (loadingVisible) {
                Swal.close();
                loadingVisible = false;
            }

            loadIncompleteIssues();
            Swal.fire("Queued", "Return queued to sync when online.", "info");
            return;
        }

        // ONLINE path
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
            loadIncompleteIssues();
            fetchProducts();
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