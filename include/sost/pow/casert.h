// cASERT — Unified consensus-rate control system for SOST
// Includes bitsQ primary controller, equalizer, and anti-stall.
#pragma once
#include "sost/types.h"
#include "sost/params.h"
#include <vector>
#include <utility>
namespace sost {

// ---- bitsQ primary controller ----
// Computes next block's bitsQ from chain history. Deterministic.
uint32_t casert_next_bitsq(const std::vector<BlockMeta>& chain, int64_t next_height,
                           int64_t now_time = 0);

// ---- Unified cASERT decision ----
// Computes the full decision (bitsQ + equalizer profile) from chain history.
// now_time=0 for validation (no anti-stall decay).
// now_time>0 for mining (anti-stall may adjust profile downward).
CasertDecision casert_compute(const std::vector<BlockMeta>& chain,
                               int64_t next_height,
                               int64_t now_time = 0);

// Apply cASERT profile to ConvergenceX consensus params.
ConsensusParams casert_apply_profile(const ConsensusParams& base,
                                      const CasertDecision& dec,
                                      int64_t height = 0);

// V11 cascade — linear escalation, no artificial cap.
// Returns the number of profile steps to drop when a block has been
// elapsed `block_elapsed_s` seconds:
//
//   elapsed <  540 s  →  0
//   elapsed >= 540 s  →  1 + (elapsed - 540) / 60
//
// The natural floor (E7 = CASERT_H_MIN) is enforced by the caller via
// `max(E7, profile - drop)`. This function intentionally does NOT cap
// the drop value — the cascade keeps growing each 60 s past the
// activation threshold, so a chain whose natural profile is high
// (e.g. H32) can still reach E7 within ~49 minutes, well inside the
// 90-minute anti-stall window.
//
// CONSENSUS-CRITICAL: this function MUST be used identically by miner
// and verifier. Any divergence triggers a chain split. Both sides go
// through this single helper.
//
// Active for `next_height >= CASERT_V11_HEIGHT`. For pre-V11 heights
// the V9/V10 continuous formula in casert.cpp is used instead.
int32_t compute_v11_cascade_drop(int64_t block_elapsed_s);
int32_t compute_v11_cascade_drop_triangular(int64_t block_elapsed_s);

// Height-gated triangular cascade — pre-V12 caps at 6 steps, V12+ caps at 7.
// Used by the production validator/miner path. The legacy
// compute_v11_cascade_drop_triangular(elapsed) is preserved as a thin
// wrapper that calls this with next_height=0 (= pre-V12 cap) so existing
// callers / tests are unaffected.
int32_t compute_v11_cascade_drop_triangular_h(int64_t block_elapsed_s,
                                               int64_t next_height);

// V12 Slingshot tier ladder (consensus-critical helper).
// Returns 0..5 — strict greater-than at every threshold, boundary
// values do NOT trigger the higher tier:
//   current_elapsed >  V12_SLINGSHOT_T5_SECONDS (10800 = 180 min) → 5
//   current_elapsed >  V12_SLINGSHOT_T4_SECONDS ( 7200 = 120 min) → 4
//   current_elapsed >  V12_SLINGSHOT_T3_SECONDS ( 3600 =  60 min) → 3
//   current_elapsed >  V12_SLINGSHOT_T2_SECONDS ( 1800 =  30 min) → 2
//   current_elapsed >  V12_SLINGSHOT_T1_SECONDS ( 1200 =  20 min) → 1
//   else                                                           → 0
//
// Used identically by miner (mid-search rebuild watch) and validator
// (bitsQ relief) so consensus is symmetric. Pure function — no globals.
int32_t slingshot_v12_tier(int64_t current_elapsed);

// ---- Timestamp validation ----
int64_t median_time_past(const std::vector<BlockMeta>& chain,
                          int32_t window = MTP_WINDOW);

std::pair<bool, const char*> validate_block_time(
    int64_t block_time,
    const std::vector<BlockMeta>& chain,
    int64_t current_time);

} // namespace sost
