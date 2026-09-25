#include <sost/subsidy.h>
#include <cstdio>
int main(){ long long h;
  while(scanf("%lld",&h)==1)
    printf("%lld %lld %lld\n", h, (long long)sost::sost_subsidy_stocks(h), (long long)sost::sost_cumulative_emission_stocks(h));
  return 0; }
