// test_popc_v15_lifecycle.cpp — V15 PoPC P4b: deterministic auto-slash + auto-settle.
//
// The lifecycle is closed PURELY in chain_popc_recompute: an activated commitment
// that misses a scheduled audit (no re-attestation past the grace window) is
// auto-slashed; one that reaches end_height in good standing is auto-settled. No
// Guardian, no signature, no oracle — every node recomputes the identical state
// from the chain events, so it is reorg-safe. These tests drive the pure engine
// directly (no node, no crypto) for Model A and Model B.
#include "sost/popc_v15.h"
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
static bool inSet(const std::vector<PopcActiveEntry>& s, Bytes32 cid){
    for(auto&e:s) if(e.commitment_id==cid) return true; return false;
}

int main(){
    std::printf("=== PoPC V15 P4b — auto-slash + auto-settle (pure, reorg-safe) ===\n");
    const int64_t I = POPC_V15_AUDIT_INTERVAL_BLOCKS;     // 1440
    const int64_t G = POPC_V15_AUDIT_GRACE_BLOCKS;        // 288
    const Bytes32 A=id(1);
    const PubKeyHash oA=own(0xA1), oB=own(0xB2);

    // Activated commitment: Register + Activate at h=100, long term.
    auto baseA = [&](int64_t end, uint8_t model){
        return std::vector<PopcV15Event>{
            ev(PopcEventType::Register, A, oA, model, 100, end),
            ev(PopcEventType::Activate, A, oA, model, 100, end),
        };
    };

    // ---- auto-slash timing: not before grace, yes after ----
    {
        auto e = baseA(100000, (uint8_t)PopcModel::A);
        int64_t firstAudit = 100 + I;                       // 1540
        // exactly at the audit, within grace -> still Active
        CHECK("no slash at the audit height (within grace)",
              popc_v15_commitment_status(e, A, firstAudit) == PopcV15Status::Active);
        CHECK("no slash at last grace block",
              popc_v15_commitment_status(e, A, firstAudit + G) == PopcV15Status::Active);
        // one block past grace -> auto-slashed
        CHECK("AUTO-SLASH one block past grace",
              popc_v15_commitment_status(e, A, firstAudit + G + 1) == PopcV15Status::Slashed);
        CHECK("auto-slashed owner not active",
              !popc_v15_owner_active(e, oA, firstAudit + G + 1));
        CHECK("before first audit: still active (no audit due yet)",
              popc_v15_commitment_status(e, A, firstAudit - 1) == PopcV15Status::Active);
    }

    // ---- re-attestation (a fresh Activate) answers the audit and avoids slash ----
    {
        auto e = baseA(100000, (uint8_t)PopcModel::A);
        e.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::A, 100 + I + 10, 100000)); // re-attest after audit due
        CHECK("re-attest after audit -> stays Active past grace",
              popc_v15_commitment_status(e, A, 100 + I + G + 1) == PopcV15Status::Active);
        // a re-attest BEFORE the audit became due does NOT answer it
        auto e2 = baseA(100000, (uint8_t)PopcModel::A);
        e2.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::A, 100 + I - 50, 100000)); // too early
        CHECK("re-attest before the audit does NOT answer it -> slashed",
              popc_v15_commitment_status(e2, A, 100 + I + G + 1) == PopcV15Status::Slashed);
    }

    // ---- auto-settle at end_height in good standing ----
    {
        int64_t end = 2000;                                  // first audit 1540 < end
        auto e = baseA(end, (uint8_t)PopcModel::A);
        e.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::A, 1600, end)); // answer the 1540 audit
        CHECK("before end & audits answered -> Active", popc_v15_commitment_status(e, A, 1999) == PopcV15Status::Active);
        CHECK("AUTO-SETTLE at end_height in good standing", popc_v15_commitment_status(e, A, end) == PopcV15Status::Settled);
        CHECK("settled owner not active", !popc_v15_owner_active(e, oA, end));
    }

    // ---- slashed does NOT settle as good: missed audit before end -> Slashed at end ----
    {
        int64_t end = 2000;
        auto e = baseA(end, (uint8_t)PopcModel::A);          // never re-attests; audit 1540 missed
        CHECK("missed audit then reaches end -> SLASHED not Settled",
              popc_v15_commitment_status(e, A, end) == PopcV15Status::Slashed);
    }

    // ---- renew before expiry avoids an incorrect settle/slash ----
    {
        auto e = baseA(2000, (uint8_t)PopcModel::A);
        e.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::A, 1600, 2000)); // answer 1540 audit
        e.push_back(ev(PopcEventType::Renew,    A, oA, (uint8_t)PopcModel::A, 1800, 5000)); // extend term
        CHECK("renew extends -> not settled past OLD end", popc_v15_commitment_status(e, A, 2500) == PopcV15Status::Active);
        CHECK("renewed commitment is in the active set", inSet(chain_active_popc_set(e, 2500), A));
    }

    // ---- explicit Slash/Settle carriers stay terminal (never auto-overridden) ----
    {
        auto e = baseA(100000, (uint8_t)PopcModel::A);
        e.push_back(ev(PopcEventType::Settle, A, oA, (uint8_t)PopcModel::A, 500, 0));
        CHECK("explicit Settle is terminal (no later auto-slash)",
              popc_v15_commitment_status(e, A, 100000) == PopcV15Status::Settled);
    }

    // ---- a bare Register (never Activated) is Pending (P4c) — not active, not slashed ----
    {
        std::vector<PopcV15Event> e = { ev(PopcEventType::Register, A, oA, (uint8_t)PopcModel::A, 100, 100000) };
        CHECK("never-activated commitment stays Pending (never active, never auto-slashed)",
              popc_v15_commitment_status(e, A, 100 + 10*I) == PopcV15Status::Pending);
    }

    // ---- Model B: same auto-slash / auto-settle behaviour ----
    {
        auto sl = baseA(100000, (uint8_t)PopcModel::B);
        CHECK("Model B auto-slash past grace",
              popc_v15_commitment_status(sl, A, 100 + I + G + 1) == PopcV15Status::Slashed);
        int64_t end = 2000;
        auto st = baseA(end, (uint8_t)PopcModel::B);
        st.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::B, 1600, end));
        CHECK("Model B auto-settle at end", popc_v15_commitment_status(st, A, end) == PopcV15Status::Settled);
    }

    // ---- reorg recompute: same height, different event lists -> different state ----
    {
        auto missed   = baseA(100000, (uint8_t)PopcModel::A);                       // no re-attest
        auto answered = baseA(100000, (uint8_t)PopcModel::A);
        answered.push_back(ev(PopcEventType::Activate, A, oA, (uint8_t)PopcModel::A, 100 + I + 5, 100000));
        int64_t q = 100 + I + G + 1;
        CHECK("reorg: missed-audit chain -> Slashed",  popc_v15_commitment_status(missed,   A, q) == PopcV15Status::Slashed);
        CHECK("reorg: answered chain     -> Active",   popc_v15_commitment_status(answered, A, q) == PopcV15Status::Active);
        // pure recompute: no stale state survives between calls
        CHECK("recompute deterministic / no stale state",
              popc_v15_commitment_status(missed, A, q) == PopcV15Status::Slashed);
    }

    // ---- P4c: register-only is Pending (never in the active set); activated is ----
    {
        std::vector<PopcV15Event> e = { ev(PopcEventType::Register, A, oA, 0, 1000, 9000) };
        CHECK("register-only NOT in active set (P4c)", !inSet(chain_active_popc_set(e, 2000), A));
        std::vector<PopcV15Event> e2 = {
            ev(PopcEventType::Register, A, oA, 0, 1000, 9000),
            ev(PopcEventType::Activate, A, oA, 0, 1000, 9000),
        };
        CHECK("registered + activated IS in active set", inSet(chain_active_popc_set(e2, 2000), A));
        CHECK("registered + activated out at end",       !inSet(chain_active_popc_set(e2, 9000), A));
    }

    // ---- gating: empty events = no-op (no carriers); V15 ACTIVATED on both profiles ----
    CHECK("no events -> empty active set (no-op)", chain_active_popc_set({}, 5000).empty());
    CHECK("no events -> Pending status (no-op)",   popc_v15_commitment_status({}, A, 5000) == PopcV15Status::Pending);
    CHECK("DTD-PoPC bridge ACTIVE (V15)", DTD_POPC_GATE_CONSENSUS_ACTIVE == true);
    CHECK("popc_v15 active at V15_HEIGHT", popc_v15_active_at(V15_HEIGHT) == true);

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    (void)oB;
    return g_fail==0?0:1;
}
