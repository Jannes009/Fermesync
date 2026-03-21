import { db } from '/main_static/offline/db.js?v=43';

document.addEventListener("DOMContentLoaded", async () => {
    loadIncompleteIssues();
});

async function loadIncompleteIssues() {
  const list = document.getElementById("incomplete-issues-list");
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
        <tr>
            <td>${p.product_desc}</td>
            <td>${p.qty_issued.toFixed(2)} ${p.uom_code || p.stocking_uom_code || ""}</td>
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