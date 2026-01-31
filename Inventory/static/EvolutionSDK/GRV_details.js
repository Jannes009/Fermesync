import {
  db
} from '/main_static/offline/db.js?v=44';
let supplierRef = "";

document.addEventListener("DOMContentLoaded", async () => {
    await loadPOLines(currentPoNumber);

    const draft = await loadGrvDraft(currentPoNumber);
    if (!draft) return;

    document.getElementById("SupplierRef").value = draft.supplierRef || "";

    document.querySelectorAll(".po-line").forEach(line => {
        const savedQty = draft.lines?.[line.dataset.lineId];
        if (savedQty !== undefined) {
            line.querySelector(".qty-input").value = savedQty;
        }
    });
});

// Helper function to format UOM display
function formatUOM(uom) {
    return uom && uom.trim() ? uom : "";
}

// Helper function to get UOM display with space
function getUOMDisplay(uom) {
    const formatted = formatUOM(uom);
    return formatted ? ` ${formatted}` : "";
}

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

        const uomDisplay = getUOMDisplay(line.UOM);

        row.dataset.lineId = line.LineId
        row.dataset.stockId = line.StockId
        row.dataset.qtyOrdered = line.QtyOutstanding
        row.dataset.StockDesc = line.StockDesc
        row.dataset.UOM = line.UOM || ""

        row.innerHTML = `
            <strong>${line.StockDesc}</strong>
            <div>
                Ordered Qty: ${line.QtyOutstanding}${uomDisplay} @ R${line.Price}
            </div>
            <div>
                Confirm Qty:
                <input class="qty-input" type="number" min="0" step="0.01" placeholder="Qty">
                <span>${uomDisplay}</span>
            </div>

            <small class="warning" style="display:none;color:#ff6b6b"></small>
        `;
        container.addEventListener("input", () => {
            saveGrvDraft(currentPoNumber);
        });
        container.appendChild(row);
    });

    document.getElementById("next-to-summary").onclick = validateAndContinue;
}

// ---------------- VALIDATION ----------------
function validateAndContinue() {
    supplierRef = document.getElementById("SupplierRef").value.trim();

    if (!supplierRef) {
        Swal.fire("Missing info", "Supplier Ref required", "error");
        return;
    }

    let overQtys = [];
    let underQtys = [];
    let lines = [];
    let hasErrors = false;

    document.querySelectorAll(".po-line").forEach(line => {
        const qtyInput = line.querySelector(".qty-input");
        const warning = line.querySelector(".warning");

        const qty = parseFloat(qtyInput.value);

        warning.style.display = "none";

        if (qtyInput.value === "" || Number.isNaN(qty)) {
            warning.textContent = "Qty required";
            warning.style.display = "block";
            hasErrors = true;
            return;
        }

        lines.push({
            lineId: line.dataset.lineId,
            qty: qty
        });
        console.log(qty, line.dataset.qtyOrdered);
        if (qty > parseFloat(line.dataset.qtyOrdered)) {
            overQtys.push({
                LineId: line.dataset.lineId,
                StockId: line.dataset.stockId,
                StockDesc: line.dataset.StockDesc,
                QtyOrdered: line.dataset.qtyOrdered,
                QtyDelivered: qty,
                UOM: formatUOM(line.dataset.UOM)
            });
        }
        if (qty < parseFloat(line.dataset.qtyOrdered)) {
            underQtys.push({
                StockDesc: line.dataset.StockDesc,
                UOM: formatUOM(line.dataset.UOM)
            });
        }
    });
    if (hasErrors) return;

    // check under-qty
    if (underQtys.length) {
        Swal.fire({
            icon: 'warning',
            title: 'Qty confirmed less than ordered',
            html: `
                <div style="text-align:left">
                On these product lines
                    ${underQtys.map(m => {
                        const uomText = m.UOM ? ` - ${m.UOM}` : "";
                        return `• ${m.StockDesc}${uomText}`;
                    }).join("<br>")}
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: "Continue",
            cancelButtonText: "Cancel",
            reverseButtons: true,
            allowOutsideClick: false
        }).then(result => {
            if (result.isConfirmed) {
                submitGRV(lines);
            }
        });
        return;
    }

    // Over-qty always checked
    if (overQtys.length) {
        Swal.fire({
            icon: 'warning',
            title: 'Qty exceeds ordered qty',
            html: `
                <div style="text-align:left">
                On these product lines
                    ${overQtys.map(m => {
                        const uomText = m.UOM ? ` - ${m.UOM}` : "";
                        return `• ${m.StockDesc}${uomText}`;
                    }).join("<br>")}
                </div>
            `,
            showCancelButton: true,
            confirmButtonText: "Send to Supervisor",
            cancelButtonText: "Cancel",
            reverseButtons: true,
            allowOutsideClick: false
        }).then(result => {
            if (result.isConfirmed) {
                sendToSupervisor(overQtys);
            }
        });
        return; // ⬅ stop here
    }

    // 3️⃣ Clean submit
    submitGRV(lines);

        

}

// ---------------- SUBMIT ----------------
function submitGRV(lines) {
    fetch("/inventory/submit_grv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            poNumber: currentPoNumber,
            supplierRef,
            lines
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            clearGrvDraft(currentPoNumber);
            Swal.fire({
                icon: "success",
                title: "GRV submitted succesfully",
                text: "The GRV was created in Evolution"
            }).then(() => {
                window.location.href = "/inventory/grv";
            });
        } else {
            Swal.fire("Error", res.message || res.error || "Failed", "error");
        }
    });
}

async function sendToSupervisor(overQtys) {
    await saveGrvDraft(currentPoNumber);

    fetch("/inventory/incorrect_po", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            poNumber: currentPoNumber,
            supplierRef,
            overQtys
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.success) {
            Swal.fire({
                icon: "info",
                title: "Sent to supervisor",
                text: "Please wait for supplier confirmation",
                allowOutsideClick: false
            }).then(() => {
                window.location.href = "/inventory/grv";
            });
        } else {
            Swal.fire("Error", res.message || res.error || "Failed", "error");
        }
    });
}


// ---------------- Draft saving ----------------
async function saveGrvDraft(poNumber) {
    const lines = {};

    document.querySelectorAll(".po-line").forEach(line => {
        const input = line.querySelector(".qty-input");
        if (input.value !== "") {
            lines[line.dataset.lineId] = input.value;
        }
    });

    await db.grvDrafts.put({
        poNumber,
        supplierRef: document.getElementById("SupplierRef").value,
        lines,
        updatedAt: Date.now()
    });
}

async function loadGrvDraft(poNumber) {
    return await db.grvDrafts.get(poNumber);
}

async function clearGrvDraft(poNumber) {
    await db.grvDrafts.delete(poNumber);
}
