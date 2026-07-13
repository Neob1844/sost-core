// V15 Historical DTD Jackpot — pure amount/cadence logic tests.
// Spec: docs/V15_HISTORICAL_JACKPOT_SPEC.md
//
// Covers the deterministic core (the parts NOT involving UTXO/chain state):
// cadence trigger, base payout, rollover, 500 cap, final partial payout,
// exhaustion/disable, and the "never promise more than the reserve" invariant.
// The constitutional-spend / UTXO / reorg parts are tested in the integration
// suite once that path is implemented.

#include "sost/jackpot.h"
#include "sost/params.h"
#include <cstdio>

using namespace sost;
using namespace sost::jackpot;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static const int64_t BASE = HIST_JACKPOT_BASE_STOCKS;   // 100 SOST
static const int64_t CAP  = HIST_JACKPOT_CAP_STOCKS;    // 500 SOST
static const int64_t BIG  = 1000000LL * 100000000LL;    // 1,000,000 SOST reserve (plenty)

int main() {
    printf("== cadence — jackpot OPPORTUNITY every %lld DTD lottery blocks (~288, approx) ==\n", (long long)HIST_JACKPOT_DTD_INTERVAL);
    TEST("lottery-block #96 is an opportunity",   is_jackpot_trigger(96));
    TEST("lottery-block #95 is NOT",              !is_jackpot_trigger(95));
    TEST("lottery-block #97 is NOT",              !is_jackpot_trigger(97));
    TEST("lottery-block #192 is an opportunity",  is_jackpot_trigger(192));
    TEST("lottery-block #0 never",                !is_jackpot_trigger(0));

    printf("== first jackpot opportunity height (off-by-one pin: V15=20000) ==\n");
    {
        // V15_HEIGHT=20000 (20000 %% 3 == 2, NOT a lottery block). First lottery
        // block is 20001 (opportunity #1). Opportunity #96 = 20001 + 95*3 = 20286.
        auto nth_lottery_height = [](int64_t v15, int64_t n) {
            int64_t h = v15 + 1;
            while (h % 3 != 0) ++h;          // first lottery block strictly after V15
            return h + (n - 1) * 3;          // permanent 1-of-3 cadence
        };
        TEST("first lottery block after V15(20000) is 20001", nth_lottery_height(20000, 1) == 20001);
        TEST("96th lottery opportunity is height 20286",       nth_lottery_height(20000, 96) == 20286);
        TEST("is_jackpot_trigger(96) true",                    is_jackpot_trigger(96));
        TEST("opportunity #95 (height 20283) NOT a jackpot",   !is_jackpot_trigger(95));
    }

    printf("== overflow guard (consensus hygiene) ==\n");
    {
        int64_t reserve = 1000LL * 100000000LL;   // 1000 SOST
        auto r = compute_jackpot(INT64_MAX, reserve, true);   // absurd pending
        TEST("huge pending -> no overflow, payout in [0, reserve]", r.payout >= 0 && r.payout <= reserve);
        TEST("huge pending -> payout + pending_after <= reserve",   r.payout + r.pending_after <= reserve);
        auto r2 = compute_jackpot(INT64_MAX, reserve, false);
        TEST("huge pending, no winner -> pending clamped to reserve", r2.pending_after == reserve);
    }

    printf("== base payout ==\n");
    {
        auto r = compute_jackpot(/*pending*/0, /*reserve*/BIG, /*winner*/true);
        TEST("winner, no pending -> pays base 100", r.payout == BASE);
        TEST("winner, no pending -> pending stays 0", r.pending_after == 0);
    }

    printf("== rollover (no winner) ==\n");
    {
        auto r = compute_jackpot(0, BIG, /*winner*/false);
        TEST("no winner -> payout 0", r.payout == 0);
        TEST("no winner -> pending += base (100)", r.pending_after == BASE);
        auto r2 = compute_jackpot(r.pending_after, BIG, false);
        TEST("no winner twice -> pending 200", r2.pending_after == 2 * BASE);
        auto r3 = compute_jackpot(r2.pending_after, BIG, true);
        TEST("then winner -> pays 300 (base + 200 pending)", r3.payout == 3 * BASE);
        TEST("then winner -> pending back to 0", r3.pending_after == 0);
    }

    printf("== 500 cap ==\n");
    {
        // pending 450 + base 100 = 550 target -> cap 500, 50 rolls forward
        auto r = compute_jackpot(450LL * 100000000LL, BIG, true);
        TEST("target 550 -> payout capped at 500", r.payout == CAP);
        TEST("target 550 -> 50 rolls forward", r.pending_after == 50LL * 100000000LL);
    }

    printf("== final partial payout (reserve < payout) ==\n");
    {
        int64_t reserve = 30LL * 100000000LL;   // only 30 SOST left
        auto r = compute_jackpot(0, reserve, true);
        TEST("reserve 30 < base 100 -> pays only 30 (remnant)", r.payout == reserve);
        TEST("final partial -> pending 0", r.pending_after == 0);
    }

    printf("== exhaustion / disabled forever ==\n");
    {
        auto r = compute_jackpot(0, 0, true);
        TEST("reserve 0 -> payout 0", r.payout == 0);
        TEST("reserve 0 -> pending 0 (disabled)", r.pending_after == 0);
        auto r2 = compute_jackpot(500LL * 100000000LL, 0, true);  // even with pending
        TEST("reserve 0 + pending -> still 0/0", r2.payout == 0 && r2.pending_after == 0);
    }

    printf("== invariant: never PROMISE more than the reserve ==\n");
    {
        // reserve 250, big pending, no winner: pending would grow past reserve -> capped to reserve
        int64_t reserve = 250LL * 100000000LL;
        auto r = compute_jackpot(200LL * 100000000LL, reserve, false);
        TEST("no-winner pending capped at reserve (250, not 300)", r.pending_after == reserve);
        // reserve 250, winner, pending 200: target 300 > reserve -> pays 250, pending 0
        auto r2 = compute_jackpot(200LL * 100000000LL, reserve, true);
        TEST("winner target 300 > reserve 250 -> pays 250", r2.payout == reserve);
        TEST("payout + pending_after <= reserve", r2.payout + r2.pending_after <= reserve);
    }

    printf("== invariant sweep: payout<=cap, payout<=reserve, payout+pending<=reserve ==\n");
    {
        bool ok = true;
        const int64_t U = 100000000LL;
        for (int64_t pend = 0; pend <= 800; pend += 137)
          for (int64_t res = 0; res <= 900; res += 111)
            for (int w = 0; w <= 1; ++w) {
                auto r = compute_jackpot(pend*U, res*U, w != 0);
                if (r.payout < 0 || r.payout > CAP) ok = false;
                if (r.payout > res*U) ok = false;
                if (r.payout + r.pending_after > res*U) ok = false;
            }
        TEST("all invariants hold across the sweep", ok);
    }

    printf("== FIFO spend plan (deterministic, oldest-first) ==\n");
    {
        auto tid = [](uint8_t s){ Bytes32 t{}; for (size_t i=0;i<t.size();++i) t[i]=(uint8_t)(s^(i*7)); return t; };
        auto mk  = [&](int64_t h, uint8_t s, uint32_t v, int64_t amtSost){
            ReserveUtxo u; u.height=h; u.txid=tid(s); u.vout=v; u.amount=amtSost*100000000LL; return u; };
        // reserve UTXOs at mixed heights (2 SOST each), intentionally unsorted
        std::vector<ReserveUtxo> res = {
            mk(120, 0x30, 0, 2), mk(100, 0x10, 1, 2), mk(110, 0x20, 0, 2),
            mk(100, 0x10, 0, 2), mk(130, 0x40, 0, 2)
        };
        // payout 5 SOST -> needs 3 UTXOs (2+2+2=6). Oldest first: h100/v0, h100/v1, h110.
        auto p = plan_jackpot_spend(res, 5LL*100000000LL);
        TEST("plan ok", p.ok);
        TEST("selected exactly 3 inputs (2+2+2 >= 5)", p.inputs.size() == 3);
        TEST("input 0 is oldest (h100, vout0)", p.inputs[0].height==100 && p.inputs[0].vout==0);
        TEST("input 1 is h100 vout1 (vout tiebreak)", p.inputs[1].height==100 && p.inputs[1].vout==1);
        TEST("input 2 is h110 (next height)", p.inputs[2].height==110);
        TEST("input_sum = 6 SOST", p.input_sum == 6LL*100000000LL);
        TEST("winner_amount = payout 5 SOST", p.winner_amount == 5LL*100000000LL);
        TEST("change = 1 SOST back to reserve", p.change_amount == 1LL*100000000LL);

        // exact match -> no change
        auto p2 = plan_jackpot_spend(res, 6LL*100000000LL);
        TEST("exact 6 SOST -> 3 inputs, change 0", p2.inputs.size()==3 && p2.change_amount==0);

        // determinism: shuffle input order -> identical plan
        std::vector<ReserveUtxo> shuffled = { res[4],res[0],res[3],res[2],res[1] };
        auto p3 = plan_jackpot_spend(shuffled, 5LL*100000000LL);
        bool same = (p3.inputs.size()==p.inputs.size());
        for (size_t i=0; same && i<p.inputs.size(); ++i)
            same = (p3.inputs[i].height==p.inputs[i].height && p3.inputs[i].vout==p.inputs[i].vout
                    && p3.inputs[i].txid==p.inputs[i].txid);
        TEST("plan is order-independent (deterministic)", same && p3.change_amount==p.change_amount);

        // payout larger than the whole reserve -> ok=false (must not happen; payout<=reserve guaranteed upstream)
        auto p4 = plan_jackpot_spend(res, 999LL*100000000LL);
        TEST("payout > reserve -> ok=false (guard)", !p4.ok);

        // payout 0 -> empty ok
        auto p5 = plan_jackpot_spend(res, 0);
        TEST("payout 0 -> empty plan, ok", p5.ok && p5.inputs.empty());
    }

    printf("== expected_jackpot_tx builder (byte-exact, miner == validator) ==\n");
    {
        auto tid = [](uint8_t s){ Bytes32 t{}; for (size_t i=0;i<t.size();++i) t[i]=(uint8_t)(s^(i*7)); return t; };
        auto pkh = [](uint8_t s){ PubKeyHash p{}; for (size_t i=0;i<p.size();++i) p[i]=(uint8_t)(s^(i*3)); return p; };
        auto mk  = [&](int64_t h, uint8_t s, uint32_t v, int64_t amtSost){
            ReserveUtxo u; u.height=h; u.txid=tid(s); u.vout=v; u.amount=amtSost*100000000LL; return u; };
        std::vector<ReserveUtxo> res = { mk(100,0x10,0,2), mk(100,0x10,1,2), mk(110,0x20,0,2) };
        PubKeyHash winner = pkh(0xAA), reserve = pkh(0xBB);

        auto plan = plan_jackpot_spend(res, 5LL*100000000LL);   // 3 inputs, change 1
        auto tx = build_expected_jackpot_tx(plan, winner, reserve);

        TEST("tx has 3 inputs (FIFO reserve UTXOs)", tx.inputs.size() == 3);
        bool zerosig = true;
        for (auto& in : tx.inputs) for (auto b : in.signature) if (b) zerosig = false;
        TEST("all inputs have ZERO signature (constitutional)", zerosig);
        TEST("tx has 2 outputs (winner + change)", tx.outputs.size() == 2);
        TEST("out[0] = winner payout, OUT_TRANSFER", tx.outputs[0].amount==5LL*100000000LL
             && tx.outputs[0].pubkey_hash==winner && tx.outputs[0].type==OUT_TRANSFER);
        TEST("out[1] = change to reserve", tx.outputs[1].amount==1LL*100000000LL
             && tx.outputs[1].pubkey_hash==reserve);
        TEST("value conserved: inputs_sum == out0 + out1",
             plan.input_sum == tx.outputs[0].amount + tx.outputs[1].amount);

        // determinism: identical tx on a second (independent) build -> identical bytes
        auto tx2 = build_expected_jackpot_tx(plan_jackpot_spend(res, 5LL*100000000LL), winner, reserve);
        std::vector<Byte> b1, b2; std::string e1, e2;
        bool s1 = tx.Serialize(b1, &e1), s2 = tx2.Serialize(b2, &e2);
        TEST("both serialize ok", s1 && s2);
        TEST("byte-exact determinism (miner == validator)", b1 == b2);

        // exact-match payout -> no change output
        auto plan3 = plan_jackpot_spend(res, 6LL*100000000LL);
        auto tx3 = build_expected_jackpot_tx(plan3, winner, reserve);
        TEST("exact payout -> 1 output (no change)", tx3.outputs.size() == 1);
    }

    printf("== reserve UTXO adapter (live UTXO set -> ReserveUtxo FIFO) ==\n");
    {
        auto tid = [](uint8_t s){ Bytes32 t{}; for (size_t i=0;i<t.size();++i) t[i]=(uint8_t)(s^(i*7)); return t; };
        auto pkh = [](uint8_t s){ PubKeyHash p{}; for (size_t i=0;i<p.size();++i) p[i]=(uint8_t)(s^(i*3)); return p; };
        PubKeyHash gold = pkh(0x11), popc = pkh(0x22), miner = pkh(0x99);
        auto put = [&](std::map<OutPoint,UTXOEntry>& m, uint8_t txs, uint32_t v, int64_t h, const PubKeyHash& a, int64_t amtSost){
            OutPoint op; op.txid=tid(txs); op.index=v; UTXOEntry e; e.pubkey_hash=a; e.amount=amtSost*100000000LL; e.height=h; m[op]=e; };

        std::map<OutPoint,UTXOEntry> utxos;
        put(utxos, 0x01, 0, 100, gold,  2);   // reserve (gold)
        put(utxos, 0x02, 0, 110, popc,  2);   // reserve (popc)
        put(utxos, 0x01, 1, 100, gold,  2);   // reserve (gold)
        put(utxos, 0x03, 0, 105, miner, 7);   // NOT reserve (miner) — must be ignored
        put(utxos, 0x04, 0, 120, miner, 5);   // NOT reserve

        auto res = collect_reserve_utxos(utxos, gold, popc);
        TEST("adapter collects exactly 3 reserve UTXOs (2 gold + 1 popc)", res.size() == 3);
        bool onlyreserve = true;
        for (auto& u : res) { (void)u; }   // (pubkey filtered inside adapter)
        TEST("reserve_sum = 6 SOST (miner UTXOs excluded)", reserve_sum(res) == 6LL*100000000LL);

        // end-to-end: plan a 3 SOST payout from the live-collected reserve
        auto plan = plan_jackpot_spend(res, 3LL*100000000LL);
        TEST("e2e: plan ok, oldest-first from live set", plan.ok && plan.inputs.size() == 2
             && plan.inputs[0].height == 100);
        TEST("e2e: change = 1 SOST", plan.change_amount == 1LL*100000000LL);
        (void)onlyreserve;
    }

    printf("== block-level opportunity index (real helper, off-by-one pin) ==\n");
    {
        const int64_t P2 = 7100, V15 = 20000;
        TEST("V15 height 20000 is NOT a lottery block -> index 0", jackpot_lottery_index(20000, P2, V15) == 0);
        TEST("first lottery block 20001 -> index 1",               jackpot_lottery_index(20001, P2, V15) == 1);
        TEST("96th opportunity is exactly height 20286",           jackpot_lottery_index(20286, P2, V15) == 96);
        TEST("pre-V15 lottery block 19998 -> index 0",             jackpot_lottery_index(19998, P2, V15) == 0);
        TEST("is_jackpot_opportunity(20286) == true",              is_jackpot_opportunity(20286, P2, V15));
        TEST("is_jackpot_opportunity(20001) == false",            !is_jackpot_opportunity(20001, P2, V15));
        TEST("is_jackpot_opportunity(20000) == false (not lottery)", !is_jackpot_opportunity(20000, P2, V15));
        TEST("no opportunity before V15 (19998)",                 !is_jackpot_opportunity(19998, P2, V15));
    }

    printf("== block validation (fabricated blocks -> validate_block_jackpot) ==\n");
    {
        const int64_t P2 = 7100, V15 = 20000;
        const int64_t U = 100000000LL, PAY = 100*U;
        auto tid = [](uint8_t s){ Bytes32 t{}; for (size_t i=0;i<t.size();++i) t[i]=(uint8_t)(s^(i*7)); return t; };
        auto pkh = [](uint8_t s){ PubKeyHash p{}; for (size_t i=0;i<p.size();++i) p[i]=(uint8_t)(s^(i*3)); return p; };
        PubKeyHash gold=pkh(0x11), popc=pkh(0x22), winner=pkh(0xAA), user=pkh(0x55);

        auto build_map = [&](int64_t nGold){
            std::map<OutPoint,UTXOEntry> m;
            for (int64_t i=0;i<nGold;++i){ OutPoint op; op.txid=tid((uint8_t)(0x40+i)); op.index=0;
                UTXOEntry e; e.pubkey_hash=gold; e.amount=2*U; e.height=100+i; m[op]=e; }
            return m; };
        Transaction cb; cb.tx_type=0x01;                     // minimal coinbase (not inspected)
        auto only_cb = [&](){ return std::vector<Transaction>{cb}; };
        auto expected_tx = [&](const std::map<OutPoint,UTXOEntry>& m, int64_t payout){
            return build_expected_jackpot_tx(plan_jackpot_spend(collect_reserve_utxos(m,gold,popc),payout), winner, gold); };
        auto reserve_spend_tx = [&](const std::map<OutPoint,UTXOEntry>& m, bool signed_){
            Transaction t; t.tx_type=0x00; TxInput in; in.prev_txid=m.begin()->first.txid; in.prev_index=m.begin()->first.index;
            if(signed_) for(auto&b:in.signature) b=0xAB; t.inputs.push_back(in);
            TxOutput o; o.amount=2*U; o.type=OUT_TRANSFER; o.pubkey_hash=user; t.outputs.push_back(o); return t; };

        // 1) pre-V15 -> accept (no-op)
        { auto m=build_map(60); auto r=validate_block_jackpot(only_cb(),19998,P2,V15,m,gold,popc,true,winner,0);
          TEST("1) pre-V15 -> ok, no-op", r.ok && r.jackpot_pending_after==0); }
        // 2) opportunity+winner, missing txs[1] -> reject
        { auto m=build_map(120); auto r=validate_block_jackpot(only_cb(),20286,P2,V15,m,gold,popc,true,winner,0);
          TEST("2) opp 20286 + winner, missing txs[1] -> reject", !r.ok); }
        // 3) correct txs[1] accept; altered reject
        { auto m=build_map(120); Transaction j=expected_tx(m,PAY);
          TEST("3a) correct txs[1] -> ok", validate_block_jackpot({cb,j},20286,P2,V15,m,gold,popc,true,winner,0).ok);
          Transaction bad=j; bad.outputs[0].amount+=1;
          TEST("3b) altered amount -> reject", !validate_block_jackpot({cb,bad},20286,P2,V15,m,gold,popc,true,winner,0).ok);
          Transaction bw=j; bw.outputs[0].pubkey_hash=user;
          TEST("3c) altered winner -> reject", !validate_block_jackpot({cb,bw},20286,P2,V15,m,gold,popc,true,winner,0).ok);
          Transaction bi=j; if(!bi.inputs.empty()) bi.inputs[0].prev_index^=1u;
          TEST("3d) altered input -> reject", !validate_block_jackpot({cb,bi},20286,P2,V15,m,gold,popc,true,winner,0).ok); }
        // 4) reserve-spend on a NON-opportunity block -> reject
        { auto m=build_map(60); auto r=validate_block_jackpot({cb,reserve_spend_tx(m,false)},20287,P2,V15,m,gold,popc,false,winner,0);
          TEST("4) reserve spend on non-opportunity block -> reject", !r.ok); }
        // 5) no winner -> no tx, pending += base
        { auto m=build_map(60); auto r=validate_block_jackpot(only_cb(),20286,P2,V15,m,gold,popc,false,winner,0);
          TEST("5) opp no winner -> ok, pending += 100", r.ok && r.jackpot_pending_after==PAY); }
        // 6) reserve exhausted -> no tx, pending 0, no crash
        { std::map<OutPoint,UTXOEntry> empty; auto r=validate_block_jackpot(only_cb(),20286,P2,V15,empty,gold,popc,true,winner,0);
          TEST("6) empty reserve -> ok, pending 0", r.ok && r.jackpot_pending_after==0); }
        // 7) address-lock: signed normal tx spending reserve -> reject
        { auto m=build_map(60); auto r=validate_block_jackpot({cb,reserve_spend_tx(m,true)},20290,P2,V15,m,gold,popc,false,winner,0);
          TEST("7) signed tx spending reserve -> reject (sig ignored)", !r.ok); }
        // 8) pending flow (undo relies on this): no-winner then winner pays base+pending
        { auto m=build_map(120); auto r1=validate_block_jackpot(only_cb(),20286,P2,V15,m,gold,popc,false,winner,0);
          TEST("8a) opp#96 no winner -> pending 100", r1.jackpot_pending_after==PAY);
          Transaction j2=expected_tx(m,200*U);
          auto r2=validate_block_jackpot({cb,j2},20574,P2,V15,m,gold,popc,true,winner,r1.jackpot_pending_after);
          TEST("8b) opp#192 winner pays base+pending (200), pending 0", r2.ok && r2.jackpot_pending_after==0); }
    }

    printf("\n== jackpot pure tests: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
