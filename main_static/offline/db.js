// db.js
import Dexie from 'https://unpkg.com/dexie@4.2.1/dist/dexie.mjs';

export const db = new Dexie('fermesync-db-v1');

db.version(1).stores({
  meta: 'key',

  outbox: '++id, created_at, retry_count',
  notifications: 'id, created_at, read',
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