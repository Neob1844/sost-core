# V15 Readiness

Living status doc. Updated 2026-07-25. Branch `feat/v15-jackpot-explorer-card`
(pushed; NOT on main, NOT deployed). Evidence-based — a feature is only "READY"
when its release gate (below) is green, not when it compiles.

## Canonical activation values
| Value | Height | Notes |
|---|---|---|
| V15 mainnet activation | **25,000** | moved from 20,000 (2026-07-25) for implementation + soak runway |
| First Historical DTD Jackpot | **25,290** | draw-aligned (`%3==0`), static_asserted |
| DTD-PoPC eligibility | **30,000** | derived = V15_HEIGHT + 5,000 grace (cascaded automatically) |
| Current mainnet height | ~19,022 | deployed binary has V15 gates DEFERRED → nothing activates at 20,000 |
| Forge program | independent / **unchanged** | its 20,000/25,000 are its own phases, not V15 |

## Component status
| Component | Implemented | Tested | Mainnet ready | Blockers |
|---|---|---|---|---|
| Gold Vault/PoPC transition (T) | ✅ | ✅ 289 asserts | ❌ | live regtest soak; testnet DTD schedule |
| Historical Jackpot (J) — pure core | ✅ | ✅ 62 asserts | ❌ | — |
| Historical Jackpot (J) — A1 tx (canonical+exact-match) | ✅ | ✅ (in 62) | ❌ | — |
| Historical Jackpot (J) — live wiring: process_block canonical gate + keyless auth + mempool isolation + min-validation exception | ✅ CODE (commits 9834c889/cf6c1afa/864ea3c2) | ✅ unit (jackpot 108 + block-rule); ❌ live integration | ❌ | regtest harness (needs accelerated testnet schedule: testnet V15=300 sits BELOW DTD activation 7100 — incoherent), miner/template jackpot construction, live Connect/Disconnect/reorg/restart/reindex tests, testnet, soak |
| Explorer V15 (25,000/25,290/30,000) | ✅ | ✅ 24 (gateway) | ❌ (not deployed) | coordinate deploy with node rollout |
| Consumer swap dashboard | ✅ | parse-validated | ❌ (founder-testing) | real quotes need counterparty; not deployed |
| Atomic Swap — policy layer (timeout/swapId/preimage/RPC) | ✅ | ✅ 49 | n/a (off-chain) | route coordinator/orderbook through it |
| Atomic Swap EVM — contract (SafeERC20 + balance-delta) | ⏸ held | ✅ 60 Foundry | ❌ | **fund-custody change — needs external audit before landing/deploy** |
| Atomic Swap BTC — HTLC signing lifecycle | ✅ (gated OFF) | ✅ 121 ON / 50 OFF | ❌ | live bitcoind regtest (no infra), external crypto review; gate stays OFF |

## Release gates
**V15 CONSENSUS:** T ✅ · T tests ✅ · J core ✅ · J process_block gate ✅ · **keyless auth bound to exact canonical tx on EVERY ConnectBlock caller (process_block + reorg + load_chain/reindex) ✅** · adversarial module tests ✅ (test_jackpot 108: wrong winner/amount/input/order/position/extra/missing/duplicate/non-event-height/empty-reserve/signature-set all rejected) · mempool isolation ✅ · min-validation exception ✅ · activation-boundary (T) ✅ · miner/template ❌ · live node accept/Disconnect ❌ · reorg ❌ · restart/reindex ❌ · regtest harness ❌ · testnet ❌ · soak ❌ → **NOT MET** (2026-08-04: security-audit §2 CLOSED, commit d15be583; ctest 101/101; remaining = network-param refactor → harness → runtime integration → testnet/soak)
**EVM SWAP:** create/fund/detect/redeem/refund logic present · timeout policy ✅ · persistence partial · E2E ❌ · contract audit ❌ → **NOT MET**
**BTC SWAP:** script ✅ · funding ✅ · sign ✅ · redeem/refund ✅ · preimage ✅ · regtest ❌ · review ❌ → **NOT MET** (gate stays OFF)
**DASHBOARD:** UI ✅ · backend hooks partial · history ✅ · unsupported pairs disabled ✅ · deployed ❌ → **NOT MET**

## Overall verdict
**V15 READY FOR TESTNET/REGTEST ONLY (partial).** Real blockers to reach Release Candidate:
1. **J live wiring CODE is done** (2026-08-04): process_block calls the canonical
   `validate_block_jackpot` gate BEFORE `ConnectBlock` (the SOLE keyless authorization =
   byte-exact match to the reconstruction from pre-block reserve + this block's DTD winner +
   history-derived rollover), the block loop grants the narrowest exemption (skip R2/signature
   + G1 governance only for the canonical jackpot at a jackpot height), and the mempool
   rejects `TX_TYPE_JACKPOT` explicitly. ctest 101/101. **Remaining:** the regtest **harness**
   (real node+miner) to PROVE end-to-end acceptance/disconnect/reorg/restart/reindex, the
   **miner/block-template** jackpot construction, and testnet + soak. The harness is blocked
   on the incoherent testnet schedule (V15=300 < DTD=7100) which must be lowered coherently.
2. **Regtest/testnet infra**: lower testnet DTD schedule so V15+DTD+J are exercisable; a live fork+jackpot+reorg soak (needs bitcoind for the BTC leg).
3. **EVM contract audit** decision before any SafeERC20 landing/deploy.
4. **Node-upgrade rollout plan** before the public Explorer banner is deployed.

## Deliberately NOT enabled / done (by design)
- Mainnet BTC capability (gate hardwired OFF; code is dormant behind a build option).
- EVM contract change (held in a worktree for an audited PR).
- Any main-branch merge or production deploy (founder decision).
- No `$10`/fiat/purchase jackpot-eligibility rule (rejected on consensus grounds).
