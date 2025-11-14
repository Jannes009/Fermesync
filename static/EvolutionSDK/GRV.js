
// Load Suppliers
document.addEventListener("DOMContentLoaded", () => {
    fetch("/SDK/fetch_suppliers")
        .then(res => res.json())
        .then(data => {
            const sup = document.getElementById("supplier");
            sup.innerHTML = `<option value="">Select Supplier</option>`;
            data.suppliers.forEach(s => {
                sup.innerHTML += `<option value="${s.code}">${s.name}</option>`;
            });
        });
});

// Load PO table when supplier changes
document.getElementById("supplier").addEventListener("change", function () {
    const supplierCode = this.value;
    const wrapper = document.getElementById("poTableWrapper");
    const tbody = document.getElementById("poTableBody");

    if (!supplierCode) {
        wrapper.classList.add("hidden");
        return;
    }

    fetch("/get_po_numbers", {
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
    const res = await fetch(`/SDK/fetch_po_lines/${poNumber}`);
    const data = await res.json();
    const container = document.getElementById("po-lines");
    container.innerHTML = "";

    data.po_lines.forEach((line, index) => {
        const price = line.Price ?? 0;
        container.innerHTML += `
            <div class="po-line" data-stock-id="${line.iStockCodeID}">
                <div class="line-header"><strong>${line.StockDesc}</strong></div>
                <div class="line-row"><strong>Warehouse:</strong> ${line.WHName}</div>
                <div class="line-row"><strong>Outstanding:</strong> ${line.QtyOutstanding}</div>
                <div class="line-row"><strong>Price:</strong> R${price.toFixed(2)}</div>
                <div class="input-row">
                    <label>Qty Received:</label>
                    <input type="number" min="0" step="0.01" class="qty-input" placeholder="Enter received qty">
                </div>
            </div>
        `;
    });


    // Show PO lines section
    document.querySelector('section[data-step="1"]').classList.add("hidden");
    const poLinesSection = document.getElementById("po-lines-section");
    poLinesSection.style.display = "block";

    document.getElementById("next-to-summary").onclick = () => {
    const lines = document.querySelectorAll("#po-lines .po-line");
    const summaryContainer = document.getElementById("po-summary");
    summaryContainer.innerHTML = "";

    // Build array for backend
    const grvLines = [];
    const summaryData = [];  // <-- declare array here

    lines.forEach(line => {
        const stockId = line.dataset.stockId; // NEW
        const stock = line.querySelector(".line-header strong").innerText;
        const warehouse = line.querySelector(".line-row:nth-child(2)").innerText.split(": ")[1];
        const outstanding = line.querySelector(".line-row:nth-child(3)").innerText.split(": ")[1];
        const price = parseFloat(line.querySelector(".line-row:nth-child(4)").innerText.replace("R","")) || 0;
        const qtyReceived = parseFloat(line.querySelector(".qty-input").value) || 0;

        summaryData.push({ stockId, stock, warehouse, outstanding, price, qtyReceived });

        summaryContainer.innerHTML += `
            <div class="po-line">
                <div class="line-header"><strong>${stock}</strong></div>
                <div class="line-row"><strong>Warehouse:</strong> ${warehouse}</div>
                <div class="line-row"><strong>Outstanding:</strong> ${outstanding}</div>
                <div class="line-row"><strong>Price:</strong> R${price.toFixed(2)}</div>
                <div class="line-row"><strong>Qty Received:</strong> ${qtyReceived}</div>
            </div>
        `;
    });


    // Hide PO lines, show summary
    document.getElementById("po-lines-section").style.display = "none";
    document.getElementById("po-summary-section").style.display = "block";

// Submit GRV
document.getElementById("submit-grv").onclick = () => {
    fetch("/submit_grv", {
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
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            alert("✅ GRV submitted successfully!");
        } else {
            alert("⚠️ Failed to submit GRV: " + (resData.message || JSON.stringify(resData)));
        }
    })
    .catch(err => {
        alert("❌ Error submitting GRV: " + err);
    });
};

};
}
