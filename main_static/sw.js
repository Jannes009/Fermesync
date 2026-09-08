
const IS_DEV = true;

const CACHE_NAME = IS_DEV
  ? 'fermesync-dev-v4'          // never rely on versioning
  : 'fermesync-v2';          // bump ONLY on prod deploys

// ------------------
// Static app shell
// ------------------
const SHELL = [
  '/',
  '/main_static/manifest.json',
  '/main_static/icons/icon-192.png',
  '/main_static/icons/icon-512.png',
  '/main_static/color-template.css',
  '/static/color-template.css',
  '/static/icons/LogoIcon - Copy.svg',
  '/static/icons/HorizontalLogoAndText.svg',

  // JS modules
  '/main_static/offline/db.js',

  // Rendered pages (HTML)
  '/main_static/offline.html',
  'https://unpkg.com/dexie@4.2.1/dist/dexie.mjs',
  'https://code.jquery.com/jquery-3.7.0.min.js',
  'https://code.jquery.com/jquery-3.6.0.min.js',
  'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css',
  'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js',
  'https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.min.css',
  'https://cdn.jsdelivr.net/npm/sweetalert2@11',
  'https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js',
  // '/inventory/',
  // '/inventory/ibt/popup',
  // '/inventory/suggested-order/popup',
  // '/inventory/static/css/stock_adjustment.css',
  // '/inventory/static/stock_adjustment_ui.js',
  //'/inventory/SDK/stock_issue_wizard',
  //'/inventory/SDK/stock_issue_summary',

  // spray pages
  '/agri/spray-recommendations-summary',
  '/agri/spray-recommendation/create',
  '/agri/spray/0',
];

const STATIC_PREFIXES = [
  '/main_static/',
  '/static/',
  '/agri/static/',
];

const EXTERNAL_PREFIXES = [
  'https://unpkg.com/',
  'https://code.jquery.com/',
  'https://cdn.jsdelivr.net/',
  'https://cdnjs.cloudflare.com/'
];

// ------------------
// INSTALL
// ------------------
self.addEventListener("install", event => {

    event.waitUntil(
        caches.open(CACHE_NAME).then(async cache => {
          await Promise.all(SHELL.map(async url => {
            try {
              const response = await fetch(url, { credentials: 'same-origin' });
              if (response.ok) await cache.put(url, response);
            } catch {
              // Optional authenticated routes must not abort installation.
            }
          }));
        })
    );

    self.skipWaiting();

});

// ------------------
// ACTIVATE
// ------------------
self.addEventListener('activate', event => {
  event.waitUntil(
    Promise.all([
      caches.keys().then(keys =>
        Promise.all(
          keys
            .filter(k => k !== CACHE_NAME)
            .map(k => caches.delete(k))
        )
      ),
      caches.open(CACHE_NAME).then(async cache => {
        const requests = await cache.keys();
        await Promise.all(requests
          .filter(request => /^\/agri\/spray\/\d+$/.test(new URL(request.url).pathname) && !request.url.endsWith('/agri/spray/0'))
          .map(request => cache.delete(request)));
      })
    ])
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
  const externalDependency = EXTERNAL_PREFIXES.some(prefix => req.url.startsWith(prefix));
  if (!req.url.startsWith(self.location.origin) && !externalDependency) return;

  const url = new URL(req.url);
  const detailNavigation = req.mode === 'navigate' && /^\/agri\/spray\/\d+$/.test(url.pathname);
  if (detailNavigation) {
    event.respondWith(networkFirstDetail(req));
    return;
  }

  if (req.mode === 'navigate') {
    event.respondWith(networkFirst(req));
    return;
  }

  if (STATIC_PREFIXES.some(prefix => url.pathname.startsWith(prefix)) || externalDependency) {
    event.respondWith(cacheFirst(req));
  }
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
        const cached = await cache.match(request, { ignoreSearch: true });
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

async function networkFirstDetail(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    return await fetch(request);
  } catch {
    const shell = await cache.match('/agri/spray/0');
    if (shell) return shell;
    return new Response('Offline detail shell is not available yet.', { status: 503 });
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}