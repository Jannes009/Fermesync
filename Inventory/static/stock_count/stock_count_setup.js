
function init() {
    const urlParams = new URLSearchParams(window.location.search);
    const preWarehouse = urlParams.get("warehouse");
    const preCategory = urlParams.get("category");

    loadWarehouses();
    if (preWarehouse) {
        $('#warehouse-select').val(preWarehouse).trigger('change');
    }
    if (preCategory) {
        $('#category-select').val(preCategory).trigger('change');
    }

    if (sessionId) {
        loadProductsForSession(sessionId);
        showStep(2);
    }

    document.getElementById("step-1-next").addEventListener("click", onStartCounting);
    document.getElementById("step-2-next").addEventListener("click", onCompleteCount);

    const finalizeBtn = document.getElementById("step-3-next");
    if (finalizeBtn) finalizeBtn.addEventListener("click", onFinalizeClicked);

    // Command bar setup
    setupCommandBar();
}