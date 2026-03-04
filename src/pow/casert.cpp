#include "sost/pow/casert.h"
#include <algorithm>
namespace sost {

// ---------------------------------------------------------------------------
// cASERT v2 — Unidirectional hardening (chain-ahead only)
//
// Computes "lag" = how many blocks the chain is ahead of the ideal schedule.
//   lag > 0  → chain behind  (ASERT handles this alone, no CX overlay)
//   lag ≤ 0  → chain on-time or ahead  (apply CX hardening levels)
//
// Levels (stab_scale):
//   L3 (base)  = 0–20  blocks ahead  → neutral, no extra CX cost
//   L4         = 21–50 blocks ahead  → light CX hardening
//   L5         = 51–100 blocks ahead → moderate
//   L6         = 101+  blocks ahead  → maximum CX cost
// ---------------------------------------------------------------------------

CasertDecision casert_mode_from_chain(const std::vector<BlockMeta>& chain,
                                       int64_t next_height)
{
    if (next_height < 2 || chain.size() < 2)
        return {CasertMode::WARMUP, 0, 0};

    // Lag in blocks: positive = behind schedule, negative = ahead
    int64_t latest_time  = chain.back().time;
    int64_t elapsed      = latest_time - GENESIS_TIME;
    int64_t expected_h   = elapsed / TARGET_SPACING;
    int32_t lag          = (int32_t)(expected_h - (next_height - 1));

    int32_t ahead = (lag < 0) ? -lag : 0;

    CasertMode mode;
    if      (ahead < CASERT_L4_BLOCKS) mode = CasertMode::NORMAL;    // L3 (0–20)
    else if (ahead < CASERT_L5_BLOCKS) mode = CasertMode::DEGRADED;  // L4 (21–50)
    else                               mode = CasertMode::OPEN;      // L5/L6 (51+)

    return {mode, lag, (int32_t)(chain.size() - 1)};
}

ConsensusParams casert_apply_overlay(const ConsensusParams& base,
                                      const CasertDecision& dec)
{
    ConsensusParams out = base;

    // Unidirectional: only harden when chain is ahead (lag < 0).
    // When behind or on-time → return base params untouched (L3).
    if (dec.signal_s >= 0) return out;

    int32_t ahead = -dec.signal_s;

    int32_t level;
    if      (ahead < CASERT_L4_BLOCKS) level = 3;   // L3 — neutral  (0–20)
    else if (ahead < CASERT_L5_BLOCKS) level = 4;   // L4 — light    (21–50)
    else if (ahead < CASERT_L6_BLOCKS) level = 5;   // L5 — moderate (51–100)
    else                               level = 6;   // L6 — maximum  (101+)

    out.stab_scale  = level;
    out.stab_k      = 4;
    out.stab_steps  = 3;
    out.stab_margin = CX_STB_MARGIN;
    return out;
}

} // namespace sost
