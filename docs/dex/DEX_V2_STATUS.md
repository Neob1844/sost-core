# SOST DEX V2 — status (lab / not deployed)

New page `website/sost-dex-v2.html` (self-contained). Production `website/sost-dex.html` is
UNCHANGED and not deployed. Everything in V2 is clearly marked DEMO / TESTNET·LAB; no real
prices, balances, quotes, orders, or liquidity are shown or implied.

## Audit of existing code (reused / classified)
| File | What it is | Status |
|---|---|---|
| `website/sost-dex.html` (2021 ln) | current production DEX page | KEEP intact; V2 is a separate page |
| `website/atomic-swap.html` / `atomic-swap-console.html` | founder atomic-swap UI + operative console | reference; V2 links the proven lab flow |
| `website/js/atomic-swap-evm.js` (219 ln) | dependency-free ABI codec for the REAL `AtomicSwapHTLC` (static 32-byte words only) | REUSABLE for V2's EVM leg (real) |
| `website/js/atomic-swap-htlc-runtime.js` | expected deployed runtime bytecode for `eth_getCode` verification | REUSABLE (contract-authenticity check) |
| `website/js/dex-trade-engine.js` / `dex-session.js` | Trade Composer → crypto ops; session lifecycle | reference for the real wiring phase |
| `contracts/atomic-swap/src/AtomicSwapHTLC.sol` | the HTLC contract (proven in the cross-chain lab) | REAL; V2 Activity mirrors its lifecycle |

No new blockchain / EVM / wrapped-SOST / custodial bridge is introduced. V2 reuses the native
atomic-swap protocol that is proven end-to-end in the lab (see `docs/v15/CROSS_CHAIN_SWAP_RESULTS.md`).

## Phase status
- **Phase 1 — visual dashboard: DONE + visually verified** (headless Chromium screenshots).
  SWAP (YOU PAY / invert / YOU RECEIVE, state-driven CTA, honest "No executable quote available"),
  TRADE (demo-labelled chart, Market/Limit form, orders/fills), ORDERS (empty, honest), ACTIVITY
  (canonical HTLC lifecycle mirroring a real lab swap). SOST identity per spec (#05070A/#0D1117/
  #FB010D/#DAA520, Space Grotesk + JetBrains Mono). Responsive (desktop + mobile). Wallet connect
  is a placeholder that never requests a seed/key. `node --check` clean.
- **Phase 2 SWAP / Phase 3 TRADE**: shells built with honest empty/DEMO states.
- **Phase 4 price & liquidity: modules built + tested (23/23).** `js/dex-price-adapter.js` (decoupled
  Price Reference Adapter — lab returns a non-executable simulated reference; a future CEX source
  yields bid/ask/depth/volume/age/status but a *reference is never executable*), `js/dex-rfq.js`
  (signed-quote book with expiry, reserved-inventory check, replay + double-accept protection),
  `js/dex-liquidity-sim.js` ($2,000 SOST/USDC inventory simulator for INDEPENDENT providers —
  spread, max-quote size, per-offer reservation, fill/PnL/fees, suspend on stale ref or depletion,
  adverse-shock model). Tests: `js/test/dex-phase4.test.js` (node, 23/23). The gold reference
  (1.14 mg) is NEVER used as a market price — see `GOLD_REFERENCE_RECONCILIATION.md`. No real
  funds; the owner is not assumed to self-trade. UI wiring of these modules into the dashboard is
  the remaining Phase-4 step.
- **Phase 5 orderbook / signed-quote engine**: NOT built (design only).
- **Phase 6 real atomic-swap wiring** (SOST devnet ⇄ BTC regtest / Anvil): the underlying swap is
  proven in the lab; wiring the dashboard to the live coordinator/watcher is the next step.
- **Phase 7 security/UX guards, Phase 8 regulatory review, Phase 9 browser E2E**: pending.

## Hard rules honored
Production page intact; no deploy; no mainnet/real funds; no consensus/V16 change; no own EVM or
new coin; wallet flows never ask for seed/keys; never simulate an executable price or liquidity
that does not exist.
