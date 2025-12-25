import { db, fetchWithOffline } from "/main_static/offline/db.js?v=43";

/**
 * Ensure sufficient stock for a product.
 *
 * @param {Object} params
 * @param {number|string} params.product_link
 * @param {string} params.whse
 * @param {number} params.qtyNeeded
 * @param {Function} params.onUpdated  // callback to refresh UI (dropdown, dataset)
 *
 * @returns {boolean} true if stock is sufficient or successfully adjusted
 */
export async function ensureStockAvailable({
    product_link,
    whse,
    qtyNeeded,
    onUpdated
}) {
    // Fetch current local stock
    const product = await db.products
        .where("[product_link+whse]")
        .equals([product_link, whse])
        .first();

    const available = Number(product?.qty_in_whse ?? 0);

    if (available >= qtyNeeded) {
        return true;
    }

    const shortfall = qtyNeeded - available;

    // Permission check
    const canAdjust = window.FERMESYNC?.permissions?.includes("StockAdjustment");

    if (!canAdjust) {
        await Swal.fire(
            "Insufficient Stock",
            `Available: ${available}. Required: ${qtyNeeded}.`,
            "error"
        );
        return false;
    }

    // Ask user
    const res = await Swal.fire({
        title: "Insufficient Stock",
        html: `
            <p>Available: <b>${available}</b></p>
            <p>Required: <b>${qtyNeeded}</b></p>
            <p>Add <b>${shortfall}</b> to warehouse <b>${whse}</b>?</p>
        `,
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Add Stock",
        cancelButtonText: "Cancel"
    });

    if (!res.isConfirmed) return false;
    console.log(res.isConfirmed)
    // Offline path
    if (!navigator.onLine) {
        console.log("Offline")
        await db.transaction("rw", db.products, db.outbox, async () => {
            await db.products
                .where("[product_link+whse]")
                .equals([product_link, whse])
                .modify(p => {
                    p.qty_in_whse = (p.qty_in_whse ?? 0) + shortfall;
                });

            await db.outbox.add({
                url: "/inventory/add_stock",
                method: "POST",
                body: {
                    product_link,
                    warehouse_code: whse,
                    quantity: shortfall
                },
                created_at: new Date().toISOString(),
                retry_count: 0
            });
        });

        if (onUpdated) await onUpdated();
        Swal.fire("Queued", "Stock adjustment queued for sync.", "info");
        return true;
    }
    console.log("Online submit")
    // Online path
    const resApi = await fetchWithOffline({
        url: "/inventory/add_stock",
        method: "POST",
        body: {
            product_link,
            warehouse_code: whse,
            quantity: shortfall
        }
    });

    if (!resApi?.success) {
        Swal.fire("Error", resApi?.message || "Stock adjustment failed", "error");
        return false;
    }

    const products = await fetch(`/inventory/fetch_products`)
    .then(r => r.json())
    .then(d => d.products.map(p => ({
        product_link: p.product_link,
        whse: p.WhseCode,        // 👈 REQUIRED
        qty_in_whse: p.qty_in_whse,

        product_code: p.product_code,
        product_desc: p.product_desc,

        whse_link: p.WhseLink,
        whse_name: p.WhseName,

        stocking_uom_id: p.stocking_uom_id,
        stocking_uom_code: p.stocking_uom_code,
        purchase_uom_id: p.purchase_uom_id,
        purchase_uom_code: p.purchase_uom_code,
        uom_cat_id: p.uom_cat_id
    })));
    await db.products.bulkPut(products);
    return true;
}
