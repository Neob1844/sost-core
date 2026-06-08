// test_popc_v15_eligibility.cpp — V15 PoPC P4a: the consensus eligibility hook.
//
// P4a wires lottery::has_active_canonical_popc to a chain-derived PoPC event
// source (set_popc_event_source). This test injects a synthetic source (so it
// does NOT depend on node/block plumbing) and proves:
//   * gated: on a mainnet build popc_v15 is deferred (INT64_MAX) → the hook is a
//     pure no-op (always true), byte-identical to pre-P4a — the source is never
//     consulted, even for an owner with NO commitment.
//   * active: on a testnet build (SOST_TESTNET_FORKS) the hook recomputes the
//     active set from the injected events: an active owner passes; an unknown /
//     expired / slashed / settled / suspended owner does NOT; a Renew revives.
//
// The discriminating case is the NEGATIVE one (unknown/expired owner): pre-P4a
// the hook returned true for everyone; post-P4a, once the gate is live, it must
// return false. On mainnet the same query must still return true (no-op).
#include "sost/lottery.h"
#include "sost/popc_v15.h"
#include "sost/params.h"
#include <cstdio>
#include <vector>

using namespace sost;

static int g_pass=0, g_fail=0;
#define CHECK(n,c) do{ if(c){++g_pass;std::printf("  ok  %s\n",n);} else {++g_fail;std::printf("  *** FAIL: %s\n",n);} }while(0)

static Bytes32 id(uint8_t b){ Bytes32 x{}; x.fill(b); return x; }
static PubKeyHash own(uint8_t b){ PubKeyHash p{}; p.fill(b); return p; }

static PopcV15Event ev(PopcEventType t, uint8_t cid, uint8_t owner, int64_t h, int64_t end){
    PopcV15Event e; e.type=t; e.commitment_id=id(cid); e.owner_pkh=own(owner);
    e.model=(uint8_t)PopcModel::A; e.height=h; e.end_height=end; return e;
}

int main(){
    std::printf("=== PoPC V15 P4a — consensus eligibility hook ===\n");

    // Owners used across the scenarios.
    const uint8_t A=0x10, B=0x20, EXP=0x30, SLA=0x40, SET=0x50, SUS=0x60, REN=0x70, UNK=0x99;
    const int64_t Q = 5000;   // query height (>= testnet V15_HEIGHT=300)

    // Build one event log covering every state, applied in chain order.
    std::vector<PopcV15Event> log = {
        // A: active, end well past the query
        ev(PopcEventType::Register, 0x01, A,   100,  100000),
        // EXP: registered active but end_height already reached at the query
        ev(PopcEventType::Register, 0x02, EXP, 100,  4000),
        // SLA: registered then slashed (terminal)
        ev(PopcEventType::Register, 0x03, SLA, 100,  100000),
        ev(PopcEventType::Slash,    0x03, SLA, 200,  0),
        // SET: registered then settled (terminal)
        ev(PopcEventType::Register, 0x04, SET, 100,  100000),
        ev(PopcEventType::Settle,   0x04, SET, 200,  0),
        // SUS: registered then suspended (not active until re-activated)
        ev(PopcEventType::Register, 0x05, SUS, 100,  100000),
        ev(PopcEventType::Suspend,  0x05, SUS, 200,  0),
        // REN: registered with an end before the query, then renewed past it
        ev(PopcEventType::Register, 0x06, REN, 100,  4000),
        ev(PopcEventType::Renew,    0x06, REN, 300,  100000),
    };

    // Inject the source. node_collect_popc_events is bypassed on purpose — we are
    // testing the hook contract, not the block scanner.
    lottery::set_popc_event_source([log](int64_t /*h*/){ return log; });

#ifndef SOST_TESTNET_FORKS
    // --- Mainnet build: deferred at INT64_MAX → pure no-op (always true). ---
    CHECK("mainnet: popc_v15 deferred",            popc_v15_active_at(Q)==false);
    CHECK("mainnet: active owner -> true (no-op)",  lottery::has_active_canonical_popc(own(A),   Q)==true);
    CHECK("mainnet: unknown owner -> true (no-op)", lottery::has_active_canonical_popc(own(UNK), Q)==true);
    CHECK("mainnet: expired owner -> true (no-op)", lottery::has_active_canonical_popc(own(EXP), Q)==true);
    CHECK("mainnet: slashed owner -> true (no-op)", lottery::has_active_canonical_popc(own(SLA), Q)==true);
#else
    // --- Testnet build: gate live at/after V15_HEIGHT → recompute from events. ---
    CHECK("testnet: popc_v15 active at query",      popc_v15_active_at(Q)==true);

    // Pre-activation height is below the gate → still the no-op (true) path.
    CHECK("testnet: below gate -> true (no-op)",
          lottery::has_active_canonical_popc(own(UNK), V15_HEIGHT-1)==true);

    // At/after the gate, eligibility is the real chain-derived answer.
    CHECK("testnet: active owner PASSES",           lottery::has_active_canonical_popc(own(A),   Q)==true);
    CHECK("testnet: unknown owner does NOT pass",   lottery::has_active_canonical_popc(own(UNK), Q)==false);
    CHECK("testnet: expired owner does NOT pass",   lottery::has_active_canonical_popc(own(EXP), Q)==false);
    CHECK("testnet: slashed owner does NOT pass",   lottery::has_active_canonical_popc(own(SLA), Q)==false);
    CHECK("testnet: settled owner does NOT pass",   lottery::has_active_canonical_popc(own(SET), Q)==false);
    CHECK("testnet: suspended owner does NOT pass", lottery::has_active_canonical_popc(own(SUS), Q)==false);
    CHECK("testnet: renewed owner PASSES",          lottery::has_active_canonical_popc(own(REN), Q)==true);

    // Reorg/time safety: query strictly before an event sees the earlier state.
    // At height 3500 REN's renew (height 300, end 100000) is already applied, but
    // EXP (end 4000) is still active; at 4500 EXP has lapsed.
    CHECK("testnet: EXP active before its end_height",
          lottery::has_active_canonical_popc(own(EXP), 3500)==true);
    CHECK("testnet: EXP inactive after its end_height",
          lottery::has_active_canonical_popc(own(EXP), 4500)==false);

    // Defensive: with no source installed the hook falls back to true (no-op).
    lottery::set_popc_event_source(nullptr);
    CHECK("testnet: no source -> true (defensive no-op)",
          lottery::has_active_canonical_popc(own(UNK), Q)==true);
#endif

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
