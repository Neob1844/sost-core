// ============================================================================
// V16 — Node participation tx layer (implementation).
// See include/sost/node_participation.h. Pure + deterministic; signature verify
// reuses the audited SbPoW Schnorr helpers. No UTXO/mint side effects.
// ============================================================================
#include "sost/node_participation.h"

#include "sost/crypto.h"       // sha256
#include "sost/serialize.h"    // append, append_u64_le, read_u64_le
#include "sost/params.h"       // node_participation_active_at, HIST_JACKPOT_V2_HEIGHT

#include <cstring>
#include <set>
#include <utility>

namespace sost::node_participation {

using namespace sost::jackpot_v2;
using namespace sost::sbpow;

// ---- serialization ---------------------------------------------------------
std::vector<uint8_t> serialize_bind(const NodeBindTx& t) {
    std::vector<uint8_t> b;
    b.reserve(NODE_BIND_WIRE_BYTES);
    append(b, t.mining_pubkey.data(), t.mining_pubkey.size());
    append(b, t.node_pubkey.data(),   t.node_pubkey.size());
    append_u64_le(b, t.bind_seq);
    append(b, t.mining_sig.data(),    t.mining_sig.size());
    return b;
}
std::vector<uint8_t> serialize_heartbeat(const NodeHeartbeatTx& t) {
    std::vector<uint8_t> b;
    b.reserve(NODE_HEARTBEAT_WIRE_BYTES);
    append(b, t.node_pubkey.data(), t.node_pubkey.size());
    append_u64_le(b, t.epoch_idx);
    append(b, t.tip_ref_hash);
    append(b, t.node_sig.data(),    t.node_sig.size());
    return b;
}
bool deserialize_bind(const std::vector<uint8_t>& b, NodeBindTx& out) {
    if (b.size() != NODE_BIND_WIRE_BYTES) return false;
    size_t o = 0;
    std::memcpy(out.mining_pubkey.data(), b.data() + o, 33); o += 33;
    std::memcpy(out.node_pubkey.data(),   b.data() + o, 33); o += 33;
    out.bind_seq = read_u64_le(b.data() + o); o += 8;
    std::memcpy(out.mining_sig.data(),    b.data() + o, 64); o += 64;
    return true;
}
bool deserialize_heartbeat(const std::vector<uint8_t>& b, NodeHeartbeatTx& out) {
    if (b.size() != NODE_HEARTBEAT_WIRE_BYTES) return false;
    size_t o = 0;
    std::memcpy(out.node_pubkey.data(), b.data() + o, 33); o += 33;
    out.epoch_idx = read_u64_le(b.data() + o); o += 8;
    std::memcpy(out.tip_ref_hash.data(), b.data() + o, 32); o += 32;
    std::memcpy(out.node_sig.data(),    b.data() + o, 64); o += 64;
    return true;
}

// ---- signing messages ------------------------------------------------------
Bytes32 bind_message(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey, uint64_t bind_seq) {
    std::vector<uint8_t> m;
    const size_t dl = sizeof(NODE_BIND_DOMAIN) - 1;
    m.insert(m.end(), reinterpret_cast<const uint8_t*>(NODE_BIND_DOMAIN),
                      reinterpret_cast<const uint8_t*>(NODE_BIND_DOMAIN) + dl);
    append(m, mining_pkh.data(), mining_pkh.size());
    append(m, node_pubkey.data(), node_pubkey.size());
    append_u64_le(m, bind_seq);
    return sha256(m);
}
Bytes32 heartbeat_message(const NodePubKey& node_pubkey, uint64_t epoch_idx, const Bytes32& tip_ref_hash) {
    std::vector<uint8_t> m;
    const size_t dl = sizeof(NODE_HB_DOMAIN) - 1;
    m.insert(m.end(), reinterpret_cast<const uint8_t*>(NODE_HB_DOMAIN),
                      reinterpret_cast<const uint8_t*>(NODE_HB_DOMAIN) + dl);
    append(m, node_pubkey.data(), node_pubkey.size());
    append_u64_le(m, epoch_idx);
    append(m, tip_ref_hash);
    return sha256(m);
}

// ---- structural validation -------------------------------------------------
BindCheck check_bind(const NodeBindTx& tx, int64_t height) {
    BindCheck c;
    if (!node_participation_active_at(height)) { c.reason = "before_activation"; return c; }
    c.mining_pkh = derive_pkh_from_pubkey(tx.mining_pubkey);
    const Bytes32 msg = bind_message(c.mining_pkh, tx.node_pubkey, tx.bind_seq);
    if (!verify_sbpow_signature(tx.mining_pubkey, msg, tx.mining_sig)) { c.reason = "bad_signature"; return c; }
    c.ok = true; return c;
}

HeartbeatCheck check_heartbeat(const NodeHeartbeatTx& tx, int64_t inclusion_height,
                               int64_t A, int64_t L, const Bytes32& expected_tip_ref) {
    HeartbeatCheck c;
    if (!node_participation_active_at(inclusion_height)) { c.reason = "before_activation"; return c; }
    const int64_t e = jv2_epoch_of_height(A, L, inclusion_height);
    if (e < 0)                                { c.reason = "before_activation"; return c; }
    if ((int64_t)tx.epoch_idx != e)           { c.reason = "wrong_epoch"; return c; }   // no future / no late
    if (!(tx.tip_ref_hash == expected_tip_ref)) { c.reason = "bad_tip_ref"; return c; }
    const Bytes32 msg = heartbeat_message(tx.node_pubkey, tx.epoch_idx, tx.tip_ref_hash);
    if (!verify_sbpow_signature(tx.node_pubkey, msg, tx.node_sig)) { c.reason = "bad_signature"; return c; }
    c.ok = true; return c;
}

// ---- reorg-safe state ------------------------------------------------------
bool NodeState::bind_acceptable(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey,
                                uint64_t bind_seq, int64_t H) const {
    DerivedBindState st = jv2_derive_bind_state(binds_, H);
    auto oit = st.owner.find(node_pubkey);
    if (oit != st.owner.end() && oit->second != mining_pkh) return false;   // owned by another miner
    auto mit = st.max_seq.find(mining_pkh);
    if (mit != st.max_seq.end() && (int64_t)bind_seq <= mit->second) return false; // not strictly greater
    return true;
}

void NodeState::apply_bind(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey,
                           uint64_t bind_seq, int64_t inclusion_height) {
    NodeBindRecord r;
    r.mining_pkh       = mining_pkh;
    r.node_pubkey      = node_pubkey;
    r.bind_seq         = (int64_t)bind_seq;
    r.inclusion_height = inclusion_height;
    binds_.push_back(r);
}
void NodeState::undo_bind() { if (!binds_.empty()) binds_.pop_back(); }

bool NodeState::apply_heartbeat(const NodePubKey& node_pubkey, int64_t epoch_idx, int64_t inclusion_height) {
    // Resolve owner via the active binding at inclusion height.
    auto active = jv2_active_bindings_at(binds_, inclusion_height);
    for (const auto& kv : active) {
        if (kv.second.node_pubkey == node_pubkey) {
            HeartbeatRecord h; h.mining_pkh = kv.first; h.epoch_idx = epoch_idx;
            hbs_.push_back(h);
            return true;
        }
    }
    return false;  // node key not the active binding for any miner -> nothing recorded
}
void NodeState::undo_heartbeat() { if (!hbs_.empty()) hbs_.pop_back(); }

bool NodeState::has_heartbeat(const PubKeyHash& mining_pkh, int64_t epoch_idx) const {
    for (const auto& h : hbs_)
        if (h.mining_pkh == mining_pkh && h.epoch_idx == epoch_idx) return true;
    return false;
}
void NodeState::record_heartbeat(const PubKeyHash& mining_pkh, int64_t epoch_idx) {
    HeartbeatRecord h; h.mining_pkh = mining_pkh; h.epoch_idx = epoch_idx;
    hbs_.push_back(h);
}

bool NodeState::is_node_bound(const PubKeyHash& mining_pkh, int64_t H) const {
    return jv2_is_node_bound_at(binds_, mining_pkh, H);
}
int64_t NodeState::heartbeats_in_window(const PubKeyHash& mining_pkh, int64_t A, int64_t L, int64_t H) const {
    return jv2_heartbeats_in_window(hbs_, mining_pkh, A, L, H);
}
std::map<PubKeyHash, ActiveBinding> NodeState::active_bindings(int64_t H) const {
    return jv2_active_bindings_at(binds_, H);
}

// ---- block-level processing (what ConnectBlock calls) ----------------------
ConnectResult connect_block_node_txs(
    NodeState& state, const BlockNodeTxs& txs, int64_t height, int64_t A, int64_t L,
    const std::function<bool(int64_t, Bytes32&)>& block_hash_at) {

    ConnectResult r;

    // Activation guard: below activation NO node tx may appear.
    if (!node_participation_active_at(height)) {
        if (!txs.binds.empty() || !txs.heartbeats.empty()) { r.reason = "node_tx_before_activation"; return r; }
        r.ok = true; return r;
    }

    // ---- validate BINDS (structural + same-block caps + pre-block accept) ----
    std::set<PubKeyHash> block_bind_miners;
    std::set<NodePubKey> block_bind_nodes;
    std::vector<NodeBindRecord> to_bind;
    for (const auto& b : txs.binds) {
        BindCheck bc = check_bind(b, height);
        if (!bc.ok) { r.reason = bc.reason; return r; }
        if (!block_bind_miners.insert(bc.mining_pkh).second) { r.reason = "double_bind_same_block"; return r; }
        if (!block_bind_nodes.insert(b.node_pubkey).second)  { r.reason = "node_pubkey_twice_same_block"; return r; }
        // pre-block state acceptance (seq strictly increasing + global uniqueness)
        if (!state.bind_acceptable(bc.mining_pkh, b.node_pubkey, b.bind_seq, height)) { r.reason = "bind_not_acceptable"; return r; }
        NodeBindRecord rec; rec.mining_pkh = bc.mining_pkh; rec.node_pubkey = b.node_pubkey;
        rec.bind_seq = (int64_t)b.bind_seq; rec.inclusion_height = height;
        to_bind.push_back(rec);
    }

    // ---- validate HEARTBEATS vs PRE-BLOCK active bindings --------------------
    const int64_t e = jackpot_v2::jv2_epoch_of_height(A, L, height);
    Bytes32 expected_tip{};
    if (e >= 0) {
        const int64_t ref_h = jackpot_v2::jv2_epoch_start(A, L, e) - 1;
        if (!block_hash_at(ref_h, expected_tip)) { r.reason = "no_tip_ref"; return r; }
    }
    // PRE-BLOCK bindings: this block's binds are NOT yet applied, so this is the
    // state at the START of block H. Order-independent by construction.
    auto preblock_active = state.active_bindings(height);
    std::set<std::pair<std::array<uint8_t,20>, int64_t>> block_hb;
    std::vector<std::pair<PubKeyHash,int64_t>> to_hb;
    for (const auto& h : txs.heartbeats) {
        HeartbeatCheck hc = check_heartbeat(h, height, A, L, expected_tip);
        if (!hc.ok) { r.reason = hc.reason; return r; }
        // resolve owner via PRE-BLOCK active bindings (same-block new key -> invalid)
        const PubKeyHash* owner = nullptr;
        for (const auto& kv : preblock_active)
            if (kv.second.node_pubkey == h.node_pubkey) { owner = &kv.first; break; }
        if (!owner) { r.reason = "heartbeat_node_not_active_preblock"; return r; }
        auto key = std::make_pair(*owner, (int64_t)h.epoch_idx);
        if (!block_hb.insert(key).second)           { r.reason = "dup_heartbeat_same_block"; return r; }
        if (state.has_heartbeat(*owner, (int64_t)h.epoch_idx)) { r.reason = "heartbeat_already_on_chain"; return r; }
        to_hb.emplace_back(*owner, (int64_t)h.epoch_idx);
    }

    // ---- all valid -> APPLY: heartbeats first, then binds (H+1 effective) ----
    for (const auto& hb : to_hb) state.record_heartbeat(hb.first, hb.second);
    for (const auto& rec : to_bind)
        state.apply_bind(rec.mining_pkh, rec.node_pubkey, (uint64_t)rec.bind_seq, rec.inclusion_height);

    r.ok = true; r.binds_applied = (int)to_bind.size(); r.hbs_applied = (int)to_hb.size();
    return r;
}

void disconnect_block_node_txs(NodeState& state, const ConnectResult& applied) {
    if (!applied.ok) return;
    for (int i = 0; i < applied.binds_applied; ++i) state.undo_bind();       // binds applied last -> undo first
    for (int i = 0; i < applied.hbs_applied;   ++i) state.undo_heartbeat();
}

} // namespace sost::node_participation
