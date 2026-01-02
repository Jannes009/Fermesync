document.addEventListener("DOMContentLoaded", () => {
    loadPOLines(currentPoNumber);
});
// ---------------- PO LINES ----------------
async function loadPOLines(poNumber) {
    const res = await fetch(`/inventory/SDK/fetch_po_lines/${poNumber}`);
    const data = await res.json();

    const container = document.getElementById("po-lines");
    container.innerHTML = "";
    console.log(data.po_lines)
    data.po_lines.forEach(line => {
        const row = document.createElement("div");
        row.className = "po-line";

        row.dataset.lineId = line.LineId
        row.dataset.stockId = line.StockId;
        row.dataset.StockDesc = line.StockDesc;
        row.dataset.originalQty = line.QtyOutstanding;
        row.dataset.originalPrice = line.Price;
        row.dataset.UOM = line.UOM;

        row.innerHTML = `
            <strong>${line.StockDesc}</strong>

            <div>
                Qty:
                <input class="qty-input" type="number" min="0" step="0.01" placeholder="Qty">
                <span>${line.UOM}</span>
            </div>

            <div>
                Price:
                <input class="price-input" type="number" min="0" step="0.01" placeholder="Price">
            </div>

            <small class="warning" style="display:none;color:#ff6b6b"></small>
        `;

        container.appendChild(row);
    });

    document.getElementById("next-to-summary").onclick = validateAndContinue;
}

// ---------------- VALIDATION ----------------
function validateAndContinue() {
    currentReceiverName = document.getElementById("receiver").value.trim();
    supplierRef = document.getElementById("SupplierRef").value.trim();

    if (!currentReceiverName || !supplierRef) {
        Swal.fire("Missing info", "Receiver and Supplier Ref required", "error");
        return;
    }

    let mismatches = [];
    let lines = [];
    let hasErrors = false;

    document.querySelectorAll(".po-line").forEach(line => {
        const qtyInput = line.querySelector(".qty-input");
        const priceInput = line.querySelector(".price-input");
        const warning = line.querySelector(".warning");

        const qty = parseFloat(qtyInput.value);
        const price = parseFloat(priceInput.value);

        warning.style.display = "none";

        if (qtyInput.value === "" || Number.isNaN(qty)) {
            warning.textContent = "Qty required";
            warning.style.display = "block";
            hasErrors = true;
            return;
        }

        if (priceInput.value === "" || Number.isNaN(price)) {
            warning.textContent = "Price required";
            warning.style.display = "block";
            hasErrors = true;
            return;
        }

        lines.push({
            lineId: line.dataset.lineId,
            stockId: line.dataset.stockId,
            qty,
            price,
            UOM: line.dataset.UOM
        });
        console.log(line.dataset)
        if (
            qty !== parseFloat(line.dataset.originalQty) ||
            price !== parseFloat(line.dataset.originalPrice)
        ) {
            mismatches.push({
                LineId: line.dataset.lineId,
                ProductId: line.dataset.stockId,
                StockDesc: line.dataset.StockDesc,
                OriginalQty: line.dataset.originalQty,
                QtyReceived: qty,
                OriginalPrice: line.dataset.originalPrice,
                PriceReceived: price,
                UOM: line.dataset.UOM
            });
        }
    });

    if (hasErrors) return;
    console.log(lines, mismatches)
    if (mismatches.length) {
        Swal.fire({
            icon: 'warning',
            title: 'PO Differences Detected',
            html: `
                <div style="text-align:left">
                On these product lines4
                    ${mismatches.map(m =>
                        `• ${m.StockDesc} - ${m.UOM}`
                    ).join("<br>")}
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: "Send to Supervisor",
            cancelButtonText: "Cancel",
            reverseButtons: true,
            allowOutsideClick: false
        }).then(result => {
            if (result.isConfirmed) {
                sendToSupervisor(mismatches)
            }
            // cancel → do nothing, user stays on screen
        });

    } else {
        submitGRV(lines);
    }

}

// ---------------- SUBMIT ----------------
function submitGRV(lines) {
    fetch("/inventory/submit_grv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            poNumber: currentPoNumber,
            receiverName: currentReceiverName,
            supplierRef,
            lines
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            Swal.fire("Success", "GRV submitted", "success");
        } else {
            Swal.fire("Error", res.message || res.error || "Failed", "error");
        }
    });
}

function sendToSupervisor(mismatches) {
    fetch("/inventory/incorrect_po", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            poNumber: currentPoNumber,
            receiverName: currentReceiverName,
            supplierRef,
            mismatches
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            Swal.fire("Success", "Request send to supplier", "success");
        } else {
            Swal.fire("Error", res.message || "Failed", "error");
        }
    });
}
