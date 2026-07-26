// ============================================================================
// test_jackpot — V15 Historical DTD Jackpot (J), PURE consensus core.
// Exercises include/sost/jackpot.h: payout/rollover/cap arithmetic, reserve
// membership, deterministic ordering + oldest-first selection. Heights are
// expressed relative to sost::HIST_JACKPOT_FIRST_HEIGHT so the file is correct
// on mainnet (25290) and testnet builds alike.
// ============================================================================
#include "sost/jackpot.h"
#include "sost/jackpot_reserve.h"
#include "sost/params.h"
#include "sost/transaction.h"

#include <cstdio>
#include <vector>
#include <algorithm>

using namespace sost;
using namespace sost::jackpot;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { ++g_pass; printf("  PASS: %s\n", msg); } \
    else      { ++g_fail; printf("  FAIL: %s\n", msg); } \
} while (0)

static int64_t S(int64_t sost_units) { return sost_units * STOCKS_PER_SOST; }

static PubKeyHash pkh_fill(uint8_t b) { PubKeyHash p{}; p.fill(b); return p; }
static Bytes32   txid_fill(uint8_t b) { Bytes32 t{}; t.fill(b); return t; }

// ---------------------------------------------------------------------------
static void test_cadence() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    const int64_t C = HIST_JACKPOT_CADENCE_BLOCKS;
    TEST("first jackpot height is a jackpot block", is_hist_jackpot_height(F));
    TEST("F-1 is NOT a jackpot block",              !is_hist_jackpot_height(F - 1));
    TEST("F+1 is NOT a jackpot block",              !is_hist_jackpot_height(F + 1));
    TEST("F+cadence IS a jackpot block",            is_hist_jackpot_height(F + C));
    TEST("F+cadence-1 is NOT a jackpot block",      !is_hist_jackpot_height(F + C - 1));
    TEST("activation height itself is NOT (warm-up)", !is_hist_jackpot_height(HIST_JACKPOT_ACTIVATION_HEIGHT));
}

static void test_payout_basic_winner() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    auto r = hist_jackpot_apply(F, /*winner*/true, /*reserve*/S(52523), /*rollover*/0);
    TEST("is a jackpot block", r.is_jackpot_block);
    TEST("winner paid base 100 SOST", r.paid && r.payout == S(100));
    TEST("reserve decreased by exactly payout", r.reserve_after == S(52523) - S(100));
    TEST("no rollover carried (prize < cap)", r.rollover_after == 0);
    TEST("not retired", !r.retired);
    TEST("supply-neutral: payout <= reserve_before", r.payout <= S(52523));
}

static void test_no_winner_accrues_rollover() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    auto r = hist_jackpot_apply(F, /*winner*/false, /*reserve*/S(52523), /*rollover*/0);
    TEST("no winner: nothing paid", !r.paid && r.payout == 0);
    TEST("no winner: reserve untouched", r.reserve_after == S(52523));
    TEST("no winner: rollover += base", r.rollover_after == S(100));
}

static void test_rollover_clamped() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    // rollover already at cap-base (400): another miss must NOT exceed 400.
    auto r = hist_jackpot_apply(F, /*winner*/false, S(52523), /*rollover*/S(400));
    TEST("rollover clamped at CAP-BASE (400 SOST)", r.rollover_after == S(400));
}

static void test_cap_hit() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    // rollover 400 + base 100 = 500 = CAP → pay exactly 500, carry 0.
    auto r = hist_jackpot_apply(F, /*winner*/true, S(52523), /*rollover*/S(400));
    TEST("cap hit: payout == 500 SOST (cap)", r.payout == S(500));
    TEST("cap hit: rollover resets to 0", r.rollover_after == 0);
    TEST("cap hit: reserve -= 500", r.reserve_after == S(52523) - S(500));
}

static void test_reserve_limited_retires() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    // reserve smaller than the prize → pay only what's left, retire.
    auto r = hist_jackpot_apply(F, /*winner*/true, /*reserve*/S(30), /*rollover*/0);
    TEST("reserve-limited: payout == remaining reserve", r.payout == S(30));
    TEST("reserve-limited: reserve_after == 0", r.reserve_after == 0);
    TEST("reserve-limited: retired latch set", r.retired);
    TEST("reserve-limited: no rollover", r.rollover_after == 0);
}

static void test_exhausted_reserve() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    auto r = hist_jackpot_apply(F, /*winner*/true, /*reserve*/0, /*rollover*/0);
    TEST("empty reserve: retired, no payout", r.retired && !r.paid && r.payout == 0);
    TEST("empty reserve: reserve stays 0", r.reserve_after == 0);
}

static void test_non_jackpot_height_noop() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    auto r = hist_jackpot_apply(F + 1, true, S(52523), S(50));
    TEST("non-jackpot height: not a jackpot block", !r.is_jackpot_block);
    TEST("non-jackpot height: state carried unchanged",
         r.reserve_after == S(52523) && r.rollover_after == S(50) && !r.paid);
}

static void test_defensive_negatives() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    auto r = hist_jackpot_apply(F, true, /*reserve*/-1, 0);
    TEST("negative reserve: no-op, not paid", !r.paid && !r.is_jackpot_block);
}

static void test_reserve_membership() {
    PubKeyHash gold = pkh_fill(0xAA), popc = pkh_fill(0xBB), other = pkh_fill(0xCC);
    TEST("GOLD output at gold addr is reserve",
         is_reserve_output(OUT_COINBASE_GOLD, gold, gold, popc));
    TEST("POPC output at popc addr is reserve",
         is_reserve_output(OUT_COINBASE_POPC, popc, gold, popc));
    TEST("MINER output is NOT reserve",
         !is_reserve_output(OUT_COINBASE_MINER, gold, gold, popc));
    TEST("GOLD type at wrong pkh is NOT reserve",
         !is_reserve_output(OUT_COINBASE_GOLD, other, gold, popc));
    TEST("LOTTERY output is NOT reserve",
         !is_reserve_output(OUT_COINBASE_LOTTERY, gold, gold, popc));
}

static void test_deterministic_ordering() {
    ReserveUtxo a{100, txid_fill(0x10), 0, S(5)};
    ReserveUtxo b{100, txid_fill(0x10), 1, S(5)};   // same height+txid, higher vout
    ReserveUtxo c{100, txid_fill(0x20), 0, S(5)};   // same height, higher txid
    ReserveUtxo d{ 99, txid_fill(0xFF), 9, S(5)};   // lower height wins
    TEST("older height sorts first", reserve_utxo_less(d, a));
    TEST("same height: lower txid first", reserve_utxo_less(a, c));
    TEST("same height+txid: lower vout first", reserve_utxo_less(a, b));
    TEST("ordering is antisymmetric", !reserve_utxo_less(a, d));
}

static void test_selection_oldest_first() {
    // Deliberately out of order; caller sorts, then selects.
    std::vector<ReserveUtxo> v = {
        {102, txid_fill(0x03), 0, S(40)},
        {100, txid_fill(0x01), 0, S(30)},
        {101, txid_fill(0x02), 0, S(50)},
    };
    std::sort(v.begin(), v.end(), reserve_utxo_less);
    TEST("sorted oldest-first (height 100 first)", v[0].height == 100 && v[2].height == 102);

    // Need 100 SOST: 30 (h100) + 50 (h101) = 80 < 100 → also take 40 (h102) = 120.
    auto sel = select_reserve_utxos(v, S(100));
    TEST("selection covers needed", sel.sufficient);
    TEST("selection took 3 oldest UTXOs", sel.indices.size() == 3 && sel.total == S(120));

    // Need exactly 30: just the single oldest.
    auto sel2 = select_reserve_utxos(v, S(30));
    TEST("exact-first selection took 1 UTXO", sel2.indices.size() == 1 && sel2.total == S(30));

    // Need more than the whole reserve → insufficient, takes all.
    auto sel3 = select_reserve_utxos(v, S(1000));
    TEST("insufficient reserve flagged", !sel3.sufficient && sel3.indices.size() == 3);
}

static void test_change_is_supply_neutral() {
    // Model A conservation identity: selected_total == payout + change.
    const int64_t payout = S(100);
    const int64_t selected_total = S(120);
    const int64_t change = selected_total - payout;
    TEST("change back to reserve keeps supply constant",
         payout + change == selected_total && change == S(20));
}

static void test_canonical_jackpot_tx() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    PubKeyHash winner = pkh_fill(0x77);
    PubKeyHash gold   = pkh_fill(0xAA);

    // Reserve: 70 + 60 SOST (payout 100 needs both → change 30).
    std::vector<ReserveUtxo> res = {
        {100, txid_fill(0x01), 0, S(70)},
        {101, txid_fill(0x02), 1, S(60)},
    };
    std::sort(res.begin(), res.end(), reserve_utxo_less);

    Transaction tx;
    bool built = build_canonical_jackpot_tx(F, true, winner, S(52523), 0, res, gold, tx);
    TEST("canonical tx built at jackpot height", built);
    TEST("tx_type == TX_TYPE_JACKPOT", tx.tx_type == TX_TYPE_JACKPOT);
    TEST("2 inputs selected (70+60 covers 100)", tx.inputs.size() == 2);
    TEST("input keyless: zero signature", tx.inputs[0].signature[0] == 0 && tx.inputs[0].signature[63] == 0);
    TEST("2 outputs (winner + change)", tx.outputs.size() == 2);
    TEST("output0 = payout 100 to winner (OUT_TRANSFER)",
         tx.outputs[0].amount == S(100) && tx.outputs[0].type == OUT_TRANSFER && tx.outputs[0].pubkey_hash == winner);
    TEST("output1 = change 30 to reserve sink (OUT_COINBASE_GOLD)",
         tx.outputs[1].amount == S(30) && tx.outputs[1].type == OUT_COINBASE_GOLD && tx.outputs[1].pubkey_hash == gold);
    TEST("supply-neutral: Σin == Σout", (S(70)+S(60)) == (tx.outputs[0].amount + tx.outputs[1].amount));

    // Exact-match validator accepts the canonical tx.
    TEST("validator ACCEPTS canonical tx",
         jackpot_tx_matches_canonical(tx, F, true, winner, S(52523), 0, res, gold));

    // Tamper cases — all must be REJECTED.
    { Transaction t = tx; t.outputs[0].pubkey_hash = pkh_fill(0x66);
      TEST("reject: wrong winner", !jackpot_tx_matches_canonical(t, F, true, winner, S(52523), 0, res, gold)); }
    { Transaction t = tx; t.outputs[0].amount += 1; t.outputs[1].amount -= 1;
      TEST("reject: wrong payout amount", !jackpot_tx_matches_canonical(t, F, true, winner, S(52523), 0, res, gold)); }
    { Transaction t = tx; TxOutput extra; extra.amount = 1; extra.type = OUT_TRANSFER; extra.pubkey_hash = pkh_fill(0x66); t.outputs.push_back(extra);
      TEST("reject: extra output", !jackpot_tx_matches_canonical(t, F, true, winner, S(52523), 0, res, gold)); }
    { Transaction t = tx; t.inputs[0].signature[0] = 0x01;
      TEST("reject: non-keyless input (signature set)", !jackpot_tx_matches_canonical(t, F, true, winner, S(52523), 0, res, gold)); }
    { Transaction t = tx; std::swap(t.inputs[0], t.inputs[1]);
      TEST("reject: wrong input order", !jackpot_tx_matches_canonical(t, F, true, winner, S(52523), 0, res, gold)); }
    { // A perfectly-formed tx at a NON-jackpot height is not expected → reject.
      TEST("reject: jackpot tx at non-jackpot height",
           !jackpot_tx_matches_canonical(tx, F + 1, true, winner, S(52523), 0, res, gold)); }
    { // No winner this block → no jackpot tx expected → any tx rejected.
      TEST("reject: jackpot tx when no eligible winner",
           !jackpot_tx_matches_canonical(tx, F, false, winner, S(52523), 0, res, gold)); }

    // Exact-reserve case: single UTXO == payout → no change output.
    std::vector<ReserveUtxo> res2 = { {100, txid_fill(0x05), 0, S(100)} };
    Transaction tx2;
    bool built2 = build_canonical_jackpot_tx(F, true, winner, S(100), 0, res2, gold, tx2);
    TEST("exact-reserve tx built", built2);
    TEST("exact-reserve: 1 input, 1 output, no change",
         tx2.inputs.size() == 1 && tx2.outputs.size() == 1 && tx2.outputs[0].amount == S(100));

    // No tx expected when reserve is empty.
    Transaction tx3;
    TEST("empty reserve → no canonical tx built",
         !build_canonical_jackpot_tx(F, true, winner, 0, 0, {}, gold, tx3));
}

static void test_jackpot_tx_serialization() {
    const int64_t F = HIST_JACKPOT_FIRST_HEIGHT;
    PubKeyHash winner = pkh_fill(0x77), gold = pkh_fill(0xAA);
    std::vector<ReserveUtxo> res = {
        {100, txid_fill(0x01), 0, S(70)},
        {101, txid_fill(0x02), 1, S(60)},
    };
    std::sort(res.begin(), res.end(), reserve_utxo_less);
    Transaction tx;
    build_canonical_jackpot_tx(F, true, winner, S(52523), 0, res, gold, tx);

    // Serialize -> deserialize round-trip (tx_type 0x02 must survive).
    std::vector<uint8_t> raw; std::string err;
    TEST("jackpot tx serializes", tx.Serialize(raw, &err));
    Transaction back; std::string err2;
    TEST("jackpot tx deserializes (TX_TYPE_JACKPOT accepted)",
         Transaction::Deserialize(raw, back, &err2));
    TEST("round-trip preserves tx_type == TX_TYPE_JACKPOT", back.tx_type == TX_TYPE_JACKPOT);
    TEST("round-trip preserves input/output counts",
         back.inputs.size() == tx.inputs.size() && back.outputs.size() == tx.outputs.size());

    // txid determinism across the round-trip.
    Hash256 id1{}, id2{}; std::string e3, e4;
    TEST("txid computes on both", tx.ComputeTxId(id1, &e3) && back.ComputeTxId(id2, &e4));
    TEST("txid deterministic across round-trip", id1 == id2);

    // The deserialized tx still passes canonical exact-match validation.
    TEST("round-tripped tx still validates canonical",
         jackpot_tx_matches_canonical(back, F, true, winner, S(52523), 0, res, gold));
}

static void test_reserve_discovery() {
    UtxoSet u;
    PubKeyHash gold = pkh_fill(0xAA), popc = pkh_fill(0xBB), miner = pkh_fill(0xCC);
    auto add = [&](uint8_t tb, uint32_t vout, int64_t h, uint8_t type, PubKeyHash pkh, int64_t amt){
        OutPoint op; op.txid = txid_fill(tb); op.index = vout;
        UTXOEntry e; e.amount = amt; e.type = type; e.pubkey_hash = pkh; e.height = h; e.is_coinbase = true;
        std::string err; u.AddUTXO(op, e, &err);
    };
    // 3 genuine reserve UTXOs (added OUT OF ORDER) + 2 non-reserve decoys.
    add(0x03, 0, 102, OUT_COINBASE_GOLD, gold,  S(40));
    add(0x01, 0, 100, OUT_COINBASE_GOLD, gold,  S(30));
    add(0x02, 1, 101, OUT_COINBASE_POPC, popc,  S(50));
    add(0x09, 0, 103, OUT_COINBASE_MINER, miner, S(999));  // miner output — NOT reserve
    add(0x0A, 0, 104, OUT_COINBASE_GOLD, popc,  S(7));      // GOLD type at wrong pkh — NOT reserve

    auto r = discover_reserve_utxos(u, gold, popc);
    TEST("discovery finds exactly the 3 reserve UTXOs", r.size() == 3);
    TEST("discovery sorted oldest-first (h100 first, h102 last)",
         r.front().height == 100 && r.back().height == 102);
    TEST("discovery excludes miner + wrong-pkh decoys (balance == 120 SOST)",
         reserve_balance(r) == S(120));

    // Integration: discovered reserve -> canonical jackpot tx (payout 100).
    Transaction tx;
    bool built = build_canonical_jackpot_tx(HIST_JACKPOT_FIRST_HEIGHT, /*winner*/true,
                                            pkh_fill(0x77), reserve_balance(r), 0, r, gold, tx);
    TEST("canonical jackpot tx builds from DISCOVERED reserve",
         built && tx.tx_type == TX_TYPE_JACKPOT && tx.outputs[0].amount == S(100));

    // Empty UTXO set -> empty reserve -> no jackpot tx.
    UtxoSet empty;
    auto r0 = discover_reserve_utxos(empty, gold, popc);
    Transaction tx0;
    TEST("empty chainstate -> empty reserve -> no jackpot tx",
         r0.empty() && !build_canonical_jackpot_tx(HIST_JACKPOT_FIRST_HEIGHT, true, pkh_fill(0x77), 0, 0, r0, gold, tx0));
}

int main() {
    printf("== test_jackpot — V15 Historical DTD Jackpot (J) pure core ==\n");
    test_cadence();
    test_payout_basic_winner();
    test_no_winner_accrues_rollover();
    test_rollover_clamped();
    test_cap_hit();
    test_reserve_limited_retires();
    test_exhausted_reserve();
    test_non_jackpot_height_noop();
    test_defensive_negatives();
    test_reserve_membership();
    test_deterministic_ordering();
    test_selection_oldest_first();
    test_change_is_supply_neutral();
    test_canonical_jackpot_tx();
    test_jackpot_tx_serialization();
    test_reserve_discovery();
    printf("\n== summary: %d pass, %d fail ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
