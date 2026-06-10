// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-2 — off-chain order board tests (pure, no consensus, gate-agnostic).

#include "sost/atomic_swap_orderbook.h"
#include <array>
#include <cstdio>
#include <string>

using namespace sost;
using namespace sost::atomic_swap;

static int g_fail = 0;
#define TEST(msg, cond) do { \
    if (!(cond)) { std::printf("  FAIL: %s\n", msg); ++g_fail; } \
    else { std::printf("  ok:   %s\n", msg); } \
} while (0)

static bool HasWarningContaining(const OfferValidation& v, const char* needle) {
    for (const auto& w : v.warnings)
        if (w.find(needle) != std::string::npos) return true;
    return false;
}
static bool HasErrorContaining(const OfferValidation& v, const char* needle) {
    for (const auto& e : v.errors)
        if (e.find(needle) != std::string::npos) return true;
    return false;
}

static Offer GoodOffer() {
    Offer o;
    o.id = "swap-001";
    o.maker_role = Role::Initiator;
    o.give = Asset::SOST;
    o.want = Asset::BTC;
    o.give_amount = 1000000;
    o.want_amount = 50000;
    o.hashlock.fill(0xAB);                 // non-zero
    o.responder_refund_height = 1000;      // T2 opens first
    o.initiator_refund_height = 1020;      // T1 opens last (gap 20 >= margin 6)
    o.safety_margin_min_blocks = 6;
    return o;
}

int main() {
    std::printf("[OTC-2 orderbook]\n");

    // Asset parsing + names
    {
        Asset a;
        TEST("AssetParse btc (ci)", AssetParse("btc", a) && a == Asset::BTC);
        TEST("AssetParse USDT", AssetParse("USDT", a) && a == Asset::USDT);
        TEST("AssetParse junk fails", !AssetParse("DOGE", a));
        TEST("AssetName SOST", std::string(AssetName(Asset::SOST)) == "SOST");
    }

    // Issuer-freeze classification
    {
        TEST("USDT freezable", AssetHasIssuerFreeze(Asset::USDT));
        TEST("USDC freezable", AssetHasIssuerFreeze(Asset::USDC));
        TEST("PAXG freezable", AssetHasIssuerFreeze(Asset::PAXG));
        TEST("XAUT freezable", AssetHasIssuerFreeze(Asset::XAUT));
        TEST("BTC not freezable", !AssetHasIssuerFreeze(Asset::BTC));
        TEST("ETH not freezable", !AssetHasIssuerFreeze(Asset::ETH));
        TEST("BNB not freezable", !AssetHasIssuerFreeze(Asset::BNB));
        TEST("SOST not freezable", !AssetHasIssuerFreeze(Asset::SOST));
        TEST("issuer warning non-empty for USDT",
             !IssuerFreezeWarning(Asset::USDT).empty());
        TEST("issuer warning empty for BTC",
             IssuerFreezeWarning(Asset::BTC).empty());
    }

    // Valid offer passes
    {
        auto v = ValidateOffer(GoodOffer());
        TEST("good offer ok", v.ok && v.errors.empty());
        TEST("good offer no issuer warning (SOST/BTC)", v.warnings.empty());
    }

    // Issuer-freeze warning surfaces for USDT/USDC/PAXG/XAUT legs
    {
        for (Asset a : {Asset::USDT, Asset::USDC, Asset::PAXG, Asset::XAUT}) {
            Offer o = GoodOffer();
            o.want = a;  // SOST <-> issuer token
            auto v = ValidateOffer(o);
            std::string label = std::string("issuer warning present for ") + AssetName(a);
            TEST(label.c_str(), v.ok && HasWarningContaining(v, "ISSUER_FREEZE_RISK"));
        }
    }

    // Timeout ordering: responder must open FIRST. Reject mis-ordered.
    {
        Offer o = GoodOffer();
        o.responder_refund_height = 1020;   // equal-or-after initiator -> invalid
        o.initiator_refund_height = 1000;
        auto v = ValidateOffer(o);
        TEST("mis-ordered timeouts rejected",
             !v.ok && HasErrorContaining(v, "TIMEOUT_ORDER_INVALID"));
    }
    // Equal heights rejected
    {
        Offer o = GoodOffer();
        o.responder_refund_height = 1000;
        o.initiator_refund_height = 1000;
        auto v = ValidateOffer(o);
        TEST("equal timeouts rejected",
             !v.ok && HasErrorContaining(v, "TIMEOUT_ORDER_INVALID"));
    }
    // Gap below margin rejected
    {
        Offer o = GoodOffer();
        o.responder_refund_height = 1000;
        o.initiator_refund_height = 1003;   // gap 3 < margin 6
        o.safety_margin_min_blocks = 6;
        auto v = ValidateOffer(o);
        TEST("insufficient margin rejected",
             !v.ok && HasErrorContaining(v, "TIMEOUT_ORDER_INVALID"));
    }

    // Structural errors
    {
        Offer o = GoodOffer(); o.give = Asset::BTC; o.want = Asset::ETH;  // no SOST leg
        auto v = ValidateOffer(o);
        TEST("offer with no SOST leg rejected",
             !v.ok && HasErrorContaining(v, "one leg must be SOST"));
    }
    {
        Offer o = GoodOffer(); o.hashlock.fill(0);
        auto v = ValidateOffer(o);
        TEST("zero hashlock rejected", !v.ok && HasErrorContaining(v, "hashlock"));
    }
    {
        Offer o = GoodOffer(); o.give_amount = 0;
        auto v = ValidateOffer(o);
        TEST("zero amount rejected", !v.ok && HasErrorContaining(v, "give_amount"));
    }

    if (g_fail == 0) std::printf("ALL ORDERBOOK TESTS PASSED\n");
    else std::printf("%d ORDERBOOK TESTS FAILED\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
