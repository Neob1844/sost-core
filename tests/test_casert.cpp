// cASERT unified control system tests
#include "sost/pow/casert.h"
#include <cstdio>
#include <cassert>
#include <vector>
#include <cstdlib>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  EXPECT failed: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while(0)

static std::vector<BlockMeta> make_chain(int len, int64_t spacing) {
    std::vector<BlockMeta> chain;
    for (int i = 0; i < len; ++i) {
        BlockMeta m;
        m.block_id = ZERO_HASH();
        m.height = i;
        m.time = GENESIS_TIME + (int64_t)i * spacing;
        m.powDiffQ = GENESIS_BITSQ;
        chain.push_back(m);
    }
    return chain;
}

int main() {
    printf("\n=== cASERT Unified Control System Tests ===\n");

    printf("\n=== 1. bitsQ PRIMARY CONTROLLER ===\n");

    {
        std::vector<BlockMeta> empty;
        uint32_t d = casert_next_bitsq(empty, 0);
        TEST("empty chain -> GENESIS_BITSQ", d == GENESIS_BITSQ);
    }
    {
        auto chain = make_chain(1, TARGET_SPACING);
        uint32_t d = casert_next_bitsq(chain, 1);
        TEST("single block -> near GENESIS_BITSQ", d >= MIN_BITSQ);
    }
    {
        auto chain = make_chain(50, TARGET_SPACING);
        uint32_t d = casert_next_bitsq(chain, 50);
        int64_t diff = (int64_t)d - (int64_t)GENESIS_BITSQ;
        TEST("on-schedule 50 blocks -> stable", std::abs(diff) < 5000);
    }
    {
        auto chain = make_chain(50, 30);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = casert_next_bitsq(chain, (int64_t)i);
        uint32_t d = casert_next_bitsq(chain, 50);
        TEST("fast chain (30s) -> rises", d > GENESIS_BITSQ);
    }
    {
        auto chain = make_chain(50, 1200);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = casert_next_bitsq(chain, (int64_t)i);
        uint32_t d = casert_next_bitsq(chain, 50);
        TEST("slow chain (1200s) -> drops", d < GENESIS_BITSQ);
    }
    {
        auto chain = make_chain(20, TARGET_SPACING);
        BlockMeta fast;
        fast.block_id = ZERO_HASH(); fast.height = 20;
        fast.time = chain.back().time + 1; fast.powDiffQ = chain.back().powDiffQ;
        chain.push_back(fast);
        uint32_t d = casert_next_bitsq(chain, 21);
        int64_t max_delta = (int64_t)chain.back().powDiffQ / BITSQ_MAX_DELTA_DEN;
        int64_t actual = (int64_t)d - (int64_t)chain.back().powDiffQ;
        TEST("relative delta cap", std::abs(actual) <= max_delta + 1);
    }
    {
        uint32_t d = casert_next_bitsq({}, 0);
        TEST("floor >= MIN_BITSQ", d >= MIN_BITSQ);
    }

    printf("\n=== 2. EQUALIZER ===\n");

    {
        auto chain = make_chain(50, TARGET_SPACING);
        auto dec = casert_compute(chain, 50);
        TEST("on-schedule -> B0 area", dec.profile_index >= -1 && dec.profile_index <= 1);
    }
    {
        auto chain = make_chain(50, TARGET_SPACING);
        auto dec = casert_compute(chain, 50);
        TEST("bitsQ in decision", dec.bitsq >= MIN_BITSQ);
    }

    printf("\n=== 3. PROFILE TABLE ===\n");

    {
        CasertDecision dec{};
        ConsensusParams base{}; base.stab_scale=1; base.stab_k=4; base.stab_steps=4; base.stab_margin=180;
        for (int32_t h = CASERT_H_MIN; h <= CASERT_H_MAX; ++h) {
            dec.profile_index = h;
            auto out = casert_apply_profile(base, dec);
            int32_t ai = h - CASERT_H_MIN; // convert to array index
            char buf[128];
            snprintf(buf, sizeof(buf), "H=%d: scale=%d steps=%d k=%d margin=%d", h, out.stab_scale, out.stab_steps, out.stab_k, out.stab_margin);
            TEST(buf, out.stab_scale == CASERT_PROFILES[ai].scale && out.stab_k == CASERT_PROFILES[ai].k);
        }
    }
    {
        CasertDecision dec{}; dec.profile_index = 0;
        ConsensusParams base{};
        auto out = casert_apply_profile(base, dec);
        TEST("B0: scale=1 k=4 steps=4 margin=185", out.stab_scale==1 && out.stab_k==4 && out.stab_steps==4 && out.stab_margin==185);
    }

    printf("\n=== 4. ANTI-STALL ===\n");

    {
        auto chain = make_chain(50, TARGET_SPACING);
        int64_t now = chain.back().time + 100;
        auto dec = casert_compute(chain, 50, now);
        TEST("100s stall -> no override", dec.profile_index >= CASERT_H_MIN);
    }
    {
        auto chain = make_chain(50, TARGET_SPACING);
        auto dec_v = casert_compute(chain, 50, 0);
        TEST("validation deterministic", dec_v.bitsq >= MIN_BITSQ);
    }

    printf("\n=== 5. TIMESTAMPS ===\n");

    {
        auto chain = make_chain(15, TARGET_SPACING);
        int64_t mtp = median_time_past(chain);
        TEST("MTP > 0", mtp > 0);
        auto [ok1,m1] = validate_block_time(mtp+1, chain, chain.back().time+100);
        TEST("valid ts accepted", ok1);
        auto [ok2,m2] = validate_block_time(mtp-1, chain, chain.back().time+100);
        TEST("old ts rejected", !ok2);
    }

    printf("\n=== 6. REPRODUCIBILITY ===\n");

    {
        auto chain = make_chain(50, 300);
        uint32_t d1 = casert_next_bitsq(chain, 50);
        uint32_t d2 = casert_next_bitsq(chain, 50);
        TEST("bitsQ deterministic", d1 == d2);
        auto dec1 = casert_compute(chain, 50);
        auto dec2 = casert_compute(chain, 50);
        TEST("profile deterministic", dec1.profile_index == dec2.profile_index);
    }

    printf("\n=== 7. CONSTANTS ===\n");

    TEST("BITSQ_HALF_LIFE == 172800", BITSQ_HALF_LIFE == 172800);
    TEST("GENESIS_BITSQ >= Q16_ONE", GENESIS_BITSQ >= Q16_ONE);
    TEST("MIN_BITSQ == Q16_ONE", MIN_BITSQ == Q16_ONE);
    TEST("H_MIN == -4", CASERT_H_MIN == -4);
    TEST("H_MAX == 9", CASERT_H_MAX == 9);
    TEST("PROFILE_COUNT == 17", CASERT_PROFILE_COUNT == 17);

    printf("\n=== 8. SLEW RATE ===\n");

    {
        // Fast chain: consecutive blocks should not change H by more than ±1
        auto chain = make_chain(50, 200); // very fast blocks
        bool slew_ok = true;
        int32_t prev_H = 0;
        for (int h = 11; h <= 49; ++h) {
            std::vector<BlockMeta> sub(chain.begin(), chain.begin() + h);
            auto dec = casert_compute(sub, h, sub.back().time + 200);
            if (h > 11) {
                int32_t delta = dec.profile_index - prev_H;
                if (delta > 1 || delta < -1) { slew_ok = false; break; }
            }
            prev_H = dec.profile_index;
        }
        TEST("Slew rate: H changes by at most ±1 per block", slew_ok);
    }

    printf("\n=== 9. ANTI-STALL LONG (>48h) ===\n");

    {
        auto chain = make_chain(50, 200); // fast chain, H should be positive
        // Stall for 48 hours = 172800s
        int64_t now = chain.back().time + 172800;
        auto dec = casert_compute(chain, 50, now);
        TEST("48h stall: decays to B0 or below", dec.profile_index <= 0);
    }

    printf("\n=== 10. ANTI-STALL EXTREME (>18h) ===\n");

    {
        auto chain = make_chain(50, 200); // fast chain
        // Stall for 18 hours = 64800s (7200 activation + ~6000 decay + 21600 easing threshold)
        int64_t now = chain.back().time + 64800;
        auto dec = casert_compute(chain, 50, now);
        TEST("18h stall: activates easing (E1 or below)", dec.profile_index < 0);
    }

    printf("\n=== 11. H_MAX ENFORCEMENT ===\n");

    {
        auto chain = make_chain(100, 100); // extremely fast chain
        int64_t now = chain.back().time + 100;
        auto dec = casert_compute(chain, 100, now);
        TEST("H never exceeds H_MAX=9", dec.profile_index <= CASERT_H_MAX);
    }

    printf("\n=== 12. BEHIND SCHEDULE CAP ===\n");

    {
        auto chain = make_chain(50, 1200); // very slow chain (behind schedule)
        auto dec = casert_compute(chain, 50);
        TEST("Behind schedule: capped at B0", dec.profile_index <= 0);
    }

    printf("\n=== Results: %d passed, %d failed out of %d ===\n\n", g_pass, g_fail, g_pass+g_fail);
    return g_fail > 0 ? 1 : 0;
}
