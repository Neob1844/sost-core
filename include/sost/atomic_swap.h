// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap HTLC — V13 candidate scaffolding (DORMANT)
// =============================================================================
//
// THIS IS SCAFFOLDING ONLY.
//
// This header declares the activation gate for a future native HTLC
// (Hashed-Time-Locked Contract) transaction primitive that would enable
// non-custodial crypto-to-crypto atomic swaps between SOST and BTC / ETH /
// USDT / USDC / BNB / PAXG / XAUT.
//
// The full design lives in:
//   - docs/design/ATOMIC_SWAP_IMPLEMENTATION_MAP.md
//   - docs/design/ATOMIC_SWAP_HTLC_IMPLEMENTATION_PLAN.md
//   - docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md
//
// NO HTLC transaction type is added to include/sost/transaction.h in this
// scaffolding. NO validation rules are added to src/tx_validation.cpp.
// NO wallet / RPC paths exist yet. The constant below is DEFINED but is
// NOT REFERENCED from any .cpp file in this commit, so it is a no-op
// at runtime by construction.
//
// Future Phase 3 (a separate, dedicated multi-week sprint) will add:
//   - OUT_HTLC_LOCK   (proposed 0x12) — typed output locking SOST under hashlock+timelock
//   - OUT_HTLC_CLAIM  (proposed 0x13) — spend path requiring preimage before timeout
//   - OUT_HTLC_REFUND (proposed 0x14) — spend path requiring timeout
//   - serialization, mempool acceptance, block-validation rules
//   - wallet builders + RPC endpoints (createhtlclock, claimhtlc, refundhtlc,
//     decodehtlc, gethtlcstatus)
//   - exhaustive unit + integration + adversarial tests (~20+ test cases)
//   - external review of cryptographic and economic safety
//   - then flip ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT from INT64_MAX to a
//     finite block height in a single one-line activation commit.
//
// Rollback: revert to INT64_MAX. Same single-line change. No fork.
//
// PRECEDENT this file follows verbatim:
//   - include/sost/gold_vault_slice1.h    (GV_SLICE1_ACTIVATION_HEIGHT)
//   - include/sost/params.h               (BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT)
//   Both define a constant at INT64_MAX, document the activation procedure,
//   and expose a `is_active_at(height)` helper that returns false while
//   the gate is at the sentinel.
//
// =============================================================================
#pragma once

#include <cstdint>
#include <climits>

namespace sost {

// -----------------------------------------------------------------------------
// Activation gate
// -----------------------------------------------------------------------------
//
// INT64_MAX = OFF (sentinel). While this constant equals INT64_MAX the
// helper `atomic_swap_htlc_active_at()` returns false for every height.
// This is the bit-identical behaviour required for V13 deployment in the
// "scaffolding only — no consensus impact" mode.
//
// To activate the rule in a future commit, the operator MUST first land
// the full Phase 3 implementation (output types, validation rules,
// serialization, mempool, block validator, wallet, RPC, tests, external
// review). Then in a SEPARATE one-line activation commit, replace
// INT64_MAX with the chosen activation block height.
//
// At the time this scaffolding header is committed, the project's earliest
// realistic activation candidate is V14 (block 15000). V13 (block 12000)
// is feasible only if Phase 3 can be completed, tested, and externally
// reviewed before the V13 freeze — which the implementation map flags as
// extremely unlikely given the remaining V13 cycle length.
// SAFETY-CLOSED. Gate moved BACK to INT64_MAX after Phase 3A scope-B
// (commit c8a315a5) shipped HTLC_LOCK structural validation only.
// HTLC_CLAIM and HTLC_REFUND spending paths are NOT yet implemented,
// so activating LOCK at any finite height would allow users to create
// a LOCK output that has no spend path — locking SOST permanently.
// To prevent any accidental loss-of-funds even in dev / test mode, the
// gate stays at INT64_MAX until ALL THREE of the following are true:
//
//   1. HTLC_CLAIM validation rules are implemented and tested
//      (preimage check, signature, timeout check, all adversarial
//      tests passing: wrong preimage, claim after timeout, etc.).
//   2. HTLC_REFUND validation rules are implemented and tested
//      (signature, timeout check, all adversarial tests passing:
//      refund before timeout, refund after claim, etc.).
//   3. External cryptographic and economic review of the full
//      LOCK + CLAIM + REFUND set has been completed.
//
// V14_HEIGHT is the INTENDED activation height when those gates are
// met; the constant is kept here so the single-line flip back to
// V14_HEIGHT is trivial when conditions are satisfied. Until then:
//   - LOCK outputs cannot appear in any valid block (R11 rejects).
//   - CLAIM / REFUND tx_types cannot appear (no validation yet
//     anyway, but R2_BAD_TX_TYPE would also reject).
//   - Pre-activation chain replay is bit-identical to the pre-patch
//     state for all historical and future blocks while the gate
//     stays at INT64_MAX.
//
// Rollback discipline: never flip this gate to a finite value
// without verifying the 3-condition checklist above. The flip is a
// single-line change and must be paired with a unit-test run + a
// full ctest --output-on-failure run before the commit lands.
inline constexpr int64_t V14_HEIGHT = 15000;
inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX;

// -----------------------------------------------------------------------------
// is_height_active helper
// -----------------------------------------------------------------------------
//
// Returns true iff atomic-swap HTLC validation rules should be enforced
// at the given block height. With the gate at INT64_MAX this always
// returns false — every call site is a guaranteed no-op.
//
// Once Phase 3 lands, validators must call this helper at every consensus
// decision point that touches HTLC outputs / inputs. The helper is the
// SINGLE source of truth for the activation height.
inline constexpr bool atomic_swap_htlc_active_at(int64_t height) {
    return height >= ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
}

} // namespace sost
