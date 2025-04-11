document.addEventListener("DOMContentLoaded", () => {
    const salesAmountField = document.getElementById("InvoiceSalesAmnt");
    const totalDeductedField = document.getElementById("ZZInvoiceTotalDeducted");
    const netAmountDisplay = document.getElementById('net-amount');
    const dateInput = document.getElementById('ZZInvoiceDate');

    async function getTaxRate(dateStr) {
        // Check if dateStr is a valid date
        let parsedDate = Date.parse(dateStr);
        if (isNaN(parsedDate)) {
            const today = new Date();
            dateStr = today.toISOString().split("T")[0]; // Format as 'YYYY-MM-DD'
        }
    
        try {
            console.log(dateStr)
            const response = await fetch(`/get-tax-rate?date=${encodeURIComponent(dateStr)}`);
            const data = await response.json();
            if (response.ok && data.tax_rate !== undefined) {
                return data.tax_rate;
            } else {
                console.error("Failed to get tax rate:", data.error || data.message);
                return getTaxRate(); // fallback
            }
        } catch (error) {
            console.error("Error fetching tax rate:", error);
            return getTaxRate();
        }
    }
    

    function calculateNetAmount() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        const totalDeducted = parseFloat(totalDeductedField.value) || 0;
        const netAmount = salesAmount - totalDeducted;
        netAmountDisplay.textContent = "R" + netAmount.toFixed(2);
    }

    async function updateInclFields() {
        const vatMultiplier = await getTaxRate(dateInput.value);

        const markCommExcl = parseFloat(document.getElementById("ZZInvoiceMarketCommExcl").value) || 0;
        const agentCommExcl = parseFloat(document.getElementById("ZZInvoiceAgentCommExcl").value) || 0;
        const otherCostsExcl = parseFloat(document.getElementById("ZZInvoiceOtherCostsExcl").value) || 0;

        document.getElementById("ZZInvoiceMarketCommIncl").value = (markCommExcl * (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceAgentCommIncl").value = (agentCommExcl * (1 + vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsIncl").value = (otherCostsExcl * (1 + vatMultiplier / 100)).toFixed(2);
    }

    async function updateExclFields() {
        const vatMultiplier = await getTaxRate(dateInput.value);

        const markCommInc = parseFloat(document.getElementById("ZZInvoiceMarketCommIncl").value) || 0;
        const agentCommInc = parseFloat(document.getElementById("ZZInvoiceAgentCommIncl").value) || 0;
        const otherCostsIncl = parseFloat(document.getElementById("ZZInvoiceOtherCostsIncl").value) || 0;

        document.getElementById("ZZInvoiceMarketCommExcl").value = (markCommInc * (1 - vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceAgentCommExcl").value = (agentCommInc * (1 - vatMultiplier / 100)).toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsExcl").value = (otherCostsIncl * (1 - vatMultiplier / 100)).toFixed(2);
    }

    async function updateFields() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        const vatMultiplier = await getTaxRate(dateInput.value);
        let marketCommPerc = window.marketComm / 100;
        let agentCommPerc = window.agentComm / 100;

        const marketComm = (salesAmount * marketCommPerc).toFixed(2);
        const agentComm = (salesAmount * agentCommPerc).toFixed(2);
        const totalDeductedIncl = (
            parseFloat(marketComm * vatMultiplier) +
            parseFloat(agentComm * vatMultiplier)
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
        const otherCostsExcl = otherCostsIncl / vatMultiplier;

        document.getElementById("ZZInvoiceOtherCostsIncl").value = otherCostsIncl.toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsExcl").value = otherCostsExcl.toFixed(2);

        calculateNetAmount();
    }

    salesAmountField.addEventListener("input", updateFields);
    totalDeductedField.addEventListener("input", updateOtherCosts);
    document.getElementById("delivery-note-number").addEventListener("input", check_delivery_note);

    document.querySelectorAll('input[id*="Incl"]').forEach(input => {
        input.addEventListener("input", () => {
            updateExclFields();
        });
    });

    document.querySelectorAll('input[id*="Excl"]').forEach(input => {
        input.addEventListener("input", () => {
            updateInclFields();
        });
    });

    dateInput.addEventListener("change", () => {
        updateFields();
        updateOtherCosts();
    });

    updateFields();
});

document.addEventListener("DOMContentLoaded", () => {
    const submitBtn = document.getElementById("submit-btn");

    submitBtn.addEventListener("click", (event) => {
        event.preventDefault();

        const invoiceData = {
            InvoiceDate: document.querySelector('input[name="ZZInvoiceDate"]').value,
            InvoiceNo: document.querySelector('input[name="ZZInvoiceNo"]').value,
            InvoiceDelNoteNo: document.getElementById('delivery-note-number').value,
            InvoiceQty: document.querySelector('input[name="InvoiceSalesQty"]').value,
            InvoiceGross: parseFloat(document.querySelector('input[name="InvoiceSalesAmnt"]').value),
            InvoiceTotalDeducted: parseFloat(document.querySelector('input[name="ZZInvoiceTotalDeducted"]').value),
            InvoiceMarketCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceMarketCommIncl"]').value),
            InvoiceAgentCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceAgentCommIncl"]').value),
            InvoiceOtherCostsIncl: parseFloat(document.querySelector('input[name="ZZInvoiceOtherCostsIncl"]').value) || 0,
            tickedLines: [],
        };

        const calculatedAmount = document.getElementById("total-selected").textContent;
        const numericalValue = parseFloat(calculatedAmount.replace(/[^\d.-]/g, ""));
        const calculatedQuantity = document.getElementById("total-quantity").textContent;

        const totalDeducted = invoiceData['InvoiceTotalDeducted'];
        const marketComm = invoiceData['InvoiceMarketCommIncl'];
        const agentComm = invoiceData['InvoiceAgentCommIncl'];
        const extraCosts = invoiceData['InvoiceOtherCostsIncl'];

        if (invoiceData['InvoiceGross'] != numericalValue) {
            alert("Amounts don't balance");
            return;
        } else if (invoiceData['InvoiceQty'] != calculatedQuantity) {
            alert("Quantities don't balance");
            return;
        } else if (totalDeducted != (parseFloat(marketComm) + parseFloat(agentComm) + parseFloat(extraCosts)).toFixed(2)) {
            alert("Market Commission + Agent Commission + Other Costs must equal Total Deducted!");
            return;
        }

        const checkedBoxes = document.querySelectorAll('.child-line-checkbox:checked');
        checkedBoxes.forEach((checkbox) => {
            const compositeId = checkbox.getAttribute('data-id');
            if (compositeId) {
                const [noteNumber, lineId, salesLineId] = compositeId.split('-');
                invoiceData['tickedLines'].push({ salesLineId });
            }
        });

        fetch('/submit_invoice', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(invoiceData),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = '/create_invoice';
                alert("Invoice created successfully!");
            } else {
                alert(`Failed to submit invoice: ${data.error}`);
            }
        })
        .catch(error => console.error('Error:', error));
    });
});