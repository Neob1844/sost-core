/* SOST Tokenization / DEX public-access GATE + regulatory notice  (V30000)
 * ---------------------------------------------------------------------------
 * REAL functional barrier, not a CSS overlay: a capture-phase click
 * interceptor on document stops the operation handlers (including inline
 * onclick) from ever firing while public access is disabled. Action controls
 * are also set disabled, and a blocking veil covers the operation panel.
 *
 * Flags (public OFF by default; developer access allowed):
 *     DEX_PUBLIC_ENABLED          = false
 *     TOKENIZATION_PUBLIC_ENABLED = false
 * Developer unlock: ?dev=1 (persists in localStorage) or localStorage
 * sost_dev_access === '1'. Public users have neither -> blocked.
 *
 * The notice reflects the REAL state and auto-switches on chain height:
 *   height < 30000  OR not mainnet-validated ->  pre-activation copy
 *   height >= 30000 AND MAINNET_VALIDATED     ->  LIVE copy
 * MAINNET_VALIDATED stays false until #30000 has activated AND mainnet is
 * validated by hand — technical availability is never claimed early.
 *
 * Per-page config (set BEFORE this script):
 *   window.__SOST_GATE_CFG__ = {
 *     surface: 'DEX' | 'TOKENIZATION',
 *     label:   'Atomic Swap DEX',            // shown in the notice
 *     modalities: ['Tokenize','Auction','Draw','Project Funding'],  // optional
 *     actionSelectors: ['#swapCta', ...],    // controls to intercept/disable
 *     veil: '#opPanel'                        // optional element to veil
 *   };
 */
(function () {
  'use strict';
  var CFG = window.__SOST_GATE_CFG__ || {};
  // ---- flags (single source of truth) ----
  var DEX_PUBLIC_ENABLED = false;
  var TOKENIZATION_PUBLIC_ENABLED = false;
  var MAINNET_VALIDATED = false;
  var ACTIVATION_HEIGHT = 30000;

  function publicEnabled() {
    return CFG.surface === 'DEX' ? DEX_PUBLIC_ENABLED : TOKENIZATION_PUBLIC_ENABLED;
  }
  function isDeveloper() {
    try {
      if (/[?&]dev=1(&|$)/.test(location.search)) localStorage.setItem('sost_dev_access', '1');
      if (/[?&]dev=0(&|$)/.test(location.search)) localStorage.removeItem('sost_dev_access');
      return localStorage.getItem('sost_dev_access') === '1';
    } catch (e) { return false; }
  }
  function blocked() { return !publicEnabled() && !isDeveloper(); }

  function noticeLines(height) {
    var live = MAINNET_VALIDATED && height != null && height >= ACTIVATION_HEIGHT;
    return live
      ? ['LIVE AT PROTOCOL LEVEL', 'PUBLIC ACCESS RESTRICTED',
         'DEVELOPER / CONTROLLED MAINNET USE', 'PENDING REGULATORY READINESS']
      : ['IMPLEMENTED & DEVNET-VALIDATED', 'ACTIVATES AT BLOCK #30,000',
         'NOT YET LIVE ON MAINNET', 'PUBLIC ACCESS RESTRICTED',
         'DEVELOPER / CONTROLLED TESTING', 'PENDING REGULATORY READINESS'];
  }

  var ACTIONS = (CFG.actionSelectors && CFG.actionSelectors.length)
    ? CFG.actionSelectors
    : ['button[type=submit]', '.cta', '[data-gate-action]'];

  function injectStyles() {
    if (document.getElementById('sost-gate-css')) return;
    var s = document.createElement('style'); s.id = 'sost-gate-css';
    s.textContent =
      '.sost-gate-banner{position:relative;z-index:50;margin:0 auto 14px;max-width:1100px;' +
      'border:1px solid #fb010d;border-radius:12px;background:linear-gradient(180deg,rgba(40,2,4,.92),rgba(14,0,1,.95));' +
      'color:#ffd7d9;font-family:"JetBrains Mono",ui-monospace,monospace;padding:14px 18px;box-shadow:0 0 24px rgba(251,1,13,.25)}' +
      '.sost-gate-banner h4{margin:0 0 6px;font-size:13px;letter-spacing:1.5px;color:#ff5a63;text-transform:uppercase}' +
      '.sost-gate-tags{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 6px}' +
      '.sost-gate-tags span{font-size:11px;font-weight:700;letter-spacing:.5px;padding:3px 8px;border-radius:999px;' +
      'border:1px solid rgba(251,1,13,.5);background:rgba(251,1,13,.12);color:#ffb3b7;white-space:nowrap}' +
      '.sost-gate-banner .sost-gate-foot{font-size:11px;color:#c99;margin-top:6px;line-height:1.5}' +
      '.sost-gate-veil{position:absolute;inset:0;z-index:40;background:rgba(6,0,1,.35);backdrop-filter:blur(1.5px);' +
      'cursor:not-allowed;border-radius:inherit}' +
      '.sost-gate-modal{position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;' +
      'background:rgba(0,0,0,.72);backdrop-filter:blur(4px)}' +
      '.sost-gate-modal.show{display:flex}' +
      '.sost-gate-modal .box{max-width:460px;border:1px solid #fb010d;border-radius:14px;background:#120003;' +
      'color:#ffd7d9;font-family:"JetBrains Mono",ui-monospace,monospace;padding:22px 24px;box-shadow:0 0 40px rgba(251,1,13,.4)}' +
      '.sost-gate-modal h3{margin:0 0 10px;color:#ff5a63;font-size:15px;letter-spacing:1px}' +
      '.sost-gate-modal p{font-size:12.5px;line-height:1.6;color:#e9c7c9}' +
      '.sost-gate-modal button{margin-top:14px;background:#fb010d;color:#fff;border:0;border-radius:8px;padding:9px 18px;' +
      'font-weight:700;cursor:pointer;font-family:inherit}';
    document.head.appendChild(s);
  }

  function buildBanner(height) {
    var b = document.createElement('div');
    b.className = 'sost-gate-banner'; b.setAttribute('role', 'status');
    var lines = noticeLines(height);
    var devNote = isDeveloper()
      ? '<span style="border-color:#2e7;background:rgba(34,238,119,.12);color:#9f9">DEVELOPER ACCESS ACTIVE</span>'
      : '';
    b.innerHTML =
      '<h4>' + (CFG.label || 'SOST ' + (CFG.surface === 'DEX' ? 'DEX' : 'Tokenization')) + ' — access notice</h4>' +
      '<div class="sost-gate-tags">' + lines.map(function (l) { return '<span>' + l + '</span>'; }).join('') + devNote + '</div>' +
      (CFG.modalities ? '<div class="sost-gate-foot">Modalities: ' + CFG.modalities.join(' · ') + '</div>' : '') +
      '<div class="sost-gate-foot">Technical availability does not constitute regulatory authorization.' +
      (blocked() ? ' Public execution is disabled; operations are restricted to developer / controlled testing.' : '') +
      '</div>';
    return b;
  }

  function mountBanner(height) {
    var old = document.getElementById('sostGateBanner'); if (old) old.remove();
    var b = buildBanner(height); b.id = 'sostGateBanner';
    var host = (CFG.bannerHost && document.querySelector(CFG.bannerHost)) || document.body;
    host.insertBefore(b, host.firstChild);
  }

  function veilPanel() {
    if (!blocked() || !CFG.veil) return;
    var p = document.querySelector(CFG.veil); if (!p) return;
    if (getComputedStyle(p).position === 'static') p.style.position = 'relative';
    if (!p.querySelector('.sost-gate-veil')) {
      var v = document.createElement('div'); v.className = 'sost-gate-veil';
      v.addEventListener('click', function (e) { e.preventDefault(); e.stopImmediatePropagation(); showModal(); }, true);
      p.appendChild(v);
    }
  }

  function disableActions() {
    if (!blocked()) return;
    ACTIONS.forEach(function (sel) {
      document.querySelectorAll(sel).forEach(function (el) {
        el.setAttribute('data-sost-gated', '1');
        // NOT el.disabled = true: a disabled control never dispatches click, so the
        // capture interceptor (the real block + the explanatory modal) would never
        // run. aria-disabled + a class convey the state; the interceptor enforces it.
        el.setAttribute('aria-disabled', 'true');
        el.classList.add('sost-gated-btn');
        el.style.opacity = '0.55'; el.style.cursor = 'not-allowed';
      });
    });
  }

  function showModal() {
    var m = document.getElementById('sostGateModal');
    if (!m) {
      m = document.createElement('div'); m.id = 'sostGateModal'; m.className = 'sost-gate-modal';
      m.innerHTML = '<div class="box"><h3>Public access restricted</h3>' +
        '<p>This operation is <b>implemented and devnet-validated</b> but <b>not yet live on mainnet</b> ' +
        '(activates at block #30,000). Public execution is disabled pending regulatory readiness. ' +
        'Access is limited to developer / controlled testing.<br><br>' +
        'Technical availability does not constitute regulatory authorization.</p>' +
        '<button type="button">Understood</button></div>';
      document.body.appendChild(m);
      m.addEventListener('click', function (e) { if (e.target === m || e.target.tagName === 'BUTTON') m.classList.remove('show'); });
    }
    m.classList.add('show');
  }

  // ---- capture-phase interceptor: the REAL block ----
  function installInterceptor() {
    document.addEventListener('click', function (e) {
      if (!blocked()) return;
      var sel = ACTIONS.join(','); var t = null;
      try { t = e.target.closest(sel); } catch (ex) { t = null; }
      if (t) { e.preventDefault(); e.stopImmediatePropagation(); showModal(); }
    }, true); // capture: runs before the target's own onclick/handlers
    document.addEventListener('keydown', function (e) {
      if (!blocked()) return;
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var el = document.activeElement; if (!el) return;
      var sel = ACTIONS.join(',');
      if (el.matches && el.matches(sel)) { e.preventDefault(); e.stopImmediatePropagation(); showModal(); }
    }, true);
  }

  function heightThenMount() {
    mountBanner(null);
    // auto-switch copy: ask the public RPC for the tip height (best-effort)
    try {
      fetch('/rpc', { method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'getblockcount', params: [] }) })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d && typeof d.result === 'number') mountBanner(d.result); })
        .catch(function () {});
    } catch (e) {}
  }

  function init() {
    injectStyles();
    installInterceptor();
    heightThenMount();
    disableActions();
    veilPanel();
    // re-apply after late DOM mutations (SPA-ish pages re-render panels)
    var mo = new MutationObserver(function () { disableActions(); veilPanel(); });
    try { mo.observe(document.body, { childList: true, subtree: true }); } catch (e) {}
    // expose read-only state for tests / debugging
    window.SOST_GATE = { blocked: blocked, isDeveloper: isDeveloper, publicEnabled: publicEnabled,
      flags: { DEX_PUBLIC_ENABLED: DEX_PUBLIC_ENABLED, TOKENIZATION_PUBLIC_ENABLED: TOKENIZATION_PUBLIC_ENABLED,
        MAINNET_VALIDATED: MAINNET_VALIDATED, ACTIVATION_HEIGHT: ACTIVATION_HEIGHT } };
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
