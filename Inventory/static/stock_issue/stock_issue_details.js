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
        document.getElementById("issue-lines-body").innerHTML = '<tr><td colspan="5">Issue details could not be loaded.</td></tr>';
    }
}

function renderStockIssueDetails(issue) {
    const permissions = window.FERMESYNC?.permissions || [];
    document.getElementById("issue-title").textContent = `Issue ${issue.number || `#${issue.id}`}`;
    const status = issue.is_cancelled
        ? "Cancelled"
        : (issue.is_finalised ? "Finalised" : "Outstanding");
    const statusBadge = document.createElement("span");
    statusBadge.className = "issue-status";
    statusBadge.textContent = status;
    document.getElementById("issue-subtitle").replaceChildren(statusBadge);

    const fields = [
        ["Evolution reference", issue.evolution_reference],
        ["Transaction date", formatIssueDate(issue.issue_date)],
        ["Warehouse", issue.warehouse],
        ["Evolution credit note", issue.evolution_credit_note_no],
    ];
    const fieldContainer = document.getElementById("issue-header-fields");
    fieldContainer.replaceChildren();
    for (const [label, value] of fields) {
        appendIssueField(fieldContainer, label, value);
    }
    const executionField = appendIssueField(fieldContainer, "Spray execution", "");
    const executionValue = executionField.querySelector(".issue-detail-value");
    if (issue.execution_id !== null && issue.execution_id !== undefined) {
        const executionLink = document.createElement("a");
        executionLink.className = "execution-description-link";
        executionLink.href = `/agri/execution/${encodeURIComponent(issue.execution_id)}`;
        executionLink.textContent = issue.execution_description || "View execution";
        executionValue.replaceChildren(executionLink);
    } else {
        executionValue.textContent = "—";
    }

    renderIssueEvents(issue);

    const linesBody = document.getElementById("issue-lines-body");
    linesBody.replaceChildren();
    if (!issue.lines.length) {
        linesBody.innerHTML = '<tr><td colspan="5">No lines on this issue.</td></tr>';
    } else {
        for (const line of issue.lines) {
            const row = document.createElement("tr");
            row.className = "issue-line-row";
            const productCell = document.createElement("td");
            productCell.dataset.label = "Product";
            productCell.textContent = line.product_desc || "Unknown product";
            row.appendChild(productCell);

            const quantities = [
                ["Issued", line.qty_issued],
                ["Received", line.qty_received],
                ["Finalised", line.qty_finalised],
            ];
            for (const [label, quantity] of quantities) {
                const cell = document.createElement("td");
                cell.className = "numeric";
                cell.dataset.label = label;
                appendIssueQuantity(cell, quantity, line.uom_code);
                row.appendChild(cell);
            }

            const allocationCell = document.createElement("td");
            allocationCell.dataset.label = "Projects";
            const allocations = line.project_allocations || [];
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "allocation-toggle";
            toggle.setAttribute("aria-expanded", "false");
            toggle.setAttribute("aria-label", "Show project allocations");
            toggle.innerHTML = '<span class="allocation-chevron" aria-hidden="true">▶</span>';
            toggle.disabled = allocations.length === 0;
            toggle.title = allocations.length ? "Show project quantities" : "No project allocations";
            allocationCell.appendChild(toggle);
            row.appendChild(allocationCell);
            linesBody.appendChild(row);

            const allocationsRow = document.createElement("tr");
            allocationsRow.className = "allocation-row";
            allocationsRow.hidden = true;
            const allocationsCell = document.createElement("td");
            allocationsCell.className = "allocation-cell";
            allocationsCell.colSpan = 5;
            allocationsCell.appendChild(renderProjectAllocations(allocations, line.uom_code));
            allocationsRow.appendChild(allocationsCell);
            linesBody.appendChild(allocationsRow);

            toggle.addEventListener("click", () => {
                const isExpanded = toggle.getAttribute("aria-expanded") === "true";
                toggle.setAttribute("aria-expanded", String(!isExpanded));
                toggle.setAttribute("aria-label", isExpanded ? "Show project allocations" : "Hide project allocations");
                toggle.title = isExpanded ? "Show project quantities" : "Hide project quantities";
                allocationsRow.hidden = isExpanded;
            });
        }
    }

    const receiveButton = document.getElementById("receive-issue-button");
    receiveButton.hidden = !permissions.includes("STOCK_ISSUE_CREATE") || issue.is_finalised || issue.is_cancelled;
    receiveButton.onclick = () => window.startReturnWizard(issue.id, receiveButton);
    const cancelButton = document.getElementById("cancel-issue-button");
    cancelButton.hidden = !permissions.includes("STOCK_ISSUE_CANCEL") || issue.is_cancelled;
    cancelButton.onclick = () => window.cancelStockIssue(
        issue.id,
        cancelButton,
        Boolean(issue.evolution_reference)
    );
    window.onStockIssueReturnSuccess = loadStockIssueDetails;
    window.onStockIssueCancelSuccess = loadStockIssueDetails;
}

function appendIssueField(container, label, value) {
    const field = document.createElement("div");
    field.className = "issue-detail-field";
    const labelElement = document.createElement("span");
    labelElement.className = "issue-detail-label";
    labelElement.textContent = label;
    const valueElement = document.createElement("span");
    valueElement.className = "issue-detail-value";
    valueElement.textContent = value ?? "—";
    field.append(labelElement, valueElement);
    container.appendChild(field);
    return field;
}

function renderIssueEvents(issue) {
    const events = [
        { label: "Created", timestamp: issue.created_at, username: issue.created_by },
        { label: "Finalised", timestamp: issue.finalised_at, username: issue.finalised_by },
        { label: "Cancelled", timestamp: issue.cancelled_at, username: issue.cancelled_by },
    ].filter(event => event.timestamp);
    events.sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));

    const list = document.getElementById("issue-event-list");
    list.replaceChildren();
    if (!events.length) {
        const empty = document.createElement("li");
        empty.textContent = "No recorded activity.";
        list.appendChild(empty);
        return;
    }

    for (const event of events) {
        const item = document.createElement("li");
        item.className = "issue-event";
        const timestamp = document.createElement("time");
        timestamp.dateTime = new Date(event.timestamp).toISOString();
        timestamp.textContent = formatIssueDate(event.timestamp);
        const detail = document.createElement("div");
        const title = document.createElement("span");
        title.className = "issue-event-title";
        title.textContent = event.label;
        detail.appendChild(title);
        if (event.username) {
            const actor = document.createElement("span");
            actor.textContent = ` by ${event.username}`;
            detail.appendChild(actor);
        }
        item.append(timestamp, detail);
        list.appendChild(item);
    }
}

function renderProjectAllocations(allocations, uomCode) {
    const container = document.createElement("div");
    if (!allocations.length) {
        container.textContent = "No project allocations stored for this line.";
        return container;
    }

    const table = document.createElement("table");
    table.className = "allocation-table";
    const header = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const label of ["Project", "Share", "Issued", "Received", "Finalised"]) {
        const cell = document.createElement("th");
        cell.textContent = label;
        if (["Issued", "Received", "Finalised"].includes(label)) cell.className = "numeric";
        headerRow.appendChild(cell);
    }
    header.appendChild(headerRow);
    table.appendChild(header);

    const body = document.createElement("tbody");
    for (const allocation of allocations) {
        const row = document.createElement("tr");
        const project = document.createElement("td");
        project.dataset.label = "Project";
        project.textContent = [allocation.project_name].filter(Boolean).join(" · ") || "Unknown project";
        row.appendChild(project);
        const share = document.createElement("td");
        share.className = "allocation-share";
        share.dataset.label = "Share";
        share.textContent = `${formatIssueQuantity(allocation.weight * 100)}%`;
        row.appendChild(share);
        const quantities = [
            ["Issued", allocation.qty_issued],
            ["Received", allocation.qty_received],
            ["Finalised", allocation.qty_finalised],
        ];
        for (const [label, quantity] of quantities) {
            const cell = document.createElement("td");
            cell.className = "numeric";
            cell.dataset.label = label;
            appendIssueQuantity(cell, quantity, uomCode);
            row.appendChild(cell);
        }
        body.appendChild(row);
    }
    table.appendChild(body);
    container.appendChild(table);
    return container;
}

function appendIssueQuantity(container, value, uomCode) {
    const quantity = document.createElement("span");
    quantity.className = "quantity-value";
    quantity.textContent = formatIssueQuantity(value);
    container.appendChild(quantity);
    if (uomCode) {
        const unit = document.createElement("span");
        unit.className = "uom-badge";
        unit.textContent = uomCode;
        container.appendChild(unit);
    }
}

function formatIssueDate(value) {
    return value ? new Date(value).toLocaleString() : "—";
}

function formatIssueQuantity(value) {
    return value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}