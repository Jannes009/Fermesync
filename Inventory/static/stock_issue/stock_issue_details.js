document.addEventListener("DOMContentLoaded", loadStockIssueDetails);

async function loadStockIssueDetails() {
    const message = document.getElementById("issue-detail-message");
    try {
        const response = await request(`/inventory/SDK/stock_issue_details_data/${window.STOCK_ISSUE_ID}`);
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "Unable to load this stock issue.");
        }
        renderStockIssueDetails(result.issue);
    } catch (error) {
        message.textContent = error.message || "Unable to load this stock issue.";
        document.getElementById("issue-lines-body").innerHTML = '<tr><td colspan="6">Issue details could not be loaded.</td></tr>';
    }
}

function renderStockIssueDetails(issue) {
    const permissions = window.FERMESYNC?.permissions || [];
    document.getElementById("issue-title").textContent = `Issue ${issue.number || `#${issue.id}`}`;
    document.getElementById("issue-subtitle").textContent = issue.is_cancelled
        ? "Cancelled"
        : (issue.is_finalised ? "Finalised" : "Outstanding");

    const fields = [
        ["Issue ID", issue.id],
        ["Evolution reference", issue.evolution_reference],
        ["Issue date", formatIssueDate(issue.issue_date)],
        ["Created", formatIssueDate(issue.created_at)],
        ["Created by", userWithId(issue.created_by, issue.created_by_id)],
        ["Warehouse", issue.warehouse],
        ["Spray execution", issue.execution_id],
        ["Execution description", issue.execution_description],
        ["Finalised", issue.is_finalised ? "Yes" : "No"],
        ["Finalised by", userWithId(issue.finalised_by, issue.finalised_by_id)],
        ["Finalised at", formatIssueDate(issue.finalised_at)],
        ["Cancelled", issue.is_cancelled ? "Yes" : "No"],
        ["Cancelled by", userWithId(issue.cancelled_by, issue.cancelled_by_id)],
        ["Cancelled at", formatIssueDate(issue.cancelled_at)],
        ["Evolution credit note", issue.evolution_credit_note_no],
    ];
    const fieldContainer = document.getElementById("issue-header-fields");
    fieldContainer.replaceChildren();
    for (const [label, value] of fields) {
        const field = document.createElement("div");
        field.className = "issue-detail-field";
        const labelElement = document.createElement("span");
        labelElement.className = "issue-detail-label";
        labelElement.textContent = label;
        const valueElement = document.createElement("span");
        valueElement.className = "issue-detail-value";
        valueElement.textContent = value ?? "—";
        field.append(labelElement, valueElement);
        fieldContainer.appendChild(field);
    }

    const linesBody = document.getElementById("issue-lines-body");
    linesBody.replaceChildren();
    if (!issue.lines.length) {
        linesBody.innerHTML = '<tr><td colspan="6">No lines on this issue.</td></tr>';
    } else {
        for (const line of issue.lines) {
            const row = document.createElement("tr");
            const cells = [
                line.product_desc || `Stock ${line.product_link}`,
                line.project_ids || "—",
                formatIssueQuantity(line.qty_issued),
                formatIssueQuantity(line.qty_received),
                formatIssueQuantity(line.qty_finalised),
                line.uom_code || "—",
            ];
            cells.forEach((value, index) => {
                const cell = document.createElement("td");
                cell.textContent = value;
                if (index >= 2 && index <= 4) cell.className = "numeric";
                row.appendChild(cell);
            });
            linesBody.appendChild(row);
        }
    }

    const receiveButton = document.getElementById("receive-issue-button");
    receiveButton.hidden = !permissions.includes("STOCK_ISSUE_CREATE") || issue.is_finalised || issue.is_cancelled;
    receiveButton.onclick = () => window.startReturnWizard(issue.id, receiveButton);
    const cancelButton = document.getElementById("cancel-issue-button");
    cancelButton.hidden = !permissions.includes("STOCK_ISSUE_CANCEL") || issue.is_cancelled || !(
        issue.execution_id == null || issue.execution_finalised === false
    );
    cancelButton.onclick = () => window.cancelStockIssue(
        issue.id,
        cancelButton,
        Boolean(issue.evolution_reference)
    );
    window.onStockIssueReturnSuccess = loadStockIssueDetails;
    window.onStockIssueCancelSuccess = loadStockIssueDetails;
}

function formatIssueDate(value) {
    return value ? new Date(value).toLocaleString() : "—";
}

function formatIssueQuantity(value) {
    return value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function userWithId(username, userId) {
    if (username && userId) return `${username} (#${userId})`;
    return username || (userId ? `User #${userId}` : "—");
}