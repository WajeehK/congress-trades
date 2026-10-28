/* The Insider House service worker (build __BUILD__).
   App shell: cache-first, refreshed per build. Data JSON: network-first with offline fallback. */
const SHELL = 'ct-shell-__BUILD__';
const DATA = 'ct-data';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './static/style.css?v=__BUILD__', './static/search.js?v=__BUILD__', './static/data.js?v=__BUILD__',
  './static/app.js?v=__BUILD__', './static/icon-192.png', './static/icon-512.png', './static/apple-touch-icon.png?v=__BUILD__', './static/favicon.svg?v=__BUILD__', './static/img/trump.jpg', './static/img/people/photos.js?v=__BUILD__', './static/logos/logos.js?v=__BUILD__', './static/badge-96.png'];
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

/* native Web Push (payload from webpush.py: {title, body, url, tag}) */
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = {body: e.data ? e.data.text() : ''}; }
  // tell open windows too, so a visible app can refresh its data right away
  self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(cs => cs.forEach(c => c.postMessage({type: 'push', title: d.title || '', url: d.url || ''})));
  e.waitUntil(self.registration.showNotification(d.title || 'The Insider House', {
    body: d.body || 'New trades disclosed', icon: './static/icon-192.png', badge: './static/badge-96.png',
    tag: d.tag || undefined, renotify: !!d.tag, data: {url: d.url || self.registration.scope}}));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(async cs => {
    for (const c of cs) {
      if (c.url.startsWith(self.registration.scope)) {
        try { await c.focus(); if (c.url !== url) await c.navigate(url); return; } catch (_) {}
      }
    }
    return self.clients.openWindow(url);
  }));
});
