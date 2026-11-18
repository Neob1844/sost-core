/* Registers the minimal SOST service worker (/sw.js, scope "/"), pwa-20261118.
 * /sw.js has no fetch handler and stores nothing: see the comment in that file. Safe to include on any page. */
(function () {
  'use strict';
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  var go = function () {
    navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).catch(function () {});
  };
  if (document.readyState === 'complete') go(); else window.addEventListener('load', go);
})();
