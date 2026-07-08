// Load POs on page load
document.addEventListener("DOMContentLoaded", () => loadPOTable());

let currentReceiverName = '';
let supplierRef = '';
let currentPoNumber = null;

// (supplier dropdown removed) POs load directly via loadPOTable()

function loadPOTable(supplierCode) {
    const wrapper = document.getElementById("poTableWrapper");
    const tbody = document.getElementById("poTableBody");

    wrapper.classList.remove("hidden");
    tbody.innerHTML = "<tr><td colspan='5'>Loading...</td></tr>";

    const body = supplierCode ? { supplier_code: supplierCode } : {};
    fetch("/inventory/get_po_numbers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    })
        .then(r => r.json())
        .then(data => {
            tbody.innerHTML = "";
            if (!data.po_list?.length) {
                tbody.innerHTML = `<tr><td colspan="5">No PO’s found</td></tr>`;
                return;
            }

            data.po_list.forEach(p => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${p.order_num}</td>
                    <td>${formatDate(p.order_date)}</td>
                    <td>${p.supplier_name || p.supplier_code || ''}</td>
                    <td>${p.order_desc}</td>
                    <td>${p.order_total}</td>
                `;
                tr.addEventListener("click", () => {
                    window.location.href = `/inventory/grv/${p.order_num}`;
                });
                tbody.appendChild(tr);
            });

            // attach search handler to filter table rows across all columns
            const search = document.getElementById('poSearch');
            if (search) {
                search.addEventListener('input', function () {
                    const q = this.value.trim().toLowerCase();
                    const rows = tbody.querySelectorAll('tr');
                    rows.forEach(r => {
                        const text = Array.from(r.cells).map(c => c.textContent.trim().toLowerCase()).join(' ');
                        r.style.display = q === '' || text.includes(q) ? '' : 'none';
                    });
                });
            }
        });
}

function formatDate(d) {
    const date = new Date(d);
    if (isNaN(date)) return "Invalid Date";
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
