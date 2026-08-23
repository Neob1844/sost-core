// V15 DTD recency gate tests.
//   dtd_recency_window_at(height): 0 pre-V15 · 5000 normal · 2016 jackpot.
//   compute_lottery_eligibility_set applies it (miner<->validator parity: one predicate).
// Pure functions; no Schnorr dependency. Gate anchored at V15_HEIGHT (mainnet 25000);
// pre-V15 replay is byte-identical (window == 0).
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
// fill [h-40, h-11] with 30 distinct filler miners (inside the 288 dominance window,
// outside the last-6 cooldown) so no specific miner is anti-dominance-flagged.
static void fill(std::vector<LotteryMinedBlockView>&hist,int64_t h){
    for(int i=0;i<30;i++) hist.push_back(blk(h-40+i, mk((uint8_t)(100+i))));
}
int main(){
    printf("== dtd_recency_window_at ==\n");
    TEST("pre-V15 (24999) window 0", dtd_recency_window_at(24999)==0);
    TEST("post-V15 normal (25010) window 5000", dtd_recency_window_at(25010)==5000);
    TEST("first jackpot (25290) window 2016", dtd_recency_window_at(25290)==2016);
    TEST("post-jackpot normal (25291) window 5000", dtd_recency_window_at(25291)==5000);
    TEST("is_hist_jackpot_height(25290) true", is_hist_jackpot_height(25290));

    const PubKeyHash RECENT=mk(1), MID=mk(2), OLD=mk(3);

    printf("== pre-V15 height: recency is a NO-OP ==\n");
    {
        int64_t h=24000; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-10,   RECENT));  // recent
        hist.push_back(blk(h-3000, MID));     // 3000 ago
        hist.push_back(blk(h-9000, OLD));     // 9000 ago (all >=7100 sbpow ok: 24000-9000=15000)
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("pre-V15: recent eligible", has(e,RECENT));
        TEST("pre-V15: 3000-ago eligible (no recency)", has(e,MID));
        TEST("pre-V15: 9000-ago eligible (no recency)", has(e,OLD));
    }

    printf("== post-V15 NORMAL block (window 5000) ==\n");
    {
        int64_t h=25010; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-10,   RECENT));  // within 5000 & 2016
        hist.push_back(blk(h-3000, MID));     // within 5000, outside 2016
        hist.push_back(blk(h-6000, OLD));     // outside 5000 (25010-6000=19010, sbpow ok >=7100)
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("normal: recent (10 ago) ELIGIBLE", has(e,RECENT));
        TEST("normal: 3000-ago ELIGIBLE (<5000)", has(e,MID));
        TEST("normal: 6000-ago EXCLUDED (>5000)", !has(e,OLD));
    }

    printf("== post-V15 JACKPOT block (stricter window 2016) ==\n");
    {
        int64_t h=25290; std::vector<LotteryMinedBlockView> hist; fill(hist,h);
        hist.push_back(blk(h-10,   RECENT));  // within 2016
        hist.push_back(blk(h-2290, MID));     // 2290 ago: within 5000 but OUTSIDE 2016
        auto e=compute_lottery_eligibility_set(hist,h,PubKeyHash{},lottery_exclusion_window_at(h));
        TEST("jackpot: recent (10 ago) ELIGIBLE", has(e,RECENT));
        TEST("jackpot: 2290-ago EXCLUDED (>2016, though <5000)", !has(e,MID));
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
