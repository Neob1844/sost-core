// test_popc_v15_set.cpp — V15 PoPC P2 (+ P4c): chain_active_popc_set pure recompute.
// Deterministic, reorg-safe fold over canonical PoPC events. No crypto, no node.
//
// P4c: Register only DECLARES a commitment (Pending). It is NOT active until a
// valid Activate lands. So every "active" scenario here registers AND activates;
// a register-only commitment must NOT appear in the active set. "Active" queries
// are kept below the first audit deadline so auto-slash (P4b) does not interfere
// with what these tests check (the explicit-event fold).
#include "sost/popc_v15.h"
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
// Register (rh) + Activate (ah) — the canonical path to an Active commitment.
static void reg_act(std::vector<PopcV15Event>& v, Bytes32 cid, PubKeyHash o, uint8_t model, int64_t rh, int64_t ah, int64_t end){
    v.push_back(ev(PopcEventType::Register,cid,o,model,rh,end));
    v.push_back(ev(PopcEventType::Activate,cid,o,model,ah,end));
}
static bool inSet(const std::vector<PopcActiveEntry>& s, Bytes32 cid){
    for(auto&e:s) if(e.commitment_id==cid) return true; return false;
}

int main(){
    std::printf("=== PoPC V15 P2/P4c — chain_active_popc_set (pure, reorg-safe) ===\n");
    Bytes32 A=id(1), B=id(2), C=id(3), D=id(4);
    PubKeyHash oA=own(0xA1), oB=own(0xB2), oC=own(0xC3), oD=own(0xD4);

    // empty
    CHECK("empty events -> empty set", chain_active_popc_set({}, 5000).empty());

    // Model A + B activated & active; expired one out; register-only NOT active
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, (uint8_t)PopcModel::A, 1000, 1000, 9000);
        reg_act(events, B, oB, (uint8_t)PopcModel::B, 1100, 1100, 9000);
        reg_act(events, C, oC, (uint8_t)PopcModel::A, 1200, 1200, 1500);   // short term
        events.push_back(ev(PopcEventType::Register, D, oD, (uint8_t)PopcModel::A, 1000, 9000)); // register-only
        auto s=chain_active_popc_set(events,2000);
        CHECK("Model A activated -> active", inSet(s,A));
        CHECK("Model B activated -> active", inSet(s,B));
        CHECK("expired (H>=end) out of set", !inSet(s,C));
        CHECK("register-only (no Activate) NOT active", !inSet(s,D));
        CHECK("set size == 2", s.size()==2);
        CHECK("owner_active(oA) true", popc_v15_owner_active(events,oA,2000));
        CHECK("owner_active(oD) false (register-only)", !popc_v15_owner_active(events,oD,2000));
        CHECK("owner_active(oC) false (expired)", !popc_v15_owner_active(events,oC,2000));
        CHECK("register-only status is Pending", popc_v15_commitment_status(events,D,2000)==PopcV15Status::Pending);
    }

    // slashed leaves the set; terminal (later renew ignored)
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, 0, 1000, 1000, 9000);
        events.push_back(ev(PopcEventType::Slash,A,oA,0,1500,0));
        events.push_back(ev(PopcEventType::Renew,A,oA,0,1800,12000));   // must be ignored (terminal)
        CHECK("slashed -> out of set", !inSet(chain_active_popc_set(events,2000),A));
    }

    // settle leaves the set
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, 0, 1000, 1000, 9000);
        events.push_back(ev(PopcEventType::Settle,A,oA,0,1500,0));
        CHECK("settled -> out of set", !inSet(chain_active_popc_set(events,2000),A));
    }

    // renew extends the term: active past the OLD end (query below first audit)
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, 0, 1000, 1000, 2000);
        events.push_back(ev(PopcEventType::Renew,A,oA,0,1800,5000));
        CHECK("after renew: active past old end", inSet(chain_active_popc_set(events,2300),A));
        CHECK("after renew: out past new end",   !inSet(chain_active_popc_set(events,5000),A));
    }

    // duplicate Register is idempotent (first wins → deterministic)
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, 0, 1000, 1000, 9000);
        events.push_back(ev(PopcEventType::Register,A,oB,1,1100,3000)); // dup id, diff owner/end
        auto s=chain_active_popc_set(events,2000);
        CHECK("duplicate register: still one entry", s.size()==1);
        CHECK("duplicate register: first wins (owner oA, end 9000)", s[0].owner_pkh==oA && s[0].end_height==9000);
    }

    // slash vs renew: order-independent terminal outcome
    {
        std::vector<PopcV15Event> renThenSlash; reg_act(renThenSlash,A,oA,0,1000,1000,9000);
        renThenSlash.push_back(ev(PopcEventType::Renew,A,oA,0,1200,12000));
        renThenSlash.push_back(ev(PopcEventType::Slash,A,oA,0,1500,0));
        std::vector<PopcV15Event> slashThenRen; reg_act(slashThenRen,A,oA,0,1000,1000,9000);
        slashThenRen.push_back(ev(PopcEventType::Slash,A,oA,0,1200,0));
        slashThenRen.push_back(ev(PopcEventType::Renew,A,oA,0,1500,12000));
        CHECK("renew-then-slash -> slashed (out)", !inSet(chain_active_popc_set(renThenSlash,2000),A));
        CHECK("slash-then-renew -> slashed (out)", !inSet(chain_active_popc_set(slashThenRen,2000),A));
    }

    // expiry boundary: H==end-1 in, H==end out (activate late so no audit is due)
    {
        std::vector<PopcV15Event> events;
        reg_act(events, A, oA, 0, 1000, 4000, 5000);   // activate at 4000; first audit 5440 > 4999
        CHECK("boundary H=end-1 in", inSet(chain_active_popc_set(events,4999),A));
        CHECK("boundary H=end out",  !inSet(chain_active_popc_set(events,5000),A));
    }

    // future events ignored (height > at_height)
    {
        std::vector<PopcV15Event> events; reg_act(events,A,oA,0,1000,1000,9000);
        events.push_back(ev(PopcEventType::Slash,A,oA,0,1500,0));
        CHECK("at H=1200: slash (h=1500) not yet applied -> active", inSet(chain_active_popc_set(events,1200),A));
        CHECK("at H=2000: slash applied -> out", !inSet(chain_active_popc_set(events,2000),A));
    }

    // REORG: a different event list (with a slash) yields a different set; recompute is pure
    {
        std::vector<PopcV15Event> chainNoSlash; reg_act(chainNoSlash,A,oA,0,1000,1000,9000);
        std::vector<PopcV15Event> chainSlash;   reg_act(chainSlash,A,oA,0,1000,1000,9000);
        chainSlash.push_back(ev(PopcEventType::Slash,A,oA,0,1500,0));
        CHECK("reorg: no-slash chain has it",  inSet(chain_active_popc_set(chainNoSlash,2000),A)==true);
        CHECK("reorg: slash chain drops it",   inSet(chain_active_popc_set(chainSlash,2000),A)==false);
        CHECK("recompute deterministic / no stale state", inSet(chain_active_popc_set(chainNoSlash,2000),A)==true);
    }

    // determinism: same input twice -> identical set (size + order + ids)
    {
        std::vector<PopcV15Event> events; reg_act(events,B,oB,1,1100,1100,9000); reg_act(events,A,oA,0,1000,1000,9000);
        auto s1=chain_active_popc_set(events,2000), s2=chain_active_popc_set(events,2000);
        bool same = s1.size()==s2.size();
        for(size_t i=0;same&&i<s1.size();++i) same = (s1[i].commitment_id==s2[i].commitment_id);
        CHECK("deterministic identical output", same);
    }

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
