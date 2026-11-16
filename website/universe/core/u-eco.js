/* SOST Universe — ecosystem modules and their REAL status (DIRECTIVA 4D §5-D). One list for home.html and ecosystem.html.
 * [name, status, description, href, extra badge]. Status keys are those of SOSTU.nav.STATUS. Sources: protocol-status.json, the
 * security notices (H-01: the HTLC atomic swap contracts are RETIRED; the swap paths are disabled) and the site audit. No bridge is
 * active. Change a state here only when its source changes. */
(function (root) {
  'use strict';
  var U = root.SOSTU = root.SOSTU || {};
  U.eco = { LIST: [['SOST L1 mainnet','active','Proof-of-work chain, V30000 rules.','../sost-explorer.html'],
 ['Explorer','active','Read-only network observation.','../sost-explorer.html'],
 ['Wallet','active','Self-custody web wallet (separate, protected).','../sost-wallet.html'],
 ['Mining','active','ConvergenceX on CPU, solo mining.','proto-d-launchpad.html'],
 ['DTD (every block)','active','Deterministic draw, 50 % of the subsidy.','#dtd'],
 ['DTD Jackpot V2','active','Every 288 blocks since #30,000 (first draw #30,186).','proto-c-orbit.html'],
 ['SOST app (web)','active','Installable app (PWA) that opens the SOST Explorer. No Android app on Google Play.','install.html'],
 ['Native assets & tokenization','blocked','Deferred / fail-closed on mainnet; admin-gated (S14 restricted developer mode).','../sost-universal-assets.html'],
 ['SOST-layer DEX','blocked','Native-asset DEX deferred (fail-closed); EVM mainnet not deployed; public trading disabled.','../sost-gold-dex.html'],
 ['HTLC atomic swaps','retired','Contracts retired after security finding H-01. Do not use.','../news.html'],
 ['OTC / P2P','retired','Swap paths disabled under H-01.','../sost-otc.html'],
 ['wSOST / bridge','research','Research roadmap; not live. No bridge is active.','../sost-wsost-gold-vault.html','NOT ACTIVE'],
 ['E2E coordination','research','Signed off-chain offers and notices; design work.','../sost-e2e.html'],
 ['#40,000 reward study','research','80/15/5 scenario; not consensus.','#research'],
 ['Post-quantum migration','research','Study only; signatures are ECDSA today.','../sost-security.html'],
 ['Metals reserve (25 %)','retired','Ended at #25,000; the reserve is drained by the DTD Jackpot.','../sost-gold-reserve.html'],
 ['PoPC (25 %)','retired','Paused / legacy since #25,000; escrow kept for reference only.','../sost-popc.html'],
 ['SACS V2','blocked','Deferred on mainnet.','../sost-security.html']
  ] };
})(window);
