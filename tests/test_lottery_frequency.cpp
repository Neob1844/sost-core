// V11 Phase 2 — lottery frequency tests (Commit 5 scope).
//
// Exercises sost::lottery::is_lottery_block — the height-only,
// height-anchored trigger rule. Pure function, no chain state, no
// Schnorr dependency (this test file is built unconditionally,
// regardless of -DSOST_ENABLE_PHASE2_SBPOW).
//
// Production schedule verified: V11_PHASE2_HEIGHT == 10000 (set by C10).
// is_lottery_block returns false for every chain height < 10000 and
// follows the documented 2-of-3 / 1-of-3 schedule for height >= 10000.
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
    TEST("height=10'000, INT64_MAX → false",
         !is_lottery_block(10000, SENTINEL));
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
    TEST("V11_PHASE2_HEIGHT == 10000 (set by C10)",
         V11_PHASE2_HEIGHT == 10000);
}

// ---------------------------------------------------------------------------
// 7 — Production schedule with V11_PHASE2_HEIGHT from params.h (= 10000).
//     Every chain height < 10000 returns false; from 10000 onwards the
//     2-of-3 (bootstrap) and 1-of-3 (permanent) schedules apply.
// ---------------------------------------------------------------------------
static void test_production_schedule() {
    printf("\n=== 7) Production schedule with V11_PHASE2_HEIGHT (= 10000) ===\n");

    // Pre-activation heights: ALL must be false.
    const int64_t pre_heights[] = {
        0, 1, 1450, 5000, 6700, 7000, 7001, 8000, 9000, 9998, 9999
    };
    for (int64_t h : pre_heights) {
        char buf[96];
        std::snprintf(buf, sizeof(buf),
                      "pre-activation height=%lld → false",
                      (long long)h);
        TEST(buf, !is_lottery_block(h, V11_PHASE2_HEIGHT));
    }

    // Boundary at activation:
    //   height=10000: 10000 % 3 = 1 → bootstrap rule says (h%3) != 0 → true.
    //   height=10001: 10001 % 3 = 2 → bootstrap → true.
    //   height=10002: 10002 % 3 = 0 → bootstrap rule (h%3) != 0 → false.
    TEST("activation height=10000 (bootstrap, 10000%3==1) → true",
         is_lottery_block(10000, V11_PHASE2_HEIGHT));
    TEST("activation height=10001 (bootstrap, 10001%3==2) → true",
         is_lottery_block(10001, V11_PHASE2_HEIGHT));
    TEST("activation height=10002 (bootstrap, 10002%3==0) → false",
         !is_lottery_block(10002, V11_PHASE2_HEIGHT));

    // Last block of the high-freq window: offset = 4999 → bootstrap.
    //   height=14999: 14999 % 3 = 2 → bootstrap (h%3)!=0 → true.
    TEST("last bootstrap block height=14999 (offset=4999, 14999%3==2) → true",
         is_lottery_block(14999, V11_PHASE2_HEIGHT));

    // First block of the permanent window: offset = 5000 → 1-of-3.
    //   height=15000: 15000 % 3 = 0 → permanent (h%3)==0 → true.
    //   height=15001: 15001 % 3 = 1 → permanent (h%3)==0 → false.
    //   height=15002: 15002 % 3 = 2 → permanent → false.
    //   height=15003: 15003 % 3 = 0 → permanent → true.
    TEST("first permanent block height=15000 (offset=5000, 15000%3==0) → true",
         is_lottery_block(15000, V11_PHASE2_HEIGHT));
    TEST("permanent height=15001 (h%3==1) → false",
         !is_lottery_block(15001, V11_PHASE2_HEIGHT));
    TEST("permanent height=15002 (h%3==2) → false",
         !is_lottery_block(15002, V11_PHASE2_HEIGHT));
    TEST("permanent height=15003 (h%3==0) → true",
         is_lottery_block(15003, V11_PHASE2_HEIGHT));

    // Long-range spot checks deep in the permanent window.
    TEST("permanent height=50001 (h%3==0) → true",
         is_lottery_block(50001, V11_PHASE2_HEIGHT));
    TEST("permanent height=50002 (h%3==1) → false",
         !is_lottery_block(50002, V11_PHASE2_HEIGHT));
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

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
