/* SOST DEX — official token symbols (self-contained inline SVG, no external assets).
 *
 * One recognizable glyph per swap asset, drawn in each asset's brand colour:
 *   SOST (brand red+gold), BTC (₿), ETH (diamond), USDC/USDT (dollar/tether ring),
 *   PAXG/XAUT (gold coin). Original glyphs — not copies of corporate logo artwork.
 * Usage:  el.innerHTML = SOSTTokenIcons.svg('BTC');
 *         SOSTTokenIcons.paintInto(el, 'SOST');   // also sets aria-label
 */
(function (root) {
  "use strict";
  var V = 'viewBox="0 0 32 32" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"';

  var ICONS = {
    SOST:
      '<svg ' + V + ' role="img" aria-label="SOST">' +
      '<defs><linearGradient id="sostg" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#FB010D"/><stop offset="1" stop-color="#b3060f"/></linearGradient></defs>' +
      '<circle cx="16" cy="16" r="15" fill="url(#sostg)"/>' +
      '<circle cx="16" cy="16" r="15" fill="none" stroke="#DAA520" stroke-width="1.6"/>' +
      '<path d="M20.6 11.4c-1.1-1.1-2.9-1.7-4.7-1.7-2.9 0-5 1.5-5 3.9 0 2.2 1.7 3.2 4.4 3.8 2.4.5 3.1.9 3.1 1.9 0 1-1 1.6-2.6 1.6-1.7 0-3.1-.7-4-1.7l-1.7 2.2c1.3 1.4 3.4 2.2 5.6 2.2 3.2 0 5.4-1.6 5.4-4.1 0-2.4-1.8-3.4-4.6-4-2.2-.5-2.9-.8-2.9-1.7 0-.8.8-1.4 2.2-1.4 1.4 0 2.7.6 3.5 1.4z" fill="#fff"/>' +
      '</svg>',
    USDC:
      '<svg ' + V + ' role="img" aria-label="USDC">' +
      '<circle cx="16" cy="16" r="15" fill="#2775CA"/>' +
      '<path d="M16 7v2.1M16 22.9V25" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>' +
      '<path d="M19.2 12c-.7-1-1.9-1.6-3.4-1.6-2.1 0-3.4 1-3.4 2.6 0 1.5 1.1 2.1 3.2 2.5 2.2.4 3.6 1 3.6 2.9s-1.5 3-3.9 3c-1.8 0-3.2-.7-3.9-1.9" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>' +
      '<circle cx="16" cy="16" r="11" fill="none" stroke="#fff" stroke-width="1.6" opacity=".55"/>' +
      '</svg>',
    USDT:
      '<svg ' + V + ' role="img" aria-label="USDT">' +
      '<circle cx="16" cy="16" r="15" fill="#26A17B"/>' +
      '<path d="M11 10.5h10M16 11v3M11.5 15.5c0 1.2 2 1.9 4.5 1.9s4.5-.7 4.5-1.9M16 14.5v8" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</svg>',
    BTC:
      '<svg ' + V + ' role="img" aria-label="Bitcoin">' +
      '<circle cx="16" cy="16" r="15" fill="#F7931A"/>' +
      '<path d="M14 9.5v13M17 9.5v13M11.5 12h6c1.6 0 2.8.9 2.8 2.4 0 1.3-.9 2.1-2.1 2.3 1.5.2 2.6 1 2.6 2.6 0 1.7-1.4 2.7-3.3 2.7h-6M11.5 12v10.5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</svg>',
    ETH:
      '<svg ' + V + ' role="img" aria-label="Ethereum">' +
      '<circle cx="16" cy="16" r="15" fill="#627EEA"/>' +
      '<path d="M16 6l6 10-6 3.5L10 16z" fill="#fff" opacity=".9"/>' +
      '<path d="M16 6l6 10-6 3.5z" fill="#fff" opacity=".65"/>' +
      '<path d="M16 20.7l6-3.6-6 8.9-6-8.9z" fill="#fff" opacity=".9"/>' +
      '<path d="M16 20.7l6-3.6-6 8.9z" fill="#fff" opacity=".65"/>' +
      '</svg>',
    PAXG:
      '<svg ' + V + ' role="img" aria-label="PAX Gold">' +
      '<defs><linearGradient id="paxg" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#F1D06B"/><stop offset="1" stop-color="#B8860B"/></linearGradient></defs>' +
      '<circle cx="16" cy="16" r="15" fill="url(#paxg)"/>' +
      '<circle cx="16" cy="16" r="11.5" fill="none" stroke="#7a5a06" stroke-width="1.2" opacity=".6"/>' +
      '<text x="16" y="20.5" text-anchor="middle" font-family="Georgia,serif" font-size="11" font-weight="700" fill="#4a3400">Au</text>' +
      '</svg>',
    XAUT:
      '<svg ' + V + ' role="img" aria-label="Tether Gold">' +
      '<defs><linearGradient id="xaut" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#D9B44A"/><stop offset="1" stop-color="#9A7509"/></linearGradient></defs>' +
      '<circle cx="16" cy="16" r="15" fill="url(#xaut)"/>' +
      '<circle cx="16" cy="16" r="11.5" fill="none" stroke="#26A17B" stroke-width="1.4" opacity=".8"/>' +
      '<text x="16" y="20.5" text-anchor="middle" font-family="Georgia,serif" font-size="10.5" font-weight="700" fill="#3a2a00">Au</text>' +
      '</svg>'
  };

  function svg(sym) { return ICONS[(sym || "").toUpperCase()] || fallback(sym); }
  function fallback(sym) {
    var ch = (sym || "?").charAt(0).toUpperCase();
    return '<svg ' + V + ' role="img" aria-label="' + sym + '"><circle cx="16" cy="16" r="15" fill="#39424f"/>' +
      '<text x="16" y="21" text-anchor="middle" font-family="monospace" font-size="14" font-weight="700" fill="#fff">' + ch + '</text></svg>';
  }
  function has(sym) { return !!ICONS[(sym || "").toUpperCase()]; }
  function paintInto(el, sym) { if (!el) return; el.innerHTML = svg(sym); el.setAttribute("aria-label", sym); }

  var API = { svg: svg, has: has, paintInto: paintInto, symbols: Object.keys(ICONS) };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (root) root.SOSTTokenIcons = API;
})(typeof self !== "undefined" ? self : this);
