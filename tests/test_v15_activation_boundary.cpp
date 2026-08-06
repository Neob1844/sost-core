// V15 mainnet activation-boundary test (P9).
// Compiled with NO SOST_DEVNET_FORKS / SOST_TESTNET_FORKS → the MAINNET profile, so it also
// proves the profile selection is not confused (V15_HEIGHT must be 25000, not 18 or 12500).
// Verifies the exact activation boundary (24998..25002) and the jackpot-first-height cadence,
// i.e. the off-by-one surface around 24999/25000/25001.
#include "sost/params.h"
#include <cstdio>
#include <cstdint>

static int fails = 0;
static void chk(bool c, const char* what) {
    std::printf("  [%s] %s\n", c ? "PASS" : "FAIL", what);
    if (!c) fails++;
}

int main() {
    using namespace sost;
    std::printf("=== V15 activation boundary (MAINNET profile) ===\n");

    // 1) Profile selection — must be MAINNET height, not DEVNET(18)/TESTNET(12500).
    chk(V15_HEIGHT == 25000, "V15_HEIGHT == 25000 (mainnet, not DEV 18 / testnet 12500)");

    // 2) The emission-transition gate is `height >= V15_HEIGHT`. Prove the exact boundary.
    chk((24998 >= V15_HEIGHT) == false, "h=24998 is PRE-V15 (>= gate false)");
    chk((24999 >= V15_HEIGHT) == false, "h=24999 is PRE-V15 (last pre-fork block)");
    chk((25000 >= V15_HEIGHT) == true,  "h=25000 is the FIRST V15 block");
    chk((25001 >= V15_HEIGHT) == true,  "h=25001 is V15");
    chk((25002 >= V15_HEIGHT) == true,  "h=25002 is V15");

    // 3) Jackpot activation is SEPARATE: first at HIST_JACKPOT_FIRST_HEIGHT (25290), then cadence.
    chk(HIST_JACKPOT_ACTIVATION_HEIGHT == V15_HEIGHT, "jackpot activation height == V15_HEIGHT");
    chk(HIST_JACKPOT_FIRST_HEIGHT == 25290, "first jackpot height == 25290 (V15 + offset 290)");
    // No jackpot anywhere in [24998, 25289] — in particular NOT at the fork block itself.
    bool none_before = true;
    for (int64_t h = 24998; h <= 25289; ++h) if (is_hist_jackpot_height(h)) none_before = false;
    chk(none_before, "NO jackpot in [24998..25289] (incl. the fork block 25000)");
    chk(is_hist_jackpot_height(25290) == true, "first jackpot at 25290");
    chk(is_hist_jackpot_height(25291) == false && is_hist_jackpot_height(25292) == false,
        "no jackpot at 25291/25292 (cadence, not every block)");
    chk(is_hist_jackpot_height(25290 + HIST_JACKPOT_CADENCE_BLOCKS) == true,
        "second jackpot at 25290 + cadence");

    // 4) Draw alignment invariant used by the schedule (first jackpot % 3 == 0).
    chk((HIST_JACKPOT_FIRST_HEIGHT % 3) == 0, "first jackpot height is DTD-draw-aligned (%3==0)");

    // 5) Coherence: V15 sits after the whole historical ladder on mainnet.
    chk(V15_HEIGHT > DTD_DOMINANCE_GATE_HEIGHT, "V15_HEIGHT > DTD dominance gate height");
    chk(HIST_JACKPOT_CAP_STOCKS >= HIST_JACKPOT_BASE_STOCKS, "jackpot cap >= base");

    std::printf("=== Summary: %s (%d failures) ===\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
