// db.js
import Dexie from 'https://unpkg.com/dexie@4.2.1/dist/dexie.mjs';

export const db = new Dexie('fermesync-db-v13');

db.version(14).stores({
  meta: 'key',
  warehouses: 'id',
  projects: 'id',
  products: '[product_link+whse], product_link, whse, qty_in_whse',

  // OFFLINE data (client-generated)
  offlineIssues: '++local_id, client_issue_id, status',
  offlineIssueLines: '++id, client_issue_id, product_link', // Simple structure

  offlineReturns: '++local_id, client_issue_id, status',
  
  // SERVER data (downloaded)
  serverIssues: 'IssueId',
  serverIssueLines: 'line_id, header_id, product_link', // Server structure
  
  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',

  grvDrafts: 'poNumber, updatedAt'
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