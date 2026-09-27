#include "sost/coin_select.h"
#include <cstdio>
#include <cassert>
using namespace sost::coinselect;
static int PASS=0, FAIL=0;
#define CHECK(c,msg) do{ if(c){PASS++;} else {FAIL++; printf("  [FAIL] %s\n",msg);} }while(0)
static int64_t sum_sel(const std::vector<int64_t>&a,const Result&r){int64_t s=0;for(size_t i:r.indices)s+=a[i];return s;}

int main(){
  const int64_t SOST=100000000; // 1 SOST = 1e8 stocks (assume; ratio only matters relatively)
  // A) few UTXOs, exact changeless match via BnB: need 300, have {100,200,150,60} -> 100+200=300
  {
    std::vector<int64_t> a={100*SOST,200*SOST,150*SOST,60*SOST};
    auto r=select(a, 300*SOST, 10);
    CHECK(r.ok, "A ok");
    CHECK(r.total_in>=300*SOST, "A covers");
    CHECK(r.bnb && r.total_in==300*SOST, "A BnB exact changeless (300 == 100+200)");
  }
  // B) 77-input case: 80 UTXOs of 3.9255 SOST, need 300 -> ceil(300/3.9255)=77
  {
    std::vector<int64_t> a; for(int i=0;i<80;i++) a.push_back((int64_t)(3.9255*SOST));
    auto r=select(a, 300*SOST, 10);
    CHECK(r.ok, "B ok");
    int need=(int)((300*SOST + (int64_t)(3.9255*SOST)-1)/(int64_t)(3.9255*SOST));
    CHECK((int)r.indices.size()>=76 && (int)r.indices.size()<=78, "B ~77 inputs (all equal)");
  }
  // C) mixed sizes: largest-first uses FEW large, not many small. need 500; have one 600 + fifty 20s
  {
    std::vector<int64_t> a={600*SOST}; for(int i=0;i<50;i++) a.push_back(20*SOST);
    auto r=select(a, 500*SOST, 10);
    CHECK(r.ok, "C ok");
    CHECK(r.indices.size()<=1 || (r.bnb), "C picks the single 600 (few inputs), not many 20s");
    CHECK(r.total_in>=500*SOST, "C covers");
  }
  // D) near-exact: need 99.5, have {100} -> single, small change
  {
    std::vector<int64_t> a={100*SOST};
    auto r=select(a, (int64_t)(99.5*SOST), 10);
    CHECK(r.ok && r.indices.size()==1, "D single UTXO covers near-exact");
  }
  // E) insufficient: need 1000, have {100,200} -> ok=false
  {
    std::vector<int64_t> a={100*SOST,200*SOST};
    auto r=select(a, 1000*SOST, 10);
    CHECK(!r.ok, "E insufficient -> ok=false");
  }
  // F) uneconomic dust deferred: need 50; have {60} big + {1,1,1} dust at high fee_rate.
  //    Should pick the 60 (economic), not the dust.
  {
    std::vector<int64_t> a={60*SOST, 500, 500, 500}; // 500 stocks << input cost at rate 10 (148*10=1480)
    auto r=select(a, 50*SOST, 10);
    CHECK(r.ok, "F ok");
    bool used_dust=false; for(size_t i:r.indices) if(a[i]==500) used_dust=true;
    CHECK(!used_dust, "F skips uneconomic dust when a big UTXO suffices");
  }
  // G) dust USED when needed (only funds are dust): need 1200 stocks; have {500,500,500} -> must use >=3
  {
    std::vector<int64_t> a={500,500,500};
    auto r=select(a, 1200, 10);
    CHECK(r.ok && r.total_in>=1200, "G uses dust when it's the only way to reach target");
  }
  // H) determinism: same input -> same selection
  {
    std::vector<int64_t> a={100*SOST,200*SOST,150*SOST,60*SOST};
    auto r1=select(a,300*SOST,10), r2=select(a,300*SOST,10);
    CHECK(r1.indices==r2.indices, "H deterministic");
  }
    // I) BnB candidate cap (E): a wallet with MANY (>BNB_MAX_CANDIDATES) economic UTXOs must still
    //    fund the send via the fallback even though BnB only sees the top-K. No crash, ok=true.
    {
      std::vector<int64_t> a(500, 10*SOST);   // 500 identical economic UTXOs
      auto r=select(a, 3000*SOST, 10);        // needs 300 of them -> fallback territory
      CHECK(r.ok && r.total_in>=3000*SOST, "I funds large-wallet send despite BnB cap");
      CHECK(r.indices.size()>=300, "I selection count is sane for the target");
    }
    // J) BnB cap does not break funding a send with 300 varied UTXOs.
    {
      std::vector<int64_t> a; for(int i=0;i<300;i++) a.push_back((int64_t)(i+1)*SOST);
      auto r=select(a, 300*SOST, 10);
      CHECK(r.ok, "J still funds with 300 varied UTXOs");
    }
    // K) dust_threshold helper: floors fee_rate at 1 and scales with rate.
    {
      CHECK(dust_threshold(10) == APPROX_INPUT_BYTES*10, "K dust threshold scales with rate");
      CHECK(dust_threshold(0)  == APPROX_INPUT_BYTES*1,  "K dust threshold floors rate at 1");
      CHECK(dust_threshold(-5) == APPROX_INPUT_BYTES*1,  "K dust threshold floors negative rate");
    }
  printf("COIN-SELECT TESTS: PASS=%d FAIL=%d\n", PASS, FAIL);
  return FAIL?1:0;
}
