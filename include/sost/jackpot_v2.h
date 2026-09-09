#pragma once
// ============================================================================
// V16 — HISTORICAL JACKPOT V2: PURE consensus core.
// Spec: docs/v16/HISTORICAL_JACKPOT_V2_SPEC.md  (activation #30,000, LOCKED).
//
// Philosophy (owner-frozen):
//     NODE participation DETERMINES ELIGIBILITY.
//     PROOF-OF-WORK DETERMINES WEIGHT (linear).
//
// This header holds ONLY pure, deterministic, side-effect-free helpers:
//   - epoch math + heartbeat bootstrap ramp (min-clamp)
//   - active NODE_BIND derivation from a list of bind records
//     (effective at inclusion_height+1; highest bind_seq wins; a node_pubkey
//      is globally unique to ONE mining_pkh)
//   - heartbeat window counting per mining identity
//   - V2 jackpot eligibility predicate
//   - linear PoW weight + canonical ordering (raw mining_pkh bytes ascending)
//   - domain-separated seed + integer weighted-draw winner selection
//
// It does NOT touch tx serialization, block validation, ConnectBlock/
// DisconnectBlock, mempool, RPC or CLI — that wiring lands in later increments
// on top of this tested core (exactly as apply_lottery_block / hist_jackpot_apply
// are pure and wired separately). Nothing here mints SOST or changes DTD-normal.
//
// Signature verification (Schnorr) for NODE_BIND / NODE_HEARTBEAT is performed
// by the tx-type layer BEFORE records reach these helpers: every record passed
// in is assumed already signature-valid. These helpers enforce the STRUCTURAL
// and STATE rules (uniqueness, sequencing, effective height, epoch windows).
// ============================================================================
#include <cstdint>
#include <array>
#include <vector>
#include <algorithm>
#include <map>
#include <set>

#include "sost/params.h"      // HIST_JACKPOT_V2_HEIGHT, NODE_EPOCH_LENGTH, JACKPOT_V2_*
#include "sost/types.h"       // Bytes32
#include "sost/tx_signer.h"   // PubKeyHash (std::array<Byte,20>)
#include "sost/crypto.h"      // sha256()
#include "sost/serialize.h"   // append, append_u64_le, read_u64_le

namespace sost::jackpot_v2 {

// A node public key is a 32-byte x-only Schnorr key (same family as SbPoW).
using NodePubKey = std::array<uint8_t, 32>;

// Domain-separation tags (never reuse the DTD seed).
inline constexpr char JACKPOT_V2_DOMAIN[]  = "SOST_HIST_JACKPOT";
inline constexpr char NODE_BIND_DOMAIN[]   = "SOST_NODE_BIND";
inline constexpr char NODE_HB_DOMAIN[]     = "SOST_NODE_HEARTBEAT";

// ---------------------------------------------------------------------------
// Epoch math (aligned to activation A). epoch e = [A + e*L, A + (e+1)*L - 1].
// ---------------------------------------------------------------------------
inline int64_t jv2_epoch_start(int64_t A, int64_t L, int64_t e) { return A + e * L; }

// Number of epochs COMPLETED strictly before height H (epoch e completes at the
// end of A + (e+1)*L - 1, i.e. counts from H > that). floor((H-A)/L) for H>A.
inline int64_t jv2_completed_epochs_before(int64_t A, int64_t L, int64_t H) {
    if (H <= A || L <= 0) return 0;
    return (H - A) / L;
}

// The epoch index a height belongs to (H >= A). -1 if before activation.
inline int64_t jv2_epoch_of_height(int64_t A, int64_t L, int64_t H) {
    if (H < A || L <= 0) return -1;
    return (H - A) / L;
}

// Bootstrap ramp (min-clamp). NODE_BIND is ALWAYS required separately.
inline int64_t jv2_heartbeat_required(int64_t completed_epochs) {
    int64_t r = completed_epochs < HEARTBEAT_REQUIRED ? completed_epochs : HEARTBEAT_REQUIRED;
    return r < 0 ? 0 : r;
}
inline int64_t jv2_heartbeat_window(int64_t completed_epochs) {
    int64_t w = completed_epochs < HEARTBEAT_MAX_WINDOW ? completed_epochs : HEARTBEAT_MAX_WINDOW;
    return w < 0 ? 0 : w;
}

// ---------------------------------------------------------------------------
// NODE_BIND — structural record (signature assumed already verified upstream).
// ---------------------------------------------------------------------------
struct NodeBindRecord {
    PubKeyHash mining_pkh{};
    NodePubKey node_pubkey{};
    int64_t    bind_seq{0};          // per mining_pkh; strictly increasing
    int64_t    inclusion_height{0};  // block height where this bind was included
};

// The active binding for a mining_pkh at query height H.
struct ActiveBinding {
    NodePubKey node_pubkey{};
    int64_t    bind_seq{0};
    int64_t    effective_height{0};  // inclusion_height + 1
};

// Derive the active node binding per mining_pkh at height H from ALL bind
// records seen on-chain, applying (deterministically):
//   * a record is only in force at H if effective_height (= inclusion_height+1) <= H
//   * within a mining_pkh, bind_seq must be strictly increasing in inclusion
//     order; a record whose bind_seq <= the max already accepted is IGNORED
//     (replay / stale) — the highest accepted seq is the active binding
//   * global uniqueness: a node_pubkey may belong to exactly ONE mining_pkh
//     ever; the FIRST mining_pkh to claim it (by inclusion_height, then
//     mining_pkh order) owns it; any later bind of the same node_pubkey by a
//     DIFFERENT mining_pkh is rejected
// Records are consumed in canonical order (inclusion_height, then bind_seq,
// then mining_pkh) so the result is order-independent of input vector order.
std::map<PubKeyHash, ActiveBinding>
jv2_active_bindings_at(std::vector<NodeBindRecord> records, int64_t H);

// Convenience: is `mining_pkh` node-bound at height H?
bool jv2_is_node_bound_at(const std::vector<NodeBindRecord>& records,
                          const PubKeyHash& mining_pkh, int64_t H);

// ---------------------------------------------------------------------------
// NODE_HEARTBEAT — structural record (signature assumed already verified).
// A heartbeat is VALID for epoch e iff (checked by the tx layer, restated here
// for the pure counter): node_pubkey was the active binding for its mining_pkh
// at inclusion height; epoch_idx == epoch_of(inclusion_height); tip_ref_hash ==
// hash(epoch_start(epoch_idx) - 1). Here we count DISTINCT epochs satisfied.
// ---------------------------------------------------------------------------
struct HeartbeatRecord {
    PubKeyHash mining_pkh{};   // resolved owner (via the active binding at inclusion)
    int64_t    epoch_idx{0};
};

// Count DISTINCT completed epochs, among the last `window` completed epochs
// before jackpot height H, in which `mining_pkh` has >= 1 valid heartbeat.
// Dedup is per (mining_pkh, epoch): rotating node keys within an epoch cannot
// manufacture multiple credited heartbeats for the same epoch.
int64_t jv2_heartbeats_in_window(const std::vector<HeartbeatRecord>& hbs,
                                 const PubKeyHash& mining_pkh,
                                 int64_t A, int64_t L, int64_t H);

// ---------------------------------------------------------------------------
// Eligibility + weight.
// ---------------------------------------------------------------------------
// One candidate's fully chain-derived V2 view at jackpot height H.
struct JackpotV2Candidate {
    PubKeyHash mining_pkh{};
    bool       sbpow_valid{false};       // has a signed SbPoW identity
    int64_t    pow_blocks{0};            // SbPoW blocks in [H-WINDOW, H-1] (LINEAR weight)
    bool       node_bound{false};        // active NODE_BIND at H-1
    int64_t    heartbeats_in_window{0};  // distinct epochs satisfied in the ramp window
};

// Reason bitmask for the eligibility check (diagnostic; consensus only needs the bool).
enum JackpotV2Reason : uint32_t {
    JV2_OK              = 0,
    JV2_NOT_V2_HEIGHT   = 1u << 0,
    JV2_NO_SBPOW        = 1u << 1,
    JV2_POW_TOO_LOW     = 1u << 2,
    JV2_NOT_NODE_BOUND  = 1u << 3,
    JV2_HEARTBEAT_SHORT = 1u << 4,
};

// Pure predicate. `A` = V2 activation, `L` = epoch length. required heartbeats
// are computed from the bootstrap ramp at H.
uint32_t jv2_eligibility_reason(const JackpotV2Candidate& c, int64_t A, int64_t L, int64_t H);
inline bool jv2_is_eligible(const JackpotV2Candidate& c, int64_t A, int64_t L, int64_t H) {
    return jv2_eligibility_reason(c, A, L, H) == JV2_OK;
}

// An eligible participant reduced to (canonical key, linear weight).
struct JackpotV2Weighted {
    PubKeyHash pkh{};
    int64_t    weight{0};   // == pow_blocks
};

// Filter candidates to the eligible set and project to (pkh, weight), sorted in
// CANONICAL order: raw mining_pkh bytes ascending. Deterministic, order-free.
std::vector<JackpotV2Weighted>
jv2_build_weighted_set(const std::vector<JackpotV2Candidate>& candidates,
                       int64_t A, int64_t L, int64_t H);

inline int64_t jv2_total_weight(const std::vector<JackpotV2Weighted>& s) {
    int64_t t = 0;
    for (const auto& e : s) t += e.weight;   // window <= 5000 => no overflow; int64 headroom huge
    return t;
}

// ---------------------------------------------------------------------------
// Seed + winner selection (integer only; NEVER float in consensus).
// seed = sha256( "SOST_HIST_JACKPOT" || entropy_hashes... || height_le )
// entropy_hashes are chain-derived recent block hashes (same family the DTD
// selector uses), but under the V2 domain tag so the two draws are independent.
// ---------------------------------------------------------------------------
Bytes32 jv2_seed(const std::vector<Bytes32>& entropy_hashes, int64_t height);

// Weighted draw over a CANONICALLY-SORTED weighted set.
//   roll = read_u64_le(seed) % total_weight
//   winner = first i with (running_cumulative > roll)
// Returns index in `sorted`, or -1 if the set is empty / total weight is 0
// (=> no winner => jackpot rolls over; funds preserved).
int64_t jv2_select_winner_index(const std::vector<JackpotV2Weighted>& sorted,
                                const Bytes32& seed);

} // namespace sost::jackpot_v2
