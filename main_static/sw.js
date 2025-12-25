const IS_DEV = true;

const CACHE_NAME = IS_DEV
  ? 'fermesync-dev'          // never rely on versioning
  : 'fermesync-v1';          // bump ONLY on prod deploys

// ------------------
// Static app shell
// ------------------
const SHELL = [
  '/',
  '/main_static/manifest.json',
  '/main_static/icons/icon-192.png',
  '/main_static/icons/icon-512.png',
  '/inventory/static/color-template.css',

  // JS modules
  '/main_static/offline/db.js',
  '/inventory/static/stock_issue/offline.js',
  '/inventory/static/stock_issue/stock_issue_wizard.js',
  '/inventory/static/stock_issue/stock_issue_list.js',
  '/inventory/static/stock_adjustment.js',

  // Rendered pages (HTML)
  '/inventory/dashboard',
  '/inventory/SDK/stock_issue',
];

// ------------------
// INSTALL
// ------------------
self.addEventListener('install', event => {
  if (IS_DEV) {
    self.skipWaiting();
    return;
  }

  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL))
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

  if (req.method !== 'GET') return;
  if (!req.url.startsWith(self.location.origin)) return;

  const url = new URL(req.url);
  url.search = ''; // normalize ?v=

  const pathname = url.pathname;

  const isShellRequest = SHELL.includes(pathname);
  const isApiRequest = pathname.startsWith('/inventory/');

  // ❌ Let your app handle APIs
  if (isApiRequest && !isShellRequest) {
    return;
  }

  const isImage = pathname.match(/\.(png|jpg|jpeg|svg|webp)$/);

  if (!IS_DEV && isImage) {
    event.respondWith(
      (async () => {
        const cache = await caches.open('images-v1');
        const cached = await cache.match(req);

        if (cached) {
          // Update in background
          fetch(req).then(res => {
            if (res.ok) cache.put(req, res.clone());
          });
          return cached;
        }

        const res = await fetch(req);
        if (res.ok) cache.put(req, res.clone());
        return res;
      })()
    );
    return;
  }


  // DEV: always go network-first
  if (IS_DEV) {
    event.respondWith(fetch(req));
    return;
  }

  // PROD: cache-first for shell
  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(url.toString());

      if (cached) return cached;

      const res = await fetch(req);
      if (res && res.status === 200) {
        cache.put(url.toString(), res.clone());
      }

      return res;
    })()
  );
});
