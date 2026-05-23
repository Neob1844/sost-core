// SOST Beacon Phase III — P2P notice gossip (ACTIVE at V13).
// See include/sost/beacon_p2p.h for the public contract.
//
// As of V13, BEACON_P2P_ACTIVATION_HEIGHT = V13_HEIGHT (= 12000). For
// heights strictly below the gate the pipeline returns DiscardDormant
// before any allocation; at or above the gate the full 7-check
// pipeline (size cap, parse, sig verify, network, expiry, dedup LRU,
// per-peer rate-limit) runs and the dispatcher relays accepted
// notices to other peers.
//
// ADVISORY ONLY: this file does not link consensus, block validation,
// or mining symbols. Bad signatures are silent; oversized / malformed
// / rate-limit are loud (caller adds misbehavior).

#include "sost/beacon_p2p.h"
#include "sost/beacon.h"
#include "sost/params.h"

#include <climits>
#include <ctime>

namespace sost::beacon::p2p {

bool is_p2p_enabled(int64_t current_height) {
    // Two-step gate:
    //   1. If BEACON_P2P_ACTIVATION_HEIGHT == INT64_MAX, the operator
    //      has explicitly disabled Phase III (sentinel mode). Return
    //      false for every height, even INT64_MAX itself.
    //   2. Otherwise return (current_height >= BEACON_P2P_ACTIVATION_HEIGHT).
    //
    // Production (V13): the gate is V13_HEIGHT (= 12000), so the
    // sentinel branch is inactive and the comparison branch decides.
    // The sentinel preserved in code lets a future operator disable
    // Phase III again by re-setting the constant to INT64_MAX without
    // touching call sites.
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
    // Legacy / scaffold entry point — preserved for tests that pin the
    // gate-respecting contract against the original (peer-less)
    // signature. The production dispatcher in src/sost-node.cpp uses
    // BeaconP2PState::process_incoming(...) instead, which carries the
    // peer identity, network, and optional gate override needed for
    // testing the active path.
    //
    // For heights strictly below BEACON_P2P_ACTIVATION_HEIGHT this
    // function returns DiscardDormant before any allocation.
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
// Production gate: BEACON_P2P_ACTIVATION_HEIGHT == V13_HEIGHT. For
// heights below the gate the first check returns DiscardDormant before
// any allocation; from the gate onwards the pipeline runs. Tests pass
// a finite gate_height_override to exercise the active branches against
// a synthetic height regardless of the production gate.
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
    // Activation gate. Tests pass gate_height_override = 0 (or any
    // finite value) to enable the path under a synthetic height.
    // Production callers leave it at the INT64_MIN sentinel and fall
    // through to is_p2p_enabled() which honours the global
    // BEACON_P2P_ACTIVATION_HEIGHT (= V13_HEIGHT in this build).
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
