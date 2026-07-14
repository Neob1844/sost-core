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
#include "sost/gv_g4.h"   // GV_G4_ACTIVATION_HEIGHT — Gold Vault governance decoupling check
#include "sost/gv_g5.h"   // GV_G5_ACTIVATION_HEIGHT

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

// PSM58: the explicit by-height settle matrix — chains popc_single_model_active(h)
// AND popc_gold_boost_active(h) into popc_settle_reward_stocks, the exact path the
// node's popc_release handler runs. Build-agnostic: on the mainnet build the gold
// gate is deferred (INT64_MAX) so V15 pays base only; on the -DSOST_TESTNET_FORKS
// build the gold gate equals V15 so V15 can pay base+boost. We assert the right
// branch from what the gates actually return, never from a hard-coded height.
TEST(PSM58_by_height_settle_matrix) {
    const int64_t base    = 100  * (int64_t)STOCKS_PER_SOST;
    const int64_t surplus = 1000 * (int64_t)STOCKS_PER_SOST;

    // h = V15_HEIGHT - 1  (e.g. 19,999 on mainnet): single-model inert -> legacy base,
    // regardless of gold/days/surplus.
    int64_t below = popc_settle_reward_stocks(
        popc_single_model_active(V15_HEIGHT - 1),
        popc_gold_boost_active(V15_HEIGHT - 1),
        base, /*has_gold=*/true, /*days=*/360, surplus);
    EXPECT(below == base, "one block before V15 -> legacy base, no boost");

    // h = V15_HEIGHT (20,000 on mainnet): single-model ACTIVE. The two gates are
    // independent — the gold boost applies ONLY if its own gate is also active.
    bool single_at_v15 = popc_single_model_active(V15_HEIGHT);
    bool gold_at_v15   = popc_gold_boost_active(V15_HEIGHT);
    EXPECT(single_at_v15 == true, "single-model must be active at V15");
    int64_t at_v15 = popc_settle_reward_stocks(single_at_v15, gold_at_v15,
                                               base, /*has_gold=*/true, /*days=*/360, surplus);
    if (gold_at_v15) {
        // testnet build: gold gate == V15 -> base + full-tier boost (+20%).
        EXPECT(at_v15 == base + 20 * (int64_t)STOCKS_PER_SOST,
               "V15 with gold gate active (testnet) -> base + boost");
    } else {
        // mainnet build: gold gate deferred (INT64_MAX) -> base only, NO boost.
        EXPECT(at_v15 == base, "V15 with gold boost deferred (mainnet) -> base only");
    }

    // single-model active != gold boost active: two distinct gates, gold never first.
    EXPECT(POPC_GOLD_BOOST_HEIGHT >= POPC_SINGLE_MODEL_HEIGHT,
           "gold boost gate must never precede the single-model gate");
}

// =============================================================================
// Gold Boost eligibility threshold: max(25% of bond value, 0.25 PAXG/XAUT)
// =============================================================================

TEST(PSM60_dust_gold_not_eligible) {
    // 0.001 PAXG ~ 31 mg, far below the 0.25 oz (7775 mg) floor.
    EXPECT(popc_gold_boost_eligible(31, 100000, 1000) == false,
           "dust 0.001 PAXG must not qualify");
}

TEST(PSM61_below_quarter_oz_not_eligible) {
    // 0.2 oz = 6220 mg < 7775 mg floor, even with a huge value.
    EXPECT(popc_gold_boost_eligible(6220, 1000000000, 1000) == false,
           "below 0.25 PAXG/XAUT must not qualify");
}

TEST(PSM62_below_25pct_bond_not_eligible) {
    // Above the dust floor (8000 mg) but gold value < 25% of bond value:
    // gold_value 1000 micro, bond_value 100000 micro -> 25% = 25000 > 1000.
    EXPECT(popc_gold_boost_eligible(8000, 1000, 100000) == false,
           "gold below 25% of bond value must not qualify");
}

TEST(PSM63_meets_both_qualifies) {
    // 8000 mg (>= 0.25 oz) and gold_value 30000 >= 25% of bond 100000 (=25000).
    EXPECT(popc_gold_boost_eligible(8000, 30000, 100000) == true,
           "gold above max(25% bond, 0.25 PAXG/XAUT) qualifies");
}

TEST(PSM64_exactly_quarter_oz_floor) {
    EXPECT(popc_gold_boost_eligible(POPC_GOLD_MIN_ABS_MG, 1000000, 1000) == true,
           "exactly 0.25 oz with ample value qualifies");
    EXPECT(popc_gold_boost_eligible(POPC_GOLD_MIN_ABS_MG - 1, 1000000, 1000) == false,
           "one mg below 0.25 oz does not qualify");
    EXPECT(POPC_GOLD_MIN_ABS_MG == 7775, "0.25 oz floor = 31103/4 = 7775 mg");
}

TEST(PSM65_eligible_plus_insufficient_surplus_clips_boost) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    bool elig = popc_gold_boost_eligible(8000, 30000, 100000);   // qualifies
    int64_t out = popc_settle_reward_stocks(true, true, base, elig, 360, 5 * (int64_t)STOCKS_PER_SOST);
    EXPECT(elig == true, "precondition: qualifies");
    EXPECT(out == base + 5 * (int64_t)STOCKS_PER_SOST, "qualifying gold + small surplus -> clipped boost");
}

TEST(PSM66_eligible_plus_no_surplus_base_only) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    bool elig = popc_gold_boost_eligible(8000, 30000, 100000);
    int64_t out = popc_settle_reward_stocks(true, true, base, elig, 360, 0);
    EXPECT(out == base, "qualifying gold + no surplus -> base only");
}

TEST(PSM67_not_eligible_pays_base_only) {
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    bool elig = popc_gold_boost_eligible(31, 100, 100000);       // dust -> not eligible
    int64_t out = popc_settle_reward_stocks(true, true, base, elig, 360, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(elig == false, "precondition: dust does not qualify");
    EXPECT(out == base, "non-qualifying gold -> base only despite surplus");
}

TEST(PSM68_eligibility_overflow_safe) {
    // gold_value_micro * 4 must not wrap. 4e18 * 4 overflows int64; with 128-bit
    // math the huge-gold case still qualifies and the huge-bond case still rejects.
    int64_t big = 4000000000000000000LL;  // 4e18
    EXPECT(popc_gold_boost_eligible(8000, big, 1000) == true,
           "huge gold value must not wrap to a rejection");
    EXPECT(popc_gold_boost_eligible(8000, 1000, big) == false,
           "huge bond value must not wrap to a false qualification");
}

// =============================================================================
// Continuous-verification interface + snapshot guard + governance decoupling
// =============================================================================

TEST(PSM69_snapshot_gold_earns_no_boost) {
    // Eligible by amount/value, gates on, ample surplus — but 0 PROVEN continuous
    // days (only a registration snapshot) -> base only. This is the anti-snapshot guard.
    int64_t base = 100 * (int64_t)STOCKS_PER_SOST;
    int64_t out = popc_settle_reward_stocks(true, true, base, true, 0, 1000 * (int64_t)STOCKS_PER_SOST);
    EXPECT(out == base, "snapshot gold (0 continuous days) earns no boost despite surplus");
}

TEST(PSM70_payout_overflow_safe) {
    // 1e17 stocks: base * 2000 overflows int64 without 128-bit math.
    int64_t base = 100000000000000000LL;
    int64_t out  = popc_gold_boost_payout_stocks(base, 91, base);   // ample surplus
    EXPECT(out == base / 5, "1e17 base +20% computed without wrap (= base/5)");
}

TEST(PSM71_commitment_gold_verified_days_default_zero) {
    PoPCCommitment c{};
    EXPECT(c.gold_verified_days == 0, "gold_verified_days must default to 0 (no snapshot credit)");
}

TEST(PSM72_gold_vault_governance_decoupled) {
    // Activating the PoPC single model must NOT activate Gold Vault spend-governance.
    EXPECT(GV_G4_ACTIVATION_HEIGHT >= POPC_SINGLE_MODEL_HEIGHT, "G4 never activates before the base model");
    EXPECT(GV_G5_ACTIVATION_HEIGHT >= POPC_SINGLE_MODEL_HEIGHT, "G5 never activates before the base model");
}

TEST(PSM73_continuous_days_broken_when_gold_dips) {
    int64_t first = 1000, last = 1000 + 91 * 144, req = 8000, bpd = 144;
    EXPECT(popc_continuous_verified_days(first, last, req - 1, req, bpd) == 0,
           "a dip below required breaks continuity -> 0 days");
}

TEST(PSM74_continuous_days_full_span_when_held) {
    int64_t first = 1000, last = 1000 + 91 * 144, req = 8000, bpd = 144;
    EXPECT(popc_continuous_verified_days(first, last, req,        req, bpd) == 91, "held at required -> 91 days");
    EXPECT(popc_continuous_verified_days(first, last, req + 5000, req, bpd) == 91, "held above required -> 91 days");
}

TEST(PSM75_continuous_days_edge_cases) {
    EXPECT(popc_continuous_verified_days(0, 1000, 9000, 8000, 144) == 0, "no first height -> 0");
    EXPECT(popc_continuous_verified_days(1000, 1000, 9000, 8000, 144) == 0, "zero span -> 0");
    EXPECT(popc_continuous_verified_days(1000, 2000, 9000, 8000, 0) == 0, "blocks_per_day 0 -> 0");
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
#ifndef SOST_TESTNET_FORKS
    // V15 final-decentralization fork RETIRES PoPC on mainnet: the PoPC V15
    // subsystem never auto-activates (popc_v15_active_at == false at every
    // height). This suite exercises the live subsystem only on the testnet
    // profile; on mainnet it verifies the retirement invariant and exits green.
    // See docs/V15_FINAL_DECENTRALIZATION_SPEC.md.
    if (sost::popc_single_model_active(sost::V15_HEIGHT) ||
        sost::popc_single_model_active(sost::V15_HEIGHT + 100000)) {
        std::cout << "FAIL: single-model must be inactive (retired) on mainnet under the V15 fork" << std::endl;
        return 1;
    }
    std::cout << "[mainnet] PoPC single-model retired by the V15 fork - subsystem is testnet-only. OK" << std::endl;
    return 0;
#endif
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
