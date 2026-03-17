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

inline constexpr int64_t  BITSQ_HALF_LIFE       = 43200;   // 12 hours
inline constexpr int32_t  BITSQ_MAX_DELTA_NUM   = 1;       // relative delta cap numerator
inline constexpr int32_t  BITSQ_MAX_DELTA_DEN   = 16;      // relative delta cap denominator (6.25%)

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
inline constexpr int32_t  CASERT_H_MAX            = 9;      // H9 max (H10-H12 defined but capped)
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

// --- cASERT profile table (17 profiles) ---
// Each profile: { scale, steps, k, margin }
// Index: -4=E4, -3=E3, ..., 0=B0, 1=H1, ..., 12=H12
// Active range: E4(-4) to H9(+9). H10-H12 defined but capped (future reserve).
struct CasertProfile {
    int32_t scale, steps, k, margin;
};

inline constexpr CasertProfile CASERT_PROFILES[] = {
    // E4       E3       E2       E1       B0
    {1,2,3,280}, {1,3,3,240}, {1,4,3,225}, {1,4,4,205}, {1,4,4,185},
    // H1       H2       H3       H4       H5
    {1,5,4,170}, {1,5,5,160}, {1,6,5,150}, {1,6,6,145}, {2,5,5,140},
    // H6       H7       H8       H9       H10      H11      H12
    {2,6,5,135}, {2,6,6,130}, {2,7,6,125}, {2,7,7,120}, {3,7,6,115}, {3,7,7,110}, {3,8,7,105}
};
inline constexpr int32_t CASERT_PROFILE_COUNT = 17;
// Index offset: profile_index - CASERT_H_MIN = array index
// profile_index -4 → array[0] (E4)
// profile_index  0 → array[4] (B0)
// profile_index  9 → array[13] (H9)
// profile_index 12 → array[16] (H12) — reserved, capped at H9

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
constexpr const char* ADDR_MINER_FOUNDER = "sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429";
constexpr const char* ADDR_GOLD_VAULT    = "sost1505a886a372a34e0044e3953ea2c8c0f0d7a4724";
constexpr const char* ADDR_POPC_POOL     = "sost144cc82d3c711b5a9322640c66b94a520497ac40d";

// Timestamp rules
inline constexpr int32_t MTP_WINDOW       = 11;
inline constexpr int64_t MAX_FUTURE_DRIFT = 600;

} // namespace sost
