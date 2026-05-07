// V13 lottery cooldown fork — boundary tests against the consensus path.
//
// V13 hard fork @ block 12 000 changes
// LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW from 5 to 6 via the helper
// sost::lottery_exclusion_window_at(height) (params.h).
//
// This test exercises the FULL eligibility computation path —
// sost::lottery::compute_lottery_eligibility_set + the helper — to
// confirm that:
//
//   1. The helper returns the right window at the boundary heights
//      (already covered by test_v13_helpers.cpp; included here as a
//      smoke check on the consensus link).
//
//   2. Pre-fork (h = 11 999): eligibility excludes miners of [h-5, h-1]
//      and KEEPS the miner of h-6 and earlier.
//
//   3. Post-fork (h = 12 000): eligibility excludes miners of [h-6, h-1]
//      (one extra block back) and KEEPS the miner of h-7 and earlier.
//
//   4. The pre-fork eligibility output is bit-identical whether built
//      with the helper or with the constant directly — proves the wire-up
//      did not regress pre-V13 behaviour.
//
//   5. The post-fork eligibility output is bit-identical whether built
//      with the helper-derived window (6) or with a literal 6 — proves
//      the wire-up adds no surprise.
//
// The synthetic chain is: at heights 11992..11999 (eight blocks), each
// mined by a distinct address M0..M7 in ascending-height order, where
// M7 is the most recent miner. We then compute eligibility at h = 11 999
// and h = 12 000. The current-block miner is irrelevant under C7.1;
// passed as zero pkh.

#include "sost/lottery.h"
#include "sost/params.h"

#include <cstdio>
#include <cstring>
#include <vector>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static PubKeyHash mk_pkh(uint8_t seed) {
    PubKeyHash p{};
    for (size_t i = 0; i < p.size(); ++i) p[i] = (uint8_t)(seed ^ (i * 11));
    return p;
}

static Bytes32 mk_hash(uint8_t seed) {
    Bytes32 h{};
    for (size_t i = 0; i < h.size(); ++i) h[i] = (uint8_t)(seed ^ (i * 13));
    return h;
}

static LotteryMinedBlockView mk_block(int64_t height, const PubKeyHash& miner) {
    LotteryMinedBlockView b;
    b.height     = height;
    b.miner_pkh  = miner;
    b.block_hash = mk_hash((uint8_t)(height & 0xFF));
    return b;
}

static bool contains_pkh(const std::vector<LotteryEligibilityEntry>& v,
                         const PubKeyHash& pkh) {
    for (const auto& e : v) {
        if (e.pkh == pkh) return true;
    }
    return false;
}

// Build the synthetic chain: heights 11992..11999, each mined by a
// distinct address. Returns the chain plus the eight miners in
// ascending-height order so callers can refer to them by name.
struct Fixture {
    std::vector<LotteryMinedBlockView> chain;
    PubKeyHash M[8];   // M[i] mined height (V13_HEIGHT - 8 + i)
};

static Fixture build_fixture() {
    Fixture f;
    // Distinct seeds keep the lex order well-defined and stable.
    for (uint8_t i = 0; i < 8; ++i) {
        f.M[i] = mk_pkh((uint8_t)(0x40 + i));
    }
    // Heights V13_HEIGHT-8 .. V13_HEIGHT-1, i.e. 11992..11999.
    const int64_t base = V13_HEIGHT - 8;
    for (int i = 0; i < 8; ++i) {
        f.chain.push_back(mk_block(base + i, f.M[i]));
    }
    return f;
}

// ---------------------------------------------------------------------------
// Smoke check: the helper returns the window the consensus layer expects
// at the boundary heights.
// ---------------------------------------------------------------------------
static void test_helper_smoke() {
    printf("\n=== Helper smoke check at the consensus boundary ===\n");
    TEST("lottery_exclusion_window_at(11999) == 5",
         lottery_exclusion_window_at(11999) == 5);
    TEST("lottery_exclusion_window_at(12000) == 6",
         lottery_exclusion_window_at(12000) == 6);
}

// ---------------------------------------------------------------------------
// Pre-fork case: window = 5, excludes [h-5, h-1].
// At h = 11999, miners of heights 11994..11998 are excluded.
// Miner of height 11993 (= h-6) is KEPT.
// Miner of height 11992 (= h-7) is KEPT.
// ---------------------------------------------------------------------------
static void test_pre_fork_h11999_window5() {
    printf("\n=== Pre-fork h=11999 — window must be 5, excludes h-1..h-5 ===\n");
    auto f = build_fixture();
    PubKeyHash zero_pkh{};
    auto eligible = compute_lottery_eligibility_set(
        f.chain, /*height=*/11999, zero_pkh,
        /*exclusion_window=*/lottery_exclusion_window_at(11999));

    // h-1=11998 (M[6]), h-2=11997 (M[5]), h-3=11996 (M[4]),
    // h-4=11995 (M[3]), h-5=11994 (M[2]) — all excluded.
    TEST("excludes miner of h-1 (M[6])", !contains_pkh(eligible, f.M[6]));
    TEST("excludes miner of h-2 (M[5])", !contains_pkh(eligible, f.M[5]));
    TEST("excludes miner of h-3 (M[4])", !contains_pkh(eligible, f.M[4]));
    TEST("excludes miner of h-4 (M[3])", !contains_pkh(eligible, f.M[3]));
    TEST("excludes miner of h-5 (M[2])", !contains_pkh(eligible, f.M[2]));

    // h-6=11993 (M[1]) — boundary just outside the window. KEPT.
    // h-7=11992 (M[0]) — older. KEPT.
    TEST("keeps miner of h-6 (M[1]) — pre-V13 window does NOT reach back this far",
         contains_pkh(eligible, f.M[1]));
    TEST("keeps miner of h-7 (M[0])",
         contains_pkh(eligible, f.M[0]));
}

// ---------------------------------------------------------------------------
// Post-fork case: window = 6, excludes [h-6, h-1].
// At h = 12000, miners of heights 11994..11999 are excluded.
// Miner of height 11993 (= h-7) is KEPT.
// Miner of height 11992 (= h-8) is KEPT.
// ---------------------------------------------------------------------------
static void test_post_fork_h12000_window6() {
    printf("\n=== Post-fork h=12000 — window must be 6, excludes h-1..h-6 ===\n");
    auto f = build_fixture();
    PubKeyHash zero_pkh{};
    auto eligible = compute_lottery_eligibility_set(
        f.chain, /*height=*/12000, zero_pkh,
        /*exclusion_window=*/lottery_exclusion_window_at(12000));

    // h-1=11999 (M[7]) ... h-6=11994 (M[2]) — all excluded post-V13.
    TEST("excludes miner of h-1 (M[7])", !contains_pkh(eligible, f.M[7]));
    TEST("excludes miner of h-2 (M[6])", !contains_pkh(eligible, f.M[6]));
    TEST("excludes miner of h-3 (M[5])", !contains_pkh(eligible, f.M[5]));
    TEST("excludes miner of h-4 (M[4])", !contains_pkh(eligible, f.M[4]));
    TEST("excludes miner of h-5 (M[3])", !contains_pkh(eligible, f.M[3]));
    TEST("excludes miner of h-6 (M[2]) — post-V13 reaches one block further than pre-V13",
         !contains_pkh(eligible, f.M[2]));

    // h-7=11993 (M[1]) — boundary just outside the post-V13 window. KEPT.
    // h-8=11992 (M[0]) — older. KEPT.
    TEST("keeps miner of h-7 (M[1])",
         contains_pkh(eligible, f.M[1]));
    TEST("keeps miner of h-8 (M[0])",
         contains_pkh(eligible, f.M[0]));
}

// ---------------------------------------------------------------------------
// Wire-up regression checks: the helper must produce the SAME eligibility
// set as the constant when called pre-V13, and the SAME set as a literal
// 6 when called post-V13. This catches a class of bugs where the helper's
// arithmetic accidentally diverges from the underlying constant.
// ---------------------------------------------------------------------------
static void test_helper_vs_literal_pre_fork() {
    printf("\n=== Wire-up regression — pre-fork helper output == window=5 literal ===\n");
    auto f = build_fixture();
    PubKeyHash zero_pkh{};

    auto via_helper = compute_lottery_eligibility_set(
        f.chain, /*height=*/11999, zero_pkh,
        /*window=*/lottery_exclusion_window_at(11999));
    auto via_const  = compute_lottery_eligibility_set(
        f.chain, /*height=*/11999, zero_pkh,
        /*window=*/LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW);

    bool same_size = (via_helper.size() == via_const.size());
    TEST("pre-fork helper and pre-fork constant produce same-sized eligibility set",
         same_size);

    bool same_contents = same_size;
    if (same_size) {
        for (size_t i = 0; i < via_helper.size(); ++i) {
            if (via_helper[i].pkh != via_const[i].pkh) {
                same_contents = false;
                break;
            }
        }
    }
    TEST("pre-fork helper and pre-fork constant produce byte-identical eligibility set",
         same_contents);
}

static void test_helper_vs_literal_post_fork() {
    printf("\n=== Wire-up regression — post-fork helper output == window=6 literal ===\n");
    auto f = build_fixture();
    PubKeyHash zero_pkh{};

    auto via_helper  = compute_lottery_eligibility_set(
        f.chain, /*height=*/12000, zero_pkh,
        /*window=*/lottery_exclusion_window_at(12000));
    auto via_literal = compute_lottery_eligibility_set(
        f.chain, /*height=*/12000, zero_pkh,
        /*window=*/6);

    bool same_size = (via_helper.size() == via_literal.size());
    TEST("post-fork helper and literal 6 produce same-sized eligibility set",
         same_size);

    bool same_contents = same_size;
    if (same_size) {
        for (size_t i = 0; i < via_helper.size(); ++i) {
            if (via_helper[i].pkh != via_literal[i].pkh) {
                same_contents = false;
                break;
            }
        }
    }
    TEST("post-fork helper and literal 6 produce byte-identical eligibility set",
         same_contents);
}

// ---------------------------------------------------------------------------
// is_recent_reward_winner pinning at the boundary — the audit RPC and
// any future caller that introspects the cooldown set MUST match the
// eligibility helper. Pin behavior at h-6 across the fork.
// ---------------------------------------------------------------------------
static void test_is_recent_reward_winner_boundary() {
    printf("\n=== is_recent_reward_winner — h-6 cross-fork pin ===\n");
    auto f = build_fixture();

    // Pre-fork h=11999: M[1] mined at h-6=11993. window=5 → NOT a recent winner.
    TEST("pre-fork: M[1] (h-6) is NOT a recent winner under window=5",
         !is_recent_reward_winner(f.chain, f.M[1], /*height=*/11999, /*window=*/5));

    // Post-fork h=12000: M[2] mined at h-6=11994. window=6 → IS a recent winner.
    TEST("post-fork: M[2] (h-6) IS a recent winner under window=6",
         is_recent_reward_winner(f.chain, f.M[2], /*height=*/12000, /*window=*/6));

    // Post-fork h=12000: M[1] mined at h-7=11993. window=6 → NOT a recent winner.
    TEST("post-fork: M[1] (h-7) is NOT a recent winner under window=6",
         !is_recent_reward_winner(f.chain, f.M[1], /*height=*/12000, /*window=*/6));
}

int main() {
    printf("\n=== V13 lottery cooldown fork — consensus boundary tests ===\n");

    test_helper_smoke();
    test_pre_fork_h11999_window5();
    test_post_fork_h12000_window6();
    test_helper_vs_literal_pre_fork();
    test_helper_vs_literal_post_fork();
    test_is_recent_reward_winner_boundary();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
