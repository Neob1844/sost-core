# Atomic Swap Coordinator — Internal Review (Phase 4C-1)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Status:** code-complete, internally-tested. Pure local logic; **no IO,
no signing, no broadcast, no keys, no HTTP, no chain observation**.
**Gate:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (unchanged).
**BTC signing flag:** `SOST_BTC_HTLC_SIGNING = OFF` (unchanged).

---

## 1. Purpose

The coordinator is the wallet-side state-machine layer between
chain-observation modules (Phase 4A-2 BTC signing + Phase 4B-1 EVM
contract + the existing SOST-side wallet helpers) and the user-facing
UI. It encodes:

  - The legal sequence of events in an atomic swap.
  - Pre-computed timeout-order validation.
  - Next-safe-action hints for the UI.
  - Recovery-path hints for the unhappy paths.

It does NOT decide ANY chain-touching action by itself. Every state
transition is driven by a user-/wallet-supplied event that says "I
have OBSERVED this thing on-chain" or "I have ACTED this way locally".
The coordinator never queries a chain, never reads a private key,
never builds a transaction, never signs, never broadcasts.

## 2. Scope guarantees

  - `SOSTEscrow.sol` — bit-identical, not touched.
  - PoPC DEX surface — not touched.
  - SOST consensus rules R17-R24 — bit-identical.
  - `include/sost/atomic_swap.h` activation gate — bit-identical
    (still `INT64_MAX`).
  - `SOST_BTC_HTLC_SIGNING` CMake flag — bit-identical (still OFF).
  - No new external dependency.

## 3. State machine

| State | Description |
|---|---|
| `Draft` | Session not yet created OR session created with invalid timeout ordering. |
| `AwaitingSostLock` | Initial active state; the SOST-side LOCK has not been observed yet. |
| `AwaitingCounterpartyLock` | SOST LOCK confirmed; waiting for the counterparty-chain LOCK. |
| `BothLocked` | Both LOCKs confirmed; waiting for preimage knowledge. |
| `ClaimReady` | Both LOCKs confirmed AND preimage known; user can claim. |
| `Claimed` | Terminal. A CLAIM transaction on one chain has been observed (reveals the preimage). |
| `RefundAvailable` | Timeout reached after at least one LOCK; refund path open. |
| `Refunded` | Terminal. A REFUND transaction has been observed. |
| `Expired` | Terminal. Timeout reached BEFORE the SOST LOCK was observed; no LOCK on any chain to refund. |
| `Failed` | Terminal. The wallet (or the user) marked the session as failed. |

## 4. Events

| Event | Notes |
|---|---|
| `CreateSession` | Initial event; takes `SwapParams`; invoked via `CreateSession()`, NOT `Apply()`. |
| `MarkSostLockSeen` | The wallet confirmed the SOST-side LOCK UTXO. |
| `MarkCounterpartyLockSeen` | The wallet confirmed the counterparty-chain LOCK. |
| `MarkPreimageKnown` | The user now knows the preimage (typed it in, or read it from a counterparty CLAIM). |
| `MarkSostClaimSeen` | A CLAIM on the SOST side has been broadcast/confirmed. |
| `MarkCounterpartyClaimSeen` | A CLAIM on the counterparty chain has been broadcast/confirmed. |
| `MarkSostRefundSeen` | A REFUND on the SOST side has been broadcast/confirmed. |
| `MarkCounterpartyRefundSeen` | A REFUND on the counterparty chain has been broadcast/confirmed. |
| `MarkTimeoutReached` | The wallet observed that the configured refund_height arrived. |
| `MarkFailure` | The wallet (or the user) explicitly failed the session. |

## 5. Timeout-order discipline

Atomic-swap safety requires:

  - **Initiator** locks first; their refund window MUST open LAST so
    the responder has time to complete the swap. Formally: `T1_initiator > T2_responder + safety_margin`.
  - **Responder** locks second; their refund window opens FIRST.

The coordinator translates this into:

  - If `role == Initiator`: `sost_refund_opens_after_counterparty` MUST be `true`.
  - If `role == Responder`: `sost_refund_opens_after_counterparty` MUST be `false`.
  - AND `observed_safety_margin_blocks >= safety_margin_min_blocks` (default 6).

The coordinator cannot independently compare block-times across two
chains — the wallet must normalise. Any wallet that constructs a swap
must implement chain-aware block-time conversion before populating
`SwapParams`.

When timeout-order validation fails, `CreateSession` returns `ok=true`
but stays in `Draft`, and `risk_flags()` exposes
`TIMEOUT_ORDER_INVALID` (and/or `TIMEOUT_MARGIN_TOO_SMALL`). Any
subsequent `Apply()` other than `MarkFailure` is rejected. The wallet
must rebuild the session with corrected parameters.

## 6. Test coverage

30 assertions in `tests/test_atomic_swap_coordinator.cpp`:

```
T1   Draft -> AwaitingSostLock after CreateSession (5 sub-checks)
T2   SOST lock seen -> AwaitingCounterpartyLock
T3   both locks seen -> BothLocked
T4   preimage known after BothLocked -> ClaimReady
T5   ClaimReady -> Claimed via MarkCounterpartyClaimSeen
T6   BothLocked + timeout -> RefundAvailable
T7   RefundAvailable -> Refunded
T8   illegal MarkSostClaimSeen from AwaitingSostLock rejected
T9   MarkFailure idempotent on Failed; non-failure events on Failed rejected
T10  invalid timeout ordering keeps Draft, exposes risk_flag, refuses Apply
T11  preimage observed mid-flow + later lock -> jumps directly to ClaimReady
T12  MarkFailure -> Failed; further events rejected
T13  accessor API surface present and consistent (5 sub-checks)
T14  static_assert + runtime: SOST consensus gate == INT64_MAX
T15  runtime: BTC signing backend OFF
ExtraR  Responder ordering rule reversed and validated
ExtraM  safety margin too small exposes TIMEOUT_MARGIN_TOO_SMALL
ExtraS  CreateSession twice rejected
ExtraA  Apply before CreateSession rejected
ExtraE  pre-Lock timeout -> Expired; Expired is terminal
```

Result: 30 / 30 passed. 0 failed.

## 7. Static checks

| Pattern | Hits in new code |
|---|---|
| `broadcast` | 0 |
| `sendrawtransaction` | 0 |
| `http://` / `https://` | 0 |
| `socket(` / `connect(` | 0 |
| `curl` | 0 |
| `private key` / `WIF` / `PRIVATE_KEY` | 0 (the struct fields refer to the wallet's observation flags, not key material) |
| `selfdestruct` / `delegatecall` | 0 |

`SOSTEscrow.sol` and any `contracts/popc/` / `popc/` files: zero diff
vs `origin/main`.

## 8. What is NOT in this commit

  - Wallet integration (chain observation drivers that feed events
    into the coordinator).
  - UI components that render `next_safe_action()` / `recovery_path()`.
  - BTC signing path (Phase 4A-2 — vendored library).
  - EVM contract deployment (the contract exists at
    `contracts/atomic-swap/AtomicSwapHTLC.sol` per Phase 4B-1, not
    deployed).
  - End-to-end testnet swaps.
  - External cryptographic + economic review.

## 9. Activation prerequisites

The coordinator being internally-tested is not sufficient to flip the
SOST gate. The full activation
(`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT`) still requires:

  1. Phase 4A-2 — vendored BTC signing library + BIP-143/173 vectors.
  2. THIS coordinator — done.
  3. End-to-end testnet swaps (SOST testnet ↔ Bitcoin testnet,
     SOST testnet ↔ Sepolia ETH, SOST testnet ↔ Sepolia ERC-20)
     showing happy path AND timeout-refund path.
  4. External cryptographic + economic review of the full stack.

See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md`.
