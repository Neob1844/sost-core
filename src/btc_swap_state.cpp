// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// btc_swap_state.cpp — BTC HTLC swap state machine + persistable record.
// Pure, non-consensus, no libwally, no network. See the header for the
// idempotency / double-spend-guard contract.

#include "sost/btc_swap_state.h"
#include "sost/crypto.h"   // sha256 for preimage verification

#include <array>
#include <cctype>
#include <cstdio>
#include <sstream>

namespace sost {
namespace atomic_swap {
namespace btc {

const char* BtcSwapStateName(BtcSwapState s) {
    switch (s) {
        case BtcSwapState::Created:          return "Created";
        case BtcSwapState::FundingBroadcast: return "FundingBroadcast";
        case BtcSwapState::Locked:           return "Locked";
        case BtcSwapState::Redeemable:       return "Redeemable";
        case BtcSwapState::Redeeming:        return "Redeeming";
        case BtcSwapState::Redeemed:         return "Redeemed";
        case BtcSwapState::Refundable:       return "Refundable";
        case BtcSwapState::Refunding:        return "Refunding";
        case BtcSwapState::Refunded:         return "Refunded";
        case BtcSwapState::Failed:           return "Failed";
    }
    return "?";
}

bool IsBtcSwapTerminal(BtcSwapState s) {
    return s == BtcSwapState::Redeemed || s == BtcSwapState::Refunded ||
           s == BtcSwapState::Failed;
}

const char* BtcSwapEventName(BtcSwapEvent e) {
    switch (e) {
        case BtcSwapEvent::FundingBroadcast: return "FundingBroadcast";
        case BtcSwapEvent::FundingConfirmed: return "FundingConfirmed";
        case BtcSwapEvent::BecameRedeemable: return "BecameRedeemable";
        case BtcSwapEvent::ClaimBroadcast:   return "ClaimBroadcast";
        case BtcSwapEvent::ClaimConfirmed:   return "ClaimConfirmed";
        case BtcSwapEvent::BecameRefundable: return "BecameRefundable";
        case BtcSwapEvent::RefundBroadcast:  return "RefundBroadcast";
        case BtcSwapEvent::RefundConfirmed:  return "RefundConfirmed";
        case BtcSwapEvent::Fail:             return "Fail";
    }
    return "?";
}

const char* BtcPartyName(BtcParty p) {
    return p == BtcParty::Claimant ? "Claimant" : "Funder";
}

// --------------------------------------------------------------------------
// Transition table
// --------------------------------------------------------------------------

static bool in(BtcSwapState s, std::initializer_list<BtcSwapState> set) {
    for (auto x : set) if (x == s) return true;
    return false;
}

static BtcTransition advance(BtcSwapRecord& r, BtcSwapState target,
                             std::initializer_list<BtcSwapState> from,
                             std::initializer_list<BtcSwapState> already) {
    BtcTransition t;
    if (in(r.state, from))         { r.state = target; t.ok = true; t.changed = true; return t; }
    if (in(r.state, already))      { t.ok = true; t.changed = false; return t; }  // idempotent no-op
    t.ok = false;
    t.error = std::string("illegal transition to ") + BtcSwapStateName(target) +
              " from " + BtcSwapStateName(r.state);
    return t;
}

BtcTransition ApplyBtcSwapEvent(BtcSwapRecord& r, BtcSwapEvent e) {
    using S = BtcSwapState;
    switch (e) {
        case BtcSwapEvent::FundingBroadcast:
            return advance(r, S::FundingBroadcast, {S::Created},
                           {S::FundingBroadcast, S::Locked, S::Redeemable, S::Redeeming,
                            S::Redeemed, S::Refundable, S::Refunding, S::Refunded});
        case BtcSwapEvent::FundingConfirmed:
            return advance(r, S::Locked, {S::FundingBroadcast},
                           {S::Locked, S::Redeemable, S::Redeeming, S::Redeemed,
                            S::Refundable, S::Refunding, S::Refunded});
        case BtcSwapEvent::BecameRedeemable:
            return advance(r, S::Redeemable, {S::Locked},
                           {S::Redeemable, S::Redeeming, S::Redeemed});
        case BtcSwapEvent::ClaimBroadcast:
            return advance(r, S::Redeeming, {S::Redeemable},
                           {S::Redeeming, S::Redeemed});
        case BtcSwapEvent::ClaimConfirmed:
            return advance(r, S::Redeemed, {S::Redeeming}, {S::Redeemed});
        case BtcSwapEvent::BecameRefundable:
            return advance(r, S::Refundable, {S::Locked},
                           {S::Refundable, S::Refunding, S::Refunded});
        case BtcSwapEvent::RefundBroadcast:
            return advance(r, S::Refunding, {S::Refundable},
                           {S::Refunding, S::Refunded});
        case BtcSwapEvent::RefundConfirmed:
            return advance(r, S::Refunded, {S::Refunding}, {S::Refunded});
        case BtcSwapEvent::Fail: {
            BtcTransition t;
            if (r.state == S::Failed) { t.ok = true; t.changed = false; return t; }
            if (IsBtcSwapTerminal(r.state)) {
                t.ok = false;
                t.error = std::string("cannot Fail a completed swap in state ") +
                          BtcSwapStateName(r.state);
                return t;
            }
            r.state = S::Failed; t.ok = true; t.changed = true; return t;
        }
    }
    BtcTransition bad; bad.error = "unknown event"; return bad;
}

// --------------------------------------------------------------------------
// Preimage ingest
// --------------------------------------------------------------------------

static bool hex_to_bytes(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2 != 0) return false;
    out.resize(hex.size() / 2);
    for (size_t i = 0; i < out.size(); ++i) {
        auto hv = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        };
        int hi = hv(hex[i*2]), lo = hv(hex[i*2+1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

static std::string bytes_to_hex(const uint8_t* p, size_t n) {
    static const char* H = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s.push_back(H[p[i] >> 4]); s.push_back(H[p[i] & 0xF]); }
    return s;
}

bool IngestBtcPreimage(BtcSwapRecord& r, const std::string& preimage_hex) {
    std::vector<uint8_t> pre;
    if (!hex_to_bytes(preimage_hex, pre) || pre.size() != 32) return false;
    Bytes32 h = sha256(pre.data(), pre.size());
    std::string computed = bytes_to_hex(h.data(), h.size());
    // compare case-insensitively to the stored hashlock hex
    std::string want = r.hashlock_hex;
    for (auto& c : want) c = (char)std::tolower((unsigned char)c);
    if (computed != want) return false;
    r.have_preimage = true;
    r.preimage_hex = preimage_hex;
    return true;
}

// --------------------------------------------------------------------------
// Serialization — "k=v;k=v;..." one record per line.
// Values are hex / integers / enum names: none contain ';' or '='.
// --------------------------------------------------------------------------

static BtcParty parse_party(const std::string& s) {
    return s == "Claimant" ? BtcParty::Claimant : BtcParty::Funder;
}
static BtcSwapState parse_state(const std::string& s) {
    for (int i = 0; i <= (int)BtcSwapState::Failed; ++i) {
        auto st = (BtcSwapState)i;
        if (s == BtcSwapStateName(st)) return st;
    }
    return BtcSwapState::Created;
}

std::string SerializeBtcSwapRecord(const BtcSwapRecord& r) {
    std::ostringstream o;
    o << "id=" << r.swap_id
      << ";party=" << BtcPartyName(r.party)
      << ";net=" << r.network
      << ";hashlock=" << r.hashlock_hex
      << ";redeem=" << r.redeem_script_hex
      << ";addr=" << r.htlc_address
      << ";amt=" << r.lock_amount_sats
      << ";refh=" << r.refund_height
      << ";claimdest=" << r.claim_dest_addr
      << ";refunddest=" << r.refund_dest_addr
      << ";fee=" << r.fee_sats
      << ";ftxid=" << r.funding_txid
      << ";fvout=" << r.funding_vout
      << ";claimtxid=" << r.claim_txid
      << ";refundtxid=" << r.refund_txid
      << ";conf=" << r.last_confirmations
      << ";havepre=" << (r.have_preimage ? 1 : 0)
      << ";pre=" << r.preimage_hex
      << ";state=" << BtcSwapStateName(r.state);
    return o.str();
}

bool ParseBtcSwapRecord(const std::string& line, BtcSwapRecord& out) {
    if (line.empty()) return false;
    BtcSwapRecord r;
    std::istringstream ss(line);
    std::string kv;
    bool saw_id = false;
    while (std::getline(ss, kv, ';')) {
        auto eq = kv.find('=');
        if (eq == std::string::npos) continue;
        std::string k = kv.substr(0, eq);
        std::string v = kv.substr(eq + 1);
        if      (k == "id")         { r.swap_id = v; saw_id = true; }
        else if (k == "party")      r.party = parse_party(v);
        else if (k == "net")        r.network = v;
        else if (k == "hashlock")   r.hashlock_hex = v;
        else if (k == "redeem")     r.redeem_script_hex = v;
        else if (k == "addr")       r.htlc_address = v;
        else if (k == "amt")        r.lock_amount_sats = std::atoll(v.c_str());
        else if (k == "refh")       r.refund_height = std::atoll(v.c_str());
        else if (k == "claimdest")  r.claim_dest_addr = v;
        else if (k == "refunddest") r.refund_dest_addr = v;
        else if (k == "fee")        r.fee_sats = std::atoll(v.c_str());
        else if (k == "ftxid")      r.funding_txid = v;
        else if (k == "fvout")      r.funding_vout = (uint32_t)std::atoll(v.c_str());
        else if (k == "claimtxid")  r.claim_txid = v;
        else if (k == "refundtxid") r.refund_txid = v;
        else if (k == "conf")       r.last_confirmations = std::atoll(v.c_str());
        else if (k == "havepre")    r.have_preimage = (v == "1");
        else if (k == "pre")        r.preimage_hex = v;
        else if (k == "state")      r.state = parse_state(v);
    }
    if (!saw_id) return false;
    out = r;
    return true;
}

std::string SerializeBtcSwapList(const std::vector<BtcSwapRecord>& v) {
    std::string s;
    for (const auto& r : v) { s += SerializeBtcSwapRecord(r); s += "\n"; }
    return s;
}

bool ParseBtcSwapList(const std::string& text, std::vector<BtcSwapRecord>& out) {
    out.clear();
    std::istringstream ss(text);
    std::string line;
    while (std::getline(ss, line)) {
        if (line.empty()) continue;
        BtcSwapRecord r;
        if (ParseBtcSwapRecord(line, r)) out.push_back(r);
    }
    return true;
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
