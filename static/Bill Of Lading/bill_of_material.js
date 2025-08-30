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
                data.forEach((row, index) => {
                    const tr = document.createElement('tr');
                    
                    // Add alternating row colors
                    tr.classList.add(index % 2 === 0 ? 'row-odd' : 'row-even');
                    
                    let bomCell = row.BOMCreated === 'Not Created'
                        ? `<span style='color:var(--logo-color);font-weight:bold;'>🚩 Not Created</span>`
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
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 2rem; color: var(--secondary-text);">
                            Failed to load data.
                        </td>
                    </tr>
                `;
            })
            .finally(() => {
                if (loadingRow) loadingRow.style.display = 'none';
            });
    }
    
    loadTable();
    
    const btn = document.getElementById('manufacture-all-btn');
    btn.addEventListener('click', function() {
        btn.disabled = true;
        btn.style.backgroundColor = 'var(--secondary-text)';
        btn.style.borderColor = 'var(--secondary-text)';
        btn.style.color = 'var(--container-bg)';
        btn.innerHTML = '<span class="spinner"></span> Manufacturing...';
        
        fetch('/api/create_bom', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        title: 'Success',
                        text: data.message,
                        icon: 'success',
                        confirmButtonColor: 'var(--button-bg)',
                        confirmButtonText: 'OK'
                    });
                    loadTable();
                } else {
                    Swal.fire({
                        title: 'Error',
                        text: data.message || 'Failed to create BOM',
                        icon: 'error',
                        confirmButtonColor: 'var(--button-bg)',
                        confirmButtonText: 'OK'
                    });
                }
            })
            .catch(err => {
                Swal.fire({
                    title: 'Error',
                    text: err.message || 'Failed to create BOM',
                    icon: 'error',
                    confirmButtonColor: 'var(--button-bg)',
                    confirmButtonText: 'OK'
                });
            })
            .finally(() => {
                btn.disabled = false;
                btn.style.backgroundColor = '';
                btn.style.borderColor = '';
                btn.style.color = '';
                btn.innerHTML = '<i class="fa fa-industry"></i> Manufacture';
            });
    });
    
    const createBtn = document.getElementById('create-masterfiles-btn');
    createBtn.addEventListener('click', function() {
        createBtn.disabled = true;
        createBtn.style.backgroundColor = 'var(--secondary-text)';
        createBtn.style.borderColor = 'var(--secondary-text)';
        createBtn.style.color = 'var(--container-bg)';
        createBtn.innerHTML = '<span class="spinner"></span> Creating...';
        
        fetch('/api/create_bom_masterfiles', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        title: 'Success',
                        text: data.message,
                        icon: 'success',
                        confirmButtonColor: 'var(--button-bg)',
                        confirmButtonText: 'OK'
                    });
                    loadTable();
                } else {
                    Swal.fire({
                        title: 'Error',
                        text: data.message || 'Failed to create masterfiles',
                        icon: 'error',
                        confirmButtonColor: 'var(--button-bg)',
                        confirmButtonText: 'OK'
                    });
                }
            })
            .catch(err => {
                Swal.fire({
                    title: 'Error',
                    text: err.message || 'Failed to create masterfiles',
                    icon: 'error',
                    confirmButtonColor: 'var(--button-bg)',
                    confirmButtonText: 'OK'
                });
            })
            .finally(() => {
                createBtn.disabled = false;
                createBtn.style.backgroundColor = '';
                createBtn.style.borderColor = '';
                createBtn.style.color = '';
                createBtn.innerHTML = '<i class="fa fa-tools"></i> Create Masterfiles';
            });
    });
}); 