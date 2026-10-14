// ============================================================================
// test_v17_economics — V17 (block #40,000) reward accounting 80 / 15 / 5.
//
// Covers the pure rules (include/sost/v17_economics.h), the coinbase validator
// (ValidateCoinbaseConsensus, V17 branch), the block-level jackpot rule
// (jackpot_block.h validate_block_jackpot_v17), the unchanged DTD eligibility
// helper driven through V17 coinbases, and a long UTXO-level chain simulation
// with exact supply conservation, reorg (disconnect / reconnect) across
// activation and across jackpot funding.
//
// Built with MAINNET params (ctest default): heights 39998/39999/40000/40001
// are asserted literally. Under a devnet/testnet build the generic parts run
// against that profile's V17_HEIGHT and the mainnet literals are skipped.
// ============================================================================
#include "sost/v17_economics.h"
#include "sost/jackpot.h"
#include "sost/jackpot_block.h"
#include "sost/jackpot_reserve.h"
#include "sost/lottery.h"
#include "sost/subsidy.h"
#include "sost/tx_validation.h"
#include "sost/utxo_set.h"
#include "sost/params.h"

#include <cstdio>
#include <cstring>
#include <map>
#include <random>
#include <set>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { if (cond) { ++g_pass; } else { ++g_fail; std::printf("  FAIL: %s  (%s:%d)\n", (msg), __FILE__, __LINE__); } } while (0)
#define SECTION(name) std::printf("--- %s\n", name)

static PubKeyHash P(uint8_t b) { PubKeyHash p{}; p.fill(b); return p; }
static const int64_t SOST = STOCKS_PER_SOST;
static const int64_t BASE = HIST_JACKPOT_BASE_STOCKS;
static const int64_t CAP  = HIST_JACKPOT_CAP_STOCKS;
static const int64_t EPOCH_LEN = 131553;   // src/subsidy.cpp EPOCH_LEN

// ---------------------------------------------------------------------------
// Independent reference for the canonical rounding rule (no __int128, no shared
// code): long division on decimal digits of the subsidy.
// ---------------------------------------------------------------------------
static int64_t ref_muldiv_down(int64_t a, int64_t num, int64_t den) {
    // a*num/den rounded down, via (q*den + r) decomposition, valid for a >= 0, num,den small.
    const int64_t q = a / den, r = a % den;
    return q * num + (r * num) / den;
}

static void test_split_rule() {
    SECTION("1. canonical subsidy split (80/15/5, miner absorbs the remainder)");
    // Known values at the initial reward R0.
    {
        auto s = v17::subsidy_split(785'100'863);
        CHECK(s.ok && s.dtd_subsidy == 117'765'129 && s.jackpot_j == 39'255'043 &&
              s.miner_subsidy == 628'080'691, "R0 = 785,100,863 -> 628,080,691 / 117,765,129 / 39,255,043");
    }
    // Small explicit table 0..20 (remainder cases).
    struct { int64_t s, m, d, j; } tbl[] = {
        {0,0,0,0},{1,1,0,0},{6,6,0,0},{7,6,1,0},{19,17,2,0},{20,16,3,1},{99,81,14,4},{100,80,15,5},{101,81,15,5},{119,97,17,5},
    };
    for (auto& t : tbl) {
        auto s = v17::subsidy_split(t.s);
        char m[96]; std::snprintf(m, sizeof m, "table subsidy=%lld", (long long)t.s);
        CHECK(s.ok && s.miner_subsidy == t.m && s.dtd_subsidy == t.d && s.jackpot_j == t.j, m);
    }
    // Exhaustive 0..2,000,000 + exact sum + reference + bounds.
    int64_t bad = 0;
    for (int64_t x = 0; x <= 2'000'000; ++x) {
        auto s = v17::subsidy_split(x);
        if (!s.ok || s.miner_subsidy + s.dtd_subsidy + s.jackpot_j != x ||
            s.dtd_subsidy != ref_muldiv_down(x, 15, 100) || s.jackpot_j != ref_muldiv_down(x, 5, 100) ||
            s.miner_subsidy * 100 < 80 * x || s.miner_subsidy * 100 >= 80 * x + 200) ++bad;
    }
    CHECK(bad == 0, "exhaustive 0..2,000,000: sum exact, round-down rule, 80% <= miner < 80% + 2 stocks");
    // Every distinct epoch subsidy of the schedule, start and end of each epoch, until 0.
    int64_t epochs = 0, bad_ep = 0; bool reached_zero = false;
    for (int64_t e = 0; e < 400 && !reached_zero; ++e) {
        for (int64_t h : {e * EPOCH_LEN, e * EPOCH_LEN + EPOCH_LEN - 1}) {
            const int64_t sub = sost_subsidy_stocks(h);
            auto s = v17::subsidy_split(sub);
            if (!s.ok || s.miner_subsidy + s.dtd_subsidy + s.jackpot_j != sub ||
                s.dtd_subsidy != ref_muldiv_down(sub, 15, 100) || s.jackpot_j != ref_muldiv_down(sub, 5, 100)) ++bad_ep;
            if (sub == 0) reached_zero = true;
        }
        ++epochs;
    }
    char m[128]; std::snprintf(m, sizeof m, "all %lld epoch subsidies up to the cap (subsidy reaches 0: %s) split exactly",
                               (long long)epochs, reached_zero ? "yes" : "no");
    CHECK(bad_ep == 0 && reached_zero, m);
    // Partial final subsidy at the cap (binary search for the first height whose
    // subsidy is below the epoch base reward) — still split exactly.
    {
        int64_t lo = 0, hi = 400 * EPOCH_LEN;
        while (lo < hi) { int64_t mid = lo + (hi - lo) / 2; if (sost_subsidy_stocks(mid) == 0) hi = mid; else lo = mid + 1; }
        const int64_t last = lo - 1;   // last height with a positive subsidy
        int64_t ok_tail = 0;
        for (int64_t h = last - 3; h <= last + 3; ++h) {
            const int64_t sub = sost_subsidy_stocks(h);
            auto s = v17::subsidy_split(sub);
            if (s.ok && s.miner_subsidy + s.dtd_subsidy + s.jackpot_j == sub) ++ok_tail;
        }
        std::snprintf(m, sizeof m, "cap tail around last positive-subsidy height %lld split exactly", (long long)last);
        CHECK(ok_tail == 7 && sost_subsidy_stocks(last + 1) == 0, m);
    }
    // Overflow safety: every int64 subsidy (randomized + boundaries).
    std::mt19937_64 rng(17);
    int64_t bad_big = 0;
    std::vector<int64_t> big = {INT64_MAX, INT64_MAX - 1, INT64_MAX / 15, INT64_MAX / 100 * 100 - 1, SUPPLY_MAX_STOCKS};
    for (int i = 0; i < 200000; ++i) big.push_back((int64_t)(rng() >> 1));
    for (int64_t x : big) {
        auto s = v17::subsidy_split(x);
        const __int128 sum = (__int128)s.miner_subsidy + s.dtd_subsidy + s.jackpot_j;
        if (!s.ok || sum != x || s.dtd_subsidy != ref_muldiv_down(x, 15, 100) ||
            s.jackpot_j != ref_muldiv_down(x, 5, 100) || s.miner_subsidy < 0) ++bad_big;
    }
    CHECK(bad_big == 0, "200,005 int64 subsidies incl. INT64_MAX: no overflow, exact");
    CHECK(!v17::subsidy_split(-1).ok, "negative subsidy rejected");
    // Fees: 100 % miner.
    auto c0 = v17::coinbase_amounts(785'100'863, 0);
    auto c1 = v17::coinbase_amounts(785'100'863, 123'456);
    CHECK(c0.ok && c1.ok && c1.miner_total - c0.miner_total == 123'456 && c1.dtd_subsidy == c0.dtd_subsidy &&
          c1.jackpot_j == c0.jackpot_j, "fees go 100% to the miner, DTD and J unchanged by fees");
    CHECK(!v17::coinbase_amounts(100, -1).ok && !v17::coinbase_amounts(100, SUPPLY_MAX_STOCKS + 1).ok &&
          v17::coinbase_amounts(100, SUPPLY_MAX_STOCKS).ok, "fee bounds [0, SUPPLY_MAX]");
    CHECK(v17::dtd_paid_out(true, 1, 0) && !v17::dtd_paid_out(true, 0, 0) && v17::dtd_paid_out(true, 0, 5) &&
          !v17::dtd_paid_out(false, 100, 100), "DTD output only for a non-empty set and a positive amount");
}

static void test_activation_constants() {
    SECTION("2. activation constant / boundary 39998..40001");
#if !defined(SOST_DEVNET_FORKS) && !defined(SOST_TESTNET_FORKS)
    CHECK(V17_HEIGHT == 40000, "MAINNET V17_HEIGHT == 40000");
    CHECK(!v17_active_at(39998) && !v17_active_at(39999) && v17_active_at(40000) && v17_active_at(40001),
          "v17_active_at: 39998 F, 39999 F, 40000 T, 40001 T");
    CHECK(is_hist_jackpot_height(39978) && is_hist_jackpot_height(40266) && !is_hist_jackpot_height(40000),
          "last pre-V17 jackpot #39,978, first V17 jackpot #40,266, #40,000 is not a jackpot height");
    CHECK(!v17::jackpot_funding(39978, true, 1000 * SOST, 0, 0).is_jackpot_block,
          "V17 funding never applies to the pre-V17 jackpot #39,978");
#elif defined(SOST_DEVNET_FORKS)
    CHECK(V17_HEIGHT == 60, "DEVNET V17_HEIGHT == 60");
#else
    CHECK(V17_HEIGHT == INT64_MAX && !v17_active_at(INT64_MAX - 1), "TESTNET V17 inactive");
#endif
}

static void test_funding() {
    SECTION("3. jackpot funding: H first, then J, same payment");
    if (V17_HEIGHT == INT64_MAX) return;
    // first V17 jackpot height on this build
    int64_t JH = V17_HEIGHT;
    while (!is_hist_jackpot_height(JH)) ++JH;
    // frozen example: prize 100, H 30, J 500 -> 30 from H + 70 from J -> H 0, J 430
    {
        auto f = v17::jackpot_funding(JH, true, 30 * SOST, 500 * SOST, 0);
        CHECK(f.ok && f.paid && f.prize == 100 * SOST && f.h_part == 30 * SOST && f.j_part == 70 * SOST &&
              f.h_after == 0 && f.j_after_payment == 430 * SOST && !f.underfunded && f.rollover_after == 0,
              "owner example: 100 = 30 H + 70 J -> H 0, J 430");
    }
    {
        auto f = v17::jackpot_funding(JH, true, 66'474 * SOST, 0, 0);
        CHECK(f.ok && f.h_part == BASE && f.j_part == 0 && f.h_after == 66'374 * SOST, "H-only (J = 0)");
    }
    {
        auto f = v17::jackpot_funding(JH, true, 66'474 * SOST, 900 * SOST, 0);
        CHECK(f.ok && f.h_part == BASE && f.j_part == 0 && f.j_after_payment == 900 * SOST,
              "H covers the prize: J untouched even when J > 0 (H first)");
    }
    {
        auto f = v17::jackpot_funding(JH, true, 0, 500 * SOST, 0);
        CHECK(f.ok && f.h_part == 0 && f.j_part == BASE && f.j_after_payment == 400 * SOST, "J-only (H = 0)");
    }
    {
        auto f = v17::jackpot_funding(JH, true, 0, 0, 200 * SOST);
        CHECK(f.ok && !f.paid && f.unfunded && f.payout == 0 && f.rollover_after == 300 * SOST,
              "H = J = 0 with a winner: unfunded, nothing paid, rollover accrues");
    }
    {
        auto f = v17::jackpot_funding(JH, true, 10 * SOST, 20 * SOST, 0);
        CHECK(f.ok && f.paid && f.underfunded && f.payout == 30 * SOST && f.h_part == 10 * SOST &&
              f.j_part == 20 * SOST && f.h_after == 0 && f.j_after_payment == 0 && f.rollover_after == 0,
              "underfunded H+J < prize: pay everything (H then J), rollover reset");
    }
    {
        auto f = v17::jackpot_funding(JH, false, 1000 * SOST, 1000 * SOST, 0);
        CHECK(f.ok && !f.paid && f.rollover_after == BASE && f.payout == 0, "no eligible winner: rollover +BASE");
        auto f2 = v17::jackpot_funding(JH, false, 1000 * SOST, 1000 * SOST, CAP - BASE);
        CHECK(f2.ok && f2.rollover_after == CAP - BASE, "rollover clamps at CAP - BASE (400)");
        auto f3 = v17::jackpot_funding(JH, true, 0, 1000 * SOST, CAP - BASE);
        CHECK(f3.ok && f3.prize == CAP && f3.j_part == CAP && f3.rollover_after == 0, "cap 500 paid from J after rollovers");
        auto f4 = v17::jackpot_funding(JH, true, 120 * SOST, 1000 * SOST, 300 * SOST);
        CHECK(f4.ok && f4.prize == 400 * SOST && f4.h_part == 120 * SOST && f4.j_part == 280 * SOST,
              "rollover prize 400 split 120 H + 280 J");
    }
    // impossible states
    CHECK(!v17::jackpot_funding(JH, true, -1, 0, 0).ok, "negative H rejected");
    CHECK(!v17::jackpot_funding(JH, true, 0, -1, 0).ok, "negative J rejected");
    CHECK(!v17::jackpot_funding(JH, true, 0, 0, -1).ok, "negative rollover rejected");
    CHECK(!v17::jackpot_funding(JH, true, 0, 0, CAP - BASE + 1).ok, "rollover above CAP-BASE rejected");
    CHECK(!v17::jackpot_funding(JH, true, SUPPLY_MAX_STOCKS + 1, 0, 0).ok, "H above supply rejected");
    // non-jackpot V17 height
    {
        auto f = v17::jackpot_funding(JH + 1, true, 1000 * SOST, 1000 * SOST, 0);
        CHECK(f.ok && !f.is_jackpot_block && f.payout == 0, "non-jackpot V17 height: no event");
    }
    // randomized properties
    std::mt19937_64 rng(4242);
    int64_t bad = 0;
    for (int i = 0; i < 300000; ++i) {
        const int64_t H = (int64_t)(rng() % (700 * SOST)) * (rng() % 4 == 0 ? 0 : 1);
        const int64_t J = (int64_t)(rng() % (700 * SOST)) * (rng() % 4 == 0 ? 0 : 1);
        const int64_t R = (int64_t)(rng() % 5) * BASE;
        const bool w = rng() % 5 != 0;
        auto f = v17::jackpot_funding(JH, w, H, J, R);
        const int64_t prize = std::min(BASE + R, CAP);
        bool ok = f.ok && f.prize == prize;
        if (w && H + J > 0) {
            ok = ok && f.payout == std::min(prize, H + J) && f.h_part == std::min(f.payout, H) &&
                 f.j_part == f.payout - f.h_part && f.h_after == H - f.h_part && f.j_after_payment == J - f.j_part &&
                 f.rollover_after == 0 && (f.payout == prize || f.payout == H + J);
        } else {
            ok = ok && f.payout == 0 && f.h_part == 0 && f.j_part == 0 && f.rollover_after == std::min(R + BASE, CAP - BASE);
        }
        if (!ok) ++bad;
    }
    CHECK(bad == 0, "300,000 random (H, J, rollover, winner): H-first rule, exact parts, rollover rule");
}

static void test_j_transition() {
    SECTION("4. J_BALANCE transition");
    if (V17_HEIGHT == INT64_MAX) return;
    const int64_t pre = V17_HEIGHT - 1, at = V17_HEIGHT;
    CHECK(v17::j_transition(pre, 0, 785'100'863, 0).ok && v17::j_transition(pre, 0, 785'100'863, 0).j_after == 0,
          "pre-V17: J stays 0, nothing allocated");
    CHECK(!v17::j_transition(pre, 5, 785'100'863, 0).ok, "pre-V17: non-zero J is impossible");
    CHECK(!v17::j_transition(pre, 0, 785'100'863, 1).ok, "pre-V17: any J payment is impossible");
    auto t = v17::j_transition(at, 0, 785'100'863, 0);
    CHECK(t.ok && t.j_alloc == 39'255'043 && t.j_after == 39'255'043, "activation block allocates 5% into J");
    auto t2 = v17::j_transition(at + 1, 100, 785'100'863, 100);
    CHECK(t2.ok && t2.j_after == 39'255'043, "payment uses the PRE-block balance; allocation added after");
    CHECK(!v17::j_transition(at + 1, 100, 785'100'863, 101).ok, "paying more than J_before is impossible");
    CHECK(!v17::j_transition(at + 1, -1, 785'100'863, 0).ok, "negative J impossible");
    CHECK(v17::jackpot_event_paid(at, true, 0) && v17::jackpot_event_paid(at, false, 1) &&
          !v17::jackpot_event_paid(at, false, 0) && !v17::jackpot_event_paid(pre, false, 1) &&
          v17::jackpot_event_paid(pre, true, 0), "paid predicate: tx[1] JACKPOT, or (>= V17) a coinbase J output");
}

// ---------------------------------------------------------------------------
// Coinbase builders + honest-node context
// ---------------------------------------------------------------------------
static Transaction make_cb(int64_t h, const std::vector<TxOutput>& outs) {
    Transaction tx; tx.version = 1; tx.tx_type = TX_TYPE_COINBASE;
    TxInput in; in.prev_txid = Hash256{}; in.prev_index = 0xFFFFFFFFu; in.signature.fill(0); in.pubkey.fill(0);
    for (int i = 0; i < 8; ++i) in.signature[i] = (uint8_t)(((uint64_t)h >> (8 * i)) & 0xFF);
    tx.inputs.push_back(in);
    tx.outputs = outs;
    return tx;
}
static TxOutput O(int64_t amt, uint8_t type, const PubKeyHash& p) { TxOutput o; o.amount = amt; o.type = type; o.pubkey_hash = p; return o; }

struct HonestV17 {
    Phase2CoinbaseContext ctx;
    Transaction cb;
    int64_t pending_after{0}, j_after{0};
};
// Builds what an honest V17 node/miner builds for height h.
static HonestV17 honest_v17(int64_t h, int64_t subsidy, int64_t fees, int64_t pending_before, bool dtd_eligible,
                            const PubKeyHash& miner, const PubKeyHash& dtd_winner,
                            int64_t j_before, int64_t j_payout, const PubKeyHash& jp_winner) {
    HonestV17 r;
    auto amt = v17::coinbase_amounts(subsidy, fees);
    auto& c = r.ctx;
    c.phase2_height = V11_PHASE2_HEIGHT; c.triggered = true; c.pending_before = pending_before;
    c.paid_out = v17::dtd_paid_out(dtd_eligible, amt.dtd_subsidy, pending_before);
    std::vector<TxOutput> outs = {O(amt.miner_total, OUT_COINBASE_MINER, miner)};
    if (c.paid_out) {
        c.expected_winner_pkh = dtd_winner;
        c.lottery_payout = amt.dtd_subsidy + pending_before;
        c.expected_pending_after = 0;
        outs.push_back(O(c.lottery_payout, OUT_COINBASE_LOTTERY, dtd_winner));
    } else {
        c.expected_pending_after = pending_before + amt.dtd_subsidy;
    }
    if (j_payout > 0) outs.push_back(O(j_payout, OUT_COINBASE_JACKPOT, jp_winner));
    c.j_before = j_before; c.jackpot_j_payout = j_payout; c.jackpot_winner_pkh = jp_winner;
    c.expected_j_after = j_before - j_payout + amt.jackpot_j;
    r.cb = make_cb(h, outs);
    r.pending_after = c.expected_pending_after;
    r.j_after = c.expected_j_after;
    return r;
}
// Pre-V17 (V15/V16 rules): every block triggered, 50/50 of subsidy + fees.
static void honest_pre(int64_t h, int64_t subsidy, int64_t fees, int64_t pending_before, bool dtd_eligible,
                       const PubKeyHash& miner, const PubKeyHash& dtd_winner,
                       Phase2CoinbaseContext& c, Transaction& cb) {
    auto sp = lottery::phase2_coinbase_split(subsidy + fees);
    c = Phase2CoinbaseContext{};
    c.phase2_height = V11_PHASE2_HEIGHT; c.triggered = true; c.pending_before = pending_before;
    std::vector<TxOutput> outs = {O(sp.miner_share, OUT_COINBASE_MINER, miner)};
    if (dtd_eligible) {
        c.paid_out = true; c.expected_winner_pkh = dtd_winner;
        c.lottery_payout = sp.lottery_share + pending_before; c.expected_pending_after = 0;
        outs.push_back(O(c.lottery_payout, OUT_COINBASE_LOTTERY, dtd_winner));
    } else {
        c.expected_pending_after = pending_before + sp.lottery_share;
    }
    cb = make_cb(h, outs);
}

static bool cb_ok(const Transaction& cb, int64_t h, int64_t sub, int64_t fees, const Phase2CoinbaseContext& c) {
    return ValidateCoinbaseConsensus(cb, h, sub, fees, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh(), &c).ok;
}

static void test_coinbase_boundary_and_adversarial() {
    SECTION("5. coinbase validator: boundary V17-2..V17+1, fee/zero-fee, adversarial");
    if (V17_HEIGHT == INT64_MAX) return;
    const PubKeyHash M = P(0x11), W = P(0x22), JW = P(0x33);
    for (int64_t h = V17_HEIGHT - 2; h <= V17_HEIGHT + 1; ++h) {
        const int64_t sub = sost_subsidy_stocks(h);
        for (int64_t fees : {(int64_t)0, (int64_t)1, (int64_t)12'345, (int64_t)99'999'999}) {
            for (bool elig : {false, true}) {
                char m[160];
                Phase2CoinbaseContext pc; Transaction pcb;
                honest_pre(h, sub, fees, 1000, elig, M, W, pc, pcb);
                auto v = honest_v17(h, sub, fees, 1000, elig, M, W, 0, 0, JW);
                const bool v17h = v17_active_at(h);
                std::snprintf(m, sizeof m, "h=%lld fees=%lld elig=%d: %s 50/50 coinbase", (long long)h,
                              (long long)fees, (int)elig, v17h ? "rejects" : "accepts");
                CHECK(cb_ok(pcb, h, sub, fees, pc) == !v17h, m);
                std::snprintf(m, sizeof m, "h=%lld fees=%lld elig=%d: %s 80/15/5 coinbase", (long long)h,
                              (long long)fees, (int)elig, v17h ? "accepts" : "rejects");
                CHECK(cb_ok(v.cb, h, sub, fees, v.ctx) == v17h, m);
                if (v17h) {
                    std::snprintf(m, sizeof m, "h=%lld fees=%lld: exact invariant sum+dPending+dJ == subsidy+fees", (long long)h, (long long)fees);
                    int64_t sum = 0; for (auto& o : v.cb.outputs) sum += o.amount;
                    CHECK(v17::v17_block_invariant(sub, fees, sum, 1000, v.pending_after, 0, v.j_after), m);
                }
            }
        }
    }
    // Adversarial mutations at V17 (DTD payout block with a J-funded jackpot output).
    const int64_t h = V17_HEIGHT + 7, sub = sost_subsidy_stocks(h), fees = 5000;
    auto base = honest_v17(h, sub, fees, 777, true, M, W, 50 * SOST, 20 * SOST, JW);
    CHECK(cb_ok(base.cb, h, sub, fees, base.ctx), "honest V17 coinbase MINER+LOTTERY+JACKPOT accepted");
    auto mut = [&](const char* what, auto f) {
        HonestV17 x = base; f(x);
        CHECK(!cb_ok(x.cb, h, sub, fees, x.ctx), what);
    };
    mut("miner +1 stock rejected", [](HonestV17& x){ x.cb.outputs[0].amount += 1; });
    mut("miner -1 stock rejected", [](HonestV17& x){ x.cb.outputs[0].amount -= 1; });
    mut("miner keeps the 5% J share rejected", [&](HonestV17& x){ x.cb.outputs[0].amount += v17::subsidy_split(sub).jackpot_j; });
    mut("fees split 15% to DTD rejected", [&](HonestV17& x){ x.cb.outputs[0].amount -= fees * 15 / 100; x.cb.outputs[1].amount += fees * 15 / 100; });
    mut("DTD amount +1 rejected", [](HonestV17& x){ x.cb.outputs[1].amount += 1; });
    mut("DTD wrong winner rejected", [](HonestV17& x){ x.cb.outputs[1].pubkey_hash = P(0x99); });
    mut("J amount +1 rejected", [](HonestV17& x){ x.cb.outputs[2].amount += 1; });
    mut("J amount -1 rejected", [](HonestV17& x){ x.cb.outputs[2].amount -= 1; });
    mut("J wrong winner rejected", [](HonestV17& x){ x.cb.outputs[2].pubkey_hash = P(0x98); });
    mut("J output missing rejected", [](HonestV17& x){ x.cb.outputs.pop_back(); });
    mut("J output duplicated rejected", [](HonestV17& x){ x.cb.outputs.push_back(x.cb.outputs[2]); });
    mut("J output typed as LOTTERY rejected", [](HonestV17& x){ x.cb.outputs[2].type = OUT_COINBASE_LOTTERY; });
    mut("J output typed as TRANSFER rejected", [](HonestV17& x){ x.cb.outputs[2].type = OUT_TRANSFER; });
    mut("J before LOTTERY (order) rejected", [](HonestV17& x){ std::swap(x.cb.outputs[1], x.cb.outputs[2]); });
    mut("J payload rejected", [](HonestV17& x){ x.cb.outputs[2].payload = {1}; });
    mut("Gold Vault output appended rejected", [](HonestV17& x){ x.cb.outputs.push_back(O(1, OUT_COINBASE_GOLD, jackpot::reserve_gold_pkh())); });
    mut("context J payout > J_before rejected", [](HonestV17& x){ x.ctx.jackpot_j_payout = x.ctx.j_before + 1; x.cb.outputs[2].amount = x.ctx.j_before + 1; });
    mut("context expected_j_after wrong rejected", [](HonestV17& x){ x.ctx.expected_j_after += 1; });
    mut("context expected_pending_after wrong rejected", [](HonestV17& x){ x.ctx.expected_pending_after += 1; });
    CHECK(!ValidateCoinbaseConsensus(base.cb, h, sub, fees, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh(), nullptr).ok,
          "V17 coinbase without chain context rejected");
    // J output when none is due
    {
        auto x = honest_v17(h, sub, fees, 0, false, M, W, 50 * SOST, 0, JW);
        CHECK(cb_ok(x.cb, h, sub, fees, x.ctx), "UPDATE shape (no DTD, no J) accepted");
        x.cb.outputs.push_back(O(SOST, OUT_COINBASE_JACKPOT, JW));
        CHECK(!cb_ok(x.cb, h, sub, fees, x.ctx), "J output when no J payout is due rejected");
    }
    // DTD and jackpot winner identical / different
    {
        auto same = honest_v17(h, sub, fees, 0, true, M, W, 50 * SOST, 7 * SOST, W);
        auto diff = honest_v17(h, sub, fees, 0, true, M, W, 50 * SOST, 7 * SOST, JW);
        CHECK(cb_ok(same.cb, h, sub, fees, same.ctx) && cb_ok(diff.cb, h, sub, fees, diff.ctx),
              "DTD winner == jackpot winner and DTD winner != jackpot winner both valid");
        auto selfw = honest_v17(h, sub, fees, 0, true, M, M, 50 * SOST, 7 * SOST, M);
        CHECK(cb_ok(selfw.cb, h, sub, fees, selfw.ctx), "miner == DTD winner == jackpot winner valid (3 outputs, same pkh)");
    }
    // zero DTD amount (tiny end-of-schedule subsidy): UPDATE shape, not a 0-value output
    {
        auto x = honest_v17(h, 6, 0, 0, true, M, W, 0, 0, JW);
        CHECK(!x.ctx.paid_out && x.cb.outputs.size() == 1 && cb_ok(x.cb, h, 6, 0, x.ctx),
              "subsidy 6 (dtd 0, pending 0): no zero-value DTD output, UPDATE shape valid");
    }
}

// ---------------------------------------------------------------------------
// Block-level jackpot rule (H via TX_TYPE_JACKPOT, J via coinbase output)
// ---------------------------------------------------------------------------
static std::vector<jackpot::ReserveUtxo> mk_reserve(std::initializer_list<int64_t> amts) {
    std::vector<jackpot::ReserveUtxo> r; uint8_t k = 1;
    for (int64_t a : amts) { jackpot::ReserveUtxo u; u.height = 100 + k; u.txid.fill(k); u.vout = 1; u.amount = a; r.push_back(u); ++k; }
    std::sort(r.begin(), r.end(), jackpot::reserve_utxo_less);
    return r;
}

static void test_block_jackpot_rule() {
    SECTION("6. block jackpot rule (H tx + J coinbase output)");
    if (V17_HEIGHT == INT64_MAX) return;
    int64_t JH = V17_HEIGHT; while (!is_hist_jackpot_height(JH)) ++JH;
    const PubKeyHash M = P(0x11), JW = P(0x33), SINK = jackpot::reserve_gold_pkh();
    auto run = [&](int64_t H_total, std::initializer_list<int64_t> amts, int64_t J, int64_t R, bool winner,
                   const char* label, int64_t exp_h, int64_t exp_j) {
        auto res = mk_reserve(amts);
        CHECK(jackpot::reserve_balance(res) == H_total, "reserve fixture");
        auto f = v17::jackpot_funding(JH, winner, H_total, J, R);
        std::vector<Transaction> txs;
        std::vector<TxOutput> cbo = {O(SOST, OUT_COINBASE_MINER, M)};
        if (f.j_part > 0) cbo.push_back(O(f.j_part, OUT_COINBASE_JACKPOT, JW));
        txs.push_back(make_cb(JH, cbo));
        Transaction jtx;
        if (f.h_part > 0) { CHECK(jackpot::build_jackpot_tx_for_payout(f.h_part, JW, res, SINK, jtx), "H tx builds"); txs.push_back(jtx); }
        char m[160];
        std::snprintf(m, sizeof m, "%s: parts H=%lld J=%lld", label, (long long)f.h_part, (long long)f.j_part);
        CHECK(f.h_part == exp_h && f.j_part == exp_j, m);
        std::snprintf(m, sizeof m, "%s: honest block accepted", label);
        CHECK(jackpot::validate_block_jackpot_v17(txs, f, JW, res, SINK).ok, m);
        if (f.h_part > 0) {
            // H tx value conservation: inputs == outputs
            int64_t in = 0, out = 0; std::set<std::pair<int,uint32_t>> dummy;
            for (auto& i : txs[1].inputs) for (auto& u : res) if (u.txid == i.prev_txid && u.vout == i.prev_index) in += u.amount;
            for (auto& o : txs[1].outputs) out += o.amount;
            std::snprintf(m, sizeof m, "%s: H tx is value-conserving (in %lld == out %lld)", label, (long long)in, (long long)out);
            CHECK(in == out && txs[1].outputs[0].amount == f.h_part, m);
            auto t2 = txs; t2.erase(t2.begin() + 1);
            std::snprintf(m, sizeof m, "%s: missing H tx rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t2, f, JW, res, SINK).ok, m);
            auto t3 = txs; t3[1].outputs[0].amount += 1;
            std::snprintf(m, sizeof m, "%s: H tx amount +1 rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t3, f, JW, res, SINK).ok, m);
            auto t4 = txs; t4[1].outputs[0].pubkey_hash = P(0x77);
            std::snprintf(m, sizeof m, "%s: H tx wrong winner rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t4, f, JW, res, SINK).ok, m);
            // H tx carrying the full prize (J part smuggled into the reserve spend)
            if (f.j_part > 0) {
                Transaction big;
                if (jackpot::build_jackpot_tx_for_payout(f.payout, JW, res, SINK, big)) {
                    auto t5 = txs; t5[1] = big;
                    CHECK(!jackpot::validate_block_jackpot_v17(t5, f, JW, res, SINK).ok, "H tx paying H+J from reserve rejected");
                }
            }
        } else {
            Transaction fake;
            if (jackpot::build_jackpot_tx_for_payout(BASE, JW, mk_reserve({1000 * SOST}), SINK, fake)) {
                auto t2 = txs; t2.push_back(fake);
                std::snprintf(m, sizeof m, "%s: jackpot tx when H part is 0 rejected", label);
                CHECK(!jackpot::validate_block_jackpot_v17(t2, f, JW, res, SINK).ok, m);
            }
        }
        if (f.j_part > 0) {
            auto t6 = txs; t6[0].outputs.pop_back();
            std::snprintf(m, sizeof m, "%s: missing J output rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t6, f, JW, res, SINK).ok, m);
            auto t7 = txs; t7[0].outputs.back().amount -= 1;
            std::snprintf(m, sizeof m, "%s: J output -1 rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t7, f, JW, res, SINK).ok, m);
        } else {
            auto t8 = txs; t8[0].outputs.push_back(O(SOST, OUT_COINBASE_JACKPOT, JW));
            std::snprintf(m, sizeof m, "%s: J output when J part is 0 rejected", label);
            CHECK(!jackpot::validate_block_jackpot_v17(t8, f, JW, res, SINK).ok, m);
        }
    };
    run(150 * SOST, {100 * SOST, 50 * SOST}, 0, 0, true, "H-only, J=0", BASE, 0);
    run(150 * SOST, {100 * SOST, 50 * SOST}, 300 * SOST, 0, true, "H-only, J>0 untouched", BASE, 0);
    run(30 * SOST, {10 * SOST, 20 * SOST}, 500 * SOST, 0, true, "H+J mixed (owner example)", 30 * SOST, 70 * SOST);
    run(0, {}, 500 * SOST, 0, true, "J-only, H=0", 0, BASE);
    run(0, {}, 0, 0, true, "H=0 and J=0: unfunded", 0, 0);
    run(10 * SOST, {10 * SOST}, 20 * SOST, 0, true, "insufficient H+J: pays all", 10 * SOST, 20 * SOST);
    run(150 * SOST, {150 * SOST}, 500 * SOST, 0, false, "no eligible winner", 0, 0);
    run(100 * SOST, {60 * SOST, 40 * SOST}, 1000 * SOST, CAP - BASE, true, "cap 500 after rollovers", 100 * SOST, 400 * SOST);
    // J output outside the coinbase
    {
        auto f = v17::jackpot_funding(JH, true, 0, 500 * SOST, 0);
        std::vector<Transaction> txs = {make_cb(JH, {O(SOST, OUT_COINBASE_MINER, M), O(f.j_part, OUT_COINBASE_JACKPOT, JW)})};
        Transaction t; t.version = 1; t.tx_type = TX_TYPE_STANDARD; t.outputs.push_back(O(1, OUT_COINBASE_JACKPOT, JW));
        txs.push_back(t);
        CHECK(!jackpot::validate_block_jackpot_v17(txs, f, JW, {}, SINK).ok, "OUT_COINBASE_JACKPOT in a non-coinbase tx rejected");
    }
    // impossible pre-block state
    {
        v17::JackpotFunding bad; bad.ok = false;
        std::vector<Transaction> txs = {make_cb(JH, {O(SOST, OUT_COINBASE_MINER, M)})};
        CHECK(!jackpot::validate_block_jackpot_v17(txs, bad, JW, {}, SINK).ok, "impossible funding state rejects the block");
    }
    // pre-V17 canonical builder unchanged by the refactor (payout path identical)
    {
        auto res = mk_reserve({70 * SOST, 80 * SOST});
        Transaction a, b;
        const int64_t preJ = HIST_JACKPOT_FIRST_HEIGHT;
        bool ba = jackpot::build_canonical_jackpot_tx(preJ, true, JW, 150 * SOST, 0, res, SINK, a);
        bool bb = jackpot::build_jackpot_tx_for_payout(BASE, JW, res, SINK, b);
        std::vector<Byte> ra, rb; a.Serialize(ra, nullptr); b.Serialize(rb, nullptr);
        CHECK(ba && bb && ra == rb && jackpot::jackpot_tx_matches_canonical(a, preJ, true, JW, 150 * SOST, 0, res, SINK),
              "pre-V17 canonical jackpot tx byte-identical to the payout builder");
    }
}

// ---------------------------------------------------------------------------
// DTD eligibility (unchanged helper) driven through V17 coinbases
// ---------------------------------------------------------------------------
static std::vector<lottery::LotteryMinedBlockView> hist(std::vector<std::pair<int64_t, uint8_t>> v) {
    std::vector<lottery::LotteryMinedBlockView> out;
    for (auto& x : v) { lottery::LotteryMinedBlockView b; b.height = x.first; b.miner_pkh = P(x.second); b.block_hash.fill((uint8_t)(x.first & 0xFF)); b.block_hash[1] = (uint8_t)(x.first >> 8); out.push_back(b); }
    return out;
}
static void test_dtd_scenarios() {
    SECTION("7. DTD eligibility scenarios (helper unchanged) -> V17 coinbase");
#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  (mainnet-height scenarios skipped on this build)\n");
    return;
#else
    const int64_t h = 40000 + 10;   // V17, inside V16 DTD rules (288 recency, 6 cooldown)
    const int64_t sub = sost_subsidy_stocks(h);
    auto elig = [&](const std::vector<lottery::LotteryMinedBlockView>& hv) {
        return lottery::compute_lottery_eligibility_set(hv, h, PubKeyHash{}, lottery_exclusion_window_at(h));
    };
    auto check_cb = [&](const std::vector<lottery::LotteryMinedBlockView>& hv, const char* label, size_t expect_n) {
        auto e = elig(hv);
        char m[160];
        std::snprintf(m, sizeof m, "%s: eligible count %zu (expected %zu)", label, e.size(), expect_n);
        CHECK(e.size() == expect_n, m);
        PubKeyHash w{};
        if (!e.empty()) { int64_t wi = lottery::select_lottery_winner_index_from_history(e, hv, h); w = e[(size_t)wi].pkh; }
        auto v = honest_v17(h, sub, 0, 0, !e.empty(), P(0xEE), w, 0, 0, PubKeyHash{});
        std::snprintf(m, sizeof m, "%s: V17 coinbase (%s) valid", label, v.ctx.paid_out ? "PAYOUT" : "UPDATE");
        CHECK(cb_ok(v.cb, h, sub, 0, v.ctx), m);
        if (!e.empty()) {
            auto bad = v; bad.cb.outputs[1].pubkey_hash = P(0xFE);
            bad.ctx.expected_winner_pkh = w;
            std::snprintf(m, sizeof m, "%s: paying a non-winner rejected", label);
            CHECK(!cb_ok(bad.cb, h, sub, 0, bad.ctx), m);
        }
        return e;
    };
    // none: only stale miners (outside the 288 recency window)
    check_cb(hist({{h - 1000, 1}, {h - 900, 2}}), "no eligible (stale)", 0);
    // one
    check_cb(hist({{h - 50, 1}}), "one eligible", 1);
    // multiple
    check_cb(hist({{h - 50, 1}, {h - 40, 2}, {h - 30, 3}}), "multiple eligible", 3);
    // cooldown: miner 1 mined at h-3 (excluded), miner 2 at h-20
    {
        auto e = check_cb(hist({{h - 20, 2}, {h - 3, 1}}), "cooldown excludes h-3 winner", 1);
        CHECK(!e.empty() && e[0].pkh == P(2), "cooldown: the remaining candidate is miner 2");
    }
    // fallback: everyone in cooldown -> retried without cooldown
    {
        auto e = check_cb(hist({{h - 2, 1}, {h - 1, 1}}), "fallback (all in cooldown)", 1);
        CHECK(!e.empty() && e[0].pkh == P(1), "fallback: cooldown retry returns miner 1");
    }
    // anti-dominance OFF (< 11 miners in window): a 50% miner stays eligible
    {
        std::vector<std::pair<int64_t, uint8_t>> v;
        for (int i = 0; i < 100; ++i) v.push_back({h - 200 + i, (uint8_t)(i % 2 == 0 ? 1 : (2 + (i / 2) % 5))});
        auto e = check_cb(hist(v), "anti-dominance off (6 miners)", 6);
        bool has1 = false; for (auto& x : e) has1 |= (x.pkh == P(1));
        CHECK(has1, "anti-dominance off: dominant miner 1 still eligible");
    }
    // anti-dominance ON (>= 11 distinct miners): miner with >= 10% excluded
    {
        std::vector<std::pair<int64_t, uint8_t>> v;
        for (int i = 0; i < 120; ++i) v.push_back({h - 200 + i, (uint8_t)(i % 4 == 0 ? 1 : (10 + i % 15))});
        auto e = elig(hist(v));
        bool has1 = false; for (auto& x : e) has1 |= (x.pkh == P(1));
        CHECK(!has1 && !e.empty(), "anti-dominance on (16 miners): dominant miner 1 excluded");
        check_cb(hist(v), "anti-dominance on: coinbase", e.size());
    }
#endif
}

// ---------------------------------------------------------------------------
// UTXO-level chain simulation with the real consensus helpers.
// ---------------------------------------------------------------------------
struct SimStats {
    int64_t blocks = 0, fee_blocks = 0, zero_fee_blocks = 0, dtd_paid = 0, dtd_update = 0;
    int64_t pre_jp_paid = 0, v17_h_only = 0, v17_mixed = 0, v17_j_only = 0, v17_miss = 0, v17_cap = 0;
    int64_t v17_underfunded = 0, v17_same_winner = 0, v17_diff_winner = 0, invariant_fail = 0, validate_fail = 0;
    int64_t mutation_rejects = 0, mutation_total = 0;
};
struct SimBlock {
    int64_t height = 0;
    std::vector<Transaction> txs;
    BlockUndo undo;
    int64_t pending_after = 0, j_after = 0, subsidy = 0;
    OutPoint fee_coin_before{}; int64_t fee_amt_before = 0;
};
struct Sim {
    UtxoSet utxo;
    std::vector<SimBlock> chain;
    int64_t start_h = 0, seed_value = 0, emitted = 0;
    uint64_t seed = 1;
    std::set<int64_t> forced_miss;     // jackpot heights with no eligible jackpot winner
    OutPoint fee_coin{}; int64_t fee_amt = 0;
    SimStats st;

    int64_t pending() const { return chain.empty() ? 0 : chain.back().pending_after; }
    int64_t J() const { return chain.empty() ? 0 : chain.back().j_after; }
    int64_t tip() const { return chain.empty() ? start_h - 1 : chain.back().height; }
    int64_t H() const { return jackpot::reserve_balance(jackpot::discover_reserve_utxos(utxo, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh())); }

    void init(int64_t start, uint64_t s, std::initializer_list<int64_t> reserve) {
        start_h = start; seed = s;
        uint8_t k = 1;
        for (int64_t a : reserve) {
            OutPoint op; op.txid.fill(0xC0); op.txid[1] = k; op.index = 1;
            UTXOEntry e; e.amount = a; e.type = OUT_COINBASE_GOLD; e.pubkey_hash = jackpot::reserve_gold_pkh(); e.height = 1; e.is_coinbase = true;
            utxo.AddUTXO(op, e); seed_value += a; ++k;
        }
        OutPoint op; op.txid.fill(0xF0); op.index = 0;
        UTXOEntry e; e.amount = 100000 * SOST; e.type = OUT_TRANSFER; e.pubkey_hash = P(0xA0); e.height = 1;
        utxo.AddUTXO(op, e); seed_value += e.amount;
        fee_coin = op; fee_amt = e.amount;
    }
    bool paid_at(int64_t h) const {
        if (h < start_h) return true;                       // events before the simulated window: paid
        const size_t i = (size_t)(h - start_h);
        if (i >= chain.size()) return false;
        const auto& b = chain[i];
        const bool tx1 = b.txs.size() >= 2 && b.txs[1].tx_type == TX_TYPE_JACKPOT;
        return v17::jackpot_event_paid(h, tx1, v17::count_jackpot_j_outputs(b.txs[0]));
    }
    // Build, validate, connect the next block. Deterministic in (seed, height, state).
    bool step(bool mutate_checks) {
        const int64_t h = tip() + 1;
        std::mt19937_64 rng(seed * 1000003ULL + (uint64_t)h);
        const int64_t sub = sost_subsidy_stocks(h);
        const PubKeyHash miner = P((uint8_t)(1 + rng() % 6));
        const bool dtd_elig = (rng() % 10) < 7;
        const PubKeyHash dtd_w = P((uint8_t)(1 + rng() % 6));
        const PubKeyHash jp_w = P((uint8_t)(1 + rng() % 6));
        const bool jp_winner = !forced_miss.count(h);
        // optional fee-paying tx (unsigned: ConnectBlock does not verify signatures)
        std::vector<Transaction> extra;
        int64_t fees = 0;
        if (rng() % 2 == 0) {
            fees = 1 + (int64_t)(rng() % 5'000'000);
            Transaction t; t.version = 1; t.tx_type = TX_TYPE_STANDARD;
            TxInput in; in.prev_txid = fee_coin.txid; in.prev_index = fee_coin.index; in.signature.fill(0); in.pubkey.fill(0);
            t.inputs.push_back(in);
            t.outputs.push_back(O(fee_amt - fees, OUT_TRANSFER, P(0xA0)));
            extra.push_back(t);
        }
        SimBlock nb; nb.height = h; nb.subsidy = sub; nb.fee_coin_before = fee_coin; nb.fee_amt_before = fee_amt;
        Phase2CoinbaseContext ctx; Transaction cb; Transaction jtx; bool has_jtx = false;
        const auto sorted = jackpot::discover_reserve_utxos(utxo, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh());
        const int64_t Hb = jackpot::reserve_balance(sorted);
        const int64_t R = jackpot::derive_rollover_before(h, [this](int64_t x){ return paid_at(x); });
        if (v17_active_at(h)) {
            auto f = v17::jackpot_funding(h, jp_winner, Hb, J(), R);
            if (!f.ok) { ++st.validate_fail; return false; }
            auto v = honest_v17(h, sub, fees, pending(), dtd_elig, miner, dtd_w, J(), f.j_part, jp_w);
            ctx = v.ctx; cb = v.cb;
            if (f.h_part > 0) has_jtx = jackpot::build_jackpot_tx_for_payout(f.h_part, jp_w, sorted, jackpot::reserve_gold_pkh(), jtx);
            if (f.is_jackpot_block) {
                if (!f.paid) ++st.v17_miss;
                else if (f.j_part == 0) ++st.v17_h_only;
                else if (f.h_part == 0) ++st.v17_j_only;
                else ++st.v17_mixed;
                if (f.paid && f.prize == CAP) ++st.v17_cap;
                if (f.underfunded) ++st.v17_underfunded;
                if (f.paid && ctx.paid_out) { if (dtd_w == jp_w) ++st.v17_same_winner; else ++st.v17_diff_winner; }
            }
            std::vector<Transaction> txs = {cb};
            if (has_jtx) txs.push_back(jtx);
            for (auto& t : extra) txs.push_back(t);
            if (!jackpot::validate_block_jackpot_v17(txs, f, jp_w, sorted, jackpot::reserve_gold_pkh()).ok) { ++st.validate_fail; return false; }
            if (mutate_checks && f.is_jackpot_block && f.paid) {
                // a few adversarial copies of this jackpot block must all be rejected
                auto try_bad = [&](std::vector<Transaction> b, const Phase2CoinbaseContext& c) {
                    ++st.mutation_total;
                    const bool rej = !jackpot::validate_block_jackpot_v17(b, f, jp_w, sorted, jackpot::reserve_gold_pkh()).ok ||
                                     !ValidateCoinbaseConsensus(b[0], h, sub, fees, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh(), &c).ok;
                    if (rej) ++st.mutation_rejects;
                };
                if (f.j_part > 0) { auto b = txs; b[0].outputs.back().amount += 1; try_bad(b, ctx); }
                if (f.j_part > 0) { auto b = txs; b[0].outputs.pop_back(); try_bad(b, ctx); }
                if (f.h_part > 0) { auto b = txs; b.erase(b.begin() + 1); try_bad(b, ctx); }
                { auto b = txs; b[0].outputs[0].amount += 1; try_bad(b, ctx); }
            }
            nb.txs = txs;
            nb.pending_after = v.pending_after; nb.j_after = v.j_after;
            auto jt = v17::j_transition(h, J(), sub, f.j_part);
            if (!jt.ok || jt.j_after != v.j_after) { ++st.validate_fail; return false; }
        } else {
            honest_pre(h, sub, fees, pending(), dtd_elig, miner, dtd_w, ctx, cb);
            std::vector<Transaction> txs = {cb};
            auto r = jackpot::hist_jackpot_apply(h, jp_winner, Hb, R);
            if (jackpot::build_canonical_jackpot_tx(h, jp_winner, jp_w, Hb, R, sorted, jackpot::reserve_gold_pkh(), jtx)) {
                txs.push_back(jtx); ++st.pre_jp_paid;
            }
            (void)r;
            for (auto& t : extra) txs.push_back(t);
            if (!jackpot::validate_block_jackpot(txs, h, sorted, jp_winner, jp_w, Hb, R, jackpot::reserve_gold_pkh()).ok) { ++st.validate_fail; return false; }
            nb.txs = txs;
            nb.pending_after = ctx.expected_pending_after; nb.j_after = 0;
        }
        if (!ValidateCoinbaseConsensus(nb.txs[0], h, sub, fees, jackpot::reserve_gold_pkh(), jackpot::reserve_popc_pkh(), &ctx).ok) {
            ++st.validate_fail; return false;
        }
        std::string err;
        if (!utxo.ConnectBlock(nb.txs, h, nb.undo, &err)) { std::printf("  connect h=%lld: %s\n", (long long)h, err.c_str()); ++st.validate_fail; return false; }
        if (!extra.empty()) {
            Hash256 id{}; extra[0].ComputeTxId(id, nullptr);
            fee_coin.txid = id; fee_coin.index = 0; fee_amt -= fees;
            ++st.fee_blocks;
        } else ++st.zero_fee_blocks;
        if (ctx.paid_out) ++st.dtd_paid; else ++st.dtd_update;
        emitted += sub;
        chain.push_back(std::move(nb));
        ++st.blocks;
        if (utxo.GetTotalValue() + pending() + J() != seed_value + emitted) ++st.invariant_fail;
        return true;
    }
    bool disconnect_tip() {
        if (chain.empty()) return false;
        SimBlock& b = chain.back();
        std::string err;
        if (!utxo.DisconnectBlock(b.txs, b.undo, &err)) return false;
        emitted -= b.subsidy;
        fee_coin = b.fee_coin_before; fee_amt = b.fee_amt_before;
        chain.pop_back();
        return utxo.GetTotalValue() + pending() + J() == seed_value + emitted;
    }
    uint64_t digest() const {
        uint64_t x = 1469598103934665603ULL;
        auto mix = [&](uint64_t v){ x ^= v; x *= 1099511628211ULL; };
        for (const auto& kv : utxo.GetMap()) {
            for (auto c : kv.first.txid) mix(c);
            mix(kv.first.index); mix((uint64_t)kv.second.amount); mix(kv.second.type);
            for (auto c : kv.second.pubkey_hash) mix(c);
        }
        mix((uint64_t)pending()); mix((uint64_t)J());
        return x;
    }
};

static void test_long_simulation() {
    SECTION("8. long UTXO simulation across activation + many jackpot epochs (exact supply)");
#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  (mainnet-height simulation skipped on this build)\n");
    return;
#else
    Sim s;
    s.init(39000, 7, {100 * SOST, 200 * SOST, 150 * SOST, 200 * SOST});   // H = 650 SOST
    // V17 jackpots: 40266 + 288k. Force 5 consecutive misses (k = 6..10) -> cap 500 at k = 11.
    for (int k = 6; k <= 10; ++k) s.forced_miss.insert(40266 + 288 * k);
    s.forced_miss.insert(39402);                                          // one pre-V17 miss too
    bool ok = true;
    for (int i = 0; i < 6000 && ok; ++i) ok = s.step(true);
    char m[200];
    std::snprintf(m, sizeof m, "6,000 blocks 39,000..44,999 connected and validated (validate_fail=%lld)", (long long)s.st.validate_fail);
    CHECK(ok && s.st.validate_fail == 0 && s.tip() == 44999, m);
    std::snprintf(m, sizeof m, "supply exact every block: sum(UTXO)+pending+J == seed+sum(subsidy) (failures %lld)", (long long)s.st.invariant_fail);
    CHECK(s.st.invariant_fail == 0, m);
    std::printf("  stats: blocks=%lld fee=%lld zero-fee=%lld dtd_paid=%lld dtd_update=%lld pre_jp_paid=%lld\n"
                "         v17: H-only=%lld mixed=%lld J-only=%lld miss=%lld cap500=%lld underfunded=%lld same_winner=%lld diff_winner=%lld\n"
                "         mutations rejected %lld/%lld; final H=%lld J=%lld pending=%lld\n",
                (long long)s.st.blocks, (long long)s.st.fee_blocks, (long long)s.st.zero_fee_blocks,
                (long long)s.st.dtd_paid, (long long)s.st.dtd_update, (long long)s.st.pre_jp_paid,
                (long long)s.st.v17_h_only, (long long)s.st.v17_mixed, (long long)s.st.v17_j_only,
                (long long)s.st.v17_miss, (long long)s.st.v17_cap, (long long)s.st.v17_underfunded,
                (long long)s.st.v17_same_winner, (long long)s.st.v17_diff_winner,
                (long long)s.st.mutation_rejects, (long long)s.st.mutation_total,
                (long long)s.H(), (long long)s.J(), (long long)s.pending());
    CHECK(s.st.fee_blocks > 0 && s.st.zero_fee_blocks > 0, "fee-bearing and zero-fee blocks both exercised");
    CHECK(s.st.dtd_paid > 0 && s.st.dtd_update > 0, "DTD payout and DTD rollover (no eligible) both exercised");
    CHECK(s.st.pre_jp_paid > 0, "pre-V17 jackpots paid from H under the unchanged rule");
    CHECK(s.st.v17_h_only > 0 && s.st.v17_mixed > 0 && s.st.v17_j_only > 0, "V17 H-only, H+J mixed, J-only payments exercised");
    CHECK(s.st.v17_miss == 5 && s.st.v17_cap >= 1, "5 forced misses -> rollover -> a 500 SOST cap payout");
    CHECK(s.st.v17_same_winner > 0 && s.st.v17_diff_winner > 0, "DTD/Jackpot same winner and different winners exercised");
    CHECK(s.st.mutation_total > 0 && s.st.mutation_rejects == s.st.mutation_total, "every adversarial jackpot-block mutation rejected");
    CHECK(s.H() == 0 && s.J() > 0, "historical reserve H exhausted; jackpot continues from J");
    // Cross-check J against an independent recomputation from the blocks.
    int64_t j_ref = 0;
    for (const auto& b : s.chain)
        if (v17_active_at(b.height))
            j_ref += v17::subsidy_split(b.subsidy).jackpot_j - v17::coinbase_jackpot_j_paid(b.txs[0]);
    CHECK(j_ref == s.J(), "J_BALANCE == sum(5% allocations) - sum(J outputs) over all V17 blocks");
#endif
}

static void test_reorg_and_rollback() {
    SECTION("9. reorg: disconnect/reconnect across activation and across H/J funding");
#if defined(SOST_DEVNET_FORKS) || defined(SOST_TESTNET_FORKS)
    std::printf("  (mainnet-height reorg skipped on this build)\n");
    return;
#else
    // Branch A: 39,990 .. 40,560 (activation 40,000; jackpots 40,266 H-only and 40,554 mixed).
    Sim s;
    s.init(39990, 101, {100 * SOST, 50 * SOST});   // H = 150: 40266 pays 100 H, 40554 pays 50 H + 50 J
    std::map<int64_t, uint64_t> snapA; std::map<int64_t, std::pair<int64_t,int64_t>> hjA;
    bool ok = true;
    snapA[s.tip()] = s.digest(); hjA[s.tip()] = {s.H(), s.J()};
    while (ok && s.tip() < 40560) { ok = s.step(false); snapA[s.tip()] = s.digest(); hjA[s.tip()] = {s.H(), s.J()}; }
    CHECK(ok && s.st.invariant_fail == 0, "branch A built (39,990..40,560), supply exact");
    CHECK(hjA[40265].first == 150 * SOST && hjA[40266].first == 50 * SOST && hjA[40554].first == 0,
          "branch A: H 150 -> 50 at #40,266 (H-only) -> 0 at #40,554 (mixed)");
    const int64_t j_before_mixed = hjA[40553].second, j_after_mixed = hjA[40554].second;
    CHECK(j_after_mixed == j_before_mixed - 50 * SOST + v17::subsidy_split(sost_subsidy_stocks(40554)).jackpot_j,
          "branch A: mixed payment debited exactly 50 SOST from J");
    // 1) roll back across the mixed H/J payment, verifying every intermediate state.
    int64_t mism = 0;
    while (s.tip() > 40550) { if (!s.disconnect_tip()) { ok = false; break; } if (s.digest() != snapA[s.tip()] || s.H() != hjA[s.tip()].first || s.J() != hjA[s.tip()].second) ++mism; }
    CHECK(ok && mism == 0 && s.H() == hjA[40550].first && s.J() == hjA[40550].second,
          "rollback across #40,554: H and J restored exactly (every step)");
    // 2) roll back across the H-only payment and across the V17 activation.
    while (s.tip() > 39995) { if (!s.disconnect_tip()) { ok = false; break; } if (s.digest() != snapA[s.tip()] || s.H() != hjA[s.tip()].first || s.J() != hjA[s.tip()].second) ++mism; }
    CHECK(ok && mism == 0 && s.J() == 0 && s.H() == 150 * SOST, "rollback across #40,266 and #40,000: J back to 0, H back to 150 (every step)");
    // 3) connect a different branch B (different winners/fees), across activation and funding.
    s.seed = 202; s.forced_miss.insert(40266);   // B: no jackpot winner at 40,266 -> rollover
    std::map<int64_t, std::pair<int64_t,int64_t>> hjB;
    while (ok && s.tip() < 40600) { ok = s.step(false); hjB[s.tip()] = {s.H(), s.J()}; }
    CHECK(ok && s.st.invariant_fail == 0, "branch B (39,996..40,600) connected, supply exact");
    CHECK(hjB[40266].first == 150 * SOST && hjB[40554].first == 0 &&
          hjB[40553].second - hjB[40554].second + v17::subsidy_split(sost_subsidy_stocks(40554)).jackpot_j == 50 * SOST,
          "branch B: #40,266 missed (rollover) -> #40,554 prize 200 = 150 H + 50 J");
    // 4) reorg back to branch A (disconnect B to the fork point, reconnect A from its seed).
    while (s.tip() > 39995) { if (!s.disconnect_tip()) { ok = false; break; } }
    CHECK(ok && s.digest() == snapA[39995], "disconnect branch B to the fork point: state == fork-point snapshot");
    s.seed = 101; s.forced_miss.clear();
    while (ok && s.tip() < 40560) ok = s.step(false);
    CHECK(ok && s.digest() == snapA[40560] && s.J() == hjA[40560].second && s.H() == hjA[40560].first,
          "reconnect branch A: UTXO set, pending and J identical to the original branch A tip");
#endif
}

int main() {
    std::printf("=== test_v17_economics (V17_HEIGHT=%lld) ===\n", (long long)V17_HEIGHT);
    test_split_rule();
    test_activation_constants();
    test_funding();
    test_j_transition();
    test_coinbase_boundary_and_adversarial();
    test_block_jackpot_rule();
    test_dtd_scenarios();
    test_long_simulation();
    test_reorg_and_rollback();
    std::printf("=== %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
