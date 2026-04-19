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

// Burst ceiling: NEVER push above H10 in burst mode
inline constexpr int32_t  CASERT_BURST_PROFILE_CEILING = 10;   // H10

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
inline constexpr int32_t  CASERT_H_MIN            = -4;     // E4 (emergency easing)
inline constexpr int32_t  CASERT_H_MAX_PRE_CAL         = 12;     // V6: H12 max (pre-V7)
inline constexpr int32_t  CASERT_H_MAX            = 35;     // V6-cal: H35 max — all 40 profiles active (E4 through H35)
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

// --- cASERT profile table (37 profiles) ---
// Each profile: { scale, steps, k, margin }
// Index: -4=E4, -3=E3, ..., 0=B0, 1=H1, ..., 32=H32
// Active range: E4(-4) to H32(+32).
// V7 (block 5100): extended from 17 to 37 profiles. H10+ redesigned with
// alternating k/steps increments and uniform 5-point margin gradient.
// Dynamic lag cap (H <= lag) replaces fixed H11/H12 reservation.
struct CasertProfile {
    int32_t scale, steps, k, margin;
};

inline constexpr CasertProfile CASERT_PROFILES[] = {
    // E4       E3       E2       E1       B0
    {1,2,3,280}, {1,3,3,240}, {1,4,3,225}, {1,4,4,205}, {1,4,4,185},
    // H1       H2       H3       H4       H5
    {1,5,4,170}, {1,5,5,160}, {1,6,5,150}, {1,6,6,145}, {2,5,5,140},
    // H6       H7       H8       H9
    {2,6,5,135}, {2,6,6,130}, {2,7,6,125}, {2,7,7,120},
    // H10-H32: scale=2, k and steps alternate +1, margin -5 per level
    {2, 8, 7,115},  // H10
    {2, 8, 8,110},  // H11
    {2, 9, 8,105},  // H12
    {2, 9, 9,100},  // H13 — margin fixed at 100 from here (k alone scales difficulty)
    {2,10, 9,100},  // H14
    {2,10,10,100},  // H15
    {2,11,10,100},  // H16
    {2,11,11,100},  // H17
    {2,12,11,100},  // H18
    {2,12,12,100},  // H19
    {2,13,12,100},  // H20
    {2,13,13,100},  // H21
    {2,14,13,100},  // H22
    {2,14,14,100},  // H23
    {2,15,14,100},  // H24
    {2,15,15,100},  // H25
    {2,16,15,100},  // H26
    {2,16,16,100},  // H27
    {2,17,16,100},  // H28
    {2,17,17,100},  // H29
    {2,18,17,100},  // H30
    {2,18,18,100},  // H31
    {2,19,18,100},  // H32
    {2,19,19,100},  // H33
    {2,20,19,100},  // H34
    {2,20,20,100},  // H35
};
inline constexpr int32_t CASERT_PROFILE_COUNT = 40;
// Index offset: profile_index - CASERT_H_MIN = array index
// profile_index -4 → array[0] (E4)
// profile_index  0 → array[4] (B0)
// profile_index  9 → array[13] (H9)
// profile_index 32 → array[36] (H32) — highest hardening profile

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
inline constexpr int32_t CX_STB_MARGIN = 185;     // Must match B0 profile in CASERT_PROFILES
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

} // namespace sost
