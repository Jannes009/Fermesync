document.addEventListener("DOMContentLoaded", () => {

    document.getElementById("search-button").addEventListener("click", fetch_delivery_note_sales);
    // Function to toggle all descendants
    function toggleDescendants(parentId, isChecked) {
        const descendantCheckboxes = document.querySelectorAll(`input[type='checkbox'][data-id^="${parentId}-"]`);
        descendantCheckboxes.forEach(descendant => {
            descendant.checked = isChecked;
            descendant.indeterminate = false; // Ensure descendants are not indeterminate
        });
    }

    function updateAncestors(childId) {
        const levels = childId.split("-");

    
        while (levels.length > 1) {
            levels.pop(); // Remove the last level to move up the hierarchy
            const ancestorId = levels.join("-");
            const ancestorCheckbox = document.querySelector(`input[type='checkbox'][data-id="${ancestorId}"]`);
            const siblingCheckboxes = document.querySelectorAll(`input[type='checkbox'][data-id^="${ancestorId}-"]:not([data-id="${ancestorId}"])`);
    
            // Debugging current ancestor and siblings
            console.log("Ancestor ID:", ancestorId);
            console.log("Ancestor Checkbox:", ancestorCheckbox);
            console.log("Sibling Checkboxes:", siblingCheckboxes);
    
            if (siblingCheckboxes.length === 0) {
                console.warn(`No sibling checkboxes found for ancestor ID: ${ancestorId}`);
                continue;
            }
    
            const allChecked = Array.from(siblingCheckboxes).every(cb => cb.checked);
            const anyChecked = Array.from(siblingCheckboxes).some(cb => cb.checked);
    
            if (ancestorCheckbox) {
                ancestorCheckbox.checked = allChecked;
                ancestorCheckbox.indeterminate = !allChecked && anyChecked;
    
                // Debugging state updates
                console.log(`Updated Ancestor ${ancestorId}: Checked = ${allChecked}, Indeterminate = ${ancestorCheckbox.indeterminate}`);
            } else {
                console.warn(`Ancestor checkbox not found for ID: ${ancestorId}`);
            }
        }
    }
    

    // Inline function for handling checkbox change
    window.handleCheckboxChange = function(event) {
        const checkbox = event.target;
        const id = checkbox.getAttribute("data-id");
        const isChecked = checkbox.checked;

        console.log("Checkbox ID:", id, "Checked:", isChecked);

        // Update descendants
        toggleDescendants(id, isChecked);

        // Update ancestors
        updateAncestors(id);

        // Update the total amount
        updateTotal();
    };

    

});
