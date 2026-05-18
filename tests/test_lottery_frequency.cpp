// V11 Phase 2 — lottery frequency tests (Commit 5 scope).
//
// Exercises sost::lottery::is_lottery_block — the height-only,
// height-anchored trigger rule. Pure function, no chain state, no
// Schnorr dependency (this test file is built unconditionally,
// regardless of -DSOST_ENABLE_PHASE2_SBPOW).
//
// Production schedule verified: V11_PHASE2_HEIGHT == 7100 (set by C13).
// is_lottery_block returns false for every chain height < 7100 and
// follows the documented 2-of-3 / 1-of-3 schedule for height >= 7100.
// Section 7 below pins both the dormant range and the active boundary.
// The INT64_MAX sentinel remains a test-only value used to exercise
// the "never trigger" fallback.

#include "sost/lottery.h"
#include "sost/params.h"

#include <cstdio>
#include <cstring>
#include <climits>
#include <string>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// 1 — INT64_MAX sentinel: ALWAYS returns false (production guarantee).
// ---------------------------------------------------------------------------
static void test_int64_max_sentinel_always_false() {
    printf("\n=== 1) phase2_height == INT64_MAX → never trigger ===\n");
    const int64_t SENTINEL = INT64_MAX;
    TEST("height=0, INT64_MAX → false",
         !is_lottery_block(0, SENTINEL));
    TEST("height=7000 (post-Phase 1), INT64_MAX → false",
         !is_lottery_block(7000, SENTINEL));
    TEST("height=7'100, INT64_MAX → false",
         !is_lottery_block(7100, SENTINEL));
    TEST("height=1'000'000, INT64_MAX → false",
         !is_lottery_block(1000000, SENTINEL));
    TEST("height=INT64_MAX-1, INT64_MAX → false",
         !is_lottery_block(INT64_MAX - 1, SENTINEL));
}

// ---------------------------------------------------------------------------
// 2 — Pre-Phase 2: height < phase2_height → false regardless of mod-3
// ---------------------------------------------------------------------------
static void test_pre_phase2_returns_false() {
    printf("\n=== 2) pre-Phase 2 (height < phase2_height) → false ===\n");
    const int64_t H = 1'000'000;
    TEST("height=H-1 → false (pre-Phase 2)",
         !is_lottery_block(H - 1, H));
    TEST("height=0 → false (way pre-Phase 2)",
         !is_lottery_block(0, H));
    TEST("height=H-2 → false even though height%3==1",
         !is_lottery_block(H - 2, H));   // bootstrap rule would say true if it applied
}

// ---------------------------------------------------------------------------
// 3 — Bootstrap window (first 5000 blocks): height % 3 != 0 → triggered
// ---------------------------------------------------------------------------
static void test_bootstrap_window() {
    printf("\n=== 3) Bootstrap window: 2-of-3 by height%%3 ===\n");
    // Pick a phase2_height that is itself ≡ 0 (mod 3) so the schedule
    // pattern is clean to read at a glance.
    const int64_t H = 1'000'002;  // 1'000'002 % 3 == 0
    TEST("phase2_height H itself: H%3==0 → false",
         !is_lottery_block(H, H));
    TEST("H+1: (H+1)%3==1 → true",
         is_lottery_block(H + 1, H));
    TEST("H+2: (H+2)%3==2 → true",
         is_lottery_block(H + 2, H));
    TEST("H+3: (H+3)%3==0 → false",
         !is_lottery_block(H + 3, H));
    TEST("H+4: (H+4)%3==1 → true",
         is_lottery_block(H + 4, H));
    TEST("H+5: (H+5)%3==2 → true",
         is_lottery_block(H + 5, H));
    TEST("H+6: (H+6)%3==0 → false",
         !is_lottery_block(H + 6, H));

    // 2-of-3 ratio sanity over a longer stretch (1500 blocks inside bootstrap).
    int triggered = 0;
    for (int i = 0; i < 1500; ++i) {
        if (is_lottery_block(H + i, H)) triggered++;
    }
    // 1500 blocks / 3 = 500 blocks where height%3==0 → 1000 triggered (2/3).
    TEST("1500-block bootstrap stretch → exactly 1000 triggered (2/3)",
         triggered == 1000);
}

// ---------------------------------------------------------------------------
// 4 — Boundary at offset = LOTTERY_HIGH_FREQ_WINDOW (= 5000)
//     offset = 4999 → still bootstrap (2-of-3)
//     offset = 5000 → permanent (1-of-3)
// ---------------------------------------------------------------------------
static void test_window_boundary() {
    printf("\n=== 4) Boundary at offset=LOTTERY_HIGH_FREQ_WINDOW (5000) ===\n");
    const int64_t H = 1'000'002;  // H % 3 == 0
    const int64_t W = LOTTERY_HIGH_FREQ_WINDOW;
    TEST("LOTTERY_HIGH_FREQ_WINDOW == 5000",
         W == 5000);

    // offset = 4999 → still in bootstrap. (H+4999) % 3:
    //   H % 3 = 0; 4999 % 3 = 1; sum = 1 → triggered (bootstrap rule)
    TEST("offset=4999 (last bootstrap block, height%3==1) → true (bootstrap)",
         is_lottery_block(H + 4999, H));

    // offset = 5000 → permanent rule. (H+5000) % 3:
    //   0 + (5000 % 3 = 2) = 2 → permanent rule says (height%3)==0 →
    //   false (NOT triggered).
    TEST("offset=5000 (first permanent block, height%3==2) → false (permanent)",
         !is_lottery_block(H + 5000, H));

    // Force one block where bootstrap would say "trigger" but permanent
    // would say "no trigger" to prove the rule actually switched.
    // Pick H=1'000'001 (H % 3 == 2). Then:
    //   offset=4999: (H+4999) % 3 = (2 + 1) % 3 = 0 → bootstrap says false
    //   offset=5000: (H+5000) % 3 = (2 + 2) % 3 = 1 → permanent says false
    //   offset=4998: (H+4998) % 3 = (2 + 0) % 3 = 2 → bootstrap says true
    //   offset=5001: (H+5001) % 3 = (2 + 0) % 3 = 2 → permanent says false
    {
        const int64_t H2 = 1'000'001;
        TEST("H2: offset=4998, height%3==2 → true (bootstrap)",
             is_lottery_block(H2 + 4998, H2));
        TEST("H2: offset=5001, height%3==2 → false (permanent rule flipped)",
             !is_lottery_block(H2 + 5001, H2));
    }
}

// ---------------------------------------------------------------------------
// 5 — Permanent (post-window): height % 3 == 0 → triggered
// ---------------------------------------------------------------------------
static void test_permanent_window() {
    printf("\n=== 5) Permanent window: 1-of-3 by height%%3 ===\n");
    const int64_t H = 1'000'002;  // H % 3 == 0
    const int64_t base = H + LOTTERY_HIGH_FREQ_WINDOW;  // first permanent block

    // 6000 blocks well inside permanent. Of those, ~2000 should trigger.
    int triggered = 0;
    for (int i = 0; i < 6000; ++i) {
        if (is_lottery_block(base + i, H)) triggered++;
    }
    TEST("6000-block permanent stretch → exactly 2000 triggered (1/3)",
         triggered == 2000);

    // Spot checks. base % 3 = 0+(5000%3=2) = 2.
    TEST("permanent: height%3==2 → false",
         !is_lottery_block(base, H));        // 2 → false
    TEST("permanent: height%3==0 → true",
         is_lottery_block(base + 1, H));     // (2+1)%3=0 → true
    TEST("permanent: height%3==1 → false",
         !is_lottery_block(base + 2, H));    // (2+2)%3=1 → false
    TEST("permanent: height%3==2 → false again",
         !is_lottery_block(base + 3, H));    // (2+3)%3=2 → false
}

// ---------------------------------------------------------------------------
// 6 — Constants pinned at expected values.
// ---------------------------------------------------------------------------
static void test_constants_pinned() {
    printf("\n=== 6) Constants pinned ===\n");
    TEST("LOTTERY_HIGH_FREQ_WINDOW == 5000",
         LOTTERY_HIGH_FREQ_WINDOW == 5000);
    TEST("LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5",
         LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5);
    TEST("LOTTERY_RNG_DOMAIN == \"SOST_LOTTERY_V11\"",
         std::string(LOTTERY_RNG_DOMAIN) == "SOST_LOTTERY_V11");
    TEST("LOTTERY_RNG_DOMAIN_LEN == strlen of constant",
         LOTTERY_RNG_DOMAIN_LEN == std::strlen(LOTTERY_RNG_DOMAIN));
    TEST("V11_PHASE2_HEIGHT == 7100 (set by C13)",
         V11_PHASE2_HEIGHT == 7100);
}

// ---------------------------------------------------------------------------
// 7 — Production schedule with V11_PHASE2_HEIGHT from params.h (= 7100).
//     Every chain height < 7100 returns false; from 7100 onwards the
//     2-of-3 (bootstrap) and 1-of-3 (permanent) schedules apply.
//
//     Modular arithmetic reference (verified):
//       7098 = 3 × 2366            → 7098 % 3 = 0
//       7099 % 3 = 1   7100 % 3 = 2   7101 % 3 = 0   7102 % 3 = 1
//       12099 = 7100 + 4999, 12099 = 3 × 4033 → 12099 % 3 = 0
//       12100 % 3 = 1   12101 % 3 = 2   12102 % 3 = 0
// ---------------------------------------------------------------------------
static void test_production_schedule() {
    printf("\n=== 7) Production schedule with V11_PHASE2_HEIGHT (= 7100) ===\n");

    // Pre-activation heights: ALL must be false (height < V11_PHASE2_HEIGHT).
    const int64_t pre_heights[] = {
        0, 1, 1450, 5000, 6700, 7000, 7001, 7050, 7098, 7099
    };
    for (int64_t h : pre_heights) {
        char buf[96];
        std::snprintf(buf, sizeof(buf),
                      "pre-activation height=%lld → false",
                      (long long)h);
        TEST(buf, !is_lottery_block(h, V11_PHASE2_HEIGHT));
    }

    // Boundary at activation (bootstrap rule: triggered ⟺ h%3 != 0):
    //   height=7099: pre-activation → false.
    //   height=7100: 7100 % 3 = 2 → bootstrap (h%3)!=0 → true.
    //   height=7101: 7101 % 3 = 0 → bootstrap → false.
    //   height=7102: 7102 % 3 = 1 → bootstrap → true.
    TEST("pre-boundary height=7099 (height < phase2) → false",
         !is_lottery_block(7099, V11_PHASE2_HEIGHT));
    TEST("activation height=7100 (bootstrap, 7100%3==2) → true",
         is_lottery_block(7100, V11_PHASE2_HEIGHT));
    TEST("activation height=7101 (bootstrap, 7101%3==0) → false",
         !is_lottery_block(7101, V11_PHASE2_HEIGHT));
    TEST("activation height=7102 (bootstrap, 7102%3==1) → true",
         is_lottery_block(7102, V11_PHASE2_HEIGHT));

    // Last block of the high-freq window: offset = 4999 → bootstrap.
    //   height=12099: 12099 % 3 = 0 → bootstrap (h%3)!=0 → false.
    TEST("last bootstrap block height=12099 (offset=4999, 12099%3==0) → false",
         !is_lottery_block(12099, V11_PHASE2_HEIGHT));

    // First block of the permanent window: offset = 5000 → 1-of-3.
    //   height=12100: 12100 % 3 = 1 → permanent (h%3)==0 → false.
    //   height=12101: 12101 % 3 = 2 → permanent → false.
    //   height=12102: 12102 % 3 = 0 → permanent → true.
    //   height=12103: 12103 % 3 = 1 → permanent → false.
    TEST("first permanent block height=12100 (offset=5000, 12100%3==1) → false",
         !is_lottery_block(12100, V11_PHASE2_HEIGHT));
    TEST("permanent height=12101 (h%3==2) → false",
         !is_lottery_block(12101, V11_PHASE2_HEIGHT));
    TEST("permanent height=12102 (h%3==0) → true (first permanent triggered)",
         is_lottery_block(12102, V11_PHASE2_HEIGHT));
    TEST("permanent height=12103 (h%3==1) → false",
         !is_lottery_block(12103, V11_PHASE2_HEIGHT));

    // Long-range spot checks deep in the permanent window.
    //   height=50001: 50001 = 3*16667 → %3==0 → permanent triggered.
    //   height=50002: %3==1 → false.
    TEST("permanent height=50001 (h%3==0) → true",
         is_lottery_block(50001, V11_PHASE2_HEIGHT));
    TEST("permanent height=50002 (h%3==1) → false",
         !is_lottery_block(50002, V11_PHASE2_HEIGHT));
}

// ---------------------------------------------------------------------------
// 8 — DTD flip contiguity 12095..12110 (single contiguous sweep across
//     the V11 Phase 2 cadence boundary at block 12,100).
//
//     This section visualises the 2-of-3 -> 1-of-3 transition in a
//     16-block window straddling the boundary. The pattern is
//     deterministic from V11_PHASE2_HEIGHT = 7100 +
//     LOTTERY_HIGH_FREQ_WINDOW = 5000 = 12100. Bootstrap branch:
//     triggered iff (h % 3) != 0. Permanent branch: triggered iff
//     (h % 3) == 0. The boundary at h=12100 silently switches the
//     branch without any restart, RPC call, or operator action.
// ---------------------------------------------------------------------------
static void test_dtd_flip_contiguity_12095_12110() {
    printf("\n=== 8) DTD flip contiguity 12095..12110 (single sweep) ===\n");

    struct Row {
        int64_t     h;
        bool        expected;
        const char* phase;
    };
    const Row rows[] = {
        // Bootstrap final stretch (offset < 5000, triggered iff h%3 != 0).
        { 12095, /*12095%3=2*/ true,  "bootstrap" },
        { 12096, /*12096%3=0*/ false, "bootstrap" },
        { 12097, /*12097%3=1*/ true,  "bootstrap" },
        { 12098, /*12098%3=2*/ true,  "bootstrap" },
        { 12099, /*12099%3=0*/ false, "bootstrap (LAST)" },
        // Permanent stretch (offset >= 5000, triggered iff h%3 == 0).
        { 12100, /*12100%3=1*/ false, "permanent (FIRST)" },
        { 12101, /*12101%3=2*/ false, "permanent" },
        { 12102, /*12102%3=0*/ true,  "permanent (first 1-of-3)" },
        { 12103, /*12103%3=1*/ false, "permanent" },
        { 12104, /*12104%3=2*/ false, "permanent" },
        { 12105, /*12105%3=0*/ true,  "permanent" },
        { 12106, /*12106%3=1*/ false, "permanent" },
        { 12107, /*12107%3=2*/ false, "permanent" },
        { 12108, /*12108%3=0*/ true,  "permanent" },
        { 12109, /*12109%3=1*/ false, "permanent" },
        { 12110, /*12110%3=2*/ false, "permanent" },
    };

    int bootstrap_fires = 0, bootstrap_total = 0;
    int permanent_fires = 0, permanent_total = 0;

    for (const Row& r : rows) {
        const bool got = is_lottery_block(r.h, V11_PHASE2_HEIGHT);
        char buf[128];
        std::snprintf(buf, sizeof(buf),
                      "h=%lld %-26s expected=%s got=%s",
                      (long long)r.h, r.phase,
                      r.expected ? "FIRES" : "----",
                      got        ? "FIRES" : "----");
        TEST(buf, got == r.expected);

        if (r.h < 12100) {
            ++bootstrap_total;
            if (got) ++bootstrap_fires;
        } else {
            ++permanent_total;
            if (got) ++permanent_fires;
        }
    }

    // Window-density assertions for this specific 16-block range.
    // (Long-run density 2/3 and 1/3 is already covered by sections
    //  3 and 5; this section pins the exact pattern at the flip.)
    TEST("bootstrap window 12095..12099 has 3 fires / 5 blocks",
         bootstrap_fires == 3 && bootstrap_total == 5);
    TEST("permanent window 12100..12110 has 3 fires / 11 blocks",
         permanent_fires == 3 && permanent_total == 11);

    // Boundary invariant: at no point in the contiguous sweep does
    // the function require any input other than (h, V11_PHASE2_HEIGHT).
    // The flip is purely a consequence of the height crossing
    // V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW (= 12100).
    TEST("V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW == 12100",
         (V11_PHASE2_HEIGHT + LOTTERY_HIGH_FREQ_WINDOW) == 12100);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
int main() {
    printf("=== test_lottery_frequency (V11 Phase 2 C5) ===\n");
    test_int64_max_sentinel_always_false();
    test_pre_phase2_returns_false();
    test_bootstrap_window();
    test_window_boundary();
    test_permanent_window();
    test_constants_pinned();
    test_production_schedule();
    test_dtd_flip_contiguity_12095_12110();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
