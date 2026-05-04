// V12 Slingshot — same-block 4-tier relief tests.
//
// V12 hard fork (block V12_HEIGHT = 7350) replaces the V11 dual-gate
// next-block prev_elapsed-based Slingshot with a same-block, single-gate
// 4-tier ladder keyed on current_elapsed only:
//
//   slingshot_v12_tier(current_elapsed):
//     > V12_SLINGSHOT_T4_SECONDS (7140)  → 4   (>119 min)
//     > V12_SLINGSHOT_T3_SECONDS (3540)  → 3   (>59 min)
//     > V12_SLINGSHOT_T2_SECONDS (1740)  → 2   (>29 min)
//     > V12_SLINGSHOT_T1_SECONDS  (840)  → 1   (>14 min)
//     else                                → 0
//
// Strict greater-than at every threshold; the boundary value itself does
// NOT trigger the higher tier. Drop bps:
//
//   tier 1 → V12_SLINGSHOT_T1_DROP_BPS  =  650  (-6.5%)
//   tier 2 → V12_SLINGSHOT_T2_DROP_BPS  = 1250 (-12.5%)
//   tier 3 → V12_SLINGSHOT_T3_DROP_BPS  = 2500 (-25%)
//   tier 4 → V12_SLINGSHOT_T4_DROP_BPS  = 3750 (-37.5%)
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
// to `last_interval_s`. Mirrors test_slingshot.cpp::build_chain so this
// test exercises the same shape as the V11 suite.
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
        case 4: return V12_SLINGSHOT_T4_DROP_BPS;
        case 3: return V12_SLINGSHOT_T3_DROP_BPS;
        case 2: return V12_SLINGSHOT_T2_DROP_BPS;
        case 1: return V12_SLINGSHOT_T1_DROP_BPS;
        default: return 0;
    }
}

// =============================================================================
// 1. Tier ladder boundaries — the strict > rule must be honored at every
//    threshold. Boundary values stay at the lower tier.
// =============================================================================
static void test_tier_ladder_boundaries() {
    printf("\n=== 1. V12 tier ladder boundaries (strict >) ===\n");

    // Below T1 — no drop.
    TEST("current=0    → tier 0", slingshot_v12_tier(0) == 0);
    TEST("current=839  → tier 0", slingshot_v12_tier(839) == 0);
    TEST("current=840  → tier 0 (boundary, strict >)", slingshot_v12_tier(840) == 0);

    // T1 (840, 1740].
    TEST("current=841  → tier 1 (-6.5%)", slingshot_v12_tier(841) == 1);
    TEST("current=1739 → tier 1", slingshot_v12_tier(1739) == 1);
    TEST("current=1740 → tier 1 (boundary, strict >)", slingshot_v12_tier(1740) == 1);

    // T2 (1740, 3540].
    TEST("current=1741 → tier 2 (-12.5%)", slingshot_v12_tier(1741) == 2);
    TEST("current=3539 → tier 2", slingshot_v12_tier(3539) == 2);
    TEST("current=3540 → tier 2 (boundary, strict >)", slingshot_v12_tier(3540) == 2);

    // T3 (3540, 7140].
    TEST("current=3541 → tier 3 (-25%)", slingshot_v12_tier(3541) == 3);
    TEST("current=7139 → tier 3", slingshot_v12_tier(7139) == 3);
    TEST("current=7140 → tier 3 (boundary, strict >)", slingshot_v12_tier(7140) == 3);

    // T4 (7140, ∞).
    TEST("current=7141 → tier 4 (-37.5%)", slingshot_v12_tier(7141) == 4);
    TEST("current=86400 → tier 4 (no further tier above 4)", slingshot_v12_tier(86400) == 4);

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
    // current_elapsed=0 — gate 2 closed, no V11 drop, no V12 drop. The
    // avg288 result is identical to the post-fork chain shape because
    // intervals are identical (all TARGET_SPACING with the last set to
    // `last_interval`); the only consensus difference is the Slingshot
    // path itself.
    auto run_pre = [&](int64_t last_interval) {
        auto c_pre = build_chain(V12_HEIGHT - 5, last_interval, SEED);
        return casert_next_bitsq(c_pre, V12_HEIGHT - 4, c_pre.back().time + 1);
    };

    auto run_post = [&](int64_t last_interval, int64_t cur_elapsed) {
        auto c = build_chain(tip, last_interval, SEED);
        return casert_next_bitsq(c, tip + 1, c.back().time + cur_elapsed);
    };

    // Tier 1 — current_elapsed = 1000 s (> T1=840, < T2=1740).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 1000);
        TEST("tier 1 (cur=1000) → bits_q == pre * 0.935",
             post == apply_v12_drop(pre, drop_bps_for_tier(1)));
    }

    // Tier 2 — current_elapsed = 2000 s (> T2=1740, < T3=3540).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 2000);
        TEST("tier 2 (cur=2000) → bits_q == pre * 0.875",
             post == apply_v12_drop(pre, drop_bps_for_tier(2)));
    }

    // Tier 3 — current_elapsed = 4000 s (> T3=3540, < T4=7140).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 4000);
        TEST("tier 3 (cur=4000) → bits_q == pre * 0.75",
             post == apply_v12_drop(pre, drop_bps_for_tier(3)));
    }

    // Tier 4 — current_elapsed = 8000 s (> T4=7140).
    {
        uint32_t pre  = run_pre(600);
        uint32_t post = run_post(600, 8000);
        TEST("tier 4 (cur=8000) → bits_q == pre * 0.625",
             post == apply_v12_drop(pre, drop_bps_for_tier(4)));
    }
}

// =============================================================================
// 3. Pre-V12 path unchanged — at height < V12_HEIGHT, the V11 dual-gate
//    single-12.5% Slingshot must still fire (prev_elapsed=1801 + current=601).
// =============================================================================
static void test_pre_v12_unchanged() {
    printf("\n=== 3. Pre-V12 path — V11 dual-gate must still fire ===\n");

    // Tip at V12_HEIGHT - 2, so next_height = V12_HEIGHT - 1 (= 7349). That
    // is still pre-V12 and post-V11_SLINGSHOT_HEIGHT (7000), so V11 rules apply.
    int64_t tip = V12_HEIGHT - 2;
    const uint32_t SEED = 800000;

    // V11 gate 1: prev_elapsed > SLINGSHOT_THRESHOLD_SECONDS (1800 s).
    // V11 gate 2: current_elapsed > TARGET_SPACING (600 s).
    auto c = build_chain(tip, 1801, SEED);              // gate 1 open (1801 > 1800)
    int64_t now_t = c.back().time + 601;                // gate 2 open (601 > 600)
    uint32_t b_v11 = casert_next_bitsq(c, tip + 1, now_t);

    // Reference at pre-V11_SLINGSHOT_HEIGHT — no Slingshot at all.
    auto c_ref = build_chain(V11_SLINGSHOT_HEIGHT - 2, 1801, SEED);
    uint32_t b_ref = casert_next_bitsq(c_ref, V11_SLINGSHOT_HEIGHT - 1,
                                       c_ref.back().time + 601);

    int64_t expected = ((int64_t)b_ref * (10000 - (int64_t)SLINGSHOT_DROP_BPS)) / 10000;
    if (expected < (int64_t)MIN_BITSQ) expected = (int64_t)MIN_BITSQ;
    TEST("pre-V12 (h=7349) + prev=1801 + cur=601 → V11 12.5% drop applied",
         b_v11 == (uint32_t)expected);

    // Verify the V12 tier ladder is NOT consulted at pre-V12 heights:
    // a chain with current_elapsed > 840 s but prev_elapsed=600 (V11 gate 1
    // closed) must NOT receive a V12 tier-1 drop on a pre-V12 height.
    {
        auto c2 = build_chain(tip, 600, SEED);          // V11 gate 1 closed
        uint32_t b = casert_next_bitsq(c2, tip + 1, c2.back().time + 1000);

        auto c2_ref = build_chain(V11_SLINGSHOT_HEIGHT - 2, 600, SEED);
        uint32_t b_ref2 = casert_next_bitsq(c2_ref, V11_SLINGSHOT_HEIGHT - 1,
                                            c2_ref.back().time + 1000);
        TEST("pre-V12 + V11 gate 1 closed (prev=600) + cur=1000 → no drop",
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

    // The V12 path mixes the avg288 result with the tier multiplier. To
    // isolate the multiplier, we compare against a pre-V12 reference at
    // the same intervals — that pre-V12 baseline never sees any drop
    // because gate 1 is closed (last_interval=600) — and confirm the
    // post-V12 value matches reference * (1 - drop_bps).
    int64_t cur1 = 1000;  // tier 1 (> 840)
    int64_t cur2 = 2000;  // tier 2 (> 1740)
    int64_t cur3 = 4000;  // tier 3 (> 3540)
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

    // Strong negative — a tier-2 result must NOT equal a compounded
    // tier-1 application (i.e. T1(T1(base))) — those differ.
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

    // Reference baseline (pre-V12, no Slingshot path active).
    auto c_ref = build_chain(V12_HEIGHT - 5, 600, SEED);
    uint32_t b_ref = casert_next_bitsq(c_ref, V12_HEIGHT - 4, c_ref.back().time + 1);

    uint32_t b_zero = casert_next_bitsq(c, tip + 1, 0);
    uint32_t b_neg  = casert_next_bitsq(c, tip + 1, -1);
    uint32_t b_def  = casert_next_bitsq(c, tip + 1);  // default arg = 0

    TEST("now_time=0 → no V12 drop (matches pre-V12 baseline)",
         b_zero == b_ref);
    TEST("now_time<0 → no V12 drop", b_neg == b_ref);
    TEST("now_time omitted → no V12 drop", b_def == b_ref);

    // now_time < tip.time → current_elapsed would be negative; tier helper
    // returns 0 → no drop.
    uint32_t b_past = casert_next_bitsq(c, tip + 1, c.back().time - 100);
    TEST("now_time<tip.time → tier 0 → no drop",
         b_past == b_ref);
}

// =============================================================================
// 6. Determinism — 10 identical calls produce 10 identical outputs.
// =============================================================================
static void test_determinism() {
    printf("\n=== 6. V12 determinism (10 runs each, drop branch + no-drop branch) ===\n");

    int64_t tip = V12_HEIGHT + 7;
    auto chain = build_chain(tip, 600, 1234567);

    // Tier 3 path (current_elapsed = 4000 > T3=3600, < T4=7200)
    int64_t nt_t3 = chain.back().time + 4000;
    uint32_t first_t3 = casert_next_bitsq(chain, tip + 1, nt_t3);
    bool all_eq_t3 = true;
    for (int i = 0; i < 10; ++i) {
        if (casert_next_bitsq(chain, tip + 1, nt_t3) != first_t3) { all_eq_t3 = false; break; }
    }
    TEST("10 calls in tier-3 path → 10 identical outputs", all_eq_t3);

    // No-drop path
    int64_t nt_t0 = chain.back().time + 100;
    uint32_t first_t0 = casert_next_bitsq(chain, tip + 1, nt_t0);
    bool all_eq_t0 = true;
    for (int i = 0; i < 10; ++i) {
        if (casert_next_bitsq(chain, tip + 1, nt_t0) != first_t0) { all_eq_t0 = false; break; }
    }
    TEST("10 calls in no-drop path → 10 identical outputs", all_eq_t0);

    // Drop branch and no-drop branch must differ.
    TEST("tier-3 and no-drop branches produce different bits_q",
         first_t3 != first_t0);
}

// =============================================================================
// 7. MIN_BITSQ floor — even tier 4 (37.5% off) cannot drop below MIN_BITSQ.
// =============================================================================
static void test_min_bitsq_floor() {
    printf("\n=== 7. MIN_BITSQ floor — V12 drop never goes below MIN_BITSQ ===\n");

    // Synthesize a base near the floor.
    TEST("apply_v12_drop(MIN_BITSQ, T4) == MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ, V12_SLINGSHOT_T4_DROP_BPS) == MIN_BITSQ);
    TEST("apply_v12_drop(MIN_BITSQ+1, T4) == MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ + 1, V12_SLINGSHOT_T4_DROP_BPS) == MIN_BITSQ);
    TEST("apply_v12_drop(MIN_BITSQ*4, T4) is well above MIN_BITSQ",
         apply_v12_drop(MIN_BITSQ * 4, V12_SLINGSHOT_T4_DROP_BPS) > MIN_BITSQ);

    // Direct chain test with seed at MIN_BITSQ.
    int64_t tip = V12_HEIGHT;
    auto c = build_chain(tip, 600, MIN_BITSQ);
    uint32_t b = casert_next_bitsq(c, tip + 1, c.back().time + 8000); // tier 4 (> T4=7200)
    TEST("seed=MIN_BITSQ + tier 4 → result >= MIN_BITSQ",
         b >= MIN_BITSQ);
}

int main() {
    printf("\n=== V12 Slingshot tier tests ===\n");
    printf("V12_HEIGHT                  = %lld\n", (long long)V12_HEIGHT);
    printf("V12_SLINGSHOT_T1_SECONDS    = %lld\n", (long long)V12_SLINGSHOT_T1_SECONDS);
    printf("V12_SLINGSHOT_T2_SECONDS    = %lld\n", (long long)V12_SLINGSHOT_T2_SECONDS);
    printf("V12_SLINGSHOT_T3_SECONDS    = %lld\n", (long long)V12_SLINGSHOT_T3_SECONDS);
    printf("V12_SLINGSHOT_T4_SECONDS    = %lld\n", (long long)V12_SLINGSHOT_T4_SECONDS);
    printf("V12_SLINGSHOT_T1_DROP_BPS   = %d\n",  V12_SLINGSHOT_T1_DROP_BPS);
    printf("V12_SLINGSHOT_T2_DROP_BPS   = %d\n",  V12_SLINGSHOT_T2_DROP_BPS);
    printf("V12_SLINGSHOT_T3_DROP_BPS   = %d\n",  V12_SLINGSHOT_T3_DROP_BPS);
    printf("V12_SLINGSHOT_T4_DROP_BPS   = %d\n",  V12_SLINGSHOT_T4_DROP_BPS);

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
