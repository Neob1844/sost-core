// ============================================================================
// V16 — HISTORICAL JACKPOT V2: PURE consensus core (implementation).
// See include/sost/jackpot_v2.h for the contract and invariants.
// Every function here is pure and deterministic: identical inputs -> identical
// output on every node, independent of container/iteration/RPC/db order.
// ============================================================================
#include "sost/jackpot_v2.h"

#include <cstddef>

namespace sost::jackpot_v2 {

// Canonical order for bind records: (inclusion_height, bind_seq, mining_pkh,
// node_pubkey). Total order -> processing is independent of input vector order.
static bool bind_less(const NodeBindRecord& a, const NodeBindRecord& b) {
    if (a.inclusion_height != b.inclusion_height) return a.inclusion_height < b.inclusion_height;
    if (a.bind_seq         != b.bind_seq)         return a.bind_seq         < b.bind_seq;
    if (a.mining_pkh       != b.mining_pkh)       return a.mining_pkh       < b.mining_pkh;
    return a.node_pubkey < b.node_pubkey;
}

DerivedBindState jv2_derive_bind_state(std::vector<NodeBindRecord> records, int64_t H) {
    std::sort(records.begin(), records.end(), bind_less);

    DerivedBindState st;
    for (const auto& r : records) {
        const int64_t effective = r.inclusion_height + 1;   // FROZEN: effective at inclusion_height+1
        if (effective > H) continue;                        // not yet in force at H

        // Global node_pubkey uniqueness: first miner to claim owns it forever.
        auto oit = st.owner.find(r.node_pubkey);
        if (oit != st.owner.end() && oit->second != r.mining_pkh) continue;  // claimed by a DIFFERENT miner -> reject

        // Per-miner strictly-increasing bind_seq (replay / stale -> reject).
        auto mit = st.max_seq.find(r.mining_pkh);
        if (mit != st.max_seq.end() && r.bind_seq <= mit->second) continue;

        // Accept.
        st.max_seq[r.mining_pkh] = r.bind_seq;
        if (oit == st.owner.end()) st.owner.emplace(r.node_pubkey, r.mining_pkh);
        ActiveBinding ab;
        ab.node_pubkey      = r.node_pubkey;
        ab.bind_seq         = r.bind_seq;
        ab.effective_height = effective;
        st.active[r.mining_pkh] = ab;
    }
    return st;
}

std::map<PubKeyHash, ActiveBinding>
jv2_active_bindings_at(std::vector<NodeBindRecord> records, int64_t H) {
    return jv2_derive_bind_state(std::move(records), H).active;
}

bool jv2_is_node_bound_at(const std::vector<NodeBindRecord>& records,
                          const PubKeyHash& mining_pkh, int64_t H) {
    auto active = jv2_active_bindings_at(records, H);
    return active.find(mining_pkh) != active.end();
}

int64_t jv2_heartbeats_in_window(const std::vector<HeartbeatRecord>& hbs,
                                 const PubKeyHash& mining_pkh,
                                 int64_t A, int64_t L, int64_t H) {
    const int64_t completed = jv2_completed_epochs_before(A, L, H);
    const int64_t window     = jv2_heartbeat_window(completed);
    if (window <= 0) return 0;
    const int64_t lo = completed - window;   // inclusive first epoch index
    const int64_t hi = completed - 1;        // inclusive last  epoch index

    std::set<int64_t> satisfied;             // distinct epochs with >=1 heartbeat
    for (const auto& hb : hbs) {
        if (hb.mining_pkh != mining_pkh) continue;
        if (hb.epoch_idx < lo || hb.epoch_idx > hi) continue;
        satisfied.insert(hb.epoch_idx);
    }
    return (int64_t)satisfied.size();
}

uint32_t jv2_eligibility_reason(const JackpotV2Candidate& c, int64_t A, int64_t L, int64_t H) {
    uint32_t reason = JV2_OK;
    if (H < A)                             reason |= JV2_NOT_V2_HEIGHT;
    if (!c.sbpow_valid)                    reason |= JV2_NO_SBPOW;
    if (c.pow_blocks < JACKPOT_V2_MIN_BLOCKS) reason |= JV2_POW_TOO_LOW;
    if (!c.node_bound)                     reason |= JV2_NOT_NODE_BOUND;

    const int64_t completed = jv2_completed_epochs_before(A, L, H);
    const int64_t required  = jv2_heartbeat_required(completed);
    if (c.heartbeats_in_window < required) reason |= JV2_HEARTBEAT_SHORT;

    return reason;
}

std::vector<JackpotV2Weighted>
jv2_build_weighted_set(const std::vector<JackpotV2Candidate>& candidates,
                       int64_t A, int64_t L, int64_t H) {
    std::vector<JackpotV2Weighted> out;
    out.reserve(candidates.size());
    for (const auto& c : candidates) {
        if (jv2_eligibility_reason(c, A, L, H) != JV2_OK) continue;
        JackpotV2Weighted w;
        w.pkh    = c.mining_pkh;
        w.weight = c.pow_blocks;   // LINEAR weight
        out.push_back(w);
    }
    // CANONICAL order: raw mining_pkh bytes ascending (std::array lexicographic).
    std::sort(out.begin(), out.end(),
              [](const JackpotV2Weighted& a, const JackpotV2Weighted& b) { return a.pkh < b.pkh; });
    return out;
}

Bytes32 jv2_seed(const std::vector<Bytes32>& entropy_hashes, int64_t height) {
    std::vector<uint8_t> buf;
    const size_t domain_len = sizeof(JACKPOT_V2_DOMAIN) - 1;
    buf.reserve(domain_len + entropy_hashes.size() * 32 + 8);
    buf.insert(buf.end(),
               reinterpret_cast<const uint8_t*>(JACKPOT_V2_DOMAIN),
               reinterpret_cast<const uint8_t*>(JACKPOT_V2_DOMAIN) + domain_len);
    for (const auto& h : entropy_hashes) append(buf, h);
    append_u64_le(buf, (uint64_t)height);
    return sha256(buf);
}

int64_t jv2_select_winner_index(const std::vector<JackpotV2Weighted>& sorted,
                                const Bytes32& seed) {
    if (sorted.empty()) return -1;
    int64_t total = jv2_total_weight(sorted);
    if (total <= 0) return -1;

    const uint64_t roll = read_u64_le(seed.data()) % (uint64_t)total;
    uint64_t cumulative = 0;
    for (size_t i = 0; i < sorted.size(); ++i) {
        if (sorted[i].weight <= 0) continue;         // zero-weight never wins
        cumulative += (uint64_t)sorted[i].weight;
        if (roll < cumulative) return (int64_t)i;
    }
    return (int64_t)(sorted.size() - 1);             // defensive; unreachable when total>0
}

} // namespace sost::jackpot_v2
