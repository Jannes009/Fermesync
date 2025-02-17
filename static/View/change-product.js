async function changeProductModal(lineId, lineValue) {
    // Elements
    const changeProductModal = document.querySelector('.product-modal-overlay');
    const saveProductBtn = document.getElementById('save-product-btn');
    const productDropdown = document.getElementById('product-dropdown');
    const currentLine = document.querySelector(`tr[row-id="${lineId}"]`);

    // Fetch products from the server
    const products = await fetchProducts();

    // Populate dropdown and set default value
    populateDropdown(products, lineValue);


    // Save Product
    saveProductBtn.addEventListener(
        'click',
        async () => {
            // find only text description
            const selectedOption = productDropdown.options[productDropdown.selectedIndex];
            const selectedProductId = parseInt(productDropdown.value,  10);
            const selectedText = selectedOption.textContent; // Split the text by '-'
            const parts = selectedText.split('-');
            const textAfterSixthDash = parts.slice(6).join('-');

            const success = await saveProduct(lineId, textAfterSixthDash,  selectedProductId);

            if (success) {
                alert('Product updated successfully!');
                closeModal();
            }
        },
        { once: true } // Ensures listener is only attached once
    );

    // Close Modal Function
    function closeModal() {
        changeProductModal.style.display = 'none'; // Hide modal
    }

    // Fetch Products from API
    async function fetchProducts() {
        try {
            const response = await fetch('/api/fetch_products');
            if (!response.ok) throw new Error('Failed to fetch products');
            return await response.json();
        } catch (error) {
            console.error('Error fetching products:', error);
            alert('Error fetching products');
            return [];
        }
    }

    // Populate Dropdown Function
    function populateDropdown(products, lineValue) {
        // Clear existing options
        productDropdown.innerHTML = '';

        // Add options to the dropdown
        products.forEach(productArray => {
            const [id, name] = productArray;
            const option = document.createElement('option');
            option.value = id;
            option.textContent = name;

            // Set the default selected value
            if (id === parseInt(lineValue, 10)) {
                option.selected = true;
            }

            productDropdown.appendChild(option);
        });

        // Initialize Select2 for the dropdown
        $(productDropdown).select2({
            matcher: customMatcher, // Use the reusable function
            width: '100%' // Optional: to make it responsive
        });
    }


    // Save Product to Server
    async function saveProduct(lineId, Description, productId) {
        try {
            const response = await fetch('/api/save_product', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ line_id: lineId, product_id: productId }),
            });

            if (!response.ok) {
                throw new Error('Failed to save product');
            }
            const descriptionText = currentLine.querySelector("#description");
            descriptionText.textContent = Description;
            return true; // Save was successful
        } catch (error) {
            console.error('Error saving product:', error);
            alert('Error saving product');
            return false; // Save failed
        }
    }
}

// Custom matcher function (define this once)
function customMatcher(params, data) {
    if ($.trim(params.term) === '') {
        return data;
    }

    let searchTerms = params.term.toLowerCase().split(/\s+|-/); // Split by space or dash
    let optionText = data.text.toLowerCase();
    let optionWords = optionText.split(/\s+|-/); // Normalize the option text

    let matches = searchTerms.every(term =>
        optionWords.some(word => word.includes(term))
    );

    return matches ? data : null;
}