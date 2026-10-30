# Security advisory 2026-10-30 — AtomicSwapHTLCv2 asset-kind check (F-1)

| Field | Value |
|---|---|
| Component | `contracts/atomic-swap/src/AtomicSwapHTLCv2.sol` (EVM hash-time-locked swap contract, version 2) |
| Severity | **Critical** for any deployed instance that holds native ETH/BNB |
| Affected source | every revision of `AtomicSwapHTLCv2.sol` from commit `3199e546` (2026-09-29, first version of v2) up to and including `e3452d79` (`main` before this fix) |
| Not affected | `AtomicSwapHTLC.sol` (v1), the SOST node/miner/wallet, SOST consensus, any SOST-chain HTLC |
| Fixed in | this branch (`AtomicSwapHTLCv2.sol`: asset kind enforced on every claim/refund path) |
| Status of deployed instances | **NOT fixed by this source change** — see below |

## Summary

`AtomicSwapHTLCv2` keeps native-coin swaps and ERC-20 swaps in one contract. In the affected revisions one of
the native-coin settlement functions did not check that the swap it was settling is a native-coin swap. As a
result, a swap of one asset kind could be settled through the path of the other kind, and native coin escrowed
by other, unrelated swaps in the same contract could be paid out to a party that never locked it. Honest swaps
in the same instance could then no longer be claimed or refunded.

Only instances that hold native coin are at risk. ERC-20 escrow of one token is not exposed to swaps of a
different token by this issue.

## Fix

Every claim and refund function now checks the asset kind of the swap before anything is moved
(native-only functions require a native swap, ERC-20-only functions require an ERC-20 swap); state is
written before any external call and a single reentrancy lock covers every state-changing entry point. A lock
of an ERC-20 swap additionally requires the token address to contain code. The fixed contract has a different
creation bytecode (`creation_bytecode_keccak256` in `contracts/atomic-swap/deploy/htlc-v2-config.json`).

Regression coverage (local EVM only): `test/AtomicSwapHTLCv2Isolation.t.sol`,
`test/AtomicSwapHTLCv2F1Differential.t.sol` (differential tests against a test-only copy of the old code,
asset-kind matrix on all four paths, fuzz and stateful solvency invariants) and the Echidna harness
`echidna/EchidnaHTLCv2F1.sol`. The fix has been reviewed internally twice; it is **not** externally audited.

## Already-deployed instances are NOT fixed

A smart contract cannot be patched in place: changing the source in this repository does **not** change any
contract that was deployed from the old source. Any instance deployed from an affected revision keeps the flaw
forever and must be treated as retired.

| Network | Address | Code | Status |
|---|---|---|---|
| Sepolia (test network, chain id 11155111) | `0x395295622fDE4702BA199e4898F85B9d85175794` | pre-fix v2 (runtime keccak `0x0aab418f…7167`, identical to the affected source apart from compiler metadata) | **RETIRED / VULNERABLE — DO NOT USE** |
| Ethereum mainnet, BNB Chain, Arbitrum, Base | none recorded | — | no SOST-published instance of v2 exists |

Read-only check on 2026-10-30 (Sepolia block 12,028,637, public RPC, `eth_getCode`/`eth_getBalance`/`balanceOf`
only, no transaction): the Sepolia instance still has the pre-fix code and holds 0 ETH and 0 of the SOST test
tokens. It was a test deployment with test funds only.

The experimental wSOST Stage 2 test deployment on Sepolia used the same test network and is also retired; it
was superseded by a later design and must not be used either:

| Sepolia contract | Address | Status |
|---|---|---|
| WSOST (Stage 2, experimental) | `0x4F71ef1D4878225eBd711216A75451F0bfF946C0` | **RETIRED — DO NOT USE** |
| QuarantineVault (Stage 2) | `0x8ef5A156cA578e779655085dc9655C79b61ee1A0` | **RETIRED — DO NOT USE** |
| GoldReserveVault (Stage 2) | `0x3cDaaD6a606a4ab77EBCd5DB421fbd1f8792534B` | **RETIRED — DO NOT USE** |
| SOSTEscrow (Model B, historical) | `0x01Eaab645DA10E79c5Bae1C38d884B4D1a68f113` | historical, **DO NOT USE** |

These are test-network contracts holding test tokens only; they have no monetary value and were never
endorsed for real funds.

## What users and integrators should do

* Do not lock, claim or refund anything through `0x395295622fDE4702BA199e4898F85B9d85175794` or any other
  instance whose creation bytecode hash is `0xbe82b2ed28271272808f25f639d66d0b308911af41fe43d50617a5d5d004deeb`.
* Before trusting any `AtomicSwapHTLCv2` address, compare its on-chain runtime code with a local build of the
  fixed source (same compiler 0.8.24, optimizer 200 runs); the configuration file lists the fixed creation hash.
* Do not deploy `AtomicSwapHTLCv2.sol` from any revision older than this fix.
* The SOST web console uses `AtomicSwapHTLC` (v1) and verifies its bytecode; it is not affected by this issue.

## Timeline

* 2026-09-29 — v2 added to `main` (`3199e546`).
* 2026-10-13 — Sepolia test instance deployed with test funds.
* 2026-10-27 — flaw found in an internal review; fix written (`07442f03`, unpublished).
* 2026-10-30 — independent re-review of the fix, differential/fuzz/invariant/Echidna tests, read-only check of
  the Sepolia instance, this advisory.

Exploit details are intentionally omitted. Report security issues to sost@sostcore.com.
