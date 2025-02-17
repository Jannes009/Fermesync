document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('dynamicModal');
    const modalTitle = document.getElementById('modalTitle');
    const closeModal = document.getElementById('closeModal');
    const modalForm = document.getElementById('modalForm');
    const codeInputContainer = document.getElementById('newCodeContainer');

    // Map buttons to modal content with character limits
    const modalMappings = {
        product: {
            title: 'Add Product',
            codeLabel: 'New Product Code',
            descriptionLabel: 'New Product Description',
            codeLength: 5,
        },
        type: {
            title: 'Add Type',
            codeLabel: 'New Type Code',
            descriptionLabel: 'New Type Description',
            codeLength: 3,
        },
        class: {
            title: 'Add Class',
            codeLabel: 'New Class Code',
            descriptionLabel: 'New Class Description',
            codeLength: 4,
        },
        size: {
            title: 'Add Size',
            codeLabel: 'New Size Code',
            descriptionLabel: 'New Size Description',
            codeLength: 2,
        },
        weight: {
            title: 'Add Weight',
            codeLabel: 'New Weight Code',
            descriptionLabel: 'New Weight Description',
            codeLength: 6,
        },
        brand: {
            title: 'Add Brand',
            codeLabel: 'New Brand Code',
            descriptionLabel: 'New Brand Description',
            codeLength: 4,
        },
    };

    // Function to generate input boxes for the code field
    function generateCodeInputs(codeLength) {
        codeInputContainer.innerHTML = ''; // Clear existing inputs
        for (let i = 0; i < codeLength; i++) {
            const input = document.createElement('input');
            input.type = 'text';
            input.maxLength = 1;
            input.classList.add('code-char');
            input.dataset.index = i;
            input.style.width = '30px';
            input.style.textAlign = 'center';
            input.style.marginRight = '5px';
            codeInputContainer.appendChild(input);
        }
    }

    // Function to open modal and set dynamic content
    function openModal(title, codeLabel, descriptionLabel, codeLength) {
        modalTitle.textContent = title;
        document.getElementById('newCodeLabel').textContent = codeLabel;
        document.getElementById('newDescriptionLabel').textContent = descriptionLabel;
        generateCodeInputs(codeLength);
        modal.style.display = 'flex';
    }

    // Open modal on button click
    document.querySelectorAll('.open-modal').forEach(button => {
        button.addEventListener('click', function () {
            const target = this.getAttribute('data-target').replace('#', '');
            const { title, codeLabel, descriptionLabel, codeLength } = modalMappings[target] || {};
            if (title && codeLabel && descriptionLabel && codeLength) {
                openModal(title, codeLabel, descriptionLabel, codeLength);
            }
        });
    });

    // Close modal
    closeModal.addEventListener('click', function () {
        modal.style.display = 'none';
    });

    // Close modal when clicking outside content
    window.addEventListener('click', function (event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });

    // Handle form submission
    modalForm.addEventListener('submit', function (event) {
        event.preventDefault();

        // Collect the code from individual inputs
        const codeChars = Array.from(codeInputContainer.querySelectorAll('.code-char')).map(input => input.value);
        const newCode = codeChars.join('');
        const newDescription = document.getElementById('newDescription').value;

        if (newCode.length !== codeChars.length) {
            alert('Please complete the code input.');
            return;
        }

        // Determine which field is being used
        const modalTitleText = modalTitle.textContent;
        let fieldType = '';

        if (modalTitleText.includes('Product')) fieldType = 'product';
        else if (modalTitleText.includes('Type')) fieldType = 'type';
        else if (modalTitleText.includes('Class')) fieldType = 'class';
        else if (modalTitleText.includes('Size')) fieldType = 'size';
        else if (modalTitleText.includes('Weight')) fieldType = 'weight';
        else if (modalTitleText.includes('Brand')) fieldType = 'brand';

        // Prepare data to send to backend
        const data = {
            fieldType: fieldType,
            newCode: newCode,
            newDescription: newDescription,
        };

        // Send data to the backend using fetch
        fetch('/add-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                modal.style.display = 'none';
                alert('Item added successfully.');
                addDropdownItem(data.data[0], data.data[2], data.data[1]);
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            alert('Error: ' + error);
        });
    });
});
