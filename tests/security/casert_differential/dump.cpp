// Differential dump: exercise the REAL sost::casert_next_bitsq over a systematic
// vector space for the ACTIVE regime (next_height >= 5270, incl. V12 slingshot).
// Emits CSV: kind,p1,p2,prev,height,elapsed,result  (Python recomputes result independently).
#include "sost/pow/casert.h"
#include "sost/params.h"
#include "sost/types.h"
#include <cstdio>
#include <vector>
using namespace sost;

// build a 289-block chain (288 intervals) from an interval rule, last block powDiffQ=prev
static std::vector<BlockMeta> mkchain(int kind, int64_t p1, int64_t p2, uint32_t prev) {
    std::vector<BlockMeta> c;
    int N = 289;
    int64_t t = 1000000; // arbitrary base
    for (int i = 0; i < N; ++i) {
        BlockMeta b{};
        if (i == 0) { b.time = t; }
        else {
            int64_t iv = (kind == 0) ? p1 : ((i % 2 == 1) ? p1 : p2);
            t += iv;
            b.time = t;
        }
        b.powDiffQ = prev;      // constant history diff; last one is what prev_bitsq reads
        b.height = i;
        b.profile_index = 0;
        c.push_back(b);
    }
    return c;
}

int main() {
    printf("kind,p1,p2,prev,height,elapsed,result\n");
    // prev_bitsq samples: MIN, small, genesis, mid, near MAX
    uint32_t prevs[] = {MIN_BITSQ, MIN_BITSQ+50, 200000u, GENESIS_BITSQ, 3000000u, MAX_BITSQ-100u, MAX_BITSQ};
    // heights: active (>=5270, <V12) and V12 (>=7350) for slingshot
    int64_t heights[] = {5270, 6000, 7349, 7350, 20000, 29900, 30000, 40000};
    // interval values covering all dev tiers + clamps
    int64_t ivs[] = {1, 300, 570, 585, 600, 615, 630, 660, 720, 840, 1000, 2000, 90000};
    // slingshot elapsed bands (strict > thresholds 1200/1800/3600/7200/10800)
    int64_t elapseds[] = {0, 600, 601, 1200, 1201, 1800, 1801, 3600, 3601, 7200, 7201, 10800, 10801, 50000};

    // Family A: constant intervals
    for (uint32_t prev : prevs)
      for (int64_t h : heights)
        for (int64_t iv : ivs)
          for (int64_t el : elapseds) {
            auto c = mkchain(0, iv, 0, prev);
            int64_t now = c.back().time + el;
            uint32_t r = casert_next_bitsq(c, h, now);
            printf("0,%lld,0,%u,%lld,%lld,%u\n", (long long)iv, prev, (long long)h, (long long)el, r);
          }
    // Family B: two-value intervals (avg truncation)
    int64_t pairs[][2] = {{300,900},{570,630},{599,601},{1,86400},{500,700},{610,610}};
    for (uint32_t prev : prevs)
      for (int64_t h : heights)
        for (auto& pr : pairs)
          for (int64_t el : elapseds) {
            auto c = mkchain(1, pr[0], pr[1], prev);
            int64_t now = c.back().time + el;
            uint32_t r = casert_next_bitsq(c, h, now);
            printf("1,%lld,%lld,%u,%lld,%lld,%u\n", (long long)pr[0], (long long)pr[1], prev, (long long)h, (long long)el, r);
          }
    return 0;
}
