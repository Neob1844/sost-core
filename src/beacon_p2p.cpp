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
#include "sost/beacon.h"
#include "sost/params.h"

#include <climits>
#include <ctime>

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
    // Legacy / scaffold entry point — preserved for pre-existing tests
    // that pin the dormancy invariant against the original signature.
    // The production dispatcher in src/sost-node.cpp uses
    // BeaconP2PState::process_incoming(...) instead, which carries the
    // peer identity, network, and the optional gate override needed for
    // testing the active path.
    //
    // While the global gate sentinel BEACON_P2P_ACTIVATION_HEIGHT is
    // INT64_MAX, this function always returns DiscardDormant — the
    // existing scaffold contract is preserved exactly.
    if (!is_p2p_enabled(current_height)) {
        (void)bytes;
        return IncomingDecision::DiscardDormant;
    }
    // If the global gate ever lowers, fall through to a stateless
    // single-shot evaluation. This is a thin convenience wrapper and
    // does NOT cache or relay — production callers must use
    // BeaconP2PState.
    BeaconP2PState scratch;
    return scratch.process_incoming(
        /*peer_id=*/"<legacy>",
        bytes,
        current_height,
        ::sost::beacon::Network::MAINNET,
        /*out_notice=*/nullptr,
        /*now_sec=*/0,
        /*gate_height_override=*/INT64_MIN);
}

// ---------------------------------------------------------------------------
// BeaconP2PState — full pipeline (size cap, parse, sig verify, network,
// expiry, dedup LRU, per-peer rate limit, accept+relay).
//
// The implementation is dormant by default: when no gate override is
// supplied AND BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX, the FIRST
// check returns DiscardDormant before any allocation. Tests pass a
// finite gate_height_override to exercise the active branches.
// ---------------------------------------------------------------------------

size_t BeaconP2PState::cache_size() const {
    std::lock_guard<std::mutex> lk(mu_);
    return lru_ids_.size();
}

size_t BeaconP2PState::rate_map_size() const {
    std::lock_guard<std::mutex> lk(mu_);
    return rate_map_.size();
}

IncomingDecision BeaconP2PState::process_incoming(
    const std::string& peer_id,
    const std::string& bytes,
    int64_t            current_height,
    ::sost::beacon::Network local_network,
    Notice*            out_notice,
    int64_t            now_sec_in,
    int64_t            gate_height_override)
{
    // -----------------------------------------------------------------
    // 0) Activation gate. Tests pass gate_height_override = 0 (or any
    //    finite value) to enable the path. Production callers leave it
    //    at the INT64_MIN sentinel, falling through to is_p2p_enabled
    //    which honours the global BEACON_P2P_ACTIVATION_HEIGHT (= INT64_MAX
    //    in this commit).
    // -----------------------------------------------------------------
    if (gate_height_override == INT64_MIN) {
        if (!is_p2p_enabled(current_height)) return IncomingDecision::DiscardDormant;
    } else {
        if (current_height < gate_height_override) return IncomingDecision::DiscardDormant;
    }

    // -----------------------------------------------------------------
    // 1) Size cap — checked BEFORE allocating parser scratch.
    // -----------------------------------------------------------------
    if (bytes.size() > BEACON_P2P_NOTICE_MAX_BYTES) {
        return IncomingDecision::DiscardOversized;
    }

    // -----------------------------------------------------------------
    // 2) Parse. The on-wire format is a JSON array containing exactly
    //    ONE notice (the gossiped granularity). A wrapper array keeps
    //    the parser identical to the file-loaded II-A path.
    // -----------------------------------------------------------------
    std::vector<::sost::beacon::Notice> parsed;
    if (!::sost::beacon::parse_notices_array(bytes, parsed)) {
        return IncomingDecision::DiscardMalformed;
    }
    if (parsed.size() != 1) {
        // We intentionally restrict gossip to one notice per message so
        // a single bad notice cannot taint a batch. Any other count is
        // a protocol violation.
        return IncomingDecision::DiscardMalformed;
    }
    ::sost::beacon::Notice& n = parsed.front();

    // -----------------------------------------------------------------
    // 3) Signature verification. Threshold-aware: if the notice claims
    //    threshold > 0, use verify_threshold_signatures against the
    //    hardcoded BEACON_THRESHOLD_PUBKEYS; otherwise legacy single-sig.
    // -----------------------------------------------------------------
    if (n.threshold > 0) {
        auto tr = ::sost::beacon::verify_threshold_signatures(n, nullptr, 0);
        if (!tr.ok) return IncomingDecision::DiscardBadSignature;
    } else {
        if (!::sost::beacon::verify_signature(n)) return IncomingDecision::DiscardBadSignature;
    }

    // -----------------------------------------------------------------
    // 4) Network match. Cross-network is silent (normal accidental
    //    traffic at boundaries; not misbehaviour).
    // -----------------------------------------------------------------
    if (n.network != local_network) return IncomingDecision::DiscardWrongNetwork;

    // -----------------------------------------------------------------
    // 5) Expiry. Inclusive at expires_height (same rule as is_active).
    //    Also rejects notices not yet activated — gossiping a future
    //    notice that the local node would not surface anyway is wasted
    //    bandwidth.
    // -----------------------------------------------------------------
    if (n.expires_height   <= current_height) return IncomingDecision::DiscardExpired;
    if (n.activation_height > current_height) return IncomingDecision::DiscardExpired;

    // -----------------------------------------------------------------
    // 6 + 7) Dedup + per-peer rate-limit + cache insert + commit.
    //
    // Held under mu_. Sig verify above ran OUTSIDE the lock (CPU work
    // does not need to serialise across peers). We re-check dedup
    // inside the lock to close the race where two peers send the same
    // notice concurrently.
    // -----------------------------------------------------------------
    const int64_t now = (now_sec_in != 0) ? now_sec_in : (int64_t)std::time(nullptr);
    std::lock_guard<std::mutex> lk(mu_);

    // 6) Dedup
    if (lru_set_.find(n.notice_id) != lru_set_.end()) {
        return IncomingDecision::DiscardDuplicate;
    }

    // 7) Per-peer rate-limit. Sliding 60 s window of ACCEPTED notice ids.
    PeerRate& pr = rate_map_[peer_id];
    while (!pr.arrivals.empty() && (now - pr.arrivals.front()) > 60) {
        pr.arrivals.pop_front();
    }
    if ((int)pr.arrivals.size() >= BEACON_P2P_PEER_RATE_PER_MIN) {
        return IncomingDecision::DiscardRateLimited;
    }

    // 8) Accept. Insert into LRU (FIFO eviction at cap) + bump rate window.
    if (lru_ids_.size() >= BEACON_P2P_CACHE_MAX_NOTICES) {
        const std::string& victim = lru_ids_.front();
        lru_set_.erase(victim);
        lru_ids_.pop_front();
    }
    lru_ids_.push_back(n.notice_id);
    lru_set_.insert(n.notice_id);
    pr.arrivals.push_back(now);

    if (out_notice) *out_notice = std::move(n);
    return IncomingDecision::AcceptAndRelay;
}

} // namespace sost::beacon::p2p
