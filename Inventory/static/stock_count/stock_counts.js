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
    bindDocumentControls();
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

function bindDocumentControls() {
    const toggle = document.getElementById("documentToggle");
    const menu = document.getElementById("documentMenu");
    if (!toggle || !menu) return;

    toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        const shouldOpen = menu.classList.contains("hidden");
        menu.classList.toggle("hidden", !shouldOpen);
        toggle.setAttribute("aria-expanded", String(shouldOpen));
    });

    menu.querySelectorAll("[data-document-action]").forEach(button => {
        button.addEventListener("click", () => {
            const action = button.dataset.documentAction;
            handleDocumentAction(action);
            menu.classList.add("hidden");
            toggle.setAttribute("aria-expanded", "false");
        });
    });

    document.addEventListener("click", (event) => {
        if (!toggle.contains(event.target) && !menu.contains(event.target)) {
            menu.classList.add("hidden");
            toggle.setAttribute("aria-expanded", "false");
        }
    });
}

function buildPrintableDocumentHtml(doc) {
    const lines = Array.isArray(doc?.lines) ? doc.lines : [];
    const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
    const rows = lines.map(line => `
        <tr>
            <td>${escapeHtml(line.description || "-")}</td>
            <td style="text-align:right;">${Number(line.system || 0).toFixed(2)} ${escapeHtml(line.unit || "")}</td>
            <td style="text-align:right;">${line.counted === null || line.counted === undefined ? "N/A" : Number(line.counted).toFixed(2)} ${escapeHtml(line.unit || "")}</td>
            <td style="text-align:right;">${line.variance === null || line.variance === undefined ? "N/A" : Number(line.variance).toFixed(2)}</td>
        </tr>
    `).join("") || '<tr><td colspan="4" style="text-align:center; padding: 1rem;">No line items found.</td></tr>';

    const title = escapeHtml(doc?.title || "Stock Count Document");
    const logoUrl = escapeHtml(new URL("/main_static/icons/HorizontalLogoAndText.svg", window.location.origin).href);
    return `
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>${title}</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 32px; color: #111827; }
                .header { border-bottom: 1px solid #d1d5db; padding-bottom: 16px; margin-bottom: 20px; }
                .brand-mark { display: block; width: 100px; height: auto; margin-bottom: 12px; opacity: .62; }
                h1 { margin: 0 0 8px; font-size: 28px; }
                .meta { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin-top: 16px; }
                .meta-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; background: #f9fafb; }
                .meta-box span { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; margin-bottom: 4px; }
                table { width: 100%; border-collapse: collapse; margin-top: 12px; }
                th, td { border-bottom: 1px solid #e5e7eb; padding: 9px 10px; text-align: left; }
                th { background: #f3f4f6; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }
                @media print { body { margin: 16mm; } }
            </style>
        </head>
        <body>
            <div class="header">
                <img class="brand-mark" src="${logoUrl}" alt="Fermesync">
                <h1>Stock Count Document</h1>
                <div><strong>${title}</strong></div>
            </div>
            <div class="meta">
                <div class="meta-box"><span>Warehouse</span><strong>${escapeHtml(doc?.warehouse || "")}</strong></div>
                <div class="meta-box"><span>Created by</span><strong>${escapeHtml(doc?.username || "N/A")}</strong></div>
                <div class="meta-box"><span>Completed</span><strong>${escapeHtml(doc?.end_time || "N/A")}</strong></div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th>System Qty</th>
                        <th>Counted Qty</th>
                        <th>Variance</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </body>
        </html>
    `;
}

function printStockCountDocument(documentData) {
    const frame = document.createElement("iframe");
    frame.setAttribute("title", "Stock count print document");
    frame.setAttribute("aria-hidden", "true");
    frame.style.cssText = "position:fixed;left:-10000px;bottom:0;width:1px;height:1px;border:0;";
    frame.onload = () => {
        const frameWindow = frame.contentWindow;
        if (!frameWindow) {
            frame.remove();
            return;
        }
        frameWindow.addEventListener("afterprint", () => frame.remove(), { once: true });
        frameWindow.focus();
        frameWindow.print();
        setTimeout(() => frame.remove(), 60000);
    };
    frame.srcdoc = buildPrintableDocumentHtml(documentData);
    document.body.appendChild(frame);
}

function loadLowInkStockCountLogo() {
    return new Promise(resolve => {
        const image = new Image();
        image.onload = () => {
            try {
                const canvas = document.createElement("canvas");
                canvas.width = 900;
                canvas.height = Math.round(900 * image.naturalHeight / image.naturalWidth);
                const context = canvas.getContext("2d");
                if (!context) return resolve(null);
                context.fillStyle = "#fff";
                context.fillRect(0, 0, canvas.width, canvas.height);
                context.globalAlpha = 0.62;
                context.drawImage(image, 0, 0, canvas.width, canvas.height);
                resolve(canvas.toDataURL("image/png"));
            } catch (error) {
                resolve(null);
            }
        };
        image.onerror = () => resolve(null);
        image.src = "/main_static/icons/HorizontalLogoAndText.svg";
    });
}

const stockCountLogoPromise = loadLowInkStockCountLogo();

async function createStockCountPdf(documentData) {
    const jsPDF = window.jspdf?.jsPDF;
    if (!jsPDF) throw new Error("PDF sharing is unavailable because the PDF generator did not load.");

    const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 14;
    const tableWidth = pageWidth - margin * 2;
    const columns = [tableWidth * 0.46, tableWidth * 0.18, tableWidth * 0.18, tableWidth * 0.18];
    const title = documentData.title || "Stock Count";
    let y = 18;

    const logoDataUrl = await stockCountLogoPromise;
    if (logoDataUrl) {
        pdf.addImage(logoDataUrl, "PNG", margin, y, 42, 7.8);
        y += 13;
    }

    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(18);
    const titleLines = pdf.splitTextToSize(title, tableWidth);
    pdf.text(titleLines, margin, y);
    y += titleLines.length * 8 + 3;

    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(10);
    pdf.text(`Warehouse: ${documentData.warehouse || "N/A"}`, margin, y);
    pdf.text(`Counted by: ${documentData.username || "N/A"}`, margin + tableWidth / 2, y);
    y += 6;
    pdf.text(`Started: ${documentData.start_time || "N/A"}`, margin, y);
    pdf.text(`Completed: ${documentData.end_time || "N/A"}`, margin + tableWidth / 2, y);
    y += 10;

    const drawTableHeader = () => {
        pdf.setFillColor(239, 243, 247);
        pdf.rect(margin, y, tableWidth, 8, "F");
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(8.5);
        pdf.setTextColor(31, 41, 55);
        ["Description", "System Qty", "Counted Qty", "Variance"].forEach((label, index) => {
            const x = margin + columns.slice(0, index).reduce((total, width) => total + width, 0) + 2;
            pdf.text(label, x, y + 5.3);
        });
        y += 8;
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(9);
    };

    drawTableHeader();
    (documentData.lines || []).forEach(line => {
        const unit = line.unit ? ` ${line.unit}` : "";
        const descriptionLines = pdf.splitTextToSize(String(line.description || "-"), columns[0] - 4);
        const rowHeight = Math.max(7, descriptionLines.length * 4.5 + 2);
        if (y + rowHeight > pageHeight - margin) {
            pdf.addPage();
            y = margin;
            drawTableHeader();
        }

        pdf.setDrawColor(220, 225, 231);
        pdf.line(margin, y + rowHeight, margin + tableWidth, y + rowHeight);
        pdf.setTextColor(17, 24, 39);
        pdf.text(descriptionLines, margin + 2, y + 4.5);

        const values = [
            `${Number(line.system || 0).toFixed(2)}${unit}`,
            line.counted === null || line.counted === undefined ? "N/A" : `${Number(line.counted).toFixed(2)}${unit}`,
            line.variance === null || line.variance === undefined ? "N/A" : Number(line.variance).toFixed(2)
        ];
        let x = margin + columns[0];
        values.forEach((value, index) => {
            const cellWidth = columns[index + 1];
            pdf.text(value, x + cellWidth - 2, y + 4.5, { align: "right" });
            x += cellWidth;
        });
        y += rowHeight;
    });

    const filename = `${title.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "") || "stock-count"}.pdf`;
    return new File([pdf.output("blob")], filename, { type: "application/pdf" });
}

async function handleDocumentAction(action) {
    const documentData = window.currentStockCountDocument || {};

    if (action === "print") {
        printStockCountDocument(documentData);
        return;
    }

    if (action === "share") {
        try {
            const pdfFile = createStockCountPdf(documentData);
            if (navigator.share && navigator.canShare?.({ files: [pdfFile] })) {
                await navigator.share({
                    title: documentData.title || "Stock Count Document",
                    files: [pdfFile]
                });
                return;
            }

            Swal.fire({
                icon: "info",
                title: "PDF sharing unavailable",
                text: "This browser or device cannot share PDF files. Try the Share action on a device with file sharing support.",
                confirmButtonText: "OK"
            });
            return;
        } catch (error) {
            if (error.name === "AbortError") return;
            Swal.fire({
                icon: "error",
                title: "Unable to share PDF",
                text: error.message || "The stock count PDF could not be shared.",
                confirmButtonText: "OK"
            });
        }
    }
}

function showPostCompletionDocumentPrompt(data) {
    const summary = {
        title: `${data.warehouse_name || "Warehouse"} - ${data.shelf_name || "Shelf"}`,
        warehouse: data.warehouse_name || "Warehouse",
        username: data.counted_by || "N/A",
        start_time: data.start_time || "N/A",
        end_time: data.end_time || "N/A",
        lines: Array.isArray(data.lines) ? data.lines : []
    };
    window.currentStockCountDocument = summary;

    return Swal.fire({
        title: "Stock count complete",
        html: `
            <div style="display:flex; flex-direction:column; gap:16px; text-align:left; padding: 8px 4px;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; border-bottom:1px solid #e5e7eb; padding-bottom:12px;">
                    <div>
                        <div style="font-size:12px; letter-spacing:0.08em; text-transform:uppercase; color:#6b7280;">Completed</div>
                        <strong style="font-size:18px;">${summary.title}</strong>
                    </div>
                    <span style="display:inline-flex; align-items:center; justify-content:center; width:36px; height:36px; border-radius:999px; background:#dcfce7; color:#166534; font-weight:700;">✓</span>
                </div>
                <div style="display:flex; justify-content:center; gap:10px; flex-wrap:wrap;">
                    <button type="button" class="prompt-doc-action" data-prompt-action="print" style="border:none; border-radius:8px; background:#111827; color:#fff; padding:10px 16px; font-weight:700; cursor:pointer;">Print</button>
                    <button type="button" class="prompt-doc-action" data-prompt-action="share" style="border:none; border-radius:8px; background:#dbeafe; color:#1d4ed8; padding:10px 16px; font-weight:700; cursor:pointer;">Share PDF</button>
                </div>
            </div>
        `,
        showConfirmButton: false,
        showCancelButton: true,
        cancelButtonText: "Close",
        customClass: {
            popup: "stock-count-success-popup"
        },
        didOpen: () => {
            document.querySelectorAll(".prompt-doc-action").forEach(button => {
                button.addEventListener("click", () => {
                    handleDocumentAction(button.dataset.promptAction);
                });
            });
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
                        <div class="incomplete-actions">
                            <button class="btn-action-small danger" onclick="discardCount(event, ${item.headerId})">
                                <i class="fas fa-trash-alt" aria-hidden="true"></i> Discard
                            </button>
                            <button class="btn-action-small" onclick="continueCount(event, ${item.headerId})">
                                <i class="fas fa-play" aria-hidden="true"></i> Continue
                            </button>
                        </div>
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

async function discardCount(event, headerId) {
    event?.stopPropagation();
    const confirmation = await Swal.fire({
        icon: "warning",
        title: "Discard this stock count?",
        text: "This draft will be marked as discarded and can no longer be continued.",
        showCancelButton: true,
        confirmButtonText: "Discard count",
        cancelButtonText: "Keep count",
        confirmButtonColor: "#b42318",
        reverseButtons: true
    });
    if (!confirmation.isConfirmed) return;

    try {
        const response = await request(`/inventory/stock-counts/discard/${headerId}`, { method: "POST" });
        const data = await response.json();
        if (!data.success) {
            await Swal.fire("Unable to discard", data.message || "The stock count could not be discarded.", "error");
            return;
        }

        await loadOverview();
        await Swal.fire("Discarded", "The incomplete stock count has been discarded.", "success");
    } catch (error) {
        await Swal.fire("Unable to discard", "A network or server error occurred.", "error");
    }
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
        window.currentStockCountDocument = {
            title: `${data.warehouse} - ${data.shelf}`,
            warehouse: data.warehouse,
            username: data.counted_by || "N/A",
            start_time: data.start_time || "N/A",
            end_time: data.end_time || "N/A",
            lines: Array.isArray(data.lines) ? data.lines : []
        };

        const warehouseIcon = document.createElement("i");
        warehouseIcon.className = "fas fa-warehouse";
        warehouseIcon.setAttribute("aria-hidden", "true");
        modalTitle.replaceChildren(warehouseIcon, document.createTextNode(` ${window.currentStockCountDocument.title}`));
        document.getElementById("modalUsername").textContent = window.currentStockCountDocument.username;
        document.getElementById("modalStartTime").textContent = window.currentStockCountDocument.start_time;
        document.getElementById("modalEndTime").textContent = window.currentStockCountDocument.end_time;
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
