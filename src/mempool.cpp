// =============================================================================
// SOST — Phase 6: Mempool Implementation
// =============================================================================

#include <sost/mempool.h>
#include <algorithm>
#include <limits>
#include <ctime>
#include <set>

namespace sost {

Mempool::Mempool(size_t max_entries)
    : max_entries_(max_entries)
{}

// ---------------------------------------------------------------------------
// Index management
// ---------------------------------------------------------------------------

void Mempool::AddToIndexes(const MempoolEntry& entry) {
    fee_rate_index_.insert({entry.fee, entry.size, entry.txid});
    for (const auto& op : entry.spent_outpoints) {
        spent_index_[op] = entry.txid;
    }
}

void Mempool::RemoveFromIndexes(const MempoolEntry& entry) {
    fee_rate_index_.erase({entry.fee, entry.size, entry.txid});
    for (const auto& op : entry.spent_outpoints) {
        spent_index_.erase(op);
    }
}

// ---------------------------------------------------------------------------
// ComputeFee (hardened with int128 accumulation)
// ---------------------------------------------------------------------------

bool Mempool::ComputeFee(
    const Transaction& tx,
    const IUtxoView& utxos,
    int64_t& out_fee,
    std::string* err)
{
    __int128 sum_in = 0;
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        OutPoint op{tx.inputs[i].prev_txid, tx.inputs[i].prev_index};
        auto entry = utxos.GetUTXO(op);
        if (!entry) {
            if (err) *err = "ComputeFee: input[" + std::to_string(i) + "] UTXO not found";
            return false;
        }
        sum_in += (__int128)entry->amount;
    }

    __int128 sum_out = 0;
    for (const auto& txout : tx.outputs) {
        sum_out += (__int128)txout.amount;
    }

    __int128 fee128 = sum_in - sum_out;
    if (fee128 < (__int128)std::numeric_limits<int64_t>::min() ||
        fee128 > (__int128)std::numeric_limits<int64_t>::max()) {
        if (err) *err = "ComputeFee: fee overflow";
        return false;
    }

    out_fee = (int64_t)fee128;
    return true;
}

// ---------------------------------------------------------------------------
// AcceptToMempool
// ---------------------------------------------------------------------------

MempoolAcceptResult Mempool::AcceptToMempool(
    const Transaction& tx,
    const UtxoSet& utxos,
    const TxValidationContext& ctx,
    int64_t current_time)
{
    if (tx.tx_type == TX_TYPE_COINBASE) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::COINBASE_REJECT,
            "coinbase transactions cannot enter the mempool");
    }

    if (current_time == 0) {
        current_time = (int64_t)std::time(nullptr);
    }

    // txid
    Hash256 txid{};
    std::string err;
    if (!tx.ComputeTxId(txid, &err)) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::INTERNAL_ERROR,
            "failed to compute txid: " + err);
    }

    if (entries_.count(txid)) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::ALREADY_IN_POOL,
            "transaction already in mempool", txid);
    }

    // Double-spend vs mempool
    for (const auto& txin : tx.inputs) {
        OutPoint op{txin.prev_txid, txin.prev_index};
        auto it = spent_index_.find(op);
        if (it != spent_index_.end()) {
            return MempoolAcceptResult::Fail(
                MempoolAcceptCode::DOUBLE_SPEND,
                "input " + HexStr(op.txid) + ":" + std::to_string(op.index) +
                " already spent by mempool tx " + HexStr(it->second),
                txid);
        }
    }

    // Consensus validation
    auto cres = ValidateTransactionConsensus(tx, utxos, ctx);
    if (!cres.ok) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::CONSENSUS_FAIL,
            "consensus: " + cres.message, txid);
    }

    // Policy validation
    auto pres = ValidateTransactionPolicy(tx, utxos, ctx);
    if (!pres.ok) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::POLICY_FAIL,
            "policy: " + pres.message, txid);
    }

    // Fee
    int64_t fee = 0;
    if (!ComputeFee(tx, utxos, fee, &err)) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::INTERNAL_ERROR,
            "fee computation failed: " + err, txid);
    }
    if (fee < 0) {
        // no debería pasar si consenso pasó, pero hardening
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::INTERNAL_ERROR,
            "negative fee after consensus (unexpected)", txid);
    }

    // Size
    size_t tx_size = EstimateTxSerializedSize(tx);
    if (tx_size == 0) tx_size = 1;

    // Informativo para UI (no para ordenar)
    double fee_rate = (double)fee / (double)tx_size;

    // Capacity / eviction
    if (entries_.size() >= max_entries_) {
        if (!fee_rate_index_.empty()) {
            auto lowest = fee_rate_index_.begin(); // peor fee/size
            FeeRateKey incoming{fee, tx_size, txid};

            if (!( *lowest < incoming )) {
                // incoming <= lowest
                return MempoolAcceptResult::Fail(
                    MempoolAcceptCode::POOL_FULL,
                    "mempool full and fee-rate too low to evict", txid);
            }

            // Evict worst
            RemoveTransaction(lowest->txid);
        }
    }

    // Build entry
    MempoolEntry entry;
    entry.tx = tx;
    entry.txid = txid;
    entry.fee = fee;
    entry.size = tx_size;
    entry.time_added = current_time;

    for (const auto& txin : tx.inputs) {
        entry.spent_outpoints.push_back({txin.prev_txid, txin.prev_index});
    }

    AddToIndexes(entry);
    entries_[txid] = std::move(entry);

    return MempoolAcceptResult::Ok(txid, fee, fee_rate);
}

// ---------------------------------------------------------------------------
// RemoveTransaction
// ---------------------------------------------------------------------------

bool Mempool::RemoveTransaction(const Hash256& txid) {
    auto it = entries_.find(txid);
    if (it == entries_.end()) return false;

    RemoveFromIndexes(it->second);
    entries_.erase(it);
    return true;
}

// ---------------------------------------------------------------------------
// RemoveForBlock
// ---------------------------------------------------------------------------

size_t Mempool::RemoveForBlock(const std::vector<Transaction>& block_txs) {
    std::set<OutPoint> block_spends;
    for (const auto& tx : block_txs) {
        if (tx.tx_type == TX_TYPE_COINBASE) continue;
        for (const auto& txin : tx.inputs) {
            block_spends.insert({txin.prev_txid, txin.prev_index});
        }
    }

    std::set<Hash256> confirmed_txids;
    for (const auto& tx : block_txs) {
        Hash256 txid{};
        if (tx.ComputeTxId(txid, nullptr)) {
            confirmed_txids.insert(txid);
        }
    }

    std::vector<Hash256> to_remove;
    for (const auto& [txid, entry] : entries_) {
        if (confirmed_txids.count(txid)) {
            to_remove.push_back(txid);
            continue;
        }
        for (const auto& op : entry.spent_outpoints) {
            if (block_spends.count(op)) {
                to_remove.push_back(txid);
                break;
            }
        }
    }

    for (const auto& id : to_remove) {
        RemoveTransaction(id);
    }
    return to_remove.size();
}

// ---------------------------------------------------------------------------
// BuildBlockTemplate
// ---------------------------------------------------------------------------

Mempool::BlockTemplate Mempool::BuildBlockTemplate(
    size_t max_txs,
    size_t max_block_size) const
{
    BlockTemplate tmpl;

    for (auto it = fee_rate_index_.rbegin(); it != fee_rate_index_.rend(); ++it) {
        if (tmpl.txs.size() >= max_txs) break;

        auto e_it = entries_.find(it->txid);
        if (e_it == entries_.end()) continue;

        const auto& entry = e_it->second;
        if (tmpl.total_size + entry.size > max_block_size) continue;

        tmpl.txs.push_back(entry.tx);
        tmpl.txids.push_back(entry.txid);
        tmpl.total_fees += entry.fee;
        tmpl.total_size += entry.size;
    }

    return tmpl;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

bool Mempool::HasTransaction(const Hash256& txid) const {
    return entries_.count(txid) > 0;
}

const MempoolEntry* Mempool::GetEntry(const Hash256& txid) const {
    auto it = entries_.find(txid);
    return (it == entries_.end()) ? nullptr : &it->second;
}

bool Mempool::IsSpent(const OutPoint& op) const {
    return spent_index_.count(op) > 0;
}

int64_t Mempool::TotalFees() const {
    int64_t total = 0;
    for (const auto& [_, e] : entries_) total += e.fee;
    return total;
}

size_t Mempool::TotalSize() const {
    size_t total = 0;
    for (const auto& [_, e] : entries_) total += e.size;
    return total;
}

void Mempool::Clear() {
    entries_.clear();
    fee_rate_index_.clear();
    spent_index_.clear();
}

} // namespace sost
