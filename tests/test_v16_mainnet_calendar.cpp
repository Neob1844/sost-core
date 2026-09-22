// =============================================================================
// test_v16_mainnet_calendar.cpp — the published V16 calendar, asserted against
// the constants the mainnet binary is actually compiled with.
//
// Every devnet harness runs with the activation heights moved down so a chain
// can cross them in minutes. That is exactly why none of them can catch a
// mistake in the REAL numbers. This test does nothing else: it pins the dates
// the announcement, the operator guide and the explorer all promise —
//
//     #29,898  last DTD Jackpot under V15 rules
//     #29,999  last block under V15 DTD-normal eligibility
//     #30,000  V16 activates (jackpot V2 + DTD-normal re-pointed)
//     #30,186  first DTD Jackpot V2
//     #31,338  heartbeat rule reaches its permanent 3-of-4
//
// — so that moving a constant without moving the documentation fails the build
// pipeline instead of surprising miners on the day.
//
// Under a devnet/testnet build the heights are deliberately different; the test
// says so and passes, rather than asserting numbers it knows are not in play.
// =============================================================================
#include "sost/params.h"
#include "sost/jackpot_v2.h"

#include <cstdio>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { if (cond) { printf("  PASS: %s\n", msg); ++g_pass; } \
    else { printf("  *** FAIL: %s [%s:%d]\n", msg, __FILE__, __LINE__); ++g_fail; } } while (0)

int main() {
#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS) || defined(SOST_DEVNET_V2_FIRST_JACKPOT)
    printf("=== V16 mainnet calendar ===\n");
    printf("  SKIPPED: this build moves the activation heights on purpose\n");
    printf("           (V16=%lld, first jackpot=%lld, cadence=%lld)\n",
           (long long)HIST_JACKPOT_V2_HEIGHT, (long long)HIST_JACKPOT_FIRST_HEIGHT,
           (long long)HIST_JACKPOT_CADENCE_BLOCKS);
    return 0;
#else
    printf("=== V16 mainnet calendar ===\n");

    // ---- the activation height itself ----------------------------------
    TEST("V16 activates at #30,000", HIST_JACKPOT_V2_HEIGHT == 30000);
    TEST("DTD-normal eligibility changes at the SAME height",
         DTD_V16_ELIGIBILITY_HEIGHT == HIST_JACKPOT_V2_HEIGHT);
    TEST("jackpot cadence is 288", HIST_JACKPOT_CADENCE_BLOCKS == 288);
    TEST("node epoch == jackpot cadence", NODE_EPOCH_LENGTH == 288);

    // ---- the last V15 jackpot and the first V2 one ----------------------
    int64_t last_v15 = -1, first_v2 = -1;
    for (int64_t h = 29000; h < 31000; ++h) {
        if (!is_hist_jackpot_height(h)) continue;
        if (h < HIST_JACKPOT_V2_HEIGHT) last_v15 = h;
        else if (first_v2 < 0) first_v2 = h;
    }
    printf("  (computed: last V15 jackpot #%lld, first V2 jackpot #%lld)\n",
           (long long)last_v15, (long long)first_v2);
    TEST("last jackpot under V15 rules is #29,898", last_v15 == 29898);
    TEST("first DTD Jackpot V2 is #30,186", first_v2 == 30186);
    TEST("they are one cadence apart", first_v2 - last_v15 == HIST_JACKPOT_CADENCE_BLOCKS);
    TEST("#30,000 is NOT itself a jackpot height", !is_hist_jackpot_height(30000));
    TEST("the first V2 jackpot is a DTD draw block", first_v2 % 3 == 0);

    // ---- which rule set applies on each side of the line ---------------
    TEST("#29,999 is still V15 for the jackpot", !is_hist_jackpot_v2_height(29999));
    TEST("#30,186 is a V2 jackpot", is_hist_jackpot_v2_height(30186));
    TEST("#29,898 is a jackpot but NOT a V2 one",
         is_hist_jackpot_height(29898) && !is_hist_jackpot_v2_height(29898));

    // ---- DTD-normal recency across the boundary ------------------------
    TEST("#29,999 keeps the V15 recency window",
         dtd_recency_window_at(29999) == DTD_RECENCY_WINDOW);
    TEST("#29,898 (a V15 jackpot height) keeps the 20,000 window",
         dtd_recency_window_at(29898) == DTD_JACKPOT_RECENCY_WINDOW);
    TEST("#30,000 switches to 288", dtd_recency_window_at(30000) == 288);
    TEST("#30,186 uses 288 too — no special jackpot window any more",
         dtd_recency_window_at(30186) == 288);
    TEST("the V16 window constant is 288", DTD_RECENCY_WINDOW_V16 == 288);

    // ---- jackpot V2 weighting window -----------------------------------
    TEST("PoW window is 2,016 blocks", JACKPOT_V2_POW_WINDOW == 2016);
    TEST("minimum is 3 blocks in that window", JACKPOT_V2_MIN_BLOCKS == 3);
    TEST("the first V2 jackpot's PoW window starts inside V15 territory",
         30186 - JACKPOT_V2_POW_WINDOW == 28170);

    // ---- the heartbeat ramp, epoch by epoch ----------------------------
    // A = activation, L = epoch length. Epoch 0 is [30,000 .. 30,287], so the
    // first V2 jackpot (#30,186) sits INSIDE epoch 0 — no epoch has completed
    // yet and the rule cannot demand a heartbeat that could not exist.
    const int64_t A = HIST_JACKPOT_V2_HEIGHT, L = NODE_EPOCH_LENGTH;
    TEST("#30,186 falls in epoch 0", jackpot_v2::jv2_epoch_of_height(A, L, 30186) == 0);
    TEST("no epoch has completed before #30,186",
         jackpot_v2::jv2_completed_epochs_before(A, L, 30186) == 0);
    TEST("so the first V2 jackpot requires 0 heartbeats (bind only)",
         jackpot_v2::jv2_heartbeat_required(0) == 0);

    struct { int64_t completed, required, window; } ramp[] = {
        {0, 0, 0}, {1, 1, 1}, {2, 2, 2}, {3, 3, 3}, {4, 3, 4}, {9, 3, 4},
    };
    bool ramp_ok = true;
    for (const auto& r : ramp) {
        if (jackpot_v2::jv2_heartbeat_required(r.completed) != r.required ||
            jackpot_v2::jv2_heartbeat_window(r.completed) != r.window) {
            printf("    completed=%lld -> required=%lld/%lld window=%lld/%lld\n",
                   (long long)r.completed,
                   (long long)jackpot_v2::jv2_heartbeat_required(r.completed), (long long)r.required,
                   (long long)jackpot_v2::jv2_heartbeat_window(r.completed), (long long)r.window);
            ramp_ok = false;
        }
    }
    TEST("the ramp is 0/0 -> 1/1 -> 2/2 -> 3/3 -> 3/4 and stays there", ramp_ok);

    // The permanent 3-of-4 rule starts at the first height whose completed-epoch
    // count is 4, i.e. the start of epoch 4: 30,000 + 4*288 = 31,152. The
    // published guide names #31,338 — the first JACKPOT height at/after that,
    // which is what a miner actually experiences. Both are asserted so neither
    // number can drift away from the other.
    const int64_t epoch4_start = A + 4 * L;
    TEST("epoch 4 starts at #31,152", epoch4_start == 31152);
    TEST("3-of-4 is in force from epoch 4 on",
         jackpot_v2::jv2_heartbeat_required(jackpot_v2::jv2_completed_epochs_before(A, L, epoch4_start)) == 3 &&
         jackpot_v2::jv2_heartbeat_window(jackpot_v2::jv2_completed_epochs_before(A, L, epoch4_start)) == 4);
    int64_t first_jackpot_under_3of4 = -1;
    for (int64_t h = epoch4_start; h < epoch4_start + 2 * 288; ++h) {
        if (is_hist_jackpot_height(h)) { first_jackpot_under_3of4 = h; break; }
    }
    printf("  (computed: first jackpot judged under 3-of-4 = #%lld)\n",
           (long long)first_jackpot_under_3of4);
    TEST("the published #31,338 is that jackpot", first_jackpot_under_3of4 == 31338);

    // ---- the four jackpots of the first month --------------------------
    int64_t js[4] = {0,0,0,0}; int n = 0;
    for (int64_t h = HIST_JACKPOT_V2_HEIGHT; h < HIST_JACKPOT_V2_HEIGHT + 1300 && n < 4; ++h)
        if (is_hist_jackpot_height(h)) js[n++] = h;
    TEST("the first four V2 jackpots are 30,186 / 30,474 / 30,762 / 31,050",
         js[0] == 30186 && js[1] == 30474 && js[2] == 30762 && js[3] == 31050);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
#endif
}
