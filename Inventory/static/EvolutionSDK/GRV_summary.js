// Load Suppliers
document.addEventListener("DOMContentLoaded", populateSupplierDropdown);

let currentReceiverName = '';
let supplierRef = '';
let currentPoNumber = null;

// ---------------- SUPPLIERS ----------------
function populateSupplierDropdown() {
    const $supplier = $('#supplier');

    $supplier.select2({
        placeholder: "Loading suppliers...",
        allowClear: false,
        width: '100%'
    });

    fetch("/inventory/SDK/fetch_outstanding_po_suppliers")
        .then(res => res.json())
        .then(data => {
            const sup = document.getElementById("supplier");
            sup.innerHTML = `<option value="" disabled selected>Select Supplier</option>`;
            data.suppliers.forEach(s => {
                sup.innerHTML += `<option value="${s.code}">${s.name}</option>`;
            });

            if ($(sup).data('select2')) $(sup).select2('destroy');

            $(sup).select2({ width: '100%' })
                .on('select2:select', e => loadPOTable(e.params.data.id));
        });
}

function loadPOTable(supplierCode) {
    const wrapper = document.getElementById("poTableWrapper");
    const tbody = document.getElementById("poTableBody");

    wrapper.classList.remove("hidden");
    tbody.innerHTML = "<tr><td colspan='4'>Loading...</td></tr>";

    fetch("/inventory/get_po_numbers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_code: supplierCode })
    })
        .then(r => r.json())
        .then(data => {
            tbody.innerHTML = "";
            if (!data.po_list?.length) {
                tbody.innerHTML = `<tr><td colspan="4">No PO’s found</td></tr>`;
                return;
            }

            data.po_list.forEach(p => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${p.order_num}</td>
                    <td>${formatDate(p.order_date)}</td>
                    <td>${p.order_desc}</td>
                    <td>${p.order_total}</td>
                `;
                tr.addEventListener("click", () => {
                    window.location.href = `/inventory/grv/${p.order_num}`;
                });
                tbody.appendChild(tr);
            });
        });
}

function formatDate(d) {
    const date = new Date(d);
    if (isNaN(date)) return "Invalid Date";
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
