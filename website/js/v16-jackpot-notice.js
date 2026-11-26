// SOST V17 — the ONE site-wide status banner and the shared source of V17 facts (27-Nov-2026).
//
// Every page that loads this file gets exactly one banner; pages that want the facts (V17 page, upgrade guide, News,
// Home) read window.SOST_V17 instead of hard-coding them. The file name is kept because ~60 pages already load it.
// History: the V30000 (#30,000) notice lives at sost-v30000-history.html; the withdrawn #40,000 plan is archived in
// News › Historical Network Upgrades (marked SUPERSEDED).
//
// STATUS is changed BY HAND together with an authorised release, never automatically by block height:
//   IN DEVELOPMENT | RELEASE READY | ACTIVATION SCHEDULED | ACTIVE
//
// Placement: inside <div id="sost-v16-notice-mount"></div> when the page has one (Explorer, Wallet),
// otherwise under the page header. Collapsed by default; "Details" opens what is active / in development.

(function () {
  'use strict';
  if (window.__sostV16NoticeInjected) return;
  window.__sostV16NoticeInjected = true;

  var V17 = window.SOST_V17 = Object.freeze({
    target: 45000,
    previousTarget: 40000,                 // withdrawn 26-Nov-2026
    status: 'IN DEVELOPMENT',
    statusLong: 'IN DEVELOPMENT — NOT ACTIVE',
    released: false,                       // no official V17 binaries, tag or checksums exist
    allocation: [                          // PROPOSED V17 allocation of the block subsidy
      { pct: 70, key: 'pow', label: 'PoW', long: 'Proof-of-Work miners (+ all fees)' },
      { pct: 5,  key: 'dtd', label: 'DTD', long: 'Deterministic Token Distribution' },
      { pct: 5,  key: 'jackpot', label: 'Jackpot', long: 'Jackpot (uniform among eligible miners, resolved by a VDF)' },
      { pct: 20, key: 'uc', label: 'Useful Compute', long: 'Useful Compute Vault (consensus balance, no key; spending OFF)' }
    ],
    today: '50% miner / 50% DTD (V16 rules)',
    maxSupply: '4,669,201.54789641',
    maturity: { participant: 1000, other: 5000 },
    links: { explore: 'sost-v17.html', guide: 'sost-v17-upgrade.html', news: 'news.html#v17-45000', compute: 'sost-autonomous-compute.html' }
  });

  function fmt(n) { return Number(n).toLocaleString('en-US'); }

  var CSS = '' +
'.sost-v17{max-width:1400px;margin:10px auto;border:1px solid rgba(56,189,248,.38);border-radius:14px;' +
'  background:linear-gradient(135deg,rgba(8,14,30,.97),rgba(10,8,24,.97));color:#e6ecf5;' +
'  font:13px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;box-shadow:0 0 0 1px rgba(139,92,246,.12) inset,0 6px 28px rgba(2,8,23,.45)}' +
'.sost-v17 *{box-sizing:border-box}' +
'.sost-v17-row{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;padding:11px 14px}' +
'.sost-v17-sig{flex:0 0 auto;width:30px;height:30px;display:block}' +
'.sost-v17-title{font-weight:800;letter-spacing:.4px;color:#fff;font-size:13.5px;white-space:nowrap}' +
'.sost-v17-title em{font-style:normal;color:#5eead4}' +
'.sost-v17-chip{flex:0 0 auto;padding:3px 10px;border-radius:999px;font-size:10.5px;font-weight:800;letter-spacing:1px;' +
'  border:1px solid #f59e0b;color:#fcd34d;background:rgba(245,158,11,.10);white-space:nowrap}' +
'.sost-v17-chip.active{border-color:#22c55e;color:#4ade80;background:rgba(34,197,94,.10)}' +
'.sost-v17-alloc{display:flex;align-items:center;gap:6px;flex-wrap:wrap}' +
'.sost-v17-alloc .k{font-size:10px;letter-spacing:.8px;color:#94a3b8;text-transform:uppercase;margin-right:2px}' +
'.sost-v17-pill{padding:2px 8px;border-radius:7px;font-size:11.5px;font-weight:700;color:#e2e8f0;background:rgba(148,163,184,.10);' +
'  border:1px solid rgba(148,163,184,.22);white-space:nowrap;font-variant-numeric:tabular-nums}' +
'.sost-v17-pill b{color:#fff}' +
'.sost-v17-pill.uc{border-color:rgba(94,234,212,.45);background:rgba(94,234,212,.08)}' +
'.sost-v17-pill.uc b{color:#5eead4}' +
'.sost-v17-sp{flex:1 1 auto}' +
'.sost-v17-links{display:flex;gap:7px;flex-wrap:wrap}' +
'.sost-v17-links a,.sost-v17-more{display:inline-flex;align-items:center;padding:5px 11px;border-radius:999px;' +
'  border:1px solid rgba(56,189,248,.5);color:#7dd3fc;text-decoration:none;font:700 11.5px/1.2 inherit;background:rgba(56,189,248,.06);cursor:pointer;white-space:nowrap}' +
'.sost-v17-links a:hover,.sost-v17-more:hover{background:rgba(56,189,248,.16)}' +
'.sost-v17-more{border-color:rgba(148,163,184,.4);color:#cbd5e1;background:transparent}' +
'.sost-v17-more i{display:inline-block;font-style:normal;margin-left:4px;transition:transform .15s}' +
'.sost-v17-more[aria-expanded="true"] i{transform:rotate(180deg)}' +
'.sost-v17-links a:focus-visible,.sost-v17-more:focus-visible{outline:2px solid #5eead4;outline-offset:2px}' +
'.sost-v17-msg{padding:0 14px 11px;color:#cbd5e1;font-size:12.5px}' +
'.sost-v17-msg b{color:#fff}' +
'.sost-v17-live{color:#94a3b8;font-variant-numeric:tabular-nums}' +
'.sost-v17-live b{color:#e2e8f0}' +
'.sost-v17-body{padding:4px 16px 16px;border-top:1px solid rgba(148,163,184,.14)}' +
'.sost-v17-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin-top:10px}' +
'.sost-v17-box{padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.18);background:rgba(15,23,42,.55)}' +
'.sost-v17-box h4{margin:0 0 5px;font-size:11px;letter-spacing:1px;text-transform:uppercase}' +
'.sost-v17-box ul{margin:0;padding-left:16px}.sost-v17-box li{margin:2px 0}' +
'.sost-v17-box.on h4{color:#4ade80}.sost-v17-box.dev h4{color:#fcd34d}.sost-v17-box.off h4{color:#f87171}' +
'.sost-v17-foot{margin-top:10px;font-size:11px;color:#8b95a5}' +
'@media (max-width:640px){.sost-v17{margin:8px}.sost-v17-row{padding:10px 11px;gap:8px}.sost-v17-title{font-size:12.5px;white-space:normal}' +
'  .sost-v17-sp{display:none}.sost-v17-msg{padding:0 11px 10px;font-size:12px}.sost-v17-body{padding:4px 11px 13px;font-size:12.5px}}';

  var pills = V17.allocation.map(function (a) {
    return '<span class="sost-v17-pill' + (a.key === 'uc' ? ' uc' : '') + '" title="' + a.long + '"><b>' + a.pct + '%</b> ' + a.label + '</span>';
  }).join('');

  var HTML = '' +
'<div class="sost-v17" role="region" aria-label="SOST V17 status: target block ' + fmt(V17.target) + ', in development, not active">' +
' <div class="sost-v17-row">' +
'  <img class="sost-v17-sig" src="/brand/legacy/sost-legacy-logo-512.png" alt="" width="30" height="30" decoding="async">' +
'  <span class="sost-v17-title">SOST V17 &middot; <em>TARGET BLOCK #' + fmt(V17.target) + '</em></span>' +
'  <span class="sost-v17-chip" data-v17-status>' + V17.statusLong + '</span>' +
'  <span class="sost-v17-alloc" aria-label="Proposed V17 allocation"><span class="k">Proposed V17 allocation</span>' + pills + '</span>' +
'  <span class="sost-v17-sp"></span>' +
'  <span class="sost-v17-links"><a href="' + V17.links.explore + '">Explore V17</a><a href="' + V17.links.guide + '">Operator Upgrade Guide</a>' +
'   <button type="button" class="sost-v17-more" aria-expanded="false" aria-controls="sostV17Body">Details<i>&#9662;</i></button></span>' +
' </div>' +
' <div class="sost-v17-msg">Block #' + fmt(V17.previousTarget) + ' activation and the previous upgrade window are <b>obsolete</b>. ' +
'  V17 is targeting block <b>#' + fmt(V17.target) + '</b>, subject to final validation and coordinated release. ' +
'  Current V16 mining continues normally. <b>No official V17 binaries are available yet.</b> ' +
'  <span class="sost-v17-live" data-v17-live></span></div>' +
' <div class="sost-v17-body" id="sostV17Body" hidden>' +
'  <div class="sost-v17-grid">' +
'   <div class="sost-v17-box on"><h4>Active today (V16)</h4><ul>' +
'    <li>Reward split <b>' + V17.today + '</b></li><li>ConvergenceX Proof-of-Work, cASERT difficulty</li>' +
'    <li>Maximum supply <b>' + V17.maxSupply + ' SOST</b> (unchanged by V17)</li><li>Official software: the current V30000 FINAL release</li></ul></div>' +
'   <div class="sost-v17-box dev"><h4>In V17 (not active)</h4><ul>' +
'    <li>70 / 5 / 5 / 20 allocation (proposed)</li><li>Jackpot resolved by a VDF</li>' +
'    <li>Miner coinbase maturity ' + fmt(V17.maturity.participant) + ' / ' + fmt(V17.maturity.other) + ' blocks per UTXO</li>' +
'    <li>P2P, reorg and consensus hardening; multisig</li></ul></div>' +
'   <div class="sost-v17-box off"><h4>Developed, closed to the public</h4><ul>' +
'    <li>Useful Compute marketplace (lab only)</li><li>Universal Assets (public issuance OFF)</li>' +
'    <li>SOST&harr;wSOST bridge (1:1 mint/burn, no pre-mint, closed to real funds)</li></ul></div>' +
'  </div>' +
'  <div class="sost-v17-foot">The status changes only with an authorised, published release &mdash; never automatically at a block height. ' +
'   Internal reviews are not independent audits. <a href="' + V17.links.news + '" style="color:#7dd3fc">Read the announcement</a> &middot; ' +
'   <a href="news.html#historical-network-upgrades" style="color:#7dd3fc">Historical upgrades</a></div>' +
' </div>' +
'</div>';

  function live(el) {
    function paint(h) {
      if (!(h > 0)) return;
      var left = V17.target - h;
      el.innerHTML = '&middot; Current height <b>' + fmt(h) + '</b>' + (left > 0 ? ' (' + fmt(left) + ' blocks below the target)' : '');
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
    if (document.documentElement.hasAttribute('data-no-v17-banner')) return;
    var st = document.createElement('style'); st.id = 'sost-v17-css'; st.textContent = CSS; document.head.appendChild(st);
    var wrap = document.createElement('div'); wrap.innerHTML = HTML; var box = wrap.firstChild;
    var mount = document.getElementById('sost-v16-notice-mount');
    if (mount) mount.appendChild(box);
    else {
      var anchor = document.querySelector('body > .reward-research-update') || document.querySelector('body > nav') ||
                   document.querySelector('.sost-devnote-strip');
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
      else document.body.insertBefore(box, document.body.firstChild);
      box.style.width = 'calc(100% - 32px)'; box.style.marginLeft = 'auto'; box.style.marginRight = 'auto';
    }
    var more = box.querySelector('.sost-v17-more'), body = box.querySelector('.sost-v17-body');
    more.addEventListener('click', function () {
      var open = more.getAttribute('aria-expanded') === 'true';
      more.setAttribute('aria-expanded', open ? 'false' : 'true'); body.hidden = open;
    });
    box.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !body.hidden) { body.hidden = true; more.setAttribute('aria-expanded', 'false'); more.focus(); } });
    if (V17.status === 'ACTIVE') box.querySelector('[data-v17-status]').classList.add('active');
    live(box.querySelector('[data-v17-live]'));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inject); else inject();
})();
