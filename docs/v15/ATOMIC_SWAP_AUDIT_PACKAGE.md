# SOST ⇄ BTC / EVM Atomic Swap — External Audit Package (entry point)

Single index for an external reviewer. Everything here is **regtest / test-only**. BTC mainnet is
**not** activated and nothing in this package activates it.

## Hard invariants (verify these first — they must hold in the audited build)
- `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` — the SOST HTLC consensus gate is OFF.
- Default node build (`SOST_BTC_HTLC_SIGNING` unset) links **no libwally** and every BTC signing
  function returns `ok=false`; Option A build shows **0 `wally_` symbols**.
- Runtime `SOST_BTC_ATOMIC_SWAP_ENABLED` default OFF; `NullBitcoinBackend` fail-closed.
- No consensus change, no wire change, no mainnet broadcast path.

## What to audit (scope)
1. **BTC HTLC script + signing** — `src/atomic_swap_btc.cpp` (`BuildBtcHtlcRedeemScript`, BIP-199
   layout), `src/atomic_swap_btc_signing.cpp` (BIP-143 segwit-v0 sighash, Low-R/Low-S ECDSA, P2WSH
   witness assembly, `EncodeP2WSHAddress`, `SignBtcHtlcClaim/Refund`).
2. **EVM HTLC** — `contracts/atomic-swap/src/AtomicSwapHTLC.sol` (native + ERC20 lock/claim/refund).
3. **SOST-side orchestration** — `bitcoin_backend`, `btc_swap_state`, `btc_funding`, `btc_watch`
   (state machine, funding, reorg-aware watcher + `ReconcileBtcSwapWithChain`).
4. **Cross-chain binding** — shared `hashlock = sha256(preimage)`; preimage revealed by the BTC
   claim witness feeds the SOST leg.

## Verified test evidence (as of this package)
| Leg | Test | Result |
|---|---|---|
| EVM | `forge test` (contracts/atomic-swap) | **57/57** (lock/claim/refund native+ERC20, timeouts, wrong preimage, double-spend, reentrancy, trustless) |
| SOST C++ | `ctest` atomic-swap targets | green (script/vectors/signing/coordinator/watcher/funding/state/rpc/orderbook/session/policy) |
| BTC signing (ON) | `test-atomic-swap-btc-signing` | **121/0** incl. BIP-143 native-P2WSH known-answer vector |
| BTC live regtest | claim path | ACCEPTED+confirmed, witness reveals preimage = secret (`BTC_REGTEST_E2E_RESULTS.md`) |
| BTC live regtest | refund path | early refund REJECTED `non-final` (CLTV enforced), post-timeout ACCEPTED |
| BTC live regtest | reorg/recovery | claim returns to mempool on `invalidateblock`, reconfirms, preimage intact |

Repro drivers/scripts: `scripts/btc_htlc_regtest_driver.cpp`, `scripts/otc_rehearsal_btc_regtest.sh`,
`scripts/btc_htlc_regtest_reorg_test.sh`; guide `docs/V15_OTC_BTC_REGTEST_GUIDE.md`.

## Reference documents (in this repo)
- `docs/v15/ATOMIC_SWAP_THREAT_MODEL.md` — threat enumeration.
- `docs/v15/ATOMIC_SWAP_AUDIT_SCOPE.md` — scope boundaries.
- `docs/v15/ATOMIC_SWAP_STATUS.md`, `docs/v15/BTC_HTLC_COMPLETION.md` — implementation status.
- `docs/v15/BTC_REGTEST_E2E_RESULTS.md` — live regtest evidence (claim/refund/negative/reorg).
- `docs/v15/BTC_ATOMIC_SWAP_RUNBOOK.md` — operator runbook.

## Known limitations / explicitly NOT done (auditor should weigh these)
- `SignBtcHtlcLockFunding` is IMPLEMENTED + regtest-validated (real code-driven funding P2WPKH->P2WSH); `EncodeP2WPKHAddress` added for funder addresses.
- **No external cryptographic review yet** — this package requests exactly that, plus an adversarial
  fee/locktime review, BEFORE any consideration of enabling `SOST_BTC_HTLC_SIGNING` outside a lab,
  and well before any `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` discussion.
- Live regtest exercises the happy paths + CLTV rejection + a claim-block reorg; funding-reorg /
  restart re-broadcast is covered by `btc_watch` unit tests, not a live funding-reorg run.
- Byte-order gotcha for reviewers reproducing: pass `lock_txid` to the signer in libwally internal
  (little-endian) order — reverse the big-endian txid `bitcoin-cli` displays.

## Requested auditor deliverables
1. Independent review of the BIP-143 sighash + witness assembly against the Bitcoin spec.
2. Adversarial fee / locktime / dust review of claim & refund construction.
3. EVM contract review (reentrancy, ERC20 edge cases, timelock correctness).
4. Cross-chain protocol review (preimage handling, refund vs claim race, watcher reorg logic).
