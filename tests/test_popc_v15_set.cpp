// test_popc_v15_set.cpp — V15 PoPC P2: chain_active_popc_set pure recompute.
// Deterministic, reorg-safe fold over canonical PoPC events. No crypto, no node.
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
static bool inSet(const std::vector<PopcActiveEntry>& s, Bytes32 cid){
    for(auto&e:s) if(e.commitment_id==cid) return true; return false;
}

int main(){
    std::printf("=== PoPC V15 P2 — chain_active_popc_set (pure, reorg-safe) ===\n");
    Bytes32 A=id(1), B=id(2), C=id(3);
    PubKeyHash oA=own(0xA1), oB=own(0xB2), oC=own(0xC3);

    // empty
    CHECK("empty events -> empty set", chain_active_popc_set({}, 5000).empty());

    // Model A + Model B active; expired one out
    {
        std::vector<PopcV15Event> events={
            ev(PopcEventType::Register,A,oA,(uint8_t)PopcModel::A,1000,9000),
            ev(PopcEventType::Register,B,oB,(uint8_t)PopcModel::B,1100,9000),
            ev(PopcEventType::Register,C,oC,(uint8_t)PopcModel::A,1200,1500),  // short term
        };
        auto s=chain_active_popc_set(events,2000);
        CHECK("Model A active", inSet(s,A));
        CHECK("Model B active", inSet(s,B));
        CHECK("expired (H>=end) out of set", !inSet(s,C));
        CHECK("set size == 2", s.size()==2);
        CHECK("owner_active(oA) true", popc_v15_owner_active(events,oA,2000));
        CHECK("owner_active(oC) false (expired)", !popc_v15_owner_active(events,oC,2000));
    }

    // slashed leaves the set; terminal (later renew ignored)
    {
        std::vector<PopcV15Event> events={
            ev(PopcEventType::Register,A,oA,0,1000,9000),
            ev(PopcEventType::Slash,A,oA,0,2000,0),
            ev(PopcEventType::Renew,A,oA,0,2500,12000),   // must be ignored (terminal)
        };
        CHECK("slashed -> out of set", !inSet(chain_active_popc_set(events,3000),A));
    }

    // settle leaves the set
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,A,oA,0,1000,9000),
                                           ev(PopcEventType::Settle,A,oA,0,2000,0) };
        CHECK("settled -> out of set", !inSet(chain_active_popc_set(events,3000),A));
    }

    // renew extends the term: active past the OLD end
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,A,oA,0,1000,2000),
                                           ev(PopcEventType::Renew,A,oA,0,1800,5000) };
        CHECK("after renew: active past old end", inSet(chain_active_popc_set(events,2500),A));
        CHECK("after renew: out past new end",   !inSet(chain_active_popc_set(events,5000),A));
    }

    // duplicate Register is idempotent (first wins → deterministic)
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,A,oA,0,1000,9000),
                                           ev(PopcEventType::Register,A,oB,1,1100,3000) }; // dup id, diff owner/end
        auto s=chain_active_popc_set(events,2000);
        CHECK("duplicate register: still one entry", s.size()==1);
        CHECK("duplicate register: first wins (owner oA, end 9000)", s[0].owner_pkh==oA && s[0].end_height==9000);
    }

    // slash vs renew: order-independent terminal outcome
    {
        std::vector<PopcV15Event> renThenSlash={ ev(PopcEventType::Register,A,oA,0,1000,9000),
            ev(PopcEventType::Renew,A,oA,0,1500,12000), ev(PopcEventType::Slash,A,oA,0,2000,0) };
        std::vector<PopcV15Event> slashThenRen={ ev(PopcEventType::Register,A,oA,0,1000,9000),
            ev(PopcEventType::Slash,A,oA,0,1500,0), ev(PopcEventType::Renew,A,oA,0,2000,12000) };
        CHECK("renew-then-slash -> slashed (out)", !inSet(chain_active_popc_set(renThenSlash,3000),A));
        CHECK("slash-then-renew -> slashed (out)", !inSet(chain_active_popc_set(slashThenRen,3000),A));
    }

    // expiry boundary: H==end-1 in, H==end out
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,A,oA,0,1000,5000) };
        CHECK("boundary H=end-1 in", inSet(chain_active_popc_set(events,4999),A));
        CHECK("boundary H=end out",  !inSet(chain_active_popc_set(events,5000),A));
    }

    // future events ignored (height > at_height)
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,A,oA,0,1000,9000),
                                           ev(PopcEventType::Slash,A,oA,0,3000,0) };
        CHECK("at H=2000: slash (h=3000) not yet applied -> active", inSet(chain_active_popc_set(events,2000),A));
        CHECK("at H=3000: slash applied -> out", !inSet(chain_active_popc_set(events,3000),A));
    }

    // REORG: a different event list (with a slash) yields a different set; recompute is pure
    {
        std::vector<PopcV15Event> chainNoSlash={ ev(PopcEventType::Register,A,oA,0,1000,9000) };
        std::vector<PopcV15Event> chainSlash  ={ ev(PopcEventType::Register,A,oA,0,1000,9000),
                                                 ev(PopcEventType::Slash,A,oA,0,2000,0) };
        bool a1=inSet(chain_active_popc_set(chainNoSlash,3000),A);
        bool b1=inSet(chain_active_popc_set(chainSlash,3000),A);
        CHECK("reorg: no-slash chain has it",  a1==true);
        CHECK("reorg: slash chain drops it",   b1==false);
        // recompute the first again — no surviving state from the other
        CHECK("recompute deterministic / no stale state", inSet(chain_active_popc_set(chainNoSlash,3000),A)==true);
    }

    // determinism: same input twice -> identical set (size + order + ids)
    {
        std::vector<PopcV15Event> events={ ev(PopcEventType::Register,B,oB,1,1100,9000),
                                           ev(PopcEventType::Register,A,oA,0,1000,9000) };
        auto s1=chain_active_popc_set(events,2000), s2=chain_active_popc_set(events,2000);
        bool same = s1.size()==s2.size();
        for(size_t i=0;same&&i<s1.size();++i) same = (s1[i].commitment_id==s2[i].commitment_id);
        CHECK("deterministic identical output", same);
    }

    std::printf("=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
