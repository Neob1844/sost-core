/* SOST Explorer — Read Only app: install panel (owner orders 12/13-Nov-2026 «Install App»).
 * The header button on sostcore.com opens /sost-app/?install=1. A browser can only install the manifest of the page it is on,
 * so the install happens here, with this app's own manifest (scope /sost-app/), never the whole site.
 *   Chrome / Edge / Samsung Internet (Windows, Android, ChromeOS, macOS): native install dialog (beforeinstallprompt).
 *   iPhone / iPad (Safari): no install API exists; step-by-step «Add to Home Screen» instructions.
 *   Already running as the installed app (display-mode standalone): says so, no install button.
 *   Other browsers (e.g. Firefox desktop): honest instructions; nothing is downloaded (no .exe / .apk is offered).
 * Stores nothing (no cookie, no localStorage, no identifier). */
(function () {
  'use strict';
  var box = document.getElementById('appInstall'); if (!box) return;
  var q = new URLSearchParams(location.search), asked = q.get('install') === '1';
  var ua = navigator.userAgent || '';
  var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
  var ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var android = /Android/.test(ua);
  var deferred = null;
  var msg = box.querySelector('.ai-msg'), btn = box.querySelector('.ai-btn'), steps = box.querySelector('.ai-steps');
  function show(text, html) { msg.textContent = text; steps.innerHTML = html || ''; box.hidden = false; }
  if (standalone) { if (asked) show('You are using the installed SOST Explorer app.'); return; }
  if (ios) {
    show('Install on iPhone / iPad (Safari):',
      '<ol><li>Tap <b>Share</b> <span aria-hidden="true">(square with an arrow)</span> in Safari.</li>' +
      '<li>Choose <b>Add to Home Screen</b>.</li><li>Tap <b>Add</b>. The SOST icon appears on your home screen.</li></ol>' +
      '<p class="ai-fine">In other iOS browsers, open this page in Safari first.</p>');
  } else {
    show(asked ? 'Install the SOST Explorer app:' : 'This explorer can be installed as an app.',
      '<p class="ai-fine">' + (android ? 'Chrome: menu <b>⋮</b> → <b>Install app</b> (or <b>Add to Home screen</b>).'
        : 'Chrome / Edge: the install icon in the address bar, or menu <b>⋮</b> → <b>Install SOST Explorer</b>. Firefox desktop cannot install web apps: use Chrome or Edge.') +
      ' If the app is already installed, open it from your apps or home screen.</p>');
    if (!asked) box.hidden = true;            // without ?install=1 the panel appears only when the browser offers installation
  }
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); deferred = e; btn.hidden = false; box.hidden = false;
    msg.textContent = 'Install the SOST Explorer app on this device:';
  });
  btn.addEventListener('click', function () {
    if (!deferred) return;
    deferred.prompt();
    deferred.userChoice.then(function (r) {
      deferred = null; btn.hidden = true;
      show(r && r.outcome === 'accepted' ? 'Installed. Open SOST Explorer from your apps or home screen.' : 'Installation cancelled. You can install it later from the browser menu.');
    });
  });
  window.addEventListener('appinstalled', function () { btn.hidden = true; show('Installed. Open SOST Explorer from your apps or home screen.'); });
})();
