// =============================================================================
// test_gv_governance_audit.cpp — Gold Vault governance G1-G5 audit assertions.
//
// Proves the rule helpers behave and the mainnet gates stay DEFERRED. Activates
// nothing; moves no funds; signs nothing. Mainnet build: all GV_* gates INT64_MAX.
// =============================================================================
#include "sost/gold_vault_slice1.h"   // G1/G2/G3
#include "sost/gv_g4.h"               // G4 miner signaling
#include "sost/gv_g5.h"               // G5 guardian veto
#include "sost/params.h"
#include "sost/consensus_constants.h" // STOCKS_PER_SOST

#include <climits>
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
#define EXPECT(c, m) do { if(!(c)){ std::cerr<<"  EXPECT failed: "<<m<<"  ["<<__FILE__<<":"<<__LINE__<<"]\n"; g_fail++; return; } } while(0)

// G3a — per-spend absolute cap (1000 SOST)
TEST(GV01_abs_cap) {
    int64_t cap = 1000 * STOCKS_PER_SOST;
    EXPECT(GV_SLICE1_PER_SPEND_CAP_STOCKS == cap, "abs cap = 1000 SOST");
    EXPECT(gv_slice1_amount_within_abs_cap(cap) == true,  "exactly 1000 SOST allowed");
    EXPECT(gv_slice1_amount_within_abs_cap(cap + 1) == false, "1000 SOST + 1 stock rejected");
    EXPECT(gv_slice1_amount_within_abs_cap(5000 * STOCKS_PER_SOST) == false, "5000 SOST over cap");
    EXPECT(gv_slice1_amount_within_abs_cap(-1) == false, "defensive: negative rejected");
}

// G1/G2 — whitelist destination + dual-whitelist agreement
TEST(GV02_whitelist_destination) {
    PubKeyHash genesis{{0x05,0x9d,0x1e,0xf8,0x63,0x9b,0xcf,0x47,0xec,0x35,
                        0xe9,0x29,0x9c,0x17,0xdc,0x04,0x52,0xc3,0xdf,0x33}};
    PubKeyHash unknown{};  // all-zero
    EXPECT(gv_slice1_whitelists_agree() == true, "G2: primary/mirror whitelists agree");
    EXPECT(gv_slice1_destination_allowed(genesis) == true, "G1: genesis miner whitelisted");
    EXPECT(gv_slice1_destination_allowed(unknown) == false, "G1: unknown destination rejected");
}

// G4 — miner signaling threshold (>=90% over 67, floor 61, +10% foundation)
TEST(GV03_g4_signaling_threshold) {
    EXPECT(gv_g4_approval_floor() == 61, "floor = 61/67");
    EXPECT(gv_g4_foundation_weight() == 7, "foundation weight = 7");
    EXPECT(gv_g4_window_approved(60, false) == false, "60/67 below floor");
    EXPECT(gv_g4_window_approved(61, false) == true,  "61/67 meets floor");
    EXPECT(gv_g4_window_approved(54, true)  == true,  "54 + foundation(7) = 61 meets floor");
    EXPECT(gv_g4_window_approved(53, true)  == false, "53 + 7 = 60 below floor");
    EXPECT(gv_g4_window_approved(-1, false) == false, "defensive: negative");
    EXPECT(gv_g4_window_approved(68, false) == false, "defensive: > window");
}

// G5 — guardian veto (silence=accept) + unconditional auto-disconnect
TEST(GV04_g5_veto) {
    EXPECT(gv_g5_spend_blocked(true,  true)  == true,  "active + valid veto -> blocked");
    EXPECT(gv_g5_spend_blocked(true,  false) == false, "active, no veto -> silence = accept");
    EXPECT(gv_g5_spend_blocked(false, true)  == false, "inactive -> veto ignored");
    EXPECT(GV_G5_AUTO_DISCONNECT_HEIGHT == 100000, "guardian dies at block 100000");
    EXPECT(gv_g5_active_at(100000) == false, "auto-disconnect: inactive at 100000");
    EXPECT(gv_g5_active_at(200000) == false, "auto-disconnect: inactive past 100000");
}

// Gate state — DEFERRED on mainnet, V15 on testnet build
TEST(GV05_gates_state) {
#ifdef SOST_TESTNET_FORKS
    EXPECT(GV_SLICE1_ACTIVATION_HEIGHT == V15_HEIGHT, "testnet: slice1 gate at V15");
    EXPECT(GV_G4_ACTIVATION_HEIGHT == V15_HEIGHT, "testnet: G4 gate at V15");
    EXPECT(GV_G5_ACTIVATION_HEIGHT == V15_HEIGHT, "testnet: G5 gate at V15");
#else
    EXPECT(GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX, "mainnet: slice1 DEFERRED (INT64_MAX)");
    EXPECT(GV_G4_ACTIVATION_HEIGHT == INT64_MAX, "mainnet: G4 DEFERRED (INT64_MAX)");
    EXPECT(GV_G5_ACTIVATION_HEIGHT == INT64_MAX, "mainnet: G5 DEFERRED (INT64_MAX)");
    EXPECT(gv_slice1_active_at(1000000) == false, "mainnet: slice1 never active");
    EXPECT(gv_g4_active_at(1000000) == false, "mainnet: G4 never active");
    EXPECT(gv_g5_active_at(50000) == false, "mainnet: G5 never active");
#endif
}

// G3b — rate-limit currently disabled (sentinel) + unwired; intended 144 is
// exercised by scripts/gold_vault_governance_dry_run.py.
TEST(GV06_rate_limit_unwired) {
    EXPECT(GV_SLICE1_RATE_LIMIT_BLOCKS == 0, "rate-limit currently disabled (sentinel 0)");
    EXPECT(gv_slice1_rate_limit_ok(0) == true, "sentinel 0 -> always ok (helper)");
    EXPECT(gv_slice1_rate_limit_ok(INT64_MAX) == true, "no prior spend -> ok");
}

int main() {
    std::cout << "=== Gold Vault governance audit (G1-G5) Tests ===" << std::endl;
    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev = g_fail; fn();
        if (g_fail == prev) { g_pass++; std::cout << "PASS\n"; } else std::cout << "*** FAIL ***\n";
    }
    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail
              << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;
    return g_fail > 0 ? 1 : 0;
}
