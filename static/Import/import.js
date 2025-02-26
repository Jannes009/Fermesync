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

    Swal.fire({
        title: "Auto Import in Progress",
        html: `<div id="swal-status">Connecting...</div>`,
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => { Swal.showLoading(); }
    });

    if (window.eventSource) {
        window.eventSource.close();
    }

    window.eventSource = new EventSource(`/import/auto_import?start_date=${startDate}&end_date=${endDate}`);

    window.eventSource.onmessage = function (event) {
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
        Swal.fire({ icon: "error", title: "Connection Lost", text: "Failed to connect to the server." });
        window.eventSource.close();
    };
});

function fetchImportedData() {
    let table = document.getElementById("resultsTable");
    let tbody = table.querySelector("tbody");

    tbody.innerHTML = `<tr><td colspan="10">Loading...</td></tr>`;

    fetch("/import/get_imported_results")
        .then(response => response.json())
        .then(data => {
            tbody.innerHTML = "";

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10">No records found.</td></tr>`;
                return;
            }

            data.forEach(row => {
                let tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><button class="btn btn-sm btn-info expand-btn" data-consignment="${row.ConsignmentID}">▶</button></td>
                    <td>${row.ConsignmentID || '-'}</td>
                    <td>${row.Matched || '-'}</td>
                    <td>${row.TopMatchCount || '-'}</td>
                    <td>${row.MaxMatchDuplicate || '-'}</td>
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

            table.style.display = "table";
        })
        .catch(error => {
            console.error("Error fetching imported data:", error);
            tbody.innerHTML = `<tr><td colspan="10">Error loading data. Please try again.</td></tr>`;
        });
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
            detailsCell.colSpan = 10;

            if (dockets.length === 0) {
                detailsCell.innerHTML = "<em>No dockets found for this consignment.</em>";
            } else {
                let detailsTable = `
                    <table class="table table-bordered mt-2">
                        <thead>
                            <tr>
                                <th>Docket Number</th>
                                <th>Date</th>
                                <th>Qty Sold</th>
                                <th>Price</th>
                                <th>Sales Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${dockets.map(docket => `
                                <tr>
                                    <td>${docket.DocketNumber}</td>
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

            let matchOptions = matches.map(match => `
                <tr>
                    <td><input type="radio" name="match" value="${match.ConsignmentID}"></td>
                    <td>${match.LineProduct}</td>
                    <td>${match.LineVariety}</td>
                    <td>${match.LineClass}</td>
                    <td>${match.LineMass}</td>
                    <td>${match.LineSize}</td>
                    <td>${match.LineBrand}</td>
                    <td>${match.LineQty}</td>
                </tr>
            `).join('');

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
                width: '80%',  // Set modal width to 80% of the screen width
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
                    let matchID = result.value;
                    fetch(`/import/match_consignment/${consignmentId}/${matchID}`, { method: "POST" })
                        .then(() => {
                            Swal.fire("Matched!", "Consignment has been successfully matched.", "success");
                            fetchImportedData();
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
