// cASERT — Unified consensus-rate control system for SOST
// bitsQ primary controller + equalizer + anti-stall
#include "sost/pow/casert.h"
#include <algorithm>
#include <cmath>
namespace sost {

// =========================================================================
// Timestamp utilities
// =========================================================================

int64_t median_time_past(const std::vector<BlockMeta>& chain, int32_t window) {
    if (chain.empty()) return 0;
    size_t take = std::min<size_t>(chain.size(), (size_t)window);
    std::vector<int64_t> times; times.reserve(take);
    for (size_t i = chain.size()-take; i < chain.size(); ++i)
        times.push_back(chain[i].time);
    std::sort(times.begin(), times.end());
    return times[times.size()/2];
}

std::pair<bool, const char*> validate_block_time(
    int64_t bt, const std::vector<BlockMeta>& chain, int64_t now) {
    int64_t mtp = median_time_past(chain);
    if (!chain.empty() && bt <= mtp) return {false, "time-too-old"};
    if (bt > now + MAX_FUTURE_DRIFT) return {false, "time-too-new"};
    return {true, "ok"};
}

// =========================================================================
// Fixed-point log2 approximation (Q16.16)
// =========================================================================

// Returns log2(x) in Q16.16 for x > 0 (x is a plain integer, not Q16.16)
static int32_t log2_q16(int64_t x) {
    if (x <= 0) return -((int32_t)Q16_ONE * 20); // large negative for <=0
    if (x == 1) return 0;
    // Integer part: position of highest set bit
    int32_t int_part = 0;
    int64_t tmp = x;
    while (tmp > 1) { tmp >>= 1; int_part++; }
    // Fractional part via linear interpolation between powers of 2
    int64_t lo = (int64_t)1 << int_part;
    int64_t hi = lo << 1;
    int64_t frac = 0;
    if (hi > lo) {
        frac = ((x - lo) * (int64_t)Q16_ONE) / (hi - lo);
    }
    return (int_part * (int32_t)Q16_ONE) + (int32_t)frac;
}

// =========================================================================
// bitsQ primary controller — 2^x via Horner polynomial
// =========================================================================

// Cubic polynomial approximation of 2^frac for frac in [0, Q16_ONE)
// 2^x ≈ 1 + x·ln2 + x²·ln2²/2 + x³·ln2³/6
// Constants in Q0.16: ln2=45426, ln2²/2=15743, ln2³/6=3638
static int64_t horner_2exp(uint32_t frac) {
    int64_t x = (int64_t)frac;
    int64_t t = 3638;
    t = 15743 + ((t * x) >> 16);
    t = 45426 + ((t * x) >> 16);
    return (int64_t)Q16_ONE + ((t * x) >> 16);
}

uint32_t casert_next_bitsq(const std::vector<BlockMeta>& chain, int64_t next_height) {
    if (chain.empty() || next_height <= 0) return GENESIS_BITSQ;

    // Anchor: first block of current epoch (genesis for epoch 0)
    int64_t epoch = next_height / BLOCKS_PER_EPOCH;
    size_t anchor_idx = 0;
    if (epoch > 0) {
        int64_t ai = epoch * BLOCKS_PER_EPOCH - 1;
        anchor_idx = (size_t)std::max<int64_t>(0, std::min<int64_t>(ai, (int64_t)chain.size()-1));
    }
    auto anchor_time = chain[anchor_idx].time;
    auto anchor_bitsq = (anchor_idx == 0) ? GENESIS_BITSQ : chain[anchor_idx].powDiffQ;

    // Time delta: negative when blocks arrive faster than target
    int64_t parent_idx = (int64_t)chain.size() - 1;
    int64_t expected_pt = anchor_time + (parent_idx - (int64_t)anchor_idx) * TARGET_SPACING;
    int64_t td = chain.back().time - expected_pt;

    // Exponential: next_bitsq = anchor_bitsq * 2^(-td / halflife)
    int64_t halflife = (next_height >= CASERT_V2_FORK_HEIGHT) ? BITSQ_HALF_LIFE_V2 : BITSQ_HALF_LIFE;
    int64_t exponent = ((-td) * (int64_t)Q16_ONE) / halflife;

    int32_t shifts = (int32_t)(exponent >> 16);
    uint32_t frac = (uint32_t)(exponent & 0xFFFF);

    int64_t factor = horner_2exp(frac);
    int64_t raw_result = ((int64_t)anchor_bitsq * factor) >> 16;

    if (shifts > 0) {
        if (shifts > 24) raw_result = (int64_t)MAX_BITSQ;
        else             raw_result <<= shifts;
    } else if (shifts < 0) {
        int32_t rshifts = -shifts;
        if (rshifts > 24) raw_result = 0;
        else              raw_result >>= rshifts;
    }

    // Relative per-block delta cap: prev_bitsq / delta_den
    uint32_t prev_bitsq = chain.back().powDiffQ ? chain.back().powDiffQ : GENESIS_BITSQ;
    int32_t delta_den = (next_height >= CASERT_V2_FORK_HEIGHT) ? BITSQ_MAX_DELTA_DEN_V2 : BITSQ_MAX_DELTA_DEN;
    int64_t max_delta = (int64_t)prev_bitsq / delta_den;
    if (max_delta < 1) max_delta = 1;

    int64_t delta = raw_result - (int64_t)prev_bitsq;
    delta = std::max<int64_t>(-max_delta, std::min<int64_t>(max_delta, delta));
    int64_t result = (int64_t)prev_bitsq + delta;

    // Global clamp
    result = std::max<int64_t>((int64_t)MIN_BITSQ, std::min<int64_t>((int64_t)MAX_BITSQ, result));
    return (uint32_t)result;
}

// =========================================================================
// cASERT equalizer — signal computation and profile selection
// =========================================================================

CasertDecision casert_compute(const std::vector<BlockMeta>& chain,
                               int64_t next_height,
                               int64_t now_time)
{
    CasertDecision dec{};
    dec.bitsq = casert_next_bitsq(chain, next_height);
    dec.profile_index = 0; // B0 baseline default

    if (chain.size() < 2 || next_height <= 1) {
        return dec;
    }

    // ---- Compute signals ----

    // Instantaneous log-ratio: r_n = log2(T / dt_n)
    int64_t dt = chain.back().time - chain[chain.size()-2].time;
    dt = std::max<int64_t>(CASERT_DT_MIN, std::min<int64_t>(CASERT_DT_MAX, dt));
    int32_t r_n = log2_q16(TARGET_SPACING) - log2_q16(dt);
    dec.r_q16 = r_n;

    // Schedule lag: L_n = h_n - floor((t_n - GENESIS_TIME) / T)
    int64_t elapsed = chain.back().time - GENESIS_TIME;
    int64_t expected_h = (elapsed >= 0) ? (elapsed / TARGET_SPACING) : -((-elapsed + TARGET_SPACING - 1) / TARGET_SPACING);
    int32_t lag = (int32_t)((int64_t)(next_height - 1) - expected_h);
    dec.lag = lag;

    // EWMA computation from recent blocks
    // We compute EWMAs iteratively over the last min(chain.size(), 96+8) blocks
    int32_t S = 0, M = 0, V = 0;
    int64_t I = 0;

    size_t lookback = std::min<size_t>(chain.size(), 128);
    size_t start = chain.size() - lookback;

    for (size_t i = start + 1; i < chain.size(); ++i) {
        int64_t d = chain[i].time - chain[i-1].time;
        d = std::max<int64_t>(CASERT_DT_MIN, std::min<int64_t>(CASERT_DT_MAX, d));
        int32_t r = log2_q16(TARGET_SPACING) - log2_q16(d);

        // EWMA short
        S = (int32_t)(((int64_t)CASERT_EWMA_SHORT_ALPHA * r +
                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_SHORT_ALPHA) * S) >> 8);

        // EWMA long
        M = (int32_t)(((int64_t)CASERT_EWMA_LONG_ALPHA * r +
                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_LONG_ALPHA) * M) >> 8);

        // Volatility
        int32_t abs_dev = (r > S) ? (r - S) : (S - r);
        V = (int32_t)(((int64_t)CASERT_EWMA_VOL_ALPHA * abs_dev +
                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_VOL_ALPHA) * V) >> 8);

        // Integrator (uses lag at each block)
        int64_t h_i = (int64_t)chain[i].height;
        int64_t e_i = chain[i].time - GENESIS_TIME;
        int64_t exp_i = (e_i >= 0) ? (e_i / TARGET_SPACING) : -((-e_i + TARGET_SPACING - 1) / TARGET_SPACING);
        int32_t lag_i = (int32_t)(h_i - exp_i);
        int64_t L_i_q16 = (int64_t)lag_i * (int64_t)Q16_ONE;
        I = ((int64_t)CASERT_INTEG_RHO * I + (int64_t)CASERT_EWMA_DENOM * CASERT_INTEG_ALPHA * L_i_q16) >> 8;
        I = std::max<int64_t>(-CASERT_INTEG_MAX, std::min<int64_t>(CASERT_INTEG_MAX, I));
    }

    dec.ewma_short = S;
    dec.ewma_long = M;
    dec.burst_score = S - M;
    dec.volatility = V;
    dec.integrator = I;

    // ---- Control signal ----
    int64_t L_q16 = (int64_t)lag * (int64_t)Q16_ONE;
    int64_t U = (int64_t)CASERT_K_R * r_n +
                (int64_t)CASERT_K_L * (L_q16 >> 16) +   // scale down to prevent overflow
                (int64_t)CASERT_K_I * (I >> 16) +
                (int64_t)CASERT_K_B * (dec.burst_score) +
                (int64_t)CASERT_K_V * V;
    // U is in Q16.16 * Q16.16 territory, normalize
    int32_t H_raw = (int32_t)(U >> 16);

    // Clamp to profile bounds
    int32_t H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, H_raw));

    // Safety rule 1: if chain is behind or on schedule, never harden beyond B0
    // lag > 0 means chain is AHEAD; lag <= 0 means behind or on schedule
    if (lag <= 0) {
        H = std::min<int32_t>(H, 0);
    }

    // Safety rule 2: require minimum chain depth before any hardening
    if (chain.size() < 10) {
        H = std::min<int32_t>(H, 0);
    }

    // Slew rate limit: H can change by at most ±1 per block
    // Compute previous H from the previous block's data to limit the rate
    if (chain.size() >= 3) {
        // Recompute the previous block's lag to estimate prev H
        int64_t prev_elapsed = chain[chain.size()-2].time - GENESIS_TIME;
        int64_t prev_exp = (prev_elapsed >= 0) ? (prev_elapsed / TARGET_SPACING) : 0;
        int32_t prev_lag = (int32_t)((int64_t)(next_height - 2) - prev_exp);
        int32_t prev_H_est = 0; // B0 baseline
        if (prev_lag > 0) {
            // Chain is ahead of schedule: estimate previous H from how far ahead
            int32_t ahead = prev_lag;
            if (ahead >= 20) prev_H_est = std::min((int32_t)CASERT_H_MAX, ahead / 10);
            else if (ahead >= 5) prev_H_est = 1;
        }
        // Clamp change to ±1
        H = std::max<int32_t>(prev_H_est - 1, std::min<int32_t>(prev_H_est + 1, H));
        H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, H));
    }

    // ---- Anti-stall (mining only): zone-based decay targeting B0 ----
    // Decay zones: H9-H7 = 600s/lvl, H6-H4 = 900s/lvl, H3-H1 = 1200s/lvl
    // B0 is the natural destination. Easing (E1-E4) only after 6h extra at B0.
    if (now_time > 0 && !chain.empty()) {
        int64_t stall = std::max<int64_t>(0, now_time - chain.back().time);
        int64_t t_act = std::max<int64_t>(CASERT_ANTISTALL_FLOOR,
                                           std::max<int64_t>(lag, 0) * TARGET_SPACING);
        if (stall >= t_act && H > 0) {
            // Hardening decay: drop toward B0
            int64_t decay_time = stall - t_act;
            int32_t decayed_H = H;
            while (decayed_H > 0 && decay_time > 0) {
                int64_t cost;
                if (decayed_H >= 7) cost = 600;       // H9-H7: fast (10 min)
                else if (decayed_H >= 4) cost = 900;   // H6-H4: medium (15 min)
                else cost = 1200;                       // H3-H1: standard (20 min)
                if (decay_time < cost) break;
                decay_time -= cost;
                decayed_H--;
            }
            H = decayed_H;
        }
        // Easing emergency: if at B0 for 6+ additional hours, activate E profiles
        if (stall >= t_act && H <= 0) {
            int64_t time_at_b0 = stall - t_act;
            // Subtract time spent decaying from hardening (estimate)
            if (time_at_b0 > CASERT_ANTISTALL_EASING_EXTRA) {
                int64_t easing_time = time_at_b0 - CASERT_ANTISTALL_EASING_EXTRA;
                int32_t easing_drops = (int32_t)(easing_time / 1800); // 30 min per easing level
                H = std::max<int32_t>(CASERT_H_MIN, -easing_drops);
            }
        }
    }

    dec.profile_index = H;
    return dec;
}

// =========================================================================
// Apply cASERT profile to ConvergenceX params
// =========================================================================

ConsensusParams casert_apply_profile(const ConsensusParams& base,
                                      const CasertDecision& dec)
{
    ConsensusParams out = base;
    int32_t idx = dec.profile_index - CASERT_H_MIN; // convert to array index
    if (idx < 0) idx = 0;
    if (idx >= CASERT_PROFILE_COUNT) idx = CASERT_PROFILE_COUNT - 1;

    const auto& prof = CASERT_PROFILES[idx];
    out.stab_scale  = prof.scale;
    out.stab_steps  = prof.steps;
    out.stab_k      = prof.k;
    out.stab_margin = prof.margin;
    out.stab_profile_index = idx + CASERT_H_MIN; // store actual profile index
    return out;
}

} // namespace sost
