// cASERT V11 cascade tests
//
// Verifies the V11 LINEAR cascade at block height >= CASERT_V11_HEIGHT.
//
// Formula: drop = 0                        if elapsed < 540
//          drop = 1 + (elapsed - 540) / 60 if elapsed >= 540
//
// Boundaries 540 / 600 / 660 / 720 / 780 / 840 s give drops 1 / 2 / 3 / 4 / 5 / 6
// (same values the previous saturating table produced — but the cascade KEEPS
// growing past 840 s instead of capping at 6, so a chain whose natural profile
// is high enough still reaches the E7 floor inside the anti-stall window).
//
// Pre-V11 (height 6999) must keep V10 continuous formula.
// Floor at CASERT_H_MIN (E7 = -7) must clamp the resulting profile.
#include "sost/pow/casert.h"
#include "sost/params.h"
#include <cstdio>
#include <vector>
#include <cstdlib>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Build a chain of `len` blocks ending at height `last_height-1` with the
// last timestamp chosen so that casert_compute computes lag = `target_lag`
// at next_height = last_height. Each block uses TARGET_SPACING.
static std::vector<BlockMeta> chain_with_lag(int64_t last_height,
                                              int64_t target_lag,
                                              size_t len = 200) {
    std::vector<BlockMeta> chain;
    chain.reserve(len);
    // We want: next_height - 1 - (last_time - GENESIS_TIME) / TARGET_SPACING == target_lag
    //  =>  last_time = GENESIS_TIME + (next_height - 1 - target_lag) * TARGET_SPACING
    int64_t last_time = GENESIS_TIME +
                         (last_height - 1 - target_lag) * TARGET_SPACING;
    int64_t t0 = last_time - (int64_t)(len - 1) * TARGET_SPACING;
    for (size_t i = 0; i < len; ++i) {
        BlockMeta m{};
        m.block_id = ZERO_HASH();
        m.height = (int64_t)last_height - (int64_t)len + (int64_t)i;
        m.time = t0 + (int64_t)i * TARGET_SPACING;
        m.powDiffQ = GENESIS_BITSQ;
        // Profile index does not need to be set deterministically for these
        // tests — casert_compute will derive H from the lag-based mapping.
        m.profile_index = 0;
        chain.push_back(m);
    }
    return chain;
}

// Helper: invoke casert_compute and return the profile_index.
static int32_t profile_at(const std::vector<BlockMeta>& chain,
                          int64_t next_height,
                          int64_t block_elapsed) {
    int64_t now_time = chain.back().time + block_elapsed;
    auto dec = casert_compute(chain, next_height, now_time);
    return dec.profile_index;
}

// ---------------------------------------------------------------------
// Section 1 — V11 cascade boundary table
// ---------------------------------------------------------------------
static void test_v11_cascade_boundaries() {
    printf("\n=== V11 cascade — boundary table at height %lld ===\n",
           (long long)CASERT_V11_HEIGHT);

    // raw_base_H = 10 (H10) requires lag = 10
    auto chain = chain_with_lag(CASERT_V11_HEIGHT, /*target_lag=*/10);

    // Below 540 — no relief
    TEST("elapsed=0 → no drop (profile = H10)",
         profile_at(chain, CASERT_V11_HEIGHT, 0) == 10);
    TEST("elapsed=539 → no drop",
         profile_at(chain, CASERT_V11_HEIGHT, 539) == 10);

    // Boundary 540 — drop 1
    TEST("elapsed=540 → drop 1 (H9)",
         profile_at(chain, CASERT_V11_HEIGHT, 540) == 9);
    TEST("elapsed=599 → drop 1",
         profile_at(chain, CASERT_V11_HEIGHT, 599) == 9);

    // Boundary 600 — drop 2
    TEST("elapsed=600 → drop 2 (H8)",
         profile_at(chain, CASERT_V11_HEIGHT, 600) == 8);
    TEST("elapsed=659 → drop 2",
         profile_at(chain, CASERT_V11_HEIGHT, 659) == 8);

    // Boundary 660 — drop 3
    TEST("elapsed=660 → drop 3 (H7)",
         profile_at(chain, CASERT_V11_HEIGHT, 660) == 7);
    TEST("elapsed=719 → drop 3",
         profile_at(chain, CASERT_V11_HEIGHT, 719) == 7);

    // Boundary 720 — drop 4
    TEST("elapsed=720 → drop 4 (H6)",
         profile_at(chain, CASERT_V11_HEIGHT, 720) == 6);
    TEST("elapsed=779 → drop 4",
         profile_at(chain, CASERT_V11_HEIGHT, 779) == 6);

    // Boundary 780 — drop 5
    TEST("elapsed=780 → drop 5 (H5)",
         profile_at(chain, CASERT_V11_HEIGHT, 780) == 5);
    TEST("elapsed=839 → drop 5",
         profile_at(chain, CASERT_V11_HEIGHT, 839) == 5);

    // Boundary 840 — drop 6
    TEST("elapsed=840 → drop 6 (H4)",
         profile_at(chain, CASERT_V11_HEIGHT, 840) == 4);

    // ---- Linear cascade — keeps growing past 840 s ----
    // 900 s   → drop 7  → H10 - 7 = H3
    TEST("elapsed=900 → drop 7 (H3) — linear, no cap",
         profile_at(chain, CASERT_V11_HEIGHT, 900) == 3);
    // 1020 s  → drop 9  → H10 - 9 = H1
    TEST("elapsed=1020 → drop 9 (H1) — linear",
         profile_at(chain, CASERT_V11_HEIGHT, 1020) == 1);
    // 1080 s  → drop 10 → H10 - 10 = B0
    TEST("elapsed=1080 → drop 10 (B0)",
         profile_at(chain, CASERT_V11_HEIGHT, 1080) == 0);
    // 1140 s  → drop 11 → H10 - 11 = E1
    TEST("elapsed=1140 → drop 11 (E1)",
         profile_at(chain, CASERT_V11_HEIGHT, 1140) == -1);
    // 1500 s  → drop 17 → H10 - 17 = -7 → clamped at E7 (CASERT_H_MIN)
    TEST("elapsed=1500 → drop 17, clamped at E7 floor",
         profile_at(chain, CASERT_V11_HEIGHT, 1500) == CASERT_H_MIN);
    // 3000 s (still below the 3600 s anti-stall threshold) → drop 42,
    // clamped at E7. This isolates the linear-cascade-reaches-floor case
    // from any anti-stall contribution.
    TEST("elapsed=3000 → cascade alone reaches E7 (drop 42, clamped)",
         profile_at(chain, CASERT_V11_HEIGHT, 3000) == CASERT_H_MIN);
    // 9999 s — anti-stall stacks on top, but the cascade has already
    // pinned us at the floor; profile MUST be exactly E7 (cannot go
    // below the floor regardless of how much extra drop accumulates).
    TEST("elapsed=9999 → still at E7 floor (no underflow below CASERT_H_MIN)",
         profile_at(chain, CASERT_V11_HEIGHT, 9999) == CASERT_H_MIN);
}

// ---------------------------------------------------------------------
// Section 2 — pre-V11 height (6999) must keep V10 continuous formula
// V10:  drop = floor((elapsed - 540) / 60),  drop 1 per 60s starting at 600s
//
// Effective drop at elapsed E (V10 with start=600, step=60, per_step=1):
//   E < 600          → drop 0
//   E ∈ [600, 660)   → drop 1
//   E ∈ [660, 720)   → drop 2
//   E ∈ [720, 780)   → drop 3
//   E ∈ [780, 840)   → drop 4
// At E=840 V10 gives drop 5; V11 gives drop 6 → tests must distinguish.
// ---------------------------------------------------------------------
static void test_pre_v11_keeps_v10() {
    printf("\n=== Pre-V11 (height 6999) — V10 continuous formula intact ===\n");

    int64_t pre_v11 = CASERT_V11_HEIGHT - 1;  // 6999
    auto chain = chain_with_lag(pre_v11, /*target_lag=*/10);

    // V10: drop=0 at elapsed=599, drop=1 at elapsed=600, drop=4 at elapsed=839
    TEST("V10 elapsed=599 → drop 0 (H10)",
         profile_at(chain, pre_v11, 599) == 10);
    TEST("V10 elapsed=600 → drop 1 (H9)",
         profile_at(chain, pre_v11, 600) == 9);
    TEST("V10 elapsed=659 → drop 1",
         profile_at(chain, pre_v11, 659) == 9);
    TEST("V10 elapsed=660 → drop 2 (H8)",
         profile_at(chain, pre_v11, 660) == 8);
    TEST("V10 elapsed=720 → drop 3 (H7)",
         profile_at(chain, pre_v11, 720) == 7);
    TEST("V10 elapsed=780 → drop 4 (H6)",
         profile_at(chain, pre_v11, 780) == 6);
    TEST("V10 elapsed=840 → drop 5 (H5) [V11 would give drop 6]",
         profile_at(chain, pre_v11, 840) == 5);

    // Critical — verify pre-V11 boundary differs from V11 at elapsed 540
    // V10: 540 < 600 → drop 0;  V11: 540 → drop 1
    TEST("V10 elapsed=540 → drop 0 (H10) [V11 differs]",
         profile_at(chain, pre_v11, 540) == 10);
}

// ---------------------------------------------------------------------
// Section 3 — floor (CASERT_H_MIN) must clamp deep cascades
// raw_base_H = H13 = 13.  V11 max drop = 6 → max final = 7.  No floor hit.
// raw_base_H = H4 = 4. V11 drop=6 → -2 = E2.
// raw_base_H = E1 = -1. V11 drop=6 → -7 = E7 (floor exactly).
// raw_base_H = E5 = -5. V11 drop=6 → -11 → clamp to E7 (-7).
// ---------------------------------------------------------------------
static void test_floor_clamp() {
    printf("\n=== V11 floor clamp (CASERT_H_MIN = E7 = -7) ===\n");

    // To get raw_base_H = 4, build chain with lag = 4
    {
        auto chain = chain_with_lag(CASERT_V11_HEIGHT, /*target_lag=*/4);
        // V11 elapsed=840 → drop 6 → 4-6 = -2 = E2
        TEST("base=H4 + drop=6 → E2 (no floor)",
             profile_at(chain, CASERT_V11_HEIGHT, 840) == -2);
    }

    // raw_base_H = -1 (E1) → drop 6 → -7 (E7 exact)
    // lag <= 0 sets target_profile = 0 (B0), not negative. So we cannot
    // construct base = E1 directly via lag in V6+. Instead test via the
    // floor clamp behaviour: when raw_base_H is small, the cascade
    // result must be >= CASERT_H_MIN.
    {
        auto chain = chain_with_lag(CASERT_V11_HEIGHT, /*target_lag=*/0);
        // base = B0 = 0, drop=6 → -6, floor at -7 → -6 (no clamp needed)
        TEST("base=B0 + drop=6 → E6 (clamp not yet engaged)",
             profile_at(chain, CASERT_V11_HEIGHT, 840) == -6);
    }
}

// ---------------------------------------------------------------------
// Section 4 — V10/V11 transition is sharp at CASERT_V11_HEIGHT
// ---------------------------------------------------------------------
static void test_transition_sharp() {
    printf("\n=== V11 activation height transition is sharp ===\n");

    // At elapsed=540: V10 gives drop 0, V11 gives drop 1.
    // So profile at h=6999 should be H10, profile at h=7000 should be H9.
    {
        auto chain1 = chain_with_lag(CASERT_V11_HEIGHT - 1, 10);
        auto chain2 = chain_with_lag(CASERT_V11_HEIGHT, 10);
        TEST("h=6999, elapsed=540 → H10 (V10 rule)",
             profile_at(chain1, CASERT_V11_HEIGHT - 1, 540) == 10);
        TEST("h=7000, elapsed=540 → H9 (V11 rule)",
             profile_at(chain2, CASERT_V11_HEIGHT, 540) == 9);
    }

    // At elapsed=840: V10 gives drop 5, V11 gives drop 6
    {
        auto chain1 = chain_with_lag(CASERT_V11_HEIGHT - 1, 10);
        auto chain2 = chain_with_lag(CASERT_V11_HEIGHT, 10);
        TEST("h=6999, elapsed=840 → H5 (V10 drop 5)",
             profile_at(chain1, CASERT_V11_HEIGHT - 1, 840) == 5);
        TEST("h=7000, elapsed=840 → H4 (V11 drop 6)",
             profile_at(chain2, CASERT_V11_HEIGHT, 840) == 4);
    }
}

// ---------------------------------------------------------------------
// Section 5 — compute_v11_cascade_drop helper (single source of truth)
// ---------------------------------------------------------------------
// Direct unit tests on the helper function. The miner and validator
// both call this; any divergence produces a chain split. Test every
// boundary plus extreme values to lock the contract in.
static void test_helper_compute_v11_cascade_drop() {
    printf("\n=== compute_v11_cascade_drop — linear formula ===\n");

    // Below threshold: no relief at all.
    TEST("elapsed=0    → drop 0",      compute_v11_cascade_drop(0)    == 0);
    TEST("elapsed=1    → drop 0",      compute_v11_cascade_drop(1)    == 0);
    TEST("elapsed=539  → drop 0",      compute_v11_cascade_drop(539)  == 0);

    // First step.
    TEST("elapsed=540  → drop 1",      compute_v11_cascade_drop(540)  == 1);
    TEST("elapsed=599  → drop 1",      compute_v11_cascade_drop(599)  == 1);

    // Steps every 60 s.
    TEST("elapsed=600  → drop 2",      compute_v11_cascade_drop(600)  == 2);
    TEST("elapsed=660  → drop 3",      compute_v11_cascade_drop(660)  == 3);
    TEST("elapsed=720  → drop 4",      compute_v11_cascade_drop(720)  == 4);
    TEST("elapsed=780  → drop 5",      compute_v11_cascade_drop(780)  == 5);
    TEST("elapsed=840  → drop 6",      compute_v11_cascade_drop(840)  == 6);

    // Past the legacy cap of 6 — linear keeps growing.
    TEST("elapsed=900  → drop 7",      compute_v11_cascade_drop(900)  == 7);
    TEST("elapsed=960  → drop 8",      compute_v11_cascade_drop(960)  == 8);
    TEST("elapsed=1500 → drop 17",     compute_v11_cascade_drop(1500) == 17);
    // 41 drops from H35 reaches E6, not E7.
    // 42 drops needed for H35 → E7 (3000s elapsed).
    TEST("elapsed=2940 → drop 41 (H35 → E6, one above floor)",
         compute_v11_cascade_drop(2940) == 41);
    TEST("elapsed=3000 → drop 42 (H35 → E7, worst-case reaches floor)",
         compute_v11_cascade_drop(3000) == 42);
    TEST("elapsed=5400 → drop 82",     compute_v11_cascade_drop(5400) == 82);

    // Edge: negative elapsed (clock skew) → 0.
    TEST("elapsed=-100 → drop 0 (no underflow)",
         compute_v11_cascade_drop(-100) == 0);
}

static void test_triangular_cascade_activation() {
    printf("\n=== V11 triangular cascade activation at 7100 ===\n");

    auto pre = chain_with_lag(CASERT_TRIANGULAR_CASCADE_HEIGHT - 1, 10);
    TEST("h=7099, elapsed=600 -> still linear drop 2 (H8)",
         profile_at(pre, CASERT_TRIANGULAR_CASCADE_HEIGHT - 1, 600) == 8);

    auto post = chain_with_lag(CASERT_TRIANGULAR_CASCADE_HEIGHT, 10);
    TEST("h=7100, elapsed=540 -> triangular drop 1 (H9)",
         profile_at(post, CASERT_TRIANGULAR_CASCADE_HEIGHT, 540) == 9);
    TEST("h=7100, elapsed=600 -> triangular drop 3 (H7)",
         profile_at(post, CASERT_TRIANGULAR_CASCADE_HEIGHT, 600) == 7);
    TEST("h=7100, elapsed=660 -> triangular drop 6 (H4)",
         profile_at(post, CASERT_TRIANGULAR_CASCADE_HEIGHT, 660) == 4);
    TEST("h=7100, elapsed=720 -> triangular drop 10 (B0)",
         profile_at(post, CASERT_TRIANGULAR_CASCADE_HEIGHT, 720) == 0);
    TEST("h=7100, elapsed=840 -> triangular reaches E7 floor",
         profile_at(post, CASERT_TRIANGULAR_CASCADE_HEIGHT, 840) == CASERT_H_MIN);
}

int main() {
    printf("\n=== cASERT V11 Cascade Tests ===\n");
    printf("Activation height: %lld\n", (long long)CASERT_V11_HEIGHT);

    test_v11_cascade_boundaries();
    test_pre_v11_keeps_v10();
    test_floor_clamp();
    test_transition_sharp();
    test_helper_compute_v11_cascade_drop();
    test_triangular_cascade_activation();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
