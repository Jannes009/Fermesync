document.addEventListener("DOMContentLoaded", () => {
    setDefaultPeriod();
    document.getElementById("qty-filters").addEventListener("submit", event => {
        event.preventDefault();
        loadWarehouseQuantities();
    });
    document.getElementById("qty-search").addEventListener("input", renderCurrentWarehouseQuantities);
    document.getElementById("qty-availability-filter").addEventListener("change", renderCurrentWarehouseQuantities);
    document.querySelectorAll(".qty-status-option input").forEach(input => {
        input.addEventListener("change", renderCurrentWarehouseQuantities);
    });
    loadWarehouseQuantities();
});

const hiddenWarehouseStorageKey = "qty-hidden-warehouse-columns";
let hiddenWarehouseIds = readHiddenWarehouseIds();
let currentWarehouseQtyData = null;
let currentPeriodKey = null;
const warehouseDetailCache = new Map();

function readHiddenWarehouseIds() {
    try {
        const stored = JSON.parse(localStorage.getItem(hiddenWarehouseStorageKey) || "[]");
        return new Set(Array.isArray(stored) ? stored.map(String) : []);
    } catch {
        return new Set();
    }
}

function setDefaultPeriod() {
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - ((today.getDay() + 6) % 7));
    const end = new Date(start);
    end.setDate(start.getDate() + 13);
    document.getElementById("qty-from").value = toLocalDateInput(start);
    document.getElementById("qty-to").value = toLocalDateInput(end);
}

function toLocalDateInput(date) {
    const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 10);
}

async function loadWarehouseQuantities() {
    const body = document.getElementById("qty-table-body");
    body.innerHTML = '<tr><td class="qty-message">Loading warehouse quantities...</td></tr>';
    const startDate = document.getElementById("qty-from").value;
    const endDate = document.getElementById("qty-to").value;
    const periodKey = `${startDate}|${endDate}`;
    if (currentPeriodKey !== periodKey) {
        warehouseDetailCache.clear();
        currentPeriodKey = periodKey;
    }
    const params = new URLSearchParams({
        from: startDate,
        to: endDate,
    });
    try {
        const response = await request(`/inventory/qty/data?${params}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || "Unable to load warehouse quantities.");
        }
        currentWarehouseQtyData = data;
        renderCurrentWarehouseQuantities();
    } catch (error) {
        body.innerHTML = "";
        const row = document.createElement("tr");
        const message = document.createElement("td");
        message.className = "qty-message";
        message.colSpan = Math.max(1, document.getElementById("qty-table-head").cells.length);
        message.textContent = error.message || "Unable to load warehouse quantities.";
        row.appendChild(message);
        body.appendChild(row);
    }
}

function renderCurrentWarehouseQuantities() {
    if (currentWarehouseQtyData) renderWarehouseQuantities(currentWarehouseQtyData);
}

function renderWarehouseQuantities(data) {
    const header = document.getElementById("qty-table-head");
    const body = document.getElementById("qty-table-body");
    header.replaceChildren();
    body.replaceChildren();
    renderWarehouseColumnControls(data.warehouses);

    const visibleWarehouses = data.warehouses.filter(warehouse => !hiddenWarehouseIds.has(String(warehouse.WhseLink)));
    const visibleWarehouseIds = new Set(visibleWarehouses.map(warehouse => String(warehouse.WhseLink)));

    const descriptionHeader = document.createElement("th");
    descriptionHeader.className = "qty-description";
    descriptionHeader.textContent = "Description";
    header.appendChild(descriptionHeader);
    for (const warehouse of visibleWarehouses) {
        const cell = document.createElement("th");
        const label = document.createElement("span");
        label.className = "qty-warehouse-heading";
        const name = document.createElement("span");
        name.textContent = warehouse.WhseDescription;
        const code = document.createElement("small");
        code.textContent = warehouse.WhseCode;
        label.append(name, code);
        cell.appendChild(label);
        header.appendChild(cell);
    }

    if (!data.warehouses.length) {
        appendMessageRow(body, "No warehouses are connected to your account.", 1);
        return;
    }
    if (!visibleWarehouses.length) {
        appendMessageRow(body, "All warehouse columns are hidden. Use the warehouse buttons above to show columns.", 1);
        return;
    }
    const searchTerm = document.getElementById("qty-search").value.trim().toLocaleLowerCase();
    const selectedStatuses = new Set(
        Array.from(document.querySelectorAll(".qty-status-option input:checked"), input => input.value)
    );
    const availabilityFilter = document.getElementById("qty-availability-filter").value;
    const filteredItems = data.items.filter(item => {
        const searchableText = `${item.description || ""} ${item.active_ingredient || ""}`.toLocaleLowerCase();
        const shownWarehouses = item.warehouses.filter(warehouse => visibleWarehouseIds.has(String(warehouse.id)));
        return searchableText.includes(searchTerm) && shownWarehouses.some(warehouse =>
            selectedStatuses.has(warehouse.status) && matchesAvailability(warehouse, availabilityFilter)
        );
    });

    if (!filteredItems.length) {
        appendMessageRow(body, "No products match this period, search, and status selection.", header.cells.length);
        return;
    }

    for (const item of filteredItems) {
        const summaryRow = document.createElement("tr");
        summaryRow.className = "qty-summary-row";
        const descriptionCell = document.createElement("td");
        descriptionCell.className = "qty-description";
        const descriptionContent = document.createElement("div");
        descriptionContent.className = "qty-description-content";
        const expander = document.createElement("button");
        expander.type = "button";
        expander.className = "qty-expand";
        expander.setAttribute("aria-expanded", "false");
        expander.setAttribute("aria-label", `Show warehouse details for ${item.description}`);
        expander.innerHTML = '<span aria-hidden="true">▶</span>';
        const productText = document.createElement("span");
        productText.className = "qty-product-text";
        const productName = document.createElement("span");
        productName.className = "qty-product-name";
        productName.textContent = item.description || "Unknown product";
        productText.appendChild(productName);
        if (item.active_ingredient) {
            const ingredient = document.createElement("small");
            ingredient.className = "qty-active-ingredient";
            ingredient.textContent = item.active_ingredient;
            productText.appendChild(ingredient);
        }
        const viewLink = document.createElement("a");
        viewLink.className = "qty-product-view";
        viewLink.href = `/inventory/product/${encodeURIComponent(item.stock_id)}`;
        viewLink.title = "View product details";
        viewLink.setAttribute("aria-label", `View product details for ${item.description || "product"}`);
        viewLink.innerHTML = '<i class="fas fa-eye" aria-hidden="true"></i>';
        descriptionContent.append(expander, productText, viewLink);
        descriptionCell.appendChild(descriptionContent);
        summaryRow.appendChild(descriptionCell);

        const detailRow = document.createElement("tr");
        detailRow.className = "qty-detail-row";
        detailRow.hidden = true;
        const detailCell = document.createElement("td");
        detailCell.colSpan = visibleWarehouses.length + 1;
        detailCell.textContent = "Expand this product to load warehouse details.";
        detailRow.appendChild(detailCell);

        const warehousesById = new Map(item.warehouses.map(warehouse => [String(warehouse.id), warehouse]));
        for (const warehouse of visibleWarehouses) {
            const quantity = warehousesById.get(String(warehouse.WhseLink));
            const cell = document.createElement("td");
            cell.className = "qty-available-cell";
            if (!quantity || !quantity.is_linked) {
                cell.textContent = "—";
                cell.classList.add("qty-unlinked");
                cell.title = "Not linked to this warehouse";
                summaryRow.appendChild(cell);
                continue;
            }
            const quantityChip = document.createElement("span");
            quantityChip.className = `qty-quantity ${quantity.status}`;
            quantityChip.textContent = formatQuantity(quantity.qty_available);
            cell.title = statusLabel(quantity.status);
            cell.setAttribute("aria-label", `${warehouse.WhseDescription}: ${quantityChip.textContent} available; ${statusLabel(quantity.status)}`);
            cell.appendChild(quantityChip);
            summaryRow.appendChild(cell);
        }

        let detailLoading = false;
        expander.addEventListener("click", async () => {
            const expanded = expander.getAttribute("aria-expanded") === "true";
            expander.setAttribute("aria-expanded", String(!expanded));
            expander.setAttribute("aria-label", `${expanded ? "Show" : "Hide"} warehouse details for ${item.description}`);
            detailRow.hidden = expanded;
            if (expanded || detailLoading) return;

            const renderVisibleDetails = warehouses => {
                const visibleDetails = warehouses
                    .filter(warehouse => visibleWarehouseIds.has(String(warehouse.id)))
                    .filter(warehouse => matchesAvailability(warehouse, availabilityFilter));
                detailCell.replaceChildren(renderWarehouseDetails(item.stock_id, visibleDetails));
            };
            if (warehouseDetailCache.has(item.stock_id)) {
                renderVisibleDetails(warehouseDetailCache.get(item.stock_id));
                return;
            }

            detailLoading = true;
            detailCell.textContent = "Loading warehouse details...";
            try {
                const params = new URLSearchParams({
                    from: document.getElementById("qty-from").value,
                    to: document.getElementById("qty-to").value,
                });
                const response = await request(`/inventory/qty/detail/${item.stock_id}?${params}`);
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.message || "Unable to load warehouse details.");
                }
                warehouseDetailCache.set(item.stock_id, result.warehouses || []);
                renderVisibleDetails(warehouseDetailCache.get(item.stock_id));
            } catch (error) {
                detailCell.textContent = error.message || "Unable to load warehouse details. Collapse and reopen to retry.";
            } finally {
                detailLoading = false;
            }
        });
        body.append(summaryRow, detailRow);
    }
}

function renderWarehouseColumnControls(warehouses) {
    const controls = document.getElementById("qty-column-controls");
    controls.replaceChildren();
    const label = document.createElement("span");
    label.className = "qty-column-label";
    label.textContent = "Warehouses";
    controls.appendChild(label);

    const warehouseIds = new Set(warehouses.map(warehouse => String(warehouse.WhseLink)));
    hiddenWarehouseIds = new Set([...hiddenWarehouseIds].filter(id => warehouseIds.has(id)));
    for (const warehouse of warehouses) {
        const id = String(warehouse.WhseLink);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "qty-column-toggle";
        button.textContent = warehouse.WhseCode;
        button.title = `${hiddenWarehouseIds.has(id) ? "Show" : "Hide"} ${warehouse.WhseDescription}`;
        button.setAttribute("aria-pressed", String(!hiddenWarehouseIds.has(id)));
        button.addEventListener("click", () => {
            if (hiddenWarehouseIds.has(id)) hiddenWarehouseIds.delete(id);
            else hiddenWarehouseIds.add(id);
            saveHiddenWarehouseIds();
            renderCurrentWarehouseQuantities();
        });
        controls.appendChild(button);
    }

    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "qty-columns-reset";
    reset.textContent = "Show all";
    reset.addEventListener("click", () => {
        hiddenWarehouseIds.clear();
        saveHiddenWarehouseIds();
        renderCurrentWarehouseQuantities();
    });
    controls.appendChild(reset);
}

function saveHiddenWarehouseIds() {
    try {
        localStorage.setItem(hiddenWarehouseStorageKey, JSON.stringify([...hiddenWarehouseIds]));
    } catch {
        // The page remains usable when local storage is unavailable.
    }
}

function matchesAvailability(warehouse, filter) {
    if (filter === "in-stock") return warehouse.is_linked && warehouse.qty_available > 0;
    if (filter === "out-of-stock") return !warehouse.is_linked || warehouse.qty_available <= 0;
    return true;
}

function isoWeekStringForDate(dateValue) {
    const date = new Date(dateValue);
    if (Number.isNaN(date.getTime())) return "";
    const utcDate = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = utcDate.getUTCDay() || 7;
    utcDate.setUTCDate(utcDate.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(utcDate.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((utcDate - yearStart) / 86400000) + 1) / 7);
    return `${utcDate.getUTCFullYear()}-${String(weekNo).padStart(2, "0")}`;
}

function buildWarehouseDetailQueryString() {
    const fromValue = document.getElementById("qty-from")?.value;
    const toValue = document.getElementById("qty-to")?.value;
    if (!fromValue || !toValue) return "";
    const params = new URLSearchParams();
    const fromWeek = isoWeekStringForDate(fromValue);
    const toWeek = isoWeekStringForDate(toValue);
    if (fromWeek) params.set("from_week", fromWeek);
    if (toWeek) params.set("to_week", toWeek);
    return params.toString() ? `?${params.toString()}` : "";
}

function renderWarehouseSprayDetails(stockId, warehouse, container) {
    const detailTable = document.createElement("table");
    detailTable.className = "qty-detail-spray-table";
    detailTable.innerHTML = `
        <thead>
            <tr>
                <th>Spray No</th>
                <th>Description</th>
                <th class="numeric">Recommended</th>
                <th class="numeric">Finalised</th>
                <th>Unit</th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="5">Loading spray details...</td></tr>
        </tbody>
    `;
    container.replaceChildren(detailTable);

    const query = buildWarehouseDetailQueryString();
    request(`/agri/suggested-order/detail/${encodeURIComponent(stockId)}/warehouse/${encodeURIComponent(warehouse.id)}${query}`)
        .then(async response => {
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || "Unable to load spray details.");
            }
            const body = detailTable.querySelector("tbody");
            if (!payload.sprays || !payload.sprays.length) {
                body.innerHTML = '<tr><td colspan="5">No spray details for this warehouse in the selected period.</td></tr>';
                return;
            }
            body.innerHTML = payload.sprays.map(spray => `
                <tr title="Open spray ${spray.spray_h_no}" style="cursor:pointer;" onclick="window.location.href='/agri/spray/${encodeURIComponent(spray.spray_id)}'">
                    <td>${spray.spray_h_no || "—"}</td>
                    <td>${spray.spray_h_description || "—"}</td>
                    <td class="numeric">${formatQuantity(spray.recommended_qty)}</td>
                    <td class="numeric">${formatQuantity(spray.finalised_qty)}</td>
                    <td>${spray.stocking_uom || "—"}</td>
                </tr>
            `).join("");
        })
        .catch(error => {
            detailTable.querySelector("tbody").innerHTML = `<tr><td colspan="5">${error.message || "Unable to load spray details."}</td></tr>`;
        });
}

function renderWarehouseDetails(stockId, warehouses) {
    const wrapper = document.createElement("div");
    wrapper.className = "qty-detail-wrap";
    const table = document.createElement("table");
    table.className = "qty-detail-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    const columnLabels = ["Warehouse", "Needed", "On hand", "PO", "IBT", "Status"];
    columnLabels.forEach((label, index) => {
        const cell = document.createElement("th");
        cell.textContent = label;
        if (index >= 1 && index <= 4) cell.className = "numeric";
        headRow.appendChild(cell);
    });
    head.appendChild(headRow);
    table.appendChild(head);

    const body = document.createElement("tbody");
    for (const warehouse of warehouses) {
        const row = document.createElement("tr");
        const nameCell = document.createElement("td");
        nameCell.className = "qty-detail-warehouse-cell";
        const label = document.createElement("span");
        label.textContent = `${warehouse.code} - ${warehouse.name}`;
        nameCell.appendChild(label);

        const detailRow = document.createElement("tr");
        detailRow.className = "qty-detail-spray-row";
        detailRow.hidden = true;
        const detailCell = document.createElement("td");
        detailCell.colSpan = 6;
        detailCell.textContent = "Loading spray details...";
        detailRow.appendChild(detailCell);

        if (warehouse.is_linked) {
            const expand = document.createElement("button");
            expand.type = "button";
            expand.className = "qty-detail-expand";
            expand.setAttribute("aria-expanded", "false");
            expand.textContent = "+";
            expand.title = `Show spray details for ${warehouse.name}`;
            expand.addEventListener("click", () => {
                const shouldExpand = expand.getAttribute("aria-expanded") === "false";
                expand.setAttribute("aria-expanded", String(shouldExpand));
                expand.textContent = shouldExpand ? "−" : "+";
                detailRow.hidden = !shouldExpand;
                if (shouldExpand) {
                    detailCell.textContent = "";
                    renderWarehouseSprayDetails(stockId, warehouse, detailCell);
                }
            });
            nameCell.insertBefore(expand, label);
        } else {
            const statusCell = document.createElement("td");
            statusCell.textContent = "Not linked";
            statusCell.className = "qty-unlinked";
            row.appendChild(nameCell);
            for (let index = 0; index < 4; index += 1) {
                const cell = document.createElement("td");
                cell.className = "numeric qty-unlinked";
                cell.textContent = "—";
                row.appendChild(cell);
            }
            row.appendChild(statusCell);
            body.appendChild(row);
            continue;
        }

        row.appendChild(nameCell);
        for (const quantity of [warehouse.qty_needed, warehouse.qty_available, warehouse.qty_on_po, warehouse.qty_on_ibt]) {
            const cell = document.createElement("td");
            cell.className = "numeric";
            cell.textContent = formatQuantity(quantity);
            row.appendChild(cell);
        }
        const statusCell = document.createElement("td");
        const status = document.createElement("span");
        status.className = `qty-status ${warehouse.status}`;
        status.textContent = statusLabel(warehouse.status);
        statusCell.appendChild(status);
        row.appendChild(statusCell);
        body.appendChild(row);
        body.appendChild(detailRow);
    }
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
}

function appendTextCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value || "—";
    row.appendChild(cell);
}

function appendMessageRow(body, text, colSpan) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "qty-message";
    cell.colSpan = colSpan;
    cell.textContent = text;
    row.appendChild(cell);
    body.appendChild(row);
}

function statusLabel(status) {
    return ({ enough: "Enough stock", incoming: "Incoming covers need", action: "Action required" })[status] || "Action required";
}

function formatQuantity(value) {
    return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}