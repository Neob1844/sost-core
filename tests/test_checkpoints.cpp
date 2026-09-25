// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_checkpoints.cpp — Tests for hard checkpoint and assumevalid fast sync.
//
// Checks run in BOTH Debug and Release: CHECK() is a real runtime assertion that
// records failures and makes main() exit non-zero, independent of NDEBUG (plain
// assert() is compiled out under Release and would make these tests vacuous).
#include "sost/checkpoints.h"
#include "sost/params.h"
#include <cstdio>
#include <string>

static int g_fails = 0;
#define CHECK(cond) do { if (!(cond)) { \
    printf("  FAIL: %s  (%s:%d)\n", #cond, __FILE__, __LINE__); ++g_fails; } } while (0)

// ═══════════════════════════════════════════════════════════
// 1. Hard checkpoint exact match (HARD_CHECKPOINTS is empty)
// ═══════════════════════════════════════════════════════════

void test_hard_checkpoint_empty() {
    CHECK(!sost::is_hard_checkpoint(0, "0000000000"));
    CHECK(!sost::is_hard_checkpoint(0, "anything"));
    CHECK(!sost::is_hard_checkpoint(1, "anything"));
    CHECK(!sost::is_hard_checkpoint(100, "anything"));
    CHECK(!sost::is_hard_checkpoint(999999, "anything"));
    printf("PASS: hard checkpoint empty — nothing matches\n");
}

void test_hard_checkpoint_wrong_hash() {
    CHECK(!sost::is_hard_checkpoint(0, "wrong_hash"));
    CHECK(!sost::is_hard_checkpoint(0, ""));
    printf("PASS: hard checkpoint wrong hash — rejected\n");
}

void test_lower_height_not_trusted() {
    // Lower height alone must NOT be enough for trust.
    CHECK(!sost::is_hard_checkpoint(0, "not_the_right_hash"));
    CHECK(!sost::is_hard_checkpoint(0, "fake"));
    printf("PASS: lower height alone NOT trusted\n");
}

// ═══════════════════════════════════════════════════════════
// 2. Assumevalid behaviour — the SHIPPED anchor (height 3554)
// ═══════════════════════════════════════════════════════════

void test_assumevalid_anchor_present() {
    // The release ships an assumevalid anchor at height 3554. This test asserts
    // the shipped configuration, not an empty one.
    CHECK(sost::has_assumevalid_anchor());
    CHECK(sost::get_assumevalid_height() == 3554);
    CHECK(sost::get_assumevalid_hash().size() == 64);

    // With the anchor ON the active chain, blocks AT OR BELOW the height are
    // under assumevalid; blocks above it are not.
    CHECK(sost::is_block_under_assumevalid(0, true));
    CHECK(sost::is_block_under_assumevalid(50, true));
    CHECK(sost::is_block_under_assumevalid(3554, true));      // boundary inclusive
    CHECK(!sost::is_block_under_assumevalid(3555, true));     // just above
    CHECK(!sost::is_block_under_assumevalid(999999, true));
    printf("PASS: assumevalid anchor present at 3554 — range correct\n");
}

void test_assumevalid_anchor_not_on_chain() {
    // If the anchor is NOT on the active chain, no block is trusted, at any height.
    CHECK(!sost::is_block_under_assumevalid(0, false));
    CHECK(!sost::is_block_under_assumevalid(50, false));
    CHECK(!sost::is_block_under_assumevalid(3554, false));
    printf("PASS: anchor not on active chain — no trust\n");
}

// ═══════════════════════════════════════════════════════════
// 3. Full verify override
// ═══════════════════════════════════════════════════════════

void test_full_verify_overrides_all() {
    // --full-verify must always return false (never skip CX), even under the anchor.
    CHECK(!sost::can_skip_cx_recomputation(0, "any", true, true));
    CHECK(!sost::can_skip_cx_recomputation(0, "any", false, true));
    CHECK(!sost::can_skip_cx_recomputation(100, "any", true, true));
    CHECK(!sost::can_skip_cx_recomputation(3554, "any", true, true));
    CHECK(!sost::can_skip_cx_recomputation(999999, "any", true, true));
    printf("PASS: --full-verify overrides all skip logic\n");
}

// ═══════════════════════════════════════════════════════════
// 4. Master decision function — with the shipped anchor
// ═══════════════════════════════════════════════════════════

void test_can_skip_with_anchor() {
    // No hard checkpoints exist, so skipping is driven purely by assumevalid.
    // Anchor NOT on chain (chain_contains_anchor=false): never skip.
    CHECK(!sost::can_skip_cx_recomputation(0, "any", false, false));
    CHECK(!sost::can_skip_cx_recomputation(100, "any", false, false));
    CHECK(!sost::can_skip_cx_recomputation(3554, "any", false, false));
    // Anchor ON chain: skip at/below 3554, verify above it.
    CHECK(sost::can_skip_cx_recomputation(0, "any", true, false));
    CHECK(sost::can_skip_cx_recomputation(3554, "any", true, false));
    CHECK(!sost::can_skip_cx_recomputation(3555, "any", true, false));
    CHECK(!sost::can_skip_cx_recomputation(999999, "any", true, false));
    printf("PASS: can_skip driven by assumevalid anchor (<=3554 on chain)\n");
}

// ═══════════════════════════════════════════════════════════
// 5. No parameter drift — consensus constants unchanged
// ═══════════════════════════════════════════════════════════

void test_consensus_params_unchanged() {
    CHECK(sost::GENESIS_TIME == 1773597600);
    CHECK(sost::GENESIS_BITSQ == 765730);
    CHECK(sost::R0_STOCKS == 785100863);
    CHECK(sost::TARGET_SPACING == 600);
    CHECK(sost::BLOCKS_PER_EPOCH == 131553);
    CHECK(sost::CX_N == 32);
    CHECK(sost::CX_ROUNDS_M == 100000);
    CHECK(sost::CX_SCRATCH_M == 4096);
    CHECK(sost::BITSQ_HALF_LIFE == 172800);
    CHECK(std::string(sost::ADDR_GOLD_VAULT) == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d");
    CHECK(std::string(sost::ADDR_POPC_POOL) == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f");
    printf("PASS: consensus parameters unchanged\n");
}

// ═══════════════════════════════════════════════════════════
// 6. Structural checks on checkpoint data
// ═══════════════════════════════════════════════════════════

void test_checkpoint_data_consistency() {
    if (sost::HARD_CHECKPOINTS.empty()) {
        CHECK(sost::LAST_HARD_CHECKPOINT_HEIGHT == 0);
    } else {
        uint32_t max_h = 0;
        for (const auto& cp : sost::HARD_CHECKPOINTS)
            if (cp.height > max_h) max_h = cp.height;
        CHECK(sost::LAST_HARD_CHECKPOINT_HEIGHT == max_h);
    }
    // ASSUMEVALID_HEIGHT and hash must be mutually consistent.
    if (sost::ASSUMEVALID_BLOCK_HASH.empty()) {
        CHECK(sost::ASSUMEVALID_HEIGHT == 0);
    } else {
        CHECK(sost::ASSUMEVALID_BLOCK_HASH.size() == 64);
        CHECK(sost::ASSUMEVALID_HEIGHT > 0);
    }
    printf("PASS: checkpoint data consistency\n");
}

int main() {
    printf("=== SOST Checkpoint Fast Sync Tests ===\n\n");
    test_hard_checkpoint_empty();
    test_hard_checkpoint_wrong_hash();
    test_lower_height_not_trusted();
    test_assumevalid_anchor_present();
    test_assumevalid_anchor_not_on_chain();
    test_full_verify_overrides_all();
    test_can_skip_with_anchor();
    test_consensus_params_unchanged();
    test_checkpoint_data_consistency();
    if (g_fails == 0) { printf("\n=== All checkpoint tests PASSED ===\n"); return 0; }
    printf("\n=== %d checkpoint CHECK(s) FAILED ===\n", g_fails);
    return 1;
}
