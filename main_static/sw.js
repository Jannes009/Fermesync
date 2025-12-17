const CACHE_NAME = 'fermesync-v1';
const SHELL = [
  '/',
  '/main_static/manifest.json',
  // '/main_static/color-template.css',
  '/main_static/icons/icon-192.png',
  '/main_static/icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

/* ---------- FETCH ---------- */
self.addEventListener('fetch', event => {
  const req = event.request;

  if (!req.url.startsWith(self.location.origin)) return;

  // ONLY handle GET requests
  if (req.method !== 'GET') return;

  event.respondWith(
    fetch(req)
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then(c => c.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});