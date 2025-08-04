document.addEventListener('DOMContentLoaded', function() {
    const loadingRow = document.getElementById('bom-loading-row');
    const tbody = document.querySelector('#bom-table tbody');
    function loadTable() {
        tbody.innerHTML = '';
        if (loadingRow) {
            tbody.appendChild(loadingRow);
            loadingRow.style.display = '';
        }
        fetch('/api/bill_of_materials')
            .then(response => response.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach(row => {
                    const tr = document.createElement('tr');
                    let bomCell = row.BOMCreated === 'Not Created'
                        ? `<span style='color:#e11d48;font-weight:bold;'>🚩 Not Created</span>`
                        : row.BOMCreated;
                    tr.innerHTML = `
                        <td>${row.ProductDescription}</td>
                        <td>${row.PackHouseName}</td>
                        <td>${row.QtyDeliveredNotInvoiced}</td>
                        <td>${row.QtyToManufacture}</td>
                        <td>${row.QtyOnBOM}</td>
                        <td>${row.QtyOnHand}</td>
                        <td>${bomCell}</td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Failed to load data.</td></tr>';
            })
            .finally(() => {
                if (loadingRow) loadingRow.style.display = 'none';
            });
    }
    loadTable();
    const btn = document.getElementById('manufacture-all-btn');
    btn.addEventListener('click', function() {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Manufacturing...';
        fetch('/api/create_bom', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Success', data.message, 'success');
                    loadTable();
                } else {
                    Swal.fire('Error', data.message || 'Failed to create BOM', 'error');
                }
            })
            .catch(err => {
                Swal.fire('Error', err.message || 'Failed to create BOM', 'error');
            })
            .finally(() => {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa fa-industry"></i> Manufacture';
            });
    });
    const createBtn = document.getElementById('create-masterfiles-btn');
    createBtn.addEventListener('click', function() {
        createBtn.disabled = true;
        createBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Creating...';
        fetch('/api/create_bom_masterfiles', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire('Success', data.message, 'success');
                    loadTable();
                } else {
                    Swal.fire('Error', data.message || 'Failed to create masterfiles', 'error');
                }
            })
            .catch(err => {
                Swal.fire('Error', err.message || 'Failed to create masterfiles', 'error');
            })
            .finally(() => {
                createBtn.disabled = false;
                createBtn.innerHTML = '<i class="fa fa-tools"></i>Create Masterfiles';
            });
    });
}); 