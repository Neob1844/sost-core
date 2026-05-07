// SOST Beacon Phase III — P2P notice gossip scaffold (DORMANT).
//
// =====================================================================
// THIS PHASE IS DISABLED BY DEFAULT.  IT DOES NOT SHIP A WORKING GOSSIP
// PATH.  THE TYPES AND HANDLERS BELOW ARE INTENTIONALLY INERT.
// =====================================================================
//
// The activation gate is `BEACON_P2P_ACTIVATION_HEIGHT` (declared in
// `include/sost/params.h`). It is pinned at `INT64_MAX` (sentinel =
// "never, until a future fork commit lowers the gate"). The node code
// MUST NOT register a P2P message type for Beacon notices, MUST NOT
// gossip anything, and MUST drop any incoming candidate notice silently
// while `is_p2p_enabled(...)` returns false.
//
// Rationale:
//   - Phase II-A (local-file path) is sufficient for V13 operations.
//     Adding P2P gossip introduces a new attack surface (DoS, oversized
//     payloads, replay, spam) that has not been audited.
//   - Shipping the scaffold now lets a future operator enable Phase III
//     by:
//       1. lowering BEACON_P2P_ACTIVATION_HEIGHT in params.h,
//       2. registering the network message type in the P2P layer,
//       3. wiring the existing `handle_incoming_notice_message` into
//          the dispatch table.
//     Until step (1) lowers the gate, nothing here can fire.
//   - The hard limits below (max size, max cache size, dedup, rate
//     limits) are documented now so a future enabling commit cannot
//     ship without them by accident.
//
// Hard invariants the scaffold satisfies even while disabled:
//   - `is_p2p_enabled(height)` returns false for every height that does
//     not strictly exceed `BEACON_P2P_ACTIVATION_HEIGHT - 1`. Today
//     that is "every height ever".
//   - `handle_incoming_notice_message(...)` always returns
//     `IncomingDecision::DiscardDormant` until the gate is lowered;
//     once lowered, every further check (size, schema, dedup, rate
//     limit) must pass before a notice is cached or relayed.
//   - The scaffold has no internal cache, no peer-state, no timers, no
//     threads. It is pure functions only. A future enabling commit
//     adds those resources; this one does not.

#pragma once

#include "sost/types.h"

#include <cstdint>
#include <string>

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

} // namespace sost::beacon::p2p
