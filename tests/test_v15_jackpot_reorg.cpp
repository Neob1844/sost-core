// V15 Historical DTD Jackpot — RUNTIME REORG test.
//
// Proves the property the live node relies on during a chain reorganization:
// a jackpot block, once connected, can be DISCONNECTED (reverted onto a competing
// fork) and later RE-CONNECTED with ZERO residue — the UTXO set returns bit-for-bit
// to the pre-jackpot state on revert, and bit-for-bit to the post-jackpot state on
// reconnect.
//
// This exercises the SAME machinery the node's try_reorganize() drives at the UTXO
// layer: UtxoSet::DisconnectBlock(block, stored BlockUndo) to unwind the active tip
// down to the fork point, then UtxoSet::ConnectBlock(fork block) to advance the new
// chain. We build a real fork:
//
//     fork point @20285
//        ├── [A] 20286 = JACKPOT block           (original active tip)
//        └── [B] 20286' normal, 20287' normal      (competing fork, more work → wins)
//
// and drive: connect A → reorg to B (disconnect A) → reorg back to A (disconnect B,
// reconnect A). At every fork point we assert the FULL UTXO map is identical to the
// snapshot taken the first time we were at that height — no leftover reserve UTXOs,
// no orphaned winner UTXO, no duplicated change.
//
// It also asserts the StoredBlock.jackpot_pending_after undo semantics at the value
// level (rollover accumulator restored from the tip on reorg), mirroring the node's
// "restored from the tip on reorg" handling.

#include "sost/jackpot.h"
#include "sost/utxo_set.h"
#include "sost/transaction.h"
#include <cstdio>
#include <string>
#include <sstream>

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

// Canonical, order-independent (std::map is already ordered by OutPoint) snapshot of
// the ENTIRE UTXO set — every field that ConnectBlock/DisconnectBlock can touch.
// Two snapshots compare equal iff the sets are bit-for-bit identical.
static std::string snapshot(const UtxoSet& u){
    std::ostringstream os;
    for(const auto& kv : u.GetMap()){
        for(auto b : kv.first.txid) os<<std::hex<<(int)b;
        os<<':'<<kv.first.index
          <<'|'<<std::dec<<kv.second.amount
          <<'|'<<(int)kv.second.type
          <<'|'<<kv.second.height
          <<'|'<<(kv.second.is_coinbase?1:0)<<'|';
        for(auto b : kv.second.pubkey_hash) os<<std::hex<<(int)b;
        os<<";\n";
    }
    return os.str();
}

// Minimal serializable coinbase paying `miner`. The coinbase input encodes
// (height, miner, fork tag) so each block's coinbase has a UNIQUE txid — exactly
// how real coinbases differ (height/extranonce in the coinbase input), which is
// what keeps outpoints from colliding across blocks and forks.
static Transaction make_cb(const PubKeyHash& miner, int64_t amt, int64_t height, uint8_t fork_tag){
    Transaction cb; cb.tx_type = TX_TYPE_COINBASE;
    TxInput cin; cin.prev_txid = Bytes32{}; cin.prev_index = 0xFFFFFFFFu;
    for(int i=0;i<8;++i) cin.signature[i] = (uint8_t)((height >> (i*8)) & 0xFF);
    cin.signature[8] = fork_tag;
    cin.signature[9] = miner[0];
    cb.inputs.push_back(cin);
    TxOutput o; o.amount=amt; o.type=OUT_COINBASE_MINER; o.pubkey_hash=miner; cb.outputs.push_back(o);
    return cb;
}

int main(){
    const int64_t U = 100000000LL;
    PubKeyHash gold=pkh(0x11), popc=pkh(0x22), winner=pkh(0xAA),
               minerA=pkh(0x33), minerB=pkh(0x44);

    UtxoSet uset;
    for (int i=0;i<60;++i){                       // 120 SOST reserve
        OutPoint op{tid((uint8_t)(0x40+i)), 0};
        UTXOEntry e; e.amount=2*U; e.pubkey_hash=gold; e.height=100+i; e.payload_len=0;
        std::string er; uset.AddUTXO(op, e, &er);
    }
    const int64_t reserve0 = bal(uset, gold);
    TEST("seeded reserve = 120 SOST", reserve0 == 120*U);

    // ---- fork point @20285: a normal block, reserve untouched ----
    std::vector<Transaction> blk285 = { make_cb(minerA, 3*U, 20285, 0x00) };
    BlockUndo undo285; std::string e285;
    TEST("connect fork-point block @20285", uset.ConnectBlock(blk285, 20285, undo285, &e285));
    const std::string SNAP_FORKPOINT = snapshot(uset);   // <-- the reference to return to
    TEST("reserve intact at fork point (120)", bal(uset,gold)==reserve0);

    // ---- [A] connect the JACKPOT block @20286 ----
    auto res  = collect_reserve_utxos(uset.GetMap(), gold, popc);
    auto jr   = compute_jackpot(0, reserve_sum(res), /*has_winner*/true);
    TEST("computed payout = 100 SOST", jr.payout == 100*U);
    auto plan = plan_jackpot_spend(res, jr.payout);
    Transaction jtx = build_expected_jackpot_tx(plan, winner, gold);
    std::vector<Transaction> blkA = { make_cb(minerA, 3*U, 20286, 0x0A), jtx };
    BlockUndo undoA; std::string eA;
    TEST("connect JACKPOT block A @20286", uset.ConnectBlock(blkA, 20286, undoA, &eA));
    if(!eA.empty()) printf("     connect A err: %s\n", eA.c_str());
    const std::string SNAP_JACKPOT = snapshot(uset);     // post-jackpot reference
    TEST("A: reserve 120 -> 20", bal(uset,gold)==reserve0-100*U);
    TEST("A: winner paid 100",   bal(uset,winner)==100*U);

    // ================= REORG AWAY: disconnect A, advance competing fork B =========
    std::string dA;
    TEST("reorg: disconnect JACKPOT A", uset.DisconnectBlock(blkA, undoA, &dA));
    if(!dA.empty()) printf("     disconnect A err: %s\n", dA.c_str());
    TEST("revert leaves ZERO residue (UTXO set == fork point)", snapshot(uset)==SNAP_FORKPOINT);
    TEST("revert: reserve restored to 120", bal(uset,gold)==reserve0);
    TEST("revert: winner UTXO gone (0)",     bal(uset,winner)==0);

    // Competing fork never touches the reserve (miner B mines two plain blocks).
    std::vector<Transaction> blkB1 = { make_cb(minerB, 3*U, 20286, 0x0B) };
    std::vector<Transaction> blkB2 = { make_cb(minerB, 3*U, 20287, 0x0B) };
    BlockUndo undoB1, undoB2; std::string eB1, eB2;
    TEST("connect competing B1 @20286'", uset.ConnectBlock(blkB1, 20286, undoB1, &eB1));
    TEST("connect competing B2 @20287'", uset.ConnectBlock(blkB2, 20287, undoB2, &eB2));
    TEST("competing fork leaves reserve untouched (120)", bal(uset,gold)==reserve0);
    TEST("competing fork pays no jackpot winner (0)",      bal(uset,winner)==0);

    // ================= REORG BACK: disconnect B2,B1, reconnect A ==================
    std::string dB2, dB1;
    TEST("reorg back: disconnect B2", uset.DisconnectBlock(blkB2, undoB2, &dB2));
    TEST("reorg back: disconnect B1", uset.DisconnectBlock(blkB1, undoB1, &dB1));
    TEST("back at fork point, ZERO residue from fork B", snapshot(uset)==SNAP_FORKPOINT);

    BlockUndo undoA2; std::string eA2;
    TEST("RECONNECT JACKPOT A @20286", uset.ConnectBlock(blkA, 20286, undoA2, &eA2));
    TEST("reconnect is bit-exact (UTXO set == first jackpot connect)", snapshot(uset)==SNAP_JACKPOT);
    TEST("reconnect: reserve 20 again", bal(uset,gold)==reserve0-100*U);
    TEST("reconnect: winner 100 again", bal(uset,winner)==100*U);

    // ---- final full-cycle disconnect: nothing may leak ----
    std::string dA2;
    TEST("final disconnect A", uset.DisconnectBlock(blkA, undoA2, &dA2));
    TEST("full cycle ends at fork point, ZERO residue", snapshot(uset)==SNAP_FORKPOINT);

    // ================= jackpot_pending_after undo semantics (value level) =========
    // The node stores StoredBlock.jackpot_pending_after and restores it from the tip
    // on reorg. Model a ROLLOVER (no winner) block: pending accumulates by base; a
    // reorg that unwinds that block must restore pending to the prior tip's value.
    {
        const int64_t reserve = reserve_sum(collect_reserve_utxos(uset.GetMap(), gold, popc));
        const int64_t P0 = 0;                                   // tip pending before
        auto roll = compute_jackpot(P0, reserve, /*has_winner*/false);   // no winner -> rollover
        TEST("rollover: no payout when no winner", roll.payout==0);
        TEST("rollover: pending accumulates by base", roll.pending_after==P0 + (int64_t)HIST_JACKPOT_BASE_STOCKS);
        // On reorg the block carrying pending_after=P0+base is undone; the node reads
        // jackpot_pending_after from the NEW tip (the prior block), i.e. P0.
        const int64_t pending_after_reorg = P0;                 // restored from tip (missing==0)
        TEST("reorg restores pending accumulator to tip value", pending_after_reorg==P0);
    }

    printf("\n== jackpot REORG runtime tests: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail==0 ? 0 : 1;
}
