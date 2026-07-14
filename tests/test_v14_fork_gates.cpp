// =============================================================================
// test_v14_fork_gates.cpp — V14 (block 15000) constant anchors / safety pins.
//
// Compile-time guard: if any V14-gating constant drifts, the BUILD FAILS here,
// forcing a conscious review (and a test update) before a consensus parameter
// can change. This is the cheapest, zero-risk brick of the V14 safety net
// (docs/V14_EXECUTION_PLAN.md, Phase A / A1).
//
// What is pinned:
//   * V14_HEIGHT and the policy/consensus constants that ride on it.
//   * The deferred gates that MUST ship as no-ops in V14 (PoPC eligibility,
//     DTD emergency control, Gold Vault Slice 1). Flipping any of these is a
//     separate, announced point release — never an accidental edit.
// =============================================================================

#include "sost/params.h"
#include "sost/consensus_constants.h"
#include "sost/gold_vault_slice1.h"
#include <cstdint>
#include <cstdio>

using namespace sost;

// ---- V14 fork height + the changes that actually ENFORCE in V14 -------------
#ifdef SOST_TESTNET_FORKS
static_assert(V14_HEIGHT == 200,
    "Testnet build: V14_HEIGHT must be the early testnet height (200).");
static_assert(V15_HEIGHT == 300,
    "Testnet build: V15_HEIGHT must be the early testnet height (300).");
#else
static_assert(V14_HEIGHT == 15000,
    "V14_HEIGHT moved from 15000 — V14 (H3/H4 hardening) ships at 15000 UNCHANGED "
    "(already in deployed binaries). The automation bundle is V15, not V14.");
static_assert(V15_HEIGHT == 20000,
    "V15_HEIGHT moved from 20000 — V15 (PoPC A/B, atomic swap, Gold Vault gov) is "
    "the full automation bundle; re-audit scope before changing.");
#endif
static_assert(DYNAMIC_FEE_BASE == 1,
    "Pre-V14 relay floor base must stay 1 stock/byte (historical replay).");
static_assert(DYNAMIC_FEE_BASE_V14 == 10,
    "V14 relay floor base changed from 10 stocks/byte — confirm intentional.");
static_assert(DYNAMIC_FEE_ACTIVATION_HEIGHT == 10000,
    "Dynamic-fee policy activation height changed.");

// ---- Deferred gates: MUST be no-ops in V14 (flip only via point release) ----
// P4c — DTD-PoPC eligibility is staged AFTER PoPC automation (V15_HEIGHT) by a
// grace window, so miners can create+activate a contract before the lottery
// requires it. The gate itself still ships DEFERRED (flag false).
static_assert(DTD_POPC_GRACE_BLOCKS == 5000,
    "PoPC eligibility grace window changed from 5000 blocks — confirm intentional.");
// V15 Final Decentralization Fork: the DTD-PoPC eligibility gate is RETIRED on
// mainnet (DTD never requires PoPC — SOST is fully autonomous). The testnet
// profile keeps it soaked so the PoPC subsystem can still be exercised there.
#ifdef SOST_TESTNET_FORKS
static_assert(DTD_POPC_ELIGIBILITY_HEIGHT == V15_HEIGHT + DTD_POPC_GRACE_BLOCKS,
    "Testnet: DTD_POPC_ELIGIBILITY_HEIGHT == V15_HEIGHT + grace (5300).");
static_assert(DTD_POPC_GATE_CONSENSUS_ACTIVE == true,
    "Testnet: DTD-PoPC eligibility gate kept ACTIVE to soak the PoPC subsystem.");
#else
static_assert(DTD_POPC_ELIGIBILITY_HEIGHT == INT64_MAX,
    "Mainnet: DTD-PoPC eligibility RETIRED to INT64_MAX by the V15 final-decentralization fork.");
static_assert(DTD_POPC_GATE_CONSENSUS_ACTIVE == false,
    "Mainnet: DTD-PoPC eligibility gate RETIRED (false) by the V15 final-decentralization fork.");
#endif
static_assert(DTD_EMERGENCY_CONTROL_MIN_HEIGHT == V14_HEIGHT,
    "DTD emergency-control min height must equal V14_HEIGHT.");
static_assert(DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE == false,
    "DTD emergency pause/resume must ship DEFERRED (no-op) in V14.");

// ---- Gold Vault Phase I governance ----------------------------------------
static_assert(GV_THRESHOLD_EPOCH01 == 90,
    "Gold Vault governance threshold synced to 90% in V14-1; do not revert.");
#ifdef SOST_TESTNET_FORKS
static_assert(GV_SLICE1_ACTIVATION_HEIGHT == V15_HEIGHT,
    "Testnet: Gold Vault Slice 1 activates at V15_HEIGHT to dry-run (V15 bundle).");
#else
static_assert(GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX,
    "MAINNET: Gold Vault Slice 1 stays DEFERRED (INT64_MAX) until full G1-G5 is "
    "built + testnet-soaked; the final pre-fork commit flips it to V15_HEIGHT "
    "(automation bundle, block 20000). Do NOT flip here.");
#endif
// Whitelist + cap are now CONFIGURED (genesis miner, 1,000 SOST) even while the
// mainnet gate is deferred — they only take effect once the gate is active.
static_assert(GV_SLICE1_WHITELIST_PRIMARY_LEN == 1,
    "Gold Vault Slice 1 whitelist must hold exactly the genesis miner.");
static_assert(GV_SLICE1_PER_SPEND_CAP_STOCKS == 1000 * STOCKS_PER_SOST,
    "Gold Vault Slice 1 absolute cap must be 1,000 SOST.");

int main() {
    std::printf("V14 fork-gate constants pinned: PASS\n");
    std::printf("  V14_HEIGHT=%lld  fee_base_v14=%lld\n",
                (long long)V14_HEIGHT, (long long)DYNAMIC_FEE_BASE_V14);
    std::printf("  deferred: popc_gate=%d dtd_emergency=%d gv_slice1_height=%lld\n",
                (int)DTD_POPC_GATE_CONSENSUS_ACTIVE,
                (int)DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE,
                (long long)GV_SLICE1_ACTIVATION_HEIGHT);
    return 0;
}
