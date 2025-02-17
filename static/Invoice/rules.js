document.addEventListener("DOMContentLoaded", () => {
    const salesAmountField = document.getElementById("InvoiceSalesAmnt");
    const totalDeductedField = document.getElementById("ZZInvoiceTotalDeducted");
    const netAmountDisplay = document.getElementById('net-amount');

    function calculateNetAmount() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        const totalDeducted = parseFloat(totalDeductedField.value) || 0;
        const netAmount = salesAmount - totalDeducted;

        netAmountDisplay.textContent = "R" + netAmount.toFixed(2);
    }

    function updateInclFields(){
        const markCommExcl = document.getElementById("ZZInvoiceMarketCommExcl").value
        const agentCommExcl = document.getElementById("ZZInvoiceAgentCommExcl").value
        const otherCostsExcl = document.getElementById("ZZInvoiceOtherCostsExcl").value

        let marketCommInc = (markCommExcl * 1.15).toFixed(2)
        let agentCommInc = (agentCommExcl * 1.15).toFixed(2)
        let otherCostsInc = (otherCostsExcl * 1.15).toFixed(2)


        document.getElementById("ZZInvoiceMarketCommIncl").value = marketCommInc;
        document.getElementById("ZZInvoiceAgentCommIncl").value = agentCommInc;
        document.getElementById("ZZInvoiceOtherCostsIncl").value = otherCostsInc;
        return marketCommInc + agentCommInc + otherCostsInc
    }

    function updateExclFields(){
        const markCommInc = document.getElementById("ZZInvoiceMarketCommIncl").value
        const agentCommInc = document.getElementById("ZZInvoiceAgentCommIncl").value
        const otherCostsIncl = document.getElementById("ZZInvoiceOtherCostsIncl").value

        let marketCommExcl = (markCommInc / 1.15).toFixed(2)
        let agentCommExcl = (agentCommInc / 1.15).toFixed(2)
        let otherCostsExcl = (otherCostsIncl / 1.15).toFixed(2)


        document.getElementById("ZZInvoiceMarketCommExcl").value = marketCommExcl;
        document.getElementById("ZZInvoiceAgentCommExcl").value = agentCommExcl;
        document.getElementById("ZZInvoiceOtherCostsExcl").value = otherCostsExcl;
        return marketCommExcl + agentCommExcl + otherCostsExcl
    }


    // Function to calculate and update the values based on sales amount
    function updateFields() {
        const salesAmount = parseFloat(salesAmountField.value) || 0;
        let marketCommPerc = window.marketComm / 100;
        let agentCommPerc = window.agentComm / 100;

        // Default calculations
        const totalDeductedIncl = (parseFloat((salesAmount * marketCommPerc * 1.15).toFixed(2)) + parseFloat((salesAmount * agentCommPerc * 1.15).toFixed(2))).toFixed(2);
        const marketComm = (salesAmount * marketCommPerc).toFixed(2);
        const agentComm = (salesAmount * agentCommPerc).toFixed(2);


        // Update the fields with the calculated values
        document.getElementById("ZZInvoiceTotalDeducted").value = totalDeductedIncl;
        document.getElementById("ZZInvoiceMarketCommExcl").value = marketComm;
        document.getElementById("ZZInvoiceAgentCommExcl").value = agentComm;
        updateInclFields();
        calculateNetAmount()
    }

    function updateOtherCosts(){
        // Default calculations
        const totalDeducted = document.getElementById("ZZInvoiceTotalDeducted").value;
        const marketComm = document.getElementById("ZZInvoiceMarketCommIncl").value ;
        const agentComm = document.getElementById("ZZInvoiceAgentCommIncl").value;
        const otherCostsIncl = totalDeducted - marketComm - agentComm;
        const otherCostsExcl = otherCostsIncl / 1.15
        document.getElementById("ZZInvoiceOtherCostsIncl").value = otherCostsIncl.toFixed(2);
        document.getElementById("ZZInvoiceOtherCostsExcl").value = otherCostsExcl.toFixed(2);
        calculateNetAmount();
    }

    // Event listener to trigger the update function when sales amount changes
    salesAmountField.addEventListener("input", updateFields);
    totalDeductedField.addEventListener("input", updateOtherCosts);
    document.getElementById("delivery-note-number").addEventListener("input", check_delivery_note)
    document.querySelectorAll('input[id*="Incl"]').forEach(input => {
        input.addEventListener("input", function () {
            updateExclFields()
        });
    });

    // Event listener for "Excl." fields
    document.querySelectorAll('input[id*="Excl"]').forEach(input => {
        input.addEventListener("input", function () {
            updateInclFields()
        });
    });



    // Initialize the fields on page load
    updateFields();
});

document.addEventListener("DOMContentLoaded", () => {
    const submitBtn = document.getElementById("submit-btn");

    // Function to handle form submission
    submitBtn.addEventListener("click", (event) => {
        event.preventDefault(); // Prevent the default form submission behavior
        const requiredFields = document.querySelectorAll("input[required]");
        // let allFieldsFilled = true;

        // requiredFields.forEach((field) => {
        //     if (!field.value.trim()) {
        //         field.classList.add("error-border"); // Add a red border (CSS required)
        //         allFieldsFilled = false;
        //     } else {
        //         field.classList.remove("error-border");
        //     }
        // });

        // if (!allFieldsFilled) {
        //     alert("Please fill in all required fields.");
        //     return;
        // }


        let invoiceData = {
            InvoiceDate: document.querySelector('input[name="ZZInvoiceDate"]').value,
            InvoiceNo: document.querySelector('input[name="ZZInvoiceNo"]').value,
            InvoiceDelNoteNo: document.getElementById('delivery-note-number').value,
            InvoiceQty: document.querySelector('input[name="InvoiceSalesQty"]').value,
            InvoiceGross: parseFloat(document.querySelector('input[name="InvoiceSalesAmnt"]').value),// document.querySelector('input[name="InvoiceGross"]').value,
            InvoiceTotalDeducted: parseFloat(document.querySelector('input[name="ZZInvoiceTotalDeducted"]').value),
            InvoiceMarketCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceMarketCommIncl"]').value),
            InvoiceAgentCommIncl: parseFloat(document.querySelector('input[name="ZZInvoiceAgentCommIncl"]').value),
            InvoiceOtherCostsIncl: parseFloat(document.querySelector('input[name="ZZInvoiceOtherCostsIncl"]').value) || 0,
            tickedLines: [], 
        };

        // get form values
        const calculatedAmount = document.getElementById("total-selected").textContent;
        const numericalValue = parseFloat(calculatedAmount.replace(/[^\d.-]/g, ""));
        const calculatedQuantity = document.getElementById("total-quantity").textContent;

        const totalDeducted = invoiceData['InvoiceTotalDeducted'];
        const marketComm = invoiceData['InvoiceMarketCommIncl']
        const agentComm = invoiceData['InvoiceAgentCommIncl']
        const extraCosts = invoiceData['InvoiceOtherCostsIncl']
        console.log(totalDeducted, marketComm, agentComm, extraCosts, marketComm + agentComm + extraCosts)
        
        if(invoiceData['InvoiceGross'] != numericalValue){
            alert("Amounts don't balance")
            return
        } else if(invoiceData['InvoiceQty'] != calculatedQuantity){
            alert("Quantities don't balance")
            return
        } else if(totalDeducted != (parseFloat(marketComm) + parseFloat(agentComm) + parseFloat(extraCosts)).toFixed(2)){
            alert("Market Commission + Agent Commission + Other Costs must equal Total Deducted! Total: ", invoiceData['InvoiceMarketCommExcl'] + invoiceData['InvoiceAgentCommExcl'] + invoiceData['InvoiceOtherCostsIncl']);
            return;
        }

        const tickedLines = [];

        // Select all checkboxes that are checked
        const checkedBoxes = document.querySelectorAll('.child-line-checkbox:checked');
        console.log(checkedBoxes)
        // Extract the composite IDs of the checked lines
        checkedBoxes.forEach((checkbox) => {
            const compositeId = checkbox.getAttribute('data-id');
            if (compositeId) {
                // Split the composite ID if needed for further processing
                const [noteNumber, lineId, salesLineId] = compositeId.split('-');
                
                tickedLines.push({
                    salesLineId
                });
            }
        });
        invoiceData['tickedLines'] = tickedLines;
        

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
                alert("Invoice created succesfully!");
            } else {
                alert(`Failed to submit invoice: ${data.error}`);
            }
        })
        .catch(error => console.error('Error:', error));

    });
});
