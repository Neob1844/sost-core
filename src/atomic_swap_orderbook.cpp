// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// Atomic Swap — off-chain maker/taker order board (OTC-2). Pure, non-custodial,
// non-consensus. See include/sost/atomic_swap_orderbook.h.

#include "sost/atomic_swap_orderbook.h"
#include <algorithm>
#include <cctype>

namespace sost {
namespace atomic_swap {

const char* AssetName(Asset a) {
    switch (a) {
        case Asset::SOST: return "SOST";
        case Asset::BTC:  return "BTC";
        case Asset::ETH:  return "ETH";
        case Asset::BNB:  return "BNB";
        case Asset::USDT: return "USDT";
        case Asset::USDC: return "USDC";
        case Asset::PAXG: return "PAXG";
        case Asset::XAUT: return "XAUT";
    }
    return "?";
}

bool AssetParse(const std::string& s, Asset& out) {
    std::string u;
    u.reserve(s.size());
    for (char c : s) u.push_back(static_cast<char>(std::toupper((unsigned char)c)));
    if (u == "SOST") { out = Asset::SOST; return true; }
    if (u == "BTC")  { out = Asset::BTC;  return true; }
    if (u == "ETH")  { out = Asset::ETH;  return true; }
    if (u == "BNB")  { out = Asset::BNB;  return true; }
    if (u == "USDT") { out = Asset::USDT; return true; }
    if (u == "USDC") { out = Asset::USDC; return true; }
    if (u == "PAXG") { out = Asset::PAXG; return true; }
    if (u == "XAUT") { out = Asset::XAUT; return true; }
    return false;
}

bool AssetHasIssuerFreeze(Asset a) {
    // Centrally-issued tokens whose issuer can freeze/blacklist an address.
    return a == Asset::USDT || a == Asset::USDC ||
           a == Asset::PAXG || a == Asset::XAUT;
}

std::string IssuerFreezeWarning(Asset a) {
    if (!AssetHasIssuerFreeze(a)) return "";
    return std::string("ISSUER_FREEZE_RISK: ") + AssetName(a) +
           " is a centrally-issued token; its issuer can freeze or blacklist an "
           "address. HTLC atomicity is NOT guaranteed for this leg — the issuer "
           "could freeze the locked funds after the lock. Treat the swap as "
           "best-effort, not trustless, for this asset.";
}

const char* OfferStatusName(OfferStatus s) {
    switch (s) {
        case OfferStatus::Open:      return "open";
        case OfferStatus::Taken:     return "taken";
        case OfferStatus::Locked:    return "locked";
        case OfferStatus::Claimed:   return "claimed";
        case OfferStatus::Refunded:  return "refunded";
        case OfferStatus::Cancelled: return "cancelled";
        case OfferStatus::Expired:   return "expired";
    }
    return "?";
}

OfferValidation ValidateOffer(const Offer& o) {
    OfferValidation v;

    // --- structural sanity ---
    if (o.give == o.want)
        v.errors.push_back("give and want assets must differ");
    if (o.give != Asset::SOST && o.want != Asset::SOST)
        v.errors.push_back("exactly one leg must be SOST (this is a SOST atomic swap)");
    if (o.give_amount <= 0)
        v.errors.push_back("give_amount must be > 0");
    if (o.want_amount <= 0)
        v.errors.push_back("want_amount must be > 0");

    bool hashlock_zero = std::all_of(o.hashlock.begin(), o.hashlock.end(),
                                     [](uint8_t b) { return b == 0; });
    if (hashlock_zero)
        v.errors.push_back("hashlock must be a real sha256(secret), not all-zero");

    if (o.safety_margin_min_blocks < 0)
        v.errors.push_back("safety_margin_min_blocks must be >= 0");

    // --- timeout ordering (the core anti-grief rule) ---
    // The responder's refund window must open FIRST, the initiator's LAST, so
    // the responder always has time to refund before the initiator can claim
    // unilaterally. Stated as: T2 (responder) < T1 (initiator), gap >= margin.
    if (o.initiator_refund_height <= 0 || o.responder_refund_height <= 0) {
        v.errors.push_back("both refund heights must be > 0");
    } else {
        if (o.responder_refund_height >= o.initiator_refund_height) {
            v.errors.push_back(
                "TIMEOUT_ORDER_INVALID: responder_refund_height (" +
                std::to_string(o.responder_refund_height) +
                ") must be < initiator_refund_height (" +
                std::to_string(o.initiator_refund_height) +
                ") — the responder's refund must open first");
        } else {
            int64_t gap = o.initiator_refund_height - o.responder_refund_height;
            if (gap < o.safety_margin_min_blocks) {
                v.errors.push_back(
                    "TIMEOUT_ORDER_INVALID: refund gap " + std::to_string(gap) +
                    " < safety_margin_min_blocks " +
                    std::to_string(o.safety_margin_min_blocks));
            }
        }
    }

    // --- issuer-freeze honesty (warnings, not errors) ---
    if (AssetHasIssuerFreeze(o.give)) v.warnings.push_back(IssuerFreezeWarning(o.give));
    if (AssetHasIssuerFreeze(o.want)) v.warnings.push_back(IssuerFreezeWarning(o.want));

    v.ok = v.errors.empty();
    return v;
}

}  // namespace atomic_swap
}  // namespace sost
