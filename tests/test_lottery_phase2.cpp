// V11 Phase 2 — PoP lottery test stubs.
//
// Spec: docs/V11_SPEC.md §4 + §10.5
// Status: PHASE 2 — implementation pending. Each test below documents
// a property that must hold once src/lottery.cpp is implemented. They
// fail intentionally (EXPECT_TRUE(false /* TODO PHASE 2 */)) so the
// scaffold cannot be silently shipped as "green tests".
//
// Wire-up: this file is NOT added to CMakeLists.txt yet — the tests
// would abort at runtime today. Wire it in the same patch that lands
// the real implementation (see V11_SPEC.md §6 gates G4.1-G4.4).
#include "sost/lottery.h"

#include <cstdio>

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)
#define EXPECT_TRUE(c)  TEST(#c, (c))

int main() {
    printf("=== test_lottery_phase2 (PHASE 2 SKELETON) ===\n");

    // ---- §4.2 trigger schedule -----------------------------------
    printf("[trigger]\n");
    // (1) bootstrap window: 2-of-3 for first 5,000 blocks after H
    EXPECT_TRUE(false /* TODO PHASE 2: for h in [H, H+5000),
                         is_triggered(h) ⟺ (h - H) % 3 != 2 */);
    // (2) steady state: 1-of-3 from H+5000 onwards
    EXPECT_TRUE(false /* TODO PHASE 2: for h >= H+5000,
                         is_triggered(h) ⟺ (h - H) % 3 == 0 */);
    // (3) handoff continuity: last bootstrap height and first steady
    //     height must produce the documented schedule with no gap
    EXPECT_TRUE(false /* TODO PHASE 2: triggered set across the
                         H+4999 → H+5000 handoff matches §4.1 table */);

    // ---- §4.3 / §4.4 eligibility ---------------------------------
    printf("[eligibility]\n");
    // (4) "since genesis" rule
    EXPECT_TRUE(false /* TODO PHASE 2: eligibility_set excludes addrs
                         that have never won a block in [0, h-1] */);
    // (5) 30-block reward exclusion
    EXPECT_TRUE(false /* TODO PHASE 2: any block-reward winner in
                         [h-30, h-1] is excluded from E(h) */);
    // (6) current miner exclusion
    EXPECT_TRUE(false /* TODO PHASE 2: miner of block h itself is
                         excluded from E(h) */);

    // ---- §4.6 winner selection -----------------------------------
    printf("[winner pick]\n");
    // (7) deterministic across nodes given identical chain state
    EXPECT_TRUE(false /* TODO PHASE 2: pick_winner is a pure function of
                         (prev_block_hash, height, sorted E(h)) */);
    // (8) lex-sort + uint64 mod selects the documented index
    EXPECT_TRUE(false /* TODO PHASE 2: index = sha256("SOST/POP-LOTTERY/v11"
                         || prev_hash || height) interpreted as u64 LE,
                         modulo |E(h)| */);
    // (9) empty E(h) returns std::nullopt
    EXPECT_TRUE(false /* TODO PHASE 2: pick_winner returns nullopt iff
                         E(h) is empty (caller then rolls over) */);

    // ---- §10.5 jackpot rollover ----------------------------------
    printf("[rollover]\n");
    // (10) initial pending = 0 at V11_PHASE2_HEIGHT
    EXPECT_TRUE(false /* TODO PHASE 2: RolloverState starts with
                         pending_lottery_amount == 0 at height H */);
    // (11) triggered + non-empty E pays share + pending; pending := 0
    EXPECT_TRUE(false /* TODO PHASE 2: apply_block on triggered+non-empty
                         pays winner = lottery_share + pending_before;
                         pending after = 0 */);
    // (12) triggered + empty E increments pending by lottery_share,
    //      emits no winner output
    EXPECT_TRUE(false /* TODO PHASE 2: apply_block on triggered+empty
                         increments pending; emit_winner_output = false;
                         winner_payout = 0 */);
    // (13) non-triggered block leaves pending unchanged
    EXPECT_TRUE(false /* TODO PHASE 2: apply_block on !triggered keeps
                         pending unchanged regardless of E(h) */);
    // (14) reorg via undo_block restores pre-block pending
    EXPECT_TRUE(false /* TODO PHASE 2: apply_block then undo_block with
                         the saved pending_before_block restores state */);
    // (15) rollover has no cap — pending grows indefinitely if needed
    EXPECT_TRUE(false /* TODO PHASE 2: 100 consecutive triggered+empty
                         blocks accumulate the full sum into pending */);

    printf("\n=== Lottery Phase 2: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
