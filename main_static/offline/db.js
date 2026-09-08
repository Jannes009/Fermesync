// db.js
import Dexie from 'https://unpkg.com/dexie@4.2.1/dist/dexie.mjs';

export const db = new Dexie('fermesync-db-v1');

db.version(1).stores({
  meta: 'key',

  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
});

db.version(2).stores({
  meta: 'key',
  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
  grvDrafts: 'poNumber',
  spray_projects: 'id, refreshed_at',
  spray_products: '[catalog_key+stock_id], catalog_key, stock_id, refreshed_at',
  spray_methods: 'project_id, refreshed_at',
  spray_recommendations: '[user_id+id], user_id, status, created_at',
  spray_instructions: '[user_id+id], user_id, refreshed_at',
});

db.version(3).stores({
  meta: 'key',
  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
  grvDrafts: 'poNumber',
  spray_projects: 'id, refreshed_at',
  spray_products: '[catalog_key+stock_id], catalog_key, stock_id, refreshed_at',
  spray_methods: 'project_id, refreshed_at',
  spray_recommendations: '[user_id+id], user_id, status, created_at',
  spray_instructions: null,
});

db.version(4).stores({
  meta: 'key',
  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
  grvDrafts: 'poNumber',
  spray_projects: 'id, refreshed_at',
  spray_products: '[catalog_key+stock_id], catalog_key, stock_id, refreshed_at',
  spray_methods: 'project_id, refreshed_at',
  spray_recommendations: '[user_id+id], user_id, status, created_at',
  spray_instructions: null,
});

db.version(5).stores({
  meta: 'key',
  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
  grvDrafts: 'poNumber',
  spray_projects: 'id, refreshed_at',
  spray_products: '[catalog_key+stock_id], catalog_key, stock_id, refreshed_at',
  spray_methods: 'project_id, refreshed_at',
  spray_recommendations: '[user_id+id], user_id, status, created_at',
  spray_instructions: null,
  spray_product_catalog: 'stock_id, refreshed_at',
  spray_method_catalog: 'farm_id, refreshed_at'
}).upgrade(async transaction => {
  await transaction.table('spray_products').clear();
  await transaction.table('spray_methods').clear();
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
  return await db[store].toArray();

}

export async function generateNotification(UserId, Title, Message, EntityId, action_url = null) {
    fetch('/inventory/notifications/create_notification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            UserId,
            Title,
            Message,
            EntityId,
            action_url
        })
    }).then(res => res.json())
      .then(data => {
          console.log("Notification generated", data);
      })
      .catch(err => {
          console.error("Failed to generate notification", err);
      });
}