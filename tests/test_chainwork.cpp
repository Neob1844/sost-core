// test_chainwork.cpp — Block work computation and chain selection tests
//
// Tests the core principle: best chain = highest cumulative valid work.
// Verifies compute_block_work(), add_be256(), and compare_chainwork().

#include "sost/sostcompact.h"
#include "sost/params.h"
#include "sost/types.h"
#include <cstdio>
#include <cstring>

using namespace sost;

static int pass = 0, fail = 0;
#define TEST(name, cond) do { if(cond){pass++;printf("  PASS: %s\n",name);}else{fail++;printf("  FAIL: %s\n",name);} } while(0)

void test_block_work_basic() {
    printf("\n=== Block Work: Basic Properties ===\n");

    // Work at genesis difficulty should be non-zero
    Bytes32 w = compute_block_work(GENESIS_BITSQ);
    bool nz = false;
    for (int i = 0; i < 32; ++i) if (w[i]) { nz = true; break; }
    TEST("Genesis work non-zero", nz);

    // Work at minimum difficulty (easiest) should be smallest
    Bytes32 w_min = compute_block_work(MIN_BITSQ);
    bool min_nz = false;
    for (int i = 0; i < 32; ++i) if (w_min[i]) { min_nz = true; break; }
    TEST("MIN_BITSQ work non-zero", min_nz);

    // Work at higher bitsQ should be more (harder = more work)
    Bytes32 w2 = compute_block_work(GENESIS_BITSQ + 65536);
    TEST("Higher bitsQ = more work", compare_chainwork(w2, w) > 0);

    // Work at even higher bitsQ should be even more
    Bytes32 w3 = compute_block_work(GENESIS_BITSQ + 2*65536);
    TEST("Even higher bitsQ = even more work", compare_chainwork(w3, w2) > 0);
}

void test_add_be256() {
    printf("\n=== add_be256: 256-bit addition ===\n");

    Bytes32 zero{};
    Bytes32 one{}; one.fill(0); one[31] = 1;
    Bytes32 two{}; two.fill(0); two[31] = 2;

    // 0 + 0 = 0
    Bytes32 r00 = add_be256(zero, zero);
    TEST("0 + 0 = 0", compare_chainwork(r00, zero) == 0);

    // 0 + 1 = 1
    Bytes32 r01 = add_be256(zero, one);
    TEST("0 + 1 = 1", compare_chainwork(r01, one) == 0);

    // 1 + 1 = 2
    Bytes32 r11 = add_be256(one, one);
    TEST("1 + 1 = 2", compare_chainwork(r11, two) == 0);

    // Commutative: a + b = b + a
    Bytes32 a = compute_block_work(GENESIS_BITSQ);
    Bytes32 b = compute_block_work(GENESIS_BITSQ + 65536);
    Bytes32 ab = add_be256(a, b);
    Bytes32 ba = add_be256(b, a);
    TEST("add_be256 commutative", compare_chainwork(ab, ba) == 0);

    // Associative: (a + b) + c = a + (b + c)
    Bytes32 c = compute_block_work(GENESIS_BITSQ + 2*65536);
    Bytes32 ab_c = add_be256(add_be256(a, b), c);
    Bytes32 a_bc = add_be256(a, add_be256(b, c));
    TEST("add_be256 associative", compare_chainwork(ab_c, a_bc) == 0);

    // Carry propagation: 0xFF...FF + 1 should work
    Bytes32 max_byte{}; max_byte.fill(0); max_byte[31] = 0xFF;
    Bytes32 carry_result = add_be256(max_byte, one);
    Bytes32 expected_carry{}; expected_carry.fill(0);
    expected_carry[30] = 1; expected_carry[31] = 0;
    TEST("Carry propagation: 0xFF + 1 = 0x100", compare_chainwork(carry_result, expected_carry) == 0);
}

void test_chainwork_monotonicity() {
    printf("\n=== Chainwork: Monotonically Increasing ===\n");

    // Adding any positive work to cumulative always increases it
    Bytes32 cumulative{};
    bool all_increasing = true;
    for (int i = 0; i < 20; ++i) {
        Bytes32 prev = cumulative;
        Bytes32 bw = compute_block_work(GENESIS_BITSQ + i * 1000);
        cumulative = add_be256(cumulative, bw);
        if (compare_chainwork(cumulative, prev) <= 0) {
            all_increasing = false;
            break;
        }
    }
    TEST("Cumulative work strictly increases with each block", all_increasing);
}

void test_work_vs_difficulty() {
    printf("\n=== Work vs Difficulty Relationship ===\n");

    // At constant difficulty, N blocks have exactly N times one block's work
    Bytes32 single = compute_block_work(GENESIS_BITSQ);
    Bytes32 five_blocks{};
    for (int i = 0; i < 5; ++i) {
        five_blocks = add_be256(five_blocks, single);
    }
    Bytes32 four_blocks{};
    for (int i = 0; i < 4; ++i) {
        four_blocks = add_be256(four_blocks, single);
    }

    TEST("5 blocks > 4 blocks at same difficulty", compare_chainwork(five_blocks, four_blocks) > 0);

    // One block at 2x difficulty should have approximately 2x work
    // (not exact due to integer division, but significantly more)
    Bytes32 w1 = compute_block_work(GENESIS_BITSQ);
    Bytes32 w2 = compute_block_work(GENESIS_BITSQ + 65536); // 2^1 harder
    // w2 should be roughly double w1 (approximately, not exact)
    // At minimum, w2 > w1
    TEST("Double difficulty = more work", compare_chainwork(w2, w1) > 0);
}

void test_target_consistency() {
    printf("\n=== Target/Work Consistency ===\n");

    // target_from_bitsQ and compute_block_work should be consistent:
    // higher bitsQ → smaller target → more work
    for (uint32_t bq = GENESIS_BITSQ; bq < GENESIS_BITSQ + 5*65536; bq += 65536) {
        Bytes32 t1 = target_from_bitsQ(bq);
        Bytes32 t2 = target_from_bitsQ(bq + 65536);
        Bytes32 w1 = compute_block_work(bq);
        Bytes32 w2 = compute_block_work(bq + 65536);

        char buf[128];
        snprintf(buf, sizeof(buf), "bitsQ=%u: higher bitsQ -> smaller target", bq);
        TEST(buf, cmp_be(t2, t1) < 0);

        snprintf(buf, sizeof(buf), "bitsQ=%u: smaller target -> more work", bq);
        TEST(buf, compare_chainwork(w2, w1) > 0);
    }
}

int main() {
    printf("SOST Chainwork Tests\n");
    printf("====================\n");

    test_block_work_basic();
    test_add_be256();
    test_chainwork_monotonicity();
    test_work_vs_difficulty();
    test_target_consistency();

    printf("\n====================\n");
    printf("Results: %d passed, %d failed\n", pass, fail);
    return fail > 0 ? 1 : 0;
}
