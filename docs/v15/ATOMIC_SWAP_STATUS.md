# Atomic Swap status (V15 release-scope) — verified at HEAD

Product decision: Atomic Swap is MANDATORY for V15 RELEASE readiness (see project memory). This is
the real inventory verified at HEAD (not the stale summary), plus what was safely closed on the
miner box vs what needs the second (non-miner) box + external artifacts.

## Component matrix (verified at HEAD)
| # | Component | Implemented | Tested | Audited | Activated | Blocking |
|---|-----------|-------------|--------|---------|-----------|----------|
| 1 | EVM HTLC (AtomicSwapHTLC.sol) | ✅ | ✅ 57 Foundry + C++ unit | ❌ external | ✅ mainnet @ V14_5=16000 (chain 20802) | external audit before real-fund custody |
| 2 | Policy layer | ✅ | ✅ `atomic-swap-policy` ctest | n/a (pure policy) | n/a (no gate) | none |
| 3 | BTC HTLC (script/lock) | ✅ code | ✅ `atomic-swap-btc-script`, `htlc-lock` | ❌ | ❌ `SOST_BTC_HTLC_SIGNING` OFF (funding path = stub) | bitcoind regtest real + crypto review |
| 4 | BTC signing flow | ✅ code | ✅ `atomic-swap-btc-signing`, `btc-test-vectors` | ❌ | ❌ gated OFF | regtest real |
| 5 | BTC redeem path | ✅ code | ✅ `htlc-helpers`, `htlc-rpc` | ❌ | ❌ | regtest real |
| 6 | BTC refund path | ✅ code | ✅ `htlc-expired-lock-template` | ❌ | ❌ | regtest real |
| 7 | timeout handling | ✅ | ✅ Foundry (before/after timeout) + `htlc-expired-lock-template` | partial | EVM ✅ / BTC ❌ | BTC regtest |
| 8 | preimage handling | ✅ | ✅ Foundry (wrong-preimage reject) + `atomic-swap-coordinator` | partial | EVM ✅ / BTC ❌ | BTC regtest |
| 9 | swapId uniqueness | ✅ | ✅ Foundry (duplicate-swapId reject, native+ERC20) | partial | EVM ✅ | — |
| 10 | EVM SafeERC20 contract | ✅ | ✅ 57 Foundry (reentrancy, no-return/failing/fee-on-transfer token, zero-checks, fund conservation) | ❌ external | ❌ undeployed | external audit before real funds |
| 11 | dashboard | ✅ partial | ⚠️ not E2E | n/a | ❌ not deployed | E2E vs lab + quotes/counterparty |
| 12 | quotes / orderbook / counterparty | ✅ code | ✅ `atomic-swap-orderbook` (unit) | n/a | ❌ | real counterparty/liquidity infra |
| 13 | RPC / API | ✅ | ✅ `atomic-swap-htlc-rpc`, `atomic-swap-status` | n/a | EVM ✅ | — |
| 14 | operator workflow | ✅ code | ✅ `atomic-swap-session`, `atomic-swap-watcher` | n/a | ❌ | E2E + go-live |
| 15 | failure/recovery workflow | ✅ code | ✅ `atomic-swap-e2e-sim` (sim), `atomic-swap-coordinator` | n/a | ❌ | real regtest recovery/reorg |

## Closed on the miner box (safe, no SbPoW mining, does not touch the miner)
- **B4 EVM Foundry suite: PASS 57/57, 0 failed** (`contracts/atomic-swap`, forge 1.5.1) —
  covers SafeERC20 reentrancy, non-standard ERC20 (no-return / failing / fee-on-transfer),
  zero-value/address rejects, timeout, redeem/refund (native+ERC20), double-claim/refund reject,
  duplicate-swapId reject, wrong-preimage reject, fund conservation, no-owner (access control),
  plain-ETH reject. Evidence: `artifacts/v15-final-validation/atomic-swap-foundry.log`.
- **15 Atomic-Swap C++ unit/sim tests: PASS** (inside ctest testnet 102/102 + mainnet): btc-script,
  btc-signing, btc-test-vectors, coordinator, e2e-sim, htlc-lock, htlc-helpers, htlc-rpc, orderbook,
  watcher, status, session, policy, htlc-block-path-v14-5, htlc-expired-lock-template.

## Requires the 2nd (non-miner) box + tooling/artifacts
- **B2 BTC regtest REAL** (redeem + refund, adversarial): `bitcoind` is NOT installed here; needs a
  regtest node on the 2nd box. All BTC paths are unit/sim-tested only until then.
- **B3 cross-chain E2E real atomicity**: needs bitcoind regtest + both chains.
- **B5 dashboard E2E**: needs a lab environment + quotes/counterparty.
- **B6 security threat-model review**: doable as analysis (next), but the real reorg/regtest items
  depend on B2.

## External blockers (start now, long lead time)
- **EVM SafeERC20 external audit** — required before the contract custodies real funds →
  `WAITING_EXTERNAL_AUDIT`. Multi-week lead time; start in parallel immediately, do NOT wait for the
  consensus SbPoW run or the RC.
- **Counterparty / orderbook / liquidity infra** → `WAITING_EXTERNAL_LIQUIDITY_INFRA`.

## Readiness
**ATOMIC SWAP READINESS: NOT READY** — EVM contract suite + all C++ unit/sim tests are GREEN and the
EVM HTLC is live @16000, but: BTC HTLC is gated OFF (needs regtest-real redeem/refund + crypto
review), the EVM contract is unaudited/undeployed (external audit), and the dashboard has no E2E.
None is a discovered defect; the gaps are real-environment tests + external audit/liquidity.
