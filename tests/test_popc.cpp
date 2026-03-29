// =============================================================================
// test_popc.cpp — Tests for PoPC (Proof of Personal Custody) Model A
// =============================================================================
//
// Tests cover:
//   Bond sizing (POPC01-03), Reward calculation (POPC04-09),
//   Reputation constants (POPC10-12), Registry CRUD (POPC13-22),
//   Reputation tracking (POPC23-25), Audit entropy (POPC26-28),
//   Persistence (POPC29), Reward amount math (POPC30-31)
// =============================================================================

#include "sost/popc.h"
#include "sost/transaction.h"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

using namespace sost;

// =============================================================================
// Test infrastructure (same pattern as test_bond_lock.cpp)
// =============================================================================

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
// Helper: build a valid PoPCCommitment
// =============================================================================

static sost::PoPCCommitment MakeTestCommitment(uint8_t fill_id = 0x01, uint16_t duration = 3) {
    sost::PoPCCommitment c;
    std::memset(c.commitment_id.data(), fill_id, 32);
    std::memset(c.user_pkh.data(), 0xAA, 20);
    c.eth_wallet = "0xd38955822b88867CD010946F0Ba25680B9DfC7a6";
    c.gold_token = "XAUT";
    c.gold_amount_mg = 31103;  // 1 oz
    c.bond_sost_stocks = 100000000;  // 1 SOST
    c.duration_months = duration;
    c.start_height = 5000;
    // end_height: approximate blocks per month = 4320 (30d * 24h * 6 blocks/h)
    c.end_height = 5000 + (duration == 1  ? 4320  :
                           duration == 3  ? 12960 :
                           duration == 6  ? 25920 :
                           duration == 9  ? 38880 : 51840);
    c.bond_pct_bps = 1200;
    c.reward_pct_bps = sost::compute_reward_pct(duration);
    c.status = sost::PoPCStatus::ACTIVE;
    c.sost_price_usd_micro = 100000;      // $0.10
    c.gold_price_usd_micro = 2000000000;  // $2000/oz
    return c;
}

// =============================================================================
// Bond sizing tests
// =============================================================================

// POPC01: low sost/gold ratio → high bond percentage (25%)
TEST(POPC01_bond_pct_low_ratio) {
    // ratio_bps=50: sost is cheap vs gold → bond must be larger to cover risk
    uint16_t bps = compute_bond_pct(50);
    EXPECT(bps == 2500, "expected 2500 bps for ratio_bps=50, got " + std::to_string(bps));
}

// POPC02: mid ratio → moderate bond percentage (15%)
TEST(POPC02_bond_pct_mid_ratio) {
    uint16_t bps = compute_bond_pct(750);
    EXPECT(bps == 1500, "expected 1500 bps for ratio_bps=750, got " + std::to_string(bps));
}

// POPC03: high ratio → minimum bond percentage (10%)
TEST(POPC03_bond_pct_high_ratio) {
    // ratio_bps=10000: sost is expensive vs gold → minimum bond required
    uint16_t bps = compute_bond_pct(10000);
    EXPECT(bps == 1000, "expected 1000 bps for ratio_bps=10000, got " + std::to_string(bps));
}

// =============================================================================
// Reward calculation tests
// =============================================================================

// POPC04: 1-month commitment → 1% reward (100 bps)
TEST(POPC04_reward_1_month) {
    uint16_t bps = compute_reward_pct(1);
    EXPECT(bps == 100, "expected 100 bps for 1 month, got " + std::to_string(bps));
}

// POPC05: 3-month commitment → 4% reward (400 bps)
TEST(POPC05_reward_3_months) {
    uint16_t bps = compute_reward_pct(3);
    EXPECT(bps == 400, "expected 400 bps for 3 months, got " + std::to_string(bps));
}

// POPC06: 6-month commitment → 9% reward (900 bps)
TEST(POPC06_reward_6_months) {
    uint16_t bps = compute_reward_pct(6);
    EXPECT(bps == 900, "expected 900 bps for 6 months, got " + std::to_string(bps));
}

// POPC07: 9-month commitment → 15% reward (1500 bps)
TEST(POPC07_reward_9_months) {
    uint16_t bps = compute_reward_pct(9);
    EXPECT(bps == 1500, "expected 1500 bps for 9 months, got " + std::to_string(bps));
}

// POPC08: 12-month commitment → 22% reward (2200 bps)
TEST(POPC08_reward_12_months) {
    uint16_t bps = compute_reward_pct(12);
    EXPECT(bps == 2200, "expected 2200 bps for 12 months, got " + std::to_string(bps));
}

// POPC09: invalid duration (7 months) → 0 (not a valid commitment tier)
TEST(POPC09_reward_invalid) {
    uint16_t bps = compute_reward_pct(7);
    EXPECT(bps == 0, "expected 0 bps for duration=7 (invalid), got " + std::to_string(bps));
}

// =============================================================================
// Reputation constant tests
// =============================================================================

// POPC10: new user (stars=0) → max gold = 0.5 oz = 15552 mg
TEST(POPC10_max_gold_new) {
    int64_t mg = max_gold_for_reputation(POPC_STARS_NEW);
    EXPECT(mg == POPC_MAX_MG_NEW,
           "expected " + std::to_string(POPC_MAX_MG_NEW) + " mg for stars=0, got " + std::to_string(mg));
}

// POPC11: veteran user (stars=5) → max gold = 10 oz = 311035 mg
TEST(POPC11_max_gold_veteran) {
    int64_t mg = max_gold_for_reputation(POPC_STARS_VETERAN);
    EXPECT(mg == POPC_MAX_MG_VETERAN,
           "expected " + std::to_string(POPC_MAX_MG_VETERAN) + " mg for stars=5, got " + std::to_string(mg));
}

// POPC12: new user (stars=0) → audit probability = 300 per mille (30%)
TEST(POPC12_audit_prob_new) {
    uint16_t prob = audit_probability(POPC_STARS_NEW);
    EXPECT(prob == POPC_AUDIT_PROB_NEW,
           "expected " + std::to_string(POPC_AUDIT_PROB_NEW) + " permille for stars=0, got " + std::to_string(prob));
}

// =============================================================================
// Registry tests
// =============================================================================

// POPC13: register a valid commitment and verify find() returns it
TEST(POPC13_register_valid) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x01, 3);
    std::string err;
    bool ok = reg.register_commitment(c, &err);
    EXPECT(ok, "register_commitment failed: " + err);

    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "find() returned nullptr after successful registration");
    EXPECT(found->duration_months == 3, "duration_months mismatch");
    EXPECT(found->bond_sost_stocks == 100000000, "bond_sost_stocks mismatch");
    EXPECT(found->gold_token == "XAUT", "gold_token mismatch");
    EXPECT(found->status == PoPCStatus::ACTIVE, "status should be ACTIVE");
}

// POPC14: register with invalid duration (7 months) → rejected
TEST(POPC14_register_bad_duration) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x02, 7);  // 7 is not a valid duration
    std::string err;
    bool ok = reg.register_commitment(c, &err);
    EXPECT(!ok, "register_commitment should have rejected duration=7");
    EXPECT(!err.empty(), "error message should be non-empty on rejection");
}

// POPC15: register with unsupported gold token → rejected
TEST(POPC15_register_bad_token) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x03, 3);
    c.gold_token = "BTC";  // not XAUT or PAXG
    std::string err;
    bool ok = reg.register_commitment(c, &err);
    EXPECT(!ok, "register_commitment should have rejected gold_token=BTC");
    EXPECT(!err.empty(), "error message should be non-empty on rejection");
}

// POPC16: register with zero bond → rejected
TEST(POPC16_register_zero_bond) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x04, 3);
    c.bond_sost_stocks = 0;
    std::string err;
    bool ok = reg.register_commitment(c, &err);
    EXPECT(!ok, "register_commitment should have rejected bond_sost_stocks=0");
    EXPECT(!err.empty(), "error message should be non-empty on rejection");
}

// POPC17: register same commitment_id twice → second attempt rejected
TEST(POPC17_register_duplicate) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x05, 3);
    std::string err;
    bool ok1 = reg.register_commitment(c, &err);
    EXPECT(ok1, "first registration should succeed: " + err);

    // Second registration with same commitment_id
    err.clear();
    bool ok2 = reg.register_commitment(c, &err);
    EXPECT(!ok2, "duplicate registration should be rejected");
    EXPECT(!err.empty(), "error message should be non-empty on duplicate");
}

// POPC18: register 3 commitments → list_active returns all 3
TEST(POPC18_list_active) {
    PoPCRegistry reg;
    for (uint8_t i = 0x10; i < 0x13; ++i) {
        auto c = MakeTestCommitment(i, 3);
        std::string err;
        bool ok = reg.register_commitment(c, &err);
        EXPECT(ok, "registration failed for fill=" + std::to_string(i) + ": " + err);
    }
    auto active = reg.list_active();
    EXPECT(active.size() == 3, "expected 3 active commitments, got " + std::to_string(active.size()));
}

// POPC19: register then complete → status becomes COMPLETED
TEST(POPC19_complete) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x20, 3);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "registration failed: " + err);

    err.clear();
    bool ok = reg.complete(c.commitment_id, &err);
    EXPECT(ok, "complete() failed: " + err);

    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after complete()");
    EXPECT(found->status == PoPCStatus::COMPLETED, "status should be COMPLETED");
}

// POPC20: complete a non-existent commitment_id → returns false with error
TEST(POPC20_complete_not_found) {
    PoPCRegistry reg;
    Hash256 fake_id{};
    std::memset(fake_id.data(), 0xFF, 32);

    std::string err;
    bool ok = reg.complete(fake_id, &err);
    EXPECT(!ok, "complete() on non-existent id should return false");
    EXPECT(!err.empty(), "error message should be non-empty");
}

// POPC21: register then slash → status becomes SLASHED
TEST(POPC21_slash) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x21, 6);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "registration failed: " + err);

    err.clear();
    bool ok = reg.slash(c.commitment_id, "audit_failure", &err);
    EXPECT(ok, "slash() failed: " + err);

    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after slash()");
    EXPECT(found->status == PoPCStatus::SLASHED, "status should be SLASHED");
}

// POPC22: active_count tracks correctly through register/complete/slash
TEST(POPC22_active_count) {
    PoPCRegistry reg;

    // Register 3 commitments
    auto c1 = MakeTestCommitment(0x31, 3);
    auto c2 = MakeTestCommitment(0x32, 6);
    auto c3 = MakeTestCommitment(0x33, 12);
    std::string err;
    EXPECT(reg.register_commitment(c1, &err), "c1 registration failed: " + err);
    EXPECT(reg.register_commitment(c2, &err), "c2 registration failed: " + err);
    EXPECT(reg.register_commitment(c3, &err), "c3 registration failed: " + err);
    EXPECT(reg.active_count() == 3, "expected 3 active, got " + std::to_string(reg.active_count()));

    // Complete c1 → active_count should drop to 2
    EXPECT(reg.complete(c1.commitment_id, &err), "complete c1 failed: " + err);
    EXPECT(reg.active_count() == 2, "expected 2 active after complete, got " + std::to_string(reg.active_count()));

    // Slash c2 → active_count should drop to 1
    EXPECT(reg.slash(c2.commitment_id, "test_slash", &err), "slash c2 failed: " + err);
    EXPECT(reg.active_count() == 1, "expected 1 active after slash, got " + std::to_string(reg.active_count()));
}

// =============================================================================
// Reputation tracking tests
// =============================================================================

// POPC23: new user has stars=0 by default
TEST(POPC23_reputation_default) {
    PoPCRegistry reg;
    PubKeyHash pkh{};
    std::memset(pkh.data(), 0xBB, 20);

    PoPCReputation rep = reg.get_reputation(pkh);
    EXPECT(rep.stars == 0, "new user should have stars=0, got " + std::to_string(rep.stars));
    EXPECT(rep.contracts_completed == 0, "new user should have 0 completed");
    EXPECT(rep.contracts_slashed == 0, "new user should have 0 slashed");
    EXPECT(!rep.blacklisted, "new user should not be blacklisted");
}

// POPC24: completing 1 contract — stars stay at 0 (need multiple completions to upgrade)
TEST(POPC24_reputation_after_complete) {
    PoPCRegistry reg;
    auto c = MakeTestCommitment(0x40, 3);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "registration failed: " + err);
    EXPECT(reg.complete(c.commitment_id, &err), "complete failed: " + err);

    PoPCReputation rep = reg.get_reputation(c.user_pkh);
    // stars=0 still — reputation upgrade requires more than 1 completion
    EXPECT(rep.stars == 0, "stars should still be 0 after 1 completion, got " + std::to_string(rep.stars));
    EXPECT(rep.contracts_completed >= 1, "contracts_completed should be >= 1");
}

// POPC25: update_reputation directly — verify success/failure counters increment
TEST(POPC25_reputation_update) {
    PoPCRegistry reg;
    PubKeyHash pkh{};
    std::memset(pkh.data(), 0xCC, 20);

    // Start: both counters at 0
    PoPCReputation rep0 = reg.get_reputation(pkh);
    EXPECT(rep0.contracts_completed == 0, "initial completed should be 0");
    EXPECT(rep0.contracts_slashed == 0, "initial slashed should be 0");

    // Record 2 successes
    reg.update_reputation(pkh, true);
    reg.update_reputation(pkh, true);
    PoPCReputation rep1 = reg.get_reputation(pkh);
    EXPECT(rep1.contracts_completed == 2,
           "expected 2 completed, got " + std::to_string(rep1.contracts_completed));
    EXPECT(rep1.contracts_slashed == 0, "slashed count should still be 0");

    // Record 1 failure
    reg.update_reputation(pkh, false);
    PoPCReputation rep2 = reg.get_reputation(pkh);
    EXPECT(rep2.contracts_completed == 2, "completed should remain 2");
    EXPECT(rep2.contracts_slashed == 1,
           "expected 1 slashed, got " + std::to_string(rep2.contracts_slashed));
}

// =============================================================================
// Audit entropy tests
// =============================================================================

// POPC26: compute_audit_seed is deterministic — same inputs → same seed
TEST(POPC26_audit_seed_deterministic) {
    Hash256 block_id{};   std::memset(block_id.data(), 0xAA, 32);
    Hash256 commit{};     std::memset(commit.data(), 0xBB, 32);
    Hash256 ckpts{};      std::memset(ckpts.data(), 0xCC, 32);

    Hash256 seed1 = compute_audit_seed(block_id, commit, ckpts);
    Hash256 seed2 = compute_audit_seed(block_id, commit, ckpts);

    EXPECT(seed1 == seed2, "same inputs must produce same audit seed");
}

// POPC27: compute_audit_seed with different inputs → different seeds
TEST(POPC27_audit_seed_different) {
    Hash256 block_id_a{}; std::memset(block_id_a.data(), 0xAA, 32);
    Hash256 block_id_b{}; std::memset(block_id_b.data(), 0xDD, 32);  // different
    Hash256 commit{};     std::memset(commit.data(), 0xBB, 32);
    Hash256 ckpts{};      std::memset(ckpts.data(), 0xCC, 32);

    Hash256 seed_a = compute_audit_seed(block_id_a, commit, ckpts);
    Hash256 seed_b = compute_audit_seed(block_id_b, commit, ckpts);

    EXPECT(seed_a != seed_b, "different block_ids must produce different audit seeds");
}

// POPC28: is_audit_triggered returns true when prob=1000 (100%) and false when prob=0 (0%)
TEST(POPC28_audit_triggered) {
    Hash256 audit_seed{}; std::memset(audit_seed.data(), 0x77, 32);
    Hash256 commit_id{};  std::memset(commit_id.data(), 0x88, 32);

    // prob = 1000 per mille = 100% → always triggered
    bool always = is_audit_triggered(audit_seed, commit_id, 0, 1000);
    EXPECT(always, "audit should always trigger at prob=1000 permille");

    // prob = 0 per mille = 0% → never triggered
    bool never = is_audit_triggered(audit_seed, commit_id, 0, 0);
    EXPECT(!never, "audit should never trigger at prob=0 permille");
}

// =============================================================================
// Save/Load (persistence) tests
// =============================================================================

// POPC29: register commitments, save to temp file, load into new registry, verify data
TEST(POPC29_save_load) {
    const char* tmp_path = "/tmp/test_popc_registry.bin";

    // Build and populate registry
    PoPCRegistry reg;
    auto c1 = MakeTestCommitment(0x50, 3);
    auto c2 = MakeTestCommitment(0x51, 6);
    auto c3 = MakeTestCommitment(0x52, 12);
    std::string err;
    EXPECT(reg.register_commitment(c1, &err), "c1 registration failed: " + err);
    EXPECT(reg.register_commitment(c2, &err), "c2 registration failed: " + err);
    EXPECT(reg.register_commitment(c3, &err), "c3 registration failed: " + err);
    EXPECT(reg.complete(c1.commitment_id, &err), "complete c1 failed: " + err);

    // Save
    err.clear();
    bool saved = reg.save(tmp_path, &err);
    EXPECT(saved, "save() failed: " + err);

    // Load into fresh registry
    PoPCRegistry reg2;
    err.clear();
    bool loaded = reg2.load(tmp_path, &err);
    EXPECT(loaded, "load() failed: " + err);

    // Verify counts and data integrity
    EXPECT(reg2.active_count() == reg.active_count(),
           "active_count mismatch after load: expected " + std::to_string(reg.active_count()) +
           " got " + std::to_string(reg2.active_count()));

    const PoPCCommitment* found1 = reg2.find(c1.commitment_id);
    EXPECT(found1 != nullptr, "c1 not found after load");
    EXPECT(found1->status == PoPCStatus::COMPLETED, "c1 status should be COMPLETED after load");
    EXPECT(found1->duration_months == 3, "c1 duration_months mismatch after load");

    const PoPCCommitment* found2 = reg2.find(c2.commitment_id);
    EXPECT(found2 != nullptr, "c2 not found after load");
    EXPECT(found2->status == PoPCStatus::ACTIVE, "c2 status should be ACTIVE after load");
    EXPECT(found2->duration_months == 6, "c2 duration_months mismatch after load");

    const PoPCCommitment* found3 = reg2.find(c3.commitment_id);
    EXPECT(found3 != nullptr, "c3 not found after load");
    EXPECT(found3->bond_sost_stocks == 100000000, "c3 bond_sost_stocks mismatch after load");
    EXPECT(found3->gold_token == "XAUT", "c3 gold_token mismatch after load");

    // Clean up
    std::remove(tmp_path);
}

// =============================================================================
// Reward amount calculation tests
// =============================================================================

// POPC30: bond=1 SOST, duration=12 → reward = 22% of bond = 0.22 SOST = 22000000 stocks
TEST(POPC30_reward_amount) {
    const int64_t bond_stocks = 100000000;  // 1 SOST
    const uint16_t reward_bps = compute_reward_pct(12);  // should be 2200 bps = 22%

    EXPECT(reward_bps == 2200,
           "reward_pct for 12 months should be 2200 bps, got " + std::to_string(reward_bps));

    // Compute reward amount using integer arithmetic: bond * bps / 10000
    int64_t reward_stocks = (bond_stocks * (int64_t)reward_bps) / 10000;
    const int64_t expected_reward = 22000000;  // 0.22 SOST
    EXPECT(reward_stocks == expected_reward,
           "expected reward " + std::to_string(expected_reward) +
           " stocks, got " + std::to_string(reward_stocks));
}

// POPC31: reward after 5% protocol fee deduction
TEST(POPC31_reward_with_fee) {
    const int64_t bond_stocks = 100000000;  // 1 SOST
    const uint16_t reward_bps = compute_reward_pct(12);  // 2200 bps
    EXPECT(reward_bps == 2200, "reward_pct for 12 months should be 2200 bps");

    // Gross reward = bond * reward_bps / 10000
    int64_t gross_reward = (bond_stocks * (int64_t)reward_bps) / 10000;
    // Net reward = gross_reward * (10000 - fee_bps) / 10000
    int64_t net_reward = (gross_reward * (int64_t)(10000 - POPC_PROTOCOL_FEE_BPS)) / 10000;
    // Expected: 22000000 * (10000 - 500) / 10000 = 22000000 * 9500 / 10000 = 20900000
    const int64_t expected_net = 20900000;
    EXPECT(net_reward == expected_net,
           "expected net reward " + std::to_string(expected_net) +
           " stocks after 5% fee, got " + std::to_string(net_reward));

    // Protocol fee itself should be 5% of gross
    int64_t fee_amount = gross_reward - net_reward;
    const int64_t expected_fee = 1100000;  // 5% of 22000000
    EXPECT(fee_amount == expected_fee,
           "expected fee " + std::to_string(expected_fee) +
           " stocks, got " + std::to_string(fee_amount));

    // Verify POPC_PROTOCOL_FEE_BPS constant matches specification (500 = 5%)
    EXPECT(POPC_PROTOCOL_FEE_BPS == 500,
           "POPC_PROTOCOL_FEE_BPS should be 500, got " + std::to_string(POPC_PROTOCOL_FEE_BPS));
}

// =============================================================================
// main
// =============================================================================

int main() {
    std::cout << "=== PoPC (Proof of Personal Custody) Tests ===" << std::endl;

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
