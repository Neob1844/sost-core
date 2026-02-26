#include "sost/wallet.h"
#include "sost/emission.h"
#include <cstdio>
#include <cstring>
#include <unistd.h>
using namespace sost;
static int pass=0,fail=0;
#define T(n,c) do{if(c){pass++;printf("  PASS: %s\n",n);}else{fail++;printf("  FAIL: %s\n",n);}}while(0)

int main() {
    printf("SOST Chunk 6 Tests - Wallet\n===========================\n");
    Wallet w;
    auto k1 = w.generate_key();
    T("key generated", !k1.addr.empty());
    T("addr starts sost1", k1.addr.substr(0,5) == "sost1");
    T("addr length=45", k1.addr.size() == 45);
    auto k2 = w.generate_key();
    T("two keys different", k1.addr != k2.addr);
    T("addresses count=2", w.addresses().size() == 2);
    T("balance=0", w.balance() == 0);
    // Credit coinbase
    Bytes32 bid{}; bid.fill(0x42);
    int64_t sub = sost_subsidy_stocks(0);
    w.credit_coinbase(0, sub, bid);
    T("balance after coinbase", w.balance() == sub);
    T("utxos count=1", w.utxos().size() == 1);
    // Second coinbase
    Bytes32 bid2{}; bid2.fill(0x43);
    w.credit_coinbase(1, sub, bid2);
    T("balance after 2 coinbases", w.balance() == 2*sub);
    // Create tx
    auto tx = w.create_tx("sost1aabbccdd00112233445566778899aabbccddeeff", sub/2, 1000);
    T("tx has txid", !is_zero(tx.txid));
    T("tx has outputs", tx.outs.size() >= 1);
    T("tx fee=1000", tx.fee == 1000);
    // Sign/verify
    Bytes32 h{}; h.fill(0xAA);
    auto sig = sign_hash(k1.priv, h);
    T("sig not zero", !is_zero(sig));
    T("sig deterministic", sign_hash(k1.priv, h) == sig);
    // Save/load
    w.save("/tmp/test_wallet.dat");
    Wallet w2;
    T("load ok", w2.load("/tmp/test_wallet.dat"));
    T("loaded keys", w2.addresses().size() == 2);
    T("loaded addr match", w2.default_address() == k1.addr);
    unlink("/tmp/test_wallet.dat");
    printf("\n===========================\nResults: %d passed, %d failed\n", pass, fail);
    return fail>0?1:0;
}
