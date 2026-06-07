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
#else
static_assert(V14_HEIGHT == 15000,
    "V14_HEIGHT moved from 15000 — re-audit the whole V14 scope before changing.");
#endif
static_assert(DYNAMIC_FEE_BASE == 1,
    "Pre-V14 relay floor base must stay 1 stock/byte (historical replay).");
static_assert(DYNAMIC_FEE_BASE_V14 == 10,
    "V14 relay floor base changed from 10 stocks/byte — confirm intentional.");
static_assert(DYNAMIC_FEE_ACTIVATION_HEIGHT == 10000,
    "Dynamic-fee policy activation height changed.");

// ---- Deferred gates: MUST be no-ops in V14 (flip only via point release) ----
static_assert(DTD_POPC_ELIGIBILITY_HEIGHT == V14_HEIGHT,
    "DTD_POPC_ELIGIBILITY_HEIGHT must equal V14_HEIGHT.");
static_assert(DTD_POPC_GATE_CONSENSUS_ACTIVE == false,
    "PoPC eligibility gate must ship DEFERRED until on-chain PoPC migration "
    "(docs/V14_EXECUTION_PLAN.md Phase C). Do NOT flip here.");
static_assert(DTD_EMERGENCY_CONTROL_MIN_HEIGHT == V14_HEIGHT,
    "DTD emergency-control min height must equal V14_HEIGHT.");
static_assert(DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE == false,
    "DTD emergency pause/resume must ship DEFERRED (no-op) in V14.");

// ---- Gold Vault Phase I governance ----------------------------------------
static_assert(GV_THRESHOLD_EPOCH01 == 90,
    "Gold Vault governance threshold synced to 90% in V14-1; do not revert.");
static_assert(GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX,
    "Gold Vault Slice 1 ships DEFERRED (INT64_MAX). Activating it is an operator "
    "decision (whitelist + cap) landed in one reviewed commit — see "
    "docs/V14_EXECUTION_PLAN.md Phase B. Update this pin deliberately when ready.");

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
