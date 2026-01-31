// Store all data in memory
let allHistoryData = [];

document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    loadDue();
    loadFilters();

    // Add event listeners for filtering (history only)
    document.querySelectorAll(
        "#warehouseFilter, #shelfFilter, #fromDate, #toDate, #varianceOnly"
    ).forEach(el => el.addEventListener("change", filterHistory));
});

// Collapsible toggle behaviour (enhance arrow visibility + state)
document.querySelectorAll(".stock-card.collapsible .toggle")
  .forEach(header => {
    header.addEventListener("click", () => {
      const card = header.closest(".stock-card");
      card.classList.toggle("open");

      // Optional: remember state
      const key = card.dataset.section;
      if (key) {
        localStorage.setItem(`stockcard_${key}`, card.classList.contains("open"));
      }
    });
  });

// Restore state on load (ensure open/closed from storage)
document.querySelectorAll(".stock-card.collapsible").forEach(card => {
  const key = card.dataset.section;
  if (!key) return;
  const open = localStorage.getItem(`stockcard_${key}`);
  if (open === "false") card.classList.remove("open");
  else if (open === "true") card.classList.add("open");
});

// --------------------------
// Filters modal controls
// --------------------------
function openFilterModal() {
    const fm = document.getElementById("filterModal");
    if (!fm) return;
    fm.classList.remove("hidden");
    fm.setAttribute("aria-hidden", "false");
}

function closeFilterModal() {
    const fm = document.getElementById("filterModal");
    if (!fm) return;
    fm.classList.add("hidden");
    fm.setAttribute("aria-hidden", "true");
}

// Apply filters and close modal
function applyAndCloseFilters() {
    // trigger existing change handlers and filterHistory
    document.getElementById("warehouseFilter")?.dispatchEvent(new Event('change'));
    document.getElementById("shelfFilter")?.dispatchEvent(new Event('change'));
    document.getElementById("fromDate")?.dispatchEvent(new Event('change'));
    document.getElementById("toDate")?.dispatchEvent(new Event('change'));
    document.getElementById("varianceOnly")?.dispatchEvent(new Event('change'));
    filterHistory();
    closeFilterModal();
}

// Close modal when clicking outside
document.addEventListener("click", (e) => {
    const scheduleModal = document.getElementById("scheduleModal");
    const countModal = document.getElementById("countModal");
    const filterModal = document.getElementById("filterModal");
    
    if (scheduleModal && e.target === scheduleModal) {
        closeScheduleModal();
    }
    if (countModal && e.target === countModal) {
        closeModal();
    }
    if (filterModal && e.target === filterModal) {
        closeFilterModal();
    }
});

// Restore state on load
document.querySelectorAll(".stock-card.collapsible").forEach(card => {
  const key = card.dataset.section;
  if (!key) return;
  const open = localStorage.getItem(`stockcard_${key}`);
  if (open === "false") card.classList.remove("open");
});


function getFilters() {
    return {
        warehouse: document.getElementById("warehouseFilter")?.value || "",
        shelf: document.getElementById("shelfFilter")?.value || "",
        from: document.getElementById("fromDate")?.value || "",
        to: document.getElementById("toDate")?.value || "",
        varianceOnly: document.getElementById("varianceOnly")?.checked || false
    };
}

function applyFilters(rows, filters) {
    return rows.filter(r => {
        // Warehouse filter
        if (filters.warehouse && r.warehouse !== filters.warehouse) return false;

        // Shelf filter
        if (filters.shelf && r.shelf !== filters.shelf) return false;

        // Date range filters
        if (filters.from) {
            const fromDate = new Date(filters.from);
            const rowDate = new Date(r.date);
            if (rowDate < fromDate) return false;
        }

        if (filters.to) {
            const toDate = new Date(filters.to);
            const rowDate = new Date(r.date);
            if (rowDate > toDate) return false;
        }

        // Variance only filter
        if (filters.varianceOnly && r.variance === 0) return false;

        return true;
    });
}

function filterHistory() {
    const filters = getFilters();
    // Filter to only completed counts before applying other filters
    const completedOnly = allHistoryData.filter(r => !r.canContinue);
    const filteredRows = applyFilters(completedOnly, filters);
    renderHistoryTable(filteredRows);
}

function getVarianceCategory(variance, systemQty) {
    if (variance === 0) return "clean";
    
    const variancePercent = Math.abs(variance / systemQty) * 100;
    
    // Slight variance: < 5%
    if (variancePercent < 5) return "slight";
    
    // Big variance: >= 5%
    return "big";
}

// Update renderHistoryTable to only show completed counts
function renderHistoryTable(rows) {
    const tbody = document.querySelector("#historyTable tbody");
    tbody.innerHTML = "";

    // Filter to only completed counts
    const completedRows = rows.filter(r => !r.canContinue);

    if (completedRows.length === 0) {
        tbody.insertAdjacentHTML("beforeend", `
            <tr>
                <td colspan="7" style="text-align: center; padding: 2rem; color: var(--secondary-text);">
                    <i class="fas fa-inbox"></i> No completed stock counts found
                </td>
            </tr>
        `);
        return;
    }

    completedRows.forEach(r => {
        const varianceCategory = getVarianceCategory(r.variance, r.systemQty);
        let statusBadge = '';
        let rowClass = '';

        if (varianceCategory === "clean") {
            statusBadge = '<span class="badge badge-completed"><i class="fas fa-check"></i> Clean</span>';
            rowClass = "ok";
        } else if (varianceCategory === "slight") {
            statusBadge = '<span class="badge badge-variance-slight"><i class="fas fa-exclamation"></i> Slight Variance</span>';
            rowClass = "warn";
        } else {
            statusBadge = '<span class="badge badge-variance-big"><i class="fas fa-exclamation-triangle"></i> Big Variance</span>';
            rowClass = "warn";
        }

        tbody.insertAdjacentHTML("beforeend", `
            <tr class="${rowClass}" onclick="openModal(${r.headerId})" style="cursor: pointer;">
                <td>${r.date}</td>
                <td>${r.warehouse}</td>
                <td>${r.shelf}</td>
                <td>${r.systemQty}</td>
                <td>${r.countedQty}</td>
                <td>${r.variance}</td>
                <td>${statusBadge}</td>
            </tr>
        `);
    });
}

// New function to render incomplete counts
function renderIncompleteTable(rows) {
    const tbody = document.querySelector("#incompleteTable tbody");
    tbody.innerHTML = "";

    // Filter to only incomplete counts
    const incompleteRows = rows.filter(r => r.canContinue);

    if (incompleteRows.length === 0) {
        tbody.insertAdjacentHTML("beforeend", `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: var(--secondary-text);">
                    <i class="fas fa-check-circle"></i> No incomplete counts
                </td>
            </tr>
        `);
        return;
    }

    incompleteRows.forEach(r => {
        console.log(r)
        // Progress is based on number of products counted vs total products
        // countedQty represents products with counted qty
        // systemQty represents total products to count
        const totalProducts = r.totalProducts || 0;
        const productsCountedLines = r.countedProducts || 0;
        const progressPercent = Math.round((productsCountedLines / totalProducts) * 100);
        
        tbody.insertAdjacentHTML("beforeend", `
            <tr class="in-progress">
                <td>${r.date}</td>
                <td>${r.warehouse}</td>
                <td>${r.shelf}</td>
                <td>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <div style="flex: 1; height: 24px; background: #e5e7eb; border-radius: 4px; overflow: hidden;">
                            <div style="height: 100%; width: ${progressPercent}%; background: #10b981; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 600; color: white;">
                                ${progressPercent > 10 ? progressPercent + '%' : ''}
                            </div>
                        </div>
                        <span style="font-size: 0.85rem; font-weight: 600; min-width: 50px; text-align: right;">${productsCountedLines}/${totalProducts}</span>
                    </div>
                </td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 4px; justify-content: center; flex-wrap: wrap;">
                        <button class="btn-action-small" onclick="continueCount(event, ${r.headerId})" title="Continue Counting">
                            <i class="fas fa-play"></i> Continue
                        </button>
                        <button class="btn-action-small danger" onclick="discardCount(event, ${r.headerId})" title="Discard This Count">
                            <i class="fas fa-trash"></i> Discard
                        </button>
                    </div>
                </td>
            </tr>
        `);
    });
}

async function discardCount(event, headerId) {
    event.stopPropagation(); // Prevent row click
    fetch(`/inventory/stock-counts/discard/${headerId}`, {
        method: "POST"
    }).then(res => res.json())
    .then(data => {
        if (data.success) {
            alert("Stock count discarded.");
            loadHistory();
        } else {
            alert("Error discarding stock count: " + (data.message || "Unknown error"));
        }
    }).catch(err => {
        console.error("Error discarding stock count:", err);
        alert("Error discarding stock count.");
    }
    );
}

async function loadDue() {
    try {
        const res = await fetch("/inventory/stock-counts/due");
        if (!res.ok) {
            console.warn("Due endpoint not available, skipping");
            return;
        }
        const rows = await res.json();

        const tbody = document.querySelector("#dueTable tbody");
        tbody.innerHTML = "";

        if (rows.length === 0) {
            tbody.insertAdjacentHTML("beforeend", `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 1.5rem; color: var(--secondary-text);">
                        <i class="fas fa-check-circle"></i> No schedules found
                    </td>
                </tr>
            `);
            return;
        }

        rows.forEach(r => {
            let badge = '';
            
            if (r.status === "Overdue") {
                badge = `<span class="badge badge-overdue"><i class="fas fa-exclamation-circle"></i> ${r.statusText}</span>`;
            } else if (r.status === "DueSoon") {
                badge = `<span class="badge badge-pending"><i class="fas fa-clock"></i> ${r.statusText}</span>`;
            } else {
                badge = `<span class="badge badge-completed"><i class="fas fa-check-circle"></i> ${r.statusText}</span>`;
            }

            tbody.insertAdjacentHTML("beforeend", `
                <tr>
                    <td>${r.warehouse} – ${r.warehouseDesc}</td>
                    <td>${r.shelf}</td>
                    <td>${r.frequency} days</td>
                    <td>${r.lastCount}</td>
                    <td>${r.nextDue}</td>
                    <td>${badge}</td>
                    <td style="text-align: center;">
                        <button class="btn-action-small" onclick="startCountFromSchedule('${r.shelf}')" title="Start Count">
                            <i class="fas fa-play-circle"></i> Start Count
                        </button>
                    </td>
                </tr>
            `);
        });
    } catch (err) {
        console.warn("Error loading due counts:", err);
    }
}

function startCountFromSchedule(shelfName) {
    window.location.href = `/inventory/start_stock_count?category=${encodeURIComponent(shelfName)}`;
}

// Schedule Modal Functions
function openScheduleModal() {
    // Load warehouses and categories
    loadScheduleOptions();
    document.getElementById("scheduleModal").classList.remove("hidden");
}

function closeScheduleModal() {
    document.getElementById("scheduleModal").classList.add("hidden");
    document.getElementById("scheduleForm").reset();
}

async function loadScheduleOptions() {
    try {
        const res = await fetch("/inventory/fetch_warehouses");
        const data = await res.json();

        const warehouseSelect = document.getElementById("scheduleWarehouse");
        const categorySelect = document.getElementById("scheduleCategory");
        categorySelect.disabled = true;

        warehouseSelect.innerHTML = "<option value=''>Select warehouse</option>";

        // Add warehouse options
        data.warehouses.forEach(w => {
            warehouseSelect.insertAdjacentHTML("beforeend", `<option value="${w.id}">${w.name}</option>`);
        });

        // Safe init: destroy only if already initialized
        if ($.fn.select2) {
            $(warehouseSelect).off('change'); // remove old handlers
            if ($(warehouseSelect).data('select2')) {
                $(warehouseSelect).select2('destroy');
            }
            $(warehouseSelect).select2({
                placeholder: "Select warehouse",
                allowClear: false,
                width: '100%'
            })
        }

        $(warehouseSelect).on('change', async () => {
            const warehouse = warehouseSelect.value;
            await fetch("/inventory/fetch_categories", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ whse_id: warehouse })
            }).then(response => response.json())
               .then(data => {
                    categorySelect.innerHTML = "<option value=''>Select category</option>";
                    // Add category options
                    data.categories.forEach(c => {
                        categorySelect.insertAdjacentHTML("beforeend", `<option value="${c.category_id}">${c.category_name}</option>`);
                    });
                     categorySelect.disabled = false;
                             // Safe init: destroy only if already initialized
                    if ($.fn.select2) {
                        $(categorySelect).off('change'); // remove old handlers
                        if ($(categorySelect).data('select2')) {
                            $(categorySelect).select2('destroy');
                        }
                        $(categorySelect).select2({
                            placeholder: "Select category",
                            allowClear: false,
                            width: '100%'
                        })
                    }
                });
        });
    } catch (err) {
        console.error("Error loading schedule options:", err);
    }
}

// Handle schedule form submission
document.addEventListener("DOMContentLoaded", () => {
    const scheduleForm = document.getElementById("scheduleForm");
    if (scheduleForm) {
        scheduleForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const warehouse = document.getElementById("scheduleWarehouse").value;
            const category = document.getElementById("scheduleCategory").value;
            const frequency = document.getElementById("scheduleFrequency").value;

            if (!warehouse || !category || !frequency) {
                alert("Please fill in all required fields");
                return;
            }

            try {
                const res = await fetch("/inventory/stock-counts/create_schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        warehouse,
                        category,
                        frequency: parseInt(frequency)
                    })
                });

                const data = await res.json();

                if (data.success) {
                    alert("Schedule created successfully!");
                    closeScheduleModal();
                    loadDue(); // Reload the table
                } else {
                    alert("Error: " + (data.message || "Failed to create schedule"));
                }
            } catch (err) {
                console.error("Error creating schedule:", err);
                alert("Error creating schedule");
            }
        });
    }
});

// Close modal when clicking outside
document.addEventListener("click", (e) => {
    const scheduleModal = document.getElementById("scheduleModal");
    const countModal = document.getElementById("countModal");
    
    if (scheduleModal && e.target === scheduleModal) {
        closeScheduleModal();
    }
    if (countModal && e.target === countModal) {
        closeModal();
    }
});

// Update loadHistory to render both tables
async function loadHistory() {
    try {
        const res = await fetch("/inventory/stock-counts/history");
        allHistoryData = await res.json();
        
        // Render both incomplete and completed tables
        renderIncompleteTable(allHistoryData);
        filterHistory(); // Apply filters to history table
    } catch (err) {
        console.error("Error loading history:", err);
        const tbody = document.querySelector("#historyTable tbody");
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 1.5rem; color: #dc2626;">
                    <i class="fas fa-exclamation-circle"></i> Error loading stock counts
                </td>
            </tr>
        `;
    }
}

// Update openModal to show variance category
async function openModal(headerId) {
    try {
        const res = await fetch(`/inventory/stock_count_details/${headerId}`);
        const data = await res.json();

        const modalTitle = document.getElementById("modalTitle");
        const modalLines = document.getElementById("modalLines");

        modalTitle.innerHTML = `<i class="fas fa-warehouse"></i> ${data.warehouse} – ${data.shelf} (${data.date})`;
        modalLines.innerHTML = "";

        if (data.lines.length === 0) {
            modalLines.insertAdjacentHTML("beforeend", `
                <tr>
                    <td colspan="5" style="text-align: center; padding: 1.5rem; color: var(--secondary-text);">
                        No line items found
                    </td>
                </tr>
            `);
        } else {
            data.lines.forEach(l => {
                const varianceCategory = getVarianceCategory(l.variance, l.system);
                let varianceText = '';
                let rowClass = '';

                if (varianceCategory === "clean") {
                    varianceText = '<span style="color: #10b981;"><i class="fas fa-check"></i> OK</span>';
                    rowClass = "ok";
                } else if (varianceCategory === "slight") {
                    const percent = ((Math.abs(l.variance) / l.system) * 100).toFixed(1);
                    varianceText = `<span style="color: #b45309;"><i class="fas fa-exclamation"></i> ${l.variance} (${percent}%)</span>`;
                    rowClass = "warn";
                } else {
                    const percent = ((Math.abs(l.variance) / l.system) * 100).toFixed(1);
                    varianceText = `<span style="color: #991b1b;"><i class="fas fa-times"></i> ${l.variance} (${percent}%)</span>`;
                    rowClass = "warn";
                }

                modalLines.insertAdjacentHTML("beforeend", `
                    <tr class="${rowClass}">
                        <td>${l.stock}</td>
                        <td>${l.description || "–"}</td>
                        <td style="text-align: right;">${l.system}</td>
                        <td style="text-align: right;">${l.counted}</td>
                        <td style="text-align: center;">${varianceText}</td>
                    </tr>
                `);
            });
        }

        document.getElementById("countModal").classList.remove("hidden");
    } catch (err) {
        console.error("Error loading count details:", err);
        alert("Error loading count details");
    }
}

function closeModal() {
    document.getElementById("countModal").classList.add("hidden");
}

async function loadFilters() {
    try {
        const res = await fetch("/inventory/stock-counts/filters");
        const data = await res.json();

        const warehouseFilter = document.getElementById("warehouseFilter");
        const shelfFilter = document.getElementById("shelfFilter");

        // Add warehouse options
        data.warehouses.forEach(w => {
            warehouseFilter.insertAdjacentHTML("beforeend", `<option value="${w}">${w}</option>`);
        });

        // Add shelf/category options
        data.shelves.forEach(s => {
            shelfFilter.insertAdjacentHTML("beforeend", `<option value="${s}">${s}</option>`);
        });
    } catch (err) {
        console.warn("Error loading filters:", err);
    }
}

// Close modal when clicking outside
document.addEventListener("click", (e) => {
    const modal = document.getElementById("countModal");
    if (modal && e.target === modal) {
        closeModal();
    }
});
