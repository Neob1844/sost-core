// SOST Beacon Phase III — P2P notice gossip (ACTIVE at V13).
//
// =====================================================================
// ACTIVE FROM BLOCK V13_HEIGHT (= 12000). BELOW THAT HEIGHT EVERY
// INCOMING BCNN MESSAGE IS SILENTLY DROPPED VIA DiscardDormant.
// =====================================================================
//
// The activation gate is `BEACON_P2P_ACTIVATION_HEIGHT` (declared in
// `include/sost/params.h`). As of the V13 release it is set to
// `V13_HEIGHT`. For heights strictly below the gate the dispatcher
// drops candidate notices silently; for heights at or above the gate
// the full pipeline (size cap, parse, sig verify, network match,
// expiry, dedup LRU, per-peer rate limit) runs.
//
// ADVISORY ONLY: nothing in this header changes consensus, block
// validation, mining validity, or rewards. The decision returned by
// the handler is never consulted by chain code.
//
// Rationale:
//   - V13 enables Beacon Phase III as a hardened advisory channel
//     ON TOP OF Phase II-A (local file) and Phase II-B (3-of-5
//     threshold). All three layers coexist; no layer overrides
//     another. P2P gossip lets a freshly-published signed notice
//     reach miners and full nodes without requiring each operator
//     to manually drop notices.json on disk.
//   - The DoS / oversized / replay / spam concerns that originally
//     justified deferring Phase III are mitigated by the hard limits
//     enforced below and audited in tests/test_v13_beacon_phase3_p2p.cpp.
//   - Bad signatures are silently discarded (no banscore tick) so an
//     honest relay carrying a stale or corrupted notice cannot be
//     punished. Oversized / malformed / rate-limit hits ARE loud
//     (the dispatcher adds misbehavior points).
//
// Hard invariants:
//   - `is_p2p_enabled(height)` returns false for heights strictly less
//     than `BEACON_P2P_ACTIVATION_HEIGHT` (= V13_HEIGHT). Pre-V13
//     remains dormant.
//   - `BeaconP2PState::process_incoming(...)` runs the full pipeline
//     for heights at or above the gate, returning AcceptAndRelay only
//     after size + parse + sig + network + expiry + dedup +
//     per-peer rate-limit all pass.
//   - The cache is bounded at BEACON_P2P_CACHE_MAX_NOTICES (= 32);
//     the per-peer sliding-window ages out entries older than 60 s.
//   - No Beacon code path links into block_validation, mining, or
//     chain commit. The advisory-only invariant is pinned by a
//     link-time test (tests/test_v13_beacon_phase3_p2p.cpp:t15).

#pragma once

#include "sost/types.h"
#include "sost/beacon.h"          // Notice, Network

#include <climits>
#include <cstdint>
#include <deque>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>

namespace sost::beacon::p2p {

// ---------------------------------------------------------------------------
// Activation gate
// ---------------------------------------------------------------------------

// Returns true iff Phase III P2P should be active at the given chain
// height. Until BEACON_P2P_ACTIVATION_HEIGHT in params.h is lowered
// from its INT64_MAX sentinel, this function returns false for every
// finite height.
bool is_p2p_enabled(int64_t current_height);

// ---------------------------------------------------------------------------
// Hard limits (frozen at scaffold time so a future enabling commit
// cannot relax them silently). The numbers are deliberate:
//
//   BEACON_P2P_NOTICE_MAX_BYTES   The on-wire size cap. 4 KiB is well
//                                 above any realistic Phase 1 notice
//                                 (under 1 KB) and small enough that
//                                 a misbehaving peer cannot use it as
//                                 a DoS amplifier.
//
//   BEACON_P2P_CACHE_MAX_NOTICES  Maximum simultaneous notices held in
//                                 memory. 32 is generous: Phase 1 has
//                                 never published more than 1 active
//                                 notice in production. Bounded LRU
//                                 eviction at the cap keeps the cache
//                                 size predictable.
//
//   BEACON_P2P_PEER_RATE_PER_MIN  Maximum NEW notice IDs accepted from
//                                 a single peer per 60 s window. A
//                                 well-behaved peer relays at most 1.
//                                 The cap is 8 to absorb burst arrivals
//                                 from a peer that just learned of a
//                                 batch but kept low enough that a
//                                 misbehaving peer is throttled fast.
// ---------------------------------------------------------------------------

inline constexpr size_t  BEACON_P2P_NOTICE_MAX_BYTES   = 4 * 1024;
inline constexpr size_t  BEACON_P2P_CACHE_MAX_NOTICES  = 32;
inline constexpr int     BEACON_P2P_PEER_RATE_PER_MIN  = 8;

// ---------------------------------------------------------------------------
// Decision returned by `handle_incoming_notice_message`. The dispatch
// table for the P2P transport layer interprets these as follows:
//
//   DiscardDormant      Phase III is gated off. Drop the message
//                       immediately; do NOT decrement the peer's
//                       reputation, do NOT relay, do NOT log loudly
//                       (a single debug-level line is acceptable).
//
//   DiscardOversized    The serialized notice exceeded
//                       BEACON_P2P_NOTICE_MAX_BYTES. Drop and tick the
//                       peer's misbehaviour counter — sending an
//                       oversized notice is a clear protocol violation.
//
//   DiscardMalformed    The bytes did not parse as a Phase 1 notice.
//                       Drop and tick the peer's misbehaviour counter.
//
//   DiscardBadSignature Signature failed to verify. Drop SILENTLY (do
//                       NOT tick a misbehaviour counter — the bad
//                       signature could be from a third party that
//                       relayed in good faith).
//
//   DiscardExpired      Notice's `expires_height` already passed. Drop
//                       silently.
//
//   DiscardWrongNetwork Notice claimed a different `network` value
//                       than the local node is on. Drop silently —
//                       cross-network propagation is normal accidental
//                       traffic at network boundaries.
//
//   DiscardDuplicate    Already in the cache. Drop silently. Common.
//
//   DiscardRateLimited  Peer exceeded BEACON_P2P_PEER_RATE_PER_MIN.
//                       Drop and tick the peer's rate-limit counter
//                       (NOT the same as misbehaviour — repeated
//                       limits eventually disconnect the peer).
//
//   AcceptAndRelay      Caller is expected to (a) cache it and (b)
//                       broadcast it to every other connected peer.
// ---------------------------------------------------------------------------

enum class IncomingDecision {
    DiscardDormant,
    DiscardOversized,
    DiscardMalformed,
    DiscardBadSignature,
    DiscardExpired,
    DiscardWrongNetwork,
    DiscardDuplicate,
    DiscardRateLimited,
    AcceptAndRelay,
};

// Pretty-print an IncomingDecision for logs / tests.
const char* decision_name(IncomingDecision d);

// ---------------------------------------------------------------------------
// Process an incoming notice from a peer. While Phase III is gated off,
// this function ALWAYS returns DiscardDormant — it never inspects
// `bytes` beyond the size cap, never touches a cache, never modifies
// peer state. The signature is identical to the eventual production
// signature so a future enabling commit only has to flip the gate and
// remove the early-return.
//
// Inputs:
//   bytes              The on-wire payload as received from the peer.
//   current_height     Used by the activation gate. Never inspected by
//                      the dormant implementation.
//
// Returns: IncomingDecision::DiscardDormant unless the activation gate
// is open AND every other check passes.
//
// MUST NOT throw.
// MUST NOT block.
// MUST NOT log at higher than debug level.
IncomingDecision handle_incoming_notice_message(
    const std::string& bytes,
    int64_t            current_height);

// ---------------------------------------------------------------------------
// BeaconP2PState — production state container (Commit A: ready, dormant).
//
// Wraps the LRU dedup cache, the per-peer sliding-window rate-limit map,
// and the mutex that serialises access to them. A single instance lives
// in src/sost-node.cpp; tests create their own to exercise the active
// path under an injected gate height.
//
// Thread-safe: every public method takes the internal mutex. The mutex
// is fine-grained (does not cover sig verification CPU work) and NEVER
// calls back into the dispatcher, so it cannot deadlock with g_peers_mu
// or g_chain_mu.
//
// Hard invariants:
//   - process_incoming is the SOLE entry point. Tests cannot poke the
//     cache directly except via cache_size() (read-only).
//   - The cache is bounded at BEACON_P2P_CACHE_MAX_NOTICES (= 32);
//     oldest entries are evicted FIFO at the cap.
//   - The rate-limit map ages out entries older than 60 seconds per
//     check, so it does not grow unboundedly with churn.
//   - The dormant gate is checked FIRST. Tests inject gate_height_override
//     to exercise the active path without changing the global sentinel.
// ---------------------------------------------------------------------------

class BeaconP2PState {
public:
    // Inspect an incoming notice payload from a specific peer. Returns
    // a single IncomingDecision describing what the caller should do.
    //
    // Inputs:
    //   peer_id              Stable identifier for the sending peer
    //                        (the node uses the address string).
    //   bytes                On-wire payload as received.
    //   current_height       Local chain tip height for the gate check.
    //   local_network        Network this node is on; cross-network
    //                        notices are silently discarded.
    //   out_notice           Optional output: populated with the parsed
    //                        Notice when the decision is AcceptAndRelay.
    //   now_sec              Optional Unix-seconds override. 0 (default)
    //                        means std::time(nullptr). Tests pass a
    //                        deterministic value.
    //   gate_height_override Optional alternate activation gate. The
    //                        sentinel INT64_MIN (default) means use the
    //                        production BEACON_P2P_ACTIVATION_HEIGHT
    //                        constant. Tests pass a finite value to
    //                        exercise the active path while the global
    //                        gate stays at INT64_MAX.
    //
    // Never throws, never blocks on I/O, never opens a socket, never
    // touches consensus state. Does NOT relay anything itself; relay is
    // the caller's job (the only entity that knows peer sockets).
    IncomingDecision process_incoming(
        const std::string& peer_id,
        const std::string& bytes,
        int64_t            current_height,
        ::sost::beacon::Network local_network,
        Notice*            out_notice = nullptr,
        int64_t            now_sec = 0,
        int64_t            gate_height_override = INT64_MIN);

    // Test-only inspectors. Cheap snapshot under the internal mutex.
    size_t cache_size() const;
    size_t rate_map_size() const;

private:
    struct PeerRate {
        // Per-peer sliding-window timestamps of ACCEPTED notice ids.
        // Entries older than 60 s are pruned on every check.
        std::deque<int64_t> arrivals;
    };

    mutable std::mutex                          mu_;
    std::deque<std::string>                     lru_ids_;   // FIFO order
    std::unordered_set<std::string>             lru_set_;   // membership index
    std::unordered_map<std::string, PeerRate>   rate_map_;
};

} // namespace sost::beacon::p2p
