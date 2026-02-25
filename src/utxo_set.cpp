// =============================================================================
// utxo_set.cpp — SOST UTXO Set (Phase 4)
//
// In-memory UTXO database. Tracks unspent outputs, supports block
// connect/disconnect with undo data for reorgs.
//
// HARDENING/SAFETY FIXES:
//   - AddUTXO rejects payload.size() > 255 and enforces payload_len match.
//   - ConnectTransaction is atomic (rollback on any failure).
//   - ConnectCoinbase is atomic (rollback on any failure).
//   - ConnectBlock is atomic (rollback whole prefix block on any failure).
//   - Basic type checks in ConnectBlock (txs[0] must be coinbase; others standard).
// =============================================================================

#include "sost/utxo_set.h"

#include <cstring>
#include <set>

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

bool UtxoSet::AddUTXO(const OutPoint& op, const UTXOEntry& entry, std::string* err) {
    // Hard bound: payload is consensus-serialized as uint8 length
    if (entry.payload.size() > 255) {
        if (err) *err = "AddUTXO: payload.size() " + std::to_string(entry.payload.size()) + " > 255";
        return false;
    }

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

bool UtxoSet::SpendUTXO(const OutPoint& op, UTXOEntry* out_entry, std::string* err) {
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
// Transaction-level: connect standard tx (ATOMIC)
// =============================================================================

bool UtxoSet::ConnectTransaction(
    const Transaction& tx,
    const Hash256& txid,
    int64_t height,
    std::vector<UndoEntry>& undo_entries,
    std::string* err)
{
    // PRECHECK: verify all inputs exist
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

    // PRECHECK: verify no outputs collide
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        OutPoint op{txid, (uint32_t)i};
        if (HasUTXO(op)) {
            if (err) *err = "ConnectTransaction: output[" + std::to_string(i) +
                            "] already exists (txid collision)";
            return false;
        }
        if (tx.outputs[i].payload.size() > 255) {
            if (err) *err = "ConnectTransaction: output[" + std::to_string(i) +
                            "] payload.size() > 255 (invalid)";
            return false;
        }
    }

    // MUTATE (atomic with rollback)
    std::vector<UndoEntry> local_undo;
    local_undo.reserve(tx.inputs.size());

    // 1) Spend inputs (record undo)
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        const auto& txin = tx.inputs[i];
        OutPoint op{txin.prev_txid, txin.prev_index};

        UndoEntry undo;
        undo.outpoint = op;
        if (!SpendUTXO(op, &undo.entry, err)) {
            // rollback already-spent inputs
            for (const auto& u : local_undo) {
                std::string tmp;
                AddUTXO(u.outpoint, u.entry, &tmp);
            }
            if (err && err->empty()) *err = "ConnectTransaction: SpendUTXO failed";
            return false;
        }
        local_undo.push_back(std::move(undo));
    }

    // 2) Add outputs
    std::vector<OutPoint> added_outputs;
    added_outputs.reserve(tx.outputs.size());

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

        std::string add_err;
        if (!AddUTXO(op, entry, &add_err)) {
            // rollback outputs added so far
            for (const auto& aop : added_outputs) {
                std::string tmp;
                SpendUTXO(aop, nullptr, &tmp);
            }
            // rollback inputs
            for (const auto& u : local_undo) {
                std::string tmp;
                AddUTXO(u.outpoint, u.entry, &tmp);
            }
            if (err) *err = "ConnectTransaction: AddUTXO failed: " + add_err;
            return false;
        }

        added_outputs.push_back(op);
    }

    // Commit undo to caller
    undo_entries.insert(undo_entries.end(), local_undo.begin(), local_undo.end());
    return true;
}

// =============================================================================
// Transaction-level: connect coinbase (ATOMIC)
// =============================================================================

bool UtxoSet::ConnectCoinbase(
    const Transaction& tx,
    const Hash256& txid,
    int64_t height,
    std::string* err)
{
    // Only add outputs, but do it atomically
    std::vector<OutPoint> added;
    added.reserve(tx.outputs.size());

    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        const auto& txout = tx.outputs[i];
        OutPoint op{txid, (uint32_t)i};

        if (txout.payload.size() > 255) {
            if (err) *err = "ConnectCoinbase: output[" + std::to_string(i) + "] payload.size() > 255";
            // rollback none needed (nothing added yet here)
            return false;
        }

        UTXOEntry entry;
        entry.amount = txout.amount;
        entry.type = txout.type;
        entry.pubkey_hash = txout.pubkey_hash;
        entry.payload_len = (uint8_t)txout.payload.size();
        entry.payload = txout.payload;
        entry.height = height;
        entry.is_coinbase = true;

        std::string add_err;
        if (!AddUTXO(op, entry, &add_err)) {
            // rollback outputs added so far
            for (const auto& aop : added) {
                std::string tmp;
                SpendUTXO(aop, nullptr, &tmp);
            }
            if (err) *err = "ConnectCoinbase: AddUTXO failed: " + add_err;
            return false;
        }

        added.push_back(op);
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
// Block-level: connect (ATOMIC)
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

    // Type sanity: txs[0] must be coinbase, rest must be standard
    if (txs[0].tx_type != TX_TYPE_COINBASE) {
        if (err) *err = "ConnectBlock: txs[0] must be coinbase";
        return false;
    }
    for (size_t t = 1; t < txs.size(); ++t) {
        if (txs[t].tx_type != TX_TYPE_STANDARD) {
            if (err) *err = "ConnectBlock: txs[" + std::to_string(t) + "] must be standard";
            return false;
        }
    }

    // Work on a temporary undo; commit only on success
    BlockUndo tmp_undo;
    tmp_undo.height = height;
    tmp_undo.spent_utxos.clear();

    // Connect coinbase
    Hash256 cb_txid;
    if (!txs[0].ComputeTxId(cb_txid, err)) {
        if (err) *err = "ConnectBlock: coinbase txid: " + *err;
        return false;
    }
    if (!ConnectCoinbase(txs[0], cb_txid, height, err)) {
        if (err && err->empty()) *err = "ConnectBlock: ConnectCoinbase failed";
        return false;
    }

    // Connect standard txs in order
    for (size_t t = 1; t < txs.size(); ++t) {
        Hash256 txid;
        if (!txs[t].ComputeTxId(txid, err)) {
            if (err) *err = "ConnectBlock: tx[" + std::to_string(t) + "] txid: " + *err;

            // rollback entire prefix (coinbase only)
            std::vector<Transaction> prefix = {txs[0]};
            std::string rb;
            DisconnectBlock(prefix, tmp_undo, &rb);
            return false;
        }

        std::string tx_err;
        if (!ConnectTransaction(txs[t], txid, height, tmp_undo.spent_utxos, &tx_err)) {
            if (err) *err = "ConnectBlock: tx[" + std::to_string(t) + "] " + tx_err;

            // rollback connected prefix (coinbase + txs[1..t-1])
            std::vector<Transaction> prefix(txs.begin(), txs.begin() + (long)t);
            std::string rb;
            if (!DisconnectBlock(prefix, tmp_undo, &rb)) {
                // if rollback fails, surface both errors
                if (err) *err += " | ROLLBACK FAILED: " + rb;
            }
            return false;
        }
    }

    // Commit undo
    out_undo = std::move(tmp_undo);
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

    // Undo entry count must match total standard tx inputs
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

    // Build per-tx undo slices
    struct TxUndoSlice {
        Hash256 txid;
        size_t undo_start;
        size_t undo_count;
    };

    std::vector<TxUndoSlice> slices;
    slices.reserve(txs.size() > 1 ? (txs.size() - 1) : 0);

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
            if (err) *err = "DisconnectBlock: tx[" + std::to_string(t) + "] " + *err;
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
    for (const auto& kv : utxos_) {
        total += kv.second.amount;
    }
    return total;
}

} // namespace sost
