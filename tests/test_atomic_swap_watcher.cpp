// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-2 — local watcher / auto-pilot tests (pure, no consensus, gate-agnostic).

#include "sost/atomic_swap_watcher.h"
#include "sost/crypto.h"
#include <array>
#include <cstdio>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::atomic_swap;

static int g_fail = 0;
#define TEST(msg, cond) do { \
    if (!(cond)) { std::printf("  FAIL: %s\n", msg); ++g_fail; } \
    else { std::printf("  ok:   %s\n", msg); } \
} while (0)

static std::array<uint8_t, 32> MakePreimage(uint8_t fill) {
    std::array<uint8_t, 32> p{}; p.fill(fill); return p;
}

static WatchedSwap BaseSwap() {
    WatchedSwap s;
    s.swap_id = "swap-XYZ";
    s.sost_lock_txid.fill(0x11);
    s.sost_lock_vout = 2;
    s.sost_refund_height = 1000;
    s.claim_pkh.fill(0xAA);
    s.refund_pkh.fill(0xBB);
    return s;
}

int main() {
    std::printf("[OTC-2 watcher]\n");

    // ---- Refunder auto-refund timing (R24 mirror) ----
    {
        WatchedSwap s = BaseSwap();
        s.side = WatchSide::Refunder;
        TEST("refunder before timeout -> Wait",
             DecideWatchAction(s, 999, /*unspent*/ true) == WatchAction::Wait);
        TEST("refunder at timeout -> Refund",
             DecideWatchAction(s, 1000, true) == WatchAction::Refund);
        TEST("refunder after timeout -> Refund",
             DecideWatchAction(s, 1500, true) == WatchAction::Refund);
        TEST("refunder, lock already spent -> Done",
             DecideWatchAction(s, 1500, /*unspent*/ false) == WatchAction::Done);
    }

    // ---- Claimant auto-claim timing (R21/R22 mirror) ----
    {
        WatchedSwap s = BaseSwap();
        s.side = WatchSide::Claimant;
        TEST("claimant, no preimage -> Wait",
             DecideWatchAction(s, 500, true) == WatchAction::Wait);
        s.have_preimage = true;
        TEST("claimant, preimage, before timeout -> Claim",
             DecideWatchAction(s, 999, true) == WatchAction::Claim);
        TEST("claimant, preimage, at timeout -> Wait (window closed)",
             DecideWatchAction(s, 1000, true) == WatchAction::Wait);
        TEST("claimant, preimage, after timeout -> Wait",
             DecideWatchAction(s, 1500, true) == WatchAction::Wait);
        s.sost_spent = true;
        TEST("claimant, already spent -> Done",
             DecideWatchAction(s, 500, true) == WatchAction::Done);
    }

    // ---- IngestRevealedPreimage: real sha256 match / mismatch ----
    {
        auto preimage = MakePreimage(0x42);
        Bytes32 hl = sha256(preimage.data(), preimage.size());

        WatchedSwap s = BaseSwap();
        s.side = WatchSide::Claimant;
        for (int i = 0; i < 32; ++i) s.hashlock[i] = hl[i];

        auto wrong = MakePreimage(0x43);
        TEST("wrong preimage ignored", !IngestRevealedPreimage(s, wrong));
        TEST("wrong preimage left have_preimage=false", !s.have_preimage);

        TEST("correct preimage accepted", IngestRevealedPreimage(s, preimage));
        TEST("correct preimage set have_preimage", s.have_preimage);

        // Auto-claim flow: before ingest -> Wait; after ingest -> Claim.
        WatchedSwap s2 = BaseSwap();
        s2.side = WatchSide::Claimant;
        for (int i = 0; i < 32; ++i) s2.hashlock[i] = hl[i];
        TEST("claimant pre-reveal -> Wait", DecideWatchAction(s2, 500, true) == WatchAction::Wait);
        IngestRevealedPreimage(s2, preimage);
        TEST("claimant post-reveal -> Claim", DecideWatchAction(s2, 500, true) == WatchAction::Claim);
    }

    // ---- Persistence round-trip (resume after restart) ----
    {
        auto preimage = MakePreimage(0x7E);
        WatchedSwap s = BaseSwap();
        s.side = WatchSide::Claimant;
        s.hashlock.fill(0xCD);
        s.have_preimage = true;
        s.preimage = preimage;
        s.sost_spent = false;

        std::string line = SerializeWatchedSwap(s);
        WatchedSwap r;
        TEST("parse serialized swap", ParseWatchedSwap(line, r));
        TEST("round-trip swap_id", r.swap_id == s.swap_id);
        TEST("round-trip side", r.side == s.side);
        TEST("round-trip txid", r.sost_lock_txid == s.sost_lock_txid);
        TEST("round-trip vout", r.sost_lock_vout == s.sost_lock_vout);
        TEST("round-trip hashlock", r.hashlock == s.hashlock);
        TEST("round-trip refund_height", r.sost_refund_height == s.sost_refund_height);
        TEST("round-trip claim_pkh", r.claim_pkh == s.claim_pkh);
        TEST("round-trip refund_pkh", r.refund_pkh == s.refund_pkh);
        TEST("round-trip have_preimage", r.have_preimage == s.have_preimage);
        TEST("round-trip preimage", r.preimage == s.preimage);
        TEST("round-trip sost_spent", r.sost_spent == s.sost_spent);

        // The resumed watcher decides identically.
        TEST("resumed decision identical",
             DecideWatchAction(r, 500, true) == DecideWatchAction(s, 500, true));
    }

    // ---- Watchlist round-trip + malformed line rejection ----
    {
        std::vector<WatchedSwap> v;
        WatchedSwap a = BaseSwap(); a.swap_id = "a"; a.side = WatchSide::Refunder;
        WatchedSwap b = BaseSwap(); b.swap_id = "b"; b.side = WatchSide::Claimant; b.have_preimage = true;
        v.push_back(a); v.push_back(b);
        std::string text = SerializeWatchlist(v);
        std::vector<WatchedSwap> out;
        TEST("parse watchlist", ParseWatchlist(text, out) && out.size() == 2);
        TEST("watchlist order preserved", out[0].swap_id == "a" && out[1].swap_id == "b");

        std::vector<WatchedSwap> bad;
        TEST("malformed line rejected", !ParseWatchedSwap("not|enough|fields", bad.emplace_back()));
    }

    if (g_fail == 0) std::printf("ALL WATCHER TESTS PASSED\n");
    else std::printf("%d WATCHER TESTS FAILED\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
