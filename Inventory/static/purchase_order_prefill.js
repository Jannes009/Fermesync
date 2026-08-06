(function () {
    function waitFor(conditionFn, interval = 100, timeout = 10000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            const iv = setInterval(() => {
                try {
                    if (conditionFn()) {
                        clearInterval(iv);
                        resolve();
                    } else if (Date.now() - start > timeout) {
                        clearInterval(iv);
                        reject(new Error('timeout'));
                    }
                } catch (err) {
                    clearInterval(iv);
                    reject(err);
                }
            }, interval);
        });
    }

    function triggerSelect2Select($el) {
        // Force the select2:select event that the main script listens to
        const data = $el.select2('data')[0];
        if (data) {
            $el.trigger({
                type: 'select2:select',
                params: { data }
            });
        }
    }

    async function applyPrefill(prefill) {
        if (!prefill) return;

        const supplierId = prefill.supplier_id || '';
        const warehouseId = prefill.warehouse_id || '';
        const lines = Array.isArray(prefill.lines) ? prefill.lines : [];

        try {
            // Wait until Select2 is ready on both fields
            await waitFor(() =>
                window.jQuery &&
                window.jQuery('#supplier-select').data('select2') &&
                window.jQuery('#warehouse-select').data('select2')
            );

            const $supplier = window.jQuery('#supplier-select');
            const $warehouse = window.jQuery('#warehouse-select');

            // --- Supplier ---
            if (supplierId) {
                $supplier.val(String(supplierId)).trigger('change');
                triggerSelect2Select($supplier);
            }

            // Small pause so the first (incomplete) loadProducts finishes
            await new Promise(r => setTimeout(r, 250));

            // --- Warehouse ---
            if (warehouseId) {
                $warehouse.val(String(warehouseId)).trigger('change');
                triggerSelect2Select($warehouse);
            }

            // Wait until products have loaded and the Add-line button is enabled
            await waitFor(() => {
                const btn = document.getElementById('add-line-btn');
                return btn && !btn.disabled;
            }, 100, 12000);

            // Extra safety: wait until at least one item select has real options
            await waitFor(() => {
                const firstItem = document.querySelector('#lines-body .line-item-select');
                return firstItem && firstItem.options && firstItem.options.length > 1;
            }, 100, 8000).catch(() => {});

            // Remove the empty line that the main script added on DOMContentLoaded
            document.querySelectorAll('#lines-body .line-row').forEach(r => r.remove());
            console.log(lines)
            // --- Create and fill each line ---
            for (const l of lines) {
                const addBtn = document.getElementById('add-line-btn');
                if (!addBtn || addBtn.disabled) break;

                addBtn.click();

                // Wait for the new row to appear and be initialised
                await waitFor(() => {
                    const rows = document.querySelectorAll('#lines-body .line-row');
                    return rows.length > 0 && rows[rows.length - 1].querySelector('.line-item-select');
                }, 80, 4000);

                const row = document.querySelector('#lines-body .line-row:last-child');
                if (!row) continue;

                const $item = window.jQuery(row).find('.line-item-select');
                const unitSelectEl = row.querySelector('.line-unit-select');

                // Set item (StockLink)
                if ($item.length && l.product_id != null) {
                    $item.val(String(l.product_id)).trigger('change');
                    triggerSelect2Select($item);   // this starts the units fetch
                }

                // Wait for units to be populated by the item's onSelect handler
                if (unitSelectEl) {
                    await waitFor(
                        () => unitSelectEl.options && unitSelectEl.options.length > 1,
                        80,
                        6000
                    ).catch(() => {});

                    if (l.unit_id != null) {
                        const $unit = window.jQuery(unitSelectEl);
                        $unit.val(String(l.unit_id)).trigger('change');
                        // optional: also fire select2:select if you ever need the unit callback
                        // triggerSelect2Select($unit);
                    }
                }

                // Qty & price (plain inputs)
                const qtyInput = row.querySelector('.line-qty');
                const priceInput = row.querySelector('.line-price');
                if (qtyInput && l.qty != null) qtyInput.value = l.qty;
                if (priceInput && l.price != null) priceInput.value = Number(l.price).toFixed(2);

                // Trigger totals recalculation
                const ev = new Event('input', { bubbles: true });
                qtyInput && qtyInput.dispatchEvent(ev);
                priceInput && priceInput.dispatchEvent(ev);

                // Small breathing room before the next line
                await new Promise(r => setTimeout(r, 120));
            }
        } catch (err) {
            console.warn('Prefill failed:', err.message || err);
        }
    }

    function tryApplyFromUrl() {
        try {
            const params = new URLSearchParams(window.location.search);
            const p = params.get('prefill');
            if (!p) return;

            let prefill = null;
            try {
                prefill = JSON.parse(decodeURIComponent(p));
            } catch (e) {
                try {
                    prefill = JSON.parse(p);
                } catch (e2) {
                    prefill = null;
                }
            }
            if (!prefill) return;

            // Give the main script time to finish its own DOMContentLoaded work
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(() => applyPrefill(prefill), 400);
            });
        } catch (e) {
            /* noop */
        }
    }

    tryApplyFromUrl();
})();