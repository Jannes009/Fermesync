
// Load Suppliers
document.addEventListener("DOMContentLoaded", populateSupplierDropdown);

function populateSupplierDropdown() {
        fetch("/inventory/SDK/fetch_suppliers")
        .then(res => res.json())
        .then(data => {
            const sup = document.getElementById("supplier");
            sup.innerHTML = `<option value="">Select Supplier</option>`;
            data.suppliers.forEach(s => {
                sup.innerHTML += `<option value="${s.code}">${s.name}</option>`;
            });
        });
}

// Load PO table when supplier changes
document.getElementById("supplier").addEventListener("change", function () {
    const supplierCode = this.value;
    const wrapper = document.getElementById("poTableWrapper");
    const tbody = document.getElementById("poTableBody");

    if (!supplierCode) {
        wrapper.classList.add("hidden");
        return;
    }

    fetch("/inventory/get_po_numbers", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ supplier_code: supplierCode })
    })
    .then(res => res.json())
    .then(data => {
        wrapper.classList.remove("hidden");
        tbody.innerHTML = "";

        if (!data.po_list || data.po_list.length === 0) {
            tbody.innerHTML = `<tr><td class="no-data" colspan="4">No PO’s found</td></tr>`;
            return;
        }

        data.po_list.forEach(p => {
            const tr = document.createElement("tr");
            tr.classList.add("po-row");
            tr.dataset.poNumber = p.order_num;
            tr.innerHTML = `
                <td>${p.order_num}</td>
                <td>${p.order_date}</td>
                <td>${p.order_desc}</td>
                <td>${p.order_total}</td>
            `;
            tr.addEventListener("click", () => loadPOLines(p.order_num));
            tbody.appendChild(tr);
        });
    });
});
let currentPoNumber = null;  // global at the top of your script
// Load PO lines
async function loadPOLines(poNumber) {
    currentPoNumber = poNumber;
    const res = await fetch(`/inventory/SDK/fetch_po_lines/${poNumber}`);
    const data = await res.json();
    const container = document.getElementById("po-lines");
    container.innerHTML = "";

    // Group lines by warehouse
    const warehouseGroups = {};
    data.po_lines.forEach((line) => {
        if (!warehouseGroups[line.WHName]) warehouseGroups[line.WHName] = [];
        warehouseGroups[line.WHName].push(line);
    });

    // Render grouped by warehouse
    Object.keys(warehouseGroups).forEach((warehouse) => {

        const warehouseBox = document.createElement("div");
        warehouseBox.className = "warehouse-box";
        warehouseBox.style = `
            border:1px solid var(--input-border);
            border-radius:8px;
            padding:12px;
            margin-bottom:20px;
            background:var(--form-bg);
        `;

        warehouseBox.innerHTML = `
            <h4 style="margin:0 0 10px 0; padding-bottom:6px;
                       border-bottom:2px solid var(--button-bg);
                       color:var(--primary-text); font-size:1.05rem;">
                ${warehouse}
            </h4>
        `;

        const productsWrapper = document.createElement("div");
        productsWrapper.style = `
            display:flex;
            flex-direction:column;
            gap:10px;
        `;

        warehouseGroups[warehouse].forEach((line) => {
            const price = line.Price ?? 0;
            const qtyOutstanding = parseFloat(line.QtyOutstanding) || 0;

            const row = document.createElement("div");
            row.className = "po-line";
            row.dataset.stockId = line.iStockCodeID;
            row.dataset.price = price;
            row.dataset.outstanding = qtyOutstanding;
            row.dataset.UOM = line.UOM;
            row.dataset.warehouse = warehouse;

            row.style = `
                padding:8px;
                border-radius:6px;
                background:white;
                display:grid;
                grid-template-columns: 1.2fr 0.6fr 0.6fr 0.6fr 0.8fr;
                align-items:center;
                gap:8px;
                font-size:0.85rem;
                border:1px solid #e2e2e2;
            `;

            row.innerHTML = `
                <div><strong>${line.StockDesc}</strong></div>
                <div>Out: <strong>${qtyOutstanding}</strong></div>
                <div>UOM: <strong>${line.UOM}</strong></div>
                <div>Unit Price: <strong>R${price.toFixed(2)}</strong></div>
                <div>
                    <input type="number" class="qty-input"
                        placeholder="0"
                        min="0" step="0.01"
                        data-outstanding="${qtyOutstanding}"
                        style="width:100%; padding:4px; border:1px solid var(--input-border); border-radius:4px; font-size:0.8rem;">
                    <small class="qty-warning" style="display:none; color:#ff6b6b; font-size:0.7rem;"></small>
                </div>
            `;

            productsWrapper.appendChild(row);
        });

        warehouseBox.appendChild(productsWrapper);
        container.appendChild(warehouseBox);
    });

    // Show PO lines section
    document.querySelector('section[data-step="1"]').classList.add("hidden");
    const poLinesSection = document.getElementById("po-lines-section");
    const poLinesHeader = poLinesSection.querySelector("h3") || document.createElement("h3");

    if (!poLinesSection.querySelector("h3")) {
        poLinesHeader.innerHTML = `Outstanding Lines - PO: <strong>${poNumber}</strong>`;
        poLinesSection.insertBefore(poLinesHeader, poLinesSection.firstChild);
    } else {
        poLinesHeader.innerHTML = `Outstanding Lines - PO: <strong>${poNumber}</strong>`;
    }

    poLinesSection.style.display = "block";

    // NEXT STEP – Summary
    document.getElementById("next-to-summary").onclick = () => {

        // Validate qtys
        let hasErrors = false;
        let errorMessage = "";

        document.querySelectorAll(".qty-input").forEach(input => {
            const outstanding = parseFloat(input.dataset.outstanding);
            const val = parseFloat(input.value) || 0;

            if (val > outstanding) {
                hasErrors = true;
                const productName = input.closest(".po-line").querySelector("strong").innerText;
                errorMessage += `\n• ${productName}: Qty ${val} exceeds outstanding ${outstanding}`;
            }
        });

        if (hasErrors) {
            Swal.fire({
                icon: 'error',
                title: 'Validation Error',
                html: 'Some items exceed outstanding:<br><br>' + errorMessage.replace(/\n/g, "<br>"),
                confirmButtonColor: 'var(--button-bg)'
            });
            return;
        }

        // ----------------- SUMMARY BUILD ------------------
        const lines = document.querySelectorAll("#po-lines .po-line");
        const summaryContainer = document.getElementById("po-summary");
        summaryContainer.innerHTML = "";

        const summaryData = [];
        let totalQty = 0;
        let totalAmount = 0;

        lines.forEach(line => {
            const qty = parseFloat(line.querySelector(".qty-input").value) || 0;
            if (qty <= 0) return;

            const price = parseFloat(line.dataset.price);
            const lineTotal = qty * price;

            summaryData.push({
                stockId: line.dataset.stockId,
                stock: line.querySelector("strong").innerText,
                warehouse: line.dataset.warehouse,
                outstanding: line.dataset.outstanding,
                price,
                UOM: line.dataset.UOM,
                qtyReceived: qty
            });

            totalQty += qty;
            totalAmount += lineTotal;
        });

        // Group summary
        const summaryGroups = {};
        summaryData.forEach(item => {
            if (!summaryGroups[item.warehouse]) summaryGroups[item.warehouse] = [];
            summaryGroups[item.warehouse].push(item);
        });

        // Render summary
        Object.keys(summaryGroups).forEach((warehouse) => {
            summaryContainer.innerHTML += `
                <h4 style="margin:15px 0 10px 0; padding-bottom:6px; border-bottom:2px solid var(--button-bg); font-size:1.05rem;">
                    ${warehouse}
                </h4>
            `;

            summaryGroups[warehouse].forEach((item) => {
                const lineTotal = item.qtyReceived * item.price;
                summaryContainer.innerHTML += `
                    <div class="po-line" style="padding:10px; border:1px solid #e2e2e2; margin-bottom:10px; border-radius:6px;">
                        <strong>${item.stock}</strong>
                        <div style="display:grid; grid-template-columns: repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin-top:6px;">
                            <div>Out: ${item.outstanding}</div>
                            <div>UOM: ${item.UOM}</div>
                            <div>Price: R${item.price.toFixed(2)}</div>
                            <div>Received: ${item.qtyReceived}</div>
                            <div><strong>Total: R${lineTotal.toFixed(2)}</strong></div>
                        </div>
                    </div>
                `;
            });
        });

        // Totals
        summaryContainer.innerHTML += `
            <div style="padding:15px; border-top:2px solid var(--button-bg); margin-top:18px;">
                <div><strong>Total Qty:</strong> ${totalQty.toFixed(2)}</div>
                <div style="color:var(--button-bg); font-size:1.1rem;"><strong>Total Amount:</strong> R${totalAmount.toFixed(2)}</div>
            </div>
        `;

        // Switch screens
        document.getElementById("po-lines-section").style.display = "none";
        const poSummarySection = document.getElementById("po-summary-section");
        const poSummaryHeader = poSummarySection.querySelector("h3") || document.createElement("h3");

        if (!poSummarySection.querySelector("h3")) {
            poSummaryHeader.innerHTML = `Review GRV - PO: <strong>${poNumber}</strong>`;
            poSummarySection.insertBefore(poSummaryHeader, poSummarySection.firstChild);
        } else {
            poSummaryHeader.innerHTML = `Review GRV - PO: <strong>${poNumber}</strong>`;
        }

        poSummarySection.style.display = "block";

        // Submit GRV
        document.getElementById("submit-grv").onclick = () => {
            fetch("/inventory/submit_grv", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    poNumber: poNumber,
                    lines: summaryData.map(l => ({
                        ProductId: l.stockId,
                        QtyReceived: l.qtyReceived
                    }))
                })
            })
                .then(r => r.json())
                .then(resData => {
                    if (resData.success) {
                        Swal.fire({
                            icon: 'success',
                            title: 'Success!',
                            text: 'GRV submitted.',
                            confirmButtonColor: 'var(--button-bg)'
                        }).then(() => {
                            document.getElementById("supplier").value = "";
                            document.getElementById("poTableWrapper").classList.add("hidden");
                            document.getElementById("po-lines-section").style.display = "none";
                            document.getElementById("po-summary-section").style.display = "none";
                            document.querySelector(`section[data-step="1"]`).classList.remove("hidden");
                            document.getElementById("po-lines").innerHTML = "";
                            document.getElementById("po-summary").innerHTML = "";
                        });
                    } else {
                        Swal.fire({
                            icon: 'error',
                            title: 'Error',
                            text: resData.message || 'Unknown error',
                            confirmButtonColor: 'var(--button-bg)'
                        });
                    }
                });
        };
    };
}

