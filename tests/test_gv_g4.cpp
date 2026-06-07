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

    // Activation gate
#ifdef SOST_TESTNET_FORKS
    CHECK("testnet: active at V14_HEIGHT",    gv_g4_active_at(V14_HEIGHT) == true);
#else
    CHECK("mainnet: deferred at 15000",       gv_g4_active_at(15000) == false);
    CHECK("mainnet: deferred at INT64_MAX-1", gv_g4_active_at(INT64_MAX-1) == false);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
