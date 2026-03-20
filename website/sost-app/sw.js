// SOST Protocol — Service Worker
const CACHE_NAME = 'sost-app-v8';
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
  // Network-first for RPC and iframe pages
  if (url.pathname.endsWith('/rpc') || e.request.method === 'POST' ||
      url.pathname.includes('sost-explorer') || url.pathname.includes('sost-wallet')) {
    e.respondWith(fetch(e.request).catch(() =>
      caches.match(e.request).then(r => r || new Response('Offline', {status: 503}))
    ));
    return;
  }
  // Cache-first for app shell
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
    if (resp.ok) { const cl = resp.clone(); caches.open(CACHE_NAME).then(c => c.put(e.request, cl)); }
    return resp;
  }).catch(() => new Response('Offline', {status: 503}))));
});
