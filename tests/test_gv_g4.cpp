// test_gv_g4.cpp — V14 Gold Vault G4 (67-block miner signaling) pure tally.
#include "sost/gv_g4.h"
#include <cstdio>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(name,cond) do{ if(cond){++g_pass; std::printf("  ok  %s\n",name);} \
  else{++g_fail; std::printf("  *** FAIL: %s\n",name);} }while(0)

int main() {
    std::printf("=== Gold Vault G4 — 67-block signaling tally ===\n");

    // Parameters
    CHECK("window == 67", GV_G4_SIGNAL_WINDOW == 67);
    CHECK("threshold == 90%", GV_G4_THRESHOLD_PCT == 90);
    CHECK("approval floor == 61 (ceil 67*90/100)", gv_g4_approval_floor() == 61);
    CHECK("foundation weight == 7 (ceil 67*10/100)", gv_g4_foundation_weight() == 7);

    // Pure miner approval (no boost)
    CHECK("61/67 yes -> approved",            gv_g4_window_approved(61, false) == true);
    CHECK("67/67 yes -> approved",            gv_g4_window_approved(67, false) == true);
    CHECK("60/67 yes -> rejected",            gv_g4_window_approved(60, false) == false);
    CHECK("0/67 yes -> rejected",             gv_g4_window_approved(0, false) == false);

    // Foundation +10% quality boost (adds 7 effective yes)
    CHECK("54 yes + boost (=61) -> approved", gv_g4_window_approved(54, true) == true);
    CHECK("53 yes + boost (=60) -> rejected", gv_g4_window_approved(53, true) == false);
    CHECK("effective yes capped at window",   gv_g4_effective_yes(67, true) == 67);

    // Defensive bounds
    CHECK("negative yes -> rejected",         gv_g4_window_approved(-1, false) == false);
    CHECK("yes > window -> rejected",         gv_g4_window_approved(68, false) == false);

    // Coinbase approval marker (the signaling channel)
    {
        Transaction cb_yes; TxOutput m; m.amount=0; m.pubkey_hash=GV_G4_APPROVAL_PKH; cb_yes.outputs.push_back(m);
        CHECK("coinbase with 0-value marker approves", gv_g4_coinbase_approves(cb_yes)==true);
        Transaction cb_no;  TxOutput n; n.amount=50; cb_no.outputs.push_back(n);
        CHECK("coinbase without marker does not",       gv_g4_coinbase_approves(cb_no)==false);
        Transaction cb_paid; TxOutput p; p.amount=100; p.pubkey_hash=GV_G4_APPROVAL_PKH; cb_paid.outputs.push_back(p);
        CHECK("nonzero-value to marker pkh does NOT count", gv_g4_coinbase_approves(cb_paid)==false);
    }

    // Activation gate (G4 is part of the V15 automation bundle)
#ifdef SOST_TESTNET_FORKS
    CHECK("testnet: active at V15_HEIGHT",     gv_g4_active_at(V15_HEIGHT) == true);
    CHECK("testnet: inactive before V15",      gv_g4_active_at(V15_HEIGHT-1) == false);
#else
    CHECK("mainnet: deferred at 15000 (V14)",  gv_g4_active_at(15000) == false);
    CHECK("mainnet: deferred at 20000 (V15)",  gv_g4_active_at(20000) == false);
    CHECK("mainnet: deferred at INT64_MAX-1",  gv_g4_active_at(INT64_MAX-1) == false);
#endif

    // W3 — window counting [h-67, h-1], current h excluded, no off-by-one.
    {
        const int64_t H = 10000;
        // all 67 preceding blocks approve, the current one also "approves"
        CHECK("count: all preceding approve -> 67",
              gv_g4_count_window(H, [](int64_t){ return true; }) == 67);
        // none approve -> 0
        CHECK("count: none approve -> 0",
              gv_g4_count_window(H, [](int64_t){ return false; }) == 0);
        // only the current height h approves -> NOT counted (window is preceding only)
        CHECK("count: current h not counted",
              gv_g4_count_window(H, [H](int64_t hh){ return hh == H; }) == 0);
        // boundaries: h-1 counts, h-67 counts, h-68 does NOT (outside window)
        CHECK("count: h-1 inside window",
              gv_g4_count_window(H, [H](int64_t hh){ return hh == H-1; }) == 1);
        CHECK("count: h-67 inside window",
              gv_g4_count_window(H, [H](int64_t hh){ return hh == H-GV_G4_SIGNAL_WINDOW; }) == 1);
        CHECK("count: h-68 outside window",
              gv_g4_count_window(H, [H](int64_t hh){ return hh == H-GV_G4_SIGNAL_WINDOW-1; }) == 0);
        // exactly 61 of the 67 approve -> approved; 60 -> rejected (no off-by-one)
        int32_t c61 = gv_g4_count_window(H, [H](int64_t hh){ return hh <= H-1 && hh >= H-61; });
        int32_t c60 = gv_g4_count_window(H, [H](int64_t hh){ return hh <= H-1 && hh >= H-60; });
        CHECK("count: 61 preceding -> 61 and approved", c61==61 && gv_g4_window_approved(c61,false));
        CHECK("count: 60 preceding -> 60 and rejected", c60==60 && !gv_g4_window_approved(c60,false));
        // near genesis: negative heights skipped, no crash
        CHECK("count: near genesis (h=3) skips negative heights",
              gv_g4_count_window(3, [](int64_t){ return true; }) == 3);
    }

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
