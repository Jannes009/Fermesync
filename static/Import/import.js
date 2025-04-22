let eventSource; // Local scoped
// document.getElementById("manualImportForm").addEventListener("submit", function (event) {
//     event.preventDefault();
//     let formData = new FormData(this);

//     Swal.fire({
//         title: "Importing...",
//         html: "<b>Processing file...</b>",
//         allowOutsideClick: false,
//         showConfirmButton: false,
//         didOpen: () => { Swal.showLoading(); }
//     });

//     fetch("/import/upload_excel", {  // Adjusted the route
//         method: "POST",
//         body: formData
//     })
//     .then(response => response.json())
//     .then(data => {
//         Swal.close();

//         let result = data.results[0];

//         if (result.status === "Success") {
//             Swal.fire({
//                 icon: "success",
//                 title: "Import Completed!",
//                 text: result.message
//             }).then(() => fetchImportedData());
//         } else {
//             Swal.fire({
//                 icon: "error",
//                 title: "Import Failed",
//                 text: result.message
//             });
//         }
//     })
//     .catch(error => {
//         Swal.fire("Error!", "An error occurred while importing.", "error");
//         console.error("Import error:", error);
//     });
// });

document.getElementById("autoImportForm").addEventListener("submit", function (event) {
    event.preventDefault();

    const service = document.getElementById("service").value;
    let startDate, endDate;

    if (service === "Technofresh") {
        startDate = document.getElementById("start_date").value;
        endDate = document.getElementById("end_date").value;

        // Convert input dates to Date objects
        const start = new Date(startDate);
        const end = new Date(endDate);

        // Check if end date is before start date
        if (start > end) {
            Swal.fire({
                icon: "error",
                title: "Invalid Date Range",
                text: "Start date cannot be later than end date."
            });
            return;
        }

        // Check if the date range exceeds 7 days
        const differenceInDays = (end - start) / (1000 * 60 * 60 * 24);
        if (differenceInDays > 7) {
            Swal.fire({
                icon: "error",
                title: "Date Range Too Large",
                text: "Please select a date range of 7 days or less."
            });
            return;
        }

    } else if (service === "FreshLinq") {
        startDate = document.getElementById("sales_date").value;
        endDate = startDate; // Only one date needed for FreshLinq

        // Convert input date to Date object
        const selectedDate = new Date(startDate);
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 2); // Calculate one year ago

        // Ensure date is not older than a year
        if (selectedDate < oneYearAgo) {
            Swal.fire({
                icon: "error",
                title: "Invalid Date",
                text: "The selected date cannot be more than a year ago."
            });
            return;
        }
    } else {
        Swal.fire({
            icon: "error",
            title: "Invalid Service",
            text: "Please select a valid service."
        });
        return;
    }

    let isCancelled = false;

    Swal.fire({
        title: "Auto Import in Progress",
        html: `<div id="swal-status">Connecting...</div>`,
        allowOutsideClick: false,
        showConfirmButton: false,
        showCancelButton: true,
        cancelButtonText: "Cancel",
        icon: Swal.showLoading(),
        didOpen: () => {
            Swal.showLoading();
        }
    }).then((result) => {
        if (result.dismiss === Swal.DismissReason.cancel) {
            isCancelled = true;
            if (eventSource) {
                eventSource.close();
            }
            Swal.fire({
                icon: "warning",
                title: "Import Cancelled",
                text: "The import process has been stopped."
            });
        }
    });

    // Close any previous eventSource connection before opening a new one
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(
        `/import/auto_import?start_date=${startDate}&end_date=${endDate}&service=${service}`
    );

    eventSource.onmessage = function (event) {
        if (isCancelled) return; // Stop processing if cancelled

        const message = event.data.replace("data: ", "");
        document.getElementById("swal-status").innerHTML = message;

        if (message.includes("SUCCESS")) {
            Swal.fire({
                icon: "success",
                title: "Import Completed!",
                text: "Import finished successfully."
            }).then(() => {
                eventSource.close();
                fetchImportedData();
            });
        }

        if (message.includes("ERROR")) {
            Swal.fire({ icon: "error", title: "Error", text: message });
            eventSource.close();
        }
    };

    eventSource.onerror = function () {
        if (!isCancelled) {
            console.log( "Failed to connect to the server.");
            //Swal.fire({ icon: "error", title: "Connection Lost", text: "Failed to connect to the server." });
        }
        eventSource.close();
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

document.addEventListener("DOMContentLoaded", function () {
    const serviceDropdown = document.getElementById("service");
    const technofreshFields = document.getElementById("technofreshFields");
    const freshlinqFields = document.getElementById("freshlinqFields");
    const unknownService = document.getElementById("unknownService");
    const autoImportBtn = document.getElementById("autoImportBtn");

    serviceDropdown.addEventListener("change", function () {
        // Reset visibility
        technofreshFields.classList.add("d-none");
        freshlinqFields.classList.add("d-none");
        unknownService.classList.add("d-none");
        autoImportBtn.classList.add("d-none");

        // Show the correct fields based on the selection
        const selectedService = serviceDropdown.value;

        if (selectedService === "Technofresh") {
            technofreshFields.classList.remove("d-none");
            autoImportBtn.classList.remove("d-none");
        } else if (selectedService === "FreshLinq") {
            freshlinqFields.classList.remove("d-none");
            autoImportBtn.classList.remove("d-none");
        } else {
            unknownService.classList.remove("d-none");
        }
    });
});
