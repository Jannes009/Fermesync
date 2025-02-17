document.addEventListener('DOMContentLoaded', () => {
    const modalOverlay = document.querySelector('.modal-overlay');
    const closeModalButton = document.querySelector('.close-btn');
    let currentLineId = null;

    // Open modal logic
    document.querySelectorAll('.sales-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            currentLineId = event.target.getAttribute('data-id');
            if (!currentLineId) {
                console.error('No Line ID found!');
                return;
            }
            modalOverlay.style.display = 'block';
            fetchSalesEntries(currentLineId);
        });
    });

    // Close modal
    closeModalButton.addEventListener('click', () => {
        modalOverlay.style.display = 'none';
    });

    // Add new line
    document.querySelector('.add-line-btn').addEventListener('click', () => {
        const modalTableBody = document.querySelector('.new-entry-row');
        if (!modalTableBody) {
            console.error('Table body with class "new-entry-row" not found!');
            return;
        }

        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td></td>
            <td><input type="date" placeholder="Enter date" required></td>
            <td><input type="text" placeholder="Quantity" required></td>
            <td><input type="number" placeholder="Price"></td>
            <td><input type="number" placeholder="Amount"></td>
            <td>
                <button class="remove-line-btn" onclick="removeRow(this)">
                    <img src="/static/recycle-bin.png" alt="Delete" class="bin-icon">
                </button>
            </td>
        `;
        modalTableBody.appendChild(newRow);
    });

    // Submit sales data
    document.querySelector('.modal-footer button[type="submit"]').addEventListener('click', () => {
        const salesData = [];
        let isValid = true; // Flag to track if submission should continue

        // Collect data from existing entries
        const existingRows = document.querySelectorAll('.sales-entries-list tr');
        console.log(existingRows);
        existingRows.forEach(row => {
            const lineId = currentLineId;
            const salesId = row.querySelector('.id')?.textContent;
            const date = row.querySelector('input[type="date"]').value;
            const quantity = row.querySelector('input[type="text"]').value;
            const price = row.querySelector('input[placeholder="price"]').value || 0;
            const amount = row.querySelector('input[placeholder="amount"]').value || 0;
            price = amount / quantity;


            if (!date || !quantity) {
                alert('Date and quantity values are required!');
                isValid = false; // Set the flag to false, preventing form submission
                return; // Stop the loop and function execution
            } else if (price == 0 && !amount == 0) {
                alert('Either Price or Amount are required');
                isValid = false;
                return;
            }

            salesData.push({
                lineId,
                salesId,
                date,
                quantity,
                price,
                amount,
            });
        });

        // Collect data from new entries
        const newRows = document.querySelectorAll('.new-entry-row tr');
        console.log(newRows);
        newRows.forEach(row => {
            const date = row.querySelector('input[type="date"]').value;
            const quantity = row.querySelector('input[type="Text"]').value;

            let succes = true;
            console.log(row.querySelector('input[placeholder="Price"]'));
            const price = row.querySelector('input[placeholder="Price"]').value || 0;
            const amount = row.querySelector('input[placeholder="Amount"]').value || 0;

            if (price == 0 && amount == 0) {
                alert("Price or amount is required");
                isValid = false;
                return; // Stop further execution if data is invalid
            }

            salesData.push({
                lineId: currentLineId,
                salesId: null,
                date,
                quantity,
                price,
                amount,
            });
        });

        if (!isValid) {
            return; // If any validation failed, prevent submission
        }

        if (salesData.length === 0) {
            alert('No sales data to submit!');
            return;
        }

        console.log(salesData);
        // Send data to the backend
        fetch('/submit_sales_entries', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                salesEntries: salesData,
            }),
        })
        .then((response) => response.json())
        .then((data) => {
            if (data.success) {
                alert('Data submitted successfully!');
                document.querySelector('.modal-overlay').style.display = 'none';
            } else {
                alert('Failed to submit data!');
            }
        })
        .catch((error) => console.error('Error:', error));
    });
});

