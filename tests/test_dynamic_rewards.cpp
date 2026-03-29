// =============================================================================
// test_dynamic_rewards.cpp — Tests for Dynamic Reward System (PUR-based)
// =============================================================================
//
// Tests cover:
//   Pool Utilization Ratio (DYN01-04), Dynamic factor curve (DYN05-08),
//   Reward application with floor (DYN09-11), Anti-whale tiers (DYN12-15),
//   Escrow rate halving (DYN16), Reservation lifecycle (DYN17-18)
// =============================================================================

#include "sost/popc.h"
#include "sost/popc_tx_builder.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>
#include <string>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define TEST(name) \
    static void test_##name(); \
    struct reg_##name { reg_##name() { tests().push_back({#name, test_##name}); } } r_##name; \
    static void test_##name()

static std::vector<std::pair<std::string, void(*)()>>& tests() {
    static std::vector<std::pair<std::string, void(*)()>> t;
    return t;
}

#define EXPECT(cond, msg) do { \
    if (!(cond)) { \
        std::cerr << "  EXPECT failed: " << msg << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

// =============================================================================
// Pool Utilization Ratio (PUR) tests
// =============================================================================

// DYN01: committed=0, pool=100M → PUR=0 (empty pool of commitments)
TEST(DYN01_pur_zero) {
    int32_t pur = compute_pur_bps(0LL, 100000000LL);
    EXPECT(pur == 0, "committed=0 should give PUR=0, got " + std::to_string(pur));
}

// DYN02: committed=50M, pool=100M → PUR=5000 (50%)
TEST(DYN02_pur_50pct) {
    int32_t pur = compute_pur_bps(50000000LL, 100000000LL);
    EXPECT(pur == 5000, "committed=50% of pool should give PUR=5000, got " + std::to_string(pur));
}

// DYN03: committed=100M, pool=100M → PUR=10000 (100%)
TEST(DYN03_pur_100pct) {
    int32_t pur = compute_pur_bps(100000000LL, 100000000LL);
    EXPECT(pur == 10000, "committed=pool should give PUR=10000, got " + std::to_string(pur));
}

// DYN04: committed=100, pool=0 → PUR=10000 (pool empty = closed)
TEST(DYN04_pur_empty_pool) {
    int32_t pur = compute_pur_bps(100LL, 0LL);
    EXPECT(pur == PUR_CLOSED_BPS, "pool=0 should return PUR_CLOSED_BPS=" + std::to_string(PUR_CLOSED_BPS)
           + ", got " + std::to_string(pur));
}

// =============================================================================
// Dynamic factor curve tests — quadratic: (1 - PUR)^2
// =============================================================================

// DYN05: PUR=0 → factor=10000 (100% — full reward)
TEST(DYN05_factor_at_pur0) {
    int32_t factor = compute_dynamic_factor_bps(0);
    EXPECT(factor == 10000, "PUR=0 should give factor=10000 (100%), got " + std::to_string(factor));
}

// DYN06: PUR=5000 → factor=2500 (25%)
// Quadratic: (1 - 0.5)^2 = 0.25 → 2500 bps
// inv=5000; 5000*5000/10000 = 2500
TEST(DYN06_factor_at_pur50) {
    int32_t factor = compute_dynamic_factor_bps(5000);
    EXPECT(factor == 2500, "PUR=5000 should give factor=2500, got " + std::to_string(factor));
}

// DYN07: PUR=8000 → factor=400 (4%)
// Quadratic: (1 - 0.8)^2 = 0.04 → 400 bps
// inv=2000; 2000*2000/10000 = 400
TEST(DYN07_factor_at_pur80) {
    int32_t factor = compute_dynamic_factor_bps(8000);
    EXPECT(factor == 400, "PUR=8000 should give factor=400 (4%), got " + std::to_string(factor));
}

// DYN08: PUR=10000 (closed) → factor=0
TEST(DYN08_factor_at_pur100) {
    int32_t factor = compute_dynamic_factor_bps(10000);
    EXPECT(factor == 0, "PUR=10000 should give factor=0, got " + std::to_string(factor));
}

// =============================================================================
// Reward application tests — apply_dynamic_reward(base, factor, floor)
// =============================================================================

// DYN09: base=2200, factor=10000 → 2200 * 10000 / 10000 = 2200 (no reduction)
TEST(DYN09_apply_dynamic_max) {
    uint16_t result = apply_dynamic_reward(2200, 10000, 100);
    EXPECT(result == 2200, "base=2200 at factor=10000 should remain 2200, got " + std::to_string(result));
}

// DYN10: base=2200, factor=5000 → 2200 * 5000 / 10000 = 1100
TEST(DYN10_apply_dynamic_half) {
    uint16_t result = apply_dynamic_reward(2200, 5000, 100);
    EXPECT(result == 1100, "base=2200 at factor=5000 should be 1100, got " + std::to_string(result));
}

// DYN11: base=2200, factor=100 → 2200 * 100 / 10000 = 22, but floor=100 → result is 100
TEST(DYN11_apply_dynamic_floor) {
    uint16_t result = apply_dynamic_reward(2200, 100, 100);
    EXPECT(result == 100, "base=2200 at factor=100 (raw=22) must be floored to 100, got " + std::to_string(result));
}

// =============================================================================
// Anti-whale tier tests
// =============================================================================

// DYN12: gold=300000mg (9.64 oz) — under 10 oz tier → multiplier=10000 (100%)
TEST(DYN12_whale_under_10oz) {
    uint16_t mult = whale_tier_multiplier(300000LL);
    EXPECT(mult == 10000, "300000mg (<10oz) should give multiplier=10000 (100%), got " + std::to_string(mult));
}

// DYN13: gold=1000000mg (32.15 oz) — 10-50 oz tier → multiplier=7500 (75%)
TEST(DYN13_whale_10_to_50oz) {
    uint16_t mult = whale_tier_multiplier(1000000LL);
    EXPECT(mult == 7500, "1000000mg (32oz) should give multiplier=7500 (75%), got " + std::to_string(mult));
}

// DYN14: gold=5000000mg (160.75 oz) — 50-200 oz tier → multiplier=5000 (50%)
TEST(DYN14_whale_50_to_200oz) {
    uint16_t mult = whale_tier_multiplier(5000000LL);
    EXPECT(mult == 5000, "5000000mg (161oz) should give multiplier=5000 (50%), got " + std::to_string(mult));
}

// DYN15: gold=7000000mg (225 oz) — above 200 oz hard cap → multiplier=0 (REJECTED)
TEST(DYN15_whale_over_200oz) {
    uint16_t mult = whale_tier_multiplier(7000000LL);
    EXPECT(mult == 0, "7000000mg (225oz) above hard cap should give multiplier=0 (REJECTED), got " + std::to_string(mult));
}

// =============================================================================
// Escrow reward rate tests
// =============================================================================

// DYN16: ESCROW_REWARD_RATES[4] (12-month) = 1100, exactly half of POPC_REWARD_RATES[4] = 2200
TEST(DYN16_escrow_rate_halved) {
    uint16_t escrow_rate = ESCROW_REWARD_RATES[4];  // 12-month tier
    uint16_t popc_rate   = POPC_REWARD_RATES[4];    // 12-month tier
    EXPECT(popc_rate == 2200,
           "POPC_REWARD_RATES[4] (12mo) should be 2200, got " + std::to_string(popc_rate));
    EXPECT(escrow_rate == 1100,
           "ESCROW_REWARD_RATES[4] (12mo) should be 1100 (half of 2200), got " + std::to_string(escrow_rate));
    EXPECT(escrow_rate == popc_rate / 2,
           "Escrow rate should be exactly half of PoPC rate for each tier");
}

// =============================================================================
// Reservation lifecycle tests
// =============================================================================

// DYN17: add_committed / release_committed on PoPCRegistry
TEST(DYN17_reservation_flow) {
    PoPCRegistry reg;
    EXPECT(reg.committed_rewards() == 0, "initial committed_rewards should be 0");

    reg.add_committed(1000000);
    EXPECT(reg.committed_rewards() == 1000000,
           "after add_committed(1000000), committed should be 1000000, got " + std::to_string(reg.committed_rewards()));

    reg.release_committed(500000);
    EXPECT(reg.committed_rewards() == 500000,
           "after release_committed(500000), committed should be 500000, got " + std::to_string(reg.committed_rewards()));

    // Release more than held — should floor at 0 (no negative committed)
    reg.release_committed(999999);
    EXPECT(reg.committed_rewards() == 0,
           "releasing more than committed should floor at 0, got " + std::to_string(reg.committed_rewards()));
}

// DYN18: full lifecycle — PUR rises as commitments are added, drops when released
TEST(DYN18_full_lifecycle) {
    const int64_t pool_balance = 100000000LL; // 1 SOST pool

    PoPCRegistry reg;

    // Initially: PUR=0, factor=10000 → full reward available
    int32_t pur0 = compute_pur_bps(reg.committed_rewards(), pool_balance);
    EXPECT(pur0 == 0, "initial PUR should be 0, got " + std::to_string(pur0));

    int32_t factor0 = compute_dynamic_factor_bps(pur0);
    EXPECT(factor0 == 10000, "initial factor should be 10000, got " + std::to_string(factor0));

    // Reserve 50% of pool
    reg.add_committed(50000000LL);
    int32_t pur1 = compute_pur_bps(reg.committed_rewards(), pool_balance);
    EXPECT(pur1 == 5000, "after 50% committed, PUR should be 5000, got " + std::to_string(pur1));

    int32_t factor1 = compute_dynamic_factor_bps(pur1);
    EXPECT(factor1 == 2500, "at PUR=5000, factor should be 2500 (quadratic), got " + std::to_string(factor1));

    // Apply to 12-month reward rate: 2200 bps at factor 2500 → 550 bps
    uint16_t adjusted_rate = apply_dynamic_reward(2200, factor1, 100);
    EXPECT(adjusted_rate == 550,
           "12-month rate (2200) at factor=2500 should yield 550 bps, got " + std::to_string(adjusted_rate));

    // Reserve another 30% (total 80%)
    reg.add_committed(30000000LL);
    int32_t pur2 = compute_pur_bps(reg.committed_rewards(), pool_balance);
    EXPECT(pur2 == 8000, "after 80% committed, PUR should be 8000, got " + std::to_string(pur2));

    int32_t factor2 = compute_dynamic_factor_bps(pur2);
    EXPECT(factor2 == 400, "at PUR=8000, factor should be 400 (4%), got " + std::to_string(factor2));

    // At factor=400: 2200*400/10000 = 88 → floored to 100
    uint16_t floor_rate = apply_dynamic_reward(2200, factor2, 100);
    EXPECT(floor_rate == 100,
           "12-month rate at factor=400 (raw=88) should be floored to 100, got " + std::to_string(floor_rate));

    // Release the 50M reservation → back to 30% committed
    reg.release_committed(50000000LL);
    int32_t pur3 = compute_pur_bps(reg.committed_rewards(), pool_balance);
    EXPECT(pur3 == 3000, "after release, PUR should drop to 3000, got " + std::to_string(pur3));

    int32_t factor3 = compute_dynamic_factor_bps(pur3);
    // (1-0.3)^2 = 0.49 → 4900 bps; inv=7000; 7000*7000/10000=4900
    EXPECT(factor3 == 4900, "at PUR=3000, factor should be 4900 (49%), got " + std::to_string(factor3));
}

// =============================================================================
// main
// =============================================================================

int main() {
    std::cout << "=== Dynamic Rewards Tests ===" << std::endl;
    for (auto& [name, fn] : tests()) {
        g_pass++;
        int before = g_fail;
        fn();
        if (g_fail > before) g_pass--;
        std::cout << (g_fail > before ? "  FAIL" : "  PASS") << "  " << name << std::endl;
    }
    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;
    return g_fail > 0 ? 1 : 0;
}
