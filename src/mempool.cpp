// =============================================================================
// SOST — Phase 6: Mempool Implementation
// =============================================================================

#include <sost/mempool.h>
#include <sost/params.h>
#include <sost/atomic_swap.h>   // V14.7 — atomic_swap_relay_active_at() gate
#include <sost/node_participation.h>  // V16 — NODE_BIND/HEARTBEAT structural accept
#include <sost/transaction.h>         // TX_TYPE_NODE_BIND / TX_TYPE_NODE_HEARTBEAT
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
    // V16: keep the node-participation relay-dedup indexes consistent on ANY removal
    // (RemoveTransaction, RBF eviction, RemoveForBlock all route through here).
    if (entry.tx.tx_type == TX_TYPE_NODE_BIND) {
        sost::node_participation::NodeBindTx b;
        if (sost::node_participation::extract_bind(entry.tx, b, nullptr)) {
            auto it = node_bind_pending_.find(b.mining_pubkey);
            if (it != node_bind_pending_.end() && it->second.first == entry.txid) node_bind_pending_.erase(it);
        }
    } else if (entry.tx.tx_type == TX_TYPE_NODE_HEARTBEAT) {
        sost::node_participation::NodeHeartbeatTx h;
        if (sost::node_participation::extract_heartbeat(entry.tx, h, nullptr)) {
            auto it = node_hb_pending_.find(std::make_pair(h.node_pubkey, h.epoch_idx));
            if (it != node_hb_pending_.end() && it->second == entry.txid) node_hb_pending_.erase(it);
        }
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

    // V16: node-participation txs (NODE_BIND / NODE_HEARTBEAT) are 0-value / 0-fee
    // protocol txs (no UTXO inputs). They bypass the fee/input/relay-floor path.
    // Only the canonical SHAPE is checked here; full validation (activation guard,
    // Schnorr signature, tip_ref, node-state seq/uniqueness/dedup) is done by the
    // node's sendrawtransaction handler (which has chain + node-state access) and,
    // authoritatively, by ConnectBlock's connect_block_node_txs before acceptance.
    if (tx.tx_type == TX_TYPE_NODE_BIND || tx.tx_type == TX_TYPE_NODE_HEARTBEAT) {
        // Activation guard at RELAY time: a node tx that would be invalid at the
        // next block MUST NOT enter the mempool — otherwise it poisons the miner's
        // block template (every block including it is rejected by ConnectBlock).
        if (!sost::node_participation_active_at(ctx.spend_height))
            return MempoolAcceptResult::Fail(MempoolAcceptCode::POLICY_FAIL,
                "node tx before V16 activation");
        Hash256 nid{}; std::string nerr;
        if (!tx.ComputeTxId(nid, &nerr))
            return MempoolAcceptResult::Fail(MempoolAcceptCode::INTERNAL_ERROR, "node tx txid: " + nerr);
        if (entries_.count(nid))
            return MempoolAcceptResult::Fail(MempoolAcceptCode::ALREADY_IN_POOL, "already in mempool", nid);
        // Rate-limit: cap total pending node txs (cheap DoS bound before any parse).
        if (node_bind_pending_.size() + node_hb_pending_.size() >= NODE_TX_MEMPOOL_MAX)
            return MempoolAcceptResult::Fail(MempoolAcceptCode::POLICY_FAIL, "node-tx mempool full", nid);

        // Helper to finish acceptance once policy passes.
        auto accept = [&]() {
            MempoolEntry e; e.tx = tx; e.txid = nid; e.fee = 0;
            e.size = EstimateTxSerializedSize(tx); if (!e.size) e.size = 1;
            e.time_added = current_time;
            AddToIndexes(e);
            entries_[nid] = std::move(e);
            return MempoolAcceptResult::Ok(nid, 0, 0.0);
        };

        if (tx.tx_type == TX_TYPE_NODE_BIND) {
            sost::node_participation::NodeBindTx b;
            if (!sost::node_participation::extract_bind(tx, b, nullptr))
                return MempoolAcceptResult::Fail(MempoolAcceptCode::CONSENSUS_FAIL, "malformed NODE_BIND", nid);
            // At most 1 pending bind per mining identity; a strictly-higher bind_seq
            // replaces the pending one (RBF-like for rotation), else reject.
            auto it = node_bind_pending_.find(b.mining_pubkey);
            if (it != node_bind_pending_.end()) {
                if (b.bind_seq <= it->second.second)
                    return MempoolAcceptResult::Fail(MempoolAcceptCode::POLICY_FAIL,
                        "a NODE_BIND with >= bind_seq is already pending for this miner", nid);
                RemoveTransaction(it->second.first);   // evict lower-seq pending bind
            }
            auto r = accept();
            node_bind_pending_[b.mining_pubkey] = std::make_pair(nid, b.bind_seq);
            return r;
        } else {
            sost::node_participation::NodeHeartbeatTx h;
            if (!sost::node_participation::extract_heartbeat(tx, h, nullptr))
                return MempoolAcceptResult::Fail(MempoolAcceptCode::CONSENSUS_FAIL, "malformed NODE_HEARTBEAT", nid);
            // At most 1 pending heartbeat per (node_pubkey, epoch).
            auto key = std::make_pair(h.node_pubkey, h.epoch_idx);
            if (node_hb_pending_.count(key))
                return MempoolAcceptResult::Fail(MempoolAcceptCode::POLICY_FAIL,
                    "a NODE_HEARTBEAT for this (node,epoch) is already pending", nid);
            auto r = accept();
            node_hb_pending_[key] = nid;
            return r;
        }
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

    // Dynamic relay fee check (block 10,000+)
    // Uses mempool pressure to raise the floor when under load
    int64_t dynamic_floor = GetDynamicRelayFloor(ctx.spend_height);
    int64_t min_dynamic_fee = (int64_t)tx_size * dynamic_floor;
    if (fee < min_dynamic_fee) {
        return MempoolAcceptResult::Fail(
            MempoolAcceptCode::POLICY_FAIL,
            "fee " + std::to_string(fee) + " below dynamic relay floor " +
            std::to_string(min_dynamic_fee) + " (" + std::to_string(dynamic_floor) +
            " stocks/byte, mempool=" + std::to_string(entries_.size()) + " tx)",
            txid);
    }

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
// RemoveExpiredHtlcLocks (V14.7 companion)
// ---------------------------------------------------------------------------
// Evict any mempool tx carrying an HTLC LOCK that has expired at next_height
// (refund_height <= next_height). Such a lock is un-mineable (consensus R17) and
// would otherwise linger and re-enter every block template. No-op before V14.7.

size_t Mempool::RemoveExpiredHtlcLocks(int64_t next_height) {
    if (next_height <= 0 || !atomic_swap_relay_active_at(next_height)) return 0;

    std::vector<Hash256> to_remove;
    for (const auto& [txid, entry] : entries_) {
        if (tx_has_expired_htlc_lock(entry.tx, next_height))
            to_remove.push_back(txid);
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
    size_t max_block_size,
    int64_t next_height) const
{
    BlockTemplate tmpl;
    const bool htlc_expiry_filter =
        next_height > 0 && atomic_swap_relay_active_at(next_height);

    for (auto it = fee_rate_index_.rbegin(); it != fee_rate_index_.rend(); ++it) {
        if (tmpl.txs.size() >= max_txs) break;

        auto e_it = entries_.find(it->txid);
        if (e_it == entries_.end()) continue;

        const auto& entry = e_it->second;
        if (tmpl.total_size + entry.size > max_block_size) continue;

        // V14.7 companion: never place an EXPIRED HTLC LOCK in the template.
        // Once the chain reaches a lock's refund_height it is un-mineable
        // (consensus R17), and mining it would get the WHOLE block rejected —
        // the template-poisoning that degraded mining in the first swap deploy.
        if (htlc_expiry_filter && tx_has_expired_htlc_lock(entry.tx, next_height))
            continue;

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
    size_t max_block_size,
    int64_t next_height) const
{
    if (entries_.empty()) return {};
    const bool htlc_expiry_filter =
        next_height > 0 && atomic_swap_relay_active_at(next_height);

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

        // V14.7 companion: drop the whole package if ANY tx in it carries an
        // EXPIRED HTLC LOCK (un-mineable under R17) — it would poison the block.
        if (htlc_expiry_filter) {
            bool has_expired = false;
            for (const auto& anc : info.ancestors) {
                auto a_it = entries_.find(anc);
                if (a_it != entries_.end() &&
                    tx_has_expired_htlc_lock(a_it->second.tx, next_height)) {
                    has_expired = true;
                    break;
                }
            }
            if (has_expired) continue;
        }

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

// =============================================================================
// Dynamic Fee Policy (activates at block 10,000)
// =============================================================================

int64_t Mempool::GetDynamicRelayFloor(int64_t chain_height) const {
    if (chain_height < DYNAMIC_FEE_ACTIVATION_HEIGHT) {
        return MIN_RELAY_FEE_PER_BYTE;
    }
    size_t sz = entries_.size();
    int64_t mult = 1;
    if (sz > DYNAMIC_FEE_PRESSURE_EXTREME)     mult = DYNAMIC_FEE_MULT_EXTREME;
    else if (sz > DYNAMIC_FEE_PRESSURE_HIGH)   mult = DYNAMIC_FEE_MULT_HIGH;
    else if (sz > DYNAMIC_FEE_PRESSURE_MED)    mult = DYNAMIC_FEE_MULT_MED;
    else if (sz > DYNAMIC_FEE_PRESSURE_LOW)    mult = DYNAMIC_FEE_MULT_LOW;
    // V14 (block 15000): the NORMAL relay floor base rises 1 -> 10 stocks/byte.
    // Policy only; pre-V14 behaviour is unchanged.
    int64_t base = (chain_height >= V14_HEIGHT) ? DYNAMIC_FEE_BASE_V14 : DYNAMIC_FEE_BASE;
    int64_t floor = base * mult;
    if (floor > DYNAMIC_FEE_CEILING) floor = DYNAMIC_FEE_CEILING;
    return floor;
}

DynamicFeeInfo Mempool::GetFeeInfo(int64_t chain_height) const {
    DynamicFeeInfo info;
    info.mempool_size = entries_.size();
    info.base_fee = (chain_height >= V14_HEIGHT) ? DYNAMIC_FEE_BASE_V14 : DYNAMIC_FEE_BASE;
    info.relay_floor = GetDynamicRelayFloor(chain_height);
    info.multiplier = info.relay_floor / std::max<int64_t>(1, info.base_fee);
    if (info.mempool_size > DYNAMIC_FEE_PRESSURE_EXTREME)      info.pressure_level = "extreme";
    else if (info.mempool_size > DYNAMIC_FEE_PRESSURE_HIGH)    info.pressure_level = "high";
    else if (info.mempool_size > DYNAMIC_FEE_PRESSURE_MED)     info.pressure_level = "medium";
    else if (info.mempool_size > DYNAMIC_FEE_PRESSURE_LOW)     info.pressure_level = "low";
    else                                                        info.pressure_level = "none";
    info.fee_slow     = info.relay_floor;
    info.fee_normal   = info.relay_floor * 2;
    info.fee_fast     = info.relay_floor * 5;
    info.fee_priority = std::min<int64_t>(info.relay_floor * 10, DYNAMIC_FEE_CEILING);
    if (!fee_rate_index_.empty()) {
        auto it = fee_rate_index_.rbegin();
        if (it->size > 0) {
            int64_t top_rate = it->fee / (int64_t)it->size;
            if (top_rate > info.fee_priority) info.fee_priority = top_rate;
        }
    }
    return info;
}

size_t Mempool::CountByAddress(const std::string&) const {
    return 0; // simplified — per-peer rate limit handles spam
}

} // namespace sost
