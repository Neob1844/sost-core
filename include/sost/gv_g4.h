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
#include "sost/transaction.h"   // Transaction, TxOutput — for the coinbase approval marker
#include <cstdint>
#include <climits>
#include <array>

namespace sost {

inline constexpr int32_t GV_G4_SIGNAL_WINDOW  = 67;   // blocks
inline constexpr int32_t GV_G4_THRESHOLD_PCT  = 90;   // affirmative %
inline constexpr int32_t GV_G4_FOUNDATION_PCT = 10;   // +10% quality boost

// SIGNALING CHANNEL = COINBASE APPROVAL MARKER (chosen 2026-06-07).
//   The block-header `version` field cannot carry signal bits (SbPoW pins it to
//   1/2). Instead, a block's miner approves the pending vault spend by including
//   a recognized 0-value marker output in its coinbase (GV_G4_APPROVAL_PKH). The
//   validator counts, over the previous GV_G4_SIGNAL_WINDOW blocks, how many
//   coinbases carry the marker, and feeds that count to the channel-agnostic
//   tally below. Deterministic from chain state; no SbPoW/header change. The
//   coinbase-shape (CB5/CB6) rule must allow this extra recognized output ONLY
//   when G4 is active (gated). See docs/V14_GOLD_VAULT_G4_DESIGN.md.

// Fixed, unspendable marker pkh = ASCII "GV-G4-APPROVE-MARKER" (20 bytes). No
// private key exists for it; a 0-value coinbase output here is a pure signal.
inline constexpr std::array<uint8_t,20> GV_G4_APPROVAL_PKH = {
    0x47,0x56,0x2D,0x47,0x34,0x2D,0x41,0x50,0x50,0x52,
    0x4F,0x56,0x45,0x2D,0x4D,0x41,0x52,0x4B,0x45,0x52 };

// True iff this coinbase tx carries the G4 approval marker (0-value output to
// GV_G4_APPROVAL_PKH). Pure, no chain state.
inline bool gv_g4_coinbase_approves(const Transaction& coinbase) {
    for (const auto& o : coinbase.outputs)
        if (o.amount == 0 && o.pubkey_hash == GV_G4_APPROVAL_PKH) return true;
    return false;
}

// Activation gate. Gold Vault governance is part of the V15 automation bundle
// (block 20000), NOT V14 (block 15000 hardening, ships untouched). Testnet active
// @ V15_HEIGHT=300; mainnet deferred until the full Gold Vault G1-G5 is built +
// soaked, then flipped to V15_HEIGHT.
#ifdef SOST_TESTNET_FORKS
inline constexpr int64_t GV_G4_ACTIVATION_HEIGHT = V15_HEIGHT;
#else
inline constexpr int64_t GV_G4_ACTIVATION_HEIGHT = INT64_MAX;  // -> V15_HEIGHT in final commit
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

// W3: count G4 approval markers over the window [h-window, h-1] using a per-height
// lookup. `approves(height)` returns true iff the coinbase at that height carries
// the marker. The current height `h` is NOT included (only PRECEDING blocks), and
// heights < 0 are skipped. Pure — the caller supplies the chain lookup, so this is
// unit-testable without the node. Result is clamped to [0, window].
template <typename Approves>
inline int32_t gv_g4_count_window(int64_t h, Approves approves,
                                  int32_t window = GV_G4_SIGNAL_WINDOW) {
    int32_t yes = 0;
    for (int64_t hh = h - window; hh <= h - 1; ++hh) {
        if (hh < 0) continue;
        if (approves(hh)) { ++yes; if (yes >= window) break; }
    }
    return yes;
}

} // namespace sost
