#include "sost/params.h"
#include <cstdio>
using namespace sost;
int main(){
  ACTIVE_PROFILE = Profile::MAINNET;
  printf("MAINNET consensus heights:\n");
  printf("  V15_HEIGHT=%lld  HIST_JACKPOT_FIRST_HEIGHT=%lld  cadence=%lld  V2_HEIGHT=%lld\n",
    (long long)V15_HEIGHT,(long long)HIST_JACKPOT_FIRST_HEIGHT,(long long)HIST_JACKPOT_CADENCE_BLOCKS,(long long)HIST_JACKPOT_V2_HEIGHT);
  long long hs[]={29899,29900,29999,30000,30001,30185,30186,30187,30474};
  printf("  height   is_jackpot  is_v2_height  is_v2_jackpot(both)\n");
  for(long long h:hs){
    bool jp=is_hist_jackpot_height(h), v2=is_hist_jackpot_v2_height(h);
    printf("  %-8lld %-11s %-13s %s\n",h, jp?"YES":"no", v2?"YES":"no", (jp&&v2)?"*** V2 JACKPOT ***":"");
  }
  return 0;
}
