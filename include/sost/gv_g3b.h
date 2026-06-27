#pragma once
// =============================================================================
// gv_g3b.h — Gold Vault G3b: rate-limit (timelock) + cumulative-outflow cap.
//
// G3a (in gold_vault_slice1.h) bounds a SINGLE vault spend. G3b bounds the
// vault's spending OVER TIME:
//   - rate-limit : a minimum number of blocks between consecutive vault spends
//   - cumulative : a hard ceiling on the TOTAL external outflow ever spent
//
// DETERMINISTIC CHAIN STATE — NO new serialized field.
// ----------------------------------------------------------------------------
// G3b needs "when did the vault last spend?" and "how much has it spent in
// total?". Rather than add a serialized StoredBlock field (which would require a
// chain-format migration AND careful reorg bookkeeping), both quantities are
// DERIVED as a pure function of the canonical chain (g_blocks): a forward scan
// that tracks the set of live vault outpoints and accumulates external outflow
// each time one is spent. Because the value is a function of whatever chain is
// currently active, it is reorg-safe BY CONSTRUCTION — a reorg simply re-derives
// against the new active chain, with nothing stale to roll back. See
// gv_g3b_derive_state() at the call site in src/sost-node.cpp.
//
// INERT BY DEFAULT.
// ----------------------------------------------------------------------------
// The live consensus sentinels (GV_SLICE1_RATE_LIMIT_BLOCKS and
// GV_SLICE1_CUMULATIVE_CAP_STOCKS in gold_vault_slice1.h) are BOTH 0 (disabled).
// With either sentinel 0 the corresponding helper returns true unconditionally,
// so wiring G3b into process_block is a pure no-op and the chain replays
// byte-for-byte identical. The pilot TARGET values below are documented for the
// future coordinated activation commit; the helpers are PARAMETERISED so tests
// can exercise non-zero windows/caps without flipping the live sentinels.
//
// Pure, header-only, no I/O — safe to include anywhere.
// =============================================================================
#include <cstdint>
#include "sost/consensus_constants.h"   // STOCKS_PER_SOST

namespace sost {

// ---- Founder-pilot DOCUMENTED TARGETS (NOT yet live) ------------------------
// The capped founder-only pilot intends these once G3b is activated. They stay
// documentation until a coordinated activation commit copies them onto the live
// GV_SLICE1_* sentinels (and flips GV_SLICE1_ACTIVATION_HEIGHT). Mirrors the
// dry-run rails in scripts/gold_vault_governance_dry_run.py
// (RATE_LIMIT_BLOCKS=144, PILOT_CUMULATIVE_CAP_SOST=10).
inline constexpr int64_t GV_G3B_PILOT_RATE_LIMIT_BLOCKS    = 144;               // ~24h @ 10-min blocks
inline constexpr int64_t GV_G3B_PILOT_CUMULATIVE_CAP_STOCKS = 10 * STOCKS_PER_SOST; // 10 SOST total

// ---- Derived chain state, as-of (but EXCLUDING) the block being validated ----
struct GvG3bState {
    int64_t last_spend_height  = -1;  // height of the most recent prior vault spend; -1 = none
    int64_t cumulative_outflow = 0;   // total external out from the vault so far, in stocks
};

// Blocks elapsed since the last vault spend. If there has been no prior spend,
// the rate-limit is trivially satisfied → return INT64_MAX.
inline int64_t gv_g3b_blocks_since(const GvG3bState& s, int64_t height) {
    if (s.last_spend_height < 0)        return INT64_MAX;  // no prior spend
    if (height <= s.last_spend_height)  return 0;          // defensive (non-monotonic)
    return height - s.last_spend_height;
}

// G3b rate-limit. Parameterised: consensus passes GV_SLICE1_RATE_LIMIT_BLOCKS
// (0 = disabled); tests pass a non-zero window. rate_blocks <= 0 → disabled.
inline constexpr bool gv_g3b_rate_ok(int64_t blocks_since_last_spend, int64_t rate_blocks) {
    if (rate_blocks <= 0)              return true;   // sentinel: rate-limit disabled
    if (blocks_since_last_spend < 0)   return false;  // defensive: corrupt state
    return blocks_since_last_spend >= rate_blocks;
}

// G3b cumulative cap. cumulative_after = prior cumulative outflow + THIS spend's
// external out. Parameterised: consensus passes GV_SLICE1_CUMULATIVE_CAP_STOCKS
// (0 = disabled); tests pass a non-zero cap. cap_stocks <= 0 → disabled.
inline constexpr bool gv_g3b_cumulative_ok(int64_t cumulative_after, int64_t cap_stocks) {
    if (cap_stocks <= 0)        return true;   // sentinel: cumulative cap disabled
    if (cumulative_after < 0)   return false;  // defensive: overflow / corrupt
    return cumulative_after <= cap_stocks;
}

} // namespace sost
