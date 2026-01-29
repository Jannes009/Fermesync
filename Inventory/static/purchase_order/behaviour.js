
// -------------------------
// UDF Page Switching
// -------------------------
function showUdfPage(page) {
  // Hide ALL pages
  document.querySelectorAll(".udf-page").forEach(p => {
    p.style.display = "none";
  });

  // Show selected page
  const el = document.getElementById("udf-page-" + page);
  if (el) {
    el.style.display = "block";
  }

  // Tabs UI
  document.querySelectorAll(".udf-tab").forEach(t => t.classList.remove("active"));
  const activeTab = document.querySelector(`.udf-tab[onclick*="${page}"]`);
  if (activeTab) activeTab.classList.add("active");
}

async function initiateWarehouseAndUOM(product_link, tr, pricePopulated = false) {

  const uomSelect = tr.querySelector(".uom-select");
  const warehouseSelect = tr.querySelector(".warehouse-select");

  // Reset
  uomSelect.innerHTML = `<option value="" disabled selected>Select UOM</option>`;
  warehouseSelect.innerHTML = `<option value="" disabled selected>Select Warehouse</option>`;

  if ($(uomSelect).data('select2')) $(uomSelect).select2('destroy');
  if ($(warehouseSelect).data('select2')) $(warehouseSelect).select2('destroy');

  const res = await fetch(
    `/inventory/fetch_item_uom_warehouse?product_link=${encodeURIComponent(product_link)}`
  );

  const data = await res.json();

    /* -------------------- WAREHOUSE -------------------- */
  if (data.WhseItem === 1) {
    Warehouses.forEach(w => {
      warehouseSelect.insertAdjacentHTML(
        "beforeend",
        `<option value="${w.id}">${w.name}</option>`
      );
    });

    warehouseSelect.readonly = false;
    $(warehouseSelect).select2({ width: '100%' });
  }

  /* -------------------- UOM -------------------- */
  if (data.bUOMItem === 1 && data.uoms.length) {
    data.uoms.forEach(u => {
      uomSelect.insertAdjacentHTML(
        "beforeend",
        `<option value="${u.id}">${u.code}</option>`
      );
    });

    uomSelect.disabled = false;
    warehouseSelect.disabled = false;

    // Default Purchase UOM
    if (data.PurchaseUnitId) {
      uomSelect.value = data.PurchaseUnitId;
    }

    $(uomSelect).select2({ width: '100%' });

    const selectedUomId = uomSelect.value;
    const selectedSupplier = document.getElementById("po-form").supplier.value;

    // don't default price when form is being populated
    if (!pricePopulated) await fetchLastInvoicePrice(product_link, selectedSupplier, selectedUomId, tr);
    $(uomSelect).change(async () => {
      if (tr.dataset.settingUom) return;
      const selectedUomId = uomSelect.value;
      const selectedSupplier = document.getElementById("po-form").supplier.value;
      await fetchLastInvoicePrice(product_link, selectedSupplier, selectedUomId, tr);
    });
  } else {
    uomSelect.disabled = true;
    const selectedSupplier = document.getElementById("po-form").supplier.value;

    // don't default price when form is being populated
    if (!pricePopulated) await fetchLastInvoicePrice(product_link, selectedSupplier, uom = 0,  tr);
  }
}

async function fetchLastInvoicePrice(productLink, supplier, uomId, tr) {
  if (!supplier || !productLink || !uomId) {
    console.warn("fetchLastInvoicePrice: missing parameters");
    return null;
  }

  try {
    const response = await fetch("/inventory/po/last_invoice_price", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({
        supplier: supplier,
        product_link: productLink,
        uom_id: uomId
      })
    });
    const priceInput = tr.querySelector(".line-price-input");
    if (!response.ok) {
      priceInput.value = "";
      // 404 = no price found is not a hard error in this case
      if (response.status === 404) return null;

      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || "Failed to fetch last invoice price");
    }

    const data = await response.json();

    if (!data.success) return null;
   
    priceInput.value = data.price.toFixed(2);
  } catch (err) {
    console.error("fetchLastInvoicePrice error:", err);
    return null;
  }
}

function removeLine(btn) {
  btn.closest("tr").remove();
}
