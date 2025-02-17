$(document).ready(function () {
    
    $(document).on('keydown', 'input[name="ZZEstimatedPrice[]"]', function (e) {
        if (e.key === 'Tab' || e.keyCode === 9) {
            e.preventDefault();  // Prevent default tabbing behavior
    
            let currentRow = $(this).closest('tr');
            let nextInput = currentRow.next().find('input[name="ZZEstimatedPrice[]"]');
    
            if (nextInput.length === 0) {
                let newRow = addCleanLine();  // Add new row and get reference
                nextInput = newRow.find('input[name="ZZEstimatedPrice[]"]'); // Find new input
            }
    
            if (nextInput.length) {
                nextInput.focus();  // Focus the next quantity input field
            }
        }
    });
    
    $(document).on('keydown', 'input[name="ZZQuantityBags[]"]', function (e) {
        if (e.key === 'Tab' || e.keyCode === 9) {
            e.preventDefault();  // Prevent default tabbing behavior
    
            let currentRow = $(this).closest('tr');
            let nextInput = currentRow.next().find('input[name="ZZQuantityBags[]"]');
    
            if (nextInput.length === 0) {
                let newRow = addCleanLine();  // Add new row and get reference
                nextInput = newRow.find('input[name="ZZQuantityBags[]"]'); // Find new input
            }
    
            if (nextInput.length) {
                nextInput.focus();  // Focus the next quantity input field
            }
        }
    });

    $(document).on('keydown', 'input[name="ZZComments[]"]', function (e) {
        if (e.key === 'Tab' || e.keyCode === 9) {
            e.preventDefault();  // Prevent default tabbing behavior
    
            let currentRow = $(this).closest('tr');
            let nextInput = currentRow.next().find('input[name="ZZComments[]"]');
    
            if (nextInput.length === 0) {
                let newRow = addCleanLine();  // Add new row and get reference
                nextInput = newRow.find('input[name="ZZComments[]"]'); // Find new input
            }
    
            if (nextInput.length) {
                nextInput.focus();  // Focus the next quantity input field
            }
        }
    });
    
    
});