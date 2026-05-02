// lottery.h — V11 Phase 2 component D: Proof-of-Participation lottery
//
// Spec: docs/V11_SPEC.md §4 + §10.5 (jackpot rollover)
// Status: SKELETON — types declared, functions not implemented.
// Activation: V11_PHASE2_HEIGHT (TBD, see params.h once Phase 2 lands).
//
// Lottery frequency schedule, with H = V11_PHASE2_HEIGHT and
// W = LOTTERY_HIGH_FREQ_WINDOW = 5000:
//   For h in [H, H+W):   triggered  ⟺  (h - H) % 3 != 2  → 2-of-3
//   For h >= H + W:      triggered  ⟺  (h - H) % 3 == 0  → 1-of-3
//
// Eligibility:
//   addrs with at least 1 block in [0, h-1]
//     minus any block-reward winner in [h - LOTTERY_REWARD_EXCLUSION_WINDOW, h-1]
//     minus the miner of block h itself.
//
// Coinbase shape on a triggered block:
//   50% miner / 50% lottery winner (vs normal 50 / 25 / 25).
//
// Jackpot rollover (§10.5): if the eligibility set is empty on a
// triggered block, the would-be 50% lottery share accumulates into a
// chain-state variable `pending_lottery_amount`. The next triggered
// block with a non-empty eligibility set pays `share + pending`.
#pragma once

#include "sost/types.h"
#include "sost/tx_signer.h"   // PubKeyHash
#include <cstdint>
#include <optional>
#include <vector>

namespace sost::lottery {

// Trigger result for a given height. The schedule is purely a function
// of height once V11_PHASE2_HEIGHT and LOTTERY_HIGH_FREQ_WINDOW are
// fixed; eligibility and rollover state live elsewhere.
//
// PHASE 2 — NOT IMPLEMENTED.
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
