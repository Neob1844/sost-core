#pragma once

// =============================================================================
// utxo_set.h — SOST UTXO Set (Phase 4)
//
// In-memory UTXO database implementing IUtxoView from Phase 3.
// Tracks unspent transaction outputs, supports block connect/disconnect
// with undo data for reorgs.
//
// Design: SOST Design v1.2a Section 7 (UTXO model)
// =============================================================================

#include "sost/tx_validation.h"
#include "sost/transaction.h"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace sost {

// =============================================================================
// UndoEntry — data needed to restore a spent UTXO on block disconnect
// =============================================================================

struct UndoEntry {
    OutPoint  outpoint;
    UTXOEntry entry;
};

// =============================================================================
// BlockUndo — all undo data for a single block (spent UTXOs)
// =============================================================================

struct BlockUndo {
    int64_t height{0};
    std::vector<UndoEntry> spent_utxos;   // UTXOs consumed by this block
};

// =============================================================================
// UtxoSet — in-memory UTXO database
// =============================================================================

class UtxoSet : public IUtxoView {
public:
    UtxoSet() = default;

    // -------------------------------------------------------------------------
    // IUtxoView interface
    // -------------------------------------------------------------------------

    // Returns nullopt if the UTXO is not found (spent or never existed)
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override;

    // -------------------------------------------------------------------------
    // Low-level UTXO operations
    // -------------------------------------------------------------------------

    // Add a new UTXO. Returns false if it already exists (duplicate).
    bool AddUTXO(const OutPoint& op, const UTXOEntry& entry,
                 std::string* err = nullptr);

    // Remove (spend) a UTXO. Returns false if not found.
    // If out_entry is provided, the spent entry is written to it (for undo).
    bool SpendUTXO(const OutPoint& op, UTXOEntry* out_entry = nullptr,
                   std::string* err = nullptr);

    // Check if a UTXO exists without returning the full entry
    bool HasUTXO(const OutPoint& op) const;

    // -------------------------------------------------------------------------
    // Transaction-level operations
    // -------------------------------------------------------------------------

    // Connect a validated standard transaction:
    //   1. Spend all inputs (remove from UTXO set)
    //   2. Add all outputs (insert into UTXO set)
    // txid must be precomputed by caller.
    // Appends spent UTXOs to undo_entries for later disconnect.
    // Returns false on error (missing input, duplicate output).
    bool ConnectTransaction(
        const Transaction& tx,
        const Hash256& txid,
        int64_t height,
        std::vector<UndoEntry>& undo_entries,
        std::string* err = nullptr);

    // Connect a validated coinbase transaction:
    //   Only adds outputs (coinbase has no real inputs to spend).
    bool ConnectCoinbase(
        const Transaction& tx,
        const Hash256& txid,
        int64_t height,
        std::string* err = nullptr);

    // Disconnect a standard transaction (undo):
    //   1. Remove outputs added by this tx
    //   2. Restore spent inputs from undo_entries
    bool DisconnectTransaction(
        const Transaction& tx,
        const Hash256& txid,
        const std::vector<UndoEntry>& undo_entries,
        std::string* err = nullptr);

    // Disconnect a coinbase transaction:
    //   Remove outputs added by this coinbase
    bool DisconnectCoinbase(
        const Transaction& tx,
        const Hash256& txid,
        std::string* err = nullptr);

    // -------------------------------------------------------------------------
    // Block-level operations
    // -------------------------------------------------------------------------

    // Connect all transactions in a block.
    // txs[0] must be coinbase, txs[1..n] must be standard.
    // Returns BlockUndo with all spent UTXOs for later disconnect.
    bool ConnectBlock(
        const std::vector<Transaction>& txs,
        int64_t height,
        BlockUndo& out_undo,
        std::string* err = nullptr);

    // Disconnect a block (undo all transactions in reverse order).
    bool DisconnectBlock(
        const std::vector<Transaction>& txs,
        const BlockUndo& undo,
        std::string* err = nullptr);

    // -------------------------------------------------------------------------
    // Statistics / queries
    // -------------------------------------------------------------------------

    // Number of unspent outputs in the set
    size_t Size() const { return utxos_.size(); }

    // Sum of all UTXO amounts (stockshis)
    int64_t GetTotalValue() const;

    // Clear all UTXOs (for testing / reset)
    void Clear() { utxos_.clear(); }

    // Direct access to the map (for testing / debugging only)
    const std::map<OutPoint, UTXOEntry>& GetMap() const { return utxos_; }

private:
    std::map<OutPoint, UTXOEntry> utxos_;
};

} // namespace sost
