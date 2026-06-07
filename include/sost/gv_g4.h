// gv_g4.h — V14 Gold Vault governance G4: 67-block miner signaling window.
//
// Pure, header-only tally logic for the affirmative miner-approval layer on top
// of Slice 1 (G1/G2/G3a). A vault spend needs >=90% miner approval over a
// 67-block window (floor 61/67), with a +10% foundation quality boost. Built and
// unit-tested in isolation BEFORE any block-validation wiring.
//
// Gate: DEFERRED on mainnet (INT64_MAX); ACTIVE on the testnet build
// (-DSOST_TESTNET_FORKS, at V14_HEIGHT) to dry-run. Below the gate, behaviour is
// unchanged. Integer-only arithmetic — deterministic on every node.
//
// See docs/V14_GOLD_VAULT_G4_DESIGN.md.
#pragma once
#include "sost/params.h"
#include <cstdint>
#include <climits>

namespace sost {

inline constexpr int32_t GV_G4_SIGNAL_WINDOW  = 67;   // blocks
inline constexpr int32_t GV_G4_THRESHOLD_PCT  = 90;   // affirmative %
inline constexpr int32_t GV_G4_FOUNDATION_PCT = 10;   // +10% quality boost

// SIGNALING CHANNEL — DESIGN DECISION PENDING.
//   The block-header `version` field CANNOT carry signaling bits: SbPoW pins it
//   to exactly 1 (pre-7100) or 2 (post-7100) and rejects anything else
//   (VERSION_MISMATCH). proposals.h's BIP9-style "bits 8-28 of version" is a
//   placeholder that is NOT consensus-wired for the same reason. The per-block
//   G4 approval signal must therefore travel through a different, deterministic
//   channel (candidate: a recognized coinbase approval marker, or a dedicated
//   approval-marker transaction counted per block over the window). The tally
//   below is intentionally CHANNEL-AGNOSTIC — it consumes a yes-count, however
//   that count is sourced. See docs/V14_GOLD_VAULT_G4_DESIGN.md.

// Activation gate (testnet active @ V14_HEIGHT=200; mainnet deferred until the
// full Gold Vault G1-G5 is built + soaked, then flipped to V14_HEIGHT).
#ifdef SOST_TESTNET_FORKS
inline constexpr int64_t GV_G4_ACTIVATION_HEIGHT = V14_HEIGHT;
#else
inline constexpr int64_t GV_G4_ACTIVATION_HEIGHT = INT64_MAX;  // -> V14_HEIGHT in final commit
#endif

inline constexpr bool gv_g4_active_at(int64_t height) {
    return height >= GV_G4_ACTIVATION_HEIGHT;
}

// ceil(window * pct / 100), integer-only.
inline constexpr int32_t gv_g4_ceil_pct(int32_t window, int32_t pct) {
    return (window <= 0 || pct <= 0) ? 0 : (window * pct + 99) / 100;
}

// Minimum YES blocks required to approve (61 of 67 at the defaults).
inline constexpr int32_t gv_g4_approval_floor(int32_t window = GV_G4_SIGNAL_WINDOW,
                                              int32_t pct = GV_G4_THRESHOLD_PCT) {
    return gv_g4_ceil_pct(window, pct);
}

// Effective YES blocks added by the foundation quality boost (7 at defaults).
inline constexpr int32_t gv_g4_foundation_weight(int32_t window = GV_G4_SIGNAL_WINDOW,
                                                 int32_t pct = GV_G4_FOUNDATION_PCT) {
    return gv_g4_ceil_pct(window, pct);
}

// effective_yes = min(window, miner_yes + (foundation ? weight : 0))
inline constexpr int32_t gv_g4_effective_yes(int32_t miner_yes, bool foundation_signaled,
                                             int32_t window = GV_G4_SIGNAL_WINDOW) {
    if (miner_yes < 0) return 0;
    int32_t e = miner_yes + (foundation_signaled ? gv_g4_foundation_weight(window) : 0);
    return e > window ? window : e;
}

// Is a vault-spend proposal approved by the window? `miner_yes` is the count of
// approving blocks in the preceding GV_G4_SIGNAL_WINDOW (sourced by the channel
// chosen above), `foundation_signaled` adds the +10% quality boost.
inline constexpr bool gv_g4_window_approved(int32_t miner_yes, bool foundation_signaled,
                                            int32_t window = GV_G4_SIGNAL_WINDOW) {
    if (miner_yes < 0 || miner_yes > window) return false;   // defensive
    return gv_g4_effective_yes(miner_yes, foundation_signaled, window)
               >= gv_g4_approval_floor(window);
}

} // namespace sost
