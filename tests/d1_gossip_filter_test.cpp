// d1_gossip_filter_test — locks the SSRF/DNS gossip-screening policy (Gate 6 fix).
#include "sost/p2p_addr_filter.h"
#include <cstdio>
#include <string>
using sost::p2p_gossip_target_ok;
static int fails=0;
int main(){
  // allow_private=true (devnet): everything that is syntactically anything passes (lab uses loopback)
  if(!p2p_gossip_target_ok("127.0.0.1", true)){ printf("FAIL devnet loopback\n"); ++fails; }
  if(!p2p_gossip_target_ok("10.9.9.9", true)){ printf("FAIL devnet private\n"); ++fails; }
  // allow_private=false (mainnet/testnet): PUBLIC literals pass
  if(!p2p_gossip_target_ok("8.8.8.8", false)){ printf("FAIL public 8.8.8.8\n"); ++fails; }
  if(!p2p_gossip_target_ok("1.2.3.4", false)){ printf("FAIL public 1.2.3.4\n"); ++fails; }
  if(!p2p_gossip_target_ok("203.0.113.5", false)){ printf("FAIL public 203.0.113.5\n"); ++fails; }
  // ... and NON-routable / private / metadata / CGNAT / malformed are REJECTED
  const char* bad[]={
    "127.0.0.1","127.255.255.255","10.0.0.5","10.255.1.1","172.16.0.1","172.31.255.1",
    "192.168.1.1","169.254.169.254","100.64.0.1","100.127.1.1","0.0.0.0","224.0.0.1",
    "239.1.1.1","240.0.0.1","255.255.255.255",
    "evil.attacker.com","localhost","not-an-ip","::1","2001:db8::1","",
    "1.2.3.4:19333" /* host field should be split by caller; raw with port is not a literal */
  };
  for(const char* b: bad){
    if(p2p_gossip_target_ok(b, false)){ printf("FAIL: should REJECT '%s'\n", b); ++fails; }
  }
  // boundary: 172.15 and 172.32 are PUBLIC (outside /12); 100.63 and 100.128 are public
  if(!p2p_gossip_target_ok("172.15.0.1", false)){ printf("FAIL 172.15 public\n"); ++fails; }
  if(!p2p_gossip_target_ok("172.32.0.1", false)){ printf("FAIL 172.32 public\n"); ++fails; }
  if(!p2p_gossip_target_ok("100.63.0.1", false)){ printf("FAIL 100.63 public\n"); ++fails; }
  if(!p2p_gossip_target_ok("100.128.0.1", false)){ printf("FAIL 100.128 public\n"); ++fails; }
  if(fails==0) printf("d1_gossip_filter_test: ALL PASS\n");
  return fails?1:0;
}
