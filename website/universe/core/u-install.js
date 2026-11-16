/* Install SOST (universe/install.html), owner P0 13-Nov-2026.
 * Installs the main SOST app (/site.webmanifest: id "/", name "SOST"), the same app identity as existing installs.
 *   Chrome / Edge / Samsung Internet: the browser's own install dialog (beforeinstallprompt), started by the button.
 *   iPhone / iPad: no install API exists; the iOS steps are selected and the button points to them.
 *   Already inside the installed app (display-mode standalone): says so.
 *   Otherwise: the button is disabled and the steps for this device are selected; nothing is downloaded.
 * Stores nothing (no cookie, no localStorage). */
(function () {
  'use strict';
  if (window.SOSTU && SOSTU.nav) SOSTU.nav.render(document.getElementById('nav'), 'install');   // same header as Home / Explorer
  var btn = document.getElementById('insBtn'), txt = document.getElementById('insBtnTxt'), st = document.getElementById('insStatus');
  if (!btn) return;
  var ua = navigator.userAgent || '';
  var ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var android = /Android/.test(ua);
  var firefox = /Firefox\//.test(ua) && !/Seamonkey/.test(ua);
  var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
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

  if (standalone) {
    mode = 'inapp'; setBtn('You are in the SOST app', false);
    status('<b>SOST is installed</b> and you are using it now.', true);
    return;
  }
  if (ios) {
    mode = 'steps'; setBtn('Show the 3 steps', true);
    status('On iPhone and iPad, install SOST from Safari’s <b>Share</b> menu: <b>Add to Home Screen</b>.');
  } else if (firefox && !android) {
    mode = 'steps'; setBtn('See the options', true);
    status('Firefox on a computer cannot install web apps. Open this page in <b>Edge</b> or <b>Chrome</b> to install SOST.');
  } else {
    setBtn('Install SOST', false);
    status('Checking whether this browser can install SOST…');
    // If the browser does not offer installation within a few seconds, SOST is most likely installed already
    // (browsers stop offering it) or this browser needs its own menu. Say both, honestly.
    setTimeout(function () {
      if (mode !== 'wait') return;
      mode = 'steps'; setBtn('Show the steps', true);
      status('This browser has not offered the install dialog. If SOST is already installed, open it from your apps' +
        (android ? ' or home screen' : ' (Edge and Chrome also show <b>Open in app</b> in the address bar)') + '. Otherwise use the browser menu: see the steps below.');
    }, 3500);
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); deferred = e; mode = 'ready';
    setBtn('Install SOST', true);
    status('Ready. Your browser will ask you to confirm: <b>Install</b>.');
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
