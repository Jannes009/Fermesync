
function validateAllUdfs() {
  const requiredFields = document.querySelectorAll("[data-required='1']");

  for (const field of requiredFields) {
    if (!field.value || field.value.trim() === "") {
      const udfPage = field.closest(".udf-page");
      if (!udfPage) continue;

      // Switch to correct page
      const page = udfPage.dataset.page;
      showUdfPage(page);

      // Scroll nicely
      setTimeout(() => {
        field.scrollIntoView({ behavior: "smooth", block: "center" });
        field.focus();
        field.classList.add("udf-error");
      }, 50);

      return false;
    }
  }

  return true;
}

// remove error class on input
document.addEventListener("input", e => {
  if (e.target.classList.contains("udf-error")) {
    e.target.classList.remove("udf-error");
  }
});

function validateLines() {
  const rows = document.querySelectorAll("#po-lines tbody tr");

  if (!rows.length) {
    alert("At least one line is required");
    return false;
  }

  for (const row of rows) {
    const key = row.dataset.index;
    if (!key) continue;

    const item = row.querySelector(
      `select[name="lines[${key}][product_id]"]`
    );
    const qty = row.querySelector(
      `input[name="lines[${key}][qty]"]`
    );
    const price = row.querySelector(
      `input[name="lines[${key}][price]"]`
    );

    const itemVal = $(item).val();
    const qtyVal = parseFloat(qty?.value);
    const priceVal = parseFloat(price?.value);
    console.log({itemVal, qtyVal, priceVal, price})
    if (!itemVal || !qtyVal || qtyVal <= 0 || priceVal < 0) {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      item?.focus();

      console.log(!itemVal, !qtyVal, qtyVal <= 0,  priceVal < 0)
      alert("All lines must have an item, price and quantity");
      return false;
    }
  }

  return true;
}

function warnZeroPrices() {
  const rows = document.querySelectorAll("#po-lines tbody tr");
  const zeroPriceRows = [];

  for (const row of rows) {
    const key = row.dataset.index;
    if (!key) continue;

    const price = row.querySelector(
      `input[name="lines[${key}][price]"]`
    );

    const priceVal = parseFloat(price?.value);

    if (priceVal === 0) {
      zeroPriceRows.push({ row, price });
    }
  }

  if (zeroPriceRows.length > 0) {
    // Scroll to the first zero-price row for visibility
    zeroPriceRows[0].row.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
    zeroPriceRows[0].price?.focus();

    const proceed = confirm(
      `⚠ Warning\n\n` +
      `${zeroPriceRows.length} line(s) have a price of 0.\n` +
      `Do you want to continue anyway?`
    );

    return proceed; // true = continue, false = cancel
  }

  return true; // no zero prices found
}
