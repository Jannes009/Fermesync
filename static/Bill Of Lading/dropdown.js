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

    const UnitCode = document.querySelector('select[name="ZZProductionUnitCode"]')
    console.log(UnitCode)
    $('select[name="ZZProductionUnitCode"]').on('change', function () {
        const selectedValue = $(this).val();
    
        $('select.production-unit-select').each(function () {
            $(this).val(selectedValue).trigger('change'); // Also works for Select2
        });
    });
    
    
    
});
