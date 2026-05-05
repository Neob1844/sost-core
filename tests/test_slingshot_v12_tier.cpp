// V12 Slingshot — same-block 5-tier relief tests.
//
// V12 hard fork (block V12_HEIGHT = 7350) replaces the V11 dual-gate
// next-block prev_elapsed-based Slingshot with a same-block, single-gate
// 5-tier ladder keyed on current_elapsed only. Round-minute thresholds:
//
//   slingshot_v12_tier(current_elapsed):
//     > V12_SLINGSHOT_T5_SECONDS (10800) → 5  (>180 min, catastrophic)
//     > V12_SLINGSHOT_T4_SECONDS  (7200) → 4  (>120 min)
//     > V12_SLINGSHOT_T3_SECONDS  (3600) → 3  (>60 min)
//     > V12_SLINGSHOT_T2_SECONDS  (1800) → 2  (>30 min)
//     > V12_SLINGSHOT_T1_SECONDS  (1200) → 1  (>20 min)
//     else                                → 0
//
// Strict greater-than at every threshold; the boundary value itself does
// NOT trigger the higher tier. Drop bps:
//
//   tier 1 → V12_SLINGSHOT_T1_DROP_BPS  =  650  (-6.5%)
//   tier 2 → V12_SLINGSHOT_T2_DROP_BPS  = 1250 (-12.5%)
//   tier 3 → V12_SLINGSHOT_T3_DROP_BPS  = 2500 (-25%)
//   tier 4 → V12_SLINGSHOT_T4_DROP_BPS  = 3750 (-37.5%)
//   tier 5 → V12_SLINGSHOT_T5_DROP_BPS  = 5000 (-50%)
//
// At heights < V12_HEIGHT the V11 dual-gate single-12.5% path is
// preserved and must keep firing exactly as before. At height
// >= V12_HEIGHT only the V12 ladder applies — no V11 prev_elapsed gate.

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

// Build a chain of `len` blocks ending at height `last_height`. All
// intervals = TARGET_SPACING (600 s) EXCEPT the very last interval, set
// to `last_interval_s`.
static std::vector<BlockMeta> build_chain(int64_t last_height,
                                          int64_t last_interval_s,
                                          uint32_t seed_bitsq,
                                          size_t len = 300) {
    std::vector<BlockMeta> chain;
    chain.reserve(len);
    int64_t t0 = GENESIS_TIME + (last_height - (int64_t)len + 1) * TARGET_SPACING;
    for (size_t i = 0; i < len; ++i) {
        BlockMeta m{};
        m.block_id = ZERO_HASH();
        m.height = last_height - (int64_t)len + 1 + (int64_t)i;
        m.time = t0 + (int64_t)i * TARGET_SPACING;
        m.powDiffQ = seed_bitsq;
        m.profile_index = 0;
        chain.push_back(m);
    }
    chain.back().time = chain[chain.size() - 2].time + last_interval_s;
    return chain;
}

// Apply the V12 tier drop to a baseline bitsQ (rounding identical to
// the implementation: integer truncation, MIN_BITSQ floor clamp).
static uint32_t apply_v12_drop(uint32_t base, int32_t drop_bps) {
    if (drop_bps <= 0) return base;
    int64_t r = ((int64_t)base * (10000 - drop_bps)) / 10000;
    if (r < (int64_t)MIN_BITSQ) r = (int64_t)MIN_BITSQ;
    return (uint32_t)r;
}

static int32_t drop_bps_for_tier(int t) {
    switch (t) {
        case 5: return V12_SLINGSHOT_T5_DROP_BPS;
        case 4: return V12_SLINGSHOT_T4_DROP_BPS;
        case 3: return V12_SLINGSHOT_T3_DROP_BPS;
        case 2: return V12_SLINGSHOT_T2_DROP_BPS;
        case 1: return V12_SLINGSHOT_T1_DROP_BPS;
        default: return 0;
    }
}

// =============================================================================
// 1. Tier ladder boundaries — strict > rule honored at every threshold.
//    Boundary values stay at the lower tier.
// =============================================================================
static void test_tier_ladder_boundaries() {
    printf("\n=== 1. V12 tier ladder boundaries (strict >) ===\n");

    // Below T1 — no drop.
    TEST("current=0     → tier 0", slingshot_v12_tier(0) == 0);
    TEST("current=1199  → tier 0", slingshot_v12_tier(1199) == 0);
    TEST("current=1200  → tier 0 (boundary, strict >)", slingshot_v12_tier(1200) == 0);

    // T1 (1200, 1800].
    TEST("current=1201  → tier 1 (-6.5%)", slingshot_v12_tier(1201) == 1);
    TEST("current=1799  → tier 1", slingshot_v12_tier(1799) == 1);
    TEST("current=1800  → tier 1 (boundary, strict >)", slingshot_v12_tier(1800) == 1);

    // T2 (1800, 3600].
    TEST("current=1801  → tier 2 (-12.5%)", slingshot_v12_tier(1801) == 2);
    TEST("current=3599  → tier 2", slingshot_v12_tier(3599) == 2);
    TEST("current=3600  → tier 2 (boundary, strict >)", slingshot_v12_tier(3600) == 2);

    // T3 (3600, 7200].
    TEST("current=3601  → tier 3 (-25%)", slingshot_v12_tier(3601) == 3);
    TEST("current=7199  → tier 3", slingshot_v12_tier(7199) == 3);
    TEST("current=7200  → tier 3 (boundary, strict >)", slingshot_v12_tier(7200) == 3);

    // T4 (7200, 10800].
    TEST("current=7201  → tier 4 (-37.5%)", slingshot_v12_tier(7201) == 4);
    TEST("current=10799 → tier 4", slingshot_v12_tier(10799) == 4);
    TEST("current=10800 → tier 4 (boundary, strict >)", slingshot_v12_tier(10800) == 4);

    // T5 (10800, ∞).
    TEST("current=10801 → tier 5 (-50%, catastrophic)", slingshot_v12_tier(10801) == 5);
    TEST("current=86400 → tier 5 (no further tier above 5)", slingshot_v12_tier(86400) == 5);

    // Negative / zero — defensive.
    TEST("current=-1 → tier 0", slingshot_v12_tier(-1) == 0);
    TEST("current=INT64_MIN-equivalent → tier 0",
         slingshot_v12_tier((int64_t)-1000000) == 0);
}

// =============================================================================
// 2. Drop math — for a chain at V12_HEIGHT the resulting bits_q drops by
//    exactly the tier's bps relative to the un-relieved baseline.
// =============================================================================
static void test_drop_magnitudes() {
    printf("\n=== 2. V12 drop magnitudes (per-tier exact ratio) ===\n");

    int64_t tip = V12_HEIGHT;
    const uint32_t SEED = 800000;

    // For the un-relieved reference we evaluate at a pre-V12 height with
    // current_elapsed=0 — gate 2 closed, no V11 drop, no V12 drop.
    auto run_pre = [&](int64_t last_interval) {
        auto c_pre = build_chain(V12_HEIGHT - 5, last_interval, SEED);
        return casert_next_bitsq(c_pre, V12_HEIGHT - 4, c_pre.back().time + 1);
    };

    auto run_post = [&](int64_t last_interval, int64_t cur_elapsed) {
        auto c = build_chain(tip, last_interval, SEED);
        return casert_next_bitsq(c, tip + 1, c.back().time + cur_elapsed);
    };

    // Tier 1 — current_elapsed = 1500 s (> T1=1200, < T2=1800).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 1500);
        TEST("tier 1 (cur=1500) → bits_q == pre * 0.935",
             post == apply_v12_drop(pre, drop_bps_for_tier(1)));
    }

    // Tier 2 — current_elapsed = 2400 s (> T2=1800, < T3=3600).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 2400);
        TEST("tier 2 (cur=2400) → bits_q == pre * 0.875",
             post == apply_v12_drop(pre, drop_bps_for_tier(2)));
    }

    // Tier 3 — current_elapsed = 5000 s (> T3=3600, < T4=7200).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 5000);
        TEST("tier 3 (cur=5000) → bits_q == pre * 0.75",
             post == apply_v12_drop(pre, drop_bps_for_tier(3)));
    }

    // Tier 4 — current_elapsed = 9000 s (> T4=7200, < T5=10800).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 9000);
        TEST("tier 4 (cur=9000) → bits_q == pre * 0.625",
             post == apply_v12_drop(pre, drop_bps_for_tier(4)));
    }

    // Tier 5 — current_elapsed = 12000 s (> T5=10800, catastrophic).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 12000);
        TEST("tier 5 (cur=12000) → bits_q == pre * 0.5 (catastrophic)",
             post == apply_v12_drop(pre, drop_bps_for_tier(5)));
    }
}

// =============================================================================
// 3. Pre-V12 path unchanged — at height < V12_HEIGHT, V11 dual-gate
//    single-12.5% Slingshot must still fire (prev_elapsed=1801 + current=601).
// =============================================================================
static void test_pre_v12_unchanged() {
    printf("\n=== 3. Pre-V12 path — V11 dual-gate must still fire ===\n");

    int64_t tip = V12_HEIGHT - 2;
    const uint32_t SEED = 800000;

    auto c = build_chain(tip, 1801, SEED);              // gate 1 open (1801 > 1800)
    int64_t now_t = c.back().time + 601;                // gate 2 open (601 > 600)
    uint32_t b_v11 = casert_next_bitsq(c, tip + 1, now_t);

    auto c_ref = build_chain(V11_SLINGSHOT_HEIGHT - 2, 1801, SEED);
    uint32_t b_ref = casert_next_bitsq(c_ref, V11_SLINGSHOT_HEIGHT - 1,
                                       c_ref.back().time + 601);

    int64_t expected = ((int64_t)b_ref * (10000 - (int64_t)SLINGSHOT_DROP_BPS)) / 10000;
    if (expected < (int64_t)MIN_BITSQ) expected = (int64_t)MIN_BITSQ;
    TEST("pre-V12 (h=7349) + prev=1801 + cur=601 → V11 12.5% drop applied",
         b_v11 == (uint32_t)expected);

    // Verify the V12 tier ladder is NOT consulted at pre-V12 heights:
    // a chain with current_elapsed > 1200 s but prev_elapsed=600 (V11 gate 1
    // closed) must NOT receive a V12 tier-1 drop on a pre-V12 height.
    {
        auto c2 = build_chain(tip, 600, SEED);          // V11 gate 1 closed
        uint32_t b = casert_next_bitsq(c2, tip + 1, c2.back().time + 1500);

        auto c2_ref = build_chain(V11_SLINGSHOT_HEIGHT - 2, 600, SEED);
        uint32_t b_ref2 = casert_next_bitsq(c2_ref, V11_SLINGSHOT_HEIGHT - 1,
                                            c2_ref.back().time + 1500);
        TEST("pre-V12 + V11 gate 1 closed (prev=600) + cur=1500 → no drop",
             b == b_ref2);
    }
}

// =============================================================================
// 4. Self-reset — three consecutive blocks with different current_elapsed
//    each compute a fresh tier independently. No compounding.
// =============================================================================
static void test_self_reset() {
    printf("\n=== 4. Self-reset — each block computes its own tier ===\n");

    const uint32_t SEED = 800000;

    auto run_at_v12 = [&](int64_t cur_elapsed, int64_t tip_height) {
        auto c = build_chain(tip_height, 600, SEED);
        return casert_next_bitsq(c, tip_height + 1, c.back().time + cur_elapsed);
    };

    auto run_at_pre_v12 = [&](int64_t cur_elapsed) {
        auto c = build_chain(V12_HEIGHT - 5, 600, SEED);
        return casert_next_bitsq(c, V12_HEIGHT - 4, c.back().time + cur_elapsed);
    };

    int64_t cur1 = 1500;  // tier 1 (> 1200)
    int64_t cur2 = 2400;  // tier 2 (> 1800)
    int64_t cur3 = 5000;  // tier 3 (> 3600)
    uint32_t pre_ref = run_at_pre_v12(0); // baseline (cur=0 → tier 0)

    uint32_t post1 = run_at_v12(cur1, V12_HEIGHT);
    uint32_t post2 = run_at_v12(cur2, V12_HEIGHT);
    uint32_t post3 = run_at_v12(cur3, V12_HEIGHT);

    TEST("tier 1 fresh — does not depend on previous block",
         post1 == apply_v12_drop(pre_ref, drop_bps_for_tier(1)));
    TEST("tier 2 fresh — does not depend on previous block",
         post2 == apply_v12_drop(pre_ref, drop_bps_for_tier(2)));
    TEST("tier 3 fresh — does not depend on previous block",
         post3 == apply_v12_drop(pre_ref, drop_bps_for_tier(3)));

    // Strong negative — tier-2 result must NOT equal compounded
    // tier-1 application (T1(T1(base))).
    uint32_t compounded = apply_v12_drop(apply_v12_drop(pre_ref,
                                          drop_bps_for_tier(1)),
                                          drop_bps_for_tier(1));
    TEST("tier 2 result is NOT the squared tier-1 multiplier (no compounding)",
         post2 != compounded || pre_ref == MIN_BITSQ);
}

// =============================================================================
// 5. now_time<=0 / now_time<tip.time — safe defaults (no drop).
// =============================================================================
static void test_safe_defaults() {
    printf("\n=== 5. Safe defaults — now_time<=0 or now_time<tip.time → no drop ===\n");

    int64_t tip = V12_HEIGHT;
    const uint32_t SEED = 800000;
    auto c = build_chain(tip, 600, SEED);

    auto c_ref = build_chain(V12_HEIGHT - 5, 600, SEED);
    uint32_t b_ref = casert_next_bitsq(c_ref, V12_HEIGHT - 4, c_ref.back().time + 1);

    uint32_t b_zero = casert_next_bitsq(c, tip + 1, 0);
    uint32_t b_neg  = casert_next_bitsq(c, tip + 1, -1);
    uint32_t b_def  = casert_next_bitsq(c, tip + 1);

    TEST("now_time=0 → no V12 drop (matches pre-V12 baseline)", b_zero == b_ref);
    TEST("now_time<0 → no V12 drop", b_neg == b_ref);
    TEST("now_time omitted → no V12 drop", b_def == b_ref);

    uint32_t b_past = casert_next_bitsq(c, tip + 1, c.back().time - 100);
    TEST("now_time<tip.time → tier 0 → no drop", b_past == b_ref);
}

// =============================================================================
// 6. Determinism — 10 identical calls produce 10 identical outputs.
// =============================================================================
static void test_determinism() {
    printf("\n=== 6. V12 determinism (10 runs each) ===\n");

    int64_t tip = V12_HEIGHT + 7;
    auto chain = build_chain(tip, 600, 1234567);

    int64_t nt_t3 = chain.back().time + 5000;  // tier 3 (> T3=3600, < T4=7200)
    uint32_t first_t3 = casert_next_bitsq(chain, tip + 1, nt_t3);
    bool all_eq_t3 = true;
    for (int i = 0; i < 10; ++i) {
        if (casert_next_bitsq(chain, tip + 1, nt_t3) != first_t3) { all_eq_t3 = false; break; }
    }
    TEST("10 calls in tier-3 path → 10 identical outputs", all_eq_t3);

    int64_t nt_t0 = chain.back().time + 100;
    uint32_t first_t0 = casert_next_bitsq(chain, tip + 1, nt_t0);
    bool all_eq_t0 = true;
    for (int i = 0; i < 10; ++i) {
        if (casert_next_bitsq(chain, tip + 1, nt_t0) != first_t0) { all_eq_t0 = false; break; }
    }
    TEST("10 calls in no-drop path → 10 identical outputs", all_eq_t0);

    TEST("tier-3 and no-drop branches produce different bits_q",
         first_t3 != first_t0);
}

// =============================================================================
// 7. MIN_BITSQ floor — even tier 5 (50% off) cannot drop below MIN_BITSQ.
// =============================================================================
static void test_min_bitsq_floor() {
    printf("\n=== 7. MIN_BITSQ floor — V12 drop never goes below MIN_BITSQ ===\n");

    TEST("apply_v12_drop(MIN_BITSQ, T5) == MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ, V12_SLINGSHOT_T5_DROP_BPS) == MIN_BITSQ);
    TEST("apply_v12_drop(MIN_BITSQ+1, T5) == MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ + 1, V12_SLINGSHOT_T5_DROP_BPS) == MIN_BITSQ);
    TEST("apply_v12_drop(MIN_BITSQ*4, T5) is well above MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ * 4, V12_SLINGSHOT_T5_DROP_BPS) > MIN_BITSQ);

    // Direct chain test with seed at MIN_BITSQ.
    int64_t tip = V12_HEIGHT;
    auto c = build_chain(tip, 600, MIN_BITSQ);
    uint32_t b = casert_next_bitsq(c, tip + 1, c.back().time + 12000); // tier 5
    TEST("seed=MIN_BITSQ + tier 5 → result >= MIN_BITSQ", b >= MIN_BITSQ);
}

int main() {
    printf("\n=== V12 Slingshot tier tests (5-tier ladder) ===\n");
    printf("V12_HEIGHT                  = %lld\n", (long long)V12_HEIGHT);
    printf("V12_SLINGSHOT_T1_SECONDS    = %lld  (= %lld min)\n",
           (long long)V12_SLINGSHOT_T1_SECONDS, (long long)V12_SLINGSHOT_T1_SECONDS / 60);
    printf("V12_SLINGSHOT_T2_SECONDS    = %lld  (= %lld min)\n",
           (long long)V12_SLINGSHOT_T2_SECONDS, (long long)V12_SLINGSHOT_T2_SECONDS / 60);
    printf("V12_SLINGSHOT_T3_SECONDS    = %lld  (= %lld min)\n",
           (long long)V12_SLINGSHOT_T3_SECONDS, (long long)V12_SLINGSHOT_T3_SECONDS / 60);
    printf("V12_SLINGSHOT_T4_SECONDS    = %lld  (= %lld min)\n",
           (long long)V12_SLINGSHOT_T4_SECONDS, (long long)V12_SLINGSHOT_T4_SECONDS / 60);
    printf("V12_SLINGSHOT_T5_SECONDS    = %lld  (= %lld min)\n",
           (long long)V12_SLINGSHOT_T5_SECONDS, (long long)V12_SLINGSHOT_T5_SECONDS / 60);
    printf("V12_SLINGSHOT_T1_DROP_BPS   = %d\n",  V12_SLINGSHOT_T1_DROP_BPS);
    printf("V12_SLINGSHOT_T2_DROP_BPS   = %d\n",  V12_SLINGSHOT_T2_DROP_BPS);
    printf("V12_SLINGSHOT_T3_DROP_BPS   = %d\n",  V12_SLINGSHOT_T3_DROP_BPS);
    printf("V12_SLINGSHOT_T4_DROP_BPS   = %d\n",  V12_SLINGSHOT_T4_DROP_BPS);
    printf("V12_SLINGSHOT_T5_DROP_BPS   = %d\n",  V12_SLINGSHOT_T5_DROP_BPS);

    test_tier_ladder_boundaries();
    test_drop_magnitudes();
    test_pre_v12_unchanged();
    test_self_reset();
    test_safe_defaults();
    test_determinism();
    test_min_bitsq_floor();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
