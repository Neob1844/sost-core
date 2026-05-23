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
// Phase 3A activation flip: gate moved from INT64_MAX (sentinel OFF) to
// V14_HEIGHT (= 15000). HTLC_LOCK validation rules in src/tx_validation.cpp
// fire only for blocks at height >= 15000. Pre-activation chain replay
// (heights 0..14999) is bit-identical because HTLC_LOCK output type was
// reserved-but-rejected by R11 for those heights. The V14 hard fork
// activates these rules at block 15000. Rollback to INT64_MAX is a single
// one-line revert if any safety issue surfaces before the V14 freeze.
inline constexpr int64_t V14_HEIGHT = 15000;
inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT;

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
