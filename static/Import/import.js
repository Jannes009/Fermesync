
document.getElementById("manualImportForm").addEventListener("submit", function (event) {
    event.preventDefault();
    let formData = new FormData(this);

    Swal.fire({
        title: "Importing...",
        html: "<b>Processing file...</b>",
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => { Swal.showLoading(); }
    });

    fetch("/import/upload_excel", {  // Adjusted the route
        method: "POST",
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        Swal.close();

        let result = data.results[0];

        if (result.status === "Success") {
            Swal.fire({
                icon: "success",
                title: "Import Completed!",
                text: result.message
            }).then(() => fetchImportedData());
        } else {
            Swal.fire({
                icon: "error",
                title: "Import Failed",
                text: result.message
            });
        }
    })
    .catch(error => {
        Swal.fire("Error!", "An error occurred while importing.", "error");
        console.error("Import error:", error);
    });
});

document.getElementById("autoImportForm").addEventListener("submit", function (event) {
    event.preventDefault();
    const startDate = document.getElementById("start_date").value;
    const endDate = document.getElementById("end_date").value;

    let isCancelled = false; // Flag to track cancellation

    Swal.fire({
        title: "Auto Import in Progress",
        html: `<div id="swal-status">Connecting...</div>`,
        allowOutsideClick: false,
        showConfirmButton: false,
        showCancelButton: true,  // Built-in cancel button
        cancelButtonText: "Cancel",
        didOpen: () => {
            Swal.showLoading();
        }
    }).then((result) => {
        if (result.dismiss === Swal.DismissReason.cancel) {
            isCancelled = true;
            if (window.eventSource) {
                window.eventSource.close();
            }
            Swal.fire({
                icon: "warning",
                title: "Import Cancelled",
                text: "The import process has been stopped."
            });
        }
    });

    if (window.eventSource) {
        window.eventSource.close();
    }

    window.eventSource = new EventSource(`/import/auto_import?start_date=${startDate}&end_date=${endDate}`);

    window.eventSource.onmessage = function (event) {
        if (isCancelled) return; // Stop processing if cancelled

        const message = event.data.replace("data: ", "");
        document.getElementById("swal-status").innerHTML = message;

        if (message.includes("SUCCESS")) {
            Swal.fire({
                icon: "success",
                title: "Import Completed!",
                text: "Import finished successfully."
            }).then(() => {
                window.eventSource.close();
                fetchImportedData();
            });
        }

        if (message.includes("ERROR")) {
            Swal.fire({ icon: "error", title: "Error", text: message });
            window.eventSource.close();
        }
    };

    window.eventSource.onerror = function () {
        if (!isCancelled) {
            Swal.fire({ icon: "error", title: "Connection Lost", text: "Failed to connect to the server." });
        }
        window.eventSource.close();
    };
});


document.addEventListener("DOMContentLoaded", () => {
    fetchImportedData();

    document.querySelectorAll(".filter-buttons button").forEach(button => {
        button.addEventListener("click", function () {
            document.querySelectorAll(".filter-buttons button").forEach(btn => btn.classList.remove("active"));
            this.classList.add("active");
            filterTable(this.id.replace("Btn", "").toLowerCase()); // Call filterTable with the correct type
        });
    });
});

let importedData = []; // Store fetched data for filtering

function fetchImportedData() {
    let table = document.getElementById("resultsTable");
    let tbody = table.querySelector("tbody");

    tbody.innerHTML = `<tr><td colspan="10">Loading...</td></tr>`;

    fetch("/import/get_imported_results")
        .then(response => response.json())
        .then(data => {
            importedData = data; // Store the data for filtering
            displayTable(data);  // Show all data initially
            filterTable("matched");
            document.getElementById("matchedBtn").classList.add("active"); // Highlight the default button
        })
        .catch(error => {
            console.error("Error fetching imported data:", error);
            tbody.innerHTML = `<tr><td colspan="10">Error loading data. Please try again.</td></tr>`;
        });
    console.log("Imported")
}

function displayTable(data) {
    let tbody = document.getElementById("resultsTable").querySelector("tbody");
    tbody.innerHTML = "";

    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10">No records found.</td></tr>`;
        return;
    }

    data.forEach(row => {
        let tr = document.createElement("tr");
        tr.innerHTML = `
            <td><button class="btn expand-btn" data-consignment="${row.ConsignmentID}">▶</button></td>
            <td>${row.ConsignmentID || '-'}</td>
            <td>${row.SupplierRef || '-'}</td>
            <td>${row.Product || '-'}</td>
            <td>${row.Class || '-'}</td>
            <td>${row.Size || '-'}</td>
            <td>${row.Variety || '-'}</td>
            <td>${row.QtySent || '-'}</td>
            <td>${(row.AveragePrice).toFixed(2) || '-'}</td>
            <td><button class="btn btn-sm btn-primary view-details-btn" data-consignment="${row.ConsignmentID}">View Details</button></td>
        `;
        tbody.appendChild(tr);
    });

    document.querySelectorAll(".view-details-btn").forEach(button => {
        button.addEventListener("click", function () {
            let consignmentId = this.getAttribute("data-consignment");
            showConsignmentDetails(consignmentId);
        });
    });

    document.querySelectorAll(".expand-btn").forEach(button => {
        button.addEventListener("click", function () {
            let consignmentId = this.getAttribute("data-consignment");
            toggleDocketDetails(this, consignmentId);
        });
    });
}

function filterTable(type) {
    let filteredData = [];
    console.log(type)
    if (type === "linked") {
        filteredData = importedData.filter(row => row.Matched === "Yes");
    } else if (type === "matched") {
        filteredData = importedData.filter(row => row.Matched === "No" && row.TopMatchCount !== 0);
    } else if (type === "nomatch") {
        filteredData = importedData.filter(row => row.Matched !== "Yes" && row.TopMatchCount === 0);
       
    }

    displayTable(filteredData);
}

function toggleDocketDetails(button, consignmentId) {
    let row = button.closest("tr");
    let nextRow = row.nextElementSibling;

    if (nextRow && nextRow.classList.contains("docket-details")) {
        nextRow.remove();
        button.innerText = "▶";
        return;
    }

    fetch(`/import/get_dockets/${consignmentId}`)
        .then(response => response.json())
        .then(dockets => {
            let detailsRow = document.createElement("tr");
            detailsRow.classList.add("docket-details");

            let detailsCell = document.createElement("td");
            detailsCell.colSpan = 13;

            if (dockets.length === 0) {
                detailsCell.innerHTML = "<em>No dockets found for this consignment.</em>";
            } else {
                let detailsTable = `
                <h5>Dockets<h5>
                    <table class="table table-bordered mt-2">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Qty Sold</th>
                                <th>Price</th>
                                <th>Sales Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${dockets.map(docket => `
                                <tr>
                                    <td>${docket.Date}</td>
                                    <td>${docket.QtySold}</td>
                                    <td>${docket.Price}</td>
                                    <td>${docket.SalesValue}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
                detailsCell.innerHTML = detailsTable;
            }

            detailsRow.appendChild(detailsCell);
            row.insertAdjacentElement("afterend", detailsRow);
            button.innerText = "▼";
        })
        .catch(error => {
            console.error("Error fetching docket details:", error);
            Swal.fire("Error!", "Failed to load docket details.", "error");
        });
}
function showConsignmentDetails(consignmentId) {
    fetch(`/import/get_consignment_details?consignment_id=${consignmentId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }

            let { ImportProduct, ImportVariety, ImportClass, ImportMass, ImportSize, ImportQty } = data.consignment_details;
            let matches = data.matches || [];

            // Function to check if values match (case-insensitive, ignores units)
            function isMatch(value1, value2) {
                if (value1 == null || value2 == null) return false;

                // Convert to strings, trim spaces, lowercase for case-insensitivity
                let v1 = String(value1).trim().toLowerCase();
                let v2 = String(value2).trim().toLowerCase();

                // Remove non-numeric characters for numbers (e.g., "10 kg" → "10")
                let num1 = parseFloat(v1.replace(/[^\d.-]/g, ""));
                let num2 = parseFloat(v2.replace(/[^\d.-]/g, ""));

                // If both are numbers, compare as numbers
                if (!isNaN(num1) && !isNaN(num2)) {
                    return num1 === num2;
                }

                // Otherwise, compare as case-insensitive strings
                return v1 === v2;
            }

            let matchOptions = matches.map(match => {
                return `
                    <tr>
                        <td><input type="radio" name="match" value="${match.DelLineIndex}"></td>
                        <td style="${isMatch(match.LineProduct, ImportProduct) ? 'background-color: #52eb34;' : ''}">${match.LineProduct}</td>
                        <td style="${isMatch(match.LineVariety, ImportVariety) ? 'background-color: #52eb34;' : ''}">${match.LineVariety}</td>
                        <td style="${isMatch(match.LineClass, ImportClass) ? 'background-color: #52eb34;' : ''}">${match.LineClass}</td>
                        <td style="${isMatch(match.LineMass, ImportMass) ? 'background-color: #52eb34;' : ''}">${match.LineMass}</td>
                        <td style="${isMatch(match.LineSize, ImportSize) ? 'background-color: #52eb34;' : ''}">${match.LineSize}</td>
                        <td>${match.LineBrand}</td>
                        <td style="${isMatch(match.LineQty, ImportQty) ? 'background-color: #52eb34;' : ''}">${match.LineQty}</td>
                    </tr>
                `;
            }).join('');

            Swal.fire({
                title: `Consignment ID: ${consignmentId}`,
                html: `
                    <b>Product:</b> ${ImportProduct} <br>
                    <b>Variety:</b> ${ImportVariety} <br>
                    <b>Class:</b> ${ImportClass} <br>
                    <b>Mass:</b> ${ImportMass} kg <br>
                    <b>Size:</b> ${ImportSize} <br>
                    <b>Quantity:</b> ${ImportQty} <br>
                    <br>
                    <table class="table table-bordered">
                        <thead>
                            <tr>
                                <th>Select</th>
                                <th>Line Product</th>
                                <th>Line Variety</th>
                                <th>Line Class</th>
                                <th>Line Mass</th>
                                <th>Line Size</th>
                                <th>Line Brand</th>
                                <th>Line Quantity</th>
                            </tr>
                        </thead>
                        <tbody>${matchOptions}</tbody>
                    </table>
                `,
                showCancelButton: true,
                width: '80%',
                confirmButtonText: "Match",
                cancelButtonText: "Close",
                preConfirm: () => {
                    let selectedMatch = document.querySelector('input[name="match"]:checked');
                    if (!selectedMatch) {
                        Swal.showValidationMessage("Please select a match.");
                    }
                    return selectedMatch ? selectedMatch.value : null;
                }
            }).then(result => {
                if (result.isConfirmed) {
                    let lineId = result.value;
                    console.log(result)
                    fetch(`/import/match_consignment/${consignmentId}/${lineId}`, { method: "POST" })
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            Swal.fire("Error!", data.error, "error");
                        } else {
                            Swal.fire("Matched!", data.message, "success");
                            fetchImportedData();
                        }
                    })
                    .catch(error => {
                        console.error("Match error:", error);
                        Swal.fire("Error!", "Failed to match consignment.", "error");
                    });
                }
            });
        })
        .catch(error => {
            console.error("Error fetching details:", error);
            Swal.fire("Error!", error.message || "Failed to load consignment details.", "error");
        });
}
