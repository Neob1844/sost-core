// SOST app — Service Worker v90: RETIREMENT (14-Nov-2026, one Explorer). The /sost-app/ interface is retired; /sost-app/ answers
// 301 to /sost-explorer.html. This worker removes the old app caches (names sost-app-*, nothing else: IndexedDB, localStorage,
// wallets and keys are never touched by a service worker), unregisters itself and opens the canonical Explorer in its windows.
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys()
    .then(function (k) { return Promise.all(k.filter(function (n) { return n.indexOf('sost-app-') === 0; }).map(function (n) { return caches.delete(n); })); })
    .then(function () { return self.registration.unregister(); })
    .then(function () { return self.clients.matchAll({ type: 'window' }); })
    .then(function (cs) { cs.forEach(function (c) { try { c.navigate('/sost-explorer.html'); } catch (x) {} }); }));
});
