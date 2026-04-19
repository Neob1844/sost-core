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

    // Ahead Guard: clamp downward bitsQ adjustment when chain is materially ahead
    // of schedule, to prevent bitsQ from undoing the equalizer's braking.
    //
    // V4 (4170 <= height < 4500): stateful hysteresis via static bool.
    //   Determinism risk: `static` persists across calls and is not reconstructed
    //   from chain state, so nodes on different sync paths can disagree. No live
    //   divergence observed, but flagged as must-fix in the V5 design doc.
    //
    // V5 (height >= 4500): stateless. The flag is derived on every call directly
    //   from the current schedule_lag. Trade-off: loses the enter/exit hysteresis,
    //   but the Ahead Guard is a one-block clamp anyway — no meaningful
    //   behavioural loss versus the safety gained.
    if (next_height >= CASERT_V4_FORK_HEIGHT && next_height < CASERT_V6_FORK_HEIGHT && delta < 0) {
        // Compute schedule lag: positive = ahead
        int64_t elapsed = chain.back().time - GENESIS_TIME;
        int64_t expected_h = (elapsed >= 0) ? (elapsed / TARGET_SPACING) : 0;
        int32_t schedule_lag = (int32_t)((int64_t)(next_height - 1) - expected_h);

        bool clamp = false;
        if (next_height >= CASERT_V5_FORK_HEIGHT) {
            // V5: stateless — fires iff schedule_lag crosses the entry threshold
            // on the current block. No memory of prior blocks, no static flag.
            clamp = (schedule_lag >= CASERT_AHEAD_ENTER);
        } else {
            // V4: stateful hysteresis (kept bit-for-bit to preserve consensus of
            // already-validated blocks in the range [4170, 4500)).
            static bool ahead_correction_mode = false;
            if (schedule_lag >= CASERT_AHEAD_ENTER) ahead_correction_mode = true;
            if (schedule_lag <= CASERT_AHEAD_EXIT)  ahead_correction_mode = false;
            clamp = ahead_correction_mode;
        }

        if (clamp) {
            // Clamp downward delta: allow only ~1.56% drop instead of 12.5%
            int64_t ahead_max_drop = (int64_t)prev_bitsq / CASERT_AHEAD_DELTA_DEN;
            if (ahead_max_drop < 1) ahead_max_drop = 1;
            delta = std::max<int64_t>(-ahead_max_drop, delta);
        }
    }

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
    // Pre-V6-calibration: lag from last block's timestamp (deterministic, frozen between blocks)
    // V6-calibration (block 5050+): lag from now_time (wall clock for mining, block timestamp
    // for validation). This makes the lag — and therefore the profile — decrease in real time
    // as wall clock advances, enabling the lag cap and lag-adjust to self-correct without
    // waiting for anti-stall. Mining and validation agree because the validator passes
    // block_timestamp as now_time, which is the time the miner set when building the block.
    int64_t lag_time = chain.back().time;
    if (next_height >= CASERT_V6_CALIBRATION_HEIGHT && now_time > 0 && now_time > lag_time) {
        lag_time = now_time;
    }
    int64_t elapsed = lag_time - GENESIS_TIME;
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

    // Clamp to profile bounds (V7 extends H_MAX from 12 to 32)
    int32_t h_max = (next_height >= CASERT_V6_CALIBRATION_HEIGHT) ? CASERT_H_MAX : CASERT_H_MAX_PRE_CAL;
    int32_t H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(h_max, H_raw));

    // Safety rule 1: if chain is behind or on schedule, never harden beyond B0
    // lag > 0 means chain is AHEAD; lag <= 0 means behind or on schedule
    if (lag <= 0) {
        H = std::min<int32_t>(H, 0);
    }

    // Safety rule 2: require minimum chain depth before any hardening
    if (chain.size() < 10) {
        H = std::min<int32_t>(H, 0);
    }

    // Slew rate limit: prevents the equalizer from jumping too many levels per block.
    // V2 (blocks < 4100): ±1 per block with heuristic prev_H estimation.
    // V3 (blocks >= 4100): ±3 per block with recomputed prev_H + lag floor.
    if (chain.size() >= 3) {
        if (next_height >= CASERT_V3_FORK_HEIGHT) {
            int32_t prev_H = 0; // B0 default

            if (next_height >= CASERT_V4_FORK_HEIGHT) {
                // --- V4: Strict stored profile_index — NO fallback ---
                // Invariant after V4 activation: every BlockMeta in the chain
                // window has profile_index set to a real value (V3+ miners
                // always write it into block JSON, load_chain parses it, and
                // StoredBlock persists it across restarts). INT32_MIN should
                // never reach here; if it somehow does (legacy anomaly), we
                // default conservatively to B0 (0) instead of disabling the
                // slew rate — the old V3.1 `prev_H = H` escape hatch is gone.
                int32_t stored_pi = chain.back().profile_index;
                if (stored_pi == INT32_MIN) stored_pi = 0; // conservative
                prev_H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, stored_pi));
            } else if (next_height >= CASERT_V3_1_FORK_HEIGHT) {
                // --- V3.1 (blocks 4110-4169): Use stored profile_index ---
                // Historical quirk: default was 0, so legit B0 was misread as
                // missing and fell through to `prev_H = H`. Kept identical to
                // preserve consensus for already-validated blocks in this range.
                int32_t stored_pi = chain.back().profile_index;
                // Normalize: V3.1 didn't know about INT32_MIN sentinel. Treat
                // INT32_MIN the same as 0 so newly-built BlockMeta behaves like
                // the old default for these heights.
                if (stored_pi == INT32_MIN) stored_pi = 0;
                if (stored_pi != 0 || chain.back().height < CASERT_V3_FORK_HEIGHT) {
                    prev_H = stored_pi;
                } else {
                    prev_H = H; // historical fallback — see comment above
                }
                prev_H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, prev_H));
            } else {
                // --- V3 (blocks 4100-4199): Original PID recomputation (has slew rate bug) ---
                // Kept for backward compatibility with already-mined blocks.
                std::vector<BlockMeta> prev_chain(chain.begin(), chain.end() - 1);
                if (prev_chain.size() >= 2) {
                    int64_t prev_elapsed = prev_chain.back().time - GENESIS_TIME;
                    int64_t prev_exp_h = (prev_elapsed >= 0) ? (prev_elapsed / TARGET_SPACING)
                        : -((-prev_elapsed + TARGET_SPACING - 1) / TARGET_SPACING);
                    int32_t prev_lag = (int32_t)((int64_t)(next_height - 2) - prev_exp_h);

                    int32_t pS = 0, pM = 0, pV = 0;
                    int64_t pI = 0;
                    size_t plb = std::min<size_t>(prev_chain.size(), 128);
                    size_t pst = prev_chain.size() - plb;
                    for (size_t pi = pst + 1; pi < prev_chain.size(); ++pi) {
                        int64_t pd = prev_chain[pi].time - prev_chain[pi-1].time;
                        pd = std::max<int64_t>(CASERT_DT_MIN, std::min<int64_t>(CASERT_DT_MAX, pd));
                        int32_t pr = log2_q16(TARGET_SPACING) - log2_q16(pd);
                        pS = (int32_t)(((int64_t)CASERT_EWMA_SHORT_ALPHA * pr +
                                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_SHORT_ALPHA) * pS) >> 8);
                        pM = (int32_t)(((int64_t)CASERT_EWMA_LONG_ALPHA * pr +
                                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_LONG_ALPHA) * pM) >> 8);
                        int32_t pabs = (pr > pS) ? (pr - pS) : (pS - pr);
                        pV = (int32_t)(((int64_t)CASERT_EWMA_VOL_ALPHA * pabs +
                                       (int64_t)(CASERT_EWMA_DENOM - CASERT_EWMA_VOL_ALPHA) * pV) >> 8);
                        int64_t ph_i = (int64_t)prev_chain[pi].height;
                        int64_t pe_i = prev_chain[pi].time - GENESIS_TIME;
                        int64_t pexp_i = (pe_i >= 0) ? (pe_i / TARGET_SPACING) : -((-pe_i + TARGET_SPACING - 1) / TARGET_SPACING);
                        int32_t plag_i = (int32_t)(ph_i - pexp_i);
                        int64_t pL_q16 = (int64_t)plag_i * (int64_t)Q16_ONE;
                        pI = ((int64_t)CASERT_INTEG_RHO * pI + (int64_t)CASERT_EWMA_DENOM * CASERT_INTEG_ALPHA * pL_q16) >> 8;
                        pI = std::max<int64_t>(-CASERT_INTEG_MAX, std::min<int64_t>(CASERT_INTEG_MAX, pI));
                    }
                    int64_t prev_dt = prev_chain.back().time - prev_chain[prev_chain.size()-2].time;
                    prev_dt = std::max<int64_t>(CASERT_DT_MIN, std::min<int64_t>(CASERT_DT_MAX, prev_dt));
                    int32_t prev_r = log2_q16(TARGET_SPACING) - log2_q16(prev_dt);

                    int64_t pL_q16 = (int64_t)prev_lag * (int64_t)Q16_ONE;
                    int64_t pU = (int64_t)CASERT_K_R * prev_r +
                                 (int64_t)CASERT_K_L * (pL_q16 >> 16) +
                                 (int64_t)CASERT_K_I * (pI >> 16) +
                                 (int64_t)CASERT_K_B * (pS - pM) +
                                 (int64_t)CASERT_K_V * pV;
                    prev_H = (int32_t)(pU >> 16);
                    prev_H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, prev_H));
                    if (prev_lag <= 0) prev_H = std::min<int32_t>(prev_H, 0);
                    if (prev_chain.size() < 10) prev_H = std::min<int32_t>(prev_H, 0);
                }
            }

            // Slew rate: limits how fast the profile can change per block.
            // Dynamic slew (block 5100+): adapts based on last block interval.
            // Fast blocks need fast profile climb to prevent lag accumulation.
            int32_t slew;
            if (next_height >= CASERT_DYNSLEW_HEIGHT) {
                if (dt < CASERT_DYNSLEW_FAST_DT) slew = CASERT_DYNSLEW_FAST;      // ±5
                else if (dt < CASERT_DYNSLEW_MED_DT) slew = CASERT_DYNSLEW_MED;   // ±3
                else slew = CASERT_V6_SLEW_RATE;                                    // ±1
            } else if (next_height >= CASERT_V6_FORK_HEIGHT) {
                slew = CASERT_V6_SLEW_RATE;   // ±1 (V6)
            } else {
                slew = CASERT_V3_SLEW_RATE;   // ±3 (pre-V6)
            }
            H = std::max<int32_t>(prev_H - slew,
                    std::min<int32_t>(prev_H + slew, H));

            // V3/V3.1 lag floor: if chain is significantly ahead, enforce minimum profile
            if (lag > 10) {
                int32_t lag_floor = std::min<int32_t>((int32_t)(lag / CASERT_V3_LAG_FLOOR_DIV),
                                                       h_max);
                H = std::max<int32_t>(H, lag_floor);
            }

            // V5: Safety rule 1 re-applied POST-SLEW + Emergency Behind Release (EBR).
            //
            // Before V5, the slew rate was applied *after* safety rule 1, which
            // meant `prev_H = 12, lag = -5` left H at 9 (slew clamped a PID-desired
            // -2 up to prev_H-3=9), shadowing the "never harden when behind" rule.
            // Chain stayed at H9/H12 for 4 blocks of slew decay while lag kept
            // dropping — the overshoot observed at block 4184.
            //
            // V5 fix: at post-V5 heights, re-apply safety rule 1 AFTER the slew
            // rate and lag_floor. If lag <= 0, H is forced to <= 0 regardless of
            // what the slew rate allowed. This guarantees the hard invariant
            // "never hardened while behind" in a single block.
            //
            // For severely negative lag (<= -10), EBR cliffs force H progressively
            // toward the easing range, giving the chain rapid liveness recovery
            // without waiting for anti-stall (which itself is reduced to 75min
            // at V5 heights — see `ANTISTALL_FLOOR_V5`).
            if (next_height >= CASERT_V5_FORK_HEIGHT) {
                // Safety rule 1 post-slew: never hardened when behind
                if (lag <= 0) {
                    H = std::min<int32_t>(H, 0);
                }
                // Emergency Behind Release: stateless cliffs
                if (lag <= CASERT_EBR_ENTER) {
                    int32_t ebr_floor;
                    if      (lag <= CASERT_EBR_LEVEL_E4) ebr_floor = CASERT_H_MIN;  // E4
                    else if (lag <= CASERT_EBR_LEVEL_E3) ebr_floor = -3;            // E3
                    else if (lag <= CASERT_EBR_LEVEL_E2) ebr_floor = -2;            // E2
                    else                                 ebr_floor =  0;            // B0
                    H = std::min<int32_t>(H, ebr_floor);
                }
                // Extreme profile entry cap: H10+ requires +1/block climb.
                //
                // Profiles H10 (15% stability), H11 (8%) and H12 (3%) are the
                // strongest brakes in the 17-profile table. Reaching them with
                // +3 slew or via lag_floor jumps causes the chain to overshoot:
                // the new profile is so hard to mine that production stalls
                // while lag was already going the other way (observed at
                // block 4184: B0→H6→H9→H12 in 3 blocks, then 155min stuck).
                //
                // Capping entry at +1/block gives the equalizer 2-3 extra
                // blocks at intermediate profiles (H9→H10→H11) during which
                // the chain still mines and lag can self-correct before the
                // worst brake is applied. Descent from extreme range is
                // unrestricted — the asymmetry is intentional.
                if (H >= CASERT_V5_EXTREME_MIN && H > prev_H + 1) {
                    H = prev_H + 1;
                }
            }

            // V7: Dynamic lag cap — profile cannot exceed current schedule lag.
            // Replaces V6 H11/H12 fixed reservation with a universal rule:
            // the brake strength is proportional to how far ahead the chain is.
            // bitsQ handles hashrate shocks independently.
            if (next_height >= CASERT_V6_CALIBRATION_HEIGHT) {
                if (H > 0 && H > lag) {
                    H = std::max<int32_t>(0, lag);
                }
            } else if (next_height >= CASERT_V6_FORK_HEIGHT) {
                // V6 (blocks 5000-5099): fixed H11/H12 reservation
                if (H >= 12 && lag < CASERT_V6_H12_MIN_LAG) H = 11;
                if (H >= 11 && lag < CASERT_V6_H11_MIN_LAG) H = 10;
            }

            H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(h_max, H));
        } else {
            // --- V2: Original ±1 slew rate with heuristic estimation ---
            int64_t prev_elapsed = chain[chain.size()-2].time - GENESIS_TIME;
            int64_t prev_exp = (prev_elapsed >= 0) ? (prev_elapsed / TARGET_SPACING) : 0;
            int32_t prev_lag = (int32_t)((int64_t)(next_height - 2) - prev_exp);
            int32_t prev_H_est = 0; // B0 baseline
            if (prev_lag > 0) {
                int32_t ahead = prev_lag;
                if (ahead >= 20) prev_H_est = std::min((int32_t)CASERT_H_MAX, ahead / 10);
                else if (ahead >= 5) prev_H_est = 1;
            }
            H = std::max<int32_t>(prev_H_est - 1, std::min<int32_t>(prev_H_est + 1, H));
            H = std::max<int32_t>(CASERT_H_MIN, std::min<int32_t>(CASERT_H_MAX, H));
        }
    }

    // ---- Anti-stall (mining only): zone-based decay targeting B0 ----
    // Decay zones: H9-H7 = 600s/lvl, H6-H4 = 900s/lvl, H3-H1 = 1200s/lvl
    // B0 is the natural destination. Easing (E1-E4) only after 6h extra at B0.
    if (now_time > 0 && !chain.empty()) {
        int64_t stall = std::max<int64_t>(0, now_time - chain.back().time);
        // Anti-stall threshold: V4 and earlier use 7200s (2h). V5 reduces it to
        // 3600s (60 min) so the safety net fires faster in small networks —
        // complements EBR which handles lag-triggered recovery, while anti-stall
        // handles time-triggered recovery (block completely stuck).
        int64_t t_act = (next_height >= CASERT_V6_CALIBRATION_HEIGHT)
            ? CASERT_ANTISTALL_FLOOR_V6C   // 5400s = 90 min
            : (next_height >= CASERT_V5_FORK_HEIGHT)
            ? CASERT_ANTISTALL_FLOOR_V5   // 3600s = 60 min
            : CASERT_ANTISTALL_FLOOR;     // 7200s = 2 hours
        if (stall >= t_act && H > 0) {
            // Hardening decay: drop toward B0
            // V6: first drop is immediate — the full t_act wait IS the penalty.
            // Subsequent drops follow zone-based costs.
            int64_t decay_time = stall - t_act;
            int32_t decayed_H = H - 1; // immediate first drop
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
                                      const CasertDecision& dec,
                                      int64_t /*height*/)
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
