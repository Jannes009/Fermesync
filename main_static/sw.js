const PRECACHE = 'app-shell-v1';
const RUNTIME = 'runtime-cache-v1';
const PRECACHE_URLS = [
  '/', // if you want index cached
  '/static/css/main.css?v={{ filemtime("main", "css/main.css") }}',
  '/static/js/main.js?v={{ filemtime("main", "js/main.js") }}',
  '/main_static/icons/icon-192.png',
  '/main_static/icons/icon-512.png'
];

// install: precache
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PRECACHE).then(cache => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// activate: cleanup
self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
  const currentCaches = [PRECACHE, RUNTIME];
  event.waitUntil(
    caches.keys().then(cacheNames =>
      Promise.all(
        cacheNames
          .filter(name => !currentCaches.includes(name))
          .map(name => caches.delete(name))
      )
    ).then(() => clients.claim())
  );
});

// helper: network-first for API GETs, stale-while-revalidate for shell assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  // API requests (network-first)
  if (url.pathname.startsWith('/api/')) {
    if (event.request.method === 'GET') {
      event.respondWith(
        fetch(event.request)
          .then(response => {
            // clone+cache
            const resClone = response.clone();
            caches.open(RUNTIME).then(cache => cache.put(event.request, resClone));
            return response;
          })
          .catch(() => caches.match(event.request))
      );
    } else {
      // non-GET (POST/PUT) should pass through; they'll be handled by client queue
      return;
    }
    return;
  }

  // Navigation requests -> serve App Shell (cache-first then network fallback)
  if (event.request.mode === 'navigate' || (event.request.method === 'GET' && event.request.headers.get('accept')?.includes('text/html'))) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        const networkFetch = fetch(event.request).then(networkResponse => {
          // update cache in background
          const clone = networkResponse.clone();
          caches.open(RUNTIME).then(cache => cache.put(event.request, clone));
          return networkResponse;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
    return;
  }

  // Static assets - stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then(cached => {
      const fetchPromise = fetch(event.request).then(networkResponse => {
        caches.open(RUNTIME).then(cache => cache.put(event.request, networkResponse.clone()));
        return networkResponse;
      }).catch(() => {}); // ignore network errors
      return cached || fetchPromise;
    })
  );
});

// Background sync event (if registered)
self.addEventListener('sync', event => {
  if (event.tag === 'sync-pending-ops') {
    event.waitUntil(runSync());
  }
});

// Basic runSync - ask clients to trigger the sync routine (the heavy work is in client)
async function runSync() {
  // Option: the service worker can perform sync itself via IndexedDB access (complex)
  // Simpler: message clients to flush the queue from the main thread (navigator.serviceWorker.ready + postMessage)
  const allClients = await clients.matchAll({ includeUncontrolled: true });
  for (const client of allClients) {
    client.postMessage({ type: 'FLUSH_QUEUE' });
  }
}
