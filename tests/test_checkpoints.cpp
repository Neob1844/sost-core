// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_checkpoints.cpp — Tests for hard checkpoint and assumevalid fast sync.
#include "sost/checkpoints.h"
#include "sost/params.h"
#include <cassert>
#include <cstdio>

// ═══════════════════════════════════════════════════════════
// 1. Hard checkpoint exact match
// ═══════════════════════════════════════════════════════════

void test_hard_checkpoint_empty() {
    // At genesis, HARD_CHECKPOINTS is empty, so everything is false
    assert(!sost::is_hard_checkpoint(0, "0000000000"));
    assert(!sost::is_hard_checkpoint(0, "anything"));
    assert(!sost::is_hard_checkpoint(1, "anything"));
    assert(!sost::is_hard_checkpoint(100, "anything"));
    assert(!sost::is_hard_checkpoint(999999, "anything"));
    printf("PASS: hard checkpoint empty — nothing matches\n");
}

void test_hard_checkpoint_wrong_hash() {
    // Even at a height that could be a checkpoint, wrong hash must fail
    assert(!sost::is_hard_checkpoint(0, "wrong_hash"));
    assert(!sost::is_hard_checkpoint(0, ""));
    printf("PASS: hard checkpoint wrong hash — rejected\n");
}

void test_lower_height_not_trusted() {
    // CRITICAL: lower height alone must NOT be enough for trust.
    // With LAST_HARD_CHECKPOINT_HEIGHT=0, height 0 with wrong hash must fail.
    assert(!sost::is_hard_checkpoint(0, "not_the_right_hash"));
    // Height below any checkpoint with wrong hash must fail
    assert(!sost::is_hard_checkpoint(0, "fake"));
    printf("PASS: lower height alone NOT trusted\n");
}

// ═══════════════════════════════════════════════════════════
// 2. Assumevalid behavior
// ═══════════════════════════════════════════════════════════

void test_no_assumevalid_anchor() {
    // With empty ASSUMEVALID_BLOCK_HASH, no anchor exists
    assert(!sost::has_assumevalid_anchor());
    // Therefore no block can be under assumevalid range
    assert(!sost::is_block_under_assumevalid(0, true));
    assert(!sost::is_block_under_assumevalid(0, false));
    assert(!sost::is_block_under_assumevalid(50, true));
    assert(!sost::is_block_under_assumevalid(50, false));
    printf("PASS: no assumevalid anchor — no trust\n");
}

void test_assumevalid_anchor_not_on_chain() {
    // Even if has_assumevalid_anchor() were true, if anchor is not
    // on active chain, no trust. Test with chain_contains_anchor=false.
    assert(!sost::is_block_under_assumevalid(50, false));
    printf("PASS: anchor not on active chain — no trust\n");
}

// ═══════════════════════════════════════════════════════════
// 3. Full verify override
// ═══════════════════════════════════════════════════════════

void test_full_verify_overrides_all() {
    // --full-verify must always return false (never skip CX)
    // Even with checkpoint match or assumevalid
    assert(!sost::can_skip_cx_recomputation(0, "any", true, true));
    assert(!sost::can_skip_cx_recomputation(0, "any", false, true));
    assert(!sost::can_skip_cx_recomputation(100, "any", true, true));
    assert(!sost::can_skip_cx_recomputation(999999, "any", true, true));
    printf("PASS: --full-verify overrides all skip logic\n");
}

// ═══════════════════════════════════════════════════════════
// 4. Master decision function
// ═══════════════════════════════════════════════════════════

void test_can_skip_empty_state() {
    // With no checkpoints and no assumevalid, can_skip must always be false
    assert(!sost::can_skip_cx_recomputation(0, "any", false, false));
    assert(!sost::can_skip_cx_recomputation(100, "any", false, false));
    assert(!sost::can_skip_cx_recomputation(0, "any", true, false));
    printf("PASS: empty state — no skip possible\n");
}

// ═══════════════════════════════════════════════════════════
// 5. No parameter drift — consensus constants unchanged
// ═══════════════════════════════════════════════════════════

void test_consensus_params_unchanged() {
    // Verify critical consensus constants are not touched
    assert(sost::GENESIS_TIME == 1773597600);
    assert(sost::GENESIS_BITSQ == 765730);
    assert(sost::R0_STOCKS == 785100863);
    assert(sost::TARGET_SPACING == 600);
    assert(sost::BLOCKS_PER_EPOCH == 131553);
    assert(sost::CX_N == 32);
    assert(sost::CX_ROUNDS_M == 100000);
    assert(sost::CX_SCRATCH_M == 4096);
    assert(sost::BITSQ_HALF_LIFE == 172800);
    assert(sost::CASERT_L2_BLOCKS == 5);
    assert(sost::CASERT_L6_BLOCKS == 101);
    // Constitutional addresses
    assert(std::string(sost::ADDR_GOLD_VAULT) == "sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d");
    assert(std::string(sost::ADDR_POPC_POOL) == "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f");
    printf("PASS: consensus parameters unchanged\n");
}

// ═══════════════════════════════════════════════════════════
// 6. Structural checks on checkpoint data
// ═══════════════════════════════════════════════════════════

void test_checkpoint_data_consistency() {
    // LAST_HARD_CHECKPOINT_HEIGHT must match actual checkpoint list
    if (sost::HARD_CHECKPOINTS.empty()) {
        assert(sost::LAST_HARD_CHECKPOINT_HEIGHT == 0);
    } else {
        uint32_t max_h = 0;
        for (const auto& cp : sost::HARD_CHECKPOINTS) {
            if (cp.height > max_h) max_h = cp.height;
        }
        assert(sost::LAST_HARD_CHECKPOINT_HEIGHT == max_h);
    }
    // ASSUMEVALID_HEIGHT must be consistent with hash
    if (sost::ASSUMEVALID_BLOCK_HASH.empty()) {
        assert(sost::ASSUMEVALID_HEIGHT == 0);
    }
    printf("PASS: checkpoint data consistency\n");
}

int main() {
    printf("=== SOST Checkpoint Fast Sync Tests ===\n\n");

    // 1. Hard checkpoint exact match
    test_hard_checkpoint_empty();
    test_hard_checkpoint_wrong_hash();
    test_lower_height_not_trusted();

    // 2. Assumevalid behavior
    test_no_assumevalid_anchor();
    test_assumevalid_anchor_not_on_chain();

    // 3. Full verify override
    test_full_verify_overrides_all();

    // 4. Master decision
    test_can_skip_empty_state();

    // 5. No parameter drift
    test_consensus_params_unchanged();

    // 6. Data consistency
    test_checkpoint_data_consistency();

    printf("\n=== All checkpoint tests PASSED ===\n");
    return 0;
}
