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

bool NodeState::is_node_bound(const PubKeyHash& mining_pkh, int64_t H) const {
    return jv2_is_node_bound_at(binds_, mining_pkh, H);
}
int64_t NodeState::heartbeats_in_window(const PubKeyHash& mining_pkh, int64_t A, int64_t L, int64_t H) const {
    return jv2_heartbeats_in_window(hbs_, mining_pkh, A, L, H);
}
std::map<PubKeyHash, ActiveBinding> NodeState::active_bindings(int64_t H) const {
    return jv2_active_bindings_at(binds_, H);
}

} // namespace sost::node_participation
