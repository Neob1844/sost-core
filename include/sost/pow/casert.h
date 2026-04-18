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
uint32_t casert_next_bitsq(const std::vector<BlockMeta>& chain, int64_t next_height);

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

// ---- Timestamp validation ----
int64_t median_time_past(const std::vector<BlockMeta>& chain,
                          int32_t window = MTP_WINDOW);

std::pair<bool, const char*> validate_block_time(
    int64_t block_time,
    const std::vector<BlockMeta>& chain,
    int64_t current_time);

} // namespace sost
