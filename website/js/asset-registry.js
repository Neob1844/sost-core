/* SOST — CANONICAL asset metadata registry (single source of truth).
 *
 * Shared by Atomic Swap (atomic-swap.html) and SOST DEX V2 (sost-dex.html) so token
 * definitions, decimals, swap status and logos never drift between UIs.
 *
 * LOGOS: `logo` is a path to an OFFICIAL image file when the project holds a licensed
 * asset (only SOST today). For third-party tokens the project holds no licensed logo
 * artwork, so `logo` is null and the UI falls back to a neutral, original glyph
 * (SOSTTokenIcons) — NOT a reproduction of the trademarked corporate logo. To use an
 * official logo, drop the licensed file at `logoDropIn` and set `logo` to that path;
 * the renderer picks it up automatically. Do not commit trademarked artwork you are
 * not licensed to redistribute.
 *
 * STATUS (swap availability), honest and per-asset:
 *   ok       — atomic-swap path implemented + lab-tested for this asset
 *   caveat   — usable but with a documented risk shown to the user
 *   disabled — NOT safe/complete yet; carries the exact outstanding requirement
 *
 * Contract addresses are intentionally null here: they are pinned per-network only in
 * the fork-test harness (never fabricated in UI code). decimals/chain/transfer are the
 * real technical facts that drive escrow correctness.
 */
(function (root) {
  "use strict";
  var LOGO_DIR = "assets/tokens/"; // drop official licensed files here (e.g. assets/tokens/xaut.png)

  var ASSETS = {
    SOST: { symbol:"SOST", name:"Sovereign Stock Token", chain:"sost", kind:"native", decimals:8,
            logo:"sost-logo.png?v=v392", logoDropIn:null,
            status:{state:"ok", reason:"native SOST HTLC (OUT_HTLC_LOCK) lab-tested"} },
    BTC:  { symbol:"BTC", name:"Bitcoin", chain:"btc", kind:"native", decimals:8,
            logo:null, logoDropIn:LOGO_DIR+"btc.png",
            status:{state:"ok", reason:"BIP-199 P2WSH HTLC lab-tested (regtest)"} },
    ETH:  { symbol:"ETH", name:"Ether", chain:"evm", kind:"native", decimals:18,
            logo:null, logoDropIn:LOGO_DIR+"eth.png",
            status:{state:"ok", reason:"AtomicSwapHTLC.lockNative lab-tested"} },
    USDC: { symbol:"USDC", name:"USD Coin", chain:"evm", kind:"erc20", decimals:6, transfer:"standard",
            logo:null, logoDropIn:LOGO_DIR+"usdc.png",
            status:{state:"caveat", reason:"Circle blacklist/pause can freeze a swap mid-flight"} },
    USDT: { symbol:"USDT", name:"Tether USD", chain:"evm", kind:"erc20", decimals:6, transfer:"no-return-value",
            logo:null, logoDropIn:LOGO_DIR+"usdt.png",
            status:{state:"disabled", reason:"USDT transfer returns no boolean — needs SafeERC20-style handling in the HTLC before it can be enabled"} },
    PAXG: { symbol:"PAXG", name:"PAX Gold", chain:"evm", kind:"erc20", decimals:18, transfer:"fee-on-transfer",
            logo:null, logoDropIn:LOGO_DIR+"paxg.png",
            status:{state:"disabled", reason:"PAXG fee-on-transfer breaks fixed-amount escrow — needs balance-delta accounting (received-amount) escrow, tested on a pinned fork with the real contract"} },
    XAUT: { symbol:"XAUT", name:"Tether Gold", chain:"evm", kind:"erc20", decimals:6, transfer:"unverified",
            logo:null, logoDropIn:LOGO_DIR+"xaut.png",
            status:{state:"disabled", reason:"XAUT real-contract behaviour not yet verified on a pinned EVM fork (approve/transferFrom/restrictions) — a mock-token pass is insufficient"} }
  };

  function get(sym){ return ASSETS[(sym||"").toUpperCase()] || null; }
  function status(sym){ var a=get(sym); return a?a.status:{state:"unknown", reason:"unknown asset"}; }
  function decimals(sym){ var a=get(sym); return a?a.decimals:null; }
  // logo HTML: official <img> if a licensed file is set, else the neutral original glyph.
  function logoHtml(sym){
    var a=get(sym); if(!a) return "";
    if(a.logo) return '<img src="'+a.logo+'" alt="'+a.symbol+'" style="width:100%;height:100%;object-fit:contain;border-radius:50%">';
    if(root.SOSTTokenIcons) return root.SOSTTokenIcons.svg(a.symbol);
    return a.symbol.charAt(0);
  }
  // A disabled/caveat reason for a PAIR — only ever the currently selected assets.
  function pairBlock(paySym, recvSym){
    var pair=[paySym, recvSym];
    for(var i=0;i<pair.length;i++){ var a=get(pair[i]); if(a && a.status.state==="disabled") return pair[i]+": "+a.status.reason; }
    return null;
  }

  var API = { ASSETS: ASSETS, get: get, status: status, decimals: decimals, logoHtml: logoHtml, pairBlock: pairBlock, LOGO_DIR: LOGO_DIR };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (root) root.SOSTAssets = API;
})(typeof self !== "undefined" ? self : this);
