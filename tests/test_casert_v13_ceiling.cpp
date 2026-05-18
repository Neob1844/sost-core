// V13 cASERT profile-ceiling tests.
//
// V13 hard fork (block V13_HEIGHT = 12000):
//   Hard profile ceiling rises from H20 → H35. The full 43-profile
//   range E7..H35 becomes active and the previously reserved
//   H21..H35 stop being rejected by the validator + controller.
//
// The cASERT controller cascade (effective_profile_ceiling_at) and
// the validator's gate (validator_profile_ceiling_at) are both
// expected to honour the new ceiling exactly at the V13_HEIGHT
// boundary. Pre-V13 behaviour must be bit-identical.
//
// We exercise the ceiling at the boundary itself (V13_HEIGHT-1 vs
// V13_HEIGHT) and at heights 11999 / 12000 / 12001 as the prompt
// requires. We use the helpers directly (validator_profile_ceiling_at
// / effective_profile_ceiling_at) so the test does not depend on
// linking the node binary.

#include "sost/params.h"
#include "sost/types.h"
#include <cstdio>
#include <cstdlib>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Same gate the validator runs in sost-node.cpp:
//   declared_pi within [CASERT_H_MIN, validator_profile_ceiling_at(h)]
static bool profile_accepted(int64_t height, int32_t declared_pi) {
    if (declared_pi < CASERT_H_MIN || declared_pi > CASERT_H_MAX) return false;
    int32_t max_profile = validator_profile_ceiling_at(height);
    return declared_pi <= max_profile;
}

static void test_validator_ceiling_at_boundary() {
    printf("\n=== V13 validator profile-ceiling gate (height boundary) ===\n");

    // Pre-V13 (V12 era) ceiling = H20.
    TEST("V13_HEIGHT-1 (=11999): declared_pi=20 → ACCEPT (V12 ceiling)",
         profile_accepted(V13_HEIGHT - 1, 20));
    TEST("V13_HEIGHT-1 (=11999): declared_pi=21 → REJECT (H21 reserved pre-V13)",
         !profile_accepted(V13_HEIGHT - 1, 21));
    TEST("V13_HEIGHT-1 (=11999): declared_pi=35 → REJECT (H35 reserved pre-V13)",
         !profile_accepted(V13_HEIGHT - 1, 35));

    // V13 boundary — H35 ceiling activates exactly at V13_HEIGHT.
    TEST("V13_HEIGHT (=12000): declared_pi=20 → ACCEPT (still within ceiling)",
         profile_accepted(V13_HEIGHT, 20));
    TEST("V13_HEIGHT (=12000): declared_pi=21 → ACCEPT (H21 active at V13)",
         profile_accepted(V13_HEIGHT, 21));
    TEST("V13_HEIGHT (=12000): declared_pi=35 → ACCEPT (top of H35 ceiling at V13)",
         profile_accepted(V13_HEIGHT, 35));
    TEST("V13_HEIGHT (=12000): declared_pi=36 → REJECT (CASERT_H_MAX is 35)",
         !profile_accepted(V13_HEIGHT, 36));

    // V13+ — every active profile must remain accepted.
    TEST("V13_HEIGHT+1 (=12001): declared_pi=35 → ACCEPT",
         profile_accepted(V13_HEIGHT + 1, 35));
    TEST("V13_HEIGHT+1 (=12001): declared_pi=21 → ACCEPT",
         profile_accepted(V13_HEIGHT + 1, 21));
    TEST("V13_HEIGHT+1 (=12001): declared_pi=0 (B0) → ACCEPT",
         profile_accepted(V13_HEIGHT + 1, 0));

    // Easing side — must still accept all valid easing profiles at V13.
    TEST("V13+: declared_pi=-7 (E7, floor) → ACCEPT",
         profile_accepted(V13_HEIGHT, CASERT_H_MIN));
    TEST("V13+: declared_pi=-8 → REJECT (below CASERT_H_MIN)",
         !profile_accepted(V13_HEIGHT, CASERT_H_MIN - 1));

    // Pre-V13 behaviour bit-identical to the V12 era.
    TEST("V12_HEIGHT (=7350): declared_pi=20 → ACCEPT (V12 ceiling unchanged)",
         profile_accepted(V12_HEIGHT, 20));
    TEST("V12_HEIGHT (=7350): declared_pi=21 → REJECT (still reserved pre-V13)",
         !profile_accepted(V12_HEIGHT, 21));
}

static void test_validator_helper_returns() {
    printf("\n=== validator_profile_ceiling_at() returns ===\n");
    TEST("h=0          → PRE_V12 (13)",
         validator_profile_ceiling_at(0) == CASERT_MAX_ACTIVE_PROFILE_PRE_V12);
    TEST("h=V12_HEIGHT-1 → PRE_V12 (13)",
         validator_profile_ceiling_at(V12_HEIGHT - 1) ==
             CASERT_MAX_ACTIVE_PROFILE_PRE_V12);
    TEST("h=V12_HEIGHT  → V12 (20)",
         validator_profile_ceiling_at(V12_HEIGHT) ==
             CASERT_MAX_ACTIVE_PROFILE_V12);
    TEST("h=V13_HEIGHT-1 → V12 (20)",
         validator_profile_ceiling_at(V13_HEIGHT - 1) ==
             CASERT_MAX_ACTIVE_PROFILE_V12);
    TEST("h=V13_HEIGHT  → V13 (35)",
         validator_profile_ceiling_at(V13_HEIGHT) ==
             CASERT_MAX_ACTIVE_PROFILE_V13);
    TEST("h=V13_HEIGHT+1 → V13 (35)",
         validator_profile_ceiling_at(V13_HEIGHT + 1) ==
             CASERT_MAX_ACTIVE_PROFILE_V13);
    TEST("h=100000      → V13 (35)",
         validator_profile_ceiling_at(100000) ==
             CASERT_MAX_ACTIVE_PROFILE_V13);
}

static void test_controller_helper_returns() {
    printf("\n=== effective_profile_ceiling_at() returns ===\n");
    TEST("h=0                            → H10 floor",
         effective_profile_ceiling_at(0) == CASERT_HARD_PROFILE_CEILING);
    TEST("h=CASERT_CEILING_H11_HEIGHT    → H11",
         effective_profile_ceiling_at(CASERT_CEILING_H11_HEIGHT) ==
             CASERT_HARD_PROFILE_CEILING_H11);
    TEST("h=CASERT_CEILING_H12_HEIGHT    → H12",
         effective_profile_ceiling_at(CASERT_CEILING_H12_HEIGHT) ==
             CASERT_HARD_PROFILE_CEILING_H12);
    TEST("h=CASERT_CEILING_H13_HEIGHT    → H13",
         effective_profile_ceiling_at(CASERT_CEILING_H13_HEIGHT) ==
             CASERT_HARD_PROFILE_CEILING_H13);
    TEST("h=V12_HEIGHT-1                  → H13 (still pre-V12)",
         effective_profile_ceiling_at(V12_HEIGHT - 1) ==
             CASERT_HARD_PROFILE_CEILING_H13);
    TEST("h=V12_HEIGHT                    → H20 (V12)",
         effective_profile_ceiling_at(V12_HEIGHT) ==
             CASERT_MAX_ACTIVE_PROFILE_V12);
    TEST("h=V13_HEIGHT-1                  → H20 (still V12)",
         effective_profile_ceiling_at(V13_HEIGHT - 1) ==
             CASERT_MAX_ACTIVE_PROFILE_V12);
    TEST("h=V13_HEIGHT                    → H35 (V13)",
         effective_profile_ceiling_at(V13_HEIGHT) ==
             CASERT_MAX_ACTIVE_PROFILE_V13);
    TEST("h=V13_HEIGHT+1                  → H35 (V13)",
         effective_profile_ceiling_at(V13_HEIGHT + 1) ==
             CASERT_MAX_ACTIVE_PROFILE_V13);
}

static void test_constants_have_expected_values() {
    printf("\n=== V13 ceiling constants ===\n");
    TEST("CASERT_MAX_ACTIVE_PROFILE_V13 == 35",
         CASERT_MAX_ACTIVE_PROFILE_V13 == 35);
    TEST("CASERT_MAX_ACTIVE_PROFILE_V13 == CASERT_H_MAX",
         CASERT_MAX_ACTIVE_PROFILE_V13 == CASERT_H_MAX);
    TEST("V13_HEIGHT == 12000",
         V13_HEIGHT == 12000);
    TEST("V12_HEIGHT < V13_HEIGHT (forks ordered)",
         V12_HEIGHT < V13_HEIGHT);
}

int main() {
    printf("\n=== V13 cASERT ceiling tests ===\n");
    printf("V12_HEIGHT                       = %lld\n", (long long)V12_HEIGHT);
    printf("V13_HEIGHT                       = %lld\n", (long long)V13_HEIGHT);
    printf("CASERT_MAX_ACTIVE_PROFILE_PRE_V12 = %d\n",
           CASERT_MAX_ACTIVE_PROFILE_PRE_V12);
    printf("CASERT_MAX_ACTIVE_PROFILE_V12     = %d\n",
           CASERT_MAX_ACTIVE_PROFILE_V12);
    printf("CASERT_MAX_ACTIVE_PROFILE_V13     = %d\n",
           CASERT_MAX_ACTIVE_PROFILE_V13);
    printf("CASERT_H_MIN (E7 floor)           = %d\n", CASERT_H_MIN);
    printf("CASERT_H_MAX (H35 cap)            = %d\n", CASERT_H_MAX);

    test_constants_have_expected_values();
    test_validator_helper_returns();
    test_controller_helper_returns();
    test_validator_ceiling_at_boundary();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
