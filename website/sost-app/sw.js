// SOST — Sovereign Stock Token — Service Worker v84
const CACHE_NAME = 'sost-app-v84';
const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // ALWAYS network-first for dynamic endpoints (never cache these)
  if (url.pathname.endsWith('/rpc') ||
      url.pathname.includes('/rpc/') ||
      url.pathname.includes('/api/') ||
      url.pathname.includes('node-status') ||
      e.request.method === 'POST' ||
      url.pathname.includes('sost-explorer') ||
      url.pathname.includes('sost-wallet') ||
      url.search.includes('nocache')) {
    e.respondWith(
      fetch(e.request).catch(() =>
        caches.match(e.request).then(r => r || new Response('Offline', {status: 503}))
      )
    );
    return;
  }

  // NETWORK-FIRST for the app shell HTML. The old cache-first rule served a
  // stale index.html to installed PWAs forever, so a deploy never reached them
  // (different data vs the browser tab, DTD stuck at an old value). Now the app
  // always loads the latest HTML when online and falls back to cache offline.
  if (e.request.mode === 'navigate' ||
      url.pathname.endsWith('/') ||
      url.pathname.endsWith('/index.html')) {
    e.respondWith(
      fetch(e.request).then(resp => {
        if (resp && resp.ok) {
          const cl = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(e.request, cl));
        }
        return resp;
      }).catch(() =>
        caches.match(e.request).then(r => r || caches.match('./index.html'))
          .then(r => r || new Response('Offline', {status: 503}))
      )
    );
    return;
  }

  // Cache-first for truly static assets (icons, manifest).
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
      if (resp.ok) {
        const cl = resp.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, cl));
      }
      return resp;
    }).catch(() => new Response('Offline', {status: 503})))
  );
});
