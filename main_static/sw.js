
const IS_DEV = false;

const CACHE_NAME = IS_DEV
  ? 'fermesync-dev-v1'          // never rely on versioning
  : 'fermesync-v1';          // bump ONLY on prod deploys

// ------------------
// Static app shell
// ------------------
const SHELL = [
  '/',
  '/main_static/manifest.json',
  '/main_static/icons/icon-192.png',
  '/main_static/icons/icon-512.png',
  '/main_static/color-template.css',

  // JS modules
  '/main_static/offline/db.js',

  // Rendered pages (HTML)
  '/main_static/offline.html',
  // '/inventory/',
  // '/inventory/ibt/popup',
  // '/inventory/suggested-order/popup',
  // '/inventory/static/css/stock_adjustment.css',
  // '/inventory/static/stock_adjustment_ui.js',
  //'/inventory/SDK/stock_issue_wizard',
  //'/inventory/SDK/stock_issue_summary',
];

// ------------------
// INSTALL
// ------------------
self.addEventListener("install", event => {

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(SHELL))
    );

    self.skipWaiting();

});

// ------------------
// ACTIVATE
// ------------------
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    )
  );

  self.clients.claim();
});

// ------------------
// FETCH
// ------------------
self.addEventListener('fetch', event => {
  const req = event.request;

  // ignore non-GET requests
  if (req.method !== 'GET') return;
  // ignore external requests
  if (!req.url.startsWith(self.location.origin)) return;

  // PROD: cache-first for shell
  event.respondWith(networkFirst(req));
});

// -------------------------
// NETWORK FIRST
// -------------------------

async function networkFirst(request) {

    const cache = await caches.open(CACHE_NAME);

    try {

        const response = await fetch(request);

        // Only cache successful responses.
        if (response.ok) {
            cache.put(request, response.clone());
        }

        return response;

    }
    catch {

        // Offline (or network failure)
        const cached = await cache.match(request);
        if (cached) {
            return cached;
        }
        // If the browser was trying to load an HTML page,
        // show the offline page.
        if (request.mode === "navigate") {
            const offline = await cache.match("/main_static/offline.html");
            if (offline)
                return offline;
        }
        // Otherwise return a normal offline response.
        return new Response(
              JSON.stringify({
                success: false,
                message: "You are offline. Please check your internet connection and try again."
              }),
              {
                status: 503,
                headers: { "Content-Type": "application/json" }
              }
            );
    }
}