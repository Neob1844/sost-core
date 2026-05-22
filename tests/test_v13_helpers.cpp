// V13 fork helpers — boundary tests.
//
// V13 hard fork lives at block V13_HEIGHT = 12 000 and gates three changes:
//   - LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW  5 → 6
//   - MAX_FUTURE_DRIFT_STAGED                 60 s → 30 s
//   - Beacon Phase II-A activation
//
// This test pins:
//   1. The activation height itself (12 000).
//   2. The two height-gated helpers introduced for the wire-up:
//        lottery_exclusion_window_at(h)
//        max_future_drift_at(h)
//      at the boundary heights h = 11999 (pre-V13) and h = 12000 (post-V13),
//      and at sentinel heights well outside the fork window.
//   3. The Beacon activation gate constants:
//        BEACON_PHASE2A_ACTIVATION_HEIGHT == V13_HEIGHT
//        BEACON_P2P_ACTIVATION_HEIGHT     == V13_HEIGHT  (active at V13)
//
// The asserts are pure compile-time `static_assert` where possible so any
// drift on these constants surfaces at build time, and runtime TEST() entries
// for completeness when a future change makes a value non-constexpr.
//
// IMPORTANT: this test does NOT exercise consensus call sites. It only
// pins the helpers themselves. Wire-up commits (lottery cooldown 6,
// drift 30s) ship their own end-to-end boundary tests over the actual
// validator paths.

#include "sost/params.h"
#include <cstdio>
#include <cstdint>
#include <climits>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Compile-time pins. If any of these break, the file does not compile.
// ---------------------------------------------------------------------------

static_assert(V13_HEIGHT == 12000,
              "V13_HEIGHT moved away from 12000 — re-audit before changing.");

static_assert(BEACON_PHASE2A_ACTIVATION_HEIGHT == V13_HEIGHT,
              "Beacon Phase II-A must activate at exactly V13_HEIGHT.");

static_assert(BEACON_P2P_ACTIVATION_HEIGHT == V13_HEIGHT,
              "Beacon Phase III P2P activates at V13_HEIGHT. "
              "Pre-V13 the dispatcher returns DiscardDormant; at/after "
              "V13_HEIGHT the full advisory pipeline (size/parse/sig/network/"
              "expiry/dedup/rate-limit) runs. Change requires a fork plan.");

// Boundary at the activation height.
static_assert(lottery_exclusion_window_at(11999) == 5,
              "Pre-V13 lottery exclusion window must remain 5.");
static_assert(lottery_exclusion_window_at(12000) == 6,
              "From V13_HEIGHT, lottery exclusion window must be 6.");
static_assert(lottery_exclusion_window_at(12001) == 6,
              "Post-V13 lottery exclusion window must stay 6.");
static_assert(lottery_exclusion_window_at(0) == 5,
              "Genesis-region heights must use the pre-V13 window.");
static_assert(lottery_exclusion_window_at(INT64_MAX) == 6,
              "Far-future heights must use the post-V13 window.");

static_assert(max_future_drift_at(11999) == 60,
              "Pre-V13 staged-relief drift cap must remain 60 seconds.");
static_assert(max_future_drift_at(12000) == 30,
              "From V13_HEIGHT, future-drift cap must be 30 seconds.");
static_assert(max_future_drift_at(12001) == 30,
              "Post-V13 future-drift cap must stay 30 seconds.");
static_assert(max_future_drift_at(0) == 600,
              "Genesis-region heights must use the legacy 600 s drift cap "
              "(pre-staged-relief regime).");
static_assert(max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT - 1) == 600,
              "Just-pre-staged heights must still use the 600 s legacy cap.");
static_assert(max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT) == 60,
              "Staged-relief activation must drop the cap to 60 s.");
static_assert(max_future_drift_at(INT64_MAX) == 30,
              "Far-future heights must use the post-V13 drift cap.");

// Pre-V13 must remain bit-identical to the pre-fork constants. If a
// regression silently changes the underlying constant, this catches it.
static_assert(lottery_exclusion_window_at(V13_HEIGHT - 1)
                == LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW,
              "Pre-V13 helper output must equal the existing constant.");
static_assert(max_future_drift_at(V13_HEIGHT - 1)
                == MAX_FUTURE_DRIFT_STAGED,
              "Pre-V13 helper output must equal the existing constant.");

// Sanity on the underlying constants — these are the "if you change me you
// also break the V13 helpers" anchors.
static_assert(LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5,
              "LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW must remain 5 pre-V13.");
static_assert(MAX_FUTURE_DRIFT_STAGED == 60,
              "MAX_FUTURE_DRIFT_STAGED must remain 60 seconds pre-V13.");

// ---------------------------------------------------------------------------
// Runtime mirror of the same checks. Redundant against the static_asserts
// above; included so a future change that drops `constexpr` from a helper
// still has a working test instead of silently degrading to "no asserts".
// ---------------------------------------------------------------------------

static void test_v13_height_anchor() {
    printf("\n=== V13_HEIGHT anchor ===\n");
    TEST("V13_HEIGHT == 12000", V13_HEIGHT == 12000);
    TEST("BEACON_PHASE2A_ACTIVATION_HEIGHT == V13_HEIGHT",
         BEACON_PHASE2A_ACTIVATION_HEIGHT == V13_HEIGHT);
    TEST("BEACON_P2P_ACTIVATION_HEIGHT == V13_HEIGHT (active at V13)",
         BEACON_P2P_ACTIVATION_HEIGHT == V13_HEIGHT);
}

static void test_lottery_window_boundary() {
    printf("\n=== lottery_exclusion_window_at — boundary ===\n");
    TEST("h=11999 → 5 (pre-V13)",         lottery_exclusion_window_at(11999) == 5);
    TEST("h=12000 → 6 (post-V13)",        lottery_exclusion_window_at(12000) == 6);
    TEST("h=12001 → 6 (post-V13 stays)",  lottery_exclusion_window_at(12001) == 6);
    TEST("h=0 → 5 (genesis region)",      lottery_exclusion_window_at(0) == 5);
    TEST("h=INT64_MAX → 6 (far future)",  lottery_exclusion_window_at(INT64_MAX) == 6);
    TEST("h=V13_HEIGHT-1 returns LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW",
         lottery_exclusion_window_at(V13_HEIGHT - 1)
             == LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW);
}

static void test_future_drift_boundary() {
    printf("\n=== max_future_drift_at — boundary ===\n");
    // V13 boundary
    TEST("h=11999 → 60 (pre-V13, staged regime)",
         max_future_drift_at(11999) == 60);
    TEST("h=12000 → 30 (post-V13)",
         max_future_drift_at(12000) == 30);
    TEST("h=12001 → 30 (post-V13 stays)",
         max_future_drift_at(12001) == 30);
    // Staged-relief boundary (preserved unchanged across V13 commit)
    TEST("h=0 → 600 (genesis, pre-staged-relief, legacy cap)",
         max_future_drift_at(0) == 600);
    TEST("h=CASERT_STAGED_RELIEF_HEIGHT-1 → 600 (just before staged)",
         max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT - 1) == 600);
    TEST("h=CASERT_STAGED_RELIEF_HEIGHT → 60 (staged tightening kicks in)",
         max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT) == 60);
    // Sentinel
    TEST("h=INT64_MAX → 30 (far future)",
         max_future_drift_at(INT64_MAX) == 30);
    // Pre-V13 helper output equals the underlying constant for the
    // height region the production validator actually uses.
    TEST("h=V13_HEIGHT-1 returns MAX_FUTURE_DRIFT_STAGED",
         max_future_drift_at(V13_HEIGHT - 1) == MAX_FUTURE_DRIFT_STAGED);
    TEST("h=CASERT_STAGED_RELIEF_HEIGHT-1 returns MAX_FUTURE_DRIFT",
         max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT - 1) == MAX_FUTURE_DRIFT);
}

static void test_pre_fork_anchors() {
    printf("\n=== Pre-V13 anchors (must not drift silently) ===\n");
    TEST("LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5",
         LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5);
    TEST("MAX_FUTURE_DRIFT_STAGED == 60",
         MAX_FUTURE_DRIFT_STAGED == 60);
    // V13_HEIGHT must be strictly above every other named fork height in
    // params.h — V13 is the most recent fork. The list below should grow
    // each time a new fork lands; treat any future failure here as a
    // signal that V13_HEIGHT was set incorrectly.
    TEST("V13_HEIGHT > V12_HEIGHT",                V13_HEIGHT > V12_HEIGHT);
    TEST("V13_HEIGHT > V11_PHASE2_HEIGHT",         V13_HEIGHT > V11_PHASE2_HEIGHT);
    TEST("V13_HEIGHT > CASERT_V11_HEIGHT",         V13_HEIGHT > CASERT_V11_HEIGHT);
    TEST("V13_HEIGHT > CASERT_STAGED_RELIEF_HEIGHT",
         V13_HEIGHT > CASERT_STAGED_RELIEF_HEIGHT);
    TEST("V13_HEIGHT > TIMESTAMP_MTP_FORK_HEIGHT",
         V13_HEIGHT > TIMESTAMP_MTP_FORK_HEIGHT);
}

int main() {
    printf("\n=== V13 fork helpers — boundary tests ===\n");
    printf("V13_HEIGHT                         = %lld\n", (long long)V13_HEIGHT);
    printf("BEACON_PHASE2A_ACTIVATION_HEIGHT   = %lld\n",
           (long long)BEACON_PHASE2A_ACTIVATION_HEIGHT);
    printf("BEACON_P2P_ACTIVATION_HEIGHT       = %lld  (V13_HEIGHT = active at V13)\n",
           (long long)BEACON_P2P_ACTIVATION_HEIGHT);
    printf("LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW = %d\n",
           (int)LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW);
    printf("MAX_FUTURE_DRIFT_STAGED            = %lld\n",
           (long long)MAX_FUTURE_DRIFT_STAGED);

    test_v13_height_anchor();
    test_lottery_window_boundary();
    test_future_drift_boundary();
    test_pre_fork_anchors();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
