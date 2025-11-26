// ============================================================================
//  LOAD INCOMPLETE ISSUES
// ============================================================================

document.addEventListener("DOMContentLoaded", async () => {
    loadIncompleteIssues();
});

async function loadIncompleteIssues() {
    const list = document.getElementById("incomplete-issues-list");
    list.innerHTML = "<i>Loading...</i>";

    const res = await fetch("/inventory/SDK/incomplete_issues");
    const data = await res.json();

    list.innerHTML = "";

    if (!data.issues || data.issues.length === 0) {
        list.innerHTML = "<i>No incomplete issues.</i>";
        return;
    }

    data.issues.forEach(issue => {
        const div = document.createElement("div");
        div.classList.add("issue-card");

        div.innerHTML = `
            <h3>Issue #${issue.IssueId}</h3>
            <p><b>Date:</b> ${issue.IssueTimeStamp}</p>
            <p><b>Project:</b> ${issue.ProjectName}</p>
            <p><b>Issued To:</b> ${issue.IssueToName}</p>

            <button class="btn-primary" onclick="startReturnWizard(${issue.IssueId})">
                Process Return →
            </button>
        `;

        list.appendChild(div);
    });
}

// ============================================================================
//  RETURN WIZARD
// ============================================================================

async function startReturnWizard(issueId) {

    // STEP 1: Who is returning the goods?
    const retInfo = await Swal.fire({
        title: "Return Details",
        html: `
            <label>Returned By:</label>
            <input id="returned_by" class="swal2-input" placeholder="Person returning items">
        `,
        confirmButtonText: "Next",
        preConfirm: () => {
            const returned = document.getElementById("returned_by").value.trim();
            if (!returned) {
                Swal.showValidationMessage("Returned By is required");
                return false;
            }
            return returned;
        }
    });

    const returnedBy = retInfo.value;

    // STEP 2: FETCH ISSUE LINES FROM BACKEND
    let products = [];
    try {
        const res = await fetch("/inventory/fetch_products_for_return", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ issue_id: issueId })
        });
        products = await res.json();
    } catch (err) {
        return Swal.fire("Error", "Failed to load issue lines", "error");
    }

    if (!products.length) {
        return Swal.fire("No Items", "This issue contains no lines.", "warning");
    }

    // Build HTML list
    const prodHTML = products.map((p, i) => `
        <tr>
            <td>${p.stock_description}</td>
            <td>${p.uom_code}</td>
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

    // STEP 3: ENTER RETURN QTY
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

                if (qty > 0) {
                    lines.push({
                        line_id: products[i].line_id,
                        qty_issued: products[i].qty_issued,
                        qty_returned: qty
                    });
                }
            }

            if (lines.length === 0) {
                Swal.showValidationMessage("Enter at least one quantity");
                return false;
            }

            return lines;
        }
    });

    const returnLines = qtyEntry.value;

    // STEP 4: CONFIRMATION
    const confirmHTML = returnLines.map(l => {
        const prod = products.find(p => p.line_id === l.line_id);
        return `
            <tr>
                <td>${prod.stock_description}</td>
                <td>${prod.uom_code}</td>
                <td>${l.qty_issued}</td>
                <td>${l.qty_returned}</td>
            </tr>
        `;
    }).join("");

    await Swal.fire({
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
        confirmButtonText: "Submit Return"
    });

    // STEP 5: SUBMIT TO BACKEND
    // STEP 5: SUBMIT TO BACKEND
    let loadingVisible = false;
    try {
        // Show a loading state so the user knows something is happening
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
            body: JSON.stringify({
                issue_id: issueId,
                returned_to: returnedBy,
                returns: returnLines
            })
        });

        // If the server responds with a non-2xx status, try to surface some detail
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
