// ============================================================================
// V16 (#30,000) — the two conditional DTD-normal gates.
//
//   cooldown  : still applied, EXCEPT when applying it would leave the draw with
//               nobody at all. On a chain with one or two producers the 6-block
//               exclusion silently switched the DTD off; from V16 it yields.
//   dominance : the 10%/288 gate is armed only at >= DTD_DOMINANCE_MIN_MINERS
//               distinct miners in the window. Below that, "dominance" has no
//               meaning and the gate would exclude the only miners keeping the
//               chain alive.
//
// Every case is asserted BOTH at a post-V16 height and at a pre-V16 height, so a
// regression that leaks the new behaviour into historical replay fails here.
// ============================================================================
#include "sost/lottery.h"
#include "sost/params.h"
#include <cstdio>
#include <vector>
using namespace sost;
using namespace sost::lottery;

static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){printf("  PASS: %s\n",m);g_pass++;} else {printf("  *** FAIL: %s [%s:%d]\n",m,__FILE__,__LINE__);g_fail++;} }while(0)

static PubKeyHash mk(uint8_t s){ PubKeyHash p{}; for(size_t i=0;i<p.size();++i)p[i]=(uint8_t)(s^(i*11)); return p; }
static LotteryMinedBlockView blk(int64_t h,const PubKeyHash&m){ LotteryMinedBlockView b; b.height=h; b.miner_pkh=m; return b; }
static bool has(const std::vector<LotteryEligibilityEntry>&v,const PubKeyHash&p){ for(auto&e:v) if(e.pkh==p) return true; return false; }
static std::vector<LotteryEligibilityEntry> run(const std::vector<LotteryMinedBlockView>&h,int64_t height){
    return compute_lottery_eligibility_set(h,height,PubKeyHash{},lottery_exclusion_window_at(height));
}

// One miner owns every block of the recency window, including the last 6.
static std::vector<LotteryMinedBlockView> sole_miner(int64_t h,const PubKeyHash&m,int64_t n){
    std::vector<LotteryMinedBlockView> v;
    for(int64_t i=1;i<=n;++i) v.push_back(blk(h-i,m));
    return v;
}

int main(){
    const int64_t H16 = DTD_V16_ELIGIBILITY_HEIGHT + 500;   // post-V16
    const int64_t H15 = DTD_V16_ELIGIBILITY_HEIGHT - 500;   // pre-V16, post-V15
    const PubKeyHash SOLO=mk(1);

    printf("== cooldown yields when it would empty the set ==\n");
    {
        auto hist = sole_miner(H16, SOLO, 200);
        auto e = run(hist,H16);
        TEST("V16: single miner of the last 6 blocks IS eligible", has(e,SOLO));
        TEST("V16: the set is exactly that one miner", e.size()==1);
    }
    {
        // Same shape below the activation height: the old rules stand and the draw
        // is empty, which is precisely the behaviour V16 fixes.
        auto hist = sole_miner(H15, SOLO, 200);
        auto e = run(hist,H15);
        TEST("pre-V16: same single miner is EXCLUDED (cooldown, unchanged)", !has(e,SOLO));
    }
    {
        // The cooldown must NOT yield when somebody else is still eligible: the
        // relaxation is a floor, not a repeal.
        const PubKeyHash OTHER=mk(2);
        auto hist = sole_miner(H16, SOLO, 20);
        hist.push_back(blk(H16-50, OTHER));           // outside the last 6, inside 288
        auto e = run(hist,H16);
        TEST("V16: cooldown STILL excludes the recent miner when another qualifies", !has(e,SOLO));
        TEST("V16: the other miner is the eligible one", has(e,OTHER) && e.size()==1);
    }

    printf("== dominance is armed only with enough distinct miners ==\n");
    {
        // 10 distinct miners: below DTD_DOMINANCE_MIN_MINERS, so no gate. Each holds
        // ~10% of the window and would be excluded under the unconditional rule.
        std::vector<LotteryMinedBlockView> hist;
        for(int i=0;i<10;i++) for(int k=0;k<20;k++) hist.push_back(blk(H16-10-(i*20+k), mk((uint8_t)(50+i))));
        auto e = run(hist,H16);
        TEST("V16: with 10 miners the gate is NOT armed -> all eligible", e.size()==10);
    }
    {
        // 11 distinct miners: gate armed. One of them owns 40% of the window and must
        // be excluded; the rest stay in.
        std::vector<LotteryMinedBlockView> hist;
        const PubKeyHash BIG=mk(90);
        for(int k=0;k<100;k++)  hist.push_back(blk(H16-10-k, BIG));          // ~40% of 288
        for(int i=0;i<10;i++) for(int k=0;k<5;k++)
            hist.push_back(blk(H16-120-(i*5+k), mk((uint8_t)(60+i))));
        auto e = run(hist,H16);
        TEST("V16: with 11 miners the gate IS armed -> dominant excluded", !has(e,BIG));
        TEST("V16: the small miners remain eligible", e.size()==10);
    }
    {
        // Pre-V16 the gate is unconditional: 10 miners, each ~10%, all excluded.
        std::vector<LotteryMinedBlockView> hist;
        for(int i=0;i<10;i++) for(int k=0;k<20;k++) hist.push_back(blk(H15-10-(i*20+k), mk((uint8_t)(50+i))));
        auto e = run(hist,H15);
        TEST("pre-V16: gate unconditional -> 10 miners at ~10% excluded", e.empty());
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
