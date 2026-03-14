#include "sost/pow/casert.h"
#include <algorithm>
namespace sost {

// ---------------------------------------------------------------------------
// cASERT v5.2 — Fixed bands L1-L5, unbounded L6+, Decay Anti-Stall
//
// Computes "lag" = how many blocks the chain is ahead of the ideal schedule.
//   lag > 0  → chain behind  (ASERT handles this alone, no CX overlay)
//   lag ≤ 0  → chain on-time or ahead  (apply CX hardening levels)
//
// Levels (canonical spec):
//   L1 (neutral) =   0–4   blocks ahead  → scale=1
//   L2           =   5–25  blocks ahead  → scale=2
//   L3           =  26–50  blocks ahead  → scale=3
//   L4           =  51–75  blocks ahead  → scale=4
//   L5           =  76–100 blocks ahead  → scale=5
//   L6+          = 101+    blocks ahead  → UNBOUNDED
//     level = 6 + floor((blocks_ahead - 101) / 50)
//     scale = level
//     No ceiling — the faster the attack, the harder the brake.
//
// Decay Anti-Stall:
//   When no block found for 2+ hours, effective level decays downward:
//     L8+:  1 level per 10 min (fast recovery from extreme)
//     L4-7: 1 level per 20 min (medium recovery)
//     L2-3: 1 level per 30 min (cautious near neutral)
//     L1:   floor, no further decay
//   Decay applies to MINING only (now_time > 0). Validation uses now_time=0.
// ---------------------------------------------------------------------------

// Returns raw cASERT level from blocks_ahead
// L1-L5 are fixed bands; L6+ is unbounded (scale = level)
static int level_from_ahead(int ahead) {
    if (ahead < CASERT_L2_BLOCKS) return 1;   //   0– 4 → L1
    if (ahead < CASERT_L3_BLOCKS) return 2;   //   5–25 → L2
    if (ahead < CASERT_L4_BLOCKS) return 3;   //  26–50 → L3
    if (ahead < CASERT_L5_BLOCKS) return 4;   //  51–75 → L4
    if (ahead < CASERT_L6_BLOCKS) return 5;   //  76–100 → L5
    // Dynamic unbounded above L5
    return 6 + (ahead - CASERT_L6_BLOCKS) / 50;
}

// Applies adaptive decay based on time without a block.
// Returns effective level after decay (never below 1).
// decay_seconds = now_time - last_block_timestamp
// raw_level = level computed from blocks_ahead schedule
static int apply_decay(int raw_level, int64_t decay_seconds, int ahead) {
    // Dynamic activation: higher levels need more patience before decay
    int64_t activation = (ahead > 100) ? 28800 : 14400;  // 8h for L6+, 4h for L1-L5
    if (decay_seconds < activation) return raw_level;

    int64_t decay_time = decay_seconds - activation;
    int effective = raw_level;

    // Apply decay level by level, tier by tier
    // Process from current level downward
    while (effective > 1 && decay_time > 0) {
        int64_t cost;
        if (effective >= 8) {
            cost = CASERT_DECAY_FAST_SECS;    // L8+: 10 min per level
        } else if (effective >= 4) {
            cost = CASERT_DECAY_MEDIUM_SECS;  // L4-L7: 20 min per level
        } else {
            cost = CASERT_DECAY_SLOW_SECS;    // L2-L3: 30 min per level
        }

        if (decay_time >= cost) {
            decay_time -= cost;
            effective--;
        } else {
            break;
        }
    }

    return std::max(1, effective);
}

CasertDecision casert_mode_from_chain(const std::vector<BlockMeta>& chain,
                                       int64_t next_height,
                                       int64_t now_time)
{
    if (next_height < 2 || chain.size() < 2)
        return {CasertMode::WARMUP, 0, 0};

    // Lag in blocks: positive = behind schedule, negative = ahead
    int64_t latest_time  = chain.back().time;
    int64_t elapsed      = latest_time - GENESIS_TIME;
    int64_t expected_h   = elapsed / TARGET_SPACING;
    int32_t lag          = (int32_t)(expected_h - (next_height - 1));

    int32_t ahead = (lag < 0) ? -lag : 0;

    // Raw level from schedule
    int raw_level = level_from_ahead(ahead);

    // Apply decay anti-stall (mining only, when now_time > 0)
    int effective_level = raw_level;
    if (now_time > 0 && !chain.empty()) {
        int64_t last_block_time = chain.back().time;
        int64_t stall_seconds = std::max<int64_t>(0, now_time - last_block_time);
        effective_level = apply_decay(raw_level, stall_seconds, ahead);
    }

    CasertMode mode;
    if      (effective_level <= 1) mode = CasertMode::L1;
    else if (effective_level == 2) mode = CasertMode::L2;
    else if (effective_level == 3) mode = CasertMode::L3;
    else if (effective_level == 4) mode = CasertMode::L4;
    else if (effective_level == 5) mode = CasertMode::L5;
    else                           mode = CasertMode::L6;

    CasertDecision dec;
    dec.mode = mode;
    dec.signal_s = lag;
    dec.samples = (int32_t)(chain.size() - 1);
    dec.effective_level = effective_level;
    return dec;
}

ConsensusParams casert_apply_overlay(const ConsensusParams& base,
                                      const CasertDecision& dec)
{
    ConsensusParams out = base;

    // Unidirectional: only harden when chain is ahead (lag < 0).
    // When behind or on-time → return base params untouched (L1).
    if (dec.signal_s >= 0) return out;

    int32_t ahead = -dec.signal_s;

    // Use effective_level if set (decay-aware from mining),
    // otherwise compute raw level from schedule (validation path).
    int32_t level;
    if (dec.effective_level > 0) {
        level = dec.effective_level;
    } else {
        level = level_from_ahead(ahead);
    }

    // scale = level (linear, all levels)
    int32_t scale = level;

    // If level == 1: skip overlay entirely (ASERT handles it)
    if (level <= 1) return out;

    out.stab_scale  = scale;
    out.stab_k      = CX_STB_K;
    out.stab_steps  = CX_STB_STEPS;
    out.stab_margin = CX_STB_MARGIN;
    return out;
}

} // namespace sost

