// SOST V17 — site-wide compact banner (14-Nov-2026). 26-Nov-2026: preventive notice — the #40,000 plan is OBSOLETE
// (owner decision: proposed new target #45,000, conditional; full page sync only after the RC13 validation).
//
// Replaces the V30000 (#30,000) operator notice. The full V30000 text is kept, unchanged, at
// sost-v30000-history.html and in News & Updates › Historical Network Upgrades.
// The file name is kept so every page that already loads it (60 pages) gets the new banner.
//
// Placement: inside <div id="sost-v16-notice-mount"></div> when the page has one (Explorer),
// otherwise at the top of <body> (below the developer note strip when present).
// Collapsed by default on every load (state never persisted): Legacy red Σ (Brand Kit /brand/legacy), title, block #40,000,
// status and blocks left. Details opens the full text (changes, CRITICAL chain-split warning, links); a second click folds it.
// 14-Nov-2026 owner P0: compact collapsed head; the long live sentence moved inside the panel.
//
// STATUS must reflect reality: PROPOSED | TESTING | RELEASE READY | ACTIVATION SCHEDULED | ACTIVE.
// It is TESTING while no approved V17 release exists. Change it only together with the release.

(function () {
  'use strict';
  if (window.__sostV16NoticeInjected) return;
  window.__sostV16NoticeInjected = true;

  var V17_HEIGHT = 40000;
  var WINDOW_START = 39900;
  var STATUS = 'TESTING';
  var STATUS_NOTE = 'Candidate under final testing. No V17 release has been published. Do not install unofficial builds.';
  var OBSOLETE = true;   // 26-Nov-2026: #40,000 target and #39,900-#39,999 window withdrawn; proposed new target #45,000 (not final)
  var LINK_NEW = 'sost-v17.html';
  var LINK_GUIDE = 'sost-v17-upgrade.html';
  var LINK_REL = 'sost-v17-upgrade.html#release';

  var CSS = '' +
'.sost-v17{max-width:1400px;margin:10px auto;border:1px solid rgba(251,1,13,.55);border-radius:12px;background:#07070a;' +
'  color:#e8e8ec;font:13px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;box-shadow:0 0 0 1px rgba(212,175,55,.10) inset}' +
'.sost-v17 *{box-sizing:border-box}' +
'.sost-v17-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;width:100%;padding:11px 14px;background:transparent;border:0;' +
'  color:inherit;font:inherit;text-align:left;cursor:pointer;border-radius:12px}' +
'.sost-v17-head:hover{background:rgba(255,255,255,.03)}' +
'.sost-v17-head:focus-visible{outline:2px solid #d4af37;outline-offset:-2px}' +
'.sost-v17-sig{flex:0 0 auto;width:30px;height:30px;display:block}' +
'.sost-v17-t{flex:1 1 auto;min-width:0;display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px}' +
'.sost-v17-title{font-weight:800;letter-spacing:.3px;color:#fff;font-size:13.5px;white-space:nowrap}' +
'.sost-v17-left{color:#a9b1bf;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}' +
'.sost-v17-left b{color:#fff}' +
'.sost-v17-title em{font-style:normal;color:#d4af37}' +
'.sost-v17-live{color:#c9ced8;font-variant-numeric:tabular-nums}' +
'.sost-v17-live b{color:#fff}' +
'.sost-v17-chip{flex:0 0 auto;padding:3px 9px;border-radius:999px;font-size:10.5px;font-weight:800;letter-spacing:1px;' +
'  border:1px solid #d4af37;color:#f6d77a;background:rgba(212,175,55,.10);white-space:nowrap}' +
'.sost-v17-chip.active{border-color:#39ff14;color:#39ff14;background:rgba(57,255,20,.08)}' +
'.sost-v17-more{flex:0 0 auto;font-size:11px;font-weight:700;color:#cfd3da;white-space:nowrap}' +
'.sost-v17-more i{display:inline-block;font-style:normal;transition:transform .15s}' +
'.sost-v17-head[aria-expanded="true"] .sost-v17-more i{transform:rotate(180deg)}' +
'.sost-v17-body{padding:2px 16px 16px;border-top:1px solid rgba(255,255,255,.08);max-height:70vh;overflow-y:auto}' +
'.sost-v17-body p{margin:.6em 0}' +
'.sost-v17-crit{margin:12px 0;padding:11px 13px;border-radius:8px;border:2px solid #fb010d;background:rgba(251,1,13,.09);color:#ffe1e1}' +
'.sost-v17-crit .h{display:block;color:#ff4d55;font-weight:900;letter-spacing:.8px;font-size:12px;margin-bottom:4px}' +
'.sost-v17-crit b{color:#fff}' +
'.sost-v17-now{margin:12px 0;padding:10px 13px;border-radius:8px;border:1px solid rgba(57,255,20,.45);background:rgba(57,255,20,.05);color:#d9f7dc}' +
'.sost-v17-now b{color:#39ff14}' +
'.sost-v17-split{margin:12px 0;padding:10px 13px;border-radius:8px;border:1px solid rgba(212,175,55,.45);background:rgba(212,175,55,.05)}' +
'.sost-v17-split .h{display:block;color:#f6d77a;font-weight:900;letter-spacing:.8px;font-size:12px;margin-bottom:4px}' +
'.sost-v17-split ul{margin:4px 0 6px;padding-left:4px;list-style:none}' +
'.sost-v17-split li{margin:2px 0}' +
'.sost-v17-split b{color:#fff}' +
'.sost-v17-split p{margin:.45em 0;color:#c9ced8}' +
'.sost-v17-links{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}' +
'.sost-v17-links a{display:inline-flex;align-items:center;padding:7px 12px;border-radius:999px;border:1px solid rgba(212,175,55,.6);' +
'  color:#f6d77a;text-decoration:none;font-size:12px;font-weight:700;background:rgba(212,175,55,.06)}' +
'.sost-v17-links a:hover{background:rgba(212,175,55,.16)}' +
'.sost-v17-foot{margin-top:10px;font-size:11px;color:#8a92a0}' +
'@media (max-width:640px){.sost-v17{margin:8px}.sost-v17-head{padding:9px 11px;gap:9px;flex-wrap:nowrap}.sost-v17-title{font-size:12.5px}' +
'  .sost-v17-chip{font-size:9.5px;padding:2px 7px}.sost-v17-left{font-size:11.5px}' +
'  .sost-v17-body{padding:2px 12px 14px;font-size:12.5px}}';

  var HTML = '' +
'<div class="sost-v17" role="region" aria-label="SOST V17 network upgrade: the block 40,000 plan is obsolete">' +
' <button type="button" class="sost-v17-head" aria-expanded="false" aria-controls="sostV17Body">' +
'  <img class="sost-v17-sig" src="/brand/legacy/sost-legacy-logo-512.png" alt="" width="30" height="30" decoding="async">' +
'  <span class="sost-v17-t"><span class="sost-v17-title">SOST V17 &middot; <em>#40,000 PLAN OBSOLETE</em></span>' +
'   <span class="sost-v17-chip" data-v17-status>' + STATUS + '</span>' +
'   <span class="sost-v17-left">proposed new target <b>#45,000</b> &middot; not final</span></span>' +
'  <span class="sost-v17-more">Details <i>&#9662;</i></span>' +
' </button>' +
' <div class="sost-v17-body" id="sostV17Body" hidden>' +
'  <div class="sost-v17-crit"><span class="h">&#9888; NOTICE &mdash; 26 NOVEMBER 2026: THE #40,000 PLAN IS OBSOLETE</span>' +
'   V17 will <b>not</b> activate at block #40,000. The #40,000 target, the #39,900&ndash;#39,999 restart window and the reward split shown below no longer apply. ' +
'   The proposed new target is block <b>#45,000</b>, conditional on the final security review and on operator coordination; it is not final until the official release is published. ' +
'   <b>No V17 release, tag or checksum exists yet: do not install any V17 build.</b> The network keeps running V30000 FINAL and mining continues normally. ' +
'   The text below is the previous plan, kept for reference until the pages are updated with the release.</div>' +
'  <p class="sost-v17-live" data-v17-live>SOST V17 &mdash; network upgrade &middot; block #40,000</p>' +
'  <p>SOST is preparing a coordinated network upgrade targeting block <b>#40,000</b>. Proposed improvements include revised mining and DTD rewards, ' +
'  new coinbase maturity rules, stronger reorganization safeguards, improved P2P synchronization and enhanced node and wallet security.</p>' +
'  <div class="sost-v17-split"><span class="h">PROPOSED V17 &mdash; NOT ACTIVE</span>' +
'   <ul><li>&#9935;&#65039; <b>80%</b> PoW miners</li>' +
'   <li>&#127919; <b>10%</b> Deterministic Token Distribution (DTD)</li>' +
'   <li>&#127942; <b>5%</b> DTD Jackpot</li>' +
'   <li>&#129504; <b>5%</b> Useful Compute Reward</li></ul>' +
'   <p>This split replaces the earlier 80/15/5 proposal. It is <b>not yet implemented or activated in consensus</b>, and it does not increase the total SOST emission.</p>' +
'   <p><b>Useful Compute Reward (5%, proposed):</b> A future protocol-controlled vault intended to fund independently verified CPU/GPU computational tasks, ' +
'   including scientific research, simulations and data processing. Verification and payment rules remain under development; no Useful Compute rewards are active.</p></div>' +
'  <p>Node operators and miners must prepare compatible, verified software before activation. The release remains subject to final testing and approval.</p>' +
'  <p style="color:#a9b1bf">Status: <b style="color:#f6d77a">' + STATUS + '</b> &mdash; ' + STATUS_NOTE + '</p>' +
'  <div class="sost-v17-crit"><span class="h">&#9888; CRITICAL &mdash; COORDINATED NETWORK UPGRADE REQUIRED</span>' +
'   All miners and validating node operators must install and verify the approved V17 release before block #40,000. ' +
'   The recommended coordinated restart window is blocks <b>#39,900&ndash;#39,999</b>. Failure to update may cause a <b>chain split</b>: ' +
'   incompatible nodes could follow different blockchain histories, reject blocks, and report divergent balances or confirmations. ' +
'   <b>Do not continue mining with an incompatible release after activation.</b></div>' +
'  <div class="sost-v17-now"><b>Today (until #40,000):</b> the network runs the V30000 rules and <b>V30000 FINAL</b> is the valid build. ' +
'   No action is needed now. Its binaries and checksums stay published on the ' +
'   <a href="sost-v30000-history.html" style="color:#39ff14;font-weight:700">V30000 page</a>.</div>' +
'  <div class="sost-v17-links">' +
'   <a href="' + LINK_NEW + '">What&rsquo;s changing</a>' +
'   <a href="' + LINK_GUIDE + '">Operator Upgrade Guide</a>' +
'   <a href="' + LINK_REL + '">Release &amp; Checksums</a>' +
'   <a href="news.html#historical-network-upgrades">Historical Network Upgrades</a>' +
'  </div>' +
'  <div class="sost-v17-foot">The 100-block window is counted in blocks, not hours: its duration depends on the real block rate. ' +
'   Dates shown are estimates from the measured block rate, not commitments.</div>' +
' </div>' +
'</div>';

  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function live(el, le) {
    function paint(h) {
      if (!(h > 0)) return;
      if (OBSOLETE) { el.innerHTML = 'Current height <b>' + fmt(h) + '</b> &middot; the #40,000 plan is obsolete &middot; proposed new target #45,000 (not final)'; return; }
      var left = V17_HEIGHT - h, w = WINDOW_START - h, txt;
      if (left > 0) {
        var days = Math.round(left * 600 / 86400);
        txt = 'Current height <b>' + fmt(h) + '</b> &middot; <b>' + fmt(left) + '</b> blocks to #40,000 ' +
              '(&asymp; ' + days + ' days at the 10-minute target)' +
              (w > 0 ? ' &middot; upgrade window opens at #39,900' : ' &middot; <b style="color:#ff4d55">upgrade window open</b>');
      } else {
        txt = 'Current height <b>' + fmt(h) + '</b> &middot; block #40,000 reached &middot; check the status before acting';
      }
      el.innerHTML = txt;
      le.innerHTML = left > 0 ? '<b>' + fmt(left) + '</b> blocks left' : '#40,000 reached';
    }
    function get() {
      try {
        fetch('/api/control_room.json', { cache: 'no-store' }).then(function (r) { return r.json(); })
          .then(function (d) { paint(+d.height); }).catch(function () {});
      } catch (e) {}
    }
    get(); setInterval(get, 120000);
  }

  function inject() {
    if (document.querySelector('.sost-v17')) return;
    var st = document.createElement('style'); st.id = 'sost-v17-css'; st.textContent = CSS; document.head.appendChild(st);
    var wrap = document.createElement('div'); wrap.innerHTML = HTML; var box = wrap.firstChild;
    var mount = document.getElementById('sost-v16-notice-mount');
    if (mount) mount.appendChild(box);
    else {
      // same flow placement as the previous notice: under the research notice, else under the page header, never above the logos
      var anchor = document.querySelector('body > .reward-research-update') || document.querySelector('body > nav') ||
                   document.querySelector('.sost-devnote-strip');
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
      else document.body.insertBefore(box, document.body.firstChild);
      box.style.width = 'calc(100% - 32px)'; box.style.marginLeft = 'auto'; box.style.marginRight = 'auto';
    }
    var head = box.querySelector('.sost-v17-head'), body = box.querySelector('.sost-v17-body');
    head.addEventListener('click', function () {
      var open = head.getAttribute('aria-expanded') === 'true';
      head.setAttribute('aria-expanded', open ? 'false' : 'true'); body.hidden = open;
    });
    box.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !body.hidden) { body.hidden = true; head.setAttribute('aria-expanded', 'false'); head.focus(); } });
    if (STATUS === 'ACTIVE') box.querySelector('[data-v17-status]').classList.add('active');
    live(box.querySelector('[data-v17-live]'), box.querySelector('[data-v17-left]'));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inject); else inject();
})();
