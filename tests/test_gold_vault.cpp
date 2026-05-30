// =============================================================================
// test_gold_vault.cpp — Tests for Gold Vault consensus governance (GV1-GV4)
// =============================================================================

#include "sost/gold_vault_governance.h"
#include <cassert>
#include <cstring>
#include <iostream>
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

// Helper constants
static constexpr int64_t VAULT_BAL = 500'000'000'000LL; // 5000 SOST in stocks
static constexpr int64_t SMALL_SPEND = 40'000'000'000LL; // 400 SOST = 8% of vault
static constexpr int64_t LARGE_SPEND = 100'000'000'000LL; // 1000 SOST = 20% of vault

// =============================================================================
// GV1: Before activation — no restrictions
// =============================================================================
TEST(GV01_before_activation) {
    GVMonthlyTracker tracker;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, nullptr, tracker, 4999);
    EXPECT(result != GVSpendType::REJECTED, "Before block 5000, all spends should be allowed");
}

// =============================================================================
// GV1: Gold purchase — no vote needed
// =============================================================================
TEST(GV02_gold_purchase_no_vote) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, true, nullptr, tracker, 11000);
    EXPECT(result == GVSpendType::GOLD_PURCHASE, "Gold purchase should be allowed without vote");
}

// =============================================================================
// GV2: Small spend ≤ 10% monthly — no vote needed
// =============================================================================
TEST(GV03_small_spend_no_vote) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    auto result = classify_gv_spend(VAULT_BAL, SMALL_SPEND, false, nullptr, tracker, 11000);
    EXPECT(result == GVSpendType::OPERATIONAL_SMALL, "Small spend (8%) should be allowed without vote");
}

// =============================================================================
// GV2: Second small spend exceeds monthly 10% → rejected
// =============================================================================
TEST(GV04_small_spend_exceeds_monthly) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    tracker.spent_stocks = 45'000'000'000LL; // already spent 9%
    // Try to spend another 8% → total 17% > 10%
    auto result = classify_gv_spend(VAULT_BAL, SMALL_SPEND, false, nullptr, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "Exceeding 10% monthly should be rejected without approval");
}

// =============================================================================
// GV3: Large spend without approval → rejected
// =============================================================================
TEST(GV05_large_spend_no_approval) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, nullptr, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "Large spend (20%) without approval should be rejected");
}

// =============================================================================
// V14-1: threshold sync 95 → 90. All large-spend boundary cases are
// re-anchored at the new 90 % threshold. Foundation quality vote
// remains +10 % in Epoch 0-1, expires at Epoch 2.
// =============================================================================

// =============================================================================
// GV3: Large spend at 91 % signaling → approved (Epoch 0-1, threshold 90)
// =============================================================================
TEST(GV06_large_spend_above_threshold_approved) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 91;
    token.threshold_required = 90;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "91% signaling should approve at 90% threshold");
}

// =============================================================================
// GV3: Large spend at 89 % signaling → rejected (Epoch 0-1, threshold 90)
// =============================================================================
TEST(GV07_large_spend_below_threshold_rejected) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 89;
    token.threshold_required = 90;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "89% signaling should be rejected at 90% threshold");
}

// =============================================================================
// GV3: Foundation boost lifts 81 % + 10 % = 91 % → approved (Epoch 0-1)
// =============================================================================
TEST(GV08_foundation_boost_lifts_to_pass) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 81;
    token.threshold_required = 90;
    token.foundation_supported = true;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "81% + 10% foundation = 91% should approve at 90% threshold");
}

// =============================================================================
// GV3: Foundation boost insufficient — 79 % + 10 % = 89 % → rejected
// =============================================================================
TEST(GV09_foundation_boost_insufficient) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 79;
    token.threshold_required = 90;
    token.foundation_supported = true;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "79% + 10% = 89% should be rejected at 90% threshold");
}

// =============================================================================
// Epoch 2: still 90 %, no foundation bonus
// =============================================================================
TEST(GV10_epoch2_below_threshold_rejected) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 89;
    token.threshold_required = 90;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REJECTED, "89% should be rejected at 90% threshold (Epoch 2)");
}

TEST(GV11_epoch2_above_threshold_approved) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 91;
    token.threshold_required = 90;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "91% should approve at 90% threshold (Epoch 2)");
}

// =============================================================================
// Epoch 2: foundation support has NO effect — boost expired
// =============================================================================
TEST(GV12_epoch2_no_foundation_bonus) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 81;
    token.threshold_required = 90;
    token.foundation_supported = true; // should be IGNORED in Epoch 2
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REJECTED, "Foundation bonus should not apply in Epoch 2 (81% < 90%)");
}

// =============================================================================
// GV4: Random address without anything → rejected
// =============================================================================
TEST(GV13_random_address_rejected) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    // Large spend, no gold marker, no approval
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, nullptr, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "Random large spend should be rejected");
}

// =============================================================================
// Monthly counter reset after window
// =============================================================================
TEST(GV14_monthly_counter_reset) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    tracker.spent_stocks = 45'000'000'000LL; // 9% already spent in old window
    // 5000 blocks later (> 4320), window has expired → fresh allowance
    auto result = classify_gv_spend(VAULT_BAL, SMALL_SPEND, false, nullptr, tracker, 15000);
    EXPECT(result == GVSpendType::OPERATIONAL_SMALL, "After window expires, fresh allowance should apply");
}

// =============================================================================
// Proposal passing check
// =============================================================================
// =============================================================================
// Proposal passing check — V14-1 boundary at 90 % threshold.
// Integer math: pct = (signal_count * 100) / window_size, then >= threshold.
// 260/288 = 90.27 % → integer 90 → PASS at threshold 90
// 259/288 = 89.93 % → integer 89 → FAIL at threshold 90
// =============================================================================
TEST(GV15_proposal_passes_90pct_boundary) {
    EXPECT(gv_proposal_passes(260, 288, false, 11000) == true, "260/288 = 90.27% should pass");
    EXPECT(gv_proposal_passes(259, 288, false, 11000) == false, "259/288 = 89.93% should fail");
}

TEST(GV16_proposal_foundation_boost_lifts_to_pass) {
    // 231/288 = 80.20 % + 10 % foundation = 90 → PASS at threshold 90
    EXPECT(gv_proposal_passes(231, 288, true, 11000) == true, "80.20% + 10% foundation should pass");
    // 230/288 = 79.86 % + 10 % = 89 → FAIL at threshold 90
    EXPECT(gv_proposal_passes(230, 288, true, 11000) == false, "79.86% + 10% = 89% should fail at 90% threshold");
}

TEST(GV17_proposal_epoch2_no_bonus) {
    // 260/288 = 90.27 % → PASS even without bonus
    EXPECT(gv_proposal_passes(260, 288, false, 263200) == true, "90.27% should pass at Epoch 2");
    // 259/288 = 89.93 % → FAIL
    EXPECT(gv_proposal_passes(259, 288, false, 263200) == false, "89.93% should fail at Epoch 2");
    // Foundation bonus does not apply in Epoch 2 — 259/288 + foundation flag is still 89 % effective
    EXPECT(gv_proposal_passes(259, 288, true, 263200) == false, "Foundation bonus should not apply in Epoch 2");
}

// =============================================================================
// V14-1 compile-time lock-in: the canonical Gold Vault thresholds are
// 90 in both epochs. If a future change touches these constants without
// the corresponding ANN + governance review, this static_assert fires
// at build time and the V14-1 sweep stays in sync with the doc.
// =============================================================================
TEST(GV18_v14_threshold_lockin) {
    static_assert(GV_THRESHOLD_EPOCH01 == 90,
                  "GV_THRESHOLD_EPOCH01 must be 90 (V14-1 canonical). "
                  "If you are intentionally changing this, update "
                  "docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md and the BTCTalk ANN first.");
    static_assert(GV_THRESHOLD_EPOCH2 == 90,
                  "GV_THRESHOLD_EPOCH2 must be 90 (V14-1 canonical). "
                  "If you are intentionally changing this, update "
                  "docs/V13_GOLD_VAULT_GOVERNANCE_GATES.md and the BTCTalk ANN first.");
    EXPECT(GV_THRESHOLD_EPOCH01 == 90, "Epoch 0-1 threshold runtime check");
    EXPECT(GV_THRESHOLD_EPOCH2  == 90, "Epoch 2 threshold runtime check");
    // Foundation boost stays at 10 %.
    EXPECT(GV_FOUNDATION_VOTE_PCT == 10, "Foundation quality vote stays at +10 %");
}

// =============================================================================
// main
// =============================================================================
int main() {
    std::cout << "=== Gold Vault Governance Tests ===" << std::endl;
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
