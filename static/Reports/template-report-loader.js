// Cache for performance
window.templateReportCache = null;

// 🧭 Main entry point
async function loadTemplateReport(name, data = window.data) {
    try {
        const container = document.getElementById("delivery-note-template");
        if (!container) throw new Error("Missing #delivery-note-template element");
        container.innerHTML = "<p>Loading report...</p>";

        const template = window.templatesData[name];
        if (!template) throw new Error(`Template "${name}" not found`);

        // Cache check
        if (
            window.templateReportCache &&
            window.templateReportCache.name === name &&
            window.templateReportCache.data === data &&
            window.templateReportCache.fragment?.hasChildNodes()
        ) {
            container.innerHTML = "";
            container.appendChild(window.templateReportCache.fragment.cloneNode(true));
            return;
        }

        // Group and render data
        const grouped = groupByTemplateLevels(data, template.levels);
        const fragment = buildReportTable(template, grouped);

        const title = document.createElement("h1")
        title.innerHTML = `Delivery Note ${name} Report`

        container.innerHTML = "";
        container.appendChild(title)
        container.appendChild(fragment);

        // Cache
        window.templateReportCache = { name, data, fragment };
    } catch (err) {
        console.error("Report load error:", err);
        container.innerHTML = `<p style="color:red;">Error loading report: ${err.message}</p>`;
    }
}

// 🧩 Group data recursively according to template levels
function groupByTemplateLevels(data, levels) {
    if (!levels || !levels.length || !data) return data || [];
    const grouped = {};
    const [currentLevel, ...rest] = levels;
    const levelField = currentLevel.field;

    for (const row of data) {
        const key = row[levelField] || "Unknown";
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(row);
    }

    // Recursively group sublevels
    const result = {};
    for (const [key, rows] of Object.entries(grouped)) {
        result[key] = rest.length ? groupByTemplateLevels(rows, rest) : rows;
    }
    return result;
}

// 🧱 Build report table and rows based on template
function buildReportTable(template, groupedData) {
    const fragment = document.createDocumentFragment();
    const table = document.createElement("table");
    table.classList.add("report-table");
    table.id = "templateTable";
    table.innerHTML = `
        <thead>
            <tr>
                <th>Labels</th>
                ${template.fields.map(f => `<th>${f.label}</th>`).join("")}
            </tr>
        </thead>
        <tbody></tbody>
    `;
    const tbody = table.querySelector("tbody");
    const rowIdCounter = { value: 0 };
    buildRowsRecursive(
        tbody,
        groupedData,
        template.levels,
        template.fields,
        rowIdCounter
    );
    fragment.appendChild(table);
    return fragment;
}

// 🪜 Recursively build table rows
function buildRowsRecursive(tbody, groupedData, levels, fields, rowIdCounter, parentRow = null, depth = 0) {
    if (!groupedData) return;
    const isLastLevel = levels.length === 1;

    for (const [key, subData] of Object.entries(groupedData)) {
        const tr = document.createElement("tr");
        tr.dataset.rowId = `row-${rowIdCounter.value++}`;
        if (parentRow) {
            tr.classList.add("hidden");
            tr.dataset.parentId = parentRow.dataset.rowId;
        }

        // Compute totals or field values
        const totals = computeFieldTotals(isLastLevel ? subData : flattenGroupedData(subData), fields);
        // Match quantities report indentation style
        const indent = depth === 0 ? "" : "↳ ".repeat(depth >= 3 ? 3 : depth) + (depth >= 3 ? "&nbsp;&nbsp;&nbsp;" : "");
        tr.innerHTML = `
            <td>${indent}${key}</td>
            ${fields.map(f => `<td>${formatValue(totals[f.field])}</td>`).join("")}
        `;

        // Toggle click handler
        if (!isLastLevel) {
            tr.classList.add("hover");
            tr.addEventListener("click", () => toggleChildren(tr.dataset.rowId));
        }
        tbody.appendChild(tr);

        if (!isLastLevel) {
            buildRowsRecursive(tbody, subData, levels.slice(1), fields, rowIdCounter, tr, depth + 1);
        }
    }
}

function isExpression(fieldName) {
    return /[+\-*/()]/.test(fieldName);
}

// 🔢 Compute totals for fields, handling computed expressions
function computeFieldTotals(rows, fields) {
    const totals = {};

    for (const field of fields) {
        const fieldName = field.field;
        const type = field.totalType || "sum";
        const weightField = field.weightField;

        if (type === "none") {
            totals[fieldName] = rows.length
                ? (isExpression(fieldName) ? evalExpression(fieldName, rows[0]) : parseFloat(rows[0][fieldName]) || 0)
                : 0;

        } else if (type === "sum") {
            let sum = 0;
            for (const row of rows) {
                sum += isExpression(fieldName) ? evalExpression(fieldName, row) : parseFloat(row[fieldName]) || 0;
            }
            totals[fieldName] = sum;

        } else if (type === "avg") {
            if (!weightField) {
                // Simple average if no weight is defined
                let sum = 0;
                for (const row of rows) {
                    sum += isExpression(fieldName) ? evalExpression(fieldName, row) : parseFloat(row[fieldName]) || 0;
                }
                totals[fieldName] = rows.length ? sum / rows.length : 0;
            } else {
                // Weighted average
                let weightedSum = 0;
                let totalWeight = 0;
                for (const row of rows) {
                    const value = isExpression(fieldName) ? evalExpression(fieldName, row) : parseFloat(row[fieldName]) || 0;
                    const weight = parseFloat(row[weightField]) || 0;
                    weightedSum += value * weight;
                    totalWeight += weight;
                }
                totals[fieldName] = totalWeight ? weightedSum / totalWeight : 0;
            }
        }
    }

    return totals;
}




function evalExpression(expression, row) {
    let expr = expression;
    for (const key of Object.keys(row)) {
        // Replace all occurrences of the field name with its value
        const regex = new RegExp(`\\b${key}\\b`, "g");
        expr = expr.replace(regex, row[key] || 0);
    }

    // Allow only numbers and operators
    if (!/^[0-9+\-*/().\s]+$/.test(expr)) {
        console.warn("Unsafe expression detected:", expression);
        return 0;
    }

    try {
        return Function(`"use strict"; return (${expr})`)();
    } catch {
        return 0;
    }
}


// 📦 Flatten nested grouped data into a single array
function flattenGroupedData(grouped) {
    let arr = [];
    for (const val of Object.values(grouped)) {
        if (Array.isArray(val)) arr = arr.concat(val);
        else arr = arr.concat(flattenGroupedData(val));
    }
    return arr;
}

// 🪄 Utility: format numbers cleanly
function formatValue(v) {
    return typeof v === "number" && !isNaN(v) ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "-";
}

// 👁️ Toggle visibility of child rows
function toggleChildren(rowId) {
    document.querySelectorAll(`[data-parent-id="${rowId}"]`).forEach(child => {
        child.classList.toggle("hidden");
    });
}