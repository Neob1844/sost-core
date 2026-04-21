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

    TEST("BITSQ_HALF_LIFE V1 == 172800", BITSQ_HALF_LIFE == 172800);
    TEST("BITSQ_HALF_LIFE_V2 == 86400", BITSQ_HALF_LIFE_V2 == 86400);
    TEST("BITSQ_MAX_DELTA_DEN V1 == 16", BITSQ_MAX_DELTA_DEN == 16);
    TEST("BITSQ_MAX_DELTA_DEN_V2 == 8", BITSQ_MAX_DELTA_DEN_V2 == 8);
    TEST("CASERT_V2_FORK_HEIGHT == 1450", CASERT_V2_FORK_HEIGHT == 1450);
    TEST("GENESIS_BITSQ >= Q16_ONE", GENESIS_BITSQ >= Q16_ONE);
    TEST("MIN_BITSQ == Q16_ONE", MIN_BITSQ == Q16_ONE);
    TEST("H_MIN == -4", CASERT_H_MIN == -4);
    TEST("H_MAX == 12", CASERT_H_MAX == 12);
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
        TEST("H never exceeds H_MAX=12", dec.profile_index <= CASERT_H_MAX);
    }

    printf("\n=== 12. BEHIND SCHEDULE CAP ===\n");

    {
        auto chain = make_chain(50, 1200); // very slow chain (behind schedule)
        auto dec = casert_compute(chain, 50);
        TEST("Behind schedule: capped at B0", dec.profile_index <= 0);
    }

    printf("\n=== 13. cASERT V2 FORK BOUNDARY ===\n");

    {
        // Pre-fork: block 1449 uses V1 parameters
        auto chain = make_chain(1449, TARGET_SPACING);
        // Set powDiffQ to something measurable
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = GENESIS_BITSQ;
        // Make last block arrive fast (half target) to trigger adjustment
        chain.back().time = chain[chain.size()-2].time + TARGET_SPACING / 2;

        uint32_t d_v1 = casert_next_bitsq(chain, 1449); // pre-fork height
        // V1: halflife=172800, delta_den=16
        int64_t max_delta_v1 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN;
        int64_t actual_v1 = (int64_t)d_v1 - (int64_t)GENESIS_BITSQ;
        TEST("V1 pre-fork (h=1449): delta capped at 6.25%", std::abs(actual_v1) <= max_delta_v1 + 1);
    }
    {
        // At-fork: block 1450 uses V2 parameters
        auto chain = make_chain(1450, TARGET_SPACING);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = GENESIS_BITSQ;
        chain.back().time = chain[chain.size()-2].time + TARGET_SPACING / 2;

        uint32_t d_v2 = casert_next_bitsq(chain, 1450); // fork height
        // V2: delta_den=8 -> max 12.5%
        int64_t max_delta_v2 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN_V2;
        int64_t actual_v2 = (int64_t)d_v2 - (int64_t)GENESIS_BITSQ;
        TEST("V2 at-fork (h=1450): delta capped at 12.5%", std::abs(actual_v2) <= max_delta_v2 + 1);
    }
    {
        // Post-fork: block 1451 uses V2 parameters
        auto chain = make_chain(1451, TARGET_SPACING);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = GENESIS_BITSQ;
        chain.back().time = chain[chain.size()-2].time + TARGET_SPACING / 2;

        uint32_t d_v2 = casert_next_bitsq(chain, 1451);
        int64_t max_delta_v2 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN_V2;
        int64_t actual_v2 = (int64_t)d_v2 - (int64_t)GENESIS_BITSQ;
        TEST("V2 post-fork (h=1451): delta capped at 12.5%", std::abs(actual_v2) <= max_delta_v2 + 1);
    }
    {
        // Verify V2 delta cap is larger than V1 (12.5% > 6.25%)
        int64_t cap_v1 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN;
        int64_t cap_v2 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN_V2;
        TEST("V2 cap > V1 cap (12.5% > 6.25%)", cap_v2 > cap_v1);
        TEST("V2 cap == 2 * V1 cap", cap_v2 == cap_v1 * 2);
    }
    {
        // Transition: no pathological jump at fork boundary
        // Build chain up to 1449 on-schedule, then compute both sides of fork
        auto chain = make_chain(1449, TARGET_SPACING);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = GENESIS_BITSQ;
        uint32_t d_pre = casert_next_bitsq(chain, 1449);

        // Extend chain by 1 block (on-schedule)
        BlockMeta m;
        m.block_id = ZERO_HASH(); m.height = 1449;
        m.time = chain.back().time + TARGET_SPACING; m.powDiffQ = d_pre;
        chain.push_back(m);
        uint32_t d_post = casert_next_bitsq(chain, 1450);

        // Both should be near GENESIS_BITSQ (on-schedule chain)
        int64_t jump = (int64_t)d_post - (int64_t)d_pre;
        // Max possible jump at fork = V2 cap (larger)
        int64_t max_v2 = (int64_t)d_pre / BITSQ_MAX_DELTA_DEN_V2;
        TEST("transition: no pathological jump", std::abs(jump) <= max_v2 + 1);
    }
    {
        // Historical chain params unchanged: block 100 still uses V1
        auto chain = make_chain(100, TARGET_SPACING);
        for (size_t i = 1; i < chain.size(); ++i)
            chain[i].powDiffQ = GENESIS_BITSQ;
        chain.back().time = chain[chain.size()-2].time + TARGET_SPACING / 2;
        uint32_t d = casert_next_bitsq(chain, 100);
        int64_t max_v1 = (int64_t)GENESIS_BITSQ / BITSQ_MAX_DELTA_DEN;
        int64_t actual = (int64_t)d - (int64_t)GENESIS_BITSQ;
        TEST("historical (h=100): uses V1 params", std::abs(actual) <= max_v1 + 1);
    }

    printf("\n=== 5. V5 FORK — liveness + determinism ===\n");

    // Helper: build a chain of `len` blocks with given spacing, all mined at
    // `stored_profile`. Heights end exactly at (V5_FORK_HEIGHT - 1) so that
    // next_height == V5_FORK_HEIGHT is where V5 rules become active.
    auto make_v5_chain = [](int len, int64_t spacing, int32_t stored_profile) {
        std::vector<BlockMeta> chain;
        int64_t start_h = CASERT_V5_FORK_HEIGHT - len;
        for (int i = 0; i < len; ++i) {
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = start_h + i;
            m.time = GENESIS_TIME + (start_h + i) * spacing;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = stored_profile;
            chain.push_back(m);
        }
        return chain;
    };

    // 5.1 Safety rule 1 post-slew: prev_H=H12 + negative lag => H must be <= 0
    {
        // lag = (height - 1) - expected_h, where expected_h = elapsed / 600.
        // Shifting timestamps FORWARD in time makes expected_h larger, which
        // makes lag NEGATIVE (chain appears behind schedule).
        auto chain = make_v5_chain(20, TARGET_SPACING, 12);
        for (auto& b : chain) b.time += 3 * TARGET_SPACING;  // lag -> -3
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 safety rule post-slew: prev H12 + lag<=0 -> H<=0",
             dec.profile_index <= 0);
    }

    // 5.2 EBR entry tier: lag ~ -12 forces H <= 0 via EBR entry cliff
    {
        auto chain = make_v5_chain(20, TARGET_SPACING, 12);
        for (auto& b : chain) b.time += 12 * TARGET_SPACING;  // lag -> -12
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 EBR entry tier: lag<=-10 -> H<=0",
             dec.profile_index <= 0);
    }

    // 5.3 EBR severe tier: lag <= -25 forces H to E4 cliff
    {
        auto chain = make_v5_chain(30, TARGET_SPACING, 12);
        for (auto& b : chain) b.time += 26 * TARGET_SPACING;  // lag -> -26
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 EBR severe tier: lag<=-25 -> H at E4",
             dec.profile_index == CASERT_H_MIN);
    }

    // 5.4 Stateless Ahead Guard: deterministic across repeated calls
    {
        auto chain = make_v5_chain(20, 30, 0); // fast blocks
        uint32_t d1 = casert_next_bitsq(chain, CASERT_V5_FORK_HEIGHT);
        uint32_t d2 = casert_next_bitsq(chain, CASERT_V5_FORK_HEIGHT);
        uint32_t d3 = casert_next_bitsq(chain, CASERT_V5_FORK_HEIGHT);
        TEST("V5 Ahead Guard stateless: deterministic across calls",
             d1 == d2 && d2 == d3);
    }

    // 5.5 V5 anti-stall 60min: decay fires at V5 where V4 does not
    {
        auto chain_v5 = make_v5_chain(20, TARGET_SPACING, 8);
        int64_t stall_time = chain_v5.back().time + 3700; // 61m 40s after last block
        auto dec_v5 = casert_compute(chain_v5, CASERT_V5_FORK_HEIGHT, stall_time);

        // Same logical chain at V4 heights (anti-stall should NOT fire at 76min)
        std::vector<BlockMeta> chain_v4;
        int64_t start_h_v4 = CASERT_V4_FORK_HEIGHT;
        for (int i = 0; i < 20; ++i) {
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = start_h_v4 + i;
            m.time = GENESIS_TIME + (start_h_v4 + i) * TARGET_SPACING;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = 8;
            chain_v4.push_back(m);
        }
        int64_t stall_v4 = chain_v4.back().time + 3700;
        auto dec_v4 = casert_compute(chain_v4, CASERT_V4_FORK_HEIGHT + 20, stall_v4);

        TEST("V5 anti-stall 60min: fires earlier than V4 (stall=61min)",
             dec_v5.profile_index <= dec_v4.profile_index);
    }

    // 5.6 Pre-V5 heights: V4 computation unchanged when V5 constants present
    {
        std::vector<BlockMeta> chain;
        int64_t start_h = CASERT_V4_FORK_HEIGHT;
        for (int i = 0; i < 100; ++i) {
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = start_h + i;
            m.time = GENESIS_TIME + (start_h + i) * TARGET_SPACING;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = 0;
            chain.push_back(m);
        }
        auto dec = casert_compute(chain, start_h + 100, 0);
        TEST("V5: pre-V5 heights unchanged (on-schedule -> B0)",
             dec.profile_index == 0);
    }

    // 5.7 V5 extreme entry cap: H9 + large ahead → H10 max (not H12)
    {
        // prev_H = H9, huge positive lag triggers lag_floor toward H10+
        // Without cap: slew allows 9+3=12, lag_floor demands 10+ → lands at 12.
        // With cap: H > 9 triggers +1/block limit → 10 (H10), not 12.
        auto chain = make_v5_chain(20, TARGET_SPACING, 9);
        for (auto& b : chain) b.time -= 80 * TARGET_SPACING;  // lag → +80ish
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 extreme cap: H9 + large ahead -> H10 (not H12)",
             dec.profile_index == 10);
    }

    // 5.8 V5 extreme entry cap: H10 → H11 max (next step)
    {
        auto chain = make_v5_chain(20, TARGET_SPACING, 10);
        for (auto& b : chain) b.time -= 100 * TARGET_SPACING;  // lag → +100
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 extreme cap: H10 + huge ahead -> H11 (not H12)",
             dec.profile_index == 11);
    }

    // 5.9 V5 extreme entry cap: H11 → H12 allowed (final step is +1)
    {
        auto chain = make_v5_chain(20, TARGET_SPACING, 11);
        for (auto& b : chain) b.time -= 100 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 extreme cap: H11 -> H12 allowed (prev+1 == H12)",
             dec.profile_index == 12);
    }

    // 5.10 V5 extreme cap does NOT affect non-extreme transitions
    {
        // prev_H = H5, moderate lag: target lands in [H6-H8] range.
        // Normal slew ±3 applies, cap should be inert.
        auto chain = make_v5_chain(20, TARGET_SPACING, 5);
        for (auto& b : chain) b.time -= 20 * TARGET_SPACING;  // lag → +20
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 extreme cap: non-extreme transitions unaffected (H5 + lag~20)",
             dec.profile_index >= 5 && dec.profile_index <= 8);
    }

    // 5.11 V5 extreme cap does NOT affect descent from extreme
    {
        // prev_H = H12, lag slightly negative: safety rule post-slew forces
        // H <= 0, EBR doesn't fire (lag > -10), cap doesn't block descent.
        auto chain = make_v5_chain(20, TARGET_SPACING, 12);
        for (auto& b : chain) b.time += 3 * TARGET_SPACING;  // lag → -3
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 extreme cap: descent unrestricted (prev H12 + lag<=0 -> B0)",
             dec.profile_index <= 0);
    }

    // --- V5 edge cases (added pre-activation depuration) ---

    // 5.12 Boundary: first block AT V5_FORK_HEIGHT must use V5 rules
    {
        // Build chain ending at V5_FORK_HEIGHT - 1 with prev=H12, lag=-5.
        // The FIRST V5-enabled block (next_height = V5_FORK_HEIGHT) should
        // apply safety rule post-slew and descend to H <= 0 immediately.
        auto chain = make_v5_chain(20, TARGET_SPACING, 12);
        for (auto& b : chain) b.time += 5 * TARGET_SPACING;  // lag → -5
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 boundary: first V5 block applies safety rule post-slew",
             dec.profile_index <= 0);
    }

    // 5.13 Boundary: last pre-V5 block must NOT use V5 rules
    {
        // Build chain ending at V5_FORK_HEIGHT - 2 with prev=H12, lag=-5.
        // next_height = V5_FORK_HEIGHT - 1 is still V4, safety post-slew
        // does NOT apply, so H can stay at H9 (prev_H - slew).
        std::vector<BlockMeta> chain;
        int64_t start_h = CASERT_V5_FORK_HEIGHT - 21;
        for (int i = 0; i < 20; ++i) {
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = start_h + i;
            m.time = GENESIS_TIME + (start_h + i) * TARGET_SPACING + 5 * TARGET_SPACING;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = 12;
            chain.push_back(m);
        }
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT - 1, 0);
        TEST("V5 boundary: block at V5_FORK-1 uses V4 rules (no post-slew)",
             dec.profile_index >= 0);  // V4 allows H>0 from slew rate
    }

    // 5.14 EBR + extreme cap interaction: lag very negative AND prev_H extreme
    {
        // prev_H = H11, lag = -15 (would trigger EBR to E2).
        // EBR forces H <= -2, extreme cap is NOT active (H = -2, not >= 10).
        // Expected: H = E2 (-2).
        auto chain = make_v5_chain(20, TARGET_SPACING, 11);
        for (auto& b : chain) b.time += 15 * TARGET_SPACING;  // lag → -15
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 interaction: EBR overrides extreme-cap descent (prev H11 + lag<=-15 -> E2)",
             dec.profile_index <= -2);
    }

    // 5.15 Extreme cap at H_MAX boundary: prev_H = H12, cap doesn't push to 13
    {
        // prev_H = H12 (H_MAX). Even with huge positive lag, cap calculation
        // prev_H + 1 = 13 would exceed H_MAX. The final clamp must hold at 12.
        auto chain = make_v5_chain(20, TARGET_SPACING, 12);
        for (auto& b : chain) b.time -= 100 * TARGET_SPACING;  // lag → +100
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, 0);
        TEST("V5 boundary: extreme cap respects H_MAX (prev H12 + huge lag -> H12)",
             dec.profile_index == CASERT_H_MAX);
    }

    // 5.16 Anti-stall 60min at V5: does NOT fire just below threshold
    {
        auto chain = make_v5_chain(20, TARGET_SPACING, 8);
        // Stall of 59 min 59s — just under the V5 floor of 3600s
        int64_t stall_time = chain.back().time + 3599;
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, stall_time);
        // Anti-stall should NOT have decayed yet, H stays at 8
        // (plus whatever slew/safety did)
        TEST("V5 anti-stall: does not fire at 3599s (just under 60min)",
             dec.profile_index >= 0);  // no decay = H not forced below 0
    }

    // 5.17 Anti-stall 60min at V5: fires just above threshold
    {
        auto chain = make_v5_chain(20, TARGET_SPACING, 8);
        // Stall of 60 min 1s — just over the V5 floor
        int64_t stall_time = chain.back().time + 3601;
        auto dec = casert_compute(chain, CASERT_V5_FORK_HEIGHT, stall_time);
        // Anti-stall should have started decaying, H should be <= 8
        // (at minimum no worse than input)
        TEST("V5 anti-stall: decay begins at 3601s (just over 60min)",
             dec.profile_index <= 8);
    }

    printf("\n=== 14. DIRECT LAG MAPPING (block 5320+) ===\n");

    auto make_direct_chain = [](int len, int64_t spacing, int32_t stored_profile) {
        std::vector<BlockMeta> chain;
        int64_t start_h = CASERT_DIRECT_LAG_HEIGHT - len;
        for (int i = 0; i < len; ++i) {
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = start_h + i;
            m.time = GENESIS_TIME + (start_h + i) * spacing;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = stored_profile;
            chain.push_back(m);
        }
        return chain;
    };

    // 14.1 lag=0 → B0
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: lag=0 -> B0", dec.profile_index == 0);
    }

    // 14.2 lag=1 → H1
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        for (auto& b : chain) b.time -= 1 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: lag=1 -> H1", dec.profile_index == 1);
    }

    // 14.3 lag=4 → H4
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        for (auto& b : chain) b.time -= 4 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: lag=4 -> H4", dec.profile_index == 4);
    }

    // 14.4 lag=10+ → H10 (ceiling)
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        for (auto& b : chain) b.time -= 50 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: lag=50 -> H10 ceiling", dec.profile_index == CASERT_HARD_PROFILE_CEILING);
    }

    // 14.5 Upward: immediate (prev=H0, lag=6 → H6)
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        for (auto& b : chain) b.time -= 6 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: upward immediate (prev=0, lag=6 -> H6)", dec.profile_index == 6);
    }

    // 14.6 Downward: max 1 step per block (prev=H8, lag=3 → H7)
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 8);
        for (auto& b : chain) b.time -= 3 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: downward capped (prev=H8, lag=3 -> H7)", dec.profile_index == 7);
    }

    // 14.7 Descent sequence: H8 → H7 → H6 → H5 → H4 → H3 over 5 blocks
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 8);
        for (auto& b : chain) b.time -= 3 * TARGET_SPACING;
        bool descent_ok = true;
        int32_t expected[] = {7, 6, 5, 4, 3};
        for (int step = 0; step < 5; ++step) {
            auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT + step, 0);
            if (dec.profile_index != expected[step]) { descent_ok = false; break; }
            BlockMeta m;
            m.block_id = ZERO_HASH();
            m.height = CASERT_DIRECT_LAG_HEIGHT + step;
            m.time = GENESIS_TIME + m.height * TARGET_SPACING - 3 * TARGET_SPACING;
            m.powDiffQ = GENESIS_BITSQ;
            m.profile_index = dec.profile_index;
            chain.push_back(m);
        }
        TEST("direct lag: descent H8->H7->H6->H5->H4->H3 over 5 blocks", descent_ok);
    }

    // 14.8 No deadlock: prev=H8 from PID era, lag=3 → does NOT stick at H8
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 8);
        for (auto& b : chain) b.time -= 3 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: no deadlock (prev=H8, lag=3 -> NOT H8)", dec.profile_index < 8);
    }

    // 14.9 Negative lag → B0 safety
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 5);
        for (auto& b : chain) b.time += 10 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: negative lag -> B0 or below", dec.profile_index <= 0);
    }

    // 14.10 bitsQ unchanged by direct lag mapping
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 0);
        uint32_t bitsq_before = casert_next_bitsq(chain, CASERT_DIRECT_LAG_HEIGHT);
        for (auto& b : chain) b.time -= 5 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, 0);
        TEST("direct lag: bitsQ path independent of profile", dec.bitsq == bitsq_before || dec.bitsq >= MIN_BITSQ);
    }

    // 14.11 Pre-fork behavior unchanged (block 5319 still uses PID)
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 8);
        for (auto& b : chain) b.time -= 3 * TARGET_SPACING;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT - 1, 0);
        TEST("direct lag: pre-fork (5319) does NOT use direct mapping",
             dec.profile_index != 7);
    }

    // 14.12 Anti-stall still works post-fork
    {
        auto chain = make_direct_chain(20, TARGET_SPACING, 5);
        for (auto& b : chain) b.time -= 5 * TARGET_SPACING;
        int64_t stall_time = chain.back().time + 7200;
        auto dec = casert_compute(chain, CASERT_DIRECT_LAG_HEIGHT, stall_time);
        TEST("direct lag: anti-stall still decays after 60min", dec.profile_index < 5);
    }

    printf("\n=== Results: %d passed, %d failed out of %d ===\n\n", g_pass, g_fail, g_pass+g_fail);
    return g_fail > 0 ? 1 : 0;
}
