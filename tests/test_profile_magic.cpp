// =============================================================================
// test_profile_magic.cpp — regression for the testnet submitblock profile bug.
//
// Bug: block validation called get_consensus_params(Profile::MAINNET, height),
// which (a) returned MAINNET CX params and (b) reset the global ACTIVE_PROFILE to
// MAINNET. MAGIC_STR_BYTES() derives the magic from ACTIVE_PROFILE, so every
// testnet block past the fast-sync height was recomputed with MAINNET magic and
// rejected as a block_id mismatch. Fix: derive params from the node's RUNTIME
// profile (ACTIVE_PROFILE). On mainnet this is byte-identical.
// =============================================================================

#include "sost/params.h"
#include "sost/emission.h"   // get_consensus_params

#include <cstring>
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
    static std::vector<std::pair<std::string, void(*)()>> t; return t;
}
#define EXPECT(cond, msg) do { \
    if (!(cond)) { std::cerr << "  EXPECT failed: " << msg << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; } } while(0)

TEST(PM01_magic_differs_by_profile) {
    ACTIVE_PROFILE = Profile::MAINNET;
    uint8_t main_magic[MAGIC_LEN]; std::memcpy(main_magic, MAGIC_STR_BYTES(), MAGIC_LEN);
    ACTIVE_PROFILE = Profile::TESTNET;
    EXPECT(std::memcmp(main_magic, MAGIC_STR_BYTES(), MAGIC_LEN) != 0,
           "testnet and mainnet magic must differ (otherwise the bug is invisible)");
}

TEST(PM02_get_consensus_params_sets_active_profile) {
    get_consensus_params(Profile::TESTNET, 1);
    EXPECT(ACTIVE_PROFILE == Profile::TESTNET, "get_consensus_params(TESTNET) must set ACTIVE_PROFILE=TESTNET");
    get_consensus_params(Profile::MAINNET, 1);
    EXPECT(ACTIVE_PROFILE == Profile::MAINNET, "get_consensus_params(MAINNET) must set ACTIVE_PROFILE=MAINNET");
}

TEST(PM03_validation_uses_runtime_profile_keeps_magic_stable) {
    // Node runtime profile = TESTNET (set at startup).
    ACTIVE_PROFILE = Profile::TESTNET;
    uint8_t before[MAGIC_LEN]; std::memcpy(before, MAGIC_STR_BYTES(), MAGIC_LEN);
    // FIXED call site: derive params from the runtime profile — magic must NOT change.
    get_consensus_params(ACTIVE_PROFILE, 2);
    EXPECT(std::memcmp(before, MAGIC_STR_BYTES(), MAGIC_LEN) == 0,
           "runtime-profile params keep testnet magic stable (regression: was flipped to MAINNET)");
    EXPECT(ACTIVE_PROFILE == Profile::TESTNET, "ACTIVE_PROFILE must remain TESTNET after runtime-profile params");
}

TEST(PM04_hardcoded_mainnet_would_flip_profile) {
    // Documents the bug: a hardcoded MAINNET call flips the runtime profile.
    ACTIVE_PROFILE = Profile::TESTNET;
    get_consensus_params(Profile::MAINNET, 2);   // the OLD (buggy) call
    EXPECT(ACTIVE_PROFILE == Profile::MAINNET, "hardcoded MAINNET flips ACTIVE_PROFILE — that was the bug");
    ACTIVE_PROFILE = Profile::TESTNET;           // restore for any later tests
}

int main() {
    std::cout << "=== Profile/Magic regression (testnet submitblock) Tests ===" << std::endl;
    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev = g_fail; fn();
        if (g_fail == prev) { g_pass++; std::cout << "PASS" << std::endl; }
        else std::cout << "*** FAIL ***" << std::endl;
    }
    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail
              << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;
    return g_fail > 0 ? 1 : 0;
}
