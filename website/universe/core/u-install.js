/* Install SOST (universe/install.html), owner P0 13-Nov-2026; detection and messages revised pwa-20261118.
 * Installs the main SOST app (/site.webmanifest: id "/", name "SOST"), the same app identity as existing installs.
 *   Chrome / Edge / Brave / Opera / Samsung Internet: the browser's own install dialog (beforeinstallprompt), started by the button.
 *   Already installed: detected inside the app (display-mode) and, where the browser supports it, from a normal tab
 *     (navigator.getInstalledRelatedApps + manifest related_applications). Says how to open it.
 *   iPhone / iPad, Safari on macOS, Firefox on a computer: no install API; the right steps are selected.
 *   Chromium without the dialog after a while: most likely already installed (also an older install), private window,
 *     or blocked by policy. Says so and shows how to check (edge://apps, chrome://apps).
 * Stores nothing (no cookie, no localStorage). The service worker (/sw.js) is registered by /sw-register.js. */
(function () {
  'use strict';
  if (window.SOSTU && SOSTU.nav) SOSTU.nav.render(document.getElementById('nav'), 'install');   // same header as Home / Explorer
  var btn = document.getElementById('insBtn'), txt = document.getElementById('insBtnTxt'), st = document.getElementById('insStatus');
  if (!btn) return;
  var ua = navigator.userAgent || '';
  var ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var android = /Android/.test(ua);
  var firefox = /Firefox\/|FxiOS\//.test(ua) && !/Seamonkey/.test(ua);
  var edge = /Edg(e|A|iOS)?\//.test(ua);
  var chromium = !!window.chrome || /Chrome\/|CriOS\//.test(ua);
  var macSafari = !ios && /Macintosh/.test(ua) && /Safari\//.test(ua) && !chromium && !firefox;
  var appsUrl = edge ? 'edge://apps' : 'chrome://apps';
  var inApp = false;
  ['standalone', 'minimal-ui', 'window-controls-overlay', 'fullscreen'].forEach(function (m) {
    if (window.matchMedia && matchMedia('(display-mode: ' + m + ')').matches) inApp = true;
  });
  if (navigator.standalone === true) inApp = true;
  var deferred = null, mode = 'wait';

  // ---- device tabs (WAI-ARIA tabs: arrows, Home, End)
  var tabs = [].slice.call(document.querySelectorAll('.ins-tabs [role="tab"]'));
  function select(id, focus) {
    tabs.forEach(function (t) {
      var on = t.id === id; t.setAttribute('aria-selected', on ? 'true' : 'false'); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
      if (on && focus) t.focus();
    });
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { select(t.id); });
    t.addEventListener('keydown', function (e) {
      var k = e.key, j = k === 'ArrowRight' ? i + 1 : k === 'ArrowLeft' ? i - 1 : k === 'Home' ? 0 : k === 'End' ? tabs.length - 1 : null;
      if (j === null) return; e.preventDefault(); select(tabs[(j + tabs.length) % tabs.length].id, true);
    });
  });
  var mine = ios ? 't-ios' : android ? (firefox ? 't-oth' : 't-and') : firefox ? 't-oth' : 't-desk';
  select(mine);

  function status(html, ok) { st.innerHTML = html; st.className = 'ins-status' + (ok ? ' ok' : ''); }
  function setBtn(label, enabled) { txt.textContent = label; btn.setAttribute('aria-disabled', enabled ? 'false' : 'true'); }
  function goSteps() { var h = document.getElementById('how'); if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' }); var t = document.getElementById(mine); if (t) t.focus({ preventScroll: true }); }
  function installedMsg() {
    mode = 'installed'; setBtn('Already installed', false);
    status('<b>SOST is already installed on this device.</b> Open it from ' +
      (android ? 'your home screen or app drawer.' : 'the Start menu, the taskbar or your apps' +
        (chromium ? ' (or the <b>Open in app</b> icon in the address bar).' : '.')), true);
  }

  if (inApp) {
    mode = 'inapp'; setBtn('You are in the SOST app', false);
    status('<b>SOST is installed</b> and you are using it now.', true);
    return;
  }
  if (ios) {
    mode = 'steps'; setBtn('Show the 3 steps', true);
    status('On iPhone and iPad, install SOST from the <b>Share</b> menu: <b>Add to Home Screen</b>.');
  } else if (firefox && !android) {
    mode = 'steps'; setBtn('See the options', true);
    status('Firefox on a computer cannot install web apps. Open <b>sostcore.com/install</b> in <b>Edge</b> or <b>Chrome</b> to install SOST.');
  } else if (macSafari) {
    mode = 'steps'; setBtn('Show the steps', true);
    status('Safari on a Mac installs SOST from its menu: <b>File</b> → <b>Add to Dock</b>.');
  } else {
    setBtn('Install SOST', false);
    status('Checking whether this browser can install SOST…');
    // Chromium browsers stop offering installation once the app is installed, and never offer it in a private
    // window or when an administrator blocks it. If no dialog has been offered after a while, say all of that.
    setTimeout(function () {
      if (mode !== 'wait') return;
      mode = 'steps'; setBtn('Show the steps', true);
      status('This browser has not offered installation. <b>SOST may already be installed</b> (also an older version): ' +
        (android ? 'look for it on your home screen.' : 'open <b>' + appsUrl + '</b> in the address bar to see it, open it or remove an old copy, then reload this page.') +
        ' A private (InPrivate / Incognito) window cannot install apps. Otherwise use the browser menu: see the steps below.');
    }, 6000);
  }

  // Already installed? (Chromium: same-origin web app listed in the manifest's related_applications)
  if (navigator.getInstalledRelatedApps) {
    navigator.getInstalledRelatedApps().then(function (apps) {
      if (apps && apps.length && mode !== 'ready' && mode !== 'done') installedMsg();
    }).catch(function () {});
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); deferred = e; mode = 'ready';
    setBtn('Install SOST', true);
    status('Ready. Press <b>Install SOST</b>; your browser will ask you to confirm with <b>Install</b>.');
  });
  btn.addEventListener('click', function () {
    if (btn.getAttribute('aria-disabled') === 'true') return;
    if (mode === 'ready' && deferred) {
      var d = deferred; deferred = null;
      d.prompt();
      d.userChoice.then(function (r) {
        if (r && r.outcome === 'accepted') { mode = 'done'; setBtn('Installed', false); status('<b>Installed.</b> SOST opens in its own window. You will find it with your apps' + (android ? ' and on your home screen.' : ', in the Start menu or Launchpad.'), true); }
        else { mode = 'steps'; setBtn('Show the steps', true); status('Installation cancelled. You can install SOST at any time from here or from the browser menu.'); }
      });
      return;
    }
    goSteps();
  });
  window.addEventListener('appinstalled', function () {
    mode = 'done'; deferred = null; setBtn('Installed', false);
    status('<b>Installed.</b> SOST opens in its own window. You will find it with your apps.', true);
  });
})();
