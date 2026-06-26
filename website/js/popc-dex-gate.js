/* popc-dex-gate.js — gate OFF the active PoPC position-trading UI.
 *
 * V15 has NO PoPC contract trading: PoPC is a non-tradeable native SOST bond.
 * While window.POPC_DEX_ENABLED !== true (the default), this hides the active
 * trading surface (Trade Composer, Buy/Sell Position, Sell Reward Right, position
 * market tables/actions) and shows a clear disabled note. It does NOT touch the
 * reusable Atomic Swap / OTC pieces (deal channels, signed offers, identity, E2E,
 * safety / anti-scam guides). Inert if the flag is turned on. No network, no keys.
 */
(function () {
  if (typeof window !== 'undefined' && window.POPC_DEX_ENABLED === true) return;

  function hide(el) { if (el && el.style) el.style.display = 'none'; }

  function run() {
    var hidden = 0;

    // 1) Known trading containers (by id or class hint).
    ['trade-composer', 'position-market', 'positions-market', 'trade-table', 'reward-right', 'sell-reward']
      .forEach(function (id) { var e = document.getElementById(id); if (e) { hide(e); hidden++; } });
    document.querySelectorAll('.trade-composer,.position-market,.positions-table,.position-actions')
      .forEach(function (e) { hide(e); hidden++; });

    // 2) Buttons that fire a position/reward trade action.
    document.querySelectorAll('[data-action^="buy_"],[data-action^="sell_"],[data-action="split"],[data-action^="reward"]')
      .forEach(function (e) { hide(e); hidden++; });

    // 3) CTA links/buttons whose visible text is a PoPC position/reward trade action.
    var re = /\b(buy|sell|split)\b[\s\S]{0,18}\b(position|reward|right)\b|trade composer|sell reward right/i;
    document.querySelectorAll('a,button').forEach(function (e) {
      var t = (e.textContent || '').trim();
      if (t && t.length < 64 && re.test(t)) { hide(e); hidden++; }
    });

    // 4) One-time disabled note near the top of the main content.
    if (hidden > 0 && !document.getElementById('popc-dex-gate-note')) {
      var note = document.createElement('div');
      note.id = 'popc-dex-gate-note';
      note.style.cssText = 'max-width:1100px;margin:14px auto;padding:10px 16px;border:1px solid rgba(255,206,84,.35);border-radius:10px;background:rgba(255,206,84,.06);color:#ffce54;font-size:13px;line-height:1.6;text-align:center';
      note.innerHTML = '⊘ PoPC contract trading is <b>disabled in V15</b>. Use the <b>Atomic Swap DEX</b> for non-custodial swap / OTC coordination. PoPC is a native SOST bond — see <a href="sost-popc.html" style="color:inherit;text-decoration:underline">PoPC Bond Staking</a>.';
      var main = document.querySelector('main') || document.querySelector('.hero') || document.body;
      if (main && main.parentNode) {
        if (main.tagName === 'MAIN' || main.classList.contains('hero')) main.parentNode.insertBefore(note, main);
        else main.insertBefore(note, main.firstChild);
      }
    }
  }

  if (document.readyState !== 'loading') run();
  else document.addEventListener('DOMContentLoaded', run);
})();
