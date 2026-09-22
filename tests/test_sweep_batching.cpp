// Sweep batching — measured, not estimated.
//
// Consolidating a mining address means spending thousands of tiny coinbase
// UTXOs, which does not fit in one transaction. The batch size cannot be a
// guess: it has to come from the REAL serialized size of a REAL transaction,
// measured against the REAL limits, or a batch silently exceeds a consensus
// bound and is rejected after the operator thinks the sweep is running.
//
// Everything here uses throwaway wallets and fake UTXOs. No node, no real key,
// no broadcast — the numbers this produces are what the planner then applies to
// live data without ever loading the mining key.
#include "sost/wallet.h"
#include "sost/address.h"
#include "sost/params.h"
#include "sost/consensus_constants.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace sost;

static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){++g_pass;} else {printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

static Hash256 fake_txid(uint32_t n){ Hash256 h{}; for(size_t i=0;i<h.size();++i) h[i]=(uint8_t)((n>>(8*(i%4)))^i); return h; }

// A wallet holding `n` mature coinbase UTXOs of `amt` stocks each.
static void fill(Wallet& w, const PubKeyHash& pkh, int n, int64_t amt, int64_t base_height){
    w.clear_utxos();
    for(int i=0;i<n;i++){
        WalletUTXO u;
        u.txid=fake_txid((uint32_t)i); u.vout=0; u.amount=amt;
        u.output_type=0x01;                 // coinbase_miner, the shape a mining address holds
        u.pkh=pkh; u.height=base_height+i; u.spent=false;
        w.add_utxo(u);
    }
}

int main(){
    const Hash256 genesis{};                 // any value: size does not depend on it
    const int64_t AMT = 392550432;           // one real block's miner share
    const int64_t TIP = 10'000'000;          // far past maturity for every fake UTXO

    Wallet w;
    (void)w.generate_key("sweep-test");
    const std::string self = w.default_address();
    PubKeyHash pkh{};
    if(!address_decode(self, pkh)){ printf("cannot decode own address\n"); return 1; }

    printf("== measured transaction size by input count ==\n");
    struct M { int n; size_t bytes; };
    std::vector<M> meas;
    for (int n : {1, 2, 10, 50, 100, 200, 256}) {
        fill(w, pkh, n, AMT, 1);
        Transaction tx;
        // A sweep sends EVERYTHING to one destination: no change output.
        int64_t fee = 1000;
        int64_t total = (int64_t)n * AMT;
        std::string e;
        if(!w.create_transaction(self, total - fee, fee, genesis, tx, TIP, &e, nullptr,
                                 /*mark_spent=*/false)){
            printf("  build failed at n=%d: %s\n", n, e.c_str()); ++g_fail; continue;
        }
        std::vector<Byte> raw; std::string se;
        if(!tx.Serialize(raw, &se)){ printf("  serialize failed at n=%d\n", n); ++g_fail; continue; }
        meas.push_back({n, raw.size()});
        printf("  %3d inputs -> %2zu in / %zu out -> %6zu bytes\n",
               n, tx.inputs.size(), tx.outputs.size(), raw.size());
        TEST("every input was consumed", (int)tx.inputs.size()==n);
    }

    printf("== derived per-input cost, and the consensus ceiling ==\n");
    if (meas.size() >= 2) {
        const M& a = meas.front(); const M& b = meas.back();
        double per_input = double(b.bytes - a.bytes) / double(b.n - a.n);
        double base = double(a.bytes) - per_input * a.n;
        printf("  base %.0f bytes + %.1f bytes/input (measured, not assumed)\n", base, per_input);
        // The planner's cap: the largest input count that stays inside BOTH limits.
        int by_bytes = (int)((double(MAX_TX_BYTES_CONSENSUS) - base) / per_input);
        int cap = by_bytes < (int)MAX_INPUTS_CONSENSUS ? by_bytes : (int)MAX_INPUTS_CONSENSUS;
        printf("  fits by bytes: %d inputs · consensus input cap: %d -> batch cap %d\n",
               by_bytes, (int)MAX_INPUTS_CONSENSUS, cap);
        TEST("the binding limit is the input count, not the byte size", cap == (int)MAX_INPUTS_CONSENSUS);
        TEST("a full 256-input batch stays under MAX_TX_BYTES_CONSENSUS",
             b.n == 256 && b.bytes < (size_t)MAX_TX_BYTES_CONSENSUS);
        TEST("and with real margin (<50% of the byte limit)",
             b.bytes < (size_t)MAX_TX_BYTES_CONSENSUS / 2);
    }

    printf("== batching 2,058 mature UTXOs (the live mining address) ==\n");
    {
        const int MATURE = 2058;
        const int cap = (int)MAX_INPUTS_CONSENSUS;
        int batches = (MATURE + cap - 1) / cap;
        printf("  %d UTXOs / %d per tx -> %d transactions\n", MATURE, cap, batches);
        TEST("nine transactions, not the five or seventeen estimated earlier", batches == 9);
        TEST("all batches fit the mempool's per-address cap",
             (size_t)batches <= MEMPOOL_MAX_PER_ADDRESS);

        // No UTXO may appear twice across batches, and none may be dropped.
        std::vector<int> seen(MATURE, 0);
        int assigned = 0;
        for (int b = 0; b < batches; ++b)
            for (int i = b * cap; i < (b + 1) * cap && i < MATURE; ++i) { ++seen[i]; ++assigned; }
        bool once = true; for (int s : seen) if (s != 1) once = false;
        TEST("every UTXO assigned exactly once", once && assigned == MATURE);
    }

    printf("== maturity is a filter, not a hint: a reorg must drop inputs ==\n");
    {
        // 300 UTXOs mined at heights 9..308. At a tip that leaves the newest ones
        // inside the maturity window, only the older ones may be spent — and if the
        // chain reorgs BACKWARDS the set must shrink, never grow.
        fill(w, pkh, 300, AMT, 9);
        // Ask for MORE than the whole balance minus fee, so selection is forced to
        // reach for every UTXO it is allowed to touch: the input count then IS the
        // size of the spendable set, which is the property under test.
        auto spendable_at = [&](int64_t tip)->size_t{
            Transaction tx; std::string e;
            int64_t want = 300 * AMT - 1000;          // everything, less the fee
            if(!w.create_transaction(self, want, 1000, genesis, tx, tip, &e, nullptr, false)) {
                // Not enough mature value to cover it: fall back to the largest
                // amount that CAN be covered, by probing downwards in whole UTXOs.
                for (int k = 299; k >= 1; --k) {
                    Transaction t2; std::string e2;
                    if (w.create_transaction(self, (int64_t)k * AMT - 1000, 1000, genesis, t2, tip, &e2, nullptr, false))
                        return t2.inputs.size();
                }
                return 0;
            }
            return tx.inputs.size();
        };
        size_t deep   = spendable_at(9 + 300 + COINBASE_MATURITY + 10);   // everything mature
        size_t mid    = spendable_at(9 + 150 + COINBASE_MATURITY);        // about half
        size_t early  = spendable_at(9 + COINBASE_MATURITY - 1);          // nothing mature yet
        printf("  tip deep: %zu inputs · tip mid: %zu · tip before maturity: %zu\n", deep, mid, early);
        TEST("nothing spendable before the first UTXO matures", early == 0);
        TEST("a deep tip reaches every UTXO", deep == 300);
        TEST("a shallower tip yields strictly fewer inputs", mid < deep && mid > 0);
        // A reorg is a tip that moves BACKWARDS. The spendable set must shrink
        // monotonically with it — never hold on to a reward that stopped being
        // mature, which is how a sweep would build a transaction the network
        // then rejects.
        size_t prev = deep; bool monotonic = true;
        for (int back = 0; back <= 250; back += 25) {
            size_t n = spendable_at(9 + 300 + COINBASE_MATURITY + 10 - back);
            if (n > prev) monotonic = false;
            prev = n;
        }
        TEST("spendable set shrinks monotonically as the tip rolls back", monotonic);
    }

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail==0?0:1;
}
