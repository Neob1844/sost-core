// lottery.h — V11 Phase 2 component D: Proof-of-Participation lottery
//
// Spec: docs/V11_SPEC.md §4 + §10.5 (jackpot rollover)
// Status (C5): is_lottery_block — pure frequency function. Real
//              implementation (header-only inline). All other entry
//              points still SKELETON / abort-on-call (eligibility,
//              winner picking, rollover state, reorg) until C6+.
// Activation: V11_PHASE2_HEIGHT (params.h) — currently INT64_MAX.
//
// Lottery frequency schedule (height-only, no chain state needed):
//   With H = V11_PHASE2_HEIGHT and W = LOTTERY_HIGH_FREQ_WINDOW = 5000,
//   For h in [H, H + W):   triggered  ⟺  (height % 3) != 0  (2-of-3 bootstrap)
//   For h >= H + W:        triggered  ⟺  (height % 3) == 0  (1-of-3 permanent)
//
// CRITICAL: the rule uses `height % 3`, NOT `(height - H) % 3`. The
// schedule is anchored to absolute block height so a hypothetical
// reorg across the activation boundary cannot shift the trigger
// pattern. See is_lottery_block below.
//
// Eligibility (C6+):
//   addrs with at least 1 block in [0, h-1]
//     minus any block-reward winner in
//       [h - LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW, h-1]   (= 5 default)
//     minus the miner of block h itself.
//
// RNG domain tag (C6+):
//   "SOST_LOTTERY_V11" — defined as LOTTERY_RNG_DOMAIN below; consumed
//   by the deterministic winner-picking helper. Treated as raw bytes,
//   no trailing NUL.
//
// Coinbase shape on a triggered block (C8):
//   50 % miner / 50 % lottery winner (vs normal 50 / 25 / 25).
//
// Jackpot rollover (§10.5): if the eligibility set is empty on a
// triggered block, the would-be 50 % lottery share accumulates into
// the chain-state variable `pending_lottery_amount`. The next
// triggered block with a non-empty eligibility set pays
// `share + pending`. Implementation lands in C7-C8.
#pragma once

#include "sost/types.h"
#include "sost/params.h"      // V11_PHASE2_HEIGHT, LOTTERY_HIGH_FREQ_WINDOW
#include "sost/tx_signer.h"   // PubKeyHash
#include <cstdint>
#include <optional>
#include <vector>

namespace sost::lottery {

// ---------------------------------------------------------------------------
// Domain-separation tag for the deterministic lottery RNG.
// Consumed by pick_winner (C6+) as:
//   sha256(LOTTERY_RNG_DOMAIN || prev_block_hash || height_le)
// Treated as raw bytes; the trailing NUL is NOT included. Length helper
// is exposed for callers that prefer std::string_view-style access.
// ---------------------------------------------------------------------------
inline constexpr char    LOTTERY_RNG_DOMAIN[]    = "SOST_LOTTERY_V11";
inline constexpr size_t  LOTTERY_RNG_DOMAIN_LEN  = sizeof(LOTTERY_RNG_DOMAIN) - 1;

// ---------------------------------------------------------------------------
// V11 Phase 2 — height-only lottery trigger rule (C5, real, pure).
//
// Implementation is `inline` so this stays a header-only function and
// does NOT require src/lottery.cpp to be linked into sost-core. The
// remaining lottery functions (eligibility_set, pick_winner, apply_block,
// etc.) keep their abort-on-call stubs in src/lottery.cpp until C6+
// and are NOT linked into the production library yet.
//
// Rules:
//   1) phase2_height == INT64_MAX        →  return false (sentinel: Phase 2 dormant)
//   2) height < phase2_height            →  return false (pre-Phase 2 block)
//   3) offset = height - phase2_height
//      if offset < LOTTERY_HIGH_FREQ_WINDOW:
//          return (height % 3) != 0     (2-of-3 bootstrap, first 5000 blocks)
//      else:
//          return (height % 3) == 0     (1-of-3 permanent, after bootstrap)
//
// Production guarantee: while V11_PHASE2_HEIGHT == INT64_MAX in
// params.h, this function returns false for every real chain height.
// Tests pass a finite phase2_height to exercise the active path.
//
// CONSENSUS-CRITICAL: the schedule MUST be height-anchored, NOT
// offset-anchored, so a reorg across V11_PHASE2_HEIGHT does not
// shift the lottery cadence. Both miner and validator MUST go through
// this single helper.
//
// Phase 2 — REAL implementation. This is the only lottery function
// that does NOT abort.
inline bool is_lottery_block(int64_t height, int64_t phase2_height) {
    if (phase2_height == INT64_MAX) return false;
    if (height < phase2_height)     return false;

    const int64_t offset = height - phase2_height;
    if (offset < LOTTERY_HIGH_FREQ_WINDOW) {
        // Bootstrap: 2 of every 3 blocks.
        return (height % 3) != 0;
    }
    // Steady state: 1 of every 3 blocks, permanently.
    return (height % 3) == 0;
}

// ---------------------------------------------------------------------------
// Trigger result for a given height. Older 3-arg API kept aborting in
// the skeleton for backward-compat with tests written under the
// previous draft. Prefer is_lottery_block above.
//
// PHASE 2 — NOT IMPLEMENTED (still abort-on-call until C6+).
bool is_triggered(int64_t height,
                  int64_t v11_phase2_height,
                  int64_t high_freq_window);

// Eligibility set for height h. Implemented as deterministic scan over
// chain history (or, in production, a maintained index). Returns the
// set of candidate winner addresses sorted lexicographically — the
// caller can then index into this vector with the deterministic RNG.
//
// `recent_block_winners` carries miner addresses for heights
// [h - exclusion_window, h-1]. `current_block_miner` is the miner of h
// itself, also excluded.
//
// PHASE 2 — NOT IMPLEMENTED.
std::vector<PubKeyHash> eligibility_set(
    int64_t height,
    const std::vector<PubKeyHash>& addrs_with_block_since_genesis,
    const std::vector<PubKeyHash>& recent_block_winners,
    const PubKeyHash& current_block_miner,
    int32_t exclusion_window);

// Deterministic winner selection. Seed is derived as
//   sha256("SOST/POP-LOTTERY/v11" || prev_block_hash || height).
// The 64-bit reduction `seed_u64 % |E(h)|` selects the index into the
// lex-sorted eligibility set.
//
// Returns std::nullopt iff E(h) is empty (caller then applies rollover
// per §10.5 by adding the would-be share to pending_lottery_amount and
// emitting only the miner subsidy output).
//
// PHASE 2 — NOT IMPLEMENTED.
std::optional<PubKeyHash> pick_winner(const Bytes32& prev_block_hash,
                                   int64_t height,
                                   const std::vector<PubKeyHash>& eligibility_sorted);

// Jackpot rollover state. Lives in chain state (initialised to 0 at
// V11_PHASE2_HEIGHT, advanced block-by-block, restored from undo data
// on reorg). Cap: none.
struct RolloverState {
    uint64_t pending_lottery_amount = 0;  // stocks
};

// Per-block transition. `triggered` and `eligibility_empty` are inputs;
// `lottery_share` is the 50% subsidy amount the lottery would pay this
// block. Mutates `state` in place and writes the pre-block value into
// `out_pending_before` so the caller can save it as undo data.
//
// PHASE 2 — NOT IMPLEMENTED.
struct TransitionInputs {
    bool     triggered;
    bool     eligibility_empty;
    uint64_t lottery_share;
};

struct TransitionOutputs {
    uint64_t pending_before_block;       // for undo data
    uint64_t winner_payout;              // 0 if no winner this block
    bool     emit_winner_output;         // false on rollover blocks
};

void apply_block(RolloverState& state,
                 const TransitionInputs& in,
                 TransitionOutputs& out);

// Reorg helper — restore pending using the saved undo value.
// PHASE 2 — NOT IMPLEMENTED.
void undo_block(RolloverState& state, uint64_t pending_before_block);

} // namespace sost::lottery
