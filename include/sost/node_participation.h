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
#include <string>

#include "sost/jackpot_v2.h"   // NodeBindRecord, HeartbeatRecord, NodePubKey, queries
#include "sost/sbpow.h"        // MinerPubkey, MinerSignature, verify_sbpow_signature, derive_pkh_from_pubkey
#include "sost/types.h"        // Bytes32
#include "sost/tx_signer.h"    // PubKeyHash
#include "sost/transaction.h"  // Transaction, TxOutput, OUT_NODE_PROTOCOL, TX_TYPE_NODE_*

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
    // NODE_BIND v2 (from NODE_BIND_V2_HEIGHT): 64B Schnorr by the NODE key over
    // bind_node_message() — proof that the binder holds the node private key.
    MinerSignature node_sig{};
    uint8_t        version{2};       // 1 = 138-byte legacy payload, 2 = 202-byte payload (wire-derived)
};
struct NodeHeartbeatTx {
    NodePubKey     node_pubkey{};    // 33B compressed
    uint64_t       epoch_idx{0};
    Bytes32        tip_ref_hash{};   // 32B
    MinerSignature node_sig{};       // 64B Schnorr by the NODE key over heartbeat_message()
};

constexpr size_t NODE_BIND_WIRE_BYTES_V1   = 33 + 33 + 8 + 64;        // 138 (legacy, below NODE_BIND_V2_HEIGHT)
constexpr size_t NODE_BIND_WIRE_BYTES      = 33 + 33 + 8 + 64 + 64;   // 202 (v2: + node_sig)
constexpr size_t NODE_HEARTBEAT_WIRE_BYTES = 33 + 8 + 32 + 64;   // 137

// ---- Serialization (canonical, fixed-size, byte-exact) ---------------------
std::vector<uint8_t> serialize_bind(const NodeBindTx&);
std::vector<uint8_t> serialize_heartbeat(const NodeHeartbeatTx&);
bool deserialize_bind(const std::vector<uint8_t>&, NodeBindTx&);
bool deserialize_heartbeat(const std::vector<uint8_t>&, NodeHeartbeatTx&);

// ---- Signing messages (domain-separated; NEVER reuse the DTD/block message) -
Bytes32 bind_message(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey, uint64_t bind_seq);
// NODE_BIND v2 node-key message: distinct domain, commits to the SAME (pkh, node_pubkey, seq).
Bytes32 bind_node_message(const PubKeyHash& mining_pkh, const NodePubKey& node_pubkey, uint64_t bind_seq);
Bytes32 heartbeat_message(const NodePubKey& node_pubkey, uint64_t epoch_idx, const Bytes32& tip_ref_hash);

// ---- Transaction transport (single 0-value OUT_NODE_PROTOCOL output) --------
// A node tx is: tx_type in {NODE_BIND, NODE_HEARTBEAT}; NO inputs; EXACTLY one
// output of type OUT_NODE_PROTOCOL with amount==0 and payload == the canonical
// bytes. OUT_NODE_PROTOCOL is NEVER spendable (see output_is_spendable).
enum class NodeTxKind { None, Bind, Heartbeat };

// True unless the output type is a non-spendable protocol-data output. The UTXO
// create path uses this to keep OUT_NODE_PROTOCOL out of the spendable set.
inline bool output_is_spendable(uint8_t out_type) { return out_type != OUT_NODE_PROTOCOL; }

Transaction build_node_bind_tx(const NodeBindTx&);
Transaction build_node_heartbeat_tx(const NodeHeartbeatTx&);

// Classify by tx_type only (cheap). Returns None for non-node txs.
NodeTxKind classify_node_tx(const Transaction&);

// Canonical extraction + shape validation (NOT signature). Enforces: correct
// tx_type; zero inputs; exactly one output; output.type==OUT_NODE_PROTOCOL;
// amount==0; payload size EXACT; canonical decode with no trailing bytes.
// Returns false (with reason) on any deviation -> the block/tx is INVALID.
bool extract_bind(const Transaction&, NodeBindTx& out, const char** reason = nullptr);
bool extract_heartbeat(const Transaction&, NodeHeartbeatTx& out, const char** reason = nullptr);

// ---- Structural validation (activation guard + fields + signature) ----------
struct BindCheck { bool ok{false}; PubKeyHash mining_pkh{}; const char* reason{"ok"}; };
// Verifies: activation guard (height >= HIST_JACKPOT_V2_HEIGHT); mining_sig over
// bind_message(derive_pkh(mining_pubkey), node_pubkey, bind_seq); and from NODE_BIND_V2_HEIGHT
// the payload must be v2 with node_sig over bind_node_message(...) by node_pubkey (below the
// gate the payload must be v1). State rules
// (seq monotonic, node_pubkey uniqueness) are enforced separately at apply time.
BindCheck check_bind(const NodeBindTx& tx, int64_t height);

struct HeartbeatCheck { bool ok{false}; const char* reason{"ok"}; };
// Verifies: activation guard; epoch_idx == epoch_of(inclusion_height) (=> no
// future/late heartbeat); tip_ref_hash == expected_tip_ref (hash of
// epoch_start(epoch_idx)-1, looked up by the caller); node_sig over
// heartbeat_message(). Binding-active + per-(miner,epoch) dedup at apply time.
HeartbeatCheck check_heartbeat(const NodeHeartbeatTx& tx, int64_t inclusion_height,
                               int64_t A, int64_t L, const Bytes32& expected_tip_ref);

// Pure bind-acceptance rule over an already-derived bind state (see NodeState::bind_acceptable).
bool bind_acceptable_in(const jackpot_v2::DerivedBindState& st, const PubKeyHash& mining_pkh,
                        const NodePubKey& node_pubkey, uint64_t bind_seq);

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

// ---- Mempool / block-template POLICY (NON-consensus) — EMERGENCY 2026-10-08 ----
// The audit (CRITICAL #2) showed node txs entering the mempool with shape checks only:
// one invalid NODE_BIND / NODE_HEARTBEAT in a template made every mined block invalid.
// These helpers apply the AUTHORITATIVE block rule (connect_block_node_txs) to a SCRATCH
// copy of the live state, so policy can never be looser than consensus, and they never
// mutate `live`. They change no block-validity rule (v16.x-compatible by construction).
//
// True iff a block at `height` containing exactly `txs` (node txs only) would pass
// connect_block_node_txs against `live`. `why` receives the consensus reason on failure.
bool node_txs_valid_for_block(const NodeState& live, const std::vector<const Transaction*>& txs,
                              int64_t height, int64_t A, int64_t L,
                              const std::function<bool(int64_t, Bytes32&)>& block_hash_at,
                              std::string* why = nullptr);

// Upper bound on node txs one template may carry. Policy only (consensus accepts more);
// bounds the per-block validation cost our own miners impose (audit HIGH #5). Heartbeats
// need 1 per miner per 288-block epoch, so 64/block is ample for any realistic miner count.
constexpr size_t MAX_NODE_TXS_PER_TEMPLATE = 64;

// Everything the per-tx policy needs at one height, derived ONCE from the live state
// (O(N log N)); judging a tx against it is then O(log N) + one signature check. The node
// caches it per (tip, height) and rebuilds it whenever the node state changes.
struct NodeTxPolicyContext {
    int64_t height{0}, A{0}, L{0};
    bool    active{false};
    bool    have_tip{false};
    Bytes32 expected_tip{};
    size_t  nbinds{0}, nhbs{0};                     // live-state size it was built from
    jackpot_v2::DerivedBindState preblock;          // == what connect_block_node_txs derives
    std::map<NodePubKey, PubKeyHash> owner_of_node; // node key -> miner, active pre-block
};
NodeTxPolicyContext make_node_tx_policy_context(const NodeState& live, int64_t height, int64_t A, int64_t L,
                                                const std::function<bool(int64_t, Bytes32&)>& block_hash_at);

struct NodeTxVerdict {
    bool        ok{false};
    std::string reason{"invalid"};
    NodeTxKind  kind{NodeTxKind::None};
    PubKeyHash  mining_pkh{};        // bind: the miner; heartbeat: the resolved owner
    NodePubKey  node_pubkey{};       // bind only
    int64_t     epoch_idx{-1};       // heartbeat only
};
// The per-tx checks of connect_block_node_txs for a block holding only `tx`.
NodeTxVerdict judge_node_tx(const NodeTxPolicyContext& c, const NodeState& live, const Transaction& tx);

struct NodeTxSelection {
    std::vector<size_t> keep;                              // indices into the input, in order
    std::vector<std::pair<size_t, std::string>> invalid;   // can never be mined at this height -> evict
    std::vector<size_t> deferred;                          // valid but conflicting / over the cap -> keep in pool
    bool        assertion_failed{false};                   // kept set failed the block rule (then keep is empty)
    std::string assertion_reason;
};
// Greedy, order-preserving selection: per-tx verdicts + the same-block caps (one bind per
// miner, one bind per node key, one heartbeat per (owner, epoch)), capped at max_keep, then
// ONE authoritative connect_block_node_txs check on the kept set (fail-safe: keep nothing).
NodeTxSelection select_node_txs_for_template(const NodeTxPolicyContext& c, const NodeState& live,
                                             const std::vector<const Transaction*>& txs,
                                             const std::function<bool(int64_t, Bytes32&)>& block_hash_at,
                                             size_t max_keep = MAX_NODE_TXS_PER_TEMPLATE);

} // namespace sost::node_participation
