// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once
#include <cstdint>
#include "sost/consensus_constants.h"

namespace sost {

// -----------------------------------------------------------------------------
// ConvergenceX domain-separation tag (CONSENSUS-CRITICAL).
// NOTE: This is NOT Bitcoin P2P "message magic".
// It is used as a hash domain separator across ConvergenceX (scratchpad keys,
// seeds, commit, stability context, etc.), so that dev/testnet/mainnet have
// different consensus domains.
//
// Matches Python:
//   MAGIC = b"CXPOW3" + SHA256("SOST/CONVERGENCEX/" + network)[:4]
// -----------------------------------------------------------------------------

enum class Profile : uint8_t { DEV=0, TESTNET=1, MAINNET=2 };

// MAGIC = "CXPOW3" + SHA256("SOST/CONVERGENCEX/" + network)[:4]  (10 bytes)
inline constexpr uint32_t MAGIC_LEN = 10;

// Precomputed per profile (verified against Python reference):
//   dev:     4358504f5733 f950f94b
//   testnet: 4358504f5733 39014c33
//   mainnet: 4358504f5733 c6e88538
inline const uint8_t MAGIC_DEV[10]     = {0x43,0x58,0x50,0x4f,0x57,0x33, 0xf9,0x50,0xf9,0x4b};
inline const uint8_t MAGIC_TESTNET[10] = {0x43,0x58,0x50,0x4f,0x57,0x33, 0x39,0x01,0x4c,0x33};
inline const uint8_t MAGIC_MAINNET[10] = {0x43,0x58,0x50,0x4f,0x57,0x33, 0xc6,0xe8,0x85,0x38};

inline const uint8_t* magic_for_profile(Profile p) {
    switch(p) {
        case Profile::DEV:     return MAGIC_DEV;
        case Profile::TESTNET: return MAGIC_TESTNET;
        default:               return MAGIC_MAINNET;
    }
}

// Global default (set by first mine/node invocation)
inline Profile ACTIVE_PROFILE = Profile::DEV;
inline const uint8_t* MAGIC_STR_BYTES() { return magic_for_profile(ACTIVE_PROFILE); }

// Time / schedule
inline constexpr int64_t GENESIS_TIME     = 1773597600; // 2026-03-15 18:00:00 UTC
inline constexpr int64_t TARGET_SPACING   = 600;
inline constexpr int64_t BLOCKS_PER_EPOCH = 131553;

// Emission math (integer-only)
inline constexpr int64_t R0_STOCKS      = 785100863;           // 7.85100863 SOST in stocks
inline constexpr int64_t EMISSION_Q_NUM = 7788007830714049LL;
inline constexpr int64_t EMISSION_Q_DEN = 10000000000000000LL;

// Q16.16 difficulty encoding
inline constexpr uint32_t Q16_SHIFT     = 16;
inline constexpr uint32_t Q16_ONE       = 1u << Q16_SHIFT;
inline constexpr uint32_t LUT_ENTRIES   = 256;
inline constexpr uint32_t MIN_BITSQ     = Q16_ONE;
inline constexpr uint32_t MAX_BITSQ     = 255u * Q16_ONE;

// =========================================================================
// cASERT — Unified consensus-rate control system
//
// cASERT includes:
//   1. bitsQ Q16.16 — primary hardness regulator
//   2. Equalizer    — structural correction (ConvergenceX profile)
//   3. Anti-stall   — recovery mechanism
//
// bitsQ controls the numeric acceptance threshold (commit < target).
// The equalizer adjusts ConvergenceX stability test parameters.
// Together they form a single integrated controller for block timing.
// =========================================================================

// --- bitsQ primary controller ---
// GENESIS_BITSQ: calibrated starting difficulty.
// Determined by Phase A benchmark (5.48 att/s, 100% stability at B0)
// and Phase C simulation (converges to ~600s mean block time).
// bitsQ = log2(600 * 5.48 * 1.0) * 65536 = 11.6841 * 65536 = 765730
inline constexpr uint32_t GENESIS_BITSQ         = 765730;  // 11.6841, calibrated

inline constexpr int64_t  BITSQ_HALF_LIFE       = 172800;  // 48 hours (288 blocks) — V1 (blocks < 1450)
inline constexpr int32_t  BITSQ_MAX_DELTA_NUM   = 1;       // relative delta cap numerator
inline constexpr int32_t  BITSQ_MAX_DELTA_DEN   = 16;      // relative delta cap denominator (6.25%) — V1

// cASERT V2 fork — activated at block 1450 (no regenesis)
inline constexpr int64_t  CASERT_V2_FORK_HEIGHT   = 1450;
inline constexpr int64_t  BITSQ_HALF_LIFE_V2      = 86400;   // 24 hours (144 blocks) — V2
inline constexpr int32_t  BITSQ_MAX_DELTA_DEN_V2  = 8;       // relative delta cap denominator (12.5%) — V2

// V6++ bitsQ tuning — activated at block 5175
// Replaces anchor-based exponential with avg288-based adjustment.
// bitsQ is the primary controller. Equalizer is emergency-only.
inline constexpr int64_t  CASERT_V6PP_HEIGHT        = 5175;
inline constexpr int64_t  BITSQ_HALF_LIFE_V6PP      = 43200;  // 12h fallback (used pre-5175)
// Legacy V6++ static cap (12.5% per block) — used only for heights
// in [5175, 5260). At block 5260 the median-based dynamic cap took
// over, and at block 5270 the avg288-only dynamic cap (see comment
// block below) became the active rule. This constant is therefore
// dead code at every height >= 5260; it is retained for historical
// consensus replay only. DO NOT use this constant to estimate the
// effective per-block cap on the live chain.
inline constexpr int32_t  BITSQ_MAX_DELTA_DEN_V6PP  = 8;      // 12.5% — pre-5260 only

// avg288-based bitsQ (block 5175+)
// bitsQ adjusts based on the average interval of the last 288 blocks.
//
// ACTIVE RULE (height >= 5270 — current network):
//   Dead band ±15s of target (585-615s) → no adjustment.
//   Outside dead band, dynamic cap by deviation magnitude:
//      |dev| in (15, 60]   →  max delta 0.5% per block
//      |dev| in (60, 120]  →  max delta 1.0%
//      |dev| in (120, 240] →  max delta 2.0%
//      |dev|  > 240        →  max delta 3.0%   ← effective ceiling
//
// The historical "12.5%/block" cap (BITSQ_MAX_DELTA_DEN_V6PP) only
// applies on heights in [5175, 5260) and is dead code at any live
// height today. Documentation that quotes 12.5%/block as the cap
// is talking about the V2/legacy path, not the active rule.
//
// Live bitsQ: during mining, bitsQ decreases as wall clock advances
// (current elapsed time counts as a virtual interval).
inline constexpr int32_t  BITSQ_AVG288_WINDOW       = 288;
inline constexpr int64_t  BITSQ_AVG288_DEADBAND     = 30;     // ±30s around target (570-630s)

// cASERT V3 fork — activated at block 4100
// Improved equalizer responsiveness: slew rate ±1 → ±3, lag floor, real prev_H
inline constexpr int64_t  CASERT_V3_FORK_HEIGHT   = 4100;
inline constexpr int32_t  CASERT_V3_SLEW_RATE     = 3;       // max ±3 profile levels per block (pre-V6)
inline constexpr int32_t  CASERT_V6_SLEW_RATE     = 1;       // max ±1 profile level per block (V6: reduced to eliminate sawtooth)
inline constexpr int64_t  CASERT_V6_FORK_HEIGHT   = 5000;    // V6 chain-stability fork activation
inline constexpr int32_t  CASERT_V6_H11_MIN_LAG   = 11;      // V6-only: H11 reserved (replaced by V7 lag cap)
inline constexpr int32_t  CASERT_V6_H12_MIN_LAG   = 21;      // V6-only: H12 reserved (replaced by V7 lag cap)

// cASERT V7 fork — activated at block 5100
// 1. Extended profile table: 37 profiles (E4 through H32), margin 5-point gradient
// 2. Dynamic lag cap: H <= lag for all hardening profiles (replaces H11/H12 reservation)
// 3. H_MAX raised from 12 to 32
inline constexpr int64_t  CASERT_V6_CALIBRATION_HEIGHT   = 5050;
inline constexpr int64_t  CASERT_ANTISTALL_FLOOR_V6C = 3600;  // 60 min (kept at V5 level)

// Direct lag mapping (block 5320+): replaces PID-based profile selection.
// profile = clamp(lag, 0, H10). Much simpler: profile equals lag directly.
// Downward hysteresis: profile only drops if lower lag persists for 3 blocks.
// PID is bypassed entirely — test data showed it adds no measurable benefit
// when lag cap + slew ±1 are active (all 7 PID weight configs produced
// identical profile paths in simulation).
inline constexpr int64_t  CASERT_DIRECT_LAG_HEIGHT       = 5323;

// ─────────────────────────────────────────────────────────────────────
// Burst Controller (block 5100)
//
// Accelerates UPWARD equalizer climb during real bursts (multiple fast
// blocks + chain materially ahead). Hard ceiling at H10 during burst
// mode — profiles H11+ are NOT pursued via fast-ramp. Downward movement
// remains unrestricted via lag cap.
//
// Also introduces a bitsQ relax guard: prevents bitsQ from softening
// too much while the chain is ahead and the profile is already high.
// ─────────────────────────────────────────────────────────────────────
// Hard profile ceiling: progressive activation.
// Block 5075: H10 ceiling (V6 era).
// Block 5480: H11 ceiling.
// Block 5635: H12 ceiling + relief valve.
// Block 5750: H13 ceiling + equalizer overhaul.
// All safety nets (lag-adjust ~6s, anti-stall 60min, bitsQ, slew ±1) apply equally.
inline constexpr int64_t  CASERT_CEILING_HEIGHT        = 5075;
inline constexpr int64_t  CASERT_CEILING_H11_HEIGHT    = 5480;
inline constexpr int64_t  CASERT_CEILING_H12_HEIGHT    = 5635;
inline constexpr int64_t  CASERT_CEILING_H13_HEIGHT    = 5750;
inline constexpr int32_t  CASERT_HARD_PROFILE_CEILING  = 10;    // H10 (block 5075+)
inline constexpr int32_t  CASERT_HARD_PROFILE_CEILING_H11 = 11; // H11 (block 5480+)
inline constexpr int32_t  CASERT_HARD_PROFILE_CEILING_H12 = 12; // H12 (block 5635+)
inline constexpr int32_t  CASERT_HARD_PROFILE_CEILING_H13 = 13; // H13 (block 5750+)

// Profile floor enforcement: block 5560+ — declared profile must fall within
// the deterministic range computed by casert_compute (ceiling AND floor).
// Fixes: H10 → H1 invalid easing bug (block 5525).
inline constexpr int64_t  CASERT_PROFILE_FLOOR_HEIGHT = 5560;

// Relief valve: block 5750+ — if block elapsed > 605s (10m 5s),
// profile drops to E7 (H_MIN) for that block only.
// Next block returns to normal lag-based profile.
// Pre-5750: block 5635+ used 630s threshold and min(H1, target).
inline constexpr int64_t  CASERT_RELIEF_VALVE_HEIGHT = 5750;
inline constexpr int64_t  CASERT_RELIEF_VALVE_THRESHOLD = 605; // 10 min 5 sec
// Legacy relief valve (block 5635-5749)
inline constexpr int64_t  CASERT_RELIEF_VALVE_HEIGHT_V1 = 5635;
inline constexpr int64_t  CASERT_RELIEF_VALVE_THRESHOLD_V1 = 630; // 10 min 30 sec

// Staged relief valve — coordinated fork at height
// CASERT_STAGED_RELIEF_HEIGHT. Replaces the single-step H10/H11→E7
// cliff with a gradual cascade so the relief block is decided by
// hashrate over a multi-minute window rather than by who reacts
// fastest to the announcement instant.
//
// Rule (height >= CASERT_STAGED_RELIEF_HEIGHT):
//
//     elapsed = candidate.timestamp - prev.timestamp
//     if elapsed < CASERT_STAGED_RELIEF_START:
//         no relief
//     else:
//         steps   = ((elapsed - START) / STEP_SECONDS) + 1
//         drop    = steps * DROP_PER_STEP
//         eff_H   = max(base_H - drop, CASERT_H_MIN)
//
// Calibration (post-trial review with vostokzyf miner logs):
//   - Start 540 s (1 minute before the 600 s target). The first
//     drop applies just before target so a chain that has already
//     been slow gets the first stage of relief at the target moment
//     rather than 5 seconds past it.
//   - 60 s windows give every miner a full minute at each profile
//     even when LAG-CHECK is the slow v0.8 (~6 s) version.
//
// Schedule for a base of H10 (most common):
//   540s→H7   600s→H4   660s→H1   720s→E2   780s→E5   840s→E7
//
// Schedule for a base of H13 (worst-case stall):
//   540s→H10  600s→H7   660s→H4   720s→H1   780s→E2   840s→E5   900s→E7
//
// Activation comes paired with a tightened future-timestamp drift
// (MAX_FUTURE_DRIFT_STAGED) — without that, the dominant could
// pre-mine future relief stages by setting the candidate timestamp
// in the future. Both rules MUST activate on the same block.
//
// See docs/staged_relief_fork_6550.md for context and the
// Monte Carlo fairness analysis.
inline constexpr int64_t  CASERT_STAGED_RELIEF_HEIGHT     = 6550;
inline constexpr int64_t  CASERT_STAGED_RELIEF_START      = 540;  // elapsed seconds
inline constexpr int64_t  CASERT_STAGED_STEP_SECONDS      = 60;
inline constexpr int32_t  CASERT_STAGED_DROP_PER_STEP     = 3;

// V10 — granular relief cascade fork at CASERT_GRANULAR_RELIEF_HEIGHT.
// Refines the V9 staged relief: drop ONE profile level every 60 s
// instead of three, and start the cascade at 600 s instead of 540 s.
// Floor stays at E7. The bitsQ controller continues to absorb any
// drift to the 10-minute target, so the chain self-regulates and the
// cascade only intervenes when wall-clock has clearly exceeded the
// schedule.
//
// Rationale (live data, blocks 6553-6595, 40 samples):
//   - Mean interval post-V9 ≈ 624 s vs target 600 s.
//   - With drop=3 the chain over-relaxes by two profile levels on each
//     relief step; the bitsQ controller then re-tightens on the next
//     block, producing a small visible oscillation.
//   - Reducing the step from 3 to 1 lets each relief decision match
//     the actual lag, and the bitsQ controller continues to converge
//     without external intervention.
//
// Schedule (post-V10) for a base of H10:
//    600 → H9   660 → H8   720 → H7   780 → H6   840 → H5
//    900 → H4   960 → H3  1020 → H2  1080 → H1  1140 → B0
//   1200 → E1  1260 → E2  1320 → E3  1380 → E4  1440 → E5
//   1500 → E6  1560+ → E7 (floor)
//
// V10 also disables the V6-calibration lag-advance (see
// src/pow/casert.cpp, the line that promotes ``lag_time = now_time``).
// Reason: the lag-advance was useful while the cascade was coarse
// because it nudged ``lag`` down within the same block to make the
// schedule self-correct. With drop=1 the cascade is fine-grained
// enough on its own, and the lag-advance was the remaining source of
// the "off-by-one" extra drop the explorer surfaced (e.g. block 6579
// declared E1 instead of B0). Disabling it makes the schedule
// deterministic at validation time: declared profile = base - drop
// exactly, no hidden lag-time arithmetic.
//
// Future-drift cap stays at MAX_FUTURE_DRIFT_STAGED = 60 s. The cap is
// already aligned with the cascade STEP, so a future-timestamp attack
// can at best steal one profile step (= 1 level under V10, vs. 3 under
// V9). Tightening to +30 s would not improve the attack surface
// further while increasing the risk of valid blocks being rejected on
// hosts with NTP drift in the 5-15 s range.
inline constexpr int64_t  CASERT_GRANULAR_RELIEF_HEIGHT    = 6700;
inline constexpr int64_t  CASERT_GRANULAR_RELIEF_START     = 600;  // elapsed seconds
inline constexpr int64_t  CASERT_GRANULAR_STEP_SECONDS     = 60;
inline constexpr int32_t  CASERT_GRANULAR_DROP_PER_STEP    = 1;

// V11 — extended cascade fork at CASERT_V11_HEIGHT.
// Replaces V10's "drop 1 per 60s starting at 600s" with an explicit
// piecewise-constant table that drops faster in the long tail. The
// floor stays at E7 (CASERT_H_MIN). bitsQ, anti-stall, future-drift
// cap and the lag controller are all unchanged.
//
// Schedule (post-V11):
//   elapsed <  540 s   →  drop 0   (no relief)
//   elapsed >= 540 s   →  drop 1
//   elapsed >= 600 s   →  drop 2
//   elapsed >= 660 s   →  drop 3
//   elapsed >= 720 s   →  drop 4
//   elapsed >= 780 s   →  drop 5
//   elapsed >= 840 s   →  drop 6
//
// Rationale: V10 drops one level per 60 s starting at 600 s, which
// keeps difficulty high for several minutes when the chain is slow.
// V11 starts dropping earlier (540 s instead of 600 s) and uses a
// table that slightly accelerates in the 600-840 s window so the
// chain recovers schedule faster after a slow block. Floor still at
// E7, so no risk of bypassing the absolute difficulty bound.
//
// Activation paired with V11 ConvergenceX state-dependent dataset
// access (see src/pow/convergencex.cpp). Both rules must activate
// on the same block since both touch consensus.
inline constexpr int64_t  CASERT_V11_HEIGHT                = 7000;

// V11 Phase 2 activation height (SbPoW + PoP lottery + jackpot rollover).
// Phase 1 activates at 7000; Phase 2 at 7100 — 100-block (~16-17h)
// deployment window between hard forks. C11+C12 wired the miner
// production loop; C13 commits the live activation height.
// Reasoning (see docs/V11_PHASE2_RELEASE_NOTES.md):
//   - Phase 1 (cASERT cascade + state-dependent dataset) activates at
//     CASERT_V11_HEIGHT = 7000. Activating Phase 2 at the same height
//     would mix two consensus changes simultaneously; spacing them
//     keeps each fork independently observable in production.
//   - 100-block margin (~16-17h at the 600-second target) gives miners
//     time to update node + miner binaries after Phase 1 lights up and
//     before Phase 2 hard-fork rules begin to apply.
//   - C9 Monte Carlo + accounting + reorg + determinism PASS
//     (docs/V11_PHASE2_MONTE_CARLO.md).
// Single source of truth: Phase 2 components C (SbPoW) and D (lottery)
// BOTH gate on this height. Other height-bearing constants
// (CASERT_V11_HEIGHT, TIMESTAMP_MTP_FORK_HEIGHT) live in this same file
// for the same reason — keeps consensus heights in one place.
inline constexpr int64_t  V11_PHASE2_HEIGHT                = 7100;

// V11 Phase 2 — PoP lottery (component D) consensus constants.
//
// All values gate on V11_PHASE2_HEIGHT above (block 7100).
//
// Frequency schedule (used by sost::lottery::is_lottery_block):
//   For h in [V11_PHASE2_HEIGHT, V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW):
//       lottery triggered  ⟺  (height % 3) != 0   (2-of-3 bootstrap)
//   For h >= V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW:
//       lottery triggered  ⟺  (height % 3) == 0   (1-of-3 permanent)
//
// Recent-winner exclusion: an address that won a block-reward in the
// last LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW blocks is excluded from
// the eligibility set on a triggered block. The default of 5 was
// chosen by the C0187fe Monte Carlo as a provisional value:
//   - cap=30 (the previous draft) had ~12 % rollover rate and the
//     largest sybil-incentive delta in the realistic network shape.
//   - cap=5 zeros out the dominant's no-sybil lottery share with
//     ~0 % rollover rate and a smaller sybil-incentive delta.
//   - cap=0 (no exclusion) gives the dominant ~3.3 % baseline but
//     the smallest sybil-incentive delta of all variants.
// Final value confirmed by C9 (formal Monte Carlo + fairness
// review). The recent-winner cap is NOT a sybil defense — eligibility-based
// rules collapse against ~100 sybil pre-legitimated addresses
// regardless of the window. Real sybil defense waits for
// Memory-Lock per-instance (post block 12 000 study) and any
// future stake-locked eligibility once a SOST market exists.
inline constexpr int64_t  LOTTERY_HIGH_FREQ_WINDOW                = 5000;
inline constexpr int32_t  LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW  = 5;

// Timestamp policy hardening — coordinated experimental fork at height
// TIMESTAMP_MTP_FORK_HEIGHT. From this height onwards, block timestamps must
// satisfy BOTH:
//   1) ts > MedianTimePast(last TIMESTAMP_MTP_WINDOW blocks)
//   2) ts >= prev.timestamp + TIMESTAMP_MIN_DELTA_SECONDS
// Pre-fork blocks remain valid under the old rule (ts > prev.ts and
// ts <= now + MAX_FUTURE_BLOCK_TIME). MTP alone does NOT prevent
// `prev.ts + 1` from being accepted when prev.ts > MTP, which is the
// normal case; the additional minimum-delta rule eliminates the
// artificial 1-second deltas observed in blocks 6200-6310.
//
// See docs/timestamp_mtp_fork_6400.md and
// docs/fast_block_investigation_6200_6310.md for context.
inline constexpr int64_t  TIMESTAMP_MTP_FORK_HEIGHT  = 6400;
inline constexpr int32_t  TIMESTAMP_MTP_WINDOW       = 11;
inline constexpr int64_t  TIMESTAMP_MIN_DELTA_SECONDS = 60;

inline constexpr int64_t  CASERT_BURST_HEIGHT          = 999999; // NOT ACTIVE — pending validation

// Burst trigger: tier 1 (moderate)
inline constexpr int32_t  CASERT_BURST_LAG_ENTER_1     = 8;    // lag >= 8
inline constexpr int64_t  CASERT_BURST_MEDIAN_FAST_1   = 120;  // median(last3) < 120s
inline constexpr int32_t  CASERT_BURST_UP_SLEW_1       = 2;    // upward slew ±2

// Burst trigger: tier 2 (severe)
inline constexpr int32_t  CASERT_BURST_LAG_ENTER_2     = 12;   // lag >= 12
inline constexpr int64_t  CASERT_BURST_MEDIAN_FAST_2   = 60;   // median(last3) < 60s
inline constexpr int32_t  CASERT_BURST_UP_SLEW_2       = 3;    // upward slew ±3

// Burst exit conditions
inline constexpr int32_t  CASERT_BURST_EXIT_LAG        = 4;    // exit when lag <= 4
inline constexpr int64_t  CASERT_BURST_EXIT_MEDIAN     = 180;  // or median(last3) >= 180s

// Burst ceiling: follows hard ceiling
inline constexpr int32_t  CASERT_BURST_PROFILE_CEILING = 10;   // H10 (block 5075+)
inline constexpr int32_t  CASERT_BURST_PROFILE_CEILING_H11 = 11; // H11 (block 5480+)

// Confirmation: require 2 consecutive evaluations
inline constexpr int32_t  CASERT_BURST_CONFIRM_TICKS   = 2;

// bitsQ high-profile relax guard
// When profile >= H9 AND lag >= 8, limit bitsQ downward adjustment
inline constexpr int32_t  CASERT_BITSQ_GUARD_PROFILE   = 9;    // H9+
inline constexpr int32_t  CASERT_BITSQ_GUARD_LAG       = 8;    // lag >= 8
inline constexpr int32_t  CASERT_BITSQ_RELAX_GUARD_DEN = 64;   // max 1/64 ≈ 1.56% relax
inline constexpr int32_t  CASERT_V3_LAG_FLOOR_DIV = 8;       // lag_floor = lag / 8

// cASERT V3.1 fork — activated at block 4200
// Fix: slew rate uses stored profile_index from BlockMeta instead of PID recomputation
// This prevents the equalizer from jumping more than ±3 in practice
inline constexpr int64_t  CASERT_V3_1_FORK_HEIGHT = 4110;

// cASERT V4 fork — Ahead Guard + profile_index persistence fix
// 1. Prevents bitsQ from dropping aggressively while chain is materially ahead.
// 2. Uses INT32_MIN sentinel so legit B0 (profile_index=0) can no longer trigger
//    the V3.1 "missing profile" fallback that disables the slew rate (the bug
//    causing B0→H12 jumps observed in the 4150-4170 oscillation loop).
inline constexpr int64_t  CASERT_V4_FORK_HEIGHT       = 4170;
inline constexpr int32_t  CASERT_AHEAD_ENTER          = 16;   // enter ahead correction when >= 16 ahead
inline constexpr int32_t  CASERT_AHEAD_EXIT           = 8;    // V4-only hysteresis exit (V5 is stateless)
// In ahead correction: max downward delta = prev_bitsq / 64 (~1.56%)
// vs normal max delta = prev_bitsq / 8 (12.5%). This is 8× slower relaxation.
inline constexpr int32_t  CASERT_AHEAD_DELTA_DEN      = 64;   // 1/64 ≈ 1.56% max downward per block
inline constexpr int32_t  CASERT_AHEAD_PROFILE_THRESH = 8;    // H8+ triggers stronger clamp

// cASERT V5 fork — unified liveness + determinism fix
// 1. Ahead Guard becomes stateless (removes V4 static bool latent consensus risk).
// 2. Safety rule 1 re-applied AFTER slew rate (was being shadowed by slew when
//    prev_H was high and chain had just crossed into lag <= 0).
// 3. Emergency Behind Release (EBR): stateless cliffs force H downward when chain
//    falls materially behind schedule (lag <= -10).
// 4. Anti-stall floor reduced from 2h to 60min at V5 heights for faster rescue
//    in small networks with limited hashrate.
// 5. Extreme profile entry cap: H10, H11, H12 may only be climbed +1 per block.
//    Prevents overshoot into the worst brake profiles (observed at block 4184
//    where B0→H6→H9→H12 in 3 blocks crashed stability 100% → 3%).
// See docs/internal/casert-v5-design.md for full rationale.
// Activation moved to 4300 (from earlier 4350 → 4260 iterations): the
// monitor confirmed RED status with 4 overshoots in 97 blocks and a loop
// pattern every ~19-35 blocks, but 4260 (26 blocks margin) was judged too
// aggressive for a coordinated fork with external miners. 4300 gives
// ~65 blocks = 6-10h margin — enough for ANN + rebuild + restart by all
// active miners, while still cutting the overshoot cycle after at most
// one more occurrence.
inline constexpr int64_t  CASERT_V5_FORK_HEIGHT       = 4300;
inline constexpr int64_t  CASERT_ANTISTALL_FLOOR_V5   = 3600;  // 60 min (V4 was 7200 = 2h)
// EBR cliff thresholds — the lower the lag, the lower the forced H floor
inline constexpr int32_t  CASERT_EBR_ENTER            = -10;   // 100 min behind → force H <= B0
inline constexpr int32_t  CASERT_EBR_LEVEL_E2         = -15;   // 150 min behind → force H <= E2
inline constexpr int32_t  CASERT_EBR_LEVEL_E3         = -20;   // 200 min behind → force H <= E3
inline constexpr int32_t  CASERT_EBR_LEVEL_E4         = -25;   // 250 min behind → force H <= E4 (H_MIN)
// Extreme profile entry cap — H10+ is "extreme range" (stability ≤15%).
// When the PID/slew/lag_floor would push H into this range, only +1 per block
// is allowed. Descent from extreme is unrestricted (normal slew + safety rule
// post-slew + EBR all still apply). Asymmetric by design: slow brake entry,
// fast brake exit.
inline constexpr int32_t  CASERT_V5_EXTREME_MIN       = 10;    // H10 is the first "extreme" profile

// --- cASERT equalizer ---
// EWMA smoothing constants (denominator = 256 for shift-by-8 division)
inline constexpr int32_t  CASERT_EWMA_SHORT_ALPHA = 32;    // 256/8  = 8-block window
inline constexpr int32_t  CASERT_EWMA_LONG_ALPHA  = 3;     // 256/96 ≈ 96-block window
inline constexpr int32_t  CASERT_EWMA_VOL_ALPHA   = 16;    // 16-block volatility window
inline constexpr int32_t  CASERT_EWMA_DENOM       = 256;   // 2^8

// Integrator
inline constexpr int32_t  CASERT_INTEG_RHO        = 253;   // 253/256 ≈ 0.988 leak
inline constexpr int32_t  CASERT_INTEG_ALPHA       = 1;     // integrator gain
inline constexpr int64_t  CASERT_INTEG_MAX         = 6553600; // 100.0 in Q16.16

// Control signal gains (Q16.16) — tuned to prevent oscillation
// Total: K_R(0.05) + K_L(0.40) + K_I(0.15) + K_B(0.05) + K_V(0.02) = 0.67
// Lag dominates (60% of total), short-term signals heavily damped
inline constexpr int32_t  CASERT_K_R              = 3277;   // 0.05 — instantaneous (was 0.25)
inline constexpr int32_t  CASERT_K_L              = 26214;  // 0.40 — schedule lag (was 0.10)
inline constexpr int32_t  CASERT_K_I              = 9830;   // 0.15 — integrator (was 0.05)
inline constexpr int32_t  CASERT_K_B              = 3277;   // 0.05 — burst score (was 0.30)
inline constexpr int32_t  CASERT_K_V              = 1311;   // 0.02 — volatility (was 0.10)

// Profile index bounds
inline constexpr int32_t  CASERT_H_MIN            = -7;     // E7 (emergency easing)
inline constexpr int32_t  CASERT_H_MAX_PRE_CAL         = 12;     // V6: H12 max (pre-V7)
inline constexpr int32_t  CASERT_H_MAX            = 35;     // V6-cal: H35 max — all 43 profiles active (E7 through H35)
inline constexpr int32_t  CASERT_HYSTERESIS        = 0;     // v1: disabled

// dt clamp for r_n calculation
inline constexpr int64_t  CASERT_DT_MIN           = 1;      // prevent div by zero
inline constexpr int64_t  CASERT_DT_MAX           = 86400;  // 24h cap

// --- cASERT anti-stall ---
// Decay is zone-based and targets B0 as natural destination.
// Easing profiles (E1-E4) only activate after 6+ additional hours at B0.
inline constexpr int64_t  CASERT_ANTISTALL_FLOOR  = 7200;   // minimum 2 hours
inline constexpr int64_t  CASERT_ANTISTALL_EASING_EXTRA = 21600; // 6h at B0 before easing
inline constexpr int32_t  CASERT_ANTISTALL_INTEG_DECAY = 240; // I *= 240/256 per 600s

// --- cASERT profile struct ---
struct CasertProfile {
    int32_t scale, steps, k, margin;
};

// --- cASERT legacy profile table (40 profiles, pre-V8: blocks < 5750) ---
// Preserved for consensus compatibility with historical blocks.
// Index: -4=E4, -3=E3, ..., 0=B0, 1=H1, ..., 35=H35
inline constexpr int32_t CASERT_H_MIN_LEGACY = -4;
inline constexpr int32_t CASERT_PROFILE_COUNT_LEGACY = 40;
inline constexpr CasertProfile CASERT_PROFILES_LEGACY[] = {
    // E4       E3       E2       E1       B0
    {1,2,3,280}, {1,3,3,240}, {1,4,3,225}, {1,4,4,205}, {1,4,4,185},
    // H1       H2       H3       H4       H5
    {1,5,4,170}, {1,5,5,160}, {1,6,5,150}, {1,6,6,145}, {2,5,5,140},
    // H6       H7       H8       H9
    {2,6,5,135}, {2,6,6,130}, {2,7,6,125}, {2,7,7,120},
    // H10-H35: scale=2, k and steps alternate +1, margin 115
    {2, 8, 7,115},  // H10
    {2, 8, 8,115},  // H11
    {2, 9, 8,115},  // H12
    {2, 9, 9,115},  // H13
    {2,10, 9,115},  // H14
    {2,10,10,115},  // H15
    {2,11,10,115},  // H16
    {2,11,11,115},  // H17
    {2,12,11,115},  // H18
    {2,12,12,115},  // H19
    {2,13,12,115},  // H20
    {2,13,13,115},  // H21
    {2,14,13,115},  // H22
    {2,14,14,115},  // H23
    {2,15,14,115},  // H24
    {2,15,15,115},  // H25
    {2,16,15,115},  // H26
    {2,16,16,115},  // H27
    {2,17,16,115},  // H28
    {2,17,17,115},  // H29
    {2,18,17,115},  // H30
    {2,18,18,115},  // H31
    {2,19,18,115},  // H32
    {2,19,19,115},  // H33
    {2,20,19,115},  // H34
    {2,20,20,115},  // H35
};

// --- cASERT profile table V8 (43 profiles, block 5750+) ---
// Each profile: { scale, steps, k, margin }
// Index: -7=E7, -6=E6, ..., 0=B0, 1=H1, ..., 35=H35
// Active range: E7(-7) to H35(+35).
// V8 (block 5750): extended from 40 to 43 profiles. E7-E5 prepended,
// E4-H2 margins revised to 5-point gradient. E7 is deepest easing.
// Dynamic lag cap (H <= lag) replaces fixed H11/H12 reservation.

inline constexpr CasertProfile CASERT_PROFILES[] = {
    // E7       E6       E5       E4       E3       E2       E1       B0
    {1,1,1,200}, {1,2,1,195}, {1,2,2,190}, {1,3,2,185}, {1,3,3,180}, {1,4,3,175}, {1,4,4,170}, {1,4,4,165},
    // H1       H2       H3       H4       H5
    {1,5,4,160}, {1,5,5,155}, {1,6,5,150}, {1,6,6,145}, {2,5,5,140},
    // H6       H7       H8       H9
    {2,6,5,135}, {2,6,6,130}, {2,7,6,125}, {2,7,7,120},
    // H10-H35: scale=2, k and steps alternate +1, margin 115
    {2, 8, 7,115},  // H10
    {2, 8, 8,115},  // H11 — margin=115 from block 10,000 (was 110)
    {2, 9, 8,115},  // H12 — margin=115 (was 105)
    {2, 9, 9,115},  // H13 — margin=115 (was 100)
    {2,10, 9,115},  // H14
    {2,10,10,115},  // H15
    {2,11,10,115},  // H16
    {2,11,11,115},  // H17
    {2,12,11,115},  // H18
    {2,12,12,115},  // H19
    {2,13,12,115},  // H20
    {2,13,13,115},  // H21
    {2,14,13,115},  // H22
    {2,14,14,115},  // H23
    {2,15,14,115},  // H24
    {2,15,15,115},  // H25
    {2,16,15,115},  // H26
    {2,16,16,115},  // H27
    {2,17,16,115},  // H28
    {2,17,17,115},  // H29
    {2,18,17,115},  // H30
    {2,18,18,115},  // H31
    {2,19,18,115},  // H32
    {2,19,19,115},  // H33
    {2,20,19,115},  // H34
    {2,20,20,115},  // H35
};
inline constexpr int32_t CASERT_PROFILE_COUNT = 43;
// Index offset: profile_index - CASERT_H_MIN = array index
// profile_index -7 → array[0] (E7)
// profile_index -4 → array[3] (E4)
// profile_index  0 → array[7] (B0)
// profile_index  9 → array[16] (H9)
// profile_index 35 → array[42] (H35) — highest hardening profile

// =============================================================================
// Dynamic Fee Policy (activates at block 10,000)
// =============================================================================
// Policy-only (NOT consensus). Affects relay/mempool acceptance, not block validity.
// Before block 10,000: static MIN_RELAY_FEE_PER_BYTE = 1 stock/byte
// After block 10,000: dynamic relay floor based on mempool pressure

inline constexpr int64_t  DYNAMIC_FEE_ACTIVATION_HEIGHT   = 10000;

// Base relay fee (same as current)
inline constexpr int64_t  DYNAMIC_FEE_BASE                = 1;     // stocks/byte (floor)

// Pressure thresholds (mempool entry count)
inline constexpr size_t   DYNAMIC_FEE_PRESSURE_LOW        = 100;   // >100 tx → 2x
inline constexpr size_t   DYNAMIC_FEE_PRESSURE_MED        = 500;   // >500 tx → 5x
inline constexpr size_t   DYNAMIC_FEE_PRESSURE_HIGH       = 2000;  // >2000 tx → 10x
inline constexpr size_t   DYNAMIC_FEE_PRESSURE_EXTREME    = 4000;  // >4000 tx → 25x

// Multipliers per pressure tier
inline constexpr int64_t  DYNAMIC_FEE_MULT_LOW            = 2;
inline constexpr int64_t  DYNAMIC_FEE_MULT_MED            = 5;
inline constexpr int64_t  DYNAMIC_FEE_MULT_HIGH           = 10;
inline constexpr int64_t  DYNAMIC_FEE_MULT_EXTREME        = 25;

// Ceiling: normal max (overridden by emergency levels)
inline constexpr int64_t  DYNAMIC_FEE_CEILING              = 50;   // stocks/byte (GREEN-RED)

// Emergency escalation ceilings (automatic, no manual activation)
inline constexpr int64_t  DYNAMIC_FEE_EMERGENCY_250X       = 250;  // BLACK level 1
inline constexpr int64_t  DYNAMIC_FEE_EMERGENCY_1000X      = 1000; // BLACK level 2 (after 5 min)
inline constexpr int64_t  DYNAMIC_FEE_EMERGENCY_5000X      = 5000; // BLACK level 3 (after 15 min)

// Pressure score thresholds for spam shield levels
inline constexpr int32_t  SPAM_LEVEL_GREEN                 = 0;    // pressure < 20
inline constexpr int32_t  SPAM_LEVEL_YELLOW                = 20;   // pressure 20-39
inline constexpr int32_t  SPAM_LEVEL_ORANGE                = 40;   // pressure 40-59
inline constexpr int32_t  SPAM_LEVEL_RED                   = 60;   // pressure 60-79
inline constexpr int32_t  SPAM_LEVEL_BLACK                 = 80;   // pressure >= 80

// Relay floor multipliers per level
inline constexpr int64_t  SPAM_MULT_GREEN                  = 1;
inline constexpr int64_t  SPAM_MULT_YELLOW                 = 3;
inline constexpr int64_t  SPAM_MULT_ORANGE                 = 10;
inline constexpr int64_t  SPAM_MULT_RED                    = 50;
inline constexpr int64_t  SPAM_MULT_BLACK                  = 250;  // initial, escalates

// Per-level admission limits
inline constexpr size_t   SPAM_PEER_LIMIT_GREEN            = 30;   // tx/peer/min
inline constexpr size_t   SPAM_PEER_LIMIT_YELLOW           = 20;
inline constexpr size_t   SPAM_PEER_LIMIT_ORANGE           = 12;
inline constexpr size_t   SPAM_PEER_LIMIT_RED              = 6;
inline constexpr size_t   SPAM_PEER_LIMIT_BLACK            = 3;

inline constexpr size_t   SPAM_ADDR_LIMIT_GREEN            = 25;   // tx/address in mempool
inline constexpr size_t   SPAM_ADDR_LIMIT_YELLOW           = 15;
inline constexpr size_t   SPAM_ADDR_LIMIT_ORANGE           = 10;
inline constexpr size_t   SPAM_ADDR_LIMIT_RED              = 5;
inline constexpr size_t   SPAM_ADDR_LIMIT_BLACK            = 2;

// Hysteresis: fast to harden, slow to relax
inline constexpr int32_t  SPAM_ESCALATION_TICKS            = 2;    // consecutive ticks to escalate
inline constexpr int64_t  SPAM_RELAXATION_SECONDS          = 600;  // 10 min stable below threshold to relax
inline constexpr int64_t  SPAM_BLACK_ESCALATE_5MIN         = 300;  // seconds before 250x → 1000x
inline constexpr int64_t  SPAM_BLACK_ESCALATE_15MIN        = 900;  // seconds before 1000x → 5000x

// Anti-spam: max tx from same address in mempool (default, overridden by level)
inline constexpr size_t   MEMPOOL_MAX_PER_ADDRESS          = 25;

// Anti-spam: rate limit per peer (tx/minute, default, overridden by level)
inline constexpr size_t   RELAY_MAX_TX_PER_PEER_PER_MIN    = 30;

// Dust threshold (unchanged, for reference)
// Already defined in tx_validation.h as DUST_THRESHOLD = 10000

// Fee estimator bands (stocks/byte) — informational for explorer/wallet
// These are computed dynamically from mempool state, not constants.

// ConvergenceX mainnet baseline (match Python)
inline constexpr int32_t CX_N         = 32;
inline constexpr int32_t CX_ROUNDS_M  = 100000;
inline constexpr int32_t CX_SCRATCH_M = 4096;
inline constexpr int32_t CX_LR_SHIFT  = 18;
inline constexpr int32_t CX_LAM       = 100;
inline constexpr int32_t CX_CP_M      = 6250;  // 100000/16

// ConvergenceX baseline stability (B0 profile matches these)
inline constexpr int32_t CX_STB_SCALE  = 1;
inline constexpr int32_t CX_STB_K      = 4;
inline constexpr int32_t CX_STB_MARGIN = 185;     // Genesis B0 margin (pre-V8; V8+ B0=165 via profile table)
inline constexpr int32_t CX_STB_STEPS  = 4;
inline constexpr int32_t CX_STB_LR     = 20;   // LR_SHIFT+2

inline constexpr int32_t CX_C_NUM = 7;
inline constexpr int32_t CX_C_DEN = 10;
inline constexpr int32_t CX_M_NUM = 1;
inline constexpr int32_t CX_M_DEN = 1;

// CX dev
inline constexpr int32_t CX_ROUNDS_D  = 512;
inline constexpr int32_t CX_SCRATCH_D = 32;
inline constexpr int32_t CX_CP_D      = 64;

// CX testnet
inline constexpr int32_t CX_ROUNDS_T  = 1200;
inline constexpr int32_t CX_SCRATCH_T = 64;
inline constexpr int32_t CX_CP_T      = 128;

// --- Transcript V2: segment commitments + sampled round verification ---
inline constexpr int32_t CX_SEGMENT_LEN    = 1024;  // rounds per segment
inline constexpr int32_t CX_CHAL_SEGMENTS  = 6;     // segments challenged per block
inline constexpr int32_t CX_CHAL_STEPS     = 2;     // rounds challenged per segment
// CX_NSEG derived: ceil(rounds / segment_len)
inline constexpr int32_t CX_NSEG_M = (CX_ROUNDS_M + CX_SEGMENT_LEN - 1) / CX_SEGMENT_LEN;
inline constexpr int32_t CX_NSEG_T = (CX_ROUNDS_T + CX_SEGMENT_LEN - 1) / CX_SEGMENT_LEN;
inline constexpr int32_t CX_NSEG_D = (CX_ROUNDS_D + CX_SEGMENT_LEN - 1) / CX_SEGMENT_LEN;

// Constitutional addresses (hardcoded at genesis, immutable)
constexpr const char* ADDR_MINER_FOUNDER = "sost1059d1ef8639bcf47ec35e9299c17dc0452c3df33";
constexpr const char* ADDR_GOLD_VAULT    = "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d";
constexpr const char* ADDR_POPC_POOL     = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f";

// Timestamp rules
inline constexpr int32_t MTP_WINDOW       = 11;
inline constexpr int64_t MAX_FUTURE_DRIFT = 600;

// Tightened future-drift window applied at heights >= CASERT_STAGED_RELIEF_HEIGHT.
// Without this tightening, a miner could pre-mine downstream staged-relief
// profiles by setting the candidate timestamp 600 seconds in the future, then
// only releasing the block once real time caught up.
//
// Calibration: matches CASERT_STAGED_STEP_SECONDS, so the maximum amount a
// miner can anticipate by setting a future timestamp is exactly one cascade
// step — never two. A drift equal to the step locks anticipation to the
// next-step boundary while still tolerating clock skew typical of
// well-configured Linux hosts (a properly NTP-synced host runs well under
// the cap).
inline constexpr int64_t MAX_FUTURE_DRIFT_STAGED = 60;

} // namespace sost
