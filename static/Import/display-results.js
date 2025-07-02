let currentSearchValue = "";
let currentSearchMode = "contains"; // or "exact"
let currentFilterType = "matched"; // or default to "all" if needed

function fetchImportedData() {
    let table = document.getElementById("resultsTable");
    let tbody = table.querySelector("tbody");

    tbody.innerHTML = `<tr><td colspan="10">Loading...</td></tr>`;

    fetch("/import/get_imported_results")
        .then(response => response.json())
        .then(data => {
            importedData = data; // Store the data for filtering
            console.log(importedData)
            displayTable(data);  // Show all data initially
            updateFilterButtonCounts()
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

    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10">No records found.</td></tr>`;
        return;
    }

    data.forEach(row => {
        let tr = document.createElement("tr");

        // Make Delivery Note No clickable for matched and linked rows
        let isMatched = row.linconsignmentidexist === 0 && row.headelnotenoexist === 1;
        let isLinked = row.linconsignmentidexist === 1;
        let delNoteNoCell = '-';
        if (row.delnoteno) {
            if (isMatched || isLinked) {
                delNoteNoCell = `<a href="/delivery-note/${row.delnoteno}" target="_blank" style="color:#2563eb;text-decoration:underline;">${row.delnoteno}</a>`;
            } else {
                delNoteNoCell = `<span class="supplier-ref-text">${row.delnoteno}</span>`;
            }
        }

        let supplierRefCell = delNoteNoCell;
        let detailsButton = `<td>`
        // Only show the edit button in No Match mode
        if (row.linconsignmentidexist !== 1 && row.headelnotenoexist === 0) {
            supplierRefCell += `
                <button class="btn btn-sm btn-warning edit-supplier-ref" 
                    data-consignment="${row.consignmentid}" 
                    data-supplier-ref="${row.delnoteno || ""}">
                    Edit
                </button>
            `;
        }
        console.log(supplierRefCell)
        // Only show the edit button in No Match mode
        if (row.linconsignmentidexist !== 1 && row.headelnotenoexist === 1) {
            detailsButton += `
                <button class="btn btn-sm btn-primary view-details-btn" data-consignment="${row.consignmentid}">Confirm Match</button>
            `;
        }

        tr.innerHTML = `
            <td><button class="btn expand-btn" data-consignment="${row.consignmentid}">▶</button></td>
            <td>${row.agent || '-'}</td>
            <td>${supplierRefCell}</td>
            <td>${row.product || '-'}</td>
            <td>${row.class || '-'}</td>
            <td>${row.size || '-'}</td>
            <td>${row.variety || '-'}</td>
            <td>${row.brand || '-'}</td>
            <td>${row.qtysent || '-'}</td>
            <td>${row.averageprice}</td>
            ${detailsButton}</td>
        `;
        tbody.appendChild(tr);

        // Add event listeners for buttons within this row
        let editButton = tr.querySelector(".edit-supplier-ref");
        if (editButton) {
            editButton.addEventListener("click", function () {
                let consignmentId = this.getAttribute("data-consignment");
                let currentValue = this.getAttribute("data-supplier-ref");
                showEditSupplierRefModal(consignmentId, currentValue);
            });
        }

        let viewDetailsButton = tr.querySelector(".view-details-btn");
        if (viewDetailsButton) {
            viewDetailsButton.addEventListener("click", function () {
                let consignmentId = this.getAttribute("data-consignment");
                showConsignmentDetails(consignmentId);
            });
        }

        let expandButton = tr.querySelector(".expand-btn");
        if (expandButton) {
            expandButton.addEventListener("click", function () {
                let consignmentId = this.getAttribute("data-consignment");
                toggleDocketDetails(this, consignmentId);
            });
        }
    });
}


function updateMarketDelNoteNo(oldDelNoteNo, newDelNoteNo) {
    console.log(oldDelNoteNo, newDelNoteNo)
    return fetch("/import/update_market_del_note_no", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            oldDelNoteNo: oldDelNoteNo,
            newDelNoteNo: newDelNoteNo
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "success") {
            Swal.fire({
                title: "Success",
                text: data.message,
                icon: "success",
                timer: 1000,
                showConfirmButton: false
              });
              
            fetchImportedData()
        } else {
            Swal.fire("Error", data.message, "error");
        }
    })
    .catch(error => {
        Swal.fire("Error", "Failed to update market del note no.", "error");
        console.error("Update error:", error);
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
            if (data.error) throw new Error(data.error);

            let {
                ImportProduct, ImportVariety, ImportClass,
                ImportMass, ImportSize, ImportQty, ImportBrand
            } = data.consignment_details;
            let matches = data.matches || [];

            function normalizeSize(value) {
                if (!value) return '';
                let v = value.toLowerCase().replace(/[-\s]/g, '');
            
                if (['xs', 'extrasmall'].includes(v)) return 'xs';
                if (['s', 'small'].includes(v)) return 's';
                if (['ms', 'mediumsmall'].includes(v)) return 'ms';
                if (['m', 'medium'].includes(v)) return 'm';
                if (['lm', 'largemedium', 'largemed', 'mediumlarge'].includes(v)) return 'lm';
                if (['l', 'large'].includes(v)) return 'l';
            
                return v; // fallback to raw normalized string if no match
            }
            

            function isMatch(value1, value2, field = "") {
                if (value1 == null || value2 == null) return false;
                let v1 = String(value1).trim().toLowerCase();
                let v2 = String(value2).trim().toLowerCase();

                if (field === 'size') {
                    return normalizeSize(v1) === normalizeSize(v2);
                }

                let num1 = parseFloat(v1.replace(/[^\d.-]/g, ""));
                let num2 = parseFloat(v2.replace(/[^\d.-]/g, ""));
                if (!isNaN(num1) && !isNaN(num2)) return num1 === num2;

                return v1 === v2;
            }

            // Score and sort matches
            let scoredMatches = matches.map(match => {
                let fields = [
                    ['LineProduct', ImportProduct],
                    ['LineVariety', ImportVariety],
                    ['LineClass', ImportClass],
                    ['LineMass', ImportMass],
                    ['LineSize', ImportSize, 'size'],
                    ['LineBrand', ImportBrand],
                    ['LineQty', ImportQty]
                ];

                let greenCount = 0;
                for (let [key, importValue, type] of fields) {
                    if (isMatch(match[key], importValue, type)) greenCount++;
                }

                let qtyMatches = isMatch(match.LineQty, ImportQty);
                return { match, greenCount, qtyMatches };
            });

            // Sort: valid qty first, then highest match score
            scoredMatches.sort((a, b) => {
                if (a.qtyMatches !== b.qtyMatches) {
                    return b.qtyMatches - a.qtyMatches;
                }
                return b.greenCount - a.greenCount;
            });

            // Build table rows
            let rowScores = [];
            let matchOptions = scoredMatches.map(({ match, greenCount, qtyMatches }) => {
                rowScores.push(greenCount);

                let fields = [
                    ['LineProduct', ImportProduct],
                    ['LineVariety', ImportVariety],
                    ['LineClass', ImportClass],
                    ['LineMass', ImportMass],
                    ['LineSize', ImportSize, 'size'],
                    ['LineBrand', ImportBrand],
                    ['LineQty', ImportQty]
                ];

                let cells = fields.map(([key, importValue, fieldType]) => {
                    let value = match[key];
                    let matched = isMatch(value, importValue, fieldType);
                    return `<td style="${matched ? 'background-color: #52eb34;' : ''}">${value}</td>`;
                }).join('');

                return `
                    <tr style="${!qtyMatches ? 'opacity: 0.5;' : ''}">
                        <td>
                            <input type="radio" name="match" value="${match.DelLineIndex}" ${!qtyMatches ? 'disabled' : ''}>
                        </td>
                        ${cells}
                    </tr>
                `;
            }).join('');

            let maxScore = Math.max(...rowScores);

            Swal.fire({
                title: `Consignment ID: ${consignmentId}`,
                html: `
                    <b>Product:</b> ${ImportProduct} <br>
                    <b>Variety:</b> ${ImportVariety} <br>
                    <b>Class:</b> ${ImportClass} <br>
                    <b>Mass:</b> ${ImportMass} kg <br>
                    <b>Size:</b> ${ImportSize} <br>
                    <b>Brand:</b> ${ImportBrand} <br>
                    <b>Quantity:</b> ${ImportQty} <br><br>

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
                    let selected = document.querySelector('input[name="match"]:checked');
                    if (!selected) {
                        Swal.showValidationMessage("Please select a match.");
                        return false;
                    }

                    let selectedIndex = [...document.querySelectorAll('input[name="match"]')].findIndex(r => r === selected);
                    if (rowScores[selectedIndex] < maxScore) {
                        Swal.showValidationMessage("You did not select the best match (most green fields).");
                        return false;
                    }

                    return selected.value;
                }
            }).then(result => {
                if (result.isConfirmed) {
                    let lineId = result.value;
                    fetch(`/import/match_consignment/${consignmentId}/${lineId}`, { method: "POST" })
                        .then(res => res.json())
                        .then(data => {
                            if (data.error) {
                                Swal.fire("Error!", data.error, "error");
                            } else {
                                Swal.fire({
                                    title: "Matched!",
                                    text: data.message,
                                    icon: "success",
                                    timer: 1000,
                                    showConfirmButton: false
                                });
                                fetchImportedData();
                            }
                        }).catch(error => {
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



function showEditSupplierRefModal(consignmentId, currentValue) {
    Swal.fire({
        title: "Edit Market Del Note No",
        input: "text",
        inputValue: currentValue,
        showCancelButton: true,
        confirmButtonText: "Save",
        preConfirm: (newSupplierRef) => {
            if (!newSupplierRef.trim()) {
                Swal.showValidationMessage("Market Del Note No cannot be empty");
                return false;
            }
            return updateMarketDelNoteNo(currentValue, newSupplierRef);
        }
    });
}

let importedData = []; // Store fetched data for filtering

function filterTable(type) {
    let filteredData = [];

    if (type === "linked") {
        filteredData = importedData.filter(row => row.linconsignmentidexist === 1);
    } else if (type === "matched") {
        filteredData = importedData.filter(row => row.linconsignmentidexist === 0 && row.headelnotenoexist === 1);
    } else if (type === "nomatch") {
        filteredData = importedData.filter(row => row.linconsignmentidexist === 0 && row.headelnotenoexist === 0);
    }

    // Apply search filtering if needed
    if (currentSearchValue) {
        const search = currentSearchValue.toLowerCase();
        filteredData = filteredData.filter(row => {
            const ref = (row.delnoteno || "").toString().toLowerCase();
            return currentSearchMode === "exact" ? ref === search : ref.includes(search);
        });
    }

    displayTable(filteredData);
    updateFilterButtonCounts();
}


function updateFilterButtonCounts() {
    let filtered = importedData;

    if (currentSearchValue) {
        const search = currentSearchValue.toLowerCase();
        filtered = importedData.filter(row => {
            const ref = (row.delnoteno || "").toString().toLowerCase();
            return currentSearchMode === "exact" ? ref === search : ref.includes(search);
        });
    }

    const matchedCount = filtered.filter(row => row.linconsignmentidexist === 0 && row.headelnotenoexist === 1).length;
    const linkedCount = filtered.filter(row => row.linconsignmentidexist === 1).length;
    const noMatchCount = filtered.filter(row => row.linconsignmentidexist === 0 && row.headelnotenoexist === 0).length;

    document.getElementById("matchedBtn").textContent = `Matched (${matchedCount})`;
    document.getElementById("linkedBtn").textContent = `Linked (${linkedCount})`;
    document.getElementById("noMatchBtn").textContent = `No Match (${noMatchCount})`;
}

document.getElementById("searchInput").addEventListener("input", function () {
    currentSearchValue = this.value.trim();
    filterTable(currentFilterType); // or call with default filter like "all"
});

document.getElementById("searchMode").addEventListener("change", function () {
    currentSearchMode = this.value;
    filterTable(currentFilterType);
});
