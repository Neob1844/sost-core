// V12 cASERT profile-ceiling and triangular-cascade tests.
//
// V12 hard fork (block V12_HEIGHT = 7350):
//   1. Hard profile ceiling rises from H13 → H20.
//      H21..H35 stay reserved (the lag-based controller will not climb
//      past H20, and the validator rejects a declared profile_index above
//      the active ceiling).
//   2. Triangular cascade max steps rise from 6 → 7 so the cascade still
//      reaches the E7 floor (CASERT_H_MIN = -7) from the new H20 ceiling
//      within the 900 s anti-stall window:
//         H20 - drop(7) = 20 - 28 = -8  → clamped to E7
//      Pre-V12 (cap = 6) keeps reaching E7 from H13 within 840 s:
//         H13 - drop(6) = 13 - 21 = -8  → clamped to E7
//
// The tests exercise:
//   - profile-index ceiling acceptance/rejection at heights straddling
//     V12_HEIGHT, with profile_index values 13/14/20/21,
//   - the triangular cascade reaching E7 from H20 within 900 s post-V12,
//   - the legacy cascade reaching E7 from H13 within 840 s pre-V12.
//
// We exercise the ceiling at the boundary itself (V12_HEIGHT-1 vs
// V12_HEIGHT) rather than going through the full sost-node block-
// validation pipeline; the rule under test is the casert.cpp ceiling
// constant gate, which is the same source of truth used by the node.

#include "sost/pow/casert.h"
#include "sost/params.h"
#include "sost/types.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// =============================================================================
// Profile-ceiling acceptance gate.
//
// The validator (sost-node.cpp) rejects a block whose declared profile_index
// exceeds the active ceiling for that height:
//   pre-V12:  CASERT_MAX_ACTIVE_PROFILE_PRE_V12 = 13
//   V12+:     CASERT_MAX_ACTIVE_PROFILE_V12     = 20
// We implement the same gate here as a pure helper so the test does not
// depend on linking the node binary.
// =============================================================================
static bool profile_accepted(int64_t height, int32_t declared_pi) {
    if (declared_pi < CASERT_H_MIN || declared_pi > CASERT_H_MAX) return false;
    int32_t max_profile = (height >= V12_HEIGHT)
        ? CASERT_MAX_ACTIVE_PROFILE_V12
        : CASERT_MAX_ACTIVE_PROFILE_PRE_V12;
    return declared_pi <= max_profile;
}

static void test_profile_ceiling() {
    printf("\n=== V12 profile-ceiling gate (declared_pi vs height) ===\n");

    // Pre-V12 height — H13 ceiling.
    TEST("pre-V12 (height=7000): declared_pi=13 → ACCEPT",
         profile_accepted(7000, 13));
    TEST("pre-V12 (height=7000): declared_pi=14 → REJECT",
         !profile_accepted(7000, 14));
    TEST("pre-V12 (height=7000): declared_pi=20 → REJECT",
         !profile_accepted(7000, 20));

    // Boundary just below V12 — still pre-V12 ceiling.
    TEST("V12_HEIGHT-1 (=7349): declared_pi=13 → ACCEPT",
         profile_accepted(V12_HEIGHT - 1, 13));
    TEST("V12_HEIGHT-1 (=7349): declared_pi=14 → REJECT",
         !profile_accepted(V12_HEIGHT - 1, 14));

    // V12 boundary — H20 ceiling activates exactly at V12_HEIGHT.
    TEST("V12_HEIGHT (=7350): declared_pi=14 → ACCEPT (post-V12 ceiling H20)",
         profile_accepted(V12_HEIGHT, 14));
    TEST("V12_HEIGHT (=7350): declared_pi=13 → ACCEPT",
         profile_accepted(V12_HEIGHT, 13));
    TEST("V12_HEIGHT (=7350): declared_pi=20 → ACCEPT (top of H20 ceiling)",
         profile_accepted(V12_HEIGHT, 20));
    TEST("V12_HEIGHT (=7350): declared_pi=21 → REJECT (H21 reserved)",
         !profile_accepted(V12_HEIGHT, 21));

    // V12+ — H21..H35 stay reserved.
    TEST("V12+ (height=8000): declared_pi=20 → ACCEPT",
         profile_accepted(8000, 20));
    TEST("V12+ (height=8000): declared_pi=21 → REJECT",
         !profile_accepted(8000, 21));
    TEST("V12+ (height=8000): declared_pi=35 → REJECT (CASERT_H_MAX but reserved)",
         !profile_accepted(8000, 35));

    // Easing side — must still accept all valid easing profiles.
    TEST("V12+: declared_pi=0 (B0) → ACCEPT",
         profile_accepted(V12_HEIGHT, 0));
    TEST("V12+: declared_pi=-7 (E7, floor) → ACCEPT",
         profile_accepted(V12_HEIGHT, CASERT_H_MIN));
    TEST("V12+: declared_pi=-8 → REJECT (below CASERT_H_MIN)",
         !profile_accepted(V12_HEIGHT, CASERT_H_MIN - 1));
}

// =============================================================================
// Cascade reach.
//
// We do NOT go through casert_compute() here (that depends on full chain
// state, lag, anti-stall, etc.). Instead we exercise the canonical
// triangular-cascade helper directly — same one casert_compute calls under
// the hood — and verify the drop magnitude is sufficient to push the base
// profile to E7 within the documented window.
// =============================================================================
static void test_cascade_reach_v12_h20() {
    printf("\n=== V12 cascade — base H20 reaches E7 within 900 s ===\n");

    // Strategy: walk elapsed seconds 540 → 900 in 60 s steps, compute drop,
    // assert that at elapsed=900 the drop is large enough that base_H=20
    // is pushed below CASERT_H_MIN.
    const int32_t base_H = CASERT_MAX_ACTIVE_PROFILE_V12; // 20

    // Step-by-step audit (informational).
    for (int64_t elapsed = 540; elapsed <= 960; elapsed += 60) {
        int32_t drop = compute_v11_cascade_drop_triangular_h(elapsed, V12_HEIGHT);
        int32_t profile = base_H - drop;
        if (profile < CASERT_H_MIN) profile = CASERT_H_MIN;
        printf("  V12 elapsed=%4llds  drop=%2d  H=%d\n",
               (long long)elapsed, drop, profile);
    }

    // 540 s — first step.
    int32_t d540 = compute_v11_cascade_drop_triangular_h(540, V12_HEIGHT);
    TEST("elapsed=540 → drop = 1 (n=1, T(1)=1)", d540 == 1);

    // 720 s — at this point cascade alone has dropped the cap-7 sequence
    // to T(4)=10 (n = 1 + (720-540)/60 = 4). H20 - 10 = H10. Not yet E7.
    int32_t d720 = compute_v11_cascade_drop_triangular_h(720, V12_HEIGHT);
    TEST("elapsed=720 → drop = 10 (T(4))", d720 == 10);
    TEST("elapsed=720 from H20 → still above E7 (cascade not yet at floor)",
         (base_H - d720) > CASERT_H_MIN);

    // 900 s — cap-7 sequence: n = clamp(1 + (900-540)/60 = 7, 7) = 7,
    // drop = T(7) = 28. H20 - 28 = -8 → clamped to E7.
    int32_t d900 = compute_v11_cascade_drop_triangular_h(900, V12_HEIGHT);
    TEST("elapsed=900 → drop = 28 (T(7), 7-step cap)", d900 == 28);
    int32_t prof900 = base_H - d900;
    if (prof900 < CASERT_H_MIN) prof900 = CASERT_H_MIN;
    TEST("V12: H20 + elapsed=900 → effective profile = E7",
         prof900 == CASERT_H_MIN);

    // > 900 s — cascade is capped at 7 steps, drop stays 28, profile stays E7.
    int32_t d960 = compute_v11_cascade_drop_triangular_h(960, V12_HEIGHT);
    TEST("elapsed=960 → drop stays 28 (cap-7 holds)", d960 == 28);
    int32_t d1500 = compute_v11_cascade_drop_triangular_h(1500, V12_HEIGHT);
    TEST("elapsed=1500 → drop stays 28 (cap-7 holds)", d1500 == 28);
}

static void test_cascade_reach_legacy_h13() {
    printf("\n=== Legacy cascade — base H13 reaches E7 within 840 s ===\n");

    // Pre-V12 path: max_steps = 6.
    const int32_t base_H = CASERT_MAX_ACTIVE_PROFILE_PRE_V12; // 13
    const int64_t pre_height = V12_HEIGHT - 1;                // 7349

    for (int64_t elapsed = 540; elapsed <= 900; elapsed += 60) {
        int32_t drop = compute_v11_cascade_drop_triangular_h(elapsed, pre_height);
        int32_t profile = base_H - drop;
        if (profile < CASERT_H_MIN) profile = CASERT_H_MIN;
        printf("  pre-V12 elapsed=%4llds  drop=%2d  H=%d\n",
               (long long)elapsed, drop, profile);
    }

    int32_t d540 = compute_v11_cascade_drop_triangular_h(540, pre_height);
    TEST("legacy elapsed=540 → drop = 1", d540 == 1);

    // 840 s — cap-6: n = 1 + (840-540)/60 = 6, T(6) = 21.
    int32_t d840 = compute_v11_cascade_drop_triangular_h(840, pre_height);
    TEST("legacy elapsed=840 → drop = 21 (T(6), 6-step cap)", d840 == 21);
    int32_t prof840 = base_H - d840;
    if (prof840 < CASERT_H_MIN) prof840 = CASERT_H_MIN;
    TEST("legacy: H13 + elapsed=840 → effective profile = E7",
         prof840 == CASERT_H_MIN);

    // Cap holds past 840 s.
    int32_t d900 = compute_v11_cascade_drop_triangular_h(900, pre_height);
    TEST("legacy elapsed=900 → drop stays 21 (cap-6 holds)", d900 == 21);
    int32_t d1500 = compute_v11_cascade_drop_triangular_h(1500, pre_height);
    TEST("legacy elapsed=1500 → drop stays 21 (cap-6 holds)", d1500 == 21);
}

// =============================================================================
// Cascade-cap boundary — pre-V12 vs V12 must produce different drops only
// at elapsed >= 900 (where cap-6 holds at 21 but cap-7 grows to 28). For
// elapsed < 900 the values are identical.
// =============================================================================
static void test_cascade_cap_boundary() {
    printf("\n=== V12 cascade-cap boundary (pre-V12 vs V12 drops) ===\n");

    for (int64_t elapsed = 540; elapsed < 900; elapsed += 60) {
        int32_t legacy = compute_v11_cascade_drop_triangular_h(elapsed, V12_HEIGHT - 1);
        int32_t v12    = compute_v11_cascade_drop_triangular_h(elapsed, V12_HEIGHT);
        char msg[160];
        std::snprintf(msg, sizeof(msg),
                      "elapsed=%llds → legacy(%d) == v12(%d) (caps not yet active)",
                      (long long)elapsed, legacy, v12);
        TEST(msg, legacy == v12);
    }

    // 900 s and beyond: legacy cap=6 (drop=21), v12 cap=7 (drop=28).
    {
        int32_t legacy = compute_v11_cascade_drop_triangular_h(900, V12_HEIGHT - 1);
        int32_t v12    = compute_v11_cascade_drop_triangular_h(900, V12_HEIGHT);
        TEST("elapsed=900 → legacy=21 (cap-6)", legacy == 21);
        TEST("elapsed=900 → v12=28 (cap-7)", v12 == 28);
    }
}

int main() {
    printf("\n=== V12 cASERT ceiling + cascade tests ===\n");
    printf("V12_HEIGHT                       = %lld\n", (long long)V12_HEIGHT);
    printf("CASERT_MAX_ACTIVE_PROFILE_PRE_V12 = %d\n", CASERT_MAX_ACTIVE_PROFILE_PRE_V12);
    printf("CASERT_MAX_ACTIVE_PROFILE_V12     = %d\n", CASERT_MAX_ACTIVE_PROFILE_V12);
    printf("TRIANGULAR_MAX_STEPS_PRE_V12      = %d\n", CASERT_TRIANGULAR_MAX_STEPS_PRE_V12);
    printf("TRIANGULAR_MAX_STEPS_V12          = %d\n", CASERT_TRIANGULAR_MAX_STEPS_V12);
    printf("CASERT_H_MIN (E7 floor)           = %d\n", CASERT_H_MIN);

    test_profile_ceiling();
    test_cascade_reach_v12_h20();
    test_cascade_reach_legacy_h13();
    test_cascade_cap_boundary();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
