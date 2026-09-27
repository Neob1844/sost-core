// Regression test for the txid byte-order helpers (removes the manual-reversal footgun).
#include "sost/atomic_swap_btc_signing.h"
#include <cstdio>
#include <array>
#include <string>
using namespace sost::atomic_swap::btc;
static int PASS=0, FAIL=0;
#define CHECK(c,msg) do{ if(c){PASS++;} else {FAIL++; printf("  [FAIL] %s\n",msg);} }while(0)

int main(){
  // A real bitcoin-cli DISPLAY txid (big-endian, 64 hex).
  std::string disp = "4fc3cbe40192dc1ab9adf523f0afbb2f436c792c94fb87be2cd38aa4f8395059";
  auto r = DisplayTxidToInternal(disp);
  CHECK(r.ok, "A display->internal ok");
  CHECK(r.bytes.size()==32, "A internal is 32 bytes");
  // internal must be the reverse of display: first internal byte == last display byte pair (0x59)
  CHECK(r.bytes.size()==32 && r.bytes[0]==0x59, "A internal[0] == display last byte (reversed)");
  CHECK(r.bytes.size()==32 && r.bytes[31]==0x4f, "A internal[31] == display first byte");

  // round-trip: internal -> display == original
  std::array<uint8_t,32> it{}; for(int i=0;i<32;i++) it[i]=r.bytes[i];
  std::string back = InternalTxidToDisplay(it);
  CHECK(back==disp, "A round-trip internal->display == original display");

  // uppercase input accepted, same result
  std::string up = disp; for(auto&c:up) if(c>='a'&&c<='f') c=c-'a'+'A';
  auto r2 = DisplayTxidToInternal(up);
  CHECK(r2.ok && r2.bytes==r.bytes, "B uppercase hex accepted, same internal");

  // validation: wrong length rejected
  CHECK(!DisplayTxidToInternal("dead").ok, "C too-short rejected");
  CHECK(!DisplayTxidToInternal(disp+"00").ok, "C too-long rejected");
  // validation: non-hex rejected
  std::string bad = disp; bad[0]='z';
  CHECK(!DisplayTxidToInternal(bad).ok, "C non-hex rejected");

  printf("TXID-ORDER TESTS: PASS=%d FAIL=%d\n", PASS, FAIL);
  return FAIL?1:0;
}
