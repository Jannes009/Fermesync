
async function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const preWarehouse = urlParams.get("warehouse");
    const preCategory = urlParams.get("category");

    const warehousesLoaded = await loadWarehouses();
    if (warehousesLoaded && preWarehouse) {
        $('#warehouse-select').val(preWarehouse).trigger('change.select2');
        await onWarehouseChanged();

        if (preCategory) {
            $('#category-select').val(preCategory).trigger('change.select2');
            selectedCategory = preCategory;
            updateStep1NextButton();
        }
    }

    if (sessionId) {
        loadProductsForSession(sessionId);
        showStep(2);
    }

    document.getElementById("step-1-next").addEventListener("click", onStartCounting);
    document.getElementById("step-2-next").addEventListener("click", onCompleteCount);

    // Command bar setup
    setupCommandBar();
}