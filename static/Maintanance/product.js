// Show creating toast
const creatingToast = Swal.mixin({
    toast: true,
    position: 'top-end',
    showConfirmButton: false,
    timerProgressBar: true,
    background: '#3085d6',
    color: 'white',
    timer: 0 // Infinite timer
});
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

    form.addEventListener("submit", async function (event) {
        event.preventDefault(); // Prevent default form submission
    
        const formData = new FormData(form);
    
        // Show the "Creating..." toast
        creatingToast.fire({
            title: 'Creating product...',
            didOpen: () => {
                Swal.showLoading();
            }
        });
    
        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: formData,
            });
    
            const body = await response.json();
            Swal.close(); // Close the creating toast
    
            if (!response.ok) {
                // If backend returned an error
                await Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: body.error || 'Something went wrong.',
                });
                return;
            }
    
            // Success
            await Swal.fire({
                icon: 'success',
                title: 'Product created!',
                text: body.success || 'The product was successfully created.',
                showConfirmButton: false,
                timer: 2000,
                timerProgressBar: true,
                toast: true,
                position: 'top-end',
            });
    
            form.reset(); // Optionally reset the form
            window.location.href = '/create_entry'; // Redirect after
    
        } catch (error) {
            Swal.close(); // Make sure to close "creating..." if still open
            console.error("Error:", error);
            await Swal.fire({
                icon: 'error',
                title: 'Unexpected Error',
                text: 'An unexpected error occurred. Please try again.',
            });
        }
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
