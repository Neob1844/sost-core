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

    printf("== EXACT activation boundary: #29,999 vs #30,000 ==\n");
    {
        const int64_t A = DTD_V16_ELIGIBILITY_HEIGHT;      // 30,000
        TEST("window at A-1 is the V15 one (5000)", dtd_recency_window_at(A-1)==DTD_RECENCY_WINDOW);
        TEST("window at A   is the V16 one (288)",  dtd_recency_window_at(A)==DTD_RECENCY_WINDOW_V16);

        // One address whose only block is 1,000 ago: inside V15's 5,000, outside V16's 288.
        const PubKeyHash OLD=mk(11);
        auto mkhist=[&](int64_t h){ std::vector<LotteryMinedBlockView> v;
            for(int i=0;i<30;i++) v.push_back(blk(h-40+i, mk((uint8_t)(100+i))));   // 30 fillers, inside 288
            v.push_back(blk(h-1000,OLD)); return v; };
        TEST("#29,999: 1000-ago ELIGIBLE (5000 window)",  has(run(mkhist(A-1),A-1),OLD));
        TEST("#30,000: 1000-ago EXCLUDED (288 window)",  !has(run(mkhist(A),  A),  OLD));

        // Recency edge: exactly at the window rim. last_mined < height - 288 is excluded,
        // so height-288 is IN and height-289 is OUT.
        const PubKeyHash RIM_IN=mk(12), RIM_OUT=mk(13);
        std::vector<LotteryMinedBlockView> h2;
        for(int i=0;i<30;i++) h2.push_back(blk(A-40+i, mk((uint8_t)(100+i))));
        h2.push_back(blk(A-288,RIM_IN));
        h2.push_back(blk(A-289,RIM_OUT));
        auto e2=run(h2,A);
        TEST("#30,000: block at h-288 is INSIDE the window",  has(e2,RIM_IN));
        TEST("#30,000: block at h-289 is OUTSIDE the window", !has(e2,RIM_OUT));
    }

    printf("== miner-count matrix: 1 / 2 / 10 / 11 distinct miners ==\n");
    {
        const int64_t A = DTD_V16_ELIGIBILITY_HEIGHT;
        auto equal_share=[&](int64_t h,int n){                 // n miners, 288 blocks, equal share
            std::vector<LotteryMinedBlockView> v;
            for(int k=0;k<288;k++) v.push_back(blk(h-1-k, mk((uint8_t)(200+(k%n)))));
            return v; };
        // 1 miner: 100% of the window, and miner of the last 6 -> both gates would kill it.
        auto e1=run(equal_share(A,1),A);
        TEST("V16 · 1 miner  -> 1 eligible (both relaxations fire)", e1.size()==1);
        // 2 miners: 50% each, both mined inside the last 6.
        auto e2=run(equal_share(A,2),A);
        TEST("V16 · 2 miners -> 2 eligible (dominance off, cooldown yields)", e2.size()==2);
        // 10 miners round-robin over 288: eight hold 29 blocks (>= the 10% threshold of
        // 28.8) and two hold 28. Post-V16 the gate is NOT armed, so all 10 are candidates
        // and only the cooldown bites (the 6 most recent blocks belong to 6 distinct
        // miners) -> 4. Pre-V16 the gate IS unconditional, so the eight dominant ones are
        // dropped and only the two 28-block miners survive -> 2. The difference between
        // 4 and 2 is exactly, and only, the arming rule.
        auto e10=run(equal_share(A,10),A);
        TEST("V16 · 10 miners -> gate NOT armed, cooldown applies, 4 eligible", e10.size()==4);
        auto e10old=run(equal_share(A-1,10),A-1);
        TEST("#29,999 · 10 miners -> gate armed unconditionally, 2 eligible", e10old.size()==2);
        // 11 miners: gate armed. 288/11 = 26.2 blocks = 9.09% < 10% -> nobody is dominant,
        // but the cooldown now bites the 6 most recent miners because others remain.
        auto e11=run(equal_share(A,11),A);
        TEST("V16 · 11 miners -> gate armed, cooldown applies, 5 eligible", e11.size()==5);
        // Same 11-miner shape below the fork: dominance unconditional, still 9.09% each,
        // so the only difference must be nil -> proves the gate arming is the ONLY change.
        auto e11old=run(equal_share(A-1,11),A-1);
        TEST("#29,999 · 11 miners -> identical outcome (5 eligible)", e11old.size()==5);
    }

    printf("== Jackpot V2 constants are the frozen V16.1 ones ==\n");
    {
        TEST("JACKPOT_V2_POW_WINDOW == 2016", JACKPOT_V2_POW_WINDOW==2016);
        TEST("JACKPOT_V2_MIN_BLOCKS == 3",    JACKPOT_V2_MIN_BLOCKS==3);
        TEST("V2 activation == 30,000",       HIST_JACKPOT_V2_HEIGHT==30000);
        TEST("#30,000 is NOT a jackpot height",  !is_hist_jackpot_height(30000));
        TEST("#30,186 IS the first V2 jackpot",   is_hist_jackpot_height(30186) && is_hist_jackpot_v2_height(30186));
        TEST("#29,898 is the last pre-V2 jackpot", is_hist_jackpot_height(29898) && !is_hist_jackpot_v2_height(29898));
        TEST("cadence unchanged at 288", HIST_JACKPOT_CADENCE_BLOCKS==288);
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
