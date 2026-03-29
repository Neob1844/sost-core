// =============================================================================
// test_proposals.cpp — Tests for Version Signaling and Soft Fork Governance
// =============================================================================
//
// Tests cover:
//   Bit detection (SIG01-02), Signal counting (SIG03-05),
//   Activation threshold (SIG06-10), Veto lifetime (SIG11-13),
//   Proposal registry (SIG14), Small window edge case (SIG15)
// =============================================================================

#include "sost/proposals.h"
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
// Helper: build a vector of block versions
// =============================================================================

// Creates [total] versions: [signaled] of them have bit set, rest are plain 1.
static std::vector<uint32_t> make_versions(int total, int signaled, uint8_t bit) {
    std::vector<uint32_t> v;
    uint32_t sig_version = 1 | (1u << bit);
    for (int i = 0; i < total; ++i) {
        if (i < signaled) v.push_back(sig_version);
        else v.push_back(1);
    }
    return v;
}

// =============================================================================
// Bit detection tests
// =============================================================================

// SIG01: version=0x00000100 (bit 8 set) → version_has_signal returns true for bit 8
TEST(SIG01_version_has_signal_bit8) {
    uint32_t version = 0x00000100u; // bit 8 set
    bool result = version_has_signal(version, 8);
    EXPECT(result, "version 0x100 should signal bit 8");
}

// SIG02: version=1 (only bit 0 set) → version_has_signal returns false for bit 8
TEST(SIG02_version_no_signal) {
    uint32_t version = 1u;
    bool result = version_has_signal(version, 8);
    EXPECT(!result, "version 1 should not signal bit 8");
}

// =============================================================================
// Signal counting tests
// =============================================================================

// SIG03: 288 blocks all with bit 8 set → count = 288
TEST(SIG03_count_signals_all) {
    auto versions = make_versions(288, 288, 8);
    int32_t count = count_version_signals(versions, 8);
    EXPECT(count == 288, "expected count=288 when all blocks signal, got " + std::to_string(count));
}

// SIG04: 288 blocks all version=1 → count = 0
TEST(SIG04_count_signals_none) {
    auto versions = make_versions(288, 0, 8);
    int32_t count = count_version_signals(versions, 8);
    EXPECT(count == 0, "expected count=0 when no blocks signal, got " + std::to_string(count));
}

// SIG05: 288 blocks, 200 with bit 8 → count = 200
TEST(SIG05_count_signals_partial) {
    auto versions = make_versions(288, 200, 8);
    int32_t count = count_version_signals(versions, 8);
    EXPECT(count == 200, "expected count=200, got " + std::to_string(count));
}

// =============================================================================
// Activation threshold tests
// =============================================================================

// SIG06: 216/288 (75%) signal bit 8 → check_activation returns true
// Threshold formula: (288 * 75) / 100 = 216 (integer division)
TEST(SIG06_activation_at_75pct) {
    auto versions = make_versions(288, 216, 8);
    bool activated = check_activation(versions, 8, /*foundation_support=*/false, /*foundation_veto=*/false);
    EXPECT(activated, "216/288 (75%) should activate (threshold is exactly 216)");
}

// SIG07: 215/288 (74.65%) → check_activation returns false
// 215 < 216 threshold
TEST(SIG07_no_activation_at_74pct) {
    auto versions = make_versions(288, 215, 8);
    bool activated = check_activation(versions, 8, /*foundation_support=*/false, /*foundation_veto=*/false);
    EXPECT(!activated, "215/288 (74.65%) should NOT activate (below threshold 216)");
}

// SIG08: 250/288 (86.8%) + foundation_veto=true → returns false regardless of count
TEST(SIG08_foundation_veto) {
    auto versions = make_versions(288, 250, 8);
    bool activated = check_activation(versions, 8, /*foundation_support=*/false, /*foundation_veto=*/true);
    EXPECT(!activated, "foundation veto must block activation even at 86.8% signaling");
}

// SIG09: 200/288 (69.4%) + foundation_support=true → effective 200+29=229 >= 216 → true
TEST(SIG09_foundation_support) {
    auto versions = make_versions(288, 200, 8);
    bool activated = check_activation(versions, 8, /*foundation_support=*/true, /*foundation_veto=*/false);
    // 200 + FOUNDATION_WEIGHT_BLOCKS(29) = 229 >= threshold(216) → true
    EXPECT(activated, "200 miner votes + 29 foundation bonus = 229 >= 216, should activate");
}

// SIG10: 180/288 (62.5%) + foundation_support=true → 180+29=209 < 216 → false
TEST(SIG10_foundation_support_not_enough) {
    auto versions = make_versions(288, 180, 8);
    bool activated = check_activation(versions, 8, /*foundation_support=*/true, /*foundation_veto=*/false);
    // 180 + 29 = 209 < 216 → false
    EXPECT(!activated, "180 + 29 foundation bonus = 209 < 216, should NOT activate");
}

// =============================================================================
// Foundation veto lifetime tests
// =============================================================================

// SIG11: height=1000, miners=1 → veto is active (early network, few miners)
TEST(SIG11_veto_active_early) {
    bool active = foundation_veto_active(1000, 1);
    EXPECT(active, "veto should be active at height=1000 with only 1 independent miner");
}

// SIG12: height=105120 → veto expired by height regardless of miners
TEST(SIG12_veto_expired_by_height) {
    bool active = foundation_veto_active(105120, 1);
    EXPECT(!active, "veto should expire at height >= 105120 (FOUNDATION_VETO_EXPIRY_BLOCKS)");
}

// SIG13: height=1000, miners=10 → veto expired by miner count
TEST(SIG13_veto_expired_by_miners) {
    bool active = foundation_veto_active(1000, 10);
    EXPECT(!active, "veto should expire when 10+ independent miners are active");
}

// =============================================================================
// Proposal registry test
// =============================================================================

// SIG14: get_proposals() returns at least 1 defined proposal
TEST(SIG14_get_proposals) {
    auto proposals = get_proposals();
    EXPECT(!proposals.empty(), "get_proposals() must return at least one proposal");
    // Verify the post-quantum proposal is present (it uses bit 8)
    bool found_bit8 = false;
    for (const auto& p : proposals) {
        if (p.bit == 8) { found_bit8 = true; break; }
    }
    EXPECT(found_bit8, "proposal with bit=8 (post-quantum) should be in the proposal list");
}

// =============================================================================
// Small window edge case
// =============================================================================

// SIG15: only 50 blocks available → count_version_signals uses the full 50-block slice
// (not truncated to a sub-window; the function uses all provided entries when < SIGNALING_WINDOW)
TEST(SIG15_small_window) {
    // 50 blocks total, 40 signaling bit 8
    auto versions = make_versions(50, 40, 8);
    int32_t count = count_version_signals(versions, 8);
    EXPECT(count == 40, "with 50 total blocks (40 signaling), count should be 40, got " + std::to_string(count));

    // check_activation with 50 blocks: window=min(50,288)=50, threshold=(50*75)/100=37
    // 40 >= 37 → should activate
    bool activated = check_activation(versions, 8, false, false);
    EXPECT(activated, "40/50 blocks signaling meets the 75% threshold on a 50-block window");
}

// =============================================================================
// main
// =============================================================================

int main() {
    std::cout << "=== Version Signaling Tests ===" << std::endl;
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
