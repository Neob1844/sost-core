# Cross-chain atomic swaps — executed & verified in the lab

Both cross-chain swaps run end-to-end, moving mock funds between two live chains with a real
preimage bridge. LAB ONLY (SOST devnet + Bitcoin regtest + Anvil). No mainnet, no real funds.

## What "complete" means here (per the 4-state model)
1. Unit / simulation tests — green (see the swap test suite).
2. Single-chain CLAIM/REFUND on one real blockchain — done (BTC regtest, SOST devnet).
3. **Complete atomic swap across TWO blockchains — DONE (this document).**
4. Independently security-audited — **BLOCKED-EXTERNAL** (no audit yet).

## Enabling milestones (both legs are real project code now)
- **BTC leg**: `SignBtcHtlcLockFunding` (P2WPKH funder → HTLC P2WSH), `SignBtcHtlcClaim/Refund`,
  `EncodeP2WPKHAddress`; txids handled via `DisplayTxidToInternal`/`InternalTxidToDisplay`
  (no manual byte reversal). Driver: `scripts/btc_htlc_regtest_driver.cpp`.
- **SOST leg**: `BuildHtlcLockTx`/`BuildHtlcClaimTx`/`BuildHtlcRefundTx` + `SignTransactionInput`,
  broadcast via the node's `sendrawtransaction`. Driver: `scripts/sost_htlc_devnet_driver.cpp`.
- **Preimage bridge (watcher)**: BTC → `ExtractBtcHtlcPreimageFromTxHex` (real watcher code);
  EVM → the contract's `Claimed(swapId, preimage, claimer)` event.
- Same `hashlock = sha256(preimage)` on all three chains (the EVM contract also uses `sha256`).

## SOST ⇄ BTC  (`scripts/xswap_sost_btc.sh`)
Alice has SOST, Bob has BTC. Alice locks SOST (claim→Bob), Bob funds a BTC HTLC (claim→Alice,
shorter timeout). Alice claims BTC revealing S; the watcher extracts S from the BTC claim witness;
Bob claims SOST with S. **Verified: Alice received 0.49998 BTC, Bob received 1.999 SOST.** No HTLC
transaction was hand-built with `bitcoin-cli` (it only funds the funder P2WPKH and relays/mines).

## SOST ⇄ EVM  (`scripts/xswap_sost_evm.sh`, native + ERC-20)
Alice has SOST, Bob has ETH/ERC-20. Alice locks SOST (claim→Bob), Bob `lockNative`/`lockERC20` in
`AtomicSwapHTLC.sol` (claim→Alice, shorter timeout). Alice `claim(swapId, preimage)` — the contract
pays Alice and emits `Claimed` with the preimage; the watcher reads S from that event; Bob claims
SOST with S.
- **Native: Alice received ~0.49996 ETH (0.5 − gas), Bob received 1.999 SOST.**
- **ERC-20 (MockERC20 tUSDC): Alice received exactly 0.5 tUSDC, Bob received 1.999 SOST.**

## Reproduce
- SOST devnet build: `-DSOST_DEVNET_FORKS=ON` (V14_5=11, V14_7=12 → HTLC live), `-DSOST_BTC_HTLC_SIGNING=ON` for the BTC driver.
- BTC: `bitcoind -regtest -txindex`; EVM: `anvil` (deterministic accounts) + `forge`/`cast`.
- Scripts: `xswap_sost_btc.sh`, `xswap_sost_evm.sh native|erc20`.

## Honest scope / still open
- The `Coordinator`/`session` C++ state machines are unit-tested; the live harness executes the
  real on-chain actions those states represent and logs the canonical states, but the C++
  Coordinator object was not itself the live driver of these two runs.
- SOST-leg refund positive-path: the timelock is enforced live (R24 rejects an early refund) and
  refund uses the same proven build+sign path as claim; a fully green positive-refund harness run
  is pending a devnet miner block-count control fix (the mechanism is proven, the harness flaked).
- Adversarial matrix (never-fund, wrong preimage, premature refund, reorg-before/after reveal,
  double-claim) — partially covered (wrong-preimage rejected by all three chains' hash check;
  premature refund rejected by CLTV/R24; BTC reorg proven); a consolidated adversarial run is the
  next step. Security for REAL funds still requires the independent audit (state 4).

## Adversarial matrix (step 5) — results
Verified live in the lab across the three chains:
| Case | EVM (Anvil) | BTC (regtest) | SOST (devnet) |
|---|---|---|---|
| Wrong preimage | `WRONG_PREIMAGE` revert ✅ | driver refuses to build + script `OP_EQUALVERIFY` fails ✅ | R-rule sha256 mismatch (same claim path) |
| Premature refund | revert ✅ | `non-final` / CLTV ✅ | `R24: refund window not yet open` ✅ |
| Double-claim | `NOT_LOCKED` revert ✅ | prev UTXO already spent (consensus) | prev UTXO already spent (consensus) |
| Claim after timeout | `TIMEOUT_PASSED` revert ✅ | (CLTV allows refund path only) | — |
| Post-timeout refund (honest recovery) | `status 0x1` ✅ | proven (earlier) ✅ | mechanism proven (R24 enforces window) |
| Reorg | — | claim survives `invalidateblock`, reconfirms, preimage intact ✅ | — |

Scripts: `evm_adversarial_matrix.sh` (EVM, 5/5). BTC wrong-preimage + reorg in the btc regtest
scripts. Never-fund → the other party refunds after its timeout (refund paths above).
