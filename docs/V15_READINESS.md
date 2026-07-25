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
| Historical Jackpot (J) — live wiring | ❌ | — | ❌ | serialization dispatch, reserve discovery, block validation, Connect/Disconnect, reorg, integration tests |
| Explorer V15 (25,000/25,290/30,000) | ✅ | ✅ 24 (gateway) | ❌ (not deployed) | coordinate deploy with node rollout |
| Consumer swap dashboard | ✅ | parse-validated | ❌ (founder-testing) | real quotes need counterparty; not deployed |
| Atomic Swap — policy layer (timeout/swapId/preimage/RPC) | ✅ | ✅ 49 | n/a (off-chain) | route coordinator/orderbook through it |
| Atomic Swap EVM — contract (SafeERC20 + balance-delta) | ⏸ held | ✅ 60 Foundry | ❌ | **fund-custody change — needs external audit before landing/deploy** |
| Atomic Swap BTC — HTLC signing lifecycle | ✅ (gated OFF) | ✅ 121 ON / 50 OFF | ❌ | live bitcoind regtest (no infra), external crypto review; gate stays OFF |

## Release gates
**V15 CONSENSUS:** T ✅ · T tests ✅ · J core ✅ · J live wiring ❌ · activation-boundary (T) ✅ · reorg ❌ · regtest ❌ · testnet ❌ · soak ❌ → **NOT MET**
**EVM SWAP:** create/fund/detect/redeem/refund logic present · timeout policy ✅ · persistence partial · E2E ❌ · contract audit ❌ → **NOT MET**
**BTC SWAP:** script ✅ · funding ✅ · sign ✅ · redeem/refund ✅ · preimage ✅ · regtest ❌ · review ❌ → **NOT MET** (gate stays OFF)
**DASHBOARD:** UI ✅ · backend hooks partial · history ✅ · unsupported pairs disabled ✅ · deployed ❌ → **NOT MET**

## Overall verdict
**V15 READY FOR TESTNET/REGTEST ONLY (partial).** Real blockers to reach Release Candidate:
1. **J live wiring** (the primary consensus gap) + its integration/reorg tests.
2. **Regtest/testnet infra**: lower testnet DTD schedule so V15+DTD+J are exercisable; a live fork+jackpot+reorg soak (needs bitcoind for the BTC leg).
3. **EVM contract audit** decision before any SafeERC20 landing/deploy.
4. **Node-upgrade rollout plan** before the public Explorer banner is deployed.

## Deliberately NOT enabled / done (by design)
- Mainnet BTC capability (gate hardwired OFF; code is dormant behind a build option).
- EVM contract change (held in a worktree for an audited PR).
- Any main-branch merge or production deploy (founder decision).
- No `$10`/fiat/purchase jackpot-eligibility rule (rejected on consensus grounds).
