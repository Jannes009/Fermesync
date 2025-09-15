const Toast = Swal.mixin({
    toast: true,
    position: 'top-end',
    showConfirmButton: false,
    timer: 1800,
    timerProgressBar: true,
    didOpen: (toast) => {
        toast.addEventListener('mouseenter', Swal.stopTimer);
        toast.addEventListener('mouseleave', Swal.resumeTimer);
    },
    backdrop: false,
});

document.addEventListener("DOMContentLoaded", () => {
    const salesAmountField = document.getElementById("InvoiceSalesAmnt");
    const totalDeductedField = document.getElementById("ZZInvoiceTotalDeducted");
    const otherCostsField = document.getElementById("ZZInvoiceOtherCostsExcl");
    const netAmountDisplay = document.getElementById('net-amount');
    const dateInput = document.getElementById('ZZInvoiceDate');
    const taxRateDisplay = document.getElementById("tax-rate-value");
    const manualTaxButton = document.getElementById("change-tax-rate-icon");

    let manualTaxRate = null;

    async function getTaxRate(dateStr) {
        if (manualTaxRate !== null) {
            return manualTaxRate;
        }

        let parsedDate = Date.parse(dateStr);
        if (isNaN(parsedDate)) {
            const today = new Date();
            dateStr = today.toISOString().split("T")[0];
        }

        try {
            const response = await fetch(`/get-tax-rate?date=${encodeURIComponent(dateStr)}`);
            const data = await response.json();
            if (response.ok && data.tax_rate !== undefined) {
                updateTaxRateDisplay(data.tax_rate);
                return data.tax_rate;
            } else {
                console.error("Failed to get tax rate:", data.error || data.message);
                return 15; // fallback default
            }
        } catch (error) {
            console.error("Error fetching tax rate:", error);
            return 15; // fallback default
        }
    }

    function updateTaxRateDisplay(rate) {
        taxRateDisplay.textContent = rate;
    }

    manualTaxButton.addEventListener("click", async () => {
        const { value: newRate } = await Swal.fire({
            title: "Enter Manual Tax Rate",
            input: "number",
            inputLabel: "Tax Rate (%)",
            inputValue: manualTaxRate ?? "",
            inputAttributes: {
                min: 0,
                max: 100,
                step: 0.01
            },
            showCancelButton: true,
            confirmButtonText: "Set"
        });

        if (newRate !== undefined && newRate !== null && newRate !== "") {
            manualTaxRate = parseFloat(newRate);
            updateTaxRateDisplay(manualTaxRate);
            updateFields();
            updateOtherCosts();
        }
    });

    function calculateNetAmount() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        const totalDeducted = parseFloat(totalDeductedField.value) || 0;
        const netAmount = salesAmount - totalDeducted;
        netAmountDisplay.textContent = netAmount.toFixed(2);
    }

    async function updateInclFields() {
        const vatMultiplier = await getTaxRate(dateInput.value);

        const markCommExcl = parseFloat(document.getElementById("ZZInvoiceMarketCommExcl").value) || 0;
        const agentCommExcl = parseFloat(document.getElementById("ZZInvoiceAgentCommExcl").value) || 0;
        const otherCostsExcl = parseFloat(document.getElementById("ZZInvoiceOtherCostsExcl").textContent) || 0;
        const otherCostsIncl = (otherCostsExcl * (1 + vatMultiplier / 100)).toFixed(2);

        document.getElementById("ZZInvoiceMarketCommIncl").value = (markCommExcl * (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceAgentCommIncl").value = (agentCommExcl * (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsIncl").textContent = otherCostsIncl;
        return otherCostsIncl;
    }

    async function updateExclFields() {
        const vatMultiplier = await getTaxRate(dateInput.value);

        const markCommInc = parseFloat(document.getElementById("ZZInvoiceMarketCommIncl").value) || 0;
        const agentCommInc = parseFloat(document.getElementById("ZZInvoiceAgentCommIncl").value) || 0;
        const otherCostsIncl = parseFloat(document.getElementById("ZZInvoiceOtherCostsIncl").textContent) || 0;

        document.getElementById("ZZInvoiceMarketCommExcl").value = (markCommInc / (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceAgentCommExcl").value = (agentCommInc / (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsExcl").textContent = (otherCostsIncl / (1 + vatMultiplier / 100)).toFixed(2);
    }

    async function updateFields() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        const vatMultiplier = await getTaxRate(dateInput.value);
        let marketCommPerc = window.marketComm / 100;
        let agentCommPerc = window.agentComm / 100;

        const marketComm = (salesAmount * marketCommPerc).toFixed(2);
        const agentComm = (salesAmount * agentCommPerc).toFixed(2);
        const totalDeductedIncl = (
            parseFloat(marketComm * (1 + vatMultiplier / 100)) +
            parseFloat(agentComm * (1 + vatMultiplier / 100))
        ).toFixed(2);

        document.getElementById("ZZInvoiceTotalDeducted").value = totalDeductedIncl;
        document.getElementById("ZZInvoiceMarketCommExcl").value = marketComm;
        document.getElementById("ZZInvoiceAgentCommExcl").value = agentComm;

        await updateInclFields();
        calculateNetAmount();
    }

    async function updateOtherCosts() {
        const vatMultiplier = await getTaxRate(dateInput.value);

        const totalDeducted = parseFloat(document.getElementById("ZZInvoiceTotalDeducted").value) || 0;
        const marketComm = parseFloat(document.getElementById("ZZInvoiceMarketCommIncl").value) || 0;
        const agentComm = parseFloat(document.getElementById("ZZInvoiceAgentCommIncl").value) || 0;

        const otherCostsIncl = totalDeducted - marketComm - agentComm;
        const otherCostsExcl = otherCostsIncl / (1 + vatMultiplier / 100);
        console.log(totalDeducted, marketComm, agentComm, otherCostsIncl)

        document.getElementById("ZZInvoiceOtherCostsIncl").textContent = otherCostsIncl.toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsExcl").textContent = otherCostsExcl.toFixed(2);

        calculateNetAmount();
    }

    salesAmountField.addEventListener("input", updateFields);
    totalDeductedField.addEventListener("input", updateOtherCosts);
    document.getElementById("delivery-note-number").addEventListener("input", check_delivery_note);
    document.getElementById("ZZInvoiceNo").addEventListener("input", check_invoice_number);

    // Listen for changes on *Excl* fields (excluding Other Costs, since it's static now)
    document.querySelectorAll('input[id*="Excl"]').forEach(input => {
        input.addEventListener("input", async () => {
            await updateInclFields();
            await updateOtherCosts()
        });
    });

    // Listen for changes on *Incl* fields (excluding Other Costs)
    document.querySelectorAll('input[id*="Incl"]').forEach(input => {
        input.addEventListener("input", async () => {
            await updateExclFields();
            await updateOtherCosts();
        });
    });


    dateInput.addEventListener("change", () => {
        manualTaxRate = null;  // Clear manual rate on date change
        updateFields();
        updateOtherCosts();
    });

    updateFields(); // initial load
});

async function isInvoiceNumberUnique(invoiceNo) {
    const response = await fetch('/check_invoice_no', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ salesOrderNo: invoiceNo })
    });
    const data = await response.json();
    return !data.exists;
}

document.addEventListener("DOMContentLoaded", () => {
    const submitBtn = document.getElementById("submit-btn");

    submitBtn.addEventListener("click", async (event) => {
        event.preventDefault();

        const invoiceNo = document.querySelector('input[name="ZZInvoiceNo"]').value;
        console.log(invoiceNo)
        const isUnique = await isInvoiceNumberUnique(invoiceNo);
        if (!isUnique) {
            Swal.fire({
                title: 'Invoice Number Exists',
                text: 'This invoice number already exists. Please use a different number.',
                icon: 'error'
            });
            return;
        }

        const salesOrderData = {
            InvoiceDate: document.querySelector('input[name="ZZInvoiceDate"]').value,
            InvoiceNo: invoiceNo,
            InvoiceDelNoteNo: document.getElementById('delivery-note-number').value,
            InvoiceQty: document.querySelector('input[name="InvoiceSalesQty"]').value,
            InvoiceGross: parseFloat(document.querySelector('input[name="InvoiceSalesAmnt"]').value),
            InvoiceTotalDeducted: parseFloat(document.querySelector('input[name="ZZInvoiceTotalDeducted"]').value),
            InvoiceMarketCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceMarketCommIncl"]').value),
            InvoiceAgentCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceAgentCommIncl"]').value),
            InvoiceOtherCostsIncl: parseFloat(document.getElementById("ZZInvoiceOtherCostsIncl").textContent) || 0,
            TaxRate: parseFloat(document.getElementById("tax-rate-value").textContent),
            tickedLines: [],
        };

        const calculatedAmount = document.getElementById("total-selected").textContent;
        const numericalValue = parseFloat(calculatedAmount.replace(/[^\d.-]/g, ""));
        const calculatedQuantity = document.getElementById("total-quantity").textContent;

        const totalDeducted = salesOrderData['InvoiceTotalDeducted'];
        const marketComm = salesOrderData['InvoiceMarketCommIncl'];
        const agentComm = salesOrderData['InvoiceAgentCommIncl'];
        const extraCosts = salesOrderData['InvoiceOtherCostsIncl'];

        const nett_input = parseFloat(document.querySelector('input[name="ZZInvoiceNettInputAmount"]').value)
        const nett_display = parseFloat(document.getElementById("net-amount").textContent)
        console.log(nett_display, nett_input)

        if (salesOrderData['InvoiceGross'] != numericalValue) {
            Swal.fire({
                title: "Amounts Don't Balance",
                text: "Amounts don't balance.",
                icon: "error"
            });
            return;
        } else if (salesOrderData['InvoiceQty'] != calculatedQuantity) {
            Swal.fire({
                title: "Quantities Don't Balance",
                text: "Quantities don't balance.",
                icon: "error"
            });
            return;
        } else if (totalDeducted != (parseFloat(marketComm) + parseFloat(agentComm) + parseFloat(extraCosts))) {
            console.log("Market Commission + Agent Commission + Other Costs must equal Total Deducted!");
            // return;
        } else if(nett_input != nett_display){
            Swal.fire({
                title: "Nett Amounts Don't Balance",
                text: "Nett amounts don't balance.",
                icon: "error"
            });
            return;
        } else if(nett_display <= 0){
            Swal.fire({
                title: "Nett Amount Must Be Greater Than Zero",
                text: "Nett amount must be greater than zero.",
                icon: "error"
            });
            return;
        }
        const agentCheckbox = document.getElementById(`confirm-agent`);
        const unitCheckbox = document.getElementById(`confirm-units`);
        console.log(agentCheckbox?.checked, unitCheckbox?.checked )
        // New check: Both Agent and Production Unit must be ticked
        if (!agentCheckbox?.checked || !unitCheckbox?.checked) {
            Swal.fire({
                title: "Confirmation Required",
                text: "Please confirm both the Market Agent and Production Unit before submitting.",
                icon: "warning"
            });
            return; // stop submission
        }

        const checkedBoxes = document.querySelectorAll('.child-line-checkbox:checked');
        checkedBoxes.forEach((checkbox) => {
            const compositeId = checkbox.getAttribute('data-id');
            if (compositeId) {
                const [noteNumber, lineId, salesLineId] = compositeId.split('-');
                salesOrderData['tickedLines'].push({ salesLineId });
            }
        });
        Swal.fire({
            title: 'Creating Invoice',
            html: '<p style="margin-top: 10px; font-size: 1.1rem; color: #555;">Please wait while we process your request...</p>',
            icon: 'info',
            allowOutsideClick: false,
            allowEscapeKey: false,
            showConfirmButton: false,
            didOpen: () => {
                Swal.showLoading();
            },
            customClass: {
                title: 'swal-title',
                htmlContainer: 'swal-text'
            }
        });


        fetch('/submit_invoice', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(salesOrderData),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    title: 'Sales Order Created Successfully',
                    icon: 'success',
                    timer: 1800,
                    showConfirmButton: false
                }).then(() => {
                    window.location.href = '/create_sales_order';
                });
            } else {
                Swal.fire({
                    title: 'Failed to Submit Sales Order',
                    text: data.error || 'Unknown error.',
                    icon: 'error'
                });
            }
        })
        .catch(error => {
            Swal.fire({
                title: 'Error',
                text: 'Error submitting sales order.',
                icon: 'error'
            });
            console.error('Error:', error);
        });
    });
});