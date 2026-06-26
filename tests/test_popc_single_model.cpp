// =============================================================================
// test_popc_single_model.cpp — Transition tests for the PoPC single-model
// redesign (whitepaper §6.0). DRAFT / consensus-DEFERRED.
// =============================================================================
//
// Covers:
//   Height gate (PSM01-03): inert before activation, active at/after it; the
//                           legacy base reward table is untouched.
//   Gold boost tiers (PSM10-16): +0 / +10 / +20% by continuously-verified days,
//                           boundary days, operational cap, technical max.
//   Apply boost (PSM20-23): base * (1 + boost); the 12-month worked example.
//   Invariants (PSM30-31): boost never exceeds the operational cap; the cap
//                           never exceeds the technical maximum.
//
// These exercise PURE functions only. Nothing here activates consensus, moves
// funds, slashes, or treats gold as collateral.
// =============================================================================

#include "sost/popc.h"
#include "sost/params.h"

#include <cstdint>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

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
// Height gate — works regardless of build profile (mainnet INT64_MAX or testnet).
// =============================================================================

TEST(PSM01_gate_active_at_height) {
    // At exactly the activation height the single model is active.
    EXPECT(popc_single_model_active(POPC_SINGLE_MODEL_HEIGHT) == true,
           "single model must be active AT the activation height");
}

TEST(PSM02_gate_inert_before_height) {
    // One block before the activation height it is inert. (Guarded against
    // underflow: INT64_MAX - 1 is well-defined.)
    EXPECT(popc_single_model_active(POPC_SINGLE_MODEL_HEIGHT - 1) == false,
           "single model must be inert one block before activation");
    EXPECT(popc_single_model_active(0) == false,
           "single model must be inert at genesis");
}

TEST(PSM04_base_tied_to_v15) {
    // The single-model base activates with V15 — it replaces Model A/B at the
    // same height PoPC goes live (no superseded architecture is launched).
    EXPECT(POPC_SINGLE_MODEL_HEIGHT == V15_HEIGHT,
           "single-model base height must equal V15_HEIGHT");
}

TEST(PSM05_gold_never_before_base) {
    EXPECT(POPC_GOLD_BOOST_HEIGHT >= POPC_SINGLE_MODEL_HEIGHT,
           "Gold Boost must never activate before the native base model");
}

TEST(PSM06_gold_gate_active_and_inert) {
    EXPECT(popc_gold_boost_active(POPC_GOLD_BOOST_HEIGHT) == true,
           "gold boost active AT its gate");
    EXPECT(popc_gold_boost_active(POPC_GOLD_BOOST_HEIGHT - 1) == false,
           "gold boost inert one block before its gate");
    EXPECT(popc_gold_boost_active(0) == false,
           "gold boost inert at genesis");
}

TEST(PSM03_legacy_base_table_untouched) {
    // The redesign does NOT change the base reward table — the boost rides on top.
    EXPECT(POPC_REWARD_RATES[0] == 100,  "1mo base must stay 1%");
    EXPECT(POPC_REWARD_RATES[1] == 400,  "3mo base must stay 4%");
    EXPECT(POPC_REWARD_RATES[2] == 900,  "6mo base must stay 9%");
    EXPECT(POPC_REWARD_RATES[3] == 1400, "9mo base must stay 14%");
    EXPECT(POPC_REWARD_RATES[4] == 2000, "12mo base must stay 20%");
}

// =============================================================================
// Gold boost tiers
// =============================================================================

TEST(PSM10_no_gold_zero_boost) {
    EXPECT(popc_gold_boost_bps(0)   == 0, "0 days -> +0%");
    EXPECT(popc_gold_boost_bps(-5)  == 0, "negative days -> +0%");
}

TEST(PSM11_below_31_days_zero_boost) {
    EXPECT(popc_gold_boost_bps(1)  == 0, "1 day -> +0%");
    EXPECT(popc_gold_boost_bps(30) == 0, "30 days (last day of tier 0) -> +0%");
}

TEST(PSM12_partial_tier_31_to_90) {
    EXPECT(popc_gold_boost_bps(31) == 1000, "31 days (first day of +10%) -> +10%");
    EXPECT(popc_gold_boost_bps(60) == 1000, "60 days -> +10%");
    EXPECT(popc_gold_boost_bps(90) == 1000, "90 days (last day of +10%) -> +10%");
}

TEST(PSM13_full_tier_91_plus) {
    EXPECT(popc_gold_boost_bps(91)    == 2000, "91 days (first day of +20%) -> +20%");
    EXPECT(popc_gold_boost_bps(365)   == 2000, "365 days -> +20%");
    EXPECT(popc_gold_boost_bps(100000) == 2000, "very large -> still +20% (operational cap)");
}

TEST(PSM14_boost_never_exceeds_operational_cap) {
    for (int64_t d = 0; d <= 5000; d += 7) {
        EXPECT(popc_gold_boost_bps(d) <= POPC_GOLD_BOOST_CAP_BPS,
               "boost must never exceed the +20% operational cap");
    }
}

TEST(PSM15_operational_cap_value) {
    EXPECT(POPC_GOLD_BOOST_CAP_BPS == 2000, "operational cap must be +20%");
}

TEST(PSM16_technical_max_value) {
    EXPECT(POPC_GOLD_BOOST_MAX_BPS == 2500, "technical maximum must be +25%");
}

// =============================================================================
// Apply boost to a base reward
// =============================================================================

TEST(PSM20_apply_no_gold_is_identity) {
    EXPECT(popc_apply_gold_boost(2000, 0)  == 2000, "20% base, no gold -> 20%");
    EXPECT(popc_apply_gold_boost(900, 30)  == 900,  "9% base, 30 days -> 9%");
}

TEST(PSM21_apply_partial_boost) {
    // 20% base + 10% boost = 22%
    EXPECT(popc_apply_gold_boost(2000, 31) == 2200, "20% base + 31 days -> 22%");
    // 9% base + 10% = 9.9% -> 990 bps
    EXPECT(popc_apply_gold_boost(900, 60)  == 990,  "9% base + 60 days -> 9.9%");
}

TEST(PSM22_worked_example_12mo_full_boost) {
    // Whitepaper §6.0 worked example: 12-month bond = 20% base; gold 91+ days
    // -> +20% -> 20% * 1.20 = 24%.
    uint16_t base = POPC_REWARD_RATES[4];               // 2000 bps = 20%
    EXPECT(popc_apply_gold_boost(base, 91) == 2400, "12mo + 91 days -> 24%");
    EXPECT(popc_apply_gold_boost(base, 0)  == 2000, "12mo without gold -> 20%");
}

TEST(PSM23_apply_never_exceeds_base_times_125) {
    // No (base, days) combination may exceed base * 1.25 (the technical ceiling).
    const uint16_t bases[] = {100, 400, 900, 1400, 2000, 2500};
    for (uint16_t b : bases) {
        for (int64_t d = 0; d <= 5000; d += 13) {
            uint32_t out = popc_apply_gold_boost(b, d);
            uint32_t ceil = b + (uint32_t)((uint64_t)b * POPC_GOLD_BOOST_MAX_BPS / 10000);
            EXPECT(out <= ceil, "boosted reward must never exceed base * 1.25");
        }
    }
}

// =============================================================================
// Surplus-aware Gold Boost payout (funding rules: PoPC Pool, base priority)
// =============================================================================

TEST(PSM40_payout_full_when_surplus_ample) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out  = popc_gold_boost_payout_stocks(base, 91, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == 20 * (int64_t)STOCKS_PER_SOST, "100 base + 91d, ample surplus -> 20 boost");
}

TEST(PSM41_payout_partial_tier) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out  = popc_gold_boost_payout_stocks(base, 31, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == 10 * (int64_t)STOCKS_PER_SOST, "100 base + 31d, ample surplus -> 10 boost");
}

TEST(PSM42_payout_throttled_by_surplus) {
    int64_t base    = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t surplus = 5  * (int64_t)STOCKS_PER_SOST;   // desired +20% = 20, surplus only 5
    EXPECT(popc_gold_boost_payout_stocks(base, 91, surplus) == surplus,
           "boost throttled to available surplus");
}

TEST(PSM43_payout_zero_when_no_surplus) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    EXPECT(popc_gold_boost_payout_stocks(base, 91, 0)   == 0, "no surplus -> 0 boost");
    EXPECT(popc_gold_boost_payout_stocks(base, 91, -50) == 0, "negative surplus -> 0 boost");
}

TEST(PSM44_payout_zero_without_gold_or_base) {
    int64_t pool = 1000 * (int64_t)STOCKS_PER_SOST;
    EXPECT(popc_gold_boost_payout_stocks(100 * (int64_t)STOCKS_PER_SOST, 0, pool) == 0,
           "no verified gold -> 0 boost");
    EXPECT(popc_gold_boost_payout_stocks(0, 91, pool) == 0, "no base reward -> 0 boost");
}

TEST(PSM45_payout_never_exceeds_ceiling_or_surplus) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t ceil = base * POPC_GOLD_BOOST_MAX_BPS / 10000;   // base * 25%
    for (int64_t d = 0; d <= 1000; d += 11) {
        for (int64_t s = 0; s <= base; s += base / 7 + 1) {
            int64_t out = popc_gold_boost_payout_stocks(base, d, s);
            EXPECT(out >= 0,        "payout never negative");
            EXPECT(out <= ceil,     "payout never exceeds base * 1.25 ceiling");
            EXPECT(out <= s,        "payout never exceeds surplus");
        }
    }
}

// =============================================================================
// Settle-time reward composition (transition matrix) — base never depends on gold
// =============================================================================

TEST(PSM50_legacy_below_activation) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    // single_model OFF -> legacy == base, regardless of gold/surplus.
    int64_t out = popc_settle_reward_stocks(false, false, base, true, 360, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base, "height < activation -> legacy base, no boost");
}

TEST(PSM51_single_model_base_when_gold_gate_deferred) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    // single ON but gold boost gate OFF -> base only.
    int64_t out = popc_settle_reward_stocks(true, false, base, true, 360, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base, "single-model active, gold deferred -> base only");
}

TEST(PSM52_no_gold_means_base_only) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out = popc_settle_reward_stocks(true, true, base, false, 360, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base, "no gold -> base only");
}

TEST(PSM53_boost_partial_tier_with_surplus) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    // 31-90 days -> +10%
    int64_t out = popc_settle_reward_stocks(true, true, base, true, 90, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base + 10 * (int64_t)STOCKS_PER_SOST, "gold 90d + surplus -> base +10%");
}

TEST(PSM54_boost_full_tier_with_surplus) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out = popc_settle_reward_stocks(true, true, base, true, 180, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base + 20 * (int64_t)STOCKS_PER_SOST, "gold 180d + surplus -> base +20%");
}

TEST(PSM55_insufficient_surplus_trims_boost_not_base) {
    int64_t base    = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t surplus = 5   * (int64_t)STOCKS_PER_SOST;   // wants +20=20, only 5 available
    int64_t out = popc_settle_reward_stocks(true, true, base, true, 360, surplus);
    EXPECT(out == base + surplus, "partial surplus -> trimmed boost, base intact");
    EXPECT(out >= base, "base is never reduced");
}

TEST(PSM56_zero_surplus_pays_base_only) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out = popc_settle_reward_stocks(true, true, base, true, 360, 0);
    EXPECT(out == base, "zero surplus -> base intact, boost 0");
}

TEST(PSM57_base_never_depends_on_gold_or_surplus) {
    // THE invariant: for any gate/gold/surplus combo, the payout is >= base.
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    bool bools[] = {false, true};
    int64_t surpluses[] = {-10, 0, 1, 7, 1000};
    for (bool sm : bools) for (bool gb : bools) for (bool hg : bools)
        for (int64_t d : {0, 30, 90, 180, 360})
            for (int64_t s : surpluses) {
                int64_t out = popc_settle_reward_stocks(sm, gb, base, hg, d, s * (int64_t)STOCKS_PER_SOST);
                EXPECT(out >= base, "base_reward must never depend on gold or surplus");
            }
}

// =============================================================================
// Structural invariants
// =============================================================================

TEST(PSM30_cap_does_not_exceed_max) {
    EXPECT(POPC_GOLD_BOOST_CAP_BPS <= POPC_GOLD_BOOST_MAX_BPS,
           "operational cap must not exceed the technical maximum");
}

TEST(PSM31_tier_boundaries_consistent) {
    EXPECT(POPC_GOLD_BOOST_DAYS_PARTIAL < POPC_GOLD_BOOST_DAYS_FULL,
           "partial-tier day must come before full-tier day");
    EXPECT(POPC_GOLD_BOOST_BPS_NONE < POPC_GOLD_BOOST_BPS_PARTIAL,
           "tier bps must increase");
    EXPECT(POPC_GOLD_BOOST_BPS_PARTIAL < POPC_GOLD_BOOST_BPS_FULL,
           "tier bps must increase");
}

// =============================================================================
// main
// =============================================================================

int main() {
    std::cout << "=== PoPC single-model redesign (transition) Tests ===" << std::endl;

    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev_fail = g_fail;
        fn();
        if (g_fail == prev_fail) {
            g_pass++;
            std::cout << "PASS" << std::endl;
        } else {
            std::cout << "*** FAIL ***" << std::endl;
        }
    }

    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail
              << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;

    return g_fail > 0 ? 1 : 0;
}
