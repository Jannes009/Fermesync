document.addEventListener('DOMContentLoaded', function () {
    fetch('/fetch-product-data')
        .then(response => response.json())
        .then(data => {
            populateDropdown('productCode', data.products, 'productDescription');
            populateDropdown('typeCode', data.types, 'typeDescription');
            populateDropdown('classCode', data.class, 'classDescription');
            populateDropdown('sizeCode', data.sizes, 'sizeDescription');
            populateDropdown('weightCode', data.weights, 'weightDescription');
            populateDropdown('brandCode', data.brands, 'brandDescription');
            populateDropdown('taxRate', data.tax_rates)
            document.querySelector('#taxRate').value = "6";
        })
        .catch(error => console.error('Error fetching product data:', error));
    

    const form = document.getElementById("createProductForm");

    form.addEventListener("submit", function (event) {
        event.preventDefault(); // Prevent default form submission
    
        const formData = new FormData(form);
    
        fetch(form.action, {
            method: "POST",
            body: formData,
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error("Network response was not OK");
                }
                return response.json(); // Backend returns JSON
            })
            .then(data => {
                if (data.error) {
                    alert(data.error);
                    return;
                }
    
                // Redirect to the Bill of Lading page
                window.location.href = '/create_entry';
    
                // Optionally reset the form
                form.reset();
            })
            .catch(error => {
                console.error("Error:", error);
                alert("An error occurred while creating the product. Please try again.");
            });
    });  
    const brandCode = this.querySelector('#brandCode');
    const productDescription = this.querySelector('#productDescription');
    console.log(brandCode.value, productDescription.value)
    generateProductCode()  
});

function populateDropdown(codeId, items, descriptionId) {
    const dropdown = document.getElementById(codeId);
    if(descriptionId == null){
        // Populate the dropdown with options
        items.forEach(item => {
            const code = document.createElement('option');
            code.value = item.id;  // Set the value to the 'id'
            code.textContent = item.code;  // Display code and description
            dropdown.appendChild(code);
        });
    } else{
        const descriptionInput = document.getElementById(descriptionId);

        // Populate the dropdown with options
        items.forEach(item => {
            const code = document.createElement('option');
            code.value = item.id;  // Set the value to the 'id'
            code.textContent = item.code;  // Display code and description
            dropdown.appendChild(code);
    
            const description = document.createElement('option');
            description.value = item.id;
            description.textContent = item.description; 
            descriptionInput.appendChild(description)
        });

        // Add event listener to update code when description is selected
        descriptionInput.addEventListener('change', function () {
            let dropdown_value = dropdown.value;
            let description_value = descriptionInput.value;

            if (dropdown_value != parseInt(description_value)) {
                dropdown.value = description_value;
            } else {
                dropdown.value = '';  // Set it to empty if no match
            }
            generateProductCode()
        });
            // Add event listener to update description when code is selected
        dropdown.addEventListener('change', function () {
            let dropdown_value = dropdown.value;
            let description_value = descriptionInput.value;

            if (dropdown_value != parseInt(description_value)) {
                descriptionInput.value = dropdown_value;
            } else {
                descriptionInput.value = '';  // Set it to empty if no match
            }
            generateProductCode()
        });
    }
}

// Function to get the displayed text of the selected option
function getSelectedText(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    const selectedOption = dropdown.options[dropdown.selectedIndex];
    if(selectedOption){
        text = selectedOption.textContent;
        if(text.includes("Select") && text.includes("Code") || text.includes("Description")){
            return ''
        } else{
            return text
        }
    }
    
    return selectedOption ? selectedOption.textContent : '';
}

// Function to generate Product Code
function generateProductCode() {
    // Retrieve the displayed text for each dropdown
    const productCode = getSelectedText('productCode');
    const typeCode = getSelectedText('typeCode');
    const classCode = getSelectedText('classCode');
    const sizeCode = getSelectedText('sizeCode');
    const weightCode = getSelectedText('weightCode');
    const brandCode = getSelectedText('brandCode');
    const productDescription = getSelectedText('productDescription');
    const typeDescription = getSelectedText('typeDescription');
    const classDescription = getSelectedText('classDescription');
    const sizeDescription = getSelectedText('sizeDescription');
    const weightDescription = getSelectedText('weightDescription');
    const brandDescription = getSelectedText('brandDescription');

    // Concatenate values to form the Product Code
    const generatedCode = `${productCode || ''}-${weightCode || ''}-${classCode || ''}-${sizeCode || ''}-${typeCode || ''}-${brandCode || ''}`;
    const generatedDescription = `${productDescription || ''}-${weightDescription || ''}-${classDescription || ''}-${sizeDescription || ''}-${typeDescription || ''}-${brandDescription || ''}`;

    // Update the display
    document.getElementById('generatedProductCode').textContent = generatedCode || 'Incomplete';
    document.getElementById("hiddenGeneratedProductCode").value = generatedCode || 'Incomplete';

    // Update the display
    document.getElementById('generatedProductDescription').textContent = generatedDescription || 'Incomplete';
    document.getElementById("hiddenGeneratedProductDescription").value = generatedDescription || 'Incomplete';
}

const dropdowns = document.querySelectorAll('select')
// Function to remove "Select Product Code" once a valid option is chosen
dropdowns.forEach(dropdown => {
    dropdown.addEventListener('change', () => {
        const firstOption = dropdown.options[0];
        if (firstOption && firstOption.value === '') {
            firstOption.remove();
        }
    });
});
