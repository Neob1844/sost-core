#include "sost/pow/casert.h"
#include <algorithm>
namespace sost {

// ---------------------------------------------------------------------------
// cASERT v5 — Unbounded dynamic scale (chain-ahead only)
//
// Computes "lag" = how many blocks the chain is ahead of the ideal schedule.
//   lag > 0  → chain behind  (ASERT handles this alone, no CX overlay)
//   lag ≤ 0  → chain on-time or ahead  (apply CX hardening levels)
//
// Levels:
//   L1 (neutral) = 0–4   blocks ahead  → scale=1
//   L2           = 5–25  blocks ahead  → scale=2
//   L3           = 26–50 blocks ahead  → scale=3
//   L4           = 51–75 blocks ahead  → scale=4
//   L5+          = 76+   blocks ahead  → UNBOUNDED
//     level = 5 + (blocks_ahead - 76) / 50
//     scale = level + 1
//     No ceiling — the faster the attack, the harder the brake.
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
    if      (ahead < CASERT_L2_BLOCKS) mode = CasertMode::L1;
    else if (ahead < CASERT_L3_BLOCKS) mode = CasertMode::L2;
    else if (ahead < CASERT_L4_BLOCKS) mode = CasertMode::L3;
    else if (ahead < CASERT_L5_BLOCKS) mode = CasertMode::L4;
    else                               mode = CasertMode::L5;

    return {mode, lag, (int32_t)(chain.size() - 1)};
}

ConsensusParams casert_apply_overlay(const ConsensusParams& base,
                                      const CasertDecision& dec)
{
    ConsensusParams out = base;

    // Unidirectional: only harden when chain is ahead (lag < 0).
    // When behind or on-time → return base params untouched (L1).
    if (dec.signal_s >= 0) return out;

    int32_t ahead = -dec.signal_s;

    int32_t level, scale;
    if      (ahead < CASERT_L2_BLOCKS) { level = 1; scale = 1; }   // L1 — neutral  (0–4)
    else if (ahead < CASERT_L3_BLOCKS) { level = 2; scale = 2; }   // L2 — light    (5–25)
    else if (ahead < CASERT_L4_BLOCKS) { level = 3; scale = 3; }   // L3 — moderate (26–50)
    else if (ahead < CASERT_L5_BLOCKS) { level = 4; scale = 4; }   // L4 — strong   (51–75)
    else {
        // Dynamic unbounded formula above L4
        // Every 50 blocks beyond 76 adds 1 to level and scale
        level = 5 + (ahead - CASERT_L5_BLOCKS) / 50;
        scale = level + 1;  // scale always = level + 1 above L4
        // Examples:
        //   76-125: level=5, scale=6
        //   126-175: level=6, scale=7
        //   176-225: level=7, scale=8
        //   326-375: level=10, scale=11
        //   500+: level=13+, scale=14+
    }

    // If level == 1: skip overlay entirely (ASERT handles it)
    if (level <= 1) return out;

    out.stab_scale  = scale;
    out.stab_k      = 4;
    out.stab_steps  = 4;
    out.stab_margin = CX_STB_MARGIN;
    return out;
}

} // namespace sost

