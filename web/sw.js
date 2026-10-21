/* The Black House service worker (build __BUILD__).
   App shell: cache-first, refreshed per build. Data JSON: network-first with offline fallback. */
const SHELL = 'ct-shell-__BUILD__';
const DATA = 'ct-data';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './static/style.css?v=__BUILD__', './static/data.js?v=__BUILD__',
  './static/app.js?v=__BUILD__', './static/icon-192.png', './static/icon-512.png', './static/apple-touch-icon.png?v=__BUILD__', './static/favicon.svg?v=__BUILD__', './static/img/trump.jpg'];
self.addEventListener('install', e => { e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('ct-shell-') && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;  // fonts, photos, logos: let the browser handle them
  if (url.pathname.includes('/data/')) {
    e.respondWith(fetch(req).then(r => {
      if (r.ok) {
        const cp = r.clone();
        caches.open(DATA).then(async c => {  // keep only the newest copy of each data file
          for (const k of await c.keys()) if (new URL(k.url).pathname === url.pathname && k.url !== req.url) c.delete(k);
          c.put(req, cp);
        });
      }
      return r;
    })
      .catch(() => caches.match(req, {ignoreSearch: url.pathname.endsWith('meta.json')})));
    return;
  }
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(r => { const cp = r.clone(); caches.open(SHELL).then(c => c.put('./index.html', cp)); return r; })
      .catch(() => caches.match('./index.html')));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
});
