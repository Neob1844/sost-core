#pragma once
// ============================================================================
// V16 — Node participation tx layer: TX_TYPE_NODE_BIND / TX_TYPE_NODE_HEARTBEAT.
// Canonical byte-exact serialization, domain-separated signing messages,
// structural validation (activation guard + fields + Schnorr sig, reusing the
// audited SbPoW crypto), and a reorg-safe node-participation state.
//
// The state is a record list: apply on ConnectBlock (append), undo on
// DisconnectBlock (pop). Undo is exact, so any reorg restores state bit-
// identically (no orphan state). All QUERIES delegate to the pure jackpot_v2
// helpers, so the incremental state always equals a fresh from-chain recompute
// (asserted in tests). Nothing here touches the UTXO set / mints SOST.
// ============================================================================
#include <cstdint>
#include <array>
#include <vector>
#include <map>
#include <functional>

#include "sost/jackpot_v2.h"   // NodeBindRecord, HeartbeatRecord, NodePubKey, queries
#include "sost/sbpow.h"        // MinerPubkey, MinerSignature, verify_sbpow_signature, derive_pkh_from_pubkey
#include "sost/types.h"        // Bytes32
#include "sost/tx_signer.h"    // PubKeyHash

namespace sost::node_participation {

using jackpot_v2::NodePubKey;
using sbpow::MinerPubkey;
using sbpow::MinerSignature;

// ---- Canonical wire structs (payload carried by the tx types) --------------
struct NodeBindTx {
    MinerPubkey    mining_pubkey{};  // 33B compressed; mining_pkh = derive_pkh_from_pubkey(...)
    NodePubKey     node_pubkey{};    // 33B compressed
    uint64_t       bind_seq{0};
    MinerSignature mining_sig{};     // 64B Schnorr by the MINING key over bind_message()
};
struct NodeHeartbeatTx {
    NodePubKey     node_pubkey{};    // 33B compressed
    uint64_t       epoch_idx{0};
    Bytes32        tip_ref_hash{};   // 32B
    MinerSignature node_sig{};       // 64B Schnorr by the NODE key over heartbeat_message()
};

constexpr size_t NODE_BIND_WIRE_BYTES      = 33 + 33 + 8 + 64;   // 138
constexpr size_t NODE_HEARTBEAT_WIRE_BYTES = 33 + 8 + 32 + 64;   // 137

// ---- Serialization (canonical, fixed-size, byte-exact) ---------------------
std::vector<uint8_t> serialize_bind(const NodeBindTx&);
std::vector<uint8_t> serialize_heartbeat(const NodeHeartbeatTx&);
bool deserialize_bind(const std::vector<uint8_t>&, NodeBindTx&);
bool deserialize_heartbeat(const std::vector<uint8_t>&, NodeHeartbeatTx&);

// ---- Signing messages (domain-separated; NEVER reuse the DTD/block message) -
Bytes32 bind_message(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey, uint64_t bind_seq);
Bytes32 heartbeat_message(const NodePubKey& node_pubkey, uint64_t epoch_idx, const Bytes32& tip_ref_hash);

// ---- Structural validation (activation guard + fields + signature) ----------
struct BindCheck { bool ok{false}; PubKeyHash mining_pkh{}; const char* reason{"ok"}; };
// Verifies: activation guard (height >= HIST_JACKPOT_V2_HEIGHT); mining_sig over
// bind_message(derive_pkh(mining_pubkey), node_pubkey, bind_seq). State rules
// (seq monotonic, node_pubkey uniqueness) are enforced separately at apply time.
BindCheck check_bind(const NodeBindTx& tx, int64_t height);

struct HeartbeatCheck { bool ok{false}; const char* reason{"ok"}; };
// Verifies: activation guard; epoch_idx == epoch_of(inclusion_height) (=> no
// future/late heartbeat); tip_ref_hash == expected_tip_ref (hash of
// epoch_start(epoch_idx)-1, looked up by the caller); node_sig over
// heartbeat_message(). Binding-active + per-(miner,epoch) dedup at apply time.
HeartbeatCheck check_heartbeat(const NodeHeartbeatTx& tx, int64_t inclusion_height,
                               int64_t A, int64_t L, const Bytes32& expected_tip_ref);

// ---- Reorg-safe node-participation state ------------------------------------
class NodeState {
public:
    // Would this bind ever become the active binding? (mempool/block accept rule)
    //   * node_pubkey not already owned by a DIFFERENT mining_pkh
    //   * bind_seq strictly greater than the miner's current max accepted seq
    bool bind_acceptable(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey,
                         uint64_t bind_seq, int64_t H) const;

    void apply_bind(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey,
                    uint64_t bind_seq, int64_t inclusion_height);
    void undo_bind();  // pop the last-applied bind (reorg)

    // Resolve the owner mining_pkh of node_pubkey via the active binding at
    // inclusion_height; push a heartbeat record for that owner. Returns false
    // (pushes nothing) if node_pubkey is not the active binding for any miner.
    bool apply_heartbeat(const NodePubKey& node_pubkey, int64_t epoch_idx, int64_t inclusion_height);
    void undo_heartbeat();  // pop the last-applied heartbeat (reorg)

    // Canonical dedup helper: is there already a heartbeat for (mining_pkh, epoch)?
    bool has_heartbeat(const PubKeyHash& mining_pkh, int64_t epoch_idx) const;
    // Direct heartbeat record (owner already resolved against the PRE-BLOCK state).
    void record_heartbeat(const PubKeyHash& mining_pkh, int64_t epoch_idx);

    bool    is_node_bound(const PubKeyHash& mining_pkh, int64_t H) const;
    int64_t heartbeats_in_window(const PubKeyHash& mining_pkh, int64_t A, int64_t L, int64_t H) const;
    std::map<PubKeyHash, jackpot_v2::ActiveBinding> active_bindings(int64_t H) const;

    const std::vector<jackpot_v2::NodeBindRecord>&  binds()      const { return binds_; }
    const std::vector<jackpot_v2::HeartbeatRecord>& heartbeats() const { return hbs_; }

private:
    std::vector<jackpot_v2::NodeBindRecord>  binds_;
    std::vector<jackpot_v2::HeartbeatRecord> hbs_;
};

// ---- Block-level node-tx processing (the function ConnectBlock calls) --------
// FROZEN semantics (order-independent within the block):
//   * height < HIST_JACKPOT_V2_HEIGHT: any node tx present -> INVALID BLOCK.
//   * two-phase: heartbeats of block H are validated & credited against the
//     PRE-BLOCK active bindings (bindings from blocks < H); the block's own
//     NODE_BINDs become effective only at H+1. So a heartbeat signed by a
//     same-block NEW node key is INVALID regardless of tx order.
//   * same-block structural caps (else INVALID BLOCK): <=1 NODE_BIND per
//     mining_pkh; a node_pubkey appears in at most one bind; <=1 NODE_HEARTBEAT
//     per (mining_pkh, epoch). Canonical chain cap: <=1 heartbeat per
//     (mining_pkh, epoch) ever.
// A block is accepted (state mutated) only if EVERY node tx is valid.
struct BlockNodeTxs {
    std::vector<NodeBindTx>      binds;
    std::vector<NodeHeartbeatTx> heartbeats;
};
struct ConnectResult {
    bool        ok{false};
    const char* reason{"ok"};
    int         binds_applied{0};
    int         hbs_applied{0};
};

// block_hash_at(h, out) must yield the canonical block hash at height h on the
// connecting chain (used for the heartbeat tip_ref check). A,L = activation, epoch.
ConnectResult connect_block_node_txs(
    NodeState& state, const BlockNodeTxs& txs, int64_t height, int64_t A, int64_t L,
    const std::function<bool(int64_t, Bytes32&)>& block_hash_at);

// Exact reversal for DisconnectBlock (reorg): pops what connect applied.
void disconnect_block_node_txs(NodeState& state, const ConnectResult& applied);

} // namespace sost::node_participation
