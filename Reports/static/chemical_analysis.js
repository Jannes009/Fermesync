(function () {
  const globalFilters = {
    start_date: "", end_date: "", farm: [], project: [], crop: [], variety: [],
    group: [], product_type: [], product: []
  };
  const documentLocationParams = new URLSearchParams(window.location.search);
  const documentContext = documentLocationParams.get("print_context");
  const documentDrilldownQuery = documentLocationParams.get("drilldown_query") || "";
  const categoryPalettes = {
    farm: ["#2563eb", "#dc2626", "#0891b2", "#9333ea", "#ea580c", "#059669", "#db2777", "#4f46e5", "#ca8a04", "#0f766e", "#c026d3", "#0284c7", "#65a30d", "#e11d48", "#7c3aed", "#0d9488"],
    crop: ["#166534", "#a16207", "#047857", "#b45309", "#0e7490", "#4d7c0f", "#9a3412", "#15803d", "#854d0e", "#0f766e", "#65a30d", "#c2410c", "#115e59", "#713f12", "#3f6212", "#a3a322"],
    default: ["#2563eb", "#0f766e", "#7c3aed", "#c2410c", "#be123c", "#0891b2", "#4d7c0f", "#a21caf", "#b45309", "#1d4ed8", "#047857", "#9333ea", "#9f1239", "#0369a1", "#4f46e5", "#15803d"]
  };
  const categoryColorMaps = new Map();
  const categoryColorIndexes = new Map();
  const categoryUsedColors = new Map();
  let sourcePage = 1;
  let sourceSearch = "";
  let sourceSort = "tx_date";
  let sourceDirection = "desc";
  let filterRefreshTimer = null;
  let drilldownQuery = null;
  let drilldownController = null;
  let drilldownPage = 1;
  let drilldownContextBase = "";
  let documentActionInProgress = false;
  const charts = {};
  let dashboardController = null;
  let graphControllers = { chart1: null, chart2: null, chart3: null };
  const filterOptionContainers = {
    farm: "farmOptions",
    project: "projectOptions",
    crop: "cropOptions",
    variety: "varietyOptions",
    group: "groupOptions",
    product_type: "productTypeOptions",
    product: "productOptions"
  };

  function generatedCategoryColor(index) {
    const hue = ((index * 137.508) % 360).toFixed(1);
    const saturation = [72, 80, 68][index % 3];
    const lightness = [42, 48, 54][index % 3];
    return `hsl(${hue} ${saturation}% ${lightness}%)`;
  }

  function categoryColor(groupBy, value) {
    if (groupBy === "none" || value == null || value === "") return "#64748b";
    const key = String(value);
    if (!categoryColorMaps.has(groupBy)) categoryColorMaps.set(groupBy, new Map());
    if (!categoryUsedColors.has(groupBy)) categoryUsedColors.set(groupBy, new Set());
    const colors = categoryColorMaps.get(groupBy);
    if (colors.has(key)) return colors.get(key);

    const palette = categoryPalettes[groupBy] || categoryPalettes.default;
    const usedColors = categoryUsedColors.get(groupBy);
    let colorIndex = categoryColorIndexes.get(groupBy) || 0;
    let color;
    do {
      color = colorIndex < palette.length
        ? palette[colorIndex]
        : generatedCategoryColor(colorIndex - palette.length);
      colorIndex += 1;
    } while (usedColors.has(color));
    colors.set(key, color);
    usedColors.add(color);
    categoryColorIndexes.set(groupBy, colorIndex);
    return color;
  }

  function registerCategoryColors(groupBy, items) {
    (items || [])
      .slice()
      .sort((left, right) => String(left.id).localeCompare(String(right.id), undefined, { numeric: true }))
      .forEach(item => categoryColor(groupBy, item.id));
  }

  function initFilterDropdowns() {
    document.querySelectorAll(".filter-slicer").forEach(slicer => {
      const options = slicer.querySelector(".slicer-options");
      const actions = document.createElement("div");
      actions.className = "slicer-actions";
      actions.innerHTML = `
        <button type="button" class="slicer-action" data-action="all" title="Select all options" aria-label="Select all options">
          <i class="fas fa-check-double"></i>
        </button>
        <button type="button" class="slicer-action" data-action="invert" title="Invert selection" aria-label="Invert selection">
          <i class="fas fa-right-left"></i>
        </button>`;
      options.before(actions);
      actions.addEventListener("click", event => {
        const button = event.target.closest("button[data-action]");
        if (!button) return;
        const checkboxes = Array.from(options.querySelectorAll("input[type=checkbox]"));
        checkboxes.forEach(input => {
          input.checked = button.dataset.action === "all" ? true : !input.checked;
        });
        updateSlicerCount(slicer);
        updateActiveFilterCount();
        scheduleFilterRefresh();
      });
      slicer.querySelector(".slicer-trigger").addEventListener("click", () => {
        const opening = !slicer.classList.contains("open");
        document.querySelectorAll(".filter-slicer.open").forEach(item => item.classList.remove("open"));
        slicer.classList.toggle("open", opening);
        if (opening) slicer.querySelector(".slicer-search").focus();
      });
      slicer.querySelector(".slicer-search").addEventListener("input", event => {
        const search = event.target.value.trim().toLocaleLowerCase();
        slicer.querySelectorAll(".slicer-option").forEach(option => {
          option.hidden = !option.dataset.label.toLocaleLowerCase().includes(search);
        });
      });
      slicer.querySelector(".slicer-options").addEventListener("change", () => {
        updateSlicerCount(slicer);
        updateActiveFilterCount();
        scheduleFilterRefresh();
      });
    });
    document.addEventListener("click", event => {
      if (!event.target.closest(".filter-slicer")) {
        document.querySelectorAll(".filter-slicer.open").forEach(item => item.classList.remove("open"));
      }
    });
  }

  function updateSlicerCount(slicer) {
    const count = slicer.querySelectorAll(".slicer-options input:checked").length;
    slicer.querySelector(".slicer-count").textContent = count ? "(" + count + ")" : "";
  }

  function updateActiveFilterCount() {
    const activeSlicers = Array.from(document.querySelectorAll(".filter-slicer"))
      .filter(slicer => slicer.querySelector(".slicer-options input:checked")).length;
    const activeDates = ["startDate", "endDate"]
      .filter(id => document.getElementById(id).value).length;
    document.getElementById("activeFilterCount").textContent =
      activeSlicers + activeDates ? "(" + (activeSlicers + activeDates) + " active)" : "";
  }

  function scheduleFilterRefresh() {
    clearTimeout(filterRefreshTimer);
    filterRefreshTimer = setTimeout(refreshAll, 350);
  }

  function populateFilter(key, items) {
    const container = document.getElementById(filterOptionContainers[key]);
    const current = new Set(globalFilters[key].map(String));
    container.innerHTML = "";
    items.forEach(item => {
      const option = document.createElement("label");
      option.className = "slicer-option";
      option.dataset.label = String(item.label);
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = item.id;
      checkbox.checked = current.has(String(item.id));
      const swatch = document.createElement("span");
      swatch.className = "slicer-color-swatch";
      swatch.style.backgroundColor = categoryColor(key, item.id);
      const text = document.createElement("span");
      text.textContent = item.label;
      option.append(checkbox, swatch, text);
      container.appendChild(option);
    });
    updateSlicerCount(container.closest(".filter-slicer"));
  }

  function filterParams(extra) {
    const params = new URLSearchParams();
    Object.entries(globalFilters).forEach(([key, value]) => {
      if (Array.isArray(value)) value.forEach(item => params.append(key, item));
      else if (value) params.set(key, value);
    });
    if (extra) Object.entries(extra).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, value);
    });
    return params;
  }

  async function getJson(url, params, signal) {
    const response = await fetch(url + (params ? "?" + params.toString() : ""), { signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "Request failed");
    return data;
  }

  async function loadFilters() {
    try {
      const data = await getJson("/reports/api/chemical-analysis/filters", filterParams());
      if (!data.success) throw new Error(data.message);
      if (!globalFilters.start_date && data.period.start) {
        document.getElementById("startDate").value = data.period.start;
        document.getElementById("endDate").value = data.period.end;
        globalFilters.start_date = data.period.start;
        globalFilters.end_date = data.period.end;
      }
      registerCategoryColors("farm", data.farms);
      registerCategoryColors("project", data.projects);
      registerCategoryColors("crop", data.crops);
      registerCategoryColors("variety", data.varieties);
      registerCategoryColors("group", data.groups);
      registerCategoryColors("product_type", data.product_types);
      registerCategoryColors("product", data.products);
      populateFilter("farm", data.farms);
      populateFilter("project", data.projects);
      populateFilter("crop", data.crops);
      populateFilter("variety", data.varieties);
      populateFilter("group", data.groups);
      populateFilter("product_type", data.product_types);
      populateFilter("product", data.products);
      return true;
    } catch (error) {
      console.error(error);
      return false;
    }
  }

  function readFilterSelections() {
    globalFilters.start_date = document.getElementById("startDate").value;
    globalFilters.end_date = document.getElementById("endDate").value;
    Object.entries(filterOptionContainers).forEach(([key, containerId]) => {
      globalFilters[key] = Array.from(document.querySelectorAll("#" + containerId + " input:checked")).map(input => input.value);
    });
  }

  function setChip(label, onRemove) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "filter-chip";
    chip.textContent = label + " ×";
    chip.addEventListener("click", onRemove);
    document.getElementById("activeFilters").appendChild(chip);
  }

  function renderActiveFilters() {
    const container = document.getElementById("activeFilters");
    container.innerHTML = "";
    const labels = [
      ["start_date", "Start"],
      ["end_date", "End"],
      ["farm", "Farm"], ["project", "Project"], ["crop", "Crop"], ["variety", "Variety"],
      ["group", "Group"], ["product_type", "Product type"], ["product", "Product"]
    ];
    labels.forEach(([key, label]) => {
      const value = globalFilters[key];
      if (Array.isArray(value) && value.length) setChip(label + ": " + value.join(", "), () => {
        globalFilters[key] = [];
        const container = document.getElementById(filterOptionContainers[key]);
        container.querySelectorAll("input").forEach(input => { input.checked = false; });
        updateSlicerCount(container.closest(".filter-slicer"));
        refreshAll();
      });
      else if (!Array.isArray(value) && value) setChip(label + ": " + value, () => {
        globalFilters[key] = "";
        if (key === "start_date") document.getElementById("startDate").value = "";
        if (key === "end_date") document.getElementById("endDate").value = "";
        refreshAll();
      });
    });
    updateActiveFilterCount();
  }

  function applyKpis(data) {
    if (!data) return;
    document.getElementById("kpiCost").textContent = FermeReports.formatCurrency(data.total_cost);
    document.getElementById("kpiCostHa").textContent = data.cost_per_hectare === null ? "Unavailable" : FermeReports.formatCurrency(data.cost_per_hectare);
    document.getElementById("kpiHaNote").textContent = data.hectares_available ? FermeReports.formatNumber(data.hectares) + " ha" : "Missing reliable hectare data";
    const breakdown = data.quantity_breakdown || [];
    const quantityList = document.getElementById("kpiQuantityBreakdown");
    quantityList.textContent = breakdown.length
      ? breakdown.map(item =>
        FermeReports.formatNumber(item.quantity) + " " + (item.unit || "Unknown")
      ).join(", ")
      : "No quantity recorded";
    document.getElementById("kpiProducts").textContent = FermeReports.formatNumber(data.products_used);
  }

  function applyChart1(data) {
    const empty = document.getElementById("chart1Empty");
    empty.textContent = data.limited ? data.message : (data.labels && data.labels.length ? "" : "No data for the selected filters.");
    const groupBy = document.getElementById("chart1Group").value;
    const datasets = (data.datasets || []).map(dataset => ({
      ...dataset,
      borderColor: categoryColor(groupBy, dataset.selection_value),
      backgroundColor: categoryColor(groupBy, dataset.selection_value),
      tension: .25,
      fill: false
    }));
    if (!data.labels || !data.labels.length) {
      if (charts.chart1) {
        charts.chart1.data.labels = [];
        charts.chart1.data.datasets = [];
        charts.chart1.update();
      }
      return;
    }
    if (charts.chart1) {
      charts.chart1.data.labels = data.labels;
      charts.chart1.data.datasets = datasets;
      charts.chart1.$periodValues = data.period_values || data.labels;
      charts.chart1.$periodRanges = data.period_ranges || [];
      charts.chart1.update();
    } else {
      charts.chart1 = new Chart(document.getElementById("chart1"), {
        type: "line",
        data: { labels: data.labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          onClick: chart1Click,
          interaction: { mode: "index", intersect: false },
          scales: { y: { beginAtZero: true, ticks: { callback: value => document.getElementById("chart1Measure").value === "cost" ? FermeReports.formatCurrency(value) : FermeReports.formatNumber(value) } } },
          plugins: { legend: { position: "bottom" } }
        }
      });
      charts.chart1.$periodValues = data.period_values || data.labels;
      charts.chart1.$periodRanges = data.period_ranges || [];
    }
  }

  function applyBarChart(chartNumber, data) {
    const canvasId = "chart" + chartNumber;
    const empty = document.getElementById(canvasId + "Empty");
    empty.textContent = data.limited ? data.message : (data.items && data.items.length ? "" : "No data for the selected filters.");
    if (!data.items || !data.items.length) {
      if (charts[canvasId]) {
        charts[canvasId].data.labels = [];
        charts[canvasId].data.datasets = [];
        charts[canvasId].update();
      }
      return;
    }
    const measure = document.getElementById(canvasId + "Measure").value;
    const groupBy = document.getElementById(canvasId + "Group").value;
    const chartData = {
      labels: data.items.map(item => item.label),
      datasets: [{
        label: measure === "cost" ? "Cost" : "Quantity",
        data: data.items.map(item => item.value),
        backgroundColor: data.items.map(item => categoryColor(groupBy, item.selection_value)),
        borderColor: data.items.map(item => categoryColor(groupBy, item.selection_value)),
        borderRadius: 3
      }]
    };
    const onClick = (event, elements) => {
      if (!elements.length) return;
      const item = data.items[elements[0].index];
      openDrilldown(chartNumber, item, null);
    };
    if (charts[canvasId]) {
      charts[canvasId].data = chartData;
      charts[canvasId].options.onClick = onClick;
      charts[canvasId].update();
    } else {
      charts[canvasId] = new Chart(document.getElementById(canvasId), {
        type: "bar",
        data: chartData,
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          onClick,
          scales: { x: { beginAtZero: true } },
          plugins: { legend: { display: false } }
        }
      });
    }
  }

  function applyPieChart(data) {
    const canvasId = "chart3";
    const empty = document.getElementById("chart3Empty");
    empty.textContent = data.limited ? data.message : (data.items && data.items.length ? "" : "No data for the selected filters.");
    if (!data.items || !data.items.length) {
      if (charts.chart3) {
        charts.chart3.data.labels = [];
        charts.chart3.data.datasets = [];
        charts.chart3.update();
      }
      return;
    }
    const groupBy = document.getElementById("chart3Group").value;
    const measure = document.getElementById("chart3Measure").value;
    registerCategoryColors(groupBy, data.items.map(item => ({id: item.selection_value})));
    const chartData = {
      labels: data.items.map(item => item.label),
      datasets: [{
        label: measure === "cost" ? "Cost" : "Quantity",
        data: data.items.map(item => item.value),
        backgroundColor: data.items.map(item => categoryColor(groupBy, item.selection_value)),
        borderColor: "#ffffff",
        borderWidth: 2
      }]
    };
    const onClick = (event, elements) => {
      if (!elements.length) return;
      openDrilldown(3, data.items[elements[0].index], null, null);
    };
    if (charts[canvasId]) {
      charts[canvasId].data = chartData;
      charts[canvasId].options.onClick = onClick;
      charts[canvasId].update();
    } else {
      charts[canvasId] = new Chart(document.getElementById(canvasId), {
        type: "pie",
        data: chartData,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          onClick,
          plugins: {
            legend: { position: "right" },
            tooltip: {
              callbacks: {
                label: context => context.label + ": " +
                  (measure === "cost" ? FermeReports.formatCurrency(context.parsed) : FermeReports.formatNumber(context.parsed))
              }
            }
          }
        }
      });
    }
  }

  function chart1Click(event, elements) {
    if (!elements.length) return;
    const point = elements[0];
    const dataset = charts.chart1.data.datasets[point.datasetIndex];
    const periodValue = charts.chart1.$periodValues[point.index];
    const periodLabel = charts.chart1.data.labels[point.index];
    const periodRange = charts.chart1.$periodRanges[point.index] || null;
    openDrilldown(1, dataset, periodValue, periodLabel, periodRange);
  }

  function destroyChart(id) {
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  }

  function initGroupTiles() {
    document.querySelectorAll(".group-tile").forEach(button => {
      button.addEventListener("click", () => {
        const target = button.dataset.target;
        const input = document.getElementById(target);
        if (input.value === button.dataset.value) return;
        input.value = button.dataset.value;
        button.closest(".group-tile-list").querySelectorAll(".group-tile").forEach(tile => {
          const selected = tile === button;
          tile.classList.toggle("active", selected);
          tile.setAttribute("aria-pressed", String(selected));
        });
        updateSubtitles();
        if (target === "chart1Group") loadChart1();
        if (target === "chart2Group") loadBarChart(2);
        if (target === "chart3Group") loadBarChart(3);
      });
    });
  }

  async function loadChart1() {
    const controllerKey = "chart1";
    if (graphControllers[controllerKey]) graphControllers[controllerKey].abort();
    graphControllers[controllerKey] = new AbortController();
    const card = document.getElementById("chart1").closest(".chart-card");
    card.classList.add("loading");
    const params = filterParams({
      chart: 1,
      measure: document.getElementById("chart1Measure").value,
      calculation: document.getElementById("chart1Calculation").value,
      group_by: document.getElementById("chart1Group").value,
      interval: document.getElementById("chart1Interval").value,
      cumulative: document.getElementById("chart1Cumulative").value
    });
    try {
      const data = await getJson("/reports/api/chemical-analysis/chart-data", params, graphControllers[controllerKey].signal);
      applyChart1(data);
    } catch (error) {
      if (error.name !== "AbortError") document.getElementById("chart1Empty").textContent = "Could not load this chart. " + error.message;
    } finally {
      card.classList.remove("loading");
    }
  }

  async function loadBarChart(chartNumber) {
    const controllerKey = "chart" + chartNumber;
    if (graphControllers[controllerKey]) graphControllers[controllerKey].abort();
    graphControllers[controllerKey] = new AbortController();
    const card = document.getElementById(controllerKey).closest(".chart-card");
    card.classList.add("loading");
    const measure = document.getElementById("chart" + chartNumber + "Measure").value;
    const calculation = document.getElementById("chart" + chartNumber + "Calculation").value;
    const groupBy = document.getElementById("chart" + chartNumber + "Group").value;
    const params = filterParams({chart: chartNumber, measure, calculation, group_by: groupBy});
    try {
      const data = await getJson("/reports/api/chemical-analysis/chart-data", params, graphControllers[controllerKey].signal);
      if (chartNumber === 3) applyPieChart(data);
      else applyBarChart(chartNumber, data);
    } catch (error) {
      if (error.name !== "AbortError") document.getElementById(controllerKey + "Empty").textContent = "Could not load this chart. " + error.message;
    } finally {
      card.classList.remove("loading");
    }
  }

  function renderSourceRows(rows) {
    const tbody = document.getElementById("sourceRows");
    tbody.innerHTML = "";
    rows.forEach(row => {
      const tr = document.createElement("tr");
      [
        row.tx_date ? String(row.tx_date).slice(0,10) : "-", row.farm || "-", row.project || "-", row.crop || "-", row.variety || "-",
        row.group || "-", row.product || "-", row.ingredient || "-", FermeReports.formatNumber(row.quantity) + " " + (row.unit || ""),
        FermeReports.formatCurrency(row.cost), row.spray_hectares == null ? "-" : FermeReports.formatNumber(row.spray_hectares)
      ].forEach(value => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      const instructionCell = document.createElement("td");
      if (row.spray_link) {
        const link = document.createElement("a");
        link.href = row.spray_link;
        link.textContent = row.spray_header_no || "View instruction";
        instructionCell.appendChild(link);
      } else {
        instructionCell.textContent = row.spray_header_no || "-";
      }
      tr.appendChild(instructionCell);
      tbody.appendChild(tr);
    });
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:var(--secondary-text)">No source records found.</td></tr>';
    }
  }

  async function loadSourceData() {
    document.getElementById("sourceLoading").classList.add("active");
    const params = filterParams({
      page: sourcePage, page_size: 50, search: sourceSearch,
      sort: sourceSort, direction: sourceDirection
    });
    try {
      const data = await getJson("/reports/api/chemical-analysis/source-data", params);
      renderSourceRows(data.rows);
      document.getElementById("sourcePage").textContent = "Page " + data.page + " of " + data.pages + " (" + data.total + " records)";
      document.getElementById("sourcePrev").disabled = data.page <= 1;
      document.getElementById("sourceNext").disabled = data.page >= data.pages;
    } catch (error) {
      console.error(error);
    } finally {
      document.getElementById("sourceLoading").classList.remove("active");
    }
  }

  function openDrilldown(chartNumber, item, periodValue, periodLabel, periodRange, shouldLoad) {
    const groupBy = chartNumber === 1
      ? document.getElementById("chart1Group").value
      : document.getElementById("chart" + chartNumber + "Group").value;
    const measure = document.getElementById("chart" + chartNumber + "Measure").value;
    const calculation = document.getElementById("chart" + chartNumber + "Calculation").value;
    const extra = {
      chart: chartNumber,
      group_by: groupBy,
      measure,
      calculation,
      selection_label: item.label,
      page_size: 25
    };
    if (groupBy !== "none") extra.group_value = item.selection_value;
    if (chartNumber === 1) {
      extra.interval = document.getElementById("chart1Interval").value;
      extra.cumulative = document.getElementById("chart1Cumulative").value;
      extra.period = periodValue;
      extra.period_label = periodLabel;
      if (periodRange) {
        extra.period_start = periodRange.start;
        extra.period_end = periodRange.end;
      }
    }
    drilldownQuery = filterParams(extra).toString();
    drilldownPage = 1;
    const groupLabel = selectedGroupLabel(chartNumber === 1 ? "chart1Group" : "chart" + chartNumber + "Group");
    const intervalLabels = {
      daily: "Daily",
      weekly: "Weekly",
      monthly: "Monthly",
      plant_week: "Planting-relative"
    };
    const metricLabel = measure === "cost" ? "Expenditure" : "Quantity";
    const calculationLabel = calculation === "per_hectare" ? "Per hectare" : "Total";
    const title = chartNumber === 1
      ? (groupBy === "none" ? periodLabel : item.label + " — " + periodLabel)
      : item.label + " — " + metricLabel;
    document.getElementById("drilldownTitle").textContent = title;
    drilldownContextBase = [
      groupBy === "none" ? "Overall" : groupLabel,
      metricLabel,
      calculationLabel
    ];
    if (chartNumber === 1) {
      drilldownContextBase.push(intervalLabels[extra.interval] || extra.interval);
      if (extra.cumulative === "true") drilldownContextBase.push("Cumulative");
    }
    document.getElementById("drilldownMeta").textContent = drilldownContextBase.join(" · ");
    document.getElementById("drilldownModal").classList.add("open");
    document.getElementById("drilldownModal").setAttribute("aria-hidden", "false");
    moveDocumentActionsToModal();
    if (shouldLoad !== false) loadDrilldown(1);
  }

  function moveDocumentActionsToModal() {
    const actions = document.getElementById("documentActions");
    const exportButton = document.getElementById("drilldownExport");
    if (actions && exportButton && actions.parentElement !== exportButton.parentElement) {
      exportButton.before(actions);
    }
  }

  function moveDocumentActionsToHeading() {
    const actions = document.getElementById("documentActions");
    const placeholder = document.getElementById("documentActionsPlaceholder");
    if (actions && placeholder) placeholder.after(actions);
  }

  function setDrilldownState(kind, message, canRetry) {
    const status = document.getElementById("drilldownStatus");
    status.innerHTML = "";
    status.className = "drilldown-status drilldown-status-" + kind;
    status.hidden = !message;
    if (!message) return;
    const icon = document.createElement("i");
    icon.className = kind === "loading" ? "fas fa-circle-notch fa-spin" :
      kind === "empty" ? "far fa-folder-open" : "fas fa-exclamation-circle";
    icon.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.className = "drilldown-status-message";
    text.textContent = message;
    status.append(icon, text);
    if (canRetry) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "drilldown-retry";
      retry.textContent = "Retry";
      retry.addEventListener("click", () => loadDrilldown(drilldownPage));
      status.appendChild(retry);
    }
  }

  function renderDrilldownSummary(data) {
    const summary = data.summary;
    const container = document.getElementById("drilldownSummary");
    container.innerHTML = "";
    const addCard = (label, value, highlight) => {
      const card = document.createElement("div");
      card.className = "drilldown-metric" + (highlight ? " drilldown-metric-highlight" : "");
      const title = document.createElement("span");
      title.textContent = label;
      const amount = document.createElement("strong");
      amount.textContent = value;
      card.append(title, amount);
      container.appendChild(card);
    };
    const finite = value => value !== null && value !== undefined && Number.isFinite(Number(value));
    if (finite(summary.chart_value)) {
      const selectedValue = data.measure === "cost"
        ? FermeReports.formatCurrency(summary.chart_value)
        : FermeReports.formatNumber(summary.chart_value);
      addCard(
        "Selected chart value",
        selectedValue + (data.calculation === "per_hectare" ? " / ha" : ""),
        true
      );
    }
    if (finite(summary.total_cost)) addCard("Total expenditure", FermeReports.formatCurrency(summary.total_cost), false);
    if (finite(summary.record_count)) addCard("Transactions", FermeReports.formatNumber(summary.record_count), false);
    if (finite(summary.hectares) && Number(summary.hectares) > 0) {
      addCard("Hectares", FermeReports.formatNumber(summary.hectares) + " ha", false);
      if (finite(summary.total_cost)) {
        addCard(
          "Cost per hectare",
          FermeReports.formatCurrency(Number(summary.total_cost) / Number(summary.hectares)),
          false
        );
      }
    }
  }

  function showDrilldownLoading() {
    document.getElementById("drilldownSummary").innerHTML =
      '<div class="drilldown-metric-skeleton"></div>'.repeat(4);
    document.getElementById("drilldownRows").innerHTML =
      '<tr class="drilldown-row-skeleton"><td colspan="12"><span></span></td></tr>'.repeat(5);
    document.getElementById("drilldownModal").setAttribute("aria-busy", "true");
    setDrilldownState("loading", "Loading transactions…", false);
    document.getElementById("drilldownPage").textContent = "";
    document.getElementById("drilldownPrev").disabled = true;
    document.getElementById("drilldownNext").disabled = true;
  }

  function renderDrilldownRows(rows) {
    const tbody = document.getElementById("drilldownRows");
    tbody.innerHTML = "";
    rows.forEach(row => {
      const tr = document.createElement("tr");
      const cells = [
        {value: row.tx_date ? String(row.tx_date).slice(0, 10) : "-"},
        {value: row.farm || "-"},
        {value: row.project || "-"},
        {value: row.crop || "-"},
        {value: row.variety || "-"},
        {value: row.product || "-", className: "drilldown-product-cell"},
        {value: row.ingredient || "-"},
        {value: row.quantity == null ? "-" : FermeReports.formatNumber(row.quantity) + (row.unit ? " " + row.unit : ""), className: "drilldown-numeric-cell"},
        {value: row.unit_cost == null ? "-" : FermeReports.formatCurrency(row.unit_cost), className: "drilldown-numeric-cell"},
        {value: row.cost == null ? "-" : FermeReports.formatCurrency(row.cost), className: "drilldown-numeric-cell"},
        {value: row.spray_header_no || "-"}
      ];
      cells.forEach(value => {
        const td = document.createElement("td");
        td.textContent = value.value;
        if (value.className) td.className = value.className;
        tr.appendChild(td);
      });
      const instructionCell = document.createElement("td");
      if (row.spray_link) {
        const link = document.createElement("a");
        link.href = row.spray_link;
        link.innerHTML = '<i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i> ';
        link.appendChild(document.createTextNode(row.spray_header_no || "View instruction"));
        instructionCell.appendChild(link);
      } else {
        instructionCell.textContent = row.spray_header_no || "-";
      }
      tr.appendChild(instructionCell);
      tbody.appendChild(tr);
    });
  }

  async function loadDrilldown(page) {
    if (!drilldownQuery) return;
    if (drilldownController) drilldownController.abort();
    const controller = new AbortController();
    drilldownController = controller;
    drilldownPage = page;
    const params = new URLSearchParams(drilldownQuery);
    params.set("page", String(page));
    showDrilldownLoading();
    document.getElementById("drilldownNote").textContent = "";
    document.getElementById("drilldownNote").hidden = true;
    try {
      const data = await getJson("/reports/api/chemical-analysis/drilldown", params, controller.signal);
      if (drilldownController !== controller) return;
      const summary = data.summary;
      renderDrilldownSummary(data);
      const note = document.getElementById("drilldownNote");
      note.hidden = !data.non_additive;
      note.textContent = data.non_additive
        ? "Active-ingredient combinations are not additive."
        : "";
      let timeContext = "";
      if (data.period_range) {
        const rangeText = data.period_range.start + " – " + data.period_range.end;
        timeContext = data.cumulative
          ? "Period " + rangeText + " · Cumulative through " + data.period_range.end
          : rangeText;
      } else if (data.period_label) {
        timeContext = data.period_label + " · dates vary by transaction";
      }
      document.getElementById("drilldownMeta").textContent =
        [drilldownContextBase.join(" · "), timeContext].filter(Boolean).join(" · ");
      renderDrilldownRows(data.rows);
      document.getElementById("drilldownModal").setAttribute("aria-busy", "false");
      setDrilldownState(
        "empty",
        data.total ? "" : "No transactions were found for this chart point.",
        false
      );
      document.getElementById("drilldownPage").textContent =
        "Page " + data.page + " of " + data.pages + " (" + data.total + " transactions)";
      document.getElementById("drilldownPrev").disabled = data.page <= 1;
      document.getElementById("drilldownNext").disabled = data.page >= data.pages;
      return true;
    } catch (error) {
      if (error.name !== "AbortError" && drilldownController === controller) {
        document.getElementById("drilldownRows").innerHTML = "";
        document.getElementById("drilldownSummary").innerHTML = "";
        document.getElementById("drilldownModal").setAttribute("aria-busy", "false");
        setDrilldownState("error", "Could not load transactions. " + error.message, true);
      }
      return false;
    }
  }

  function closeDrilldown() {
    document.getElementById("drilldownModal").classList.remove("open");
    document.getElementById("drilldownModal").setAttribute("aria-hidden", "true");
    document.getElementById("drilldownModal").setAttribute("aria-busy", "false");
    drilldownQuery = null;
    moveDocumentActionsToHeading();
    if (drilldownController) drilldownController.abort();
  }

  async function refreshAll() {
    readFilterSelections();
    renderActiveFilters();
    if (dashboardController) dashboardController.abort();
    dashboardController = new AbortController();
    const params = filterParams({
      chart1_measure: document.getElementById("chart1Measure").value,
      chart1_calculation: document.getElementById("chart1Calculation").value,
      chart1_group: document.getElementById("chart1Group").value,
      chart1_interval: document.getElementById("chart1Interval").value,
      chart1_cumulative: document.getElementById("chart1Cumulative").value,
      chart2_measure: document.getElementById("chart2Measure").value,
      chart2_calculation: document.getElementById("chart2Calculation").value,
      chart2_group: document.getElementById("chart2Group").value,
      chart3_measure: document.getElementById("chart3Measure").value,
      chart3_calculation: document.getElementById("chart3Calculation").value,
      chart3_group: document.getElementById("chart3Group").value
    });
    let succeeded = true;
    try {
      const data = await getJson("/reports/api/chemical-analysis/dashboard", params, dashboardController.signal);
      applyKpis(data.kpis);
      applyChart1(data.chart1);
      applyBarChart(2, data.chart2);
      applyPieChart(data.chart3);
    } catch (error) {
      if (error.name !== "AbortError") {
        succeeded = false;
        ["chart1Empty","chart2Empty","chart3Empty"].forEach(id => document.getElementById(id).textContent = "Could not load report data. " + error.message);
      }
    }
    if (document.getElementById("sourceTab").classList.contains("active")) {
      sourcePage = 1;
      await loadSourceData();
    }
    return succeeded;
  }

  document.getElementById("clearFilters").addEventListener("click", () => {
    clearTimeout(filterRefreshTimer);
    Object.keys(globalFilters).forEach(key => globalFilters[key] = Array.isArray(globalFilters[key]) ? [] : "");
    document.getElementById("startDate").value = "";
    document.getElementById("endDate").value = "";
    document.querySelectorAll(".slicer-options input").forEach(control => {
      control.checked = false;
    });
    document.querySelectorAll(".filter-slicer").forEach(updateSlicerCount);
    updateActiveFilterCount();
    refreshAll();
  });
  ["startDate", "endDate"].forEach(id =>
    document.getElementById(id).addEventListener("change", scheduleFilterRefresh)
  );
  document.getElementById("filterCollapse").addEventListener("click", event => {
    const grid = document.getElementById("filterGrid");
    grid.classList.toggle("collapsed");
    event.currentTarget.setAttribute("aria-expanded", String(!grid.classList.contains("collapsed")));
  });

  document.querySelectorAll(".report-tab").forEach(tab => tab.addEventListener("click", () => {
    document.querySelectorAll(".report-tab").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.tab === "source" ? "sourceTab" : "reportTab").classList.add("active");
    if (tab.dataset.tab === "source") loadSourceData();
  }));

  function updateSubtitles() {
    const chart1Measure = document.getElementById("chart1Measure").value;
    const chart1Calculation = document.getElementById("chart1Calculation").value;
    const chart1Cumulative = document.getElementById("chart1Cumulative").value === "true";
    const chart1Group = selectedGroupLabel("chart1Group");
    const chart1IntervalLabels = {
      daily: "daily",
      weekly: "weekly",
      monthly: "monthly",
      plant_week: "planting-relative"
    };
    const chart1Interval = chart1IntervalLabels[document.getElementById("chart1Interval").value];
    document.getElementById("chart1Subtitle").textContent =
      (chart1Measure === "cost" ? "Cost" : "Quantity") + " " +
      (chart1Calculation === "per_hectare" ? "per hectare" : "total") + " by " +
      chart1Group.toLowerCase() + ", " + chart1Interval.toLowerCase() +
      (chart1Cumulative ? " (cumulative)" : "");
    document.getElementById("chart1PlantDateNote").classList.toggle(
      "visible", document.getElementById("chart1Interval").value === "plant_week"
    );

    const chart2Measure = document.getElementById("chart2Measure").value;
    const chart2Calculation = document.getElementById("chart2Calculation").value;
    const chart2Group = selectedGroupLabel("chart2Group");
    document.getElementById("chart2Subtitle").textContent =
      (chart2Measure === "cost" ? "Cost" : "Quantity") + " " +
      (chart2Calculation === "per_hectare" ? "per hectare" : "total") + " by " + chart2Group.toLowerCase();

    const chart3Measure = document.getElementById("chart3Measure").value;
    const chart3Calculation = document.getElementById("chart3Calculation").value;
    const chart3Group = selectedGroupLabel("chart3Group");
    document.getElementById("chart3Subtitle").textContent =
      (chart3Measure === "cost" ? "Cost" : "Quantity") + " " +
      (chart3Calculation === "per_hectare" ? "per hectare" : "total") + " by " + chart3Group.toLowerCase();
  }

  function selectedGroupLabel(target) {
    const selected = document.querySelector('.group-tile[data-target="' + target + '"][aria-pressed="true"] span');
    return selected ? selected.textContent : "";
  }

  function setSegmentedValue(target, value) {
    const group = document.querySelector('.segmented[data-target="' + target + '"]');
    const button = group && Array.from(group.querySelectorAll("button")).find(item => item.dataset.value === value);
    if (!button) return;
    group.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
    document.getElementById(target).value = value;
  }

  function setGroupValue(target, value) {
    const button = Array.from(document.querySelectorAll('.group-tile[data-target="' + target + '"]'))
      .find(item => item.dataset.value === value);
    if (!button) return;
    button.closest(".group-tile-list").querySelectorAll(".group-tile").forEach(item => {
      const selected = item === button;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    document.getElementById(target).value = value;
  }

  function initializeDocumentState() {
    if (!documentContext) return;
    const params = documentContext === "drilldown"
      ? new URLSearchParams(documentDrilldownQuery)
      : documentLocationParams;
    ["start_date", "end_date"].forEach(key => {
      if (params.has(key)) {
        globalFilters[key] = params.get(key);
        document.getElementById(key === "start_date" ? "startDate" : "endDate").value = params.get(key);
      }
    });
    Object.keys(filterOptionContainers).forEach(key => {
      if (params.has(key)) globalFilters[key] = params.getAll(key);
    });
    [
      ["chart1_measure", "chart1Measure"], ["chart1_calculation", "chart1Calculation"],
      ["chart2_measure", "chart2Measure"], ["chart2_calculation", "chart2Calculation"],
      ["chart3_measure", "chart3Measure"], ["chart3_calculation", "chart3Calculation"]
    ].forEach(([param, target]) => {
      if (params.has(param)) setSegmentedValue(target, params.get(param));
    });
    [
      ["chart1_group", "chart1Group"], ["chart2_group", "chart2Group"], ["chart3_group", "chart3Group"]
    ].forEach(([param, target]) => {
      if (params.has(param)) setGroupValue(target, params.get(param));
    });
    if (params.has("chart1_interval")) {
      const interval = params.get("chart1_interval");
      document.getElementById("chart1Interval").value = interval;
      document.querySelectorAll('.interval-option[data-target="chart1Interval"]').forEach(button => {
        const selected = button.dataset.value === interval;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
    }
    if (params.has("chart1_cumulative")) {
      document.getElementById("chart1Cumulative").value = params.get("chart1_cumulative");
    }
    if (documentContext === "source") {
      sourceSearch = params.get("search") || "";
      sourceSort = params.get("sort") || sourceSort;
      sourceDirection = params.get("direction") || sourceDirection;
      document.getElementById("sourceSearch").value = sourceSearch;
    }
  }

  function getDocumentContext() {
    if (document.getElementById("drilldownModal").classList.contains("open")) return "drilldown";
    return document.getElementById("sourceTab").classList.contains("active") ? "source" : "report";
  }

  function getDocumentRequest(context) {
    readFilterSelections();
    if (context === "drilldown") {
      if (!drilldownQuery) throw new Error("Open a chart drill-down before creating its document.");
      return {context, query: drilldownQuery};
    }
    if (context === "source") {
      return {
        context,
        query: filterParams({
          search: sourceSearch,
          sort: sourceSort,
          direction: sourceDirection
        }).toString()
      };
    }
    return {
      context,
      query: filterParams({
        chart1_measure: document.getElementById("chart1Measure").value,
        chart1_calculation: document.getElementById("chart1Calculation").value,
        chart1_group: document.getElementById("chart1Group").value,
        chart1_interval: document.getElementById("chart1Interval").value,
        chart1_cumulative: document.getElementById("chart1Cumulative").value,
        chart2_measure: document.getElementById("chart2Measure").value,
        chart2_calculation: document.getElementById("chart2Calculation").value,
        chart2_group: document.getElementById("chart2Group").value,
        chart3_measure: document.getElementById("chart3Measure").value,
        chart3_calculation: document.getElementById("chart3Calculation").value,
        chart3_group: document.getElementById("chart3Group").value
      }).toString()
    };
  }

  function selectedFilterSummary() {
    const labels = [];
    Object.entries(filterOptionContainers).forEach(([key, containerId]) => {
      const selected = Array.from(document.querySelectorAll("#" + containerId + " input:checked"))
        .map(input => input.closest(".slicer-option").dataset.label);
      if (selected.length) {
        const name = key === "product_type" ? "Product type" :
          key.charAt(0).toUpperCase() + key.slice(1).replace("_", " ");
        labels.push(name + ": " + selected.join(", "));
      }
    });
    if (sourceSearch) labels.push("Search: " + sourceSearch);
    return labels.length ? labels.join(" · ") : "No additional filters";
  }

  function setDocumentMetadata(context) {
    const period = [
      globalFilters.start_date ? globalFilters.start_date : "All dates",
      globalFilters.end_date ? globalFilters.end_date : ""
    ].filter(Boolean).join(" to ");
    const generated = "Generated " + new Date().toLocaleString();
    const filters = selectedFilterSummary();
    if (context === "drilldown") {
      document.getElementById("drilldownPrintMeta").hidden = false;
      document.getElementById("drilldownPrintReport").textContent =
        "Chemical & Fertiliser Analysis — " + document.getElementById("drilldownTitle").textContent;
      document.getElementById("drilldownPrintPeriod").textContent =
        "Reporting period: " + period + (document.getElementById("drilldownMeta").textContent
          ? " · " + document.getElementById("drilldownMeta").textContent
          : "");
      document.getElementById("drilldownPrintFilters").textContent = "Filters: " + filters;
      document.getElementById("drilldownPrintGenerated").textContent = generated;
      return;
    }
    document.getElementById("documentPrintMeta").hidden = false;
    document.getElementById("documentPrintPeriod").textContent = "Reporting period: " + period;
    document.getElementById("documentPrintFilters").textContent = "Filters: " + filters;
    document.getElementById("documentPrintGenerated").textContent = generated;
  }

  async function loadAllSourceRows() {
    const params = filterParams({
      all: 1,
      page: 1,
      page_size: 50000,
      search: sourceSearch,
      sort: sourceSort,
      direction: sourceDirection
    });
    const data = await getJson("/reports/api/chemical-analysis/source-data", params);
    renderSourceRows(data.rows);
    document.getElementById("sourcePage").textContent = "All " + data.total + " matching records";
    document.getElementById("sourcePrev").disabled = true;
    document.getElementById("sourceNext").disabled = true;
  }

  async function loadAllDrilldownRows() {
    if (!drilldownQuery) throw new Error("The drill-down transaction query is unavailable.");
    const params = new URLSearchParams(drilldownQuery);
    params.set("all", "1");
    params.set("page", "1");
    params.set("page_size", "50000");
    const data = await getJson("/reports/api/chemical-analysis/drilldown", params);
    renderDrilldownRows(data.rows);
    document.getElementById("drilldownPage").textContent = "All " + data.total + " matching transactions";
    document.getElementById("drilldownPrev").disabled = true;
    document.getElementById("drilldownNext").disabled = true;
  }

  async function prepareDocumentDrilldown() {
    const params = new URLSearchParams(documentDrilldownQuery);
    const chartNumber = Number(params.get("chart"));
    if (![1, 2, 3].includes(chartNumber)) throw new Error("The drill-down context is invalid.");
    const groupValue = params.get("group_value");
    const selectionLabel = params.get("selection_label") || groupValue || "Overall";
    const periodRange = params.has("period_start") && params.has("period_end")
      ? {start: params.get("period_start"), end: params.get("period_end")}
      : null;
    openDrilldown(
      chartNumber,
      {label: selectionLabel, selection_value: groupValue},
      params.get("period") || "",
      params.get("period_label") || params.get("period") || selectionLabel,
      periodRange,
      false
    );
    drilldownQuery = documentDrilldownQuery;
    if (!await loadDrilldown(1)) throw new Error("Could not load the drill-down summary.");
    await loadAllDrilldownRows();
  }

  function activateReportTab(tab) {
    document.querySelectorAll(".report-tab").forEach(item => item.classList.toggle("active", item.dataset.tab === tab));
    document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
    document.getElementById(tab === "source" ? "sourceTab" : "reportTab").classList.add("active");
  }

  async function prepareDocumentContext(context) {
    readFilterSelections();
    const restoreState = {
      sourceTabActive: document.getElementById("sourceTab").classList.contains("active"),
      printMetaHidden: document.getElementById("documentPrintMeta").hidden,
      drilldownPrintMetaHidden: document.getElementById("drilldownPrintMeta").hidden,
      sourceRows: context === "source" ? document.getElementById("sourceRows").innerHTML : null,
      sourcePage: context === "source" ? document.getElementById("sourcePage").textContent : null,
      sourcePrevDisabled: context === "source" ? document.getElementById("sourcePrev").disabled : null,
      sourceNextDisabled: context === "source" ? document.getElementById("sourceNext").disabled : null,
      sourceScrollTop: context === "source" ? document.querySelector("#sourceTab .table-scroll").scrollTop : null,
      drilldownRows: context === "drilldown" ? document.getElementById("drilldownRows").innerHTML : null,
      drilldownPage: context === "drilldown" ? document.getElementById("drilldownPage").textContent : null,
      drilldownPrevDisabled: context === "drilldown" ? document.getElementById("drilldownPrev").disabled : null,
      drilldownNextDisabled: context === "drilldown" ? document.getElementById("drilldownNext").disabled : null,
      drilldownScrollTop: context === "drilldown" ? document.querySelector(".drilldown-table-scroll").scrollTop : null,
      chartSizes: {}
    };
    document.body.dataset.documentContext = context;
    document.body.classList.add("document-printing");
    try {
      if (context === "source") {
        activateReportTab("source");
        await loadAllSourceRows();
      } else if (context === "drilldown") {
        if (!document.getElementById("drilldownModal").classList.contains("open")) {
          await prepareDocumentDrilldown();
        } else {
          await loadAllDrilldownRows();
        }
      } else if (context === "report") {
        if (!await refreshAll()) throw new Error("The report charts could not be refreshed for printing.");
      } else if (context !== "report") {
        throw new Error("Unknown document context.");
      }
      if (context === "report") await resizeChartsForPrint(restoreState.chartSizes);
      setDocumentMetadata(context);
      return () => {
        if (!document.body.classList.contains("document-printing")) return;
        document.body.classList.remove("document-printing");
        delete document.body.dataset.documentContext;
        document.getElementById("documentPrintMeta").hidden = restoreState.printMetaHidden;
        document.getElementById("drilldownPrintMeta").hidden = restoreState.drilldownPrintMetaHidden;
        if (context === "source") {
          document.getElementById("sourceRows").innerHTML = restoreState.sourceRows;
          document.getElementById("sourcePage").textContent = restoreState.sourcePage;
          document.getElementById("sourcePrev").disabled = restoreState.sourcePrevDisabled;
          document.getElementById("sourceNext").disabled = restoreState.sourceNextDisabled;
          document.querySelector("#sourceTab .table-scroll").scrollTop = restoreState.sourceScrollTop;
          activateReportTab(restoreState.sourceTabActive ? "source" : "report");
        }
        if (context === "drilldown") {
          document.getElementById("drilldownRows").innerHTML = restoreState.drilldownRows;
          document.getElementById("drilldownPage").textContent = restoreState.drilldownPage;
          document.getElementById("drilldownPrev").disabled = restoreState.drilldownPrevDisabled;
          document.getElementById("drilldownNext").disabled = restoreState.drilldownNextDisabled;
          document.querySelector(".drilldown-table-scroll").scrollTop = restoreState.drilldownScrollTop;
        }
        restoreChartSizes(restoreState.chartSizes);
      };
    } catch (error) {
      document.body.classList.remove("document-printing");
      delete document.body.dataset.documentContext;
      document.getElementById("documentPrintMeta").hidden = restoreState.printMetaHidden;
      document.getElementById("drilldownPrintMeta").hidden = restoreState.drilldownPrintMetaHidden;
      if (context === "source") {
        document.getElementById("sourceRows").innerHTML = restoreState.sourceRows;
        document.getElementById("sourcePage").textContent = restoreState.sourcePage;
        document.getElementById("sourcePrev").disabled = restoreState.sourcePrevDisabled;
        document.getElementById("sourceNext").disabled = restoreState.sourceNextDisabled;
        document.querySelector("#sourceTab .table-scroll").scrollTop = restoreState.sourceScrollTop;
        activateReportTab(restoreState.sourceTabActive ? "source" : "report");
      }
      if (context === "drilldown") {
        document.getElementById("drilldownRows").innerHTML = restoreState.drilldownRows;
        document.getElementById("drilldownPage").textContent = restoreState.drilldownPage;
        document.getElementById("drilldownPrev").disabled = restoreState.drilldownPrevDisabled;
        document.getElementById("drilldownNext").disabled = restoreState.drilldownNextDisabled;
        document.querySelector(".drilldown-table-scroll").scrollTop = restoreState.drilldownScrollTop;
      }
      restoreChartSizes(restoreState.chartSizes);
      throw error;
    }
  }

  function resizeChartsForPrint(savedSizes) {
    Object.values(charts).forEach(chart => {
      if (!chart) return;
      if (!savedSizes[chart.canvas.id]) {
        savedSizes[chart.canvas.id] = {width: chart.width, height: chart.height};
      }
      chart.stop();
      chart.resize();
      chart.update("none");
    });
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function restoreChartSizes(savedSizes) {
    Object.values(charts).forEach(chart => {
      const size = chart && savedSizes[chart.canvas.id];
      if (!size) return;
      chart.resize(size.width, size.height);
      chart.update("none");
    });
  }

  window.__fermePrepareForPdf = async () => {
    await resizeChartsForPrint({});
  };

  window.addEventListener("beforeprint", () => {
    if (document.body.classList.contains("document-printing") &&
        document.body.dataset.documentContext === "report") {
      Object.values(charts).forEach(chart => {
        if (!chart) return;
        chart.stop();
        chart.resize();
        chart.update("none");
      });
    }
  });

  const documentActions = document.getElementById("documentActions");
  const documentButton = document.getElementById("documentButton");
  const documentMenu = document.getElementById("documentMenu");
  const documentGenerationStatus = document.getElementById("documentGenerationStatus");
  const documentShareDialog = document.getElementById("documentShareDialog");
  const documentShareConfirm = document.getElementById("documentShareConfirm");
  const documentShareDownload = document.getElementById("documentShareDownload");
  const documentShareCancel = document.getElementById("documentShareCancel");
  let documentOpenedByHover = false;

  function setDocumentMenuOpen(open) {
    documentMenu.hidden = !open;
    documentButton.setAttribute("aria-expanded", String(open));
  }

  function notifyDocument(icon, title, text) {
    if (window.Swal) {
      window.Swal.fire({icon, title, text});
    } else {
      window.alert(title + "\n" + text);
    }
  }

  function documentFilename(response) {
    const header = response.headers.get("Content-Disposition") || "";
    const match = header.match(/filename="?([^";]+)"?/i);
    return match ? match[1] : "Chemical_Analysis_" + new Date().toISOString().slice(0, 10) + ".pdf";
  }

  async function generateDocumentPdf(request) {
    documentGenerationStatus.hidden = false;
    documentActions.setAttribute("aria-busy", "true");
    documentMenu.querySelectorAll("[data-document-action]").forEach(button => { button.disabled = true; });
    try {
      const response = await fetch("/reports/api/chemical-analysis/document.pdf", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(request)
      });
      if (!response.ok) {
        let message = "Could not generate the PDF.";
        try {
          const data = await response.json();
          message = data.message || message;
        } catch (_) {
          // Keep the generic message when the server does not return JSON.
        }
        throw new Error(message);
      }
      return {blob: await response.blob(), filename: documentFilename(response)};
    } finally {
      documentGenerationStatus.hidden = true;
      documentActions.removeAttribute("aria-busy");
      documentMenu.querySelectorAll("[data-document-action]").forEach(button => { button.disabled = false; });
    }
  }

  function downloadPdf(blob, filename) {
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  async function shareDocumentPdf({blob, filename}) {
    if (typeof File === "undefined") {
      downloadPdf(blob, filename);
      notifyDocument(
        "info",
        "PDF ready to share",
        "This browser cannot share files directly. The PDF was downloaded so you can attach it to a message."
      );
      return;
    }
    const file = new File([blob], filename, {type: "application/pdf"});
    if (!navigator.share || !navigator.canShare || !navigator.canShare({files: [file]})) {
      downloadPdf(blob, filename);
      notifyDocument(
        "info",
        "PDF ready to share",
        "This browser cannot share files directly. The PDF was downloaded so you can attach it to a message."
      );
      return;
    }
    await new Promise((resolve, reject) => {
      let completed = false;
      const finish = error => {
        if (completed) return;
        completed = true;
        documentShareDialog.hidden = true;
        documentButton.focus();
        documentShareConfirm.disabled = false;
        documentShareDownload.disabled = false;
        documentShareCancel.disabled = false;
        documentShareConfirm.removeEventListener("click", shareFile);
        documentShareDownload.removeEventListener("click", downloadFile);
        documentShareCancel.removeEventListener("click", cancel);
        if (error && error.name !== "AbortError") reject(error);
        else resolve();
      };
      const shareFile = () => {
        documentShareConfirm.disabled = true;
        documentShareDownload.disabled = true;
        documentShareCancel.disabled = true;
        let sharePromise;
        try {
          sharePromise = navigator.share({
            files: [file],
            title: "Chemical & Fertiliser Analysis"
          });
        } catch (error) {
          finish(error);
          return;
        }
        Promise.resolve(sharePromise).then(() => finish(), finish);
      };
      const downloadFile = () => {
        downloadPdf(file, filename);
        finish();
      };
      const cancel = () => finish();
      documentShareConfirm.addEventListener("click", shareFile);
      documentShareDownload.addEventListener("click", downloadFile);
      documentShareCancel.addEventListener("click", cancel);
      documentShareDialog.hidden = false;
      documentShareConfirm.focus();
    });
  }

  function printDocumentPdf({blob}, printWindow) {
    const objectUrl = URL.createObjectURL(blob);
    let cleanupTimer;
    let cleanedUp = false;
    const cleanup = () => {
      if (cleanedUp) return;
      cleanedUp = true;
      window.clearInterval(cleanupTimer);
      URL.revokeObjectURL(objectUrl);
    };
    cleanupTimer = window.setInterval(() => {
      if (printWindow.closed) cleanup();
    }, 1000);
    printWindow.addEventListener("load", () => {
      printWindow.focus();
      printWindow.addEventListener("afterprint", cleanup, {once: true});
      printWindow.print();
    }, {once: true});
    printWindow.location.replace(objectUrl);
  }

  documentButton.addEventListener("click", () => {
    if (documentMenu.hidden) {
      setDocumentMenuOpen(true);
    } else if (documentOpenedByHover) {
      documentOpenedByHover = false;
    } else {
      setDocumentMenuOpen(false);
    }
  });
  documentButton.addEventListener("keydown", event => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setDocumentMenuOpen(true);
      documentMenu.querySelector("button").focus();
    }
  });
  documentActions.addEventListener("pointerenter", event => {
    if (event.pointerType === "mouse") {
      documentOpenedByHover = true;
      setDocumentMenuOpen(true);
    }
  });
  documentActions.addEventListener("pointerleave", event => {
    if (event.pointerType === "mouse" && !documentActions.contains(document.activeElement)) {
      documentOpenedByHover = false;
      setDocumentMenuOpen(false);
    }
  });
  document.addEventListener("pointerdown", event => {
    if (!documentActions.contains(event.target)) setDocumentMenuOpen(false);
  });
  documentShareDialog.addEventListener("click", event => {
    if (event.target === documentShareDialog) documentShareCancel.click();
  });
  documentShareDialog.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault();
      documentShareCancel.click();
    } else if (event.key === "Tab") {
      const buttons = [documentShareConfirm, documentShareDownload, documentShareCancel];
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  documentMenu.addEventListener("keydown", event => {
    const items = Array.from(documentMenu.querySelectorAll("button"));
    const index = items.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      items[(index + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      items[event.key === "Home" ? 0 : items.length - 1].focus();
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !documentMenu.hidden) {
      event.preventDefault();
      event.stopPropagation();
      setDocumentMenuOpen(false);
      if (documentActions.contains(document.activeElement)) documentButton.focus();
    }
  }, true);
  documentMenu.addEventListener("click", async event => {
    const button = event.target.closest("[data-document-action]");
    if (!button || documentActionInProgress) return;
    setDocumentMenuOpen(false);
    documentActionInProgress = true;
    let printWindow = null;
    try {
      const request = getDocumentRequest(getDocumentContext());
      if (button.dataset.documentAction === "print") {
        printWindow = window.open("about:blank", "_blank");
        if (!printWindow) throw new Error("Allow pop-ups to print the PDF.");
      }
      const result = await generateDocumentPdf(request);
      if (button.dataset.documentAction === "print") {
        printDocumentPdf(result, printWindow);
      } else if (button.dataset.documentAction === "download") {
        downloadPdf(result.blob, result.filename);
      } else if (button.dataset.documentAction === "share") {
        await shareDocumentPdf(result);
      }
    } catch (error) {
      if (printWindow && !printWindow.closed) printWindow.close();
      console.error("Document action failed:", error);
      notifyDocument("error", "Document action failed", error.message);
    } finally {
      documentActionInProgress = false;
    }
  });

  document.querySelectorAll(".segmented").forEach(group => {
    group.addEventListener("click", event => {
      const button = event.target.closest("button");
      if (!button) return;
      group.querySelectorAll("button").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(group.dataset.target).value = button.dataset.value;
      updateSubtitles();
      const target = group.dataset.target;
      if (target.startsWith("chart1")) loadChart1();
      if (target.startsWith("chart2")) loadBarChart(2);
      if (target.startsWith("chart3")) loadBarChart(3);
    });
  });

  document.querySelectorAll(".interval-option").forEach(button => {
    button.addEventListener("click", () => {
      const interval = document.getElementById(button.dataset.target);
      if (interval.value === button.dataset.value) return;
      interval.value = button.dataset.value;
      button.closest(".interval-selector").querySelectorAll(".interval-option").forEach(option => {
        const selected = option === button;
        option.classList.toggle("active", selected);
        option.setAttribute("aria-pressed", String(selected));
      });
      updateSubtitles();
      loadChart1();
    });
  });

  document.getElementById("sourceSearch").addEventListener("input", event => {
    sourceSearch = event.target.value;
    sourcePage = 1;
    clearTimeout(window.sourceSearchTimer);
    window.sourceSearchTimer = setTimeout(loadSourceData, 300);
  });
  document.querySelectorAll("th[data-sort]").forEach(header => header.addEventListener("click", () => {
    const key = header.dataset.sort;
    sourceDirection = sourceSort === key && sourceDirection === "desc" ? "asc" : "desc";
    sourceSort = key;
    sourcePage = 1;
    loadSourceData();
  }));
  document.getElementById("sourcePrev").addEventListener("click", () => { sourcePage--; loadSourceData(); });
  document.getElementById("sourceNext").addEventListener("click", () => { sourcePage++; loadSourceData(); });
  document.querySelectorAll("[data-close-drilldown]").forEach(button =>
    button.addEventListener("click", closeDrilldown)
  );
  document.getElementById("drilldownModal").addEventListener("click", event => {
    if (event.target === event.currentTarget) closeDrilldown();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && document.getElementById("drilldownModal").classList.contains("open")) {
      closeDrilldown();
    }
  });
  document.getElementById("drilldownPrev").addEventListener("click", () => loadDrilldown(drilldownPage - 1));
  document.getElementById("drilldownNext").addEventListener("click", () => loadDrilldown(drilldownPage + 1));
  document.getElementById("drilldownExport").addEventListener("click", () => {
    if (drilldownQuery) {
      window.location.href = "/reports/api/chemical-analysis/drilldown/export?" +
        new URLSearchParams(drilldownQuery).toString();
    }
  });
  document.getElementById("exportExcel").addEventListener("click", event => {
    event.preventDefault();
    window.location.href = "/reports/api/chemical-analysis/export?" + filterParams({search: sourceSearch}).toString();
  });

  function showRefreshStatus(status) {
    const element = document.getElementById("refreshStatus");
    if (!status || !status.refreshed_at) {
      element.textContent = "Reporting table has not been refreshed.";
      return;
    }
    const date = new Date(status.refreshed_at);
    element.textContent = "Last refreshed " + date.toLocaleString() + " · " + FermeReports.formatNumber(status.row_count) + " rows";
  }

  async function checkRefreshStatus() {
    try {
      const data = await getJson("/reports/api/chemical-analysis/status");
      showRefreshStatus(data.refresh);
      if (!data.refresh) {
        await refreshData(false);
      }
    } catch (error) {
      document.getElementById("refreshStatus").textContent = "Could not check refresh status.";
    }
  }

  async function refreshData(confirmFirst) {
    if (confirmFirst && !window.confirm("Refresh the Chemical Costs reporting table now?")) return;
    const button = document.getElementById("refreshData");
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Refreshing...';
    document.getElementById("refreshStatus").textContent = "Refreshing reporting table...";
    try {
      const response = await fetch("/reports/api/chemical-analysis/refresh", { method: "POST" });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.message || "Refresh failed");
      showRefreshStatus(data.refresh);
      window.Swal ? Swal.fire({ icon:"success", title:"Data refreshed", text:data.message, timer:1800, showConfirmButton:false }) : alert(data.message);
      await refreshAll();
    } catch (error) {
      document.getElementById("refreshStatus").textContent = "Refresh failed: " + error.message;
      window.Swal ? Swal.fire({ icon:"error", title:"Refresh failed", text:error.message }) : alert(error.message);
    } finally {
      button.disabled = false;
      button.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh Data';
    }
  }

  document.getElementById("refreshData").addEventListener("click", () => refreshData(true));

  initializeDocumentState();
  initFilterDropdowns();
  initGroupTiles();
  updateSubtitles();
  loadFilters().then(async filtersLoaded => {
    await checkRefreshStatus();
    const reportLoaded = await refreshAll();
    if (documentContext) {
      if (!filtersLoaded) throw new Error("Report filters could not be loaded.");
      if (!reportLoaded) throw new Error("The report data could not be loaded.");
      if (documentContext === "drilldown") {
        await prepareDocumentDrilldown();
        document.body.dataset.documentContext = "drilldown";
        document.body.classList.add("document-printing");
        setDocumentMetadata("drilldown");
      } else {
        await prepareDocumentContext(documentContext);
      }
      window.__fermeDocumentReady = true;
    }
  }).catch(error => {
    console.error("Could not prepare report document:", error);
    if (documentContext) window.__fermeDocumentError = error.message || "Could not prepare report document.";
  });
})();
