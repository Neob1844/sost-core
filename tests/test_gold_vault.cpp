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
// GV3: Large spend with 75% approval → approved (Epoch 0-1)
// =============================================================================
TEST(GV06_large_spend_75_approved) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 76;
    token.threshold_required = 75;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "76% signaling should approve at 75% threshold");
}

// =============================================================================
// GV3: Large spend with 74% → rejected (Epoch 0-1)
// =============================================================================
TEST(GV07_large_spend_74_rejected) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 74;
    token.threshold_required = 75;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "74% signaling should be rejected at 75% threshold");
}

// =============================================================================
// GV3: Foundation support 65% + 10% = 75% → approved (Epoch 0-1)
// =============================================================================
TEST(GV08_foundation_support_65_plus_10) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 65;
    token.threshold_required = 75;
    token.foundation_supported = true;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "65% + 10% foundation = 75% should approve");
}

// =============================================================================
// GV3: Foundation support 64% + 10% = 74% → rejected
// =============================================================================
TEST(GV09_foundation_support_64_plus_10) {
    GVMonthlyTracker tracker;
    tracker.reset(10000);
    GVApprovalToken token{};
    token.signal_pct = 64;
    token.threshold_required = 75;
    token.foundation_supported = true;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 11000);
    EXPECT(result == GVSpendType::REJECTED, "64% + 10% = 74% should be rejected");
}

// =============================================================================
// Epoch 2: needs 95%, no foundation bonus
// =============================================================================
TEST(GV10_epoch2_needs_95) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 94;
    token.threshold_required = 95;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REJECTED, "94% should be rejected at 95% threshold (Epoch 2)");
}

TEST(GV11_epoch2_95_approved) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 96;
    token.threshold_required = 95;
    token.foundation_supported = false;
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REQUIRES_APPROVAL, "96% should approve at 95% threshold (Epoch 2)");
}

// =============================================================================
// Epoch 2: foundation support has NO effect
// =============================================================================
TEST(GV12_epoch2_no_foundation_bonus) {
    GVMonthlyTracker tracker;
    tracker.reset(263000);
    GVApprovalToken token{};
    token.signal_pct = 86;
    token.threshold_required = 95;
    token.foundation_supported = true; // should be IGNORED in Epoch 2
    auto result = classify_gv_spend(VAULT_BAL, LARGE_SPEND, false, &token, tracker, 263200);
    EXPECT(result == GVSpendType::REJECTED, "Foundation bonus should not apply in Epoch 2 (86% < 95%)");
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
TEST(GV15_proposal_passes_75) {
    EXPECT(gv_proposal_passes(216, 288, false, 11000) == true, "216/288 = 75% should pass");
    EXPECT(gv_proposal_passes(215, 288, false, 11000) == false, "215/288 = 74.6% should fail");
}

TEST(GV16_proposal_foundation_support) {
    // 188/288 = 65.3% + 10% = 75.3% → pass
    EXPECT(gv_proposal_passes(188, 288, true, 11000) == true, "65.3% + 10% foundation should pass");
    // 187/288 = 64.9% + 10% = 74.9% → fail
    EXPECT(gv_proposal_passes(187, 288, true, 11000) == false, "64.9% + 10% should fail");
}

TEST(GV17_proposal_epoch2_no_bonus) {
    // 274/288 = 95.1% → pass even without bonus
    EXPECT(gv_proposal_passes(274, 288, false, 263200) == true, "95.1% should pass at Epoch 2");
    // 273/288 = 94.8% → fail
    EXPECT(gv_proposal_passes(273, 288, false, 263200) == false, "94.8% should fail at Epoch 2");
    // With foundation support: 273/288 = 94.8% + 10% = 104.8%... but in Epoch 2 bonus doesn't apply
    EXPECT(gv_proposal_passes(273, 288, true, 263200) == false, "Foundation bonus should not apply in Epoch 2");
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
