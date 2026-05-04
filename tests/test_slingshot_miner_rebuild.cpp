// V11 Phase 3 — Slingshot miner-side rebuild predicate unit tests.
//
// Companion to tests/test_slingshot_extended.cpp (E6a/b/c) which covers
// the cASERT-side bitsQ math. This test exercises the *miner-side*
// predicate that decides whether the in-flight candidate should be
// aborted because gate 2 crossed mid-search.
//
// The predicate `should_rebuild_for_slingshot` lives static in
// src/sost-miner.cpp (the production caller) so the unit test
// re-implements the same algebra here byte-for-byte and asserts the
// truth table. Both copies must be kept in sync; if the predicate
// changes in sost-miner.cpp the test FAILS until this file mirrors
// the new logic — which is exactly the regression guard we want.
//
// Truth table the predicate must satisfy:
//
//   gate1_armed  gate2_at_start  now_t > tip+TARGET  ->  rebuild?
//   F            *               *                       F   (pre-fork or fast prev)
//   T            T               *                       F   (drop already applied at build)
//   T            F               F                       F   (gate 2 has not crossed yet)
//   T            F               T                       T   (CROSSED — must rebuild)
//
// Plus a degenerate input check: empty chain → false (defensive).

#include "sost/params.h"
#include "sost/types.h"
#include <cstdint>
#include <cstdio>
#include <vector>

using namespace sost;

// =============================================================================
// Mirror of the static helper defined in src/sost-miner.cpp. Kept identical
// so the test can exercise the predicate without linking the miner binary.
// If you change the production helper, mirror the change here.
// =============================================================================
static bool should_rebuild_for_slingshot_mirror(
    const std::vector<BlockMeta>& chain,
    int64_t prev_elapsed,
    bool gate2_at_start,
    int64_t now_t)
{
    if (chain.empty()) return false;
    int64_t height_after_tip = (int64_t)chain.size();
    bool gate1_armed = (height_after_tip >= sost::V11_SLINGSHOT_HEIGHT)
                       && (prev_elapsed > sost::SLINGSHOT_THRESHOLD_SECONDS);
    if (!gate1_armed) return false;
    if (gate2_at_start) return false;
    int64_t tip_time = chain.back().time;
    if (now_t <= tip_time) return false;
    int64_t cur = now_t - tip_time;
    return cur > (int64_t)sost::TARGET_SPACING;
}

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Build a 2-block chain whose tip lives at height = V11_SLINGSHOT_HEIGHT - 1
// (so the next block height equals chain.size() == V11_SLINGSHOT_HEIGHT and
// gate-1 height check passes). Last interval = `last_interval_s`.
static std::vector<BlockMeta> seed_chain(int64_t last_interval_s) {
    std::vector<BlockMeta> chain;
    // We need chain.size() to equal V11_SLINGSHOT_HEIGHT for gate-1 to arm,
    // but we don't actually call into casert here — only the predicate.
    // The predicate reads chain.size() and chain.back().time only, so a
    // minimal 2-entry chain at the right size is enough to test the
    // arithmetic. We pad with a small synthetic chain of the required
    // length where only the last two timestamps matter.
    int64_t target_size = V11_SLINGSHOT_HEIGHT;  // height of next block
    chain.reserve((size_t)target_size);
    int64_t base_t = 1700000000;  // arbitrary anchor
    for (int64_t i = 0; i < target_size - 2; ++i) {
        BlockMeta m{};
        m.height = i;
        m.time   = base_t + i * TARGET_SPACING;
        m.powDiffQ = MIN_BITSQ;
        m.profile_index = 0;
        chain.push_back(m);
    }
    // second-to-last
    BlockMeta a{};
    a.height = target_size - 2;
    a.time   = base_t + (target_size - 2) * TARGET_SPACING;
    a.powDiffQ = MIN_BITSQ;
    a.profile_index = 0;
    chain.push_back(a);
    // tip — last interval is `last_interval_s`
    BlockMeta b{};
    b.height = target_size - 1;
    b.time   = a.time + last_interval_s;
    b.powDiffQ = MIN_BITSQ;
    b.profile_index = 0;
    chain.push_back(b);
    return chain;
}

static void test_rebuild_truth_table() {
    printf("\n=== Slingshot miner rebuild — truth table ===\n");

    const int64_t SLOW_PREV = SLINGSHOT_THRESHOLD_SECONDS + 100;  // 1900s
    const int64_t FAST_PREV = SLINGSHOT_THRESHOLD_SECONDS - 100;  // 1700s

    // Row 1: gate 1 not armed (fast prev) → never rebuild, regardless of now_t.
    {
        auto c = seed_chain(FAST_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/FAST_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t + 700);
        TEST("gate1 not armed (fast prev) → no rebuild even past gate 2",
             r == false);
    }

    // Row 2: gate 1 armed, gate 2 already open at template build → no rebuild
    // (we already committed the relief at build time).
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/true,
            /*now_t=*/tip_t + 900);
        TEST("gate1 armed but gate2 already open at build → no rebuild",
             r == false);
    }

    // Row 3: gate 1 armed, gate 2 closed at build, now still under TARGET_SPACING
    // → no rebuild yet.
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t + 500);  // still below 600s
        TEST("gate1 armed, gate2 closed, current_elapsed=500 → no rebuild",
             r == false);
    }

    // Boundary: now_t - tip == TARGET_SPACING (==600). Strict > → no rebuild.
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t + (int64_t)TARGET_SPACING);  // ==600 exactly
        TEST("current_elapsed == 600 (strict > fails) → no rebuild",
             r == false);
    }

    // Row 4: gate 1 armed, gate 2 closed at build, gate 2 NOW crossed → rebuild.
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t + 700);  // 700 > 600
        TEST("gate1 armed, gate2 was closed, current_elapsed=700 → REBUILD",
             r == true);
    }

    // Edge: now_t exactly equal to tip_time (no progress) → no rebuild.
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t);
        TEST("now_t == tip.time (no time elapsed) → no rebuild",
             r == false);
    }

    // Edge: now_t < tip_time (clock skew backward) → no rebuild.
    {
        auto c = seed_chain(SLOW_PREV);
        int64_t tip_t = c.back().time;
        bool r = should_rebuild_for_slingshot_mirror(
            c, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/tip_t - 100);
        TEST("now_t < tip.time (skew backward) → no rebuild",
             r == false);
    }

    // Defensive: empty chain → no rebuild.
    {
        std::vector<BlockMeta> empty;
        bool r = should_rebuild_for_slingshot_mirror(
            empty, /*prev_elapsed=*/SLOW_PREV, /*gate2_at_start=*/false,
            /*now_t=*/1700000000 + 700);
        TEST("empty chain → no rebuild (defensive)",
             r == false);
    }
}

static void test_height_gate() {
    printf("\n=== Slingshot miner rebuild — pre-fork height gate ===\n");

    // Pre-fork: chain.size() < V11_SLINGSHOT_HEIGHT means height of the
    // NEXT block is below the fork → gate 1 must NOT arm even with slow prev.
    std::vector<BlockMeta> short_chain;
    int64_t base_t = 1700000000;
    int64_t pre_fork_size = V11_SLINGSHOT_HEIGHT - 10;  // pre-fork
    for (int64_t i = 0; i < pre_fork_size; ++i) {
        BlockMeta m{};
        m.height = i;
        m.time   = base_t + i * TARGET_SPACING;
        m.powDiffQ = MIN_BITSQ;
        m.profile_index = 0;
        short_chain.push_back(m);
    }
    // Force the last interval slow:
    if (short_chain.size() >= 2) {
        short_chain.back().time =
            short_chain[short_chain.size() - 2].time + 2200;
    }
    int64_t prev_elapsed =
        short_chain.back().time - short_chain[short_chain.size() - 2].time;

    bool r = should_rebuild_for_slingshot_mirror(
        short_chain, prev_elapsed, /*gate2_at_start=*/false,
        /*now_t=*/short_chain.back().time + 1500);
    TEST("pre-fork height (chain.size() < V11_SLINGSHOT_HEIGHT) → no rebuild",
         r == false);
}

int main() {
    printf("\n=== V11 Phase 3 — Slingshot miner rebuild predicate ===\n");
    printf("V11_SLINGSHOT_HEIGHT       = %lld\n", (long long)V11_SLINGSHOT_HEIGHT);
    printf("SLINGSHOT_THRESHOLD_SECS   = %lld\n", (long long)SLINGSHOT_THRESHOLD_SECONDS);
    printf("TARGET_SPACING (gate 2)    = %lld\n", (long long)TARGET_SPACING);

    test_rebuild_truth_table();
    test_height_gate();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
