// V15 Historical DTD Jackpot — RUNTIME test using the REAL UtxoSet machinery.
// Proves the end-to-end UTXO effect the node relies on: a jackpot block, when
// connected via UtxoSet::ConnectBlock (the same call process_block makes at
// acceptance), actually MOVES coins — the reserve drops by the payout, the DTD
// winner is paid, supply is neutral — and DisconnectBlock (reorg) undoes it
// bit-exact. This complements the pure/validation tests in test_v15_jackpot.cpp.
//
// Note: this exercises the real ConnectBlock/DisconnectBlock (which do NOT verify
// signatures — they only spend inputs + add outputs), confirming the jackpot tx
// (no signature, fee 0) applies correctly at runtime.

#include "sost/jackpot.h"
#include "sost/utxo_set.h"
#include "sost/transaction.h"
#include <cstdio>

using namespace sost;
using namespace sost::jackpot;

static int g_pass = 0, g_fail = 0;
#define TEST(m,c) do{ if(c){printf("  PASS: %s\n",m);g_pass++;} \
    else {printf("  *** FAIL: %s  [%s:%d]\n",m,__FILE__,__LINE__);g_fail++;} }while(0)

static Bytes32 tid(uint8_t s){ Bytes32 t{}; for(size_t i=0;i<t.size();++i) t[i]=(uint8_t)(s^(i*7)); return t; }
static PubKeyHash pkh(uint8_t s){ PubKeyHash p{}; for(size_t i=0;i<p.size();++i) p[i]=(uint8_t)(s^(i*3)); return p; }
static int64_t bal(const UtxoSet& u, const PubKeyHash& a){
    int64_t s=0; for(const auto& kv : u.GetMap()) if(kv.second.pubkey_hash==a) s+=kv.second.amount; return s;
}

int main(){
    const int64_t U = 100000000LL;   // stocks per SOST
    PubKeyHash gold=pkh(0x11), popc=pkh(0x22), winner=pkh(0xAA), miner=pkh(0x33);

    UtxoSet uset;
    // Seed 60 Gold reserve UTXOs of 2 SOST each (120 SOST reserve).
    for (int i=0;i<60;++i){
        OutPoint op{tid((uint8_t)(0x40+i)), 0};
        UTXOEntry e; e.amount=2*U; e.pubkey_hash=gold; e.height=100+i; e.payload_len=0;
        std::string er; uset.AddUTXO(op, e, &er);
    }
    const int64_t reserve0 = bal(uset, gold);
    TEST("seeded reserve = 120 SOST", reserve0 == 120*U);
    TEST("winner starts at 0", bal(uset, winner) == 0);

    // Build the jackpot tx EXACTLY as the node/validator do (payout 100 from FIFO).
    auto res  = collect_reserve_utxos(uset.GetMap(), gold, popc);
    auto jr   = compute_jackpot(0, reserve_sum(res), /*has_winner*/true);
    TEST("computed payout = 100 SOST", jr.payout == 100*U);
    auto plan = plan_jackpot_spend(res, jr.payout);
    Transaction jtx = build_expected_jackpot_tx(plan, winner, gold);

    // Minimal coinbase txs[0] — needs a (null) coinbase input to serialize.
    Transaction cb; cb.tx_type = TX_TYPE_COINBASE;
    { TxInput cin; cin.prev_txid = Bytes32{}; cin.prev_index = 0xFFFFFFFFu; cb.inputs.push_back(cin); }
    { TxOutput o; o.amount=3*U; o.type=OUT_COINBASE_MINER; o.pubkey_hash=miner; cb.outputs.push_back(o); }

    std::vector<Transaction> blk = { cb, jtx };

    // ---- CONNECT (== what process_block does at acceptance) ----
    BlockUndo undo; std::string cerr;
    bool ok = uset.ConnectBlock(blk, 20286, undo, &cerr);
    TEST("ConnectBlock accepts the jackpot block", ok);
    if(!ok) printf("     ConnectBlock err: %s\n", cerr.c_str());

    TEST("reserve dropped by exactly the payout (120 -> 20)", bal(uset,gold) == reserve0 - 100*U);
    TEST("DTD winner was paid 100 SOST",                       bal(uset,winner) == 100*U);
    TEST("miner coinbase output present (3 SOST)",             bal(uset,miner) == 3*U);
    TEST("supply neutral: winner gain == reserve loss",        bal(uset,winner) == reserve0 - bal(uset,gold));

    // ---- DISCONNECT (reorg undo) ----
    std::string derr;
    bool dok = uset.DisconnectBlock(blk, undo, &derr);
    TEST("DisconnectBlock (reorg) ok", dok);
    if(!dok) printf("     DisconnectBlock err: %s\n", derr.c_str());
    TEST("reorg restored reserve to 120 SOST", bal(uset,gold) == reserve0);
    TEST("reorg removed the winner UTXO (0)",  bal(uset,winner) == 0);

    printf("\n== jackpot RUNTIME tests: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
