let allOverviewData = { warehouses: [], incomplete: [] };

const STATUS_LOOKUP = {
    recent: { label: "Recently counted", className: "status-recent" },
    due: { label: "Due", className: "status-due" },
    overdue: { label: "Overdue", className: "status-overdue" },
    never: { label: "Never counted", className: "status-never" }
};

const OVERVIEW_COLLAPSE_KEY = "stock-count-overview-collapsed";

function getStoredCollapseState(storageKey) {
    try {
        return JSON.parse(localStorage.getItem(storageKey) || "{}");
    } catch (err) {
        return {};
    }
}

function setStoredCollapseState(storageKey, itemKey, isCollapsed) {
    const state = getStoredCollapseState(storageKey);
    state[itemKey] = isCollapsed;
    localStorage.setItem(storageKey, JSON.stringify(state));
}

function bindCollapseToggle(button, panel, storageKey, itemKey) {
    const update = () => {
        const isCollapsed = getStoredCollapseState(storageKey)[itemKey] === true;
        panel.hidden = isCollapsed;
        button.setAttribute("aria-expanded", String(!isCollapsed));
        const icon = button.querySelector(".collapse-icon");
        icon?.classList.toggle("fa-chevron-down", !isCollapsed);
        icon?.classList.toggle("fa-chevron-right", isCollapsed);
    };

    update();
    button.addEventListener("click", () => {
        setStoredCollapseState(storageKey, itemKey, !panel.hidden);
        update();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    bindOverviewControls();
    loadOverview();
});

function bindOverviewControls() {
    document.getElementById("shelfSearch")?.addEventListener("input", renderOverview);
    document.getElementById("warehouseOverviewFilter")?.addEventListener("change", renderOverview);
    document.getElementById("needCountOnly")?.addEventListener("change", renderOverview);
}

function bindModalCloseHandlers() {
    document.addEventListener("click", (e) => {
        const countModal = document.getElementById("countModal");
        const shelfModal = document.getElementById("shelfModal");

        if (countModal && e.target === countModal) {
            closeModal();
        }
        if (shelfModal && e.target === shelfModal) {
            closeShelfModal();
        }
    });
}

function getOverviewFilters() {
    return {
        search: document.getElementById("shelfSearch")?.value.trim().toLowerCase() || "",
        warehouse: document.getElementById("warehouseOverviewFilter")?.value || "all",
        needCountOnly: document.getElementById("needCountOnly")?.checked || false
    };
}

function getStatusMeta(status) {
    return STATUS_LOOKUP[status] || STATUS_LOOKUP.recent;
}

function getDateTone(lastCount) {
    if (!lastCount) return "date-grey";

    const dateValue = new Date(lastCount + "T00:00:00");
    if (Number.isNaN(dateValue.getTime())) return "date-grey";

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffDays = Math.floor((today - dateValue) / 86400000);

    if (diffDays <= 14) return "date-green";
    if (diffDays <= 30) return "date-yellow";
    return "date-red";
}

function renderIncompleteSection(rows) {
    const container = document.getElementById("incompleteContainer");
    if (!container) return;

    if (!rows || rows.length === 0) {
        container.innerHTML = '<div class="incomplete-empty"><i class="fas fa-check-circle"></i> No incomplete stock counts</div>';
        return;
    }

    container.innerHTML = `
        <div class="incomplete-heading">${rows.length} incomplete stock count${rows.length === 1 ? "" : "s"}</div>
        ${rows.map(item => {
            const progress = item.progressPercent || 0;
            return `
                <div class="incomplete-row">
                    <div class="incomplete-details">
                        <span>${item.warehouse} · ${item.shelf}</span>
                        <small>${item.countedProducts}/${item.totalProducts} products</small>
                    </div>
                    <div class="incomplete-progress-wrap">
                        <div class="incomplete-progress" aria-label="${progress}% complete">
                            <div class="incomplete-progress-bar">
                                <div class="incomplete-progress-fill" style="width:${progress}%"></div>
                            </div>
                        </div>
                        <button class="btn-action-small" onclick="continueCount(event, ${item.headerId})">
                            <i class="fas fa-play"></i> Continue
                        </button>
                    </div>
                </div>
            `;
        }).join("")}
    `;
}

function renderOverview() {
    const filters = getOverviewFilters();

    const visibleWarehouses = (allOverviewData.warehouses || []).map(warehouse => {
        const visibleShelves = (warehouse.shelves || []).filter(shelf => {
            const text = `${warehouse.code} ${warehouse.description || ""} ${shelf.name}`.toLowerCase();
            if (filters.search && !text.includes(filters.search)) return false;
            if (filters.warehouse !== "all" && warehouse.code !== filters.warehouse) return false;
            if (filters.needCountOnly) {
                const daysSince = shelf.daysSince;
                if (daysSince === null || daysSince === undefined) return true;
                if (daysSince <= 14) return false;
            }
            return true;
        });

        return { ...warehouse, shelves: visibleShelves };
    }).filter(warehouse => warehouse.shelves.length > 0);

    const overviewContainer = document.getElementById("warehouseOverview");
    if (!overviewContainer) return;

    if (visibleWarehouses.length === 0) {
        overviewContainer.innerHTML = `
            <div class="no-results">
                <i class="fas fa-filter"></i>
                No shelves match the current filters.
            </div>
        `;
        return;
    }

    overviewContainer.innerHTML = visibleWarehouses.map(warehouse => `
        <div class="warehouse-section" data-warehouse-section="${warehouse.id}">
            <button class="warehouse-header collapse-toggle" type="button" aria-controls="warehouse-panel-${warehouse.id}">
                <span class="warehouse-title">
                    <h3>${warehouse.description || warehouse.code}</h3>
                    <span>${warehouse.shelves.length} shelf${warehouse.shelves.length === 1 ? "" : "s"}</span>
                </span>
                <i class="fas fa-chevron-down collapse-icon" aria-hidden="true"></i>
            </button>
            <div id="warehouse-panel-${warehouse.id}" class="warehouse-panel">
                <div class="warehouse-table-wrap">
                    <table class="table overview-table">
                        <thead>
                            <tr>
                                <th>Shelf</th>
                                <th>Last counted</th>
                                <th>Products linked</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${warehouse.shelves.map(shelf => {
                                const tone = getDateTone(shelf.lastCount);
                                return `
                                    <tr class="overview-row" data-warehouse-id="${warehouse.id}" data-category-id="${shelf.id}">
                                        <td data-label="Shelf"><strong>${shelf.name}</strong></td>
                                        <td data-label="Last counted"><span class="date-badge ${tone}">${shelf.lastCount || "Never"}</span></td>
                                        <td data-label="Products linked">${shelf.productCount ?? 0}</td>
                                        <td data-label="Actions" class="overview-actions">
                                            <button class="btn-action-small secondary" data-open-shelf="${warehouse.id}|${shelf.id}">View</button>
                                            <button class="btn-action-small primary" data-start-count="${warehouse.id}|${shelf.id}">Start count</button>
                                        </td>
                                    </tr>
                                `;
                            }).join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `).join("");

    document.querySelectorAll(".warehouse-section").forEach(section => {
        bindCollapseToggle(
            section.querySelector(".warehouse-header"),
            section.querySelector(".warehouse-panel"),
            OVERVIEW_COLLAPSE_KEY,
            section.dataset.warehouseSection
        );
    });

    document.querySelectorAll("[data-start-count]").forEach(button => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const [warehouseId, categoryId] = button.dataset.startCount.split("|");
            window.location.href = `/inventory/start_stock_count?warehouse=${warehouseId}&category=${categoryId}`;
        });
    });

    document.querySelectorAll("[data-open-shelf]").forEach(button => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const [warehouseId, categoryId] = button.dataset.openShelf.split("|");
            window.location.href = `/inventory/stock-counts/shelf/${warehouseId}/${categoryId}`;
        });
    });

    document.querySelectorAll(".overview-row").forEach(row => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("button")) return;
            const warehouseId = Number(row.dataset.warehouseId);
            const categoryId = Number(row.dataset.categoryId);
            window.location.href = `/inventory/stock-counts/shelf/${warehouseId}/${categoryId}`;
        });
    });
}

async function loadOverview() {
    try {
        const res = await request("/inventory/stock-counts/overview");
        const data = await res.json();

        if (!data.success) {
            const overviewContainer = document.getElementById("warehouseOverview");
            if (overviewContainer) {
                overviewContainer.innerHTML = `<div class="no-results"><i class="fas fa-exclamation-circle"></i> ${data.message || "Failed to load stock counts."}</div>`;
            }
            return;
        }

        allOverviewData = {
            warehouses: data.warehouses || [],
            incomplete: data.incomplete || []
        };

        renderIncompleteSection(allOverviewData.incomplete);
        renderOverview();
        populateOverviewFilters();
    } catch (err) {
        console.error("Error loading stock count overview:", err);
        const overviewContainer = document.getElementById("warehouseOverview");
        if (overviewContainer) {
            overviewContainer.innerHTML = '<div class="no-results"><i class="fas fa-exclamation-circle"></i> Error loading stock counts</div>';
        }
    }
}

function populateOverviewFilters() {
    const warehouseSelect = document.getElementById("warehouseOverviewFilter");
    if (!warehouseSelect) return;

    const currentValue = warehouseSelect.value || "all";
    const seen = new Set();
    warehouseSelect.innerHTML = '<option value="all">All warehouses</option>';

    (allOverviewData.warehouses || []).forEach(warehouse => {
        if (!seen.has(warehouse.code)) {
            seen.add(warehouse.code);
            const option = document.createElement("option");
            option.value = warehouse.code;
            option.textContent = warehouse.description || warehouse.code;
            if (warehouse.code === currentValue) option.selected = true;
            warehouseSelect.appendChild(option);
        }
    });
}

async function openShelfModal(warehouseId, categoryId) {
    try {
        const res = await request(`/inventory/stock-counts/shelf/${warehouseId}/${categoryId}`);
        const data = await res.json();
        if (!data.success) {
            Swal.fire("Error", data.message || "Failed to load shelf details.", "error");
            return;
        }

        const modal = document.getElementById("shelfModal");
        const title = document.getElementById("shelfModalTitle");
        const status = document.getElementById("shelfStatus");
        const lastCount = document.getElementById("shelfLastCount");
        const nextDue = document.getElementById("shelfNextDue");
        const historyTbody = document.getElementById("shelfHistoryTableBody");
        const startButton = document.getElementById("shelfStartCountButton");

        title.textContent = `${data.category.name} — ${data.warehouse.code}`;
        status.textContent = data.statusLabel || "—";
        status.className = `status-pill ${getStatusMeta(data.status).className}`;
        lastCount.textContent = data.lastCount || "Never";
        nextDue.textContent = data.nextDue || "—";

        startButton.onclick = () => {
            window.location.href = `/inventory/start_stock_count?warehouse=${warehouseId}&category=${categoryId}`;
        };

        if (!data.history || data.history.length === 0) {
            historyTbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 1.5rem; color: var(--secondary-text);">
                        No completed counts yet for this shelf.
                    </td>
                </tr>
            `;
        } else {
            historyTbody.innerHTML = data.history.map(item => `
                <tr class="history-row" data-header-id="${item.headerId}" style="cursor:pointer;">
                    <td>${item.date}</td>
                    <td>${item.user || "N/A"}</td>
                    <td>${item.totalProducts || 0}</td>
                    <td>${item.avgVariancePct === null || item.avgVariancePct === undefined ? "N/A" : `${Number(item.avgVariancePct).toFixed(1)}%`}</td>
                </tr>
            `).join("");

            historyTbody.querySelectorAll(".history-row").forEach(row => {
                row.addEventListener("click", () => openModal(Number(row.dataset.headerId)));
            });
        }

        modal.classList.remove("hidden");
    } catch (err) {
        console.error("Error loading shelf detail:", err);
        Swal.fire({
            icon: "error",
            title: "Load Error",
            text: "Unable to load shelf detail."
        });
    }
}

function closeShelfModal() {
    const modal = document.getElementById("shelfModal");
    if (modal) modal.classList.add("hidden");
}

function continueCount(event, headerId) {
    if (event) event.stopPropagation();
    window.location.href = `/inventory/stock-counts/${headerId}`;
}

async function openModal(headerId) {
    try {
        const res = await request(`/inventory/stock_count_details/${headerId}`);
        const data = await res.json();
        if (!data.success) {
            Swal.fire("Error", data.message || "Failed to load count details.", "error");
            return;
        }

        const modalTitle = document.getElementById("modalTitle");
        const modalLines = document.getElementById("modalLines");

        modalTitle.innerHTML = `<i class="fas fa-warehouse"></i> ${data.warehouse} - ${data.shelf}`;
        document.getElementById("modalUsername").textContent = data.counted_by || "N/A";
        document.getElementById("modalStartTime").textContent = data.start_time || "N/A";
        document.getElementById("modalEndTime").textContent = data.end_time || "N/A";
        modalLines.innerHTML = "";

        if (data.lines.length === 0) {
            modalLines.insertAdjacentHTML("beforeend", `
                <tr>
                    <td colspan="5" style="text-align:center; padding:1.5rem; color: var(--secondary-text);">No line items found</td>
                </tr>
            `);
        } else {
            data.lines.forEach(line => {
                const variance = line.variance ?? 0;
                const systemQty = Number(line.system) || 0;
                const variancePercent = systemQty === 0 ? 0 : (Math.abs(variance) / systemQty) * 100;
                let varianceText = "<span style=\"color:#10b981;\"><i class=\"fas fa-check\"></i> OK</span>";
                let rowClass = "ok";

                if (variance !== 0) {
                    if (variancePercent < 5) {
                        varianceText = `<span style="color:#b45309;"><i class="fas fa-exclamation"></i> ${variance} (${variancePercent.toFixed(1)}%)</span>`;
                        rowClass = "warn";
                    } else {
                        varianceText = `<span style="color:#991b1b;"><i class="fas fa-times"></i> ${variance} (${variancePercent.toFixed(1)}%)</span>`;
                        rowClass = "warn";
                    }
                }

                modalLines.insertAdjacentHTML("beforeend", `
                    <tr class="${rowClass}">
                        <td data-label="Description">${line.description || "–"}</td>
                        <td data-label="System Qty" style="text-align:right;">${line.system} ${line.unit || ""}</td>
                        <td data-label="Counted Qty" style="text-align:right;">${line.counted ?? "N/A"} ${line.unit || ""}</td>
                        <td data-label="Variance" style="text-align:center;">${varianceText}</td>
                    </tr>
                `);
            });
        }

        document.getElementById("countModal").classList.remove("hidden");
        closeShelfModal();
    } catch (err) {
        console.error("Error loading count details:", err);
        Swal.fire({
            icon: "error",
            title: "Load Error",
            text: "Error loading count details."
        });
    }
}

function closeModal() {
    const modal = document.getElementById("countModal");
    if (modal) modal.classList.add("hidden");
}
