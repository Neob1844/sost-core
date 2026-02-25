// =============================================================================
// utxo_set.cpp — SOST UTXO Set (Phase 4)
//
// In-memory UTXO database. Tracks unspent outputs, supports block
// connect/disconnect with undo data for reorgs.
// =============================================================================

#include "sost/utxo_set.h"
#include <cstring>

namespace sost {

// =============================================================================
// IUtxoView interface
// =============================================================================

std::optional<UTXOEntry> UtxoSet::GetUTXO(const OutPoint& op) const {
    auto it = utxos_.find(op);
    if (it == utxos_.end()) return std::nullopt;
    return it->second;
}

// =============================================================================
// Low-level operations
// =============================================================================

bool UtxoSet::AddUTXO(const OutPoint& op, const UTXOEntry& entry,
                       std::string* err) {
    // Integrity check: payload_len must match payload.size()
    if (entry.payload_len != (uint8_t)entry.payload.size()) {
        if (err) *err = "AddUTXO: payload_len " + std::to_string(entry.payload_len) +
                        " != payload.size() " + std::to_string(entry.payload.size());
        return false;
    }

    auto [it, inserted] = utxos_.emplace(op, entry);
    if (!inserted) {
        if (err) *err = "AddUTXO: duplicate outpoint " + HexStr(op.txid) +
                        ":" + std::to_string(op.index);
        return false;
    }
    return true;
}

bool UtxoSet::SpendUTXO(const OutPoint& op, UTXOEntry* out_entry,
                          std::string* err) {
    auto it = utxos_.find(op);
    if (it == utxos_.end()) {
        if (err) *err = "SpendUTXO: not found " + HexStr(op.txid) +
                        ":" + std::to_string(op.index);
        return false;
    }
    if (out_entry) *out_entry = it->second;
    utxos_.erase(it);
    return true;
}

bool UtxoSet::HasUTXO(const OutPoint& op) const {
    return utxos_.count(op) > 0;
}

// =============================================================================
// Transaction-level: connect standard tx
// =============================================================================

bool UtxoSet::ConnectTransaction(
    const Transaction& tx,
    const Hash256& txid,
    int64_t height,
    std::vector<UndoEntry>& undo_entries,
    std::string* err)
{
    // === PRECHECK: verify all inputs exist before mutating state ===
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& txin = tx.inputs[i];
        OutPoint op{txin.prev_txid, txin.prev_index};
        if (!HasUTXO(op)) {
            if (err) *err = "ConnectTransaction: input[" + std::to_string(i) +
                            "] not found " + HexStr(op.txid) + ":" +
                            std::to_string(op.index);
            return false;
        }
    }

    // Verify no duplicate outputs (txid collision)
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        OutPoint op{txid, (uint32_t)i};
        if (HasUTXO(op)) {
            if (err) *err = "ConnectTransaction: output[" + std::to_string(i) +
                            "] already exists (txid collision)";
            return false;
        }
    }

    // === MUTATE: safe to proceed, all prechecks passed ===

    // 1. Spend all inputs
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& txin = tx.inputs[i];
        OutPoint op{txin.prev_txid, txin.prev_index};

        UndoEntry undo;
        undo.outpoint = op;
        SpendUTXO(op, &undo.entry);  // guaranteed to succeed after precheck
        undo_entries.push_back(std::move(undo));
    }

    // 2. Add all outputs
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        const auto& txout = tx.outputs[i];
        OutPoint op{txid, (uint32_t)i};

        UTXOEntry entry;
        entry.amount = txout.amount;
        entry.type = txout.type;
        entry.pubkey_hash = txout.pubkey_hash;
        entry.payload_len = (uint8_t)txout.payload.size();
        entry.payload = txout.payload;
        entry.height = height;
        entry.is_coinbase = false;

        AddUTXO(op, entry);  // guaranteed to succeed after precheck
    }

    return true;
}

// =============================================================================
// Transaction-level: connect coinbase
// =============================================================================

bool UtxoSet::ConnectCoinbase(
    const Transaction& tx,
    const Hash256& txid,
    int64_t height,
    std::string* err)
{
    // Coinbase has no real inputs to spend (prev_txid=0, prev_index=0xFFFFFFFF)
    // Only add outputs
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        const auto& txout = tx.outputs[i];
        OutPoint op{txid, (uint32_t)i};

        UTXOEntry entry;
        entry.amount = txout.amount;
        entry.type = txout.type;
        entry.pubkey_hash = txout.pubkey_hash;
        entry.payload_len = (uint8_t)txout.payload.size();
        entry.payload = txout.payload;
        entry.height = height;
        entry.is_coinbase = true;

        if (!AddUTXO(op, entry, err)) {
            if (err) *err = "ConnectCoinbase: output[" + std::to_string(i) +
                            "] " + *err;
            return false;
        }
    }

    return true;
}

// =============================================================================
// Transaction-level: disconnect standard tx (undo)
// =============================================================================

bool UtxoSet::DisconnectTransaction(
    const Transaction& tx,
    const Hash256& txid,
    const std::vector<UndoEntry>& undo_entries,
    std::string* err)
{
    // 1. Remove outputs that were added by this tx
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        OutPoint op{txid, (uint32_t)i};
        if (!SpendUTXO(op, nullptr, err)) {
            if (err) *err = "DisconnectTransaction: remove output[" +
                            std::to_string(i) + "] " + *err;
            return false;
        }
    }

    // 2. Restore spent inputs from undo data
    for (const auto& undo : undo_entries) {
        if (!AddUTXO(undo.outpoint, undo.entry, err)) {
            if (err) *err = "DisconnectTransaction: restore input " + *err;
            return false;
        }
    }

    return true;
}

// =============================================================================
// Transaction-level: disconnect coinbase
// =============================================================================

bool UtxoSet::DisconnectCoinbase(
    const Transaction& tx,
    const Hash256& txid,
    std::string* err)
{
    // Remove outputs added by coinbase
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        OutPoint op{txid, (uint32_t)i};
        if (!SpendUTXO(op, nullptr, err)) {
            if (err) *err = "DisconnectCoinbase: output[" + std::to_string(i) +
                            "] " + *err;
            return false;
        }
    }
    return true;
}

// =============================================================================
// Block-level: connect
// =============================================================================

bool UtxoSet::ConnectBlock(
    const std::vector<Transaction>& txs,
    int64_t height,
    BlockUndo& out_undo,
    std::string* err)
{
    if (txs.empty()) {
        if (err) *err = "ConnectBlock: empty block";
        return false;
    }

    out_undo.height = height;
    out_undo.spent_utxos.clear();

    // txs[0] = coinbase
    {
        Hash256 txid;
        if (!txs[0].ComputeTxId(txid, err)) {
            if (err) *err = "ConnectBlock: coinbase txid: " + *err;
            return false;
        }
        if (!ConnectCoinbase(txs[0], txid, height, err)) {
            return false;
        }
    }

    // txs[1..n] = standard transactions
    for (size_t t = 1; t < txs.size(); ++t) {
        Hash256 txid;
        if (!txs[t].ComputeTxId(txid, err)) {
            if (err) *err = "ConnectBlock: tx[" + std::to_string(t) +
                            "] txid: " + *err;
            return false;
        }
        if (!ConnectTransaction(txs[t], txid, height,
                                 out_undo.spent_utxos, err)) {
            if (err) *err = "ConnectBlock: tx[" + std::to_string(t) +
                            "] " + *err;
            return false;
        }
    }

    return true;
}

// =============================================================================
// Block-level: disconnect (reverse order)
// =============================================================================

bool UtxoSet::DisconnectBlock(
    const std::vector<Transaction>& txs,
    const BlockUndo& undo,
    std::string* err)
{
    if (txs.empty()) {
        if (err) *err = "DisconnectBlock: empty block";
        return false;
    }

    // === INTEGRITY CHECK: undo entry count must match total standard tx inputs ===
    size_t expected_undo = 0;
    for (size_t t = 1; t < txs.size(); ++t) {
        expected_undo += txs[t].inputs.size();
    }
    if (undo.spent_utxos.size() != expected_undo) {
        if (err) *err = "DisconnectBlock: undo size " +
                        std::to_string(undo.spent_utxos.size()) +
                        " != expected " + std::to_string(expected_undo) +
                        " (corrupted undo data)";
        return false;
    }

    // Compute per-tx undo slices, then disconnect in reverse
    struct TxUndoSlice {
        Hash256 txid;
        size_t undo_start;
        size_t undo_count;
    };
    std::vector<TxUndoSlice> slices;
    size_t undo_offset = 0;

    for (size_t t = 1; t < txs.size(); ++t) {
        TxUndoSlice slice;
        if (!txs[t].ComputeTxId(slice.txid, err)) return false;
        slice.undo_start = undo_offset;
        slice.undo_count = txs[t].inputs.size();
        undo_offset += slice.undo_count;
        slices.push_back(slice);
    }

    // Disconnect standard txs in reverse
    for (int s = (int)slices.size() - 1; s >= 0; --s) {
        const auto& sl = slices[s];
        std::vector<UndoEntry> tx_undo(
            undo.spent_utxos.begin() + sl.undo_start,
            undo.spent_utxos.begin() + sl.undo_start + sl.undo_count);

        size_t t = (size_t)(s + 1);
        if (!DisconnectTransaction(txs[t], sl.txid, tx_undo, err)) {
            if (err) *err = "DisconnectBlock: tx[" + std::to_string(t) +
                            "] " + *err;
            return false;
        }
    }

    // Disconnect coinbase last
    {
        Hash256 txid;
        if (!txs[0].ComputeTxId(txid, err)) return false;
        if (!DisconnectCoinbase(txs[0], txid, err)) return false;
    }

    return true;
}

// =============================================================================
// Statistics
// =============================================================================

int64_t UtxoSet::GetTotalValue() const {
    int64_t total = 0;
    for (const auto& [op, entry] : utxos_) {
        total += entry.amount;
    }
    return total;
}

} // namespace sost
