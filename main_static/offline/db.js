// db.js
import Dexie from 'https://unpkg.com/dexie@3.2.2/dist/dexie.mjs';

export const db = new Dexie('fermesync-db');

db.version(2).stores({
  meta: 'key',
  warehouses: 'id',
  projects: 'id',
  products: '[product_link+whse], product_link, whse',
  stockIssues: '++local_id, status, created_at',
  outbox: '++id, type, created_at',
  notifications: 'id, created_at, read'
});

/**
 * Generic offline-first fetch helper
 */
export async function fetchWithOffline({
  url,
  method = 'GET',
  body = null,
  store,
  transform = d => d,
  key = null
}) {
  if (navigator.onLine) {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : null
    });

    const data = await res.json();
    const records = transform(data);

    if (store && records) {
      await db[store].clear();
      await db[store].bulkPut(records);
    }

    return records;
  }

  // OFFLINE FALLBACK
  if (!store) throw new Error('Offline fetch requires store');
  return db[store].toArray();
}

// in db.js
export async function flushOutbox() {
    const items = await db.outbox.toArray();
    for (let item of items) {
        try {
            const res = await fetch(`/inventory/SDK/create_stock_issue`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(item.payload)
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                await db.outbox.delete(item.id); // remove from outbox
            } else {
                console.warn("Failed to flush outbox item", item, data);
            }
        } catch (err) {
            console.warn("Error flushing outbox item", item, err);
        }
    }
}
