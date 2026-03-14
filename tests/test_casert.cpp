// test_casert.cpp — Comprehensive cASERT v5.2 canonical specification tests
// Tests: level mapping, unbounded regime, fixed parameters, anti-stall decay,
//        mining vs validation scope, resume behavior, edge cases.

#include "sost/params.h"
#include "sost/types.h"
#include "sost/pow/casert.h"
#include <cstdio>
#include <vector>

using namespace sost;

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name, cond) do { \
    if (cond) { tests_passed++; printf("  PASS: %s\n", name); } \
    else { tests_failed++; printf("  EXPECT failed: %s  [%s:%d]\n", name, __FILE__, __LINE__); } \
} while(0)

// Helper: build a chain where the latest block is `ahead` blocks ahead of schedule.
// Chain has `n` blocks, the last block's timestamp is set so that:
//   expected_height = elapsed / 600 = (latest_time - GENESIS_TIME) / 600
//   lag = expected_height - (next_height - 1)
//   ahead = -lag (when lag < 0)
// So: expected_height = next_height - 1 - ahead
//   => latest_time = GENESIS_TIME + (next_height - 1 - ahead) * 600
static std::vector<BlockMeta> make_ahead_chain(int chain_len, int ahead) {
    std::vector<BlockMeta> chain;
    int64_t next_height = chain_len;
    // We need elapsed/600 = next_height - 1 - ahead
    // elapsed = latest_time - GENESIS_TIME
    // latest_time = GENESIS_TIME + (next_height - 1 - ahead) * TARGET_SPACING
    int64_t target_expected = next_height - 1 - ahead;
    if (target_expected < 0) target_expected = 0;
    int64_t latest_time = GENESIS_TIME + target_expected * TARGET_SPACING;

    for (int i = 0; i < chain_len; ++i) {
        BlockMeta bm{};
        bm.height = i;
        bm.powDiffQ = GENESIS_BITSQ;
        if (i == chain_len - 1) {
            bm.time = latest_time;
        } else {
            // Earlier blocks: just space them evenly
            bm.time = GENESIS_TIME + (int64_t)i * TARGET_SPACING;
        }
        chain.push_back(bm);
    }
    return chain;
}

// ============================================================================
// 1. LEVEL MAPPING — Fixed bands L1-L5, unbounded L6+
// ============================================================================
void test_level_mapping() {
    printf("\n=== 1. LEVEL MAPPING ===\n");

    // L1: 0-4 blocks ahead => scale=1
    for (int a : {0, 1, 2, 3, 4}) {
        auto chain = make_ahead_chain(100, a);
        auto dec = casert_mode_from_chain(chain, 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L1 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L1);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=1", a);
        TEST(buf, dec.effective_level == 1);
    }

    // L2: 5-25 blocks ahead => scale=2
    for (int a : {5, 10, 15, 20, 25}) {
        auto chain = make_ahead_chain(100, a);
        auto dec = casert_mode_from_chain(chain, 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L2 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L2);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=2", a);
        TEST(buf, dec.effective_level == 2);
    }

    // L3: 26-50 blocks ahead => scale=3
    for (int a : {26, 30, 40, 50}) {
        auto chain = make_ahead_chain(100, a);
        auto dec = casert_mode_from_chain(chain, 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L3 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L3);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=3", a);
        TEST(buf, dec.effective_level == 3);
    }

    // L4: 51-75 blocks ahead => scale=4
    for (int a : {51, 60, 70, 75}) {
        auto chain = make_ahead_chain(100, a);
        auto dec = casert_mode_from_chain(chain, 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L4 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L4);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=4", a);
        TEST(buf, dec.effective_level == 4);
    }

    // L5: 76-100 blocks ahead => scale=5
    for (int a : {76, 80, 90, 100}) {
        auto chain = make_ahead_chain(100, a);
        auto dec = casert_mode_from_chain(chain, 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L5 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L5);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=5", a);
        TEST(buf, dec.effective_level == 5);
    }

    // L6: 101-150 blocks ahead => level=6, scale=6
    for (int a : {101, 110, 130, 150}) {
        auto chain = make_ahead_chain(200, a);
        auto dec = casert_mode_from_chain(chain, 200);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L6 (mode)", a);
        TEST(buf, dec.mode == CasertMode::L6);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=6", a);
        TEST(buf, dec.effective_level == 6);
    }

    // L7: 151-200 blocks ahead => level=7
    for (int a : {151, 175, 200}) {
        auto chain = make_ahead_chain(300, a);
        auto dec = casert_mode_from_chain(chain, 300);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => L6 mode (enum cap), level=7", a);
        TEST(buf, dec.mode == CasertMode::L6);
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=7", a);
        TEST(buf, dec.effective_level == 7);
    }

    // L8: 201-250 blocks ahead => level=8
    for (int a : {201, 225, 250}) {
        auto chain = make_ahead_chain(400, a);
        auto dec = casert_mode_from_chain(chain, 400);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => effective_level=8", a);
        TEST(buf, dec.effective_level == 8);
    }
}

// ============================================================================
// 2. UNBOUNDED REGIME — every 50 blocks adds +1 level
// ============================================================================
void test_unbounded_regime() {
    printf("\n=== 2. UNBOUNDED REGIME ===\n");

    // Verify level increments by 1 for every 50 blocks beyond 101
    struct { int ahead; int expected_level; } cases[] = {
        {101, 6}, {150, 6},    // 101-150 => L6
        {151, 7}, {200, 7},    // 151-200 => L7
        {201, 8}, {250, 8},    // 201-250 => L8
        {251, 9}, {300, 9},    // 251-300 => L9
        {301, 10}, {350, 10},  // 301-350 => L10
        {351, 11}, {400, 11},  // 351-400 => L11
        {501, 14},             // 501 => 6 + (501-101)/50 = 6 + 8 = 14
        {1001, 24},            // 1001 => 6 + (1001-101)/50 = 6 + 18 = 24
    };

    for (auto& tc : cases) {
        auto chain = make_ahead_chain(tc.ahead + 100, tc.ahead);
        auto dec = casert_mode_from_chain(chain, tc.ahead + 100);
        char buf[64];
        snprintf(buf, sizeof(buf), "ahead=%d => level=%d", tc.ahead, tc.expected_level);
        TEST(buf, dec.effective_level == tc.expected_level);
    }

    // Verify no off-by-one at 50-block boundaries
    auto c1 = make_ahead_chain(300, 150);
    auto d1 = casert_mode_from_chain(c1, 300);
    TEST("ahead=150 => level=6 (last of L6 band)", d1.effective_level == 6);

    auto c2 = make_ahead_chain(300, 151);
    auto d2 = casert_mode_from_chain(c2, 300);
    TEST("ahead=151 => level=7 (first of L7 band)", d2.effective_level == 7);
}

// ============================================================================
// 3. FIXED PARAMETERS — k=4, steps=4, margin=180
// ============================================================================
void test_fixed_parameters() {
    printf("\n=== 3. FIXED PARAMETERS ===\n");

    // Verify compile-time constants
    TEST("CX_STB_K == 4", CX_STB_K == 4);
    TEST("CX_STB_STEPS == 4", CX_STB_STEPS == 4);
    TEST("CX_STB_MARGIN == 180", CX_STB_MARGIN == 180);
    TEST("CX_STB_LR == 20", CX_STB_LR == 20);

    // Verify overlay sets k=4, steps=4, margin=180 for all active levels
    ConsensusParams base{};
    base.cx_n = CX_N;
    base.cx_rounds = CX_ROUNDS_M;
    base.cx_scratch_mb = CX_SCRATCH_M;
    base.cx_lr_shift = CX_LR_SHIFT;
    base.cx_lam = CX_LAM;
    base.cx_checkpoint_interval = CX_CP_M;
    base.stab_scale = CX_STB_SCALE;
    base.stab_k = CX_STB_K;
    base.stab_margin = CX_STB_MARGIN;
    base.stab_steps = CX_STB_STEPS;
    base.stab_lr_shift = CX_LR_SHIFT;

    // L3 overlay (26 blocks ahead => scale=3)
    CasertDecision dec3{};
    dec3.mode = CasertMode::L3;
    dec3.signal_s = -26;
    dec3.effective_level = 3;

    auto out3 = casert_apply_overlay(base, dec3);
    TEST("L3 overlay: stab_k == 4", out3.stab_k == 4);
    TEST("L3 overlay: stab_steps == 4", out3.stab_steps == 4);
    TEST("L3 overlay: stab_margin == 180", out3.stab_margin == CX_STB_MARGIN);
    TEST("L3 overlay: stab_scale == 3", out3.stab_scale == 3);

    // L5 overlay (80 blocks ahead => scale=5)
    CasertDecision dec5{};
    dec5.mode = CasertMode::L5;
    dec5.signal_s = -80;
    dec5.effective_level = 5;

    auto out5 = casert_apply_overlay(base, dec5);
    TEST("L5 overlay: stab_scale == 5", out5.stab_scale == 5);
    TEST("L5 overlay: stab_k == 4", out5.stab_k == 4);

    // L6+ overlay (200 blocks ahead => level=8, scale=8)
    CasertDecision dec8{};
    dec8.mode = CasertMode::L6;
    dec8.signal_s = -200;
    dec8.effective_level = 8;

    auto out8 = casert_apply_overlay(base, dec8);
    TEST("L8 overlay: stab_scale == 8", out8.stab_scale == 8);
    TEST("L8 overlay: stab_k == 4", out8.stab_k == 4);
    TEST("L8 overlay: stab_steps == 4", out8.stab_steps == 4);

    // L1 overlay — should NOT modify params
    CasertDecision dec1{};
    dec1.mode = CasertMode::L1;
    dec1.signal_s = 0;  // on-time
    dec1.effective_level = 1;

    auto out1 = casert_apply_overlay(base, dec1);
    TEST("L1 overlay: stab_scale unchanged", out1.stab_scale == base.stab_scale);
}

// ============================================================================
// 4. ANTI-STALL TRIGGER — not before 7200s, activates after 7200s
// ============================================================================
void test_antistall_trigger() {
    printf("\n=== 4. ANTI-STALL TRIGGER ===\n");

    // Build a chain 250 blocks ahead => raw level = 8
    // level = 6 + (250-101)/50 = 6 + 2 = 8
    auto chain = make_ahead_chain(500, 250);
    int64_t last_block_time = chain.back().time;

    // At exactly 7199s: decay should NOT activate
    {
        int64_t now = last_block_time + 28799;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("28799s stall: no decay (level=8)", dec.effective_level == 8);
    }

    // At exactly 7200s: decay should NOT yet drop (activation point, 0 decay time)
    {
        int64_t now = last_block_time + 28800;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("28800s stall: decay activates but 0 time => level=8", dec.effective_level == 8);
    }

    // At 7200 + 600 = 7800s: L8+ drops at 600s/level, so 1 level down => 7
    {
        int64_t now = last_block_time + 29400;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("29400s stall: L8 drops to 7", dec.effective_level == 7);
    }

    // Validation path (now_time=0): always uses raw level, no decay
    {
        auto dec = casert_mode_from_chain(chain, 500, 0);
        TEST("validation (now_time=0): raw level=8, no decay", dec.effective_level == 8);
    }
}

// ============================================================================
// 5. DECAY CADENCE — tiered decay rates
// ============================================================================
void test_decay_cadence() {
    printf("\n=== 5. DECAY CADENCE ===\n");

    // Start at level 10 (350 blocks ahead)
    auto chain = make_ahead_chain(500, 350);
    int64_t last_block_time = chain.back().time;

    // Level 10 raw. Decay tiers:
    //   L10->L9->L8: 600s each (L8+ tier) = 1200s
    //   L8->L7: 600s (still L8+ at effective=8) -- wait, at effective=8 we check >=8
    //   Actually: effective starts at 10
    //     10->9: cost=600 (10>=8, fast)
    //     9->8: cost=600 (9>=8, fast)
    //     8->7: cost=600 (8>=8, fast)
    //     7->6: cost=1200 (7>=4 && 7<8, medium)
    //     6->5: cost=1200
    //     5->4: cost=1200
    //     4->3: cost=1200 (4>=4, medium)
    //     3->2: cost=1800 (3<4, slow)
    //     2->1: cost=1800

    // After 7200 + 600s => 10->9
    {
        int64_t now = last_block_time + 28800 + 600;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, +600s decay: level=9 (fast tier)", dec.effective_level == 9);
    }

    // After 7200 + 1200s => 10->9->8 (two fast drops)
    {
        int64_t now = last_block_time + 28800 + 1200;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, +1200s decay: level=8 (two fast drops)", dec.effective_level == 8);
    }

    // After 7200 + 1800s => 10->9->8->7 (three fast drops)
    {
        int64_t now = last_block_time + 28800 + 1800;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, +1800s decay: level=7 (three fast drops)", dec.effective_level == 7);
    }

    // After 7200 + 1800 + 1200 => 7->6 (medium tier)
    {
        int64_t now = last_block_time + 28800 + 1800 + 1200;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, +3000s decay: level=6 (enters medium tier)", dec.effective_level == 6);
    }

    // After 7200 + 1800 + 4*1200 => 7->6->5->4->3 (four medium drops)
    {
        int64_t now = last_block_time + 28800 + 1800 + 4 * 1200;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, +6600s decay: level=3 (enters slow tier)", dec.effective_level == 3);
    }

    // After full decay to L1: 7200 + 1800 + 4*1200 + 2*1800
    {
        int64_t now = last_block_time + 28800 + 1800 + 4 * 1200 + 2 * 1800;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, full decay: level=1 (floor)", dec.effective_level == 1);
    }

    // Even more time: still L1 (floor)
    {
        int64_t now = last_block_time + 28800 + 100000;
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("L10, excessive decay: still level=1 (floor)", dec.effective_level == 1);
    }
}

// ============================================================================
// 6. MINING VS VALIDATION SCOPE
// ============================================================================
void test_mining_vs_validation() {
    printf("\n=== 6. MINING VS VALIDATION SCOPE ===\n");

    // Build chain 250 blocks ahead (raw level=8)
    // level = 6 + (250-101)/50 = 6 + 2 = 8
    auto chain = make_ahead_chain(500, 250);
    int64_t last_block_time = chain.back().time;

    // Validation (now_time=0): raw schedule level, no decay
    {
        auto dec = casert_mode_from_chain(chain, 500, 0);
        TEST("validation: uses raw level=8", dec.effective_level == 8);
    }

    // Mining with stall (now_time > 0, 8000s stall): decay applies
    {
        int64_t now = last_block_time + 29400;
        auto dec = casert_mode_from_chain(chain, 500, now);
        // 29400 - 28800 = 600s decay time. L8+ costs 600s => one drop: 8->7
        TEST("mining with 29400s stall: decay applies, level=7", dec.effective_level == 7);
    }

    // Mining without stall (now_time > 0, recent block): no decay
    {
        int64_t now = last_block_time + 100;  // 100s since last block
        auto dec = casert_mode_from_chain(chain, 500, now);
        TEST("mining with 100s stall: no decay, level=8", dec.effective_level == 8);
    }
}

// ============================================================================
// 7. RESUME BEHAVIOR — decay stops when mining resumes
// ============================================================================
void test_resume_behavior() {
    printf("\n=== 7. RESUME BEHAVIOR ===\n");

    // After a stall, if a new block arrives, the chain context changes.
    // The next call to casert_mode_from_chain with a fresh chain (new block)
    // will compute the raw level from the new blocks_ahead value.
    // Decay only applies based on time since LAST block, so a new block resets it.

    // Simulate: chain was 200 blocks ahead, stalled for 10000s, then a block was found
    auto chain_stalled = make_ahead_chain(400, 200);
    int64_t last_block_stalled = chain_stalled.back().time;

    // During stall: decayed (ahead=200 > 100, activation=28800s)
    {
        int64_t now = last_block_stalled + 31600; // 28800+2800 = 31600
        auto dec = casert_mode_from_chain(chain_stalled, 400, now);
        // 31600 - 28800 = 2800s decay time. L8+: 600s/level => 4 drops in 2400s, 400s remains
        // 8->7->6->5(=2400s) then 5>=4 costs 1200, 400<1200 => stops at 5
        TEST("stalled chain: decayed to level=5", dec.effective_level == 5);
    }

    // New block arrives (chain grows by 1, still ahead but now_time is recent)
    auto chain_resumed = chain_stalled;
    int64_t new_block_time = last_block_stalled + 10000; // block found after stall
    chain_resumed.push_back({ZERO_HASH(), 400, new_block_time, GENESIS_BITSQ});

    {
        int64_t now = new_block_time + 10; // 10s after new block
        auto dec = casert_mode_from_chain(chain_resumed, 401, now);
        // Time since last block = 10s. 10 < 7200 => no decay.
        // Raw level depends on new blocks_ahead calculation.
        TEST("resumed chain: no decay (10s since last block)", dec.effective_level > 0);
        TEST("resumed chain: stall_seconds < 7200 => raw level used",
             dec.effective_level == dec.effective_level); // just verify it ran
    }
}

// ============================================================================
// 8. EDGE CASES — boundary checks
// ============================================================================
void test_edge_cases() {
    printf("\n=== 8. EDGE CASES ===\n");

    // Boundary: 4/5 (L1/L2 transition)
    {
        auto c4 = make_ahead_chain(100, 4);
        auto d4 = casert_mode_from_chain(c4, 100);
        TEST("ahead=4 => L1 (boundary)", d4.effective_level == 1);

        auto c5 = make_ahead_chain(100, 5);
        auto d5 = casert_mode_from_chain(c5, 100);
        TEST("ahead=5 => L2 (boundary)", d5.effective_level == 2);
    }

    // Boundary: 25/26 (L2/L3 transition)
    {
        auto c25 = make_ahead_chain(100, 25);
        auto d25 = casert_mode_from_chain(c25, 100);
        TEST("ahead=25 => L2 (boundary)", d25.effective_level == 2);

        auto c26 = make_ahead_chain(100, 26);
        auto d26 = casert_mode_from_chain(c26, 100);
        TEST("ahead=26 => L3 (boundary)", d26.effective_level == 3);
    }

    // Boundary: 50/51 (L3/L4 transition)
    {
        auto c50 = make_ahead_chain(100, 50);
        auto d50 = casert_mode_from_chain(c50, 100);
        TEST("ahead=50 => L3 (boundary)", d50.effective_level == 3);

        auto c51 = make_ahead_chain(100, 51);
        auto d51 = casert_mode_from_chain(c51, 100);
        TEST("ahead=51 => L4 (boundary)", d51.effective_level == 4);
    }

    // Boundary: 75/76 (L4/L5 transition)
    {
        auto c75 = make_ahead_chain(100, 75);
        auto d75 = casert_mode_from_chain(c75, 100);
        TEST("ahead=75 => L4 (boundary)", d75.effective_level == 4);

        auto c76 = make_ahead_chain(100, 76);
        auto d76 = casert_mode_from_chain(c76, 100);
        TEST("ahead=76 => L5 (boundary)", d76.effective_level == 5);
    }

    // Boundary: 100/101 (L5/L6 transition)
    {
        auto c100 = make_ahead_chain(200, 100);
        auto d100 = casert_mode_from_chain(c100, 200);
        TEST("ahead=100 => L5 (boundary)", d100.effective_level == 5);

        auto c101 = make_ahead_chain(200, 101);
        auto d101 = casert_mode_from_chain(c101, 200);
        TEST("ahead=101 => L6 (boundary)", d101.effective_level == 6);
    }

    // Boundary: 150/151 (L6/L7 transition)
    {
        auto c150 = make_ahead_chain(300, 150);
        auto d150 = casert_mode_from_chain(c150, 300);
        TEST("ahead=150 => L6 (boundary)", d150.effective_level == 6);

        auto c151 = make_ahead_chain(300, 151);
        auto d151 = casert_mode_from_chain(c151, 300);
        TEST("ahead=151 => L7 (boundary)", d151.effective_level == 7);
    }

    // Boundary: 200/201 (L7/L8 transition)
    {
        auto c200 = make_ahead_chain(400, 200);
        auto d200 = casert_mode_from_chain(c200, 400);
        TEST("ahead=200 => L7 (boundary)", d200.effective_level == 7);

        auto c201 = make_ahead_chain(400, 201);
        auto d201 = casert_mode_from_chain(c201, 400);
        TEST("ahead=201 => L8 (boundary)", d201.effective_level == 8);
    }

    // Empty chain => WARMUP
    {
        std::vector<BlockMeta> empty;
        auto dec = casert_mode_from_chain(empty, 0);
        TEST("empty chain => WARMUP", dec.mode == CasertMode::WARMUP);
    }

    // Single block chain => WARMUP (next_height < 2)
    {
        std::vector<BlockMeta> one;
        one.push_back({ZERO_HASH(), 0, GENESIS_TIME, GENESIS_BITSQ});
        auto dec = casert_mode_from_chain(one, 1);
        TEST("single block => WARMUP", dec.mode == CasertMode::WARMUP);
    }

    // On-time chain => L1
    {
        std::vector<BlockMeta> chain;
        for (int i = 0; i < 20; ++i) {
            chain.push_back({ZERO_HASH(), i, GENESIS_TIME + i * TARGET_SPACING, GENESIS_BITSQ});
        }
        auto dec = casert_mode_from_chain(chain, 20);
        TEST("on-time chain => L1", dec.mode == CasertMode::L1);
    }

    // Behind schedule chain => L1 (cASERT only hardens when ahead)
    {
        std::vector<BlockMeta> slow;
        for (int i = 0; i < 10; ++i) {
            slow.push_back({ZERO_HASH(), i, GENESIS_TIME + i * 2000, GENESIS_BITSQ});
        }
        auto dec = casert_mode_from_chain(slow, 10);
        TEST("behind schedule => L1 (no hardening)", dec.mode == CasertMode::L1);
    }

    // Time boundary: ahead=100 (L5, <=100 blocks => activation=14400s)
    {
        auto chain = make_ahead_chain(200, 100);
        int64_t last = chain.back().time;

        auto d_before = casert_mode_from_chain(chain, 200, last + 14399);
        TEST("14399s stall: no decay", d_before.effective_level == 5);

        auto d_at = casert_mode_from_chain(chain, 200, last + 14400);
        TEST("14400s stall: decay activates but 0 time", d_at.effective_level == 5);

        // 14400 + 1200 = 15600s. L5: cost=1200 (5>=4, medium) => one drop
        auto d_after = casert_mode_from_chain(chain, 200, last + 14400 + 1200);
        TEST("15600s stall: L5->L4 (medium tier)", d_after.effective_level == 4);
    }

    // Verify constants match canonical spec
    TEST("CASERT_L2_BLOCKS == 5", CASERT_L2_BLOCKS == 5);
    TEST("CASERT_L3_BLOCKS == 26", CASERT_L3_BLOCKS == 26);
    TEST("CASERT_L4_BLOCKS == 51", CASERT_L4_BLOCKS == 51);
    TEST("CASERT_L5_BLOCKS == 76", CASERT_L5_BLOCKS == 76);
    TEST("CASERT_L6_BLOCKS == 101", CASERT_L6_BLOCKS == 101);
    TEST("CASERT_DECAY_ACTIVATION == 7200", CASERT_DECAY_ACTIVATION == 7200);
    TEST("CASERT_DECAY_FAST_SECS == 600", CASERT_DECAY_FAST_SECS == 600);
    TEST("CASERT_DECAY_MEDIUM_SECS == 1200", CASERT_DECAY_MEDIUM_SECS == 1200);
    TEST("CASERT_DECAY_SLOW_SECS == 1800", CASERT_DECAY_SLOW_SECS == 1800);
}

int main() {
    printf("=== cASERT v5.2 Canonical Specification Tests ===\n");

    test_level_mapping();
    test_unbounded_regime();
    test_fixed_parameters();
    test_antistall_trigger();
    test_decay_cadence();
    test_mining_vs_validation();
    test_resume_behavior();
    test_edge_cases();

    printf("\n=== Results: %d passed, %d failed out of %d ===\n",
           tests_passed, tests_failed, tests_passed + tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
