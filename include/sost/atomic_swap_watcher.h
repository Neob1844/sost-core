// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap — local non-custodial watcher / auto-pilot (OTC-2)
// =============================================================================
//
// Pure, userspace, non-consensus. The watcher decides — from chain facts the
// caller supplies — when the wallet should auto-CLAIM (a counterparty lock once
// the preimage is known) or auto-REFUND (its own lock once the timeout opens),
// and it serialises its watchlist so the wallet can RESUME after a restart.
//
// The watcher NEVER signs, NEVER broadcasts, NEVER talks to a chain directly,
// and NEVER holds funds. `DecideWatchAction` returns the action the wallet
// should take; the wallet (with the user's key, via the OTC-1 builders) is what
// actually builds/signs/submits — and on mainnet the HTLC gate (INT64_MAX)
// still rejects every HTLC tx, so the whole pipeline is no-op until OTC-FLIP.
//
// One WatchedSwap = one SOST-side HTLC LOCK utxo and this wallet's relationship
// to it: either we can CLAIM it (we are the recipient; we need the preimage) or
// we can REFUND it (we created it; we recover after the timeout).
// =============================================================================
#pragma once

#include "sost/atomic_swap_coordinator.h"  // Role
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {

using coordinator::Role;  // (from atomic_swap_coordinator.h)

// This wallet's spend relationship to one SOST HTLC LOCK.
enum class WatchSide : uint8_t { Claimant, Refunder };
const char* WatchSideName(WatchSide s);

// The action the wallet should take for a watched swap right now.
enum class WatchAction : uint8_t {
    Wait,    // nothing to do yet
    Claim,   // build+submit an HTLC_CLAIM (preimage known, before timeout)
    Refund,  // build+submit an HTLC_REFUND (timeout open, still unspent)
    Done     // the lock was already spent (claimed/refunded) — stop watching
};
const char* WatchActionName(WatchAction a);

// Persistent record of one SOST-side HTLC LOCK this wallet is watching. All
// chain facts (height, unspent status, revealed preimage) are supplied by the
// caller; the watcher itself is pure.
struct WatchedSwap {
    std::string  swap_id;                          // ties to an off-chain Offer
    WatchSide    side = WatchSide::Refunder;        // our relationship to this lock
    std::array<uint8_t, 32> sost_lock_txid{};       // the LOCK utxo
    uint32_t     sost_lock_vout = 0;
    std::array<uint8_t, 32> hashlock{};             // sha256(secret)
    int64_t      sost_refund_height = 0;            // refund opens at this SOST height
    std::array<uint8_t, 20> claim_pkh{};            // who can claim
    std::array<uint8_t, 20> refund_pkh{};           // who can refund
    bool         have_preimage = false;             // Claimant: secret known?
    std::array<uint8_t, 32> preimage{};
    bool         sost_spent = false;                // lock already claimed/refunded
};

// Pure auto-pilot decision. `current_sost_height` is the chain tip; `lock_unspent`
// is true iff the LOCK utxo is still in the UTXO set. No I/O, no signing.
//
//   Done   : sost_spent OR the LOCK utxo is gone (someone already spent it).
//   Claimant: Claim iff have_preimage && current_height < refund_height (window open).
//   Refunder: Refund iff current_height >= refund_height.
//   else    : Wait.
WatchAction DecideWatchAction(const WatchedSwap& s,
                              int64_t current_sost_height,
                              bool lock_unspent);

// Ingest a preimage observed on-chain (e.g. from a counterparty HTLC_CLAIM
// witness) into a Claimant swap. Returns true iff sha256(preimage)==hashlock
// (and then sets have_preimage). A non-matching preimage is ignored.
bool IngestRevealedPreimage(WatchedSwap& s, const std::array<uint8_t, 32>& preimage);

// -----------------------------------------------------------------------------
// Persistence — deterministic text (one swap per line, "key=hex;..."). Pure
// string<->struct so the wallet can write the watchlist to a file and re-load
// it after a restart (resume). No file I/O here.
// -----------------------------------------------------------------------------
std::string SerializeWatchedSwap(const WatchedSwap& s);
bool        ParseWatchedSwap(const std::string& line, WatchedSwap& out);
std::string SerializeWatchlist(const std::vector<WatchedSwap>& v);
bool        ParseWatchlist(const std::string& text, std::vector<WatchedSwap>& out);

}  // namespace atomic_swap
}  // namespace sost
