// =============================================================================
// test_escrow.cpp — Tests for PoPC Model B (Escrow-Based)
// =============================================================================
//
// Tests cover:
//   Registration validation (ESC01-05), List (ESC06),
//   Lifecycle (ESC07-09), Reward calculation (ESC10),
//   Persistence (ESC11)
// =============================================================================

#include "sost/popc_model_b.h"
#include "sost/popc.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <vector>
#include <string>
#include <cstdio>

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
// Helper: build a valid EscrowCommitment
// =============================================================================

static EscrowCommitment MakeTestEscrow(uint8_t fill = 0x01, uint16_t duration = 6) {
    EscrowCommitment e;
    std::memset(e.escrow_id.data(), fill, 32);
    std::memset(e.user_pkh.data(), 0xBB, 20);
    e.eth_escrow_address = "0x1234567890abcdef1234567890abcdef12345678";
    e.gold_token = "XAUT";
    e.gold_amount_mg = 31103; // 1 oz
    e.reward_stocks = calculate_escrow_reward(100000000, duration); // reward on 1 SOST equivalent
    e.duration_months = duration;
    e.start_height = 5000;
    e.end_height = 5000 + (duration == 1 ? 4320 : duration == 3 ? 12960 : duration == 6 ? 25920 : duration == 9 ? 38880 : 51840);
    e.status = EscrowStatus::ACTIVE;
    return e;
}

// =============================================================================
// ESC01: Register a valid escrow — find() must return it
// =============================================================================
TEST(ESC01_register_valid) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x01, 6);
    std::string err;
    EXPECT(reg.register_escrow(e, &err), "register_escrow failed: " + err);

    const EscrowCommitment* found = reg.find(e.escrow_id);
    EXPECT(found != nullptr, "find() returned nullptr after registration");
    EXPECT(found->gold_token == "XAUT", "gold_token not preserved");
    EXPECT(found->duration_months == 6, "duration_months not preserved");
    EXPECT(found->status == EscrowStatus::ACTIVE, "status should be ACTIVE");
}

// =============================================================================
// ESC02: Invalid duration (7 months) → rejected
// =============================================================================
TEST(ESC02_register_bad_duration) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x02, 6);
    e.duration_months = 7; // invalid
    std::string err;
    EXPECT(!reg.register_escrow(e, &err), "should reject duration=7");
    EXPECT(!err.empty(), "error message should not be empty");
}

// =============================================================================
// ESC03: Invalid gold_token ("ETH") → rejected
// =============================================================================
TEST(ESC03_register_bad_token) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x03, 6);
    e.gold_token = "ETH"; // invalid
    std::string err;
    EXPECT(!reg.register_escrow(e, &err), "should reject gold_token=ETH");
    EXPECT(!err.empty(), "error message should not be empty");
}

// =============================================================================
// ESC04: Zero gold amount → rejected
// =============================================================================
TEST(ESC04_register_zero_gold) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x04, 6);
    e.gold_amount_mg = 0; // invalid
    std::string err;
    EXPECT(!reg.register_escrow(e, &err), "should reject gold_amount_mg=0");
    EXPECT(!err.empty(), "error message should not be empty");
}

// =============================================================================
// ESC05: Duplicate escrow_id → rejected
// =============================================================================
TEST(ESC05_register_duplicate) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x05, 6);
    std::string err;
    EXPECT(reg.register_escrow(e, &err), "first registration should succeed: " + err);

    // Same escrow_id
    auto e2 = MakeTestEscrow(0x05, 3); // same fill, different duration
    EXPECT(!reg.register_escrow(e2, &err), "duplicate should be rejected");
    EXPECT(!err.empty(), "error message should not be empty");
}

// =============================================================================
// ESC06: Register 3 escrows, list_active() returns 3
// =============================================================================
TEST(ESC06_list_active) {
    EscrowRegistry reg;
    std::string err;

    auto e1 = MakeTestEscrow(0x11, 1);
    auto e2 = MakeTestEscrow(0x22, 3);
    auto e3 = MakeTestEscrow(0x33, 6);

    EXPECT(reg.register_escrow(e1, &err), "register e1 failed: " + err);
    EXPECT(reg.register_escrow(e2, &err), "register e2 failed: " + err);
    EXPECT(reg.register_escrow(e3, &err), "register e3 failed: " + err);

    auto active = reg.list_active();
    EXPECT(active.size() == 3, "expected 3 active, got " + std::to_string(active.size()));
    EXPECT(reg.active_count() == 3, "active_count() should be 3");
}

// =============================================================================
// ESC07: Register then complete → status becomes COMPLETED
// =============================================================================
TEST(ESC07_complete) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x07, 6);
    std::string err;
    EXPECT(reg.register_escrow(e, &err), "registration failed: " + err);
    EXPECT(reg.complete(e.escrow_id, &err), "complete failed: " + err);

    const EscrowCommitment* found = reg.find(e.escrow_id);
    EXPECT(found != nullptr, "find() returned nullptr after complete");
    EXPECT(found->status == EscrowStatus::COMPLETED, "status should be COMPLETED");

    // Should no longer be in active list
    auto active = reg.list_active();
    EXPECT(active.empty(), "list_active() should be empty after complete");
}

// =============================================================================
// ESC08: Complete a non-existent escrow_id → error
// =============================================================================
TEST(ESC08_complete_not_found) {
    EscrowRegistry reg;
    Hash256 fake_id{};
    std::memset(fake_id.data(), 0xFF, 32);
    std::string err;
    EXPECT(!reg.complete(fake_id, &err), "should fail for unknown escrow_id");
    EXPECT(!err.empty(), "error message should not be empty");
}

// =============================================================================
// ESC09: Register then mark_failed → status becomes FAILED
// =============================================================================
TEST(ESC09_mark_failed) {
    EscrowRegistry reg;
    auto e = MakeTestEscrow(0x09, 3);
    std::string err;
    EXPECT(reg.register_escrow(e, &err), "registration failed: " + err);
    EXPECT(reg.mark_failed(e.escrow_id, "eth escrow contract breach", &err),
           "mark_failed failed: " + err);

    const EscrowCommitment* found = reg.find(e.escrow_id);
    EXPECT(found != nullptr, "find() returned nullptr after mark_failed");
    EXPECT(found->status == EscrowStatus::FAILED, "status should be FAILED");

    // Should no longer be in active list
    EXPECT(reg.active_count() == 0, "active_count() should be 0 after mark_failed");
}

// =============================================================================
// ESC10: Reward calculation for all valid durations
// Rates (from POPC_REWARD_RATES): 1→1%, 3→4%, 6→9%, 9→15%, 12→22%
// =============================================================================
TEST(ESC10_reward_calculation) {
    int64_t base = 100000000; // 1 SOST in stocks

    // Duration 1 month → 1% = 100 bps
    int64_t r1 = calculate_escrow_reward(base, 1);
    EXPECT(r1 == base * 100 / 10000, "1-month reward mismatch, got " + std::to_string(r1));

    // Duration 3 months → 4% = 400 bps
    int64_t r3 = calculate_escrow_reward(base, 3);
    EXPECT(r3 == base * 400 / 10000, "3-month reward mismatch, got " + std::to_string(r3));

    // Duration 6 months → 9% = 900 bps
    int64_t r6 = calculate_escrow_reward(base, 6);
    EXPECT(r6 == base * 900 / 10000, "6-month reward mismatch, got " + std::to_string(r6));

    // Duration 9 months → 15% = 1500 bps
    int64_t r9 = calculate_escrow_reward(base, 9);
    EXPECT(r9 == base * 1500 / 10000, "9-month reward mismatch, got " + std::to_string(r9));

    // Duration 12 months → 22% = 2200 bps
    int64_t r12 = calculate_escrow_reward(base, 12);
    EXPECT(r12 == base * 2200 / 10000, "12-month reward mismatch, got " + std::to_string(r12));

    // Invalid duration → 0
    int64_t r_invalid = calculate_escrow_reward(base, 7);
    EXPECT(r_invalid == 0, "invalid duration should return 0 reward");
}

// =============================================================================
// ESC11: Save to temp file, load into new registry, verify round-trip
// =============================================================================
TEST(ESC11_save_load) {
    EscrowRegistry reg;
    std::string err;

    auto e1 = MakeTestEscrow(0xA1, 3);
    auto e2 = MakeTestEscrow(0xA2, 12);
    EXPECT(reg.register_escrow(e1, &err), "register e1 failed: " + err);
    EXPECT(reg.register_escrow(e2, &err), "register e2 failed: " + err);

    // Complete e1 so we can verify status round-trip
    EXPECT(reg.complete(e1.escrow_id, &err), "complete e1 failed: " + err);

    // Save to temp file
    std::string tmp_path = "/tmp/test_escrow_registry.json";
    EXPECT(reg.save(tmp_path, &err), "save failed: " + err);

    // Load into fresh registry
    EscrowRegistry reg2;
    EXPECT(reg2.load(tmp_path, &err), "load failed: " + err);

    // Verify count
    EXPECT(reg2.active_count() == 1, "loaded registry should have 1 active escrow");

    // Verify e1 (COMPLETED) round-trip
    const EscrowCommitment* found1 = reg2.find(e1.escrow_id);
    EXPECT(found1 != nullptr, "e1 not found after load");
    EXPECT(found1->status == EscrowStatus::COMPLETED, "e1 status should be COMPLETED after load");
    EXPECT(found1->gold_token == "XAUT", "e1 gold_token not preserved");
    EXPECT(found1->duration_months == 3, "e1 duration_months not preserved");

    // Verify e2 (ACTIVE) round-trip
    const EscrowCommitment* found2 = reg2.find(e2.escrow_id);
    EXPECT(found2 != nullptr, "e2 not found after load");
    EXPECT(found2->status == EscrowStatus::ACTIVE, "e2 status should be ACTIVE after load");
    EXPECT(found2->duration_months == 12, "e2 duration_months not preserved");
    EXPECT(found2->gold_amount_mg == 31103, "e2 gold_amount_mg not preserved");

    // Cleanup
    std::remove(tmp_path.c_str());
}

// =============================================================================
// main
// =============================================================================

int main() {
    std::cout << "=== PoPC Model B (Escrow) Tests ===" << std::endl;
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
