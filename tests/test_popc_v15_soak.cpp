// test_popc_v15_soak.cpp — V15 PoPC P5: staged-activation soak (deterministic).
//
// Drives the full staged flow through the gate heights as a pure, reproducible
// simulation (the live multi-node testnet soak across V15_HEIGHT runs separately
// and is tracked in docs/V15_POPC_SOAK_REPORT.md). It proves:
//   * PoPC/Gold Vault go live at V15_HEIGHT; DTD-PoPC eligibility only bites at
//     DTD_POPC_ELIGIBILITY_HEIGHT (= V15_HEIGHT + grace) AND only when the flag is on;
//   * the V15_HEIGHT -> eligibility window lets a miner create + activate a contract;
//   * register-only / unactivated owners do NOT count;
//   * reorg around the gates recomputes deterministically;
//   * mainnet replay stays byte-identical while the shipped gates are deferred/false.
#include "sost/popc_v15.h"
#include "sost/lottery.h"
#include "sost/params.h"
#include <cstdio>
#include <vector>
using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)

static Bytes32 id(uint8_t b){ Bytes32 x{}; x.fill(b); return x; }
static PubKeyHash own(uint8_t b){ PubKeyHash p{}; p.fill(b); return p; }
static PopcV15Event ev(PopcEventType t, Bytes32 cid, PubKeyHash o, uint8_t model, int64_t h, int64_t end){
    PopcV15Event e; e.type=t; e.commitment_id=cid; e.owner_pkh=o; e.model=model; e.height=h; e.end_height=end; return e;
}
// Simulate the lottery's PoPC decision: a miner is EXCLUDED iff the gate is
// enforced at this height AND the miner holds no active PoPC commitment.
static bool excluded(const std::vector<PopcV15Event>& evs, const PubKeyHash& miner, int64_t h, bool gate){
    return lottery::popc_eligibility_enforced(h, gate) && !popc_v15_owner_active(evs, miner, h);
}

int main(){
    std::printf("=== PoPC V15 P5 — staged-activation soak (deterministic) ===\n");
    const int64_t H0  = V15_HEIGHT;                    // PoPC automation goes live
    const int64_t ELI = DTD_POPC_ELIGIBILITY_HEIGHT;   // DTD starts requiring PoPC (= H0 + grace)
    CHECK("eligibility is exactly grace blocks after V15_HEIGHT", ELI == H0 + DTD_POPC_GRACE_BLOCKS);

    const Bytes32 C = id(1);
    const PubKeyHash MINER = own(0xA1), LATE = own(0xB2), NONE = own(0xC3);

    // A miner who creates + activates inside the grace window AND keeps the
    // commitment in good standing. With a 5000-block grace (> the 1440-block
    // audit interval), a one-shot Register+Activate would auto-slash before the
    // eligibility height — a PoPC must be MAINTAINED (an audit response every
    // POPC_V15_AUDIT_INTERVAL_BLOCKS) to stay OPEN through the grace window. The
    // extra Activate events model those audit responses (each updates last_attest).
    std::vector<PopcV15Event> chain = {
        ev(PopcEventType::Register, C, MINER, (uint8_t)PopcModel::A, H0 + 10, ELI + 100000),
        ev(PopcEventType::Activate, C, MINER, (uint8_t)PopcModel::A, H0 + 20, ELI + 100000),
        ev(PopcEventType::Activate, C, MINER, (uint8_t)PopcModel::A, H0 + 20 + 1*POPC_V15_AUDIT_INTERVAL_BLOCKS, ELI + 100000),
        ev(PopcEventType::Activate, C, MINER, (uint8_t)PopcModel::A, H0 + 20 + 2*POPC_V15_AUDIT_INTERVAL_BLOCKS, ELI + 100000),
        ev(PopcEventType::Activate, C, MINER, (uint8_t)PopcModel::A, H0 + 20 + 3*POPC_V15_AUDIT_INTERVAL_BLOCKS, ELI + 100000),
    };

    // ---- staged gate logic (independent of the shipped flag value) ----
    CHECK("not enforced before eligibility even if flag on", !lottery::popc_eligibility_enforced(ELI - 1, true));
    CHECK("enforced at eligibility when flag on",             lottery::popc_eligibility_enforced(ELI,     true));
    CHECK("enforced past eligibility when flag on",           lottery::popc_eligibility_enforced(ELI + 5000, true));
    CHECK("NEVER enforced while flag off",                   !lottery::popc_eligibility_enforced(ELI,     false));

    // ---- the grace window lets a miner create + activate ----
    CHECK("miner active inside the window (before eligibility)", popc_v15_owner_active(chain, MINER, H0 + 50));
    CHECK("miner still active at the eligibility height",        popc_v15_owner_active(chain, MINER, ELI));

    // ---- eligibility outcomes with the flag ON ----
    CHECK("flag ON, at eligibility: active miner NOT excluded",  !excluded(chain, MINER, ELI, true));
    CHECK("flag ON, at eligibility: owner with no PoPC excluded", excluded(chain, NONE,  ELI, true));
    CHECK("flag ON, inside window: nobody excluded yet (pre-eligibility)", !excluded(chain, NONE, ELI - 1, true));

    // ---- eligibility outcomes with the flag OFF (shipped state) ----
    CHECK("flag OFF: active miner not excluded",        !excluded(chain, MINER, ELI, false));
    CHECK("flag OFF: even no-PoPC owner not excluded",  !excluded(chain, NONE,  ELI, false));

    // ---- register-only does NOT count (P4c), so it would be excluded when on ----
    {
        std::vector<PopcV15Event> regOnly = { ev(PopcEventType::Register, C, LATE, (uint8_t)PopcModel::A, H0 + 10, ELI + 100000) };
        CHECK("register-only owner not active", !popc_v15_owner_active(regOnly, LATE, ELI));
        CHECK("flag ON: register-only owner excluded", excluded(regOnly, LATE, ELI, true));
    }

    // ---- reorg around the gates: activated vs not-activated -> different outcome ----
    {
        std::vector<PopcV15Event> noActivate = { ev(PopcEventType::Register, C, MINER, (uint8_t)PopcModel::A, H0 + 10, ELI + 100000) };
        CHECK("reorg: activated chain -> miner eligible",     !excluded(chain,      MINER, ELI, true));
        CHECK("reorg: no-activate chain -> miner excluded",    excluded(noActivate, MINER, ELI, true));
        CHECK("recompute deterministic / no stale state",     !excluded(chain,      MINER, ELI, true));
    }

    // ---- shipped-flag behaviour: mainnet deferred (no-op) vs testnet active ----
#ifndef SOST_TESTNET_FORKS
    // Mainnet: gate ships false -> a chain WITH PoPC carriers excludes nobody, so
    // processing is byte-identical to a chain with no PoPC at all.
    CHECK("mainnet: shipped flag is false", DTD_POPC_GATE_CONSENSUS_ACTIVE == false);
    CHECK("mainnet: shipped gate excludes nobody (active miner)",
          !excluded(chain, MINER, ELI, DTD_POPC_GATE_CONSENSUS_ACTIVE));
    CHECK("mainnet: shipped gate excludes nobody (no-PoPC owner, no-op)",
          !excluded(chain, NONE,  ELI, DTD_POPC_GATE_CONSENSUS_ACTIVE));
#else
    // Testnet (soak build): gate ships true -> the rule BITES with the REAL flag:
    // an owner with a maintained PoPC is included, one without is excluded.
    CHECK("testnet: shipped flag is true (soak)", DTD_POPC_GATE_CONSENSUS_ACTIVE == true);
    CHECK("testnet: shipped gate keeps the maintained miner eligible",
          !excluded(chain, MINER, ELI, DTD_POPC_GATE_CONSENSUS_ACTIVE));
    CHECK("testnet: shipped gate excludes the no-PoPC owner",
          excluded(chain, NONE,  ELI, DTD_POPC_GATE_CONSENSUS_ACTIVE));
#endif

#ifndef SOST_TESTNET_FORKS
    CHECK("mainnet: PoPC automation deferred at V15_HEIGHT (20000)", !popc_v15_active_at(H0));
    CHECK("mainnet: PoPC automation deferred at eligibility (25000)", !popc_v15_active_at(ELI));
    CHECK("mainnet: V15_HEIGHT == 20000", H0 == 20000);
    CHECK("mainnet: eligibility == 25000", ELI == 25000);
#else
    CHECK("testnet: PoPC automation live at V15_HEIGHT", popc_v15_active_at(H0));
    CHECK("testnet: PoPC automation live at eligibility", popc_v15_active_at(ELI));
    CHECK("testnet: V15_HEIGHT == 300", H0 == 300);
    CHECK("testnet: eligibility == 5300", ELI == 5300);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
