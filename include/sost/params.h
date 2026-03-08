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
inline constexpr int64_t GENESIS_TIME     = 1773360000; // 2026-03-13 00:00:00 UTC
inline constexpr int64_t TARGET_SPACING   = 600;
inline constexpr int64_t BLOCKS_PER_EPOCH = 131553;

// Emission math (integer-only)
inline constexpr int64_t R0_STOCKS      = 785100863;           // 7.85100863 SOST in stocks
inline constexpr int64_t EMISSION_Q_NUM = 7788007830714049LL;
inline constexpr int64_t EMISSION_Q_DEN = 10000000000000000LL;

// Q16.16 difficulty
inline constexpr uint32_t Q16_SHIFT     = 16;
inline constexpr uint32_t Q16_ONE       = 1u << Q16_SHIFT;
inline constexpr uint32_t LUT_ENTRIES   = 256;
inline constexpr uint32_t GENESIS_BITSQ = 353075;
inline constexpr uint32_t MIN_BITSQ     = Q16_ONE;
inline constexpr uint32_t MAX_BITSQ     = 255u * Q16_ONE;

// ASERT
inline constexpr int64_t  ASERT_HALF_LIFE  = 86400;
inline constexpr int32_t  ASERT_DOWN_STEPS = 2; // log2(4)
inline constexpr int32_t  ASERT_UP_STEPS   = 3; // log2(8)

// cASERT v5 thresholds (blocks ahead of schedule)
//   0– 4 → L1 neutral   | 5–25 → L2 light   | 26–50 → L3 moderate
//  51–75 → L4 strong    | 76+ → L5+ unbounded (scale = level + 1)
inline constexpr int32_t CASERT_L2_BLOCKS  = 5;    // unchanged
inline constexpr int32_t CASERT_L3_BLOCKS  = 26;   // was 20
inline constexpr int32_t CASERT_L4_BLOCKS  = 51;   // was 50
inline constexpr int32_t CASERT_L5_BLOCKS  = 76;   // was 75
inline constexpr int32_t CASERT_L6_BLOCKS  = 101;  // new
inline constexpr int32_t CASERT_L7_BLOCKS  = 151;  // new
inline constexpr int32_t CASERT_L8_BLOCKS  = 201;  // new
inline constexpr int32_t CASERT_L9_BLOCKS  = 251;  // new
inline constexpr int32_t CASERT_L10_BLOCKS = 301;  // new
// Above L10: level = 5 + (blocks_ahead - 76) / 50
// scale = level + 1 — unbounded, no ceiling

// ConvergenceX mainnet baseline (match Python)
inline constexpr int32_t CX_N         = 32;
inline constexpr int32_t CX_ROUNDS_M  = 100000;
inline constexpr int32_t CX_SCRATCH_M = 4096;
inline constexpr int32_t CX_LR_SHIFT  = 18;
inline constexpr int32_t CX_LAM       = 100;
inline constexpr int32_t CX_CP_M      = 6250;  // 100000/16

// ConvergenceX mainnet baseline
inline constexpr int32_t CX_STB_SCALE  = 1;    // L1 neutral = scale 1
inline constexpr int32_t CX_STB_K      = 4;
inline constexpr int32_t CX_STB_MARGIN = 180;
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

// Constitutional addresses (hardcoded at genesis, immutable)
constexpr const char* ADDR_MINER_FOUNDER = "sost13a22c277b5d5cbdc17ecc6c7bc33a9755b88d429";
constexpr const char* ADDR_GOLD_VAULT    = "sost1505a886a372a34e0044e3953ea2c8c0f0d7a4724";
constexpr const char* ADDR_POPC_POOL     = "sost144cc82d3c711b5a9322640c66b94a520497ac40d";

// Timestamp rules
inline constexpr int32_t MTP_WINDOW       = 11;
inline constexpr int64_t MAX_FUTURE_DRIFT = 600;

} // namespace sost
