// coord_gate — makes the REAL C++ Coordinator the effective governor of a live swap harness.
// State is reconstructed by replaying an append-only event log, so the harness can call this
// once per transition; the harness only advances when the Coordinator AUTHORIZES the event.
//
//   coord_gate create <logfile> <initiator|responder> <safety_min_blocks> <observed_margin_blocks>
//   coord_gate apply  <logfile> <EventName>
//   coord_gate state  <logfile>
//
// Exit 0 + "OK <State> | next=<action>" when accepted; exit 1 + "REJECT <error>" when the
// Coordinator refuses (out-of-order event, bad timeout order, terminal-state violation, ...).
#include "sost/atomic_swap_coordinator.h"
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <cstdio>
using namespace sost::atomic_swap::coordinator;

static Event evFromName(const std::string& n, bool& ok){
  ok=true;
  if(n=="MarkSostLockSeen")            return Event::MarkSostLockSeen;
  if(n=="MarkCounterpartyLockSeen")    return Event::MarkCounterpartyLockSeen;
  if(n=="MarkPreimageKnown")           return Event::MarkPreimageKnown;
  if(n=="MarkSostClaimSeen")           return Event::MarkSostClaimSeen;
  if(n=="MarkCounterpartyClaimSeen")   return Event::MarkCounterpartyClaimSeen;
  if(n=="MarkSostRefundSeen")          return Event::MarkSostRefundSeen;
  if(n=="MarkCounterpartyRefundSeen")  return Event::MarkCounterpartyRefundSeen;
  if(n=="MarkTimeoutReached")          return Event::MarkTimeoutReached;
  if(n=="MarkFailure")                 return Event::MarkFailure;
  ok=false; return Event::MarkFailure;
}

// log format: line 1 = "role safety_min observed_margin"; subsequent lines = accepted event names
static bool loadParams(std::ifstream& f, SwapParams& p){
  std::string line; if(!std::getline(f,line)) return false;
  std::istringstream is(line); std::string role; long smin=6, obs=0, rafter=0;
  is>>role>>smin>>obs>>rafter;
  p.role = (role=="responder")?Role::Responder:Role::Initiator;
  p.safety_margin_min_blocks = smin;
  p.observed_safety_margin_blocks = obs;
  p.sost_refund_opens_after_counterparty = (rafter!=0);
  return true;
}

int main(int argc,char**argv){
  if(argc<3){ fprintf(stderr,"usage: create|apply|state <logfile> ...\n"); return 2; }
  std::string mode=argv[1], logf=argv[2];

  if(mode=="create"){
    if(argc<7){ fprintf(stderr,"create <log> <role> <smin> <obs> <refund_after_cp:1|0>\n"); return 2; }
    std::ofstream o(logf, std::ios::trunc);
    o<<argv[3]<<" "<<argv[4]<<" "<<argv[5]<<" "<<argv[6]<<"\n";
    o.close();
    // verify it constructs
    SwapParams p; { std::ifstream f(logf); loadParams(f,p); }
    Coordinator c; auto r=c.CreateSession(p);
    if(!r.ok){ printf("REJECT %s\n", r.error.c_str()); return 1; }
    printf("OK %s | next=%s | timeout_order_valid=%d\n",
           Coordinator::StateName(c.current_state()), c.next_safe_action().c_str(), c.timeout_order_valid());
    return 0;
  }

  // rebuild coordinator by replay
  SwapParams p; std::vector<std::string> prior;
  { std::ifstream f(logf); if(!loadParams(f,p)){ fprintf(stderr,"no session\n"); return 2; }
    std::string ev; while(std::getline(f,ev)){ if(!ev.empty()) prior.push_back(ev); } }
  Coordinator c; auto cr=c.CreateSession(p);
  if(!cr.ok){ printf("REJECT create: %s\n", cr.error.c_str()); return 1; }
  for(auto& e: prior){ bool ok; Event ev=evFromName(e,ok); if(ok) c.Apply(ev); }

  if(mode=="state"){
    printf("OK %s | next=%s | preimage_known=%d | risk=%zu\n",
           Coordinator::StateName(c.current_state()), c.next_safe_action().c_str(),
           c.preimage_known(), c.risk_flags().size());
    return 0;
  }
  if(mode=="apply"){
    if(argc<4){ fprintf(stderr,"apply <log> <EventName>\n"); return 2; }
    bool ok; Event ev=evFromName(argv[3],ok);
    if(!ok){ printf("REJECT unknown event %s\n", argv[3]); return 1; }
    auto r=c.Apply(ev);
    if(!r.ok){ printf("REJECT %s (state=%s)\n", r.error.c_str(), Coordinator::StateName(c.current_state())); return 1; }
    // persist accepted event
    std::ofstream o(logf, std::ios::app); o<<argv[3]<<"\n"; o.close();
    printf("OK %s | next=%s\n", Coordinator::StateName(c.current_state()), c.next_safe_action().c_str());
    return 0;
  }
  fprintf(stderr,"unknown mode\n"); return 2;
}
