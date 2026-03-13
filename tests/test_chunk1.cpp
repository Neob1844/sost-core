#include "sost/params.h"
#include "sost/types.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include "sost/emission.h"
#include "sost/pow/asert.h"
#include "sost/pow/casert.h"
#include "sost/sostcompact.h"
#include <cstdio>
#include <cassert>

using namespace sost;

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name, cond) do { \
    if (cond) { tests_passed++; printf("  PASS: %s\n", name); } \
    else { tests_failed++; printf("  FAIL: %s\n", name); } \
} while(0)

void test_emission() {
    printf("\n=== Emission ===\n");
    int64_t r0 = sost_subsidy_stocks(0);
    TEST("V6: height=0 subsidy", r0 == 785100863);

    int64_t r1 = sost_subsidy_stocks(131553);
    TEST("V6: epoch 1 < epoch 0", r1 < r0);
    TEST("V6: epoch 1 > 0", r1 > 0);

    int64_t r2 = sost_subsidy_stocks(2 * 131553);
    TEST("V6: epoch 2 < epoch 1", r2 < r1);

    // Negative height
    TEST("negative height = 0", sost_subsidy_stocks(-1) == 0);
}

void test_coinbase_split() {
    printf("\n=== Coinbase Split ===\n");
    auto s = coinbase_split(785100863);
    TEST("V7: gold = 196275215", s.gold_vault == 196275215);
    TEST("V7: popc = 196275215", s.popc_pool == 196275215);
    TEST("V7: miner = 392550433", s.miner == 392550433);
    TEST("V7: sum == reward", s.miner + s.gold_vault + s.popc_pool == s.total);
    TEST("V7: total == 785100863", s.total == 785100863);
}

void test_sostcompact() {
    printf("\n=== SOSTCompact ===\n");
    // Genesis target
    auto tgt = target_from_bitsQ(GENESIS_BITSQ);
    TEST("genesis target not zero", !is_zero(tgt));

    // Monotonicity: lower bitsQ = easier = larger target
    auto t1 = target_from_bitsQ(Q16_ONE * 4);  // 4 bits
    auto t2 = target_from_bitsQ(Q16_ONE * 6);  // 6 bits
    TEST("V8: lower bitsQ -> larger target", cmp_be(t1, t2) > 0);

    // Extreme values
    auto tmin = target_from_bitsQ(MIN_BITSQ);
    TEST("min bitsQ -> max target", tmin[0] == 0xFF);

    auto tmax = target_from_bitsQ(MAX_BITSQ);
    TEST("max bitsQ -> zero target", is_zero(tmax));

    // pow_meets_target
    Bytes32 easy_commit{}; easy_commit.fill(0);
    TEST("zero commit meets any target", pow_meets_target(easy_commit, GENESIS_BITSQ));

    Bytes32 hard_commit{}; hard_commit.fill(0xFF);
    TEST("max commit fails genesis target", !pow_meets_target(hard_commit, GENESIS_BITSQ));
}

void test_asert() {
    printf("\n=== ASERT ===\n");
    // Empty chain -> genesis
    std::vector<BlockMeta> empty;
    TEST("empty chain -> GENESIS_BITSQ", asert_next_difficulty(empty, 0) == GENESIS_BITSQ);

    // One-block chain at target spacing -> no change
    std::vector<BlockMeta> chain1;
    chain1.push_back({ZERO_HASH(), 0, GENESIS_TIME, GENESIS_BITSQ});
    uint32_t d1 = asert_next_difficulty(chain1, 1);
    TEST("single block -> close to genesis", d1 == GENESIS_BITSQ);

    // On-schedule chain (600s spacing) -> difficulty unchanged
    {
        std::vector<BlockMeta> on_sched;
        for (int i = 0; i < 50; ++i)
            on_sched.push_back({ZERO_HASH(), i, GENESIS_TIME + (int64_t)i * TARGET_SPACING, GENESIS_BITSQ});
        uint32_t d = asert_next_difficulty(on_sched, 50);
        TEST("50 blocks on-schedule -> GENESIS_BITSQ", d == GENESIS_BITSQ);
    }

    // Exponential response: 100 blocks at 25s each -> difficulty rises >= 50%
    {
        std::vector<BlockMeta> fast;
        uint32_t diff = GENESIS_BITSQ;
        for (int i = 0; i < 100; ++i) {
            fast.push_back({ZERO_HASH(), i, GENESIS_TIME + (int64_t)i * 25, diff});
            if (i > 0) diff = asert_next_difficulty(fast, i + 1);
        }
        // After 100 blocks at 25s, chain is ~57500s ahead of schedule
        // Exponential ASERT should raise difficulty by ~58%
        uint32_t final_d = asert_next_difficulty(fast, 100);
        char buf[128];
        snprintf(buf, sizeof(buf), "100 blocks @25s: diff %u -> %u (%.1f%% increase >= 50%%)",
                 GENESIS_BITSQ, final_d, 100.0 * (final_d - GENESIS_BITSQ) / GENESIS_BITSQ);
        TEST(buf, final_d >= GENESIS_BITSQ * 3 / 2);  // at least +50%
    }

    // Slow blocks (1200s each) -> difficulty drops
    {
        std::vector<BlockMeta> slow;
        for (int i = 0; i < 50; ++i)
            slow.push_back({ZERO_HASH(), i, GENESIS_TIME + (int64_t)i * 1200, GENESIS_BITSQ});
        uint32_t d = asert_next_difficulty(slow, 50);
        TEST("50 blocks @1200s -> difficulty drops", d < GENESIS_BITSQ);
    }

    // Difficulty never goes below MIN_BITSQ
    {
        std::vector<BlockMeta> very_slow;
        for (int i = 0; i < 10; ++i)
            very_slow.push_back({ZERO_HASH(), i, GENESIS_TIME + (int64_t)i * 86400, GENESIS_BITSQ});
        uint32_t d = asert_next_difficulty(very_slow, 10);
        TEST("extremely slow blocks -> clamped to MIN_BITSQ", d >= MIN_BITSQ);
    }

    // Difficulty never exceeds MAX_BITSQ
    {
        std::vector<BlockMeta> ultra_fast;
        // All 500 blocks with timestamp = GENESIS_TIME (0s apart, 500 blocks ahead)
        for (int i = 0; i < 500; ++i)
            ultra_fast.push_back({ZERO_HASH(), i, GENESIS_TIME, GENESIS_BITSQ});
        uint32_t d = asert_next_difficulty(ultra_fast, 500);
        TEST("500 blocks instant -> clamped to MAX_BITSQ", d <= MAX_BITSQ);
    }
}

void test_casert() {
    printf("\n=== CASERT ===\n");
    std::vector<BlockMeta> empty;
    auto dec = casert_mode_from_chain(empty, 0);
    TEST("empty chain -> warmup", dec.mode == CasertMode::WARMUP);

    // Build chain with on-target spacing -> should be NORMAL
    std::vector<BlockMeta> chain;
    for (int i = 0; i < 10; ++i) {
        chain.push_back({ZERO_HASH(), i, GENESIS_TIME + i * TARGET_SPACING, GENESIS_BITSQ});
    }
    auto dec2 = casert_mode_from_chain(chain, 10);
    TEST("on-target -> L1", dec2.mode == CasertMode::L1);

    // Build slow chain -> should be L1 (cASERT only hardens, never relaxes)
    std::vector<BlockMeta> slow;
    for (int i = 0; i < 10; ++i) {
        slow.push_back({ZERO_HASH(), i, GENESIS_TIME + i * 2000, GENESIS_BITSQ});
    }
    auto dec3 = casert_mode_from_chain(slow, 10);
    TEST("slow chain -> L1", dec3.mode == CasertMode::L1);
}

void test_crypto() {
    printf("\n=== Crypto ===\n");
    // SHA256 of empty
    Bytes32 h = sha256((const uint8_t*)"", 0);
    TEST("sha256 empty not zero", !is_zero(h));

    // PRNG determinism
    Bytes32 seed{}; seed.fill(0x42);
    auto p1 = prng_bytes(seed, 64);
    auto p2 = prng_bytes(seed, 64);
    TEST("PRNG deterministic", p1 == p2);
    TEST("PRNG correct length", p1.size() == 64);
}

void test_serialize() {
    printf("\n=== Serialize ===\n");
    uint8_t buf[4];
    write_u32_le(buf, 0x01020304);
    TEST("u32 LE byte 0", buf[0] == 0x04);
    TEST("u32 LE byte 3", buf[3] == 0x01);
    TEST("u32 LE roundtrip", read_u32_le(buf) == 0x01020304);

    TEST("asr_i32 positive", asr_i32(256, 4) == 16);
    TEST("asr_i32 negative", asr_i32(-256, 4) == -16);
    TEST("clamp_i32 overflow", clamp_i32(3000000000LL) == INT32_MAX);
}

int main() {
    printf("SOST Chunk 1 Tests\n");
    printf("==================\n");

    test_emission();
    test_coinbase_split();
    test_sostcompact();
    test_asert();
    test_casert();
    test_crypto();
    test_serialize();

    printf("\n==================\n");
    printf("Results: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
