// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC — BTC-leg watch decision + restart-recovery store (OTC-6)
// =============================================================================
//
// Closes two PARTIAL gaps from the inventory:
//
//   (a) The watcher only reasoned about the SOST chain. DecideBtcWatchAction is
//       the BTC-side auto-pilot: from BTC chain facts (funding confirmations,
//       whether the HTLC output was spent, the BTC tip height) plus the swap
//       record, it decides Wait / WaitConfirmations / Claim / Refund / Done.
//       It is FACT-driven, so a reorg that drops the funding below
//       min-confirmations naturally reverts the decision to WaitConfirmations.
//
//   (b) Restart-recovery persisted only SOST-side fields. BtcSwapStore persists
//       the full BtcSwapRecord list to a 0600 file and reloads it. Before a
//       restart re-broadcasts anything, ReconcileBtcSwapWithChain queries the
//       backend and advances the record's state to on-chain reality (idempotent
//       ApplyBtcSwapEvent) — so a retry after a crash does NOT double-spend.
//
// The decision function is pure. The store does file I/O. Reconciliation reads
// a BitcoinBackend (which is a NullBitcoinBackend, fail-closed, in Option A).
// =============================================================================
#pragma once

#include "sost/btc_swap_state.h"
#include "sost/bitcoin_backend.h"

#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// What the wallet should do for the BTC leg right now.
enum class BtcWatchAction : uint8_t {
    Wait,               // nothing actionable yet
    WaitConfirmations,  // funding seen but not yet min-confirmed (or reorged)
    Claim,              // claimant: preimage known, window open, funded → claim
    Refund,             // funder: timeout reached, still unspent → refund
    Done,               // spent/settled — stop watching
    Failed              // record is in the Failed terminal state
};
const char* BtcWatchActionName(BtcWatchAction a);

// BTC chain facts the caller feeds in (from BitcoinBackend queries).
struct BtcChainFacts {
    int64_t     current_height = -1;           // BTC tip height
    BtcTxState  funding_state = BtcTxState::Unknown;
    int64_t     funding_confirmations = 0;     // confs on the funding(=lock) tx
    bool        htlc_output_spent = false;     // the P2WSH HTLC output is spent
    int64_t     min_confirmations = 1;         // policy: confs to treat funded
};

// Pure decision. Robust to reorg (uses funding_confirmations vs
// min_confirmations, not just the stored state). Never signs or broadcasts.
BtcWatchAction DecideBtcWatchAction(const BtcSwapRecord& r, const BtcChainFacts& f);

// -----------------------------------------------------------------------------
// Restart-recovery store — file-backed BtcSwapRecord list (0600).
// -----------------------------------------------------------------------------
class BtcSwapStore {
public:
    // Load records from `path`. Missing file → empty store, returns true.
    // Malformed lines are skipped. Returns false only on a read error.
    bool Load(const std::string& path);

    // Atomically write records to `path` with 0600 permissions (contains the
    // preimage in cleartext). Writes to a temp file then renames.
    bool Save(const std::string& path) const;

    BtcSwapRecord*       Find(const std::string& swap_id);
    const BtcSwapRecord* Find(const std::string& swap_id) const;

    // Insert or replace by swap_id.
    void Upsert(const BtcSwapRecord& r);

    std::vector<BtcSwapRecord>&       records()       { return records_; }
    const std::vector<BtcSwapRecord>& records() const { return records_; }

private:
    std::vector<BtcSwapRecord> records_;
};

// Reconcile ONE record against the chain via `backend`, mutating its state with
// idempotent ApplyBtcSwapEvent transitions to match on-chain reality. This is
// the check-before-send guard used on restart:
//
//   - if a claim/refund txid we recorded is now confirmed → advance to the
//     Redeemed/Refunded terminal (do NOT re-broadcast);
//   - if the funding tx reached min-confirmations → advance to Locked;
//   - if the funding output was spent by someone else → Done/terminal.
//
// Returns the recommended BtcWatchAction AFTER reconciliation. With a
// NullBitcoinBackend (Option A) it makes no chain queries and returns the
// action implied by the stored record alone (fail-closed: never Claim/Refund
// without positive confirmation facts).
BtcWatchAction ReconcileBtcSwapWithChain(BtcSwapRecord& r, BitcoinBackend& backend,
                                         int64_t min_confirmations = 1);

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
