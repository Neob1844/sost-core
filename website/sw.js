/* SOST app — minimal service worker (pwa-20261118), scope "/".
 *
 * Purpose: give the installed SOST app (manifest /site.webmanifest, id "/") a valid, registered service worker.
 * What it deliberately does NOT do:
 *   - No "fetch" handler: it never intercepts, reads, modifies or answers any request. Every page, API call, RPC
 *     call and wallet request goes to the network exactly as without a service worker.
 *   - No Cache Storage, no IndexedDB, no localStorage: it stores nothing. Wallets, keys and seeds live in the pages'
 *     own storage, which a service worker without a fetch handler never touches.
 * On activation it only removes Cache Storage entries left by the retired /sost-app/ worker (names "sost-app-*").
 * Rollback: replace this file with a worker that calls self.registration.unregister() (see deploy log).
 */
'use strict';
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (names) {
        return Promise.all(names.filter(function (n) { return n.indexOf('sost-app-') === 0; })
                                .map(function (n) { return caches.delete(n); }));
      })
      .catch(function () {})
      .then(function () { return self.clients.claim(); })
  );
});
