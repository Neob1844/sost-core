// DTD recency gate tests. V15: normal=5000, jackpot=20000. V16 (#30,000): 288 at every
// height, jackpot heights included. Pre-V16 heights must replay byte-identically.
//   dtd_recency_window_at(height): 0 pre-V15 · 10000 normal · 0 jackpot ("ever").
//   compute_lottery_eligibility_set applies it (one predicate -> miner<->validator parity).
// Height-gated at V15_HEIGHT; pre-V15 replay byte-identical (window 0).
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
static void fill(std::vector<LotteryMinedBlockView>&hist,int64_t h){ // 30 distinct fillers inside 288 dominance window, outside last-6 cooldown
    for(int i=0;i<30;i++) hist.push_back(blk(h-40+i, mk((uint8_t)(100+i))));
}
int main(){
    printf("== dtd_recency_window_at ==\n");
    TEST("pre-V15 (24999) window 0", dtd_recency_window_at(24999)==0);
    TEST("post-V15 normal (25010) window 5000", dtd_recency_window_at(25010)==5000);
    TEST("jackpot (25290) window 20000", dtd_recency_window_at(25290)==20000);
    TEST("post-jackpot normal (25291) window 5000", dtd_recency_window_at(25291)==5000);
    TEST("V16 normal (30010) window 288",  dtd_recency_window_at(30010)==DTD_RECENCY_WINDOW_V16);
    TEST("V16 jackpot (30186) window 288", dtd_recency_window_at(30186)==DTD_RECENCY_WINDOW_V16);

    const PubKeyHash RECENT=mk(1), MID=mk(2), OLD=mk(3);

    printf("== pre-V15 height: recency is a NO-OP ==\n");
    {
        int64_t h=24000; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-10,RECENT)); hist.push_back(blk(h-8000,MID)); hist.push_back(blk(h-15000,OLD));
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("pre-V15: 8000-ago eligible (no recency)", has(e,MID));
        TEST("pre-V15: 15000-ago eligible (no recency)", has(e,OLD));
    }

    printf("== post-V15 NORMAL block (window 10000) ==\n");
    {
        int64_t h=25010; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-10,RECENT));    // within 5000
        hist.push_back(blk(h-3000,MID));     // 3000 ago: within 5000 -> eligible
        hist.push_back(blk(h-8000,OLD));     // 8000 ago: OUTSIDE 5000 -> excluded (25010-8000=17010, sbpow ok >=7100)
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("normal: recent (10) ELIGIBLE", has(e,RECENT));
        TEST("normal: 3000-ago ELIGIBLE (<5000)", has(e,MID));
        TEST("normal: 8000-ago EXCLUDED (>5000)", !has(e,OLD));
    }

    printf("== JACKPOT block: broad window 20000 ==\n");
    {
        int64_t h=25290; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-2290,RECENT));   // within 20000 (and would have failed the old 2016 rule)
        hist.push_back(blk(h-15000,OLD));     // 15000 ago: within 20000 -> eligible
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("jackpot: 2290-ago ELIGIBLE (<20000)", has(e,RECENT));
        TEST("jackpot: 15000-ago ELIGIBLE (<20000)", has(e,OLD));
    }
    printf("== V16 (#30,000): recency is 288 at EVERY height, jackpot heights included ==\n");
    {
        // The wide jackpot window existed because the V15 jackpot paid the DTD winner.
        // From V16 the jackpot has its own winner, so the DTD-normal draw at a jackpot
        // height uses the same 288 window as any other block.
        int64_t h=45450; // (h-25290)=20160, %288==0 -> a real jackpot height, and >= 30000
        std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        const PubKeyHash A=mk(7), B=mk(8);
        hist.push_back(blk(h-100,A));    // 100 ago   -> inside 288
        hist.push_back(blk(h-15450,B));  // 15450 ago -> outside 288 (was ELIGIBLE pre-V16 under 20000)
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("V16 jackpot height: 100-ago ELIGIBLE (<288)", has(e,A));
        TEST("V16 jackpot height: 15450-ago EXCLUDED (288 applies, not 20000)", !has(e,B));
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
