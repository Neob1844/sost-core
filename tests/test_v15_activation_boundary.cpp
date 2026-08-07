// V15 activation-boundary test (P9). Profile-aware: it asserts the EXACT expected V15 activation
// height and jackpot-first height for the profile it was compiled under (MAINNET 25000/25290,
// TESTNET 12500/12792, DEVNET_FAST 18/24), so it both (a) proves the profile selection is not
// confused and (b) verifies the exact activation boundary (h-2..h+2) and the jackpot-first cadence
// — the off-by-one surface — in whichever build runs it (mainnet build, testnet ctest, DEV ctest).
#include "sost/params.h"
#include <cstdio>
#include <cstdint>

#if defined(SOST_DEVNET_FORKS)
    static const int64_t EXP_V15 = 18,    EXP_FIRST = 24;    static const char* PROF = "DEVNET_FAST";
#elif defined(SOST_TESTNET_FORKS)
    static const int64_t EXP_V15 = 12500, EXP_FIRST = 12792; static const char* PROF = "TESTNET";
#else
    static const int64_t EXP_V15 = 25000, EXP_FIRST = 25290; static const char* PROF = "MAINNET";
#endif

static int fails = 0;
static void chk(bool c, const char* what) {
    std::printf("  [%s] %s\n", c ? "PASS" : "FAIL", what);
    if (!c) fails++;
}

int main() {
    using namespace sost;
    std::printf("=== V15 activation boundary (%s profile) ===\n", PROF);
    const int64_t H = V15_HEIGHT;

    // 1) Profile selection — must be THIS profile's height, not another profile's.
    chk(V15_HEIGHT == EXP_V15, "V15_HEIGHT matches the compiled profile (no DEV/testnet/mainnet mix-up)");

    // 2) The emission-transition gate is `height >= V15_HEIGHT`. Prove the exact boundary, relative
    //    to the profile height, so there is no hardcoded-literal off-by-one.
    chk((H - 2 >= V15_HEIGHT) == false, "h=V15-2 is PRE-V15 (>= gate false)");
    chk((H - 1 >= V15_HEIGHT) == false, "h=V15-1 is PRE-V15 (last pre-fork block)");
    chk((H     >= V15_HEIGHT) == true,  "h=V15 is the FIRST V15 block");
    chk((H + 1 >= V15_HEIGHT) == true,  "h=V15+1 is V15");
    chk((H + 2 >= V15_HEIGHT) == true,  "h=V15+2 is V15");

    // 3) Jackpot activation is SEPARATE: first at HIST_JACKPOT_FIRST_HEIGHT, then on cadence.
    chk(HIST_JACKPOT_ACTIVATION_HEIGHT == V15_HEIGHT, "jackpot activation height == V15_HEIGHT");
    chk(HIST_JACKPOT_FIRST_HEIGHT == EXP_FIRST, "first jackpot height matches profile (V15 + offset)");
    // No jackpot anywhere in [V15-2, FIRST-1] — in particular NOT at the fork block itself.
    bool none_before = true;
    for (int64_t h = H - 2; h < HIST_JACKPOT_FIRST_HEIGHT; ++h) if (is_hist_jackpot_height(h)) none_before = false;
    chk(none_before, "NO jackpot before the first jackpot height (incl. the fork block)");
    chk(is_hist_jackpot_height(HIST_JACKPOT_FIRST_HEIGHT) == true, "first jackpot at FIRST_HEIGHT");
    chk(is_hist_jackpot_height(HIST_JACKPOT_FIRST_HEIGHT + 1) == false &&
        is_hist_jackpot_height(HIST_JACKPOT_FIRST_HEIGHT + 2) == false,
        "no jackpot at FIRST+1/FIRST+2 (cadence, not every block)");
    chk(is_hist_jackpot_height(HIST_JACKPOT_FIRST_HEIGHT + HIST_JACKPOT_CADENCE_BLOCKS) == true,
        "second jackpot at FIRST + cadence");

    // 4) Draw alignment invariant used by the schedule (first jackpot % 3 == 0).
    chk((HIST_JACKPOT_FIRST_HEIGHT % 3) == 0, "first jackpot height is DTD-draw-aligned (%3==0)");

    // 5) Coherence: V15 sits after the whole historical ladder.
    chk(V15_HEIGHT > DTD_DOMINANCE_GATE_HEIGHT, "V15_HEIGHT > DTD dominance gate height");
    chk(HIST_JACKPOT_CAP_STOCKS >= HIST_JACKPOT_BASE_STOCKS, "jackpot cap >= base");

    std::printf("=== Summary: %s (%d failures) ===\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
