// SOST Beacon Phase III — P2P notice gossip scaffold (DORMANT).
// See include/sost/beacon_p2p.h for the contract.
//
// The implementation is intentionally minimal: while
// BEACON_P2P_ACTIVATION_HEIGHT remains at its sentinel (INT64_MAX), the
// only paths that fire are:
//   - is_p2p_enabled(): always returns false
//   - handle_incoming_notice_message(): always returns DiscardDormant
//
// The activation gate is the single switch a future enabling commit
// has to lower. Until then, NOTHING in this file allocates resources,
// touches peers, or relays bytes.

#include "sost/beacon_p2p.h"
#include "sost/params.h"

namespace sost::beacon::p2p {

bool is_p2p_enabled(int64_t current_height) {
    // Sentinel-disabled gate: BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX
    // means "Phase III P2P never active under any height". The explicit
    // sentinel check below preserves that semantic even at the
    // degenerate edge `current_height == INT64_MAX`, where a plain
    // greater-than-or-equal comparison would otherwise return true.
    // The chain never reaches h = INT64_MAX, but a defensive
    // contract is cheaper than a future debate over the edge case.
    if (BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX) return false;
    return current_height >= BEACON_P2P_ACTIVATION_HEIGHT;
}

const char* decision_name(IncomingDecision d) {
    switch (d) {
        case IncomingDecision::DiscardDormant:      return "DiscardDormant";
        case IncomingDecision::DiscardOversized:    return "DiscardOversized";
        case IncomingDecision::DiscardMalformed:    return "DiscardMalformed";
        case IncomingDecision::DiscardBadSignature: return "DiscardBadSignature";
        case IncomingDecision::DiscardExpired:      return "DiscardExpired";
        case IncomingDecision::DiscardWrongNetwork: return "DiscardWrongNetwork";
        case IncomingDecision::DiscardDuplicate:    return "DiscardDuplicate";
        case IncomingDecision::DiscardRateLimited:  return "DiscardRateLimited";
        case IncomingDecision::AcceptAndRelay:      return "AcceptAndRelay";
    }
    return "Unknown";
}

IncomingDecision handle_incoming_notice_message(const std::string& bytes,
                                                int64_t            current_height) {
    // Hard guard: while disabled, EVERY input is dropped before any
    // parsing or signature work. The size argument is ignored on this
    // path — we deliberately do NOT even allocate scratch buffers.
    if (!is_p2p_enabled(current_height)) {
        (void)bytes;
        return IncomingDecision::DiscardDormant;
    }

    // ===================================================================
    // The block below is unreachable today (gate sentinel = INT64_MAX).
    // Documented so a future enabling commit has the order pinned:
    //
    //   1. Reject if bytes.size() > BEACON_P2P_NOTICE_MAX_BYTES
    //         → DiscardOversized
    //   2. Parse via beacon::parse_notices_array() (single-element form).
    //         Failure → DiscardMalformed
    //   3. Verify signature (beacon::verify_signature)
    //         Failure → DiscardBadSignature
    //   4. Match local network
    //         Mismatch → DiscardWrongNetwork
    //   5. Reject if expired (height >= expires_height)
    //         → DiscardExpired
    //   6. Reject if duplicate notice_id already in cache
    //         → DiscardDuplicate
    //   7. Reject if peer's per-minute rate limit exceeded
    //         → DiscardRateLimited
    //   8. Otherwise insert into cache (LRU at cap) and return
    //         → AcceptAndRelay
    // ===================================================================
    return IncomingDecision::DiscardDormant;
}

} // namespace sost::beacon::p2p
