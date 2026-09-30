// Unit test — Draw verifiable winner selection (native_assets_modalities.h)
#include "sost/native_assets_modalities.h"
#include <cstdio>
#include <map>
#include <cassert>
using namespace sost;
using namespace sost::modalities;
static int fails=0;
#define CHECK(c,m) do{ if(!(c)){ printf("  FAIL: %s\n",m); ++fails;} else printf("  ok: %s\n",m);}while(0)

static Bytes32 mk(uint8_t seed){ Bytes32 b{}; for(int i=0;i<32;++i) b[i]=(uint8_t)(seed*31+i); return b; }

int main(){
  printf("== Draw selection ==\n");
  Bytes32 bh = mk(7), did = mk(99);

  // 1. Deterministic: same inputs -> same index
  uint64_t a = draw_select_index(bh, did, 100);
  uint64_t b = draw_select_index(bh, did, 100);
  CHECK(a==b, "deterministic");

  // 2. In range [0,N)
  bool inrange=true; for(uint64_t n=1;n<=257;++n){ uint64_t i=draw_select_index(bh,did,n); if(i>=n){inrange=false;break;} }
  CHECK(inrange, "always in [0,N)");

  // 3. N=1 -> 0
  CHECK(draw_select_index(bh,did,1)==0, "single participant -> index 0");

  // 4. Different block hash -> generally different winner (entropy sensitivity)
  uint64_t x = draw_select_index(mk(7), did, 1000);
  uint64_t y = draw_select_index(mk(8), did, 1000);
  CHECK(x!=y, "block-hash change moves winner");

  // 5. Different draw_id -> independent selection (domain separation)
  uint64_t p = draw_select_index(bh, mk(1), 1000);
  uint64_t q = draw_select_index(bh, mk(2), 1000);
  CHECK(p!=q, "draw_id domain separation");

  // 6. Distribution sanity: vary block hash over 6000 draws, N=10, each bucket >0
  std::map<uint64_t,int> hist;
  for(int s=0;s<6000;++s) hist[draw_select_index(mk((uint8_t)s), did, 10)]++;
  bool all_hit=true; int mn=1e9,mx=0;
  for(uint64_t k=0;k<10;++k){ int c=hist[k]; if(c==0)all_hit=false; mn=std::min(mn,c); mx=std::max(mx,c);}
  CHECK(all_hit, "all 10 buckets hit");
  CHECK(mx < mn*3, "roughly uniform (max<3x min)");
  printf("  buckets: "); for(uint64_t k=0;k<10;++k) printf("%d ",hist[k]); printf("\n");

  // 7. Canonical ordering sorts by txid ascending
  std::vector<Hash256> v = { mk(5), mk(1), mk(9), mk(3) };
  draw_canonical_order(v);
  bool sorted=true; for(size_t i=1;i<v.size();++i) if(!(std::lexicographical_compare(v[i-1].begin(),v[i-1].end(),v[i].begin(),v[i].end()))) sorted=false;
  CHECK(sorted, "canonical order ascending by txid");

  printf(fails? "\nRESULT: %d FAIL\n":"\nRESULT: ALL PASS\n", fails);
  return fails?1:0;
}
