
let draggedElement = null;

function dragStart(event) {
    draggedElement = event.target;
}

function allowDrop(event) {
    event.preventDefault();
    const targetRow = event.target.closest("tr");  // Find the closest <tr> (row) element
    if (targetRow) {
        // Add the drop-target class to every cell in the row
        const cells = targetRow.querySelectorAll("td");  // Get all the cells in the row
        cells.forEach(cell => {
            cell.classList.add("drop-target");
        });
    }
}

function dragLeave(event) {
    const targetRow = event.target.closest("tr");  // Find the closest <tr> (row) element
    if (targetRow) {
        // Remove the drop-target class from every cell in the row
        const cells = targetRow.querySelectorAll("td");  // Get all the cells in the row
        cells.forEach(cell => {
            cell.classList.remove("drop-target");
        });
    }
}

function drop(event) {
    event.preventDefault();
    const targetRow = event.target.closest("tr");
    const data_id = targetRow.querySelector('td[data-id]').getAttribute('data-id');
    if (targetRow) {
        document.getElementById('confirmation-modal').style.display = "block";
        document.getElementById('overlay').style.display = "block";
        document.getElementById('confirm-btn').setAttribute("line-id", data_id)
        resetHighlights();
    }
}

function dragEnd() {
    resetHighlights();
}

function resetHighlights() {
    document.querySelectorAll(".drop-target").forEach(row => row.classList.remove("drop-target"));
}

function confirmMatch() {
    // Get the selected row element or the relevant <td> element that contains the data-id
    let lineId = document.querySelector('#confirm-btn').getAttribute('line-id');
    
    // Close the modal and overlay
    document.getElementById('confirmation-modal').style.display = "none";
    document.getElementById('overlay').style.display = "none";

    // Send the request to the backend to run the create_match function
    fetch('/create_match', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            // Pass any data needed by create_match here
            consignment_id: document.getElementById("ConsignmentID").innerText,
            line_id: lineId // Pass the dynamic data-id value here
        })
    }).then(response => {
        if (response.ok) {
            // You might want to redirect here after successful creation
            window.location.href = '/import_page';
        } else {
            console.error("Error creating match.");
        }
    }).catch(error => {
        console.error("There was an error with the request:", error);
    });
}



function cancelMatch() {
    document.getElementById('confirmation-modal').style.display = "none";
    document.getElementById('overlay').style.display = "none";
}

function highlightMatches() {
// Extract market data values
const marketData = {
    product: document.querySelector("#market-data div:nth-child(3) p").innerText.trim(),
    mass: document.querySelector("#market-data div:nth-child(4) p").innerText.trim(),
    class: document.querySelector("#market-data div:nth-child(5) p").innerText.trim(),
    size: document.querySelector("#market-data div:nth-child(6) p").innerText.trim(),
    variety: extractInitials(document.querySelector("#market-data div:nth-child(7) p").innerText.trim()),
    quantity: parseFloat(document.querySelector("#market-data div:nth-child(8) p").innerText.trim()),
};

// Get all rows in the table body
const rows = document.querySelectorAll("tbody tr");

rows.forEach((row) => {
    const cells = row.querySelectorAll("td");

    // Extract and normalize cell values
    const lineData = {
        product: cells[1].innerText.trim().toLowerCase(),
        mass: normalizeLineMass(cells[2].innerText),
        class: cells[3].innerText.toLowerCase(),
        size: cells[4].innerText,
        variety: cells[5].innerText.toLowerCase(),
        quantity: parseFloat(cells[7].innerText),
    };

    // Compare values
    const comparisons = {
        product: lineData.product === marketData.product.toLowerCase(),
        mass: lineData.mass === marketData.mass,
        class: lineData.class === marketData.class.toLowerCase(),
        size: lineData.size === extractInitials(marketData.size),
        variety: lineData.variety === marketData.variety.toLowerCase(),
        quantity: lineData.quantity === marketData.quantity,
    };

    // Highlight cells with a match
    Object.keys(comparisons).forEach((key, index) => {
        if (comparisons[key]) {
            let targetCell = cells[0];
            // don't format brand, format quantity
            if (index == 5){
                targetCell = cells[index + 2]
            }else{
                targetCell = cells[index + 1]
            } 
            targetCell.classList.add("matching");
        }
    });
});
}

// Function to extract the first letter of each word in the mass value
function extractInitials(size) {        
return size
    .split(" ") // Split by spaces
    .map(word => word[0]) // Take the first letter of each word
    .join(""); // Combine the initials
}

// Function to normalize the Line Data Mass by removing 'kg' and trimming
function normalizeLineMass(mass) {
return mass
    .replace(/kg/i, "") // Remove 'kg' (case-insensitive)
    .trim()
    .toLowerCase(); // Convert to lowercase for case-insensitive comparison
}

// Call the function on page load
document.addEventListener("DOMContentLoaded", highlightMatches);
