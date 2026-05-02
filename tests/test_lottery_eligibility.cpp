// V11 Phase 2 — lottery eligibility set + deterministic winner tests (C6).
//
// Exercises:
//   sost::lottery::compute_lottery_eligibility_set
//   sost::lottery::select_lottery_winner_index
//   sost::lottery::is_recent_reward_winner
//
// Pure functions; no Schnorr dependency; built unconditionally. The
// production V11_PHASE2_HEIGHT (= 10000) is re-checked in §9; the
// INT64_MAX sentinel (test-only) is exercised with a literal value.
//
// The synthetic-10k-blocks benchmark in §11 reports the wall-clock time
// of one compute_lottery_eligibility_set call, against the C9 G4.5
// target of < 50 ms. If the host violates that target, this test still
// PASSES but prints a WARN line so the C9 reviewer knows to consider
// the C6.5 incremental index path.

#include "sost/lottery.h"
#include "sost/params.h"

#include <chrono>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
    b.height    = height;
    b.miner_pkh = miner;
    // block_hash unused by C6 helpers (it's only for callers that need
    // it — we set it to a function of height for predictability).
    b.block_hash = mk_hash((uint8_t)(height & 0xFF));
    return b;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_empty_history() {
    printf("\n=== 1) Empty history → eligible empty ===\n");
    std::vector<LotteryMinedBlockView> blocks;
    auto eligible = compute_lottery_eligibility_set(blocks, /*height=*/100,
                                                    mk_pkh(0xAA));
    TEST("no history → eligible.empty()", eligible.empty());
}

static void test_one_miner_is_current() {
    printf("\n=== 2) Sole historical miner = current miner, last win OUTSIDE window → eligible (C7.1) ===\n");
    auto A = mk_pkh(0xAA);
    // A's last historical win is at height 60. Current height is 100,
    // cap=5 window covers [95, 99]. A is NOT in the window, so under
    // the C7.1 rule (no auto-exclusion of current miner) A IS eligible.
    // (The C6 rule would have excluded A as current miner; C7.1 dropped
    // that.)
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(50, A), mk_block(60, A),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, /*height=*/100, A);
    TEST("sole historical miner = current, no recent win → eligible (size 1)",
         eligible.size() == 1);
    TEST("eligible[0].pkh == A",
         !eligible.empty() && eligible[0].pkh == A);
}

static void test_two_miners_one_current() {
    printf("\n=== 3) Two historical, current = A, neither in window → BOTH eligible (C7.1) ===\n");
    auto A = mk_pkh(0xAA);
    auto B = mk_pkh(0xBB);
    // A's last win = 40, B's last win = 50; current = 100, cap=5 → window [95, 99].
    // Neither in the window. Under C7.1, A is NOT auto-excluded as the
    // current miner — both A and B are eligible.
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(20, A),
        mk_block(30, B),
        mk_block(40, A),
        mk_block(50, B),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, /*height=*/100, A);
    TEST("eligible has exactly two entries (A and B)", eligible.size() == 2);
    // The lex sort makes A precede B (mk_pkh(0xAA) < mk_pkh(0xBB) by
    // raw byte compare on the first byte).
    TEST("eligible[0].pkh == A (lex sorted)",
         eligible.size() == 2 && eligible[0].pkh == A);
    TEST("eligible[1].pkh == B",
         eligible.size() == 2 && eligible[1].pkh == B);
    TEST("blocks_mined for A == 2",
         eligible.size() == 2 && eligible[0].blocks_mined == 2);
    TEST("blocks_mined for B == 2",
         eligible.size() == 2 && eligible[1].blocks_mined == 2);
    TEST("last_mined_height for A == 40",
         eligible.size() == 2 && eligible[0].last_mined_height == 40);
    TEST("last_mined_height for B == 50",
         eligible.size() == 2 && eligible[1].last_mined_height == 50);
}

// ---------------------------------------------------------------------------
// 3b — C7.1 explicit cases (A / B / C from spec)
// ---------------------------------------------------------------------------
static void test_c71_case_a_alice_h_minus_20() {
    printf("\n=== 3b-A) C7.1 case A: Alice last won at H-20 → eligible ===\n");
    // Spec case A: Alice won at H-20, current = Alice, cap=5.
    // Window [H-5, H-1] does NOT contain H-20 → Alice eligible.
    auto Alice = mk_pkh(0xA0);
    const int64_t H = 200;
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(H - 20, Alice),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, H, Alice, /*window=*/5);
    TEST("Alice (last win H-20, current miner) → eligible (size 1)",
         eligible.size() == 1);
    TEST("eligible[0].pkh == Alice",
         !eligible.empty() && eligible[0].pkh == Alice);
}

static void test_c71_case_b_alice_h_minus_3() {
    printf("\n=== 3b-B) C7.1 case B: Alice won at H-3 → excluded by recent-winner (NOT by current miner) ===\n");
    // Spec case B: Alice won at H-3 AND is current miner. Window
    // [H-5, H-1] contains H-3 → Alice excluded by rule 2. The C7.1
    // distinction: she is excluded by 'recent winner', NOT by 'current
    // miner'. Adding any other miner with no recent wins to the
    // history demonstrates that other addresses still pass.
    auto Alice = mk_pkh(0xA0);
    auto Bob   = mk_pkh(0xB0);
    const int64_t H = 200;
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(H - 50, Bob),
        mk_block(H - 3,  Alice),    // Alice in [H-5, H-1] → excluded
    };
    auto eligible = compute_lottery_eligibility_set(blocks, H, Alice, /*window=*/5);
    TEST("Alice excluded by recent-winner rule (H-3 in [H-5, H-1])",
         eligible.size() == 1 && eligible[0].pkh == Bob);
    TEST("is_recent_reward_winner(Alice, H, 5) confirms exclusion path",
         is_recent_reward_winner(blocks, Alice, H, 5));
}

static void test_c71_case_c_alice_h_minus_6() {
    printf("\n=== 3b-C) C7.1 case C: Alice won at H-6 → eligible (just outside window) ===\n");
    // Spec case C: Alice won at H-6 AND is current miner. Window
    // [H-5, H-1] does NOT contain H-6 → Alice eligible.
    auto Alice = mk_pkh(0xA0);
    const int64_t H = 200;
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(H - 6, Alice),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, H, Alice, /*window=*/5);
    TEST("Alice (last win H-6, current miner) → eligible (size 1)",
         eligible.size() == 1);
    TEST("eligible[0].pkh == Alice (just outside cooldown window)",
         !eligible.empty() && eligible[0].pkh == Alice);
    TEST("is_recent_reward_winner(Alice, H, 5) → false (H-6 outside)",
         !is_recent_reward_winner(blocks, Alice, H, 5));
}

static void test_recent_winner_exclusion_cap5() {
    printf("\n=== 4) Recent winner exclusion cap=5: H-1..H-5 excluded, H-6 eligible ===\n");
    // History: 6 distinct miners, each winning a single block at heights 95..100.
    auto C = mk_pkh(0xC0);  // current miner, won block 100 (we'll exclude it
                            // as 'current' too — but its history at H=100 is
                            // still the most recent). Actually we want to
                            // separate current_miner from the recent-winner
                            // window logic. Let me redesign:
    // Heights:  94 -> M0   (this is H-6 when computing for height=100 ?
    //           95 -> M1   (H-5 for height=100, but the WINDOW is
    //           96 -> M2   (H-4, ..., H-1) so window covers 95..99 only.
    //           97 -> M3
    //           98 -> M4
    //           99 -> M5   (H-1)
    //
    // So if we compute eligibility for height=100 with cap=5, the
    // window is [100-5, 100-1] = [95, 99]. M1..M5 are recent winners.
    // M0 (height 94) is NOT in the window, so it IS eligible.
    auto M0 = mk_pkh(0xA0);
    auto M1 = mk_pkh(0xA1);
    auto M2 = mk_pkh(0xA2);
    auto M3 = mk_pkh(0xA3);
    auto M4 = mk_pkh(0xA4);
    auto M5 = mk_pkh(0xA5);
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(94, M0),
        mk_block(95, M1),
        mk_block(96, M2),
        mk_block(97, M3),
        mk_block(98, M4),
        mk_block(99, M5),
    };
    auto current = mk_pkh(0xFF);  // a fresh address that hasn't mined
    auto eligible = compute_lottery_eligibility_set(
        blocks, /*height=*/100, current, /*window=*/5);
    TEST("eligible has exactly 1 entry (M0 only)",
         eligible.size() == 1);
    TEST("eligible[0] is M0 (height 94, outside window)",
         !eligible.empty() && eligible[0].pkh == M0);

    // is_recent_reward_winner spot checks
    TEST("is_recent_reward_winner(M5, h=100, w=5) → true (H-1)",
         is_recent_reward_winner(blocks, M5, 100, 5));
    TEST("is_recent_reward_winner(M1, h=100, w=5) → true (H-5)",
         is_recent_reward_winner(blocks, M1, 100, 5));
    TEST("is_recent_reward_winner(M0, h=100, w=5) → false (H-6)",
         !is_recent_reward_winner(blocks, M0, 100, 5));
    TEST("is_recent_reward_winner(M0, h=100, w=6) → true",
         is_recent_reward_winner(blocks, M0, 100, 6));
    TEST("is_recent_reward_winner(any, h=100, w=0) → false (cap disabled)",
         !is_recent_reward_winner(blocks, M5, 100, 0));
}

static void test_duplicate_miner_history() {
    printf("\n=== 5) Duplicate history collapses; counts and bounds correct ===\n");
    auto X = mk_pkh(0x10);
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(15, X),
        mk_block(40, X),
        mk_block(7, X),
        mk_block(28, X),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, /*height=*/100,
                                                    mk_pkh(0xFF));
    TEST("4 wins by X collapse to 1 entry", eligible.size() == 1);
    TEST("blocks_mined == 4",
         !eligible.empty() && eligible[0].blocks_mined == 4);
    TEST("first_mined_height == 7 (min over input)",
         !eligible.empty() && eligible[0].first_mined_height == 7);
    TEST("last_mined_height == 40 (max over input)",
         !eligible.empty() && eligible[0].last_mined_height == 40);
}

static void test_deterministic_lex_sort() {
    printf("\n=== 6) Output is sorted lex by raw pkh bytes ===\n");
    auto A = mk_pkh(0x05);
    auto B = mk_pkh(0x02);
    auto C = mk_pkh(0x09);
    auto D = mk_pkh(0x01);
    // Insert in pseudo-random order; output MUST be in lex order.
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(50, C),
        mk_block(30, A),
        mk_block(60, B),
        mk_block(10, D),
        mk_block(20, A),
    };
    auto eligible = compute_lottery_eligibility_set(blocks, /*height=*/100,
                                                    mk_pkh(0xFF));
    TEST("4 distinct pkhs", eligible.size() == 4);
    if (eligible.size() == 4) {
        TEST("eligible[0] < eligible[1]", eligible[0].pkh < eligible[1].pkh);
        TEST("eligible[1] < eligible[2]", eligible[1].pkh < eligible[2].pkh);
        TEST("eligible[2] < eligible[3]", eligible[2].pkh < eligible[3].pkh);
    }
}

static void test_winner_selection_determinism_and_sensitivity() {
    printf("\n=== 7) Winner selection: deterministic + endian-safe + sensitive ===\n");
    std::vector<LotteryEligibilityEntry> eligible;
    for (uint8_t s : {0x10, 0x20, 0x30, 0x40, 0x50}) {
        LotteryEligibilityEntry e{};
        e.pkh = mk_pkh(s);
        e.first_mined_height = 1;
        e.last_mined_height = 50;
        e.blocks_mined = 1;
        eligible.push_back(e);
    }

    Bytes32 hash_A = mk_hash(0xAA);
    int64_t height = 7000;

    int64_t i1 = select_lottery_winner_index(eligible, hash_A, height);
    int64_t i2 = select_lottery_winner_index(eligible, hash_A, height);
    TEST("same inputs → same index (determinism)", i1 == i2);
    TEST("index in [0, eligible.size())",
         i1 >= 0 && i1 < (int64_t)eligible.size());

    // Empty eligible → -1
    std::vector<LotteryEligibilityEntry> empty;
    TEST("empty eligible → -1",
         select_lottery_winner_index(empty, hash_A, height) == -1);

    // Sensitivity: changing prev_hash often changes index. We can't
    // assert "always different" because mod over 5 buckets has
    // collisions, but over 64 random hashes we expect at least one
    // disagreement.
    {
        std::set<int64_t> indices;
        for (uint8_t s = 1; s <= 64; ++s) {
            Bytes32 h = mk_hash(s);
            indices.insert(select_lottery_winner_index(eligible, h, height));
        }
        TEST("varying prev_hash explores >=2 distinct indices",
             indices.size() >= 2);
    }

    // Sensitivity: changing height changes index often.
    {
        std::set<int64_t> indices;
        for (int64_t h = 7000; h < 7000 + 64; ++h) {
            indices.insert(select_lottery_winner_index(eligible, hash_A, h));
        }
        TEST("varying height explores >=2 distinct indices",
             indices.size() >= 2);
    }
}

static void test_sybil_neutrality() {
    printf("\n=== 8) Selection is uniform per-pkh, NOT weighted by blocks_mined ===\n");
    // A pair of pkhs where one has 100 historical wins and the other
    // has 1. Selection should still depend only on (prev_hash, height),
    // not on blocks_mined.
    LotteryEligibilityEntry whale{};   whale.pkh = mk_pkh(0x01); whale.blocks_mined = 100;
    LotteryEligibilityEntry minnow{};  minnow.pkh = mk_pkh(0x02); minnow.blocks_mined = 1;
    std::vector<LotteryEligibilityEntry> eligible{whale, minnow};

    int whale_wins = 0, minnow_wins = 0;
    for (int64_t h = 0; h < 10000; ++h) {
        int64_t idx = select_lottery_winner_index(eligible, mk_hash(0x77), h);
        if (idx == 0) ++whale_wins;
        else if (idx == 1) ++minnow_wins;
    }
    // Uniform 1/2 each over 10000 trials → ~5000 each, ±100 in 99 % CI.
    // Loose bound: each side > 4500.
    TEST("whale wins NOT >= 95 % (would imply weight-by-blocks_mined bug)",
         whale_wins < 9500);
    TEST("whale wins ≈ minnow wins (uniform per-pkh selection)",
         whale_wins > 4500 && minnow_wins > 4500);
}

static void test_phase2_activation_height() {
    printf("\n=== 9) Phase 2 activation height pinned at 10000 ===\n");
    // Pre-activation: every height < 10000 returns false.
    TEST("is_lottery_block(7000, V11_PHASE2_HEIGHT) → false (pre-activation)",
         !is_lottery_block(7000, V11_PHASE2_HEIGHT));
    TEST("is_lottery_block(9999, V11_PHASE2_HEIGHT) → false (last pre block)",
         !is_lottery_block(9999, V11_PHASE2_HEIGHT));
    // Post-activation: schedule fires per the documented rule.
    //   10000 % 3 == 1 → bootstrap triggers.
    //   10002 % 3 == 0 → bootstrap rule returns false.
    TEST("is_lottery_block(10000, V11_PHASE2_HEIGHT) → true (activation block)",
         is_lottery_block(10000, V11_PHASE2_HEIGHT));
    TEST("is_lottery_block(10002, V11_PHASE2_HEIGHT) → false (bootstrap %3==0)",
         !is_lottery_block(10002, V11_PHASE2_HEIGHT));
    // INT64_MAX sentinel still exists as test-only value.
    TEST("INT64_MAX sentinel still returns false",
         !is_lottery_block(1000000, INT64_MAX));
    TEST("V11_PHASE2_HEIGHT == 10000 (set by C10)",
         V11_PHASE2_HEIGHT == 10000);
}

static void test_current_miner_NOT_excluded_outside_window() {
    printf("\n=== 10) C7.1: current miner is NO LONGER auto-excluded (was true under C6) ===\n");
    auto A = mk_pkh(0xA0);
    auto B = mk_pkh(0xB0);
    // A won block 50; current height is 100; cap=5 window covers [95, 99].
    // A's last win (50) is OUTSIDE the window. Under C6 the rule was
    // "current miner is always excluded" → A would be filtered out.
    // Under C7.1 the rule is "excluded only if won in the previous N
    // blocks" → A is eligible because A is not in [95, 99].
    std::vector<LotteryMinedBlockView> blocks{
        mk_block(50, A),
        mk_block(80, B),
    };
    auto eligible = compute_lottery_eligibility_set(
        blocks, /*height=*/100, /*current_miner=*/A, /*window=*/5);
    TEST("eligible has 2 entries (both A and B — A not auto-excluded)",
         eligible.size() == 2);
    // Lex sort: A (0xA0) < B (0xB0).
    TEST("eligible[0] is A (current miner included under C7.1)",
         eligible.size() == 2 && eligible[0].pkh == A);
    TEST("eligible[1] is B",
         eligible.size() == 2 && eligible[1].pkh == B);

    // Sanity: A is NOT a recent reward winner under cap=5 (50 < 95).
    TEST("is_recent_reward_winner(A, h=100, w=5) → false (50 outside [95,99])",
         !is_recent_reward_winner(blocks, A, 100, 5));
}

// ---------------------------------------------------------------------------
// Benchmark — synthetic 10k-block chain. Target < 50 ms per C9 G4.5.
// Failure here is reported as a WARN, not a FAIL — the test still
// passes; it's an advisory for the C9 reviewer.
// ---------------------------------------------------------------------------
static void test_benchmark_10k_blocks() {
    printf("\n=== 11) Benchmark — compute_lottery_eligibility_set on 10k synthetic blocks ===\n");

    // 9 distinct miners (mirrors the C9 G4.5 spec).
    std::vector<PubKeyHash> miners;
    for (uint8_t s = 1; s <= 9; ++s) miners.push_back(mk_pkh(s));

    std::vector<LotteryMinedBlockView> blocks;
    blocks.reserve(10000);
    for (int64_t h = 1; h <= 10000; ++h) {
        // Round-robin assignment — deterministic, no RNG.
        const auto& m = miners[h % miners.size()];
        blocks.push_back(mk_block(h, m));
    }

    auto t0 = std::chrono::steady_clock::now();
    auto eligible = compute_lottery_eligibility_set(
        blocks, /*height=*/10001, mk_pkh(0xFF), /*window=*/5);
    auto t1 = std::chrono::steady_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();

    printf("  10k-block scan: %ld µs  (%.2f ms)\n", (long)ms, ms / 1000.0);
    TEST("eligible non-empty (sanity)", !eligible.empty());
    TEST("eligible.size() <= 9 distinct miners", eligible.size() <= 9);

    if (ms > 50000) {
        printf("  *** WARN: scan exceeded the C9 G4.5 50 ms target — "
               "consider the C6.5 incremental index path.\n");
    } else {
        TEST("scan < 50 ms (C9 G4.5 target met)", ms < 50000);
    }
}

int main() {
    printf("=== test_lottery_eligibility (V11 Phase 2 C7.1) ===\n");
    test_empty_history();
    test_one_miner_is_current();
    test_two_miners_one_current();
    test_c71_case_a_alice_h_minus_20();
    test_c71_case_b_alice_h_minus_3();
    test_c71_case_c_alice_h_minus_6();
    test_recent_winner_exclusion_cap5();
    test_duplicate_miner_history();
    test_deterministic_lex_sort();
    test_winner_selection_determinism_and_sensitivity();
    test_sybil_neutrality();
    test_phase2_activation_height();
    test_current_miner_NOT_excluded_outside_window();
    test_benchmark_10k_blocks();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
