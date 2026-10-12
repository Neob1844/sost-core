// Regression test for the fail-closed time-lock filter in Wallet::select_coins (review point D):
// a BOND/ESCROW-locked UTXO must NEVER be selected when the chain height is unknown (< 0).
#include "sost/wallet.h"
#include <cstdio>
using namespace sost;
static int PASS=0, FAIL=0;
#define CHECK(c,msg) do{ if(c){PASS++;} else {FAIL++; printf("  [FAIL] %s\n",msg);} }while(0)

static WalletUTXO mk(const PubKeyHash& pkh, int64_t amt, uint64_t lock){
    WalletUTXO u{}; u.amount=amt; u.pkh=pkh; u.output_type=0x00; u.height=1; u.spent=false; u.lock_until=lock; return u;
}
int main(){
    Wallet w; auto k = w.generate_key("t");
    const int64_t SOST=100000000;
    // one LOCKED utxo (unlocks at height 1000) and one FREE utxo
    std::vector<WalletUTXO> uns = { mk(k.pkh, 100*SOST, 1000), mk(k.pkh, 5*SOST, 0) };

    // chain_height UNKNOWN (-1): locked must be excluded -> only the 5-SOST free one is spendable.
    auto r1 = w.select_coins(uns, 3*SOST, nullptr, -1, 10);
    CHECK(r1.ok, "D unknown-height: can still fund from the FREE utxo");
    CHECK(r1.total_in==5*SOST, "D unknown-height: only FREE utxo used, LOCKED excluded");

    // Need MORE than the free utxo, height unknown: must FAIL (never dip into the locked one).
    auto r2 = w.select_coins(uns, 50*SOST, nullptr, -1, 10);
    CHECK(!r2.ok, "D unknown-height: refuses to spend LOCKED funds (fail-closed)");

    // height 500 (< 1000): still locked -> same as above.
    auto r3 = w.select_coins(uns, 50*SOST, nullptr, 500, 10);
    CHECK(!r3.ok, "D height<lock: LOCKED still excluded");

    // height 1000 (>= lock_until): now unlocked -> can fund the 50.
    auto r4 = w.select_coins(uns, 50*SOST, nullptr, 1000, 10);
    CHECK(r4.ok && r4.total_in>=50*SOST, "D height>=lock: LOCKED becomes spendable");

    printf("LOCK-FAILCLOSED TESTS: PASS=%d FAIL=%d\n", PASS, FAIL);
    return FAIL?1:0;
}
