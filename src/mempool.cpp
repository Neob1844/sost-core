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

    // Double-spend vs mempool — with RBF replacement logic
    std::set<Hash256> conflicting_txids;
    for (const auto& txin : tx.inputs) {
        OutPoint op{txin.prev_txid, txin.prev_index};
        auto it = spent_index_.find(op);
        if (it != spent_index_.end()) {
            conflicting_txids.insert(it->second);
        }
    }

    if (!conflicting_txids.empty() && !rbf_enabled_) {
        auto first_conflict = *conflicting_txids.begin();
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::DOUBLE_SPEND,
            "input already spent by mempool tx " + HexStr(first_conflict) +
            " (RBF disabled)",
            txid);
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

    // RBF replacement check (after fee is known)
    bool is_rbf_replacement = false;
    if (!conflicting_txids.empty()) {
        // Too many conflicts
        if (conflicting_txids.size() > RBF_MAX_REPLACEMENTS) {
            return MempoolAcceptResult::Fail(
                MempoolAcceptCode::RBF_REJECTED,
                "replacement conflicts with " + std::to_string(conflicting_txids.size()) +
                " transactions (max " + std::to_string(RBF_MAX_REPLACEMENTS) + ")",
                txid);
        }

        // Sum up replaced fees and sizes
        int64_t replaced_total_fee = 0;
        size_t  replaced_total_size = 0;
        for (const auto& c_txid : conflicting_txids) {
            auto c_it = entries_.find(c_txid);
            if (c_it == entries_.end()) continue;
            replaced_total_fee += c_it->second.fee;
            replaced_total_size += c_it->second.size;
        }

        // New TX must pay strictly higher fee-rate than ALL replaced TXs combined
        // Using integer arithmetic: new_fee/new_size > old_fee/old_size
        // => new_fee * old_size > old_fee * new_size
        __int128 new_cross = (__int128)fee * (__int128)(replaced_total_size > 0 ? replaced_total_size : 1);
        __int128 old_cross = (__int128)replaced_total_fee * (__int128)tx_size;
        if (new_cross <= old_cross) {
            return MempoolAcceptResult::Fail(
                MempoolAcceptCode::RBF_REJECTED,
                "replacement fee-rate not strictly higher than replaced transactions",
                txid);
        }

        // New TX must pay at least old_total_fee + relay_fee_increment
        int64_t min_required_fee = replaced_total_fee +
            (int64_t)tx_size * RBF_MIN_FEE_BUMP_PER_BYTE;
        if (fee < min_required_fee) {
            return MempoolAcceptResult::Fail(
                MempoolAcceptCode::RBF_REJECTED,
                "replacement fee " + std::to_string(fee) +
                " < required " + std::to_string(min_required_fee) +
                " (old_fee + relay_bump)",
                txid);
        }

        // Remove all conflicting transactions
        for (const auto& c_txid : conflicting_txids) {
            RemoveTransaction(c_txid);
        }
        is_rbf_replacement = true;
    }

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

    if (is_rbf_replacement) {
        auto result = MempoolAcceptResult::Ok(txid, fee, fee_rate);
        result.code = MempoolAcceptCode::RBF_REPLACED;
        result.reason = "accepted (replaced " +
            std::to_string(conflicting_txids.size()) + " transaction(s) via RBF)";
        return result;
    }

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
// BuildBlockTemplateCPFP — package-aware fee-rate selection
// ---------------------------------------------------------------------------

Mempool::BlockTemplate Mempool::BuildBlockTemplateCPFP(
    size_t max_txs,
    size_t max_block_size) const
{
    if (entries_.empty()) return {};

    // Step 1: Build child→parent map (TX B spends unconfirmed TX A's output)
    //         parent_of[txid_B] = {txid_A, ...}
    std::map<Hash256, std::set<Hash256>> parent_of;
    // Map: outpoint(txid:vout) → txid that CREATES that output (i.e. the parent)
    std::map<OutPoint, Hash256> output_creators;
    for (const auto& [txid, entry] : entries_) {
        for (uint32_t i = 0; i < entry.tx.outputs.size(); ++i) {
            output_creators[{txid, i}] = txid;
        }
    }
    for (const auto& [txid, entry] : entries_) {
        for (const auto& op : entry.spent_outpoints) {
            auto it = output_creators.find(op);
            if (it != output_creators.end() && it->second != txid) {
                parent_of[txid].insert(it->second);
            }
        }
    }

    // Step 2: Compute "package fee-rate" for each TX
    //         package = TX + all unconfirmed ancestors in mempool
    struct PkgInfo {
        Hash256 txid;
        int64_t pkg_fee{0};
        size_t  pkg_size{0};
        std::set<Hash256> ancestors;  // includes self
    };

    // Recursive ancestor collection
    std::map<Hash256, PkgInfo> pkg_map;
    std::function<void(const Hash256&, PkgInfo&)> collect_ancestors;
    collect_ancestors = [&](const Hash256& txid, PkgInfo& info) {
        if (info.ancestors.count(txid)) return;  // already visited
        auto e_it = entries_.find(txid);
        if (e_it == entries_.end()) return;
        info.ancestors.insert(txid);
        info.pkg_fee += e_it->second.fee;
        info.pkg_size += e_it->second.size;
        auto p_it = parent_of.find(txid);
        if (p_it != parent_of.end()) {
            for (const auto& parent : p_it->second) {
                collect_ancestors(parent, info);
            }
        }
    };

    for (const auto& [txid, entry] : entries_) {
        PkgInfo info;
        info.txid = txid;
        collect_ancestors(txid, info);
        pkg_map[txid] = std::move(info);
    }

    // Step 3: Sort by package fee-rate (descending)
    struct SortEntry {
        Hash256 txid;
        int64_t pkg_fee;
        size_t  pkg_size;
    };
    std::vector<SortEntry> sorted;
    sorted.reserve(entries_.size());
    for (const auto& [txid, info] : pkg_map) {
        sorted.push_back({txid, info.pkg_fee, info.pkg_size});
    }
    std::sort(sorted.begin(), sorted.end(), [](const SortEntry& a, const SortEntry& b) {
        // Descending by package fee-rate: a.fee/a.size > b.fee/b.size
        __int128 lhs = (__int128)a.pkg_fee * (__int128)(b.pkg_size > 0 ? b.pkg_size : 1);
        __int128 rhs = (__int128)b.pkg_fee * (__int128)(a.pkg_size > 0 ? a.pkg_size : 1);
        if (lhs != rhs) return lhs > rhs;
        return a.txid < b.txid;
    });

    // Step 4: Select transactions, ensuring ancestors are included before children
    BlockTemplate tmpl;
    std::set<Hash256> included;

    for (const auto& se : sorted) {
        if (tmpl.txs.size() >= max_txs) break;

        auto& info = pkg_map[se.txid];

        // Check if entire package fits
        size_t needed_size = 0;
        size_t needed_count = 0;
        for (const auto& anc : info.ancestors) {
            if (!included.count(anc)) {
                auto it = entries_.find(anc);
                if (it != entries_.end()) {
                    needed_size += it->second.size;
                    needed_count++;
                }
            }
        }

        if (tmpl.txs.size() + needed_count > max_txs) continue;
        if (tmpl.total_size + needed_size > max_block_size) continue;

        // Add ancestors first (topological: parents before children)
        // Simple approach: add all ancestors that aren't yet included
        std::vector<Hash256> to_add;
        for (const auto& anc : info.ancestors) {
            if (!included.count(anc)) to_add.push_back(anc);
        }
        // Sort to_add: parents before children
        std::sort(to_add.begin(), to_add.end(), [&](const Hash256& a, const Hash256& b) {
            // a should come before b if b depends on a
            return pkg_map[b].ancestors.count(a) > 0;
        });

        for (const auto& add_txid : to_add) {
            auto e_it = entries_.find(add_txid);
            if (e_it == entries_.end()) continue;
            tmpl.txs.push_back(e_it->second.tx);
            tmpl.txids.push_back(add_txid);
            tmpl.total_fees += e_it->second.fee;
            tmpl.total_size += e_it->second.size;
            included.insert(add_txid);
        }
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
