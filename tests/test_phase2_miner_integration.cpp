// V11 Phase 2 — miner ↔ validator integration test (C11).
//
// Simulates the miner ↔ node handshake without running RPC: each test
// builds a fake "lottery state" payload (the same fields the
// getlotterystate RPC would return), constructs a coinbase transaction
// the way the production miner would, and feeds it into
// ValidateCoinbaseConsensus with the matching Phase2CoinbaseContext.
//
// Boundaries probed against phase2_height = 7050 (the activation height
// proposed for C11). Tests do NOT assume V11_PHASE2_HEIGHT == 7050 in
// params.h — the fixture passes a synthetic phase2_height directly so
// the file stays valid whether C11 lands the activation change or not.
//
// Phase 2 schedule reminder (height-anchored):
//   For h in [H, H+5000):  triggered ⟺ h % 3 != 0   (2-of-3 bootstrap)
//   For h >= H+5000:       triggered ⟺ h % 3 == 0   (1-of-3 permanent)
//
// Negative cases exercise the four lottery-coinbase rejection codes:
//   CB11_LOTTERY_SHAPE     — wrong number of outputs / wrong types.
//   CB12_LOTTERY_AMOUNT    — wrong miner_share / lottery_payout amount.
//   CB13_LOTTERY_WINNER    — wrong winner pkh on PAYOUT.
//   CB14_LOTTERY_INVARIANT — pending invariant violated by the ctx.
//
// No Schnorr dependency; built unconditionally.

#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/lottery.h"
#include "sost/params.h"

#include <climits>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
static PubKeyHash g_gold_pkh{};
static PubKeyHash g_popc_pkh{};
static PubKeyHash g_miner_pkh{};
static PubKeyHash g_winner_pkh{};
static PubKeyHash g_other_pkh{};

static void init_pkhs() {
    std::memset(g_gold_pkh.data(),   0xBB, 20);
    std::memset(g_popc_pkh.data(),   0xCC, 20);
    std::memset(g_miner_pkh.data(),  0xDD, 20);
    std::memset(g_winner_pkh.data(), 0xEE, 20);
    std::memset(g_other_pkh.data(),  0x11, 20);
}

static void fill_cb_input(Transaction& tx, int64_t height) {
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;
    TxInput cbin;
    std::memset(cbin.prev_txid.data(), 0, 32);
    cbin.prev_index = 0xFFFFFFFFu;
    std::memset(cbin.signature.data(), 0, 64);
    uint64_t h = (uint64_t)height;
    std::memcpy(cbin.signature.data(), &h, 8);
    std::memset(cbin.pubkey.data(), 0, 33);
    tx.inputs.push_back(cbin);
}

// Mirrors the production miner build_coinbase_tx (NORMAL path).
static Transaction miner_build_normal(int64_t height,
                                      int64_t total_reward) {
    Transaction tx; fill_cb_input(tx, height);
    int64_t q = total_reward / 4;
    int64_t miner = total_reward - q - q;
    TxOutput om; om.amount = miner; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    TxOutput og; og.amount = q; og.type = OUT_COINBASE_GOLD;
    og.pubkey_hash = g_gold_pkh; tx.outputs.push_back(og);
    TxOutput op; op.amount = q; op.type = OUT_COINBASE_POPC;
    op.pubkey_hash = g_popc_pkh; tx.outputs.push_back(op);
    return tx;
}

// Mirrors build_phase2_update_coinbase_tx in the miner.
static Transaction miner_build_update(int64_t height, int64_t total_reward) {
    Transaction tx; fill_cb_input(tx, height);
    auto p = sost::lottery::phase2_coinbase_split(total_reward);
    TxOutput om; om.amount = p.miner_share; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    return tx;
}

// Mirrors build_phase2_payout_coinbase_tx in the miner.
static Transaction miner_build_payout(int64_t height,
                                      int64_t total_reward,
                                      int64_t pending_before,
                                      const PubKeyHash& winner) {
    Transaction tx; fill_cb_input(tx, height);
    auto p = sost::lottery::phase2_coinbase_split(total_reward);
    TxOutput om; om.amount = p.miner_share; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    TxOutput ol; ol.amount = p.lottery_share + pending_before;
    ol.type = OUT_COINBASE_LOTTERY;
    ol.pubkey_hash = winner; tx.outputs.push_back(ol);
    return tx;
}

static Phase2CoinbaseContext mk_ctx(int64_t phase2_height,
                                    int64_t pending_before,
                                    bool triggered,
                                    bool paid_out,
                                    int64_t total_reward,
                                    const PubKeyHash& winner) {
    auto p = sost::lottery::phase2_coinbase_split(total_reward);
    Phase2CoinbaseContext c;
    c.phase2_height = phase2_height;
    c.pending_before = pending_before;
    c.triggered = triggered;
    c.paid_out = paid_out;
    if (triggered && paid_out) {
        c.lottery_payout = p.lottery_share + pending_before;
        c.expected_winner_pkh = winner;
        c.expected_pending_after = 0;
    } else if (triggered && !paid_out) {
        c.lottery_payout = 0;
        c.expected_winner_pkh = PubKeyHash{};
        c.expected_pending_after = pending_before + p.lottery_share;
    } else {
        c.lottery_payout = 0;
        c.expected_winner_pkh = PubKeyHash{};
        c.expected_pending_after = pending_before;
    }
    return c;
}

// ---------------------------------------------------------------------------
// §1 — Boundary heights with phase2_height = 7050 (C11 proposed activation)
// ---------------------------------------------------------------------------

static void test_boundary_heights_7050() {
    printf("\n== §1: boundaries vs phase2_height = 7050 ==\n");
    const int64_t H = 7050;

    // height 6999 — pre-Phase 1 boundary, pre-Phase 2.
    TEST("6999 pre-Phase 2: NOT triggered",
         !sost::lottery::is_lottery_block(6999, H));

    // height 7000 — Phase 1 cASERT activates here, Phase 2 still inactive.
    TEST("7000 Phase 1 active, Phase 2 inactive (7000 < 7050): NOT triggered",
         !sost::lottery::is_lottery_block(7000, H));

    // height 7049 — last block before activation, NOT triggered.
    TEST("7049 last pre-activation block: NOT triggered",
         !sost::lottery::is_lottery_block(7049, H));

    // height 7050 — Phase 2 active, but 7050 % 3 == 0 and we're in
    // bootstrap → rule says % 3 != 0 → NOT triggered.
    TEST("7050 Phase 2 first block, h%3==0 in bootstrap: NOT triggered",
         !sost::lottery::is_lottery_block(7050, H));

    // height 7051 — h%3==1, bootstrap → triggered.
    TEST("7051 first triggered Phase 2 block (h%3==1)",
         sost::lottery::is_lottery_block(7051, H));

    // height 7052 — h%3==2, bootstrap → triggered.
    TEST("7052 triggered (h%3==2)",
         sost::lottery::is_lottery_block(7052, H));

    // height 7053 — h%3==0, bootstrap → NOT triggered.
    TEST("7053 NOT triggered (h%3==0 in bootstrap)",
         !sost::lottery::is_lottery_block(7053, H));

    // height 12049 — last bootstrap block (offset = 4999, < 5000).
    TEST("12049 last bootstrap block (offset 4999): triggered iff h%3 != 0",
         sost::lottery::is_lottery_block(12049, H) == ((12049 % 3) != 0));

    // height 12050 — first permanent block (offset = 5000).
    TEST("12050 first permanent block (offset 5000): triggered iff h%3 == 0",
         sost::lottery::is_lottery_block(12050, H) == ((12050 % 3) == 0));

    // height 12051 — permanent rule: % 3 == 0 → triggered (12051 = 3*4017).
    TEST("12051 permanent: triggered (h%3 == 0)",
         sost::lottery::is_lottery_block(12051, H));
    // height 12052 — % 3 == 1 → NOT triggered in permanent.
    TEST("12052 permanent: NOT triggered (h%3 == 1)",
         !sost::lottery::is_lottery_block(12052, H));
    // height 12053 — % 3 == 2 → NOT triggered in permanent.
    TEST("12053 permanent: NOT triggered (h%3 == 2)",
         !sost::lottery::is_lottery_block(12053, H));
    // height 12054 — % 3 == 0 → triggered in permanent.
    TEST("12054 permanent: triggered (h%3 == 0)",
         sost::lottery::is_lottery_block(12054, H));
}

// ---------------------------------------------------------------------------
// §2 — Validator accepts each shape with correct ctx (positive cases)
// ---------------------------------------------------------------------------

static void test_validator_accepts_each_shape() {
    printf("\n== §2: validator accepts each shape with correct ctx ==\n");
    const int64_t H = 7050;
    const int64_t SUBSIDY = 100'000'000;
    const int64_t FEES = 0;
    const int64_t TOT = SUBSIDY + FEES;

    // -------- (a) pre-Phase 2 height 7000 — NORMAL path -----------------
    {
        auto cb = miner_build_normal(7000, TOT);
        // Pre-Phase 2 should accept regardless of phase2_ctx (when
        // height < phase2_height, validator falls through to legacy path).
        auto ctx = mk_ctx(H, /*pending*/0, /*trig*/false, /*paid*/false, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7000, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("7000 NORMAL path accepted (pre-Phase 2 fallthrough)", r.ok);
    }

    // -------- (b) Phase 2 non-triggered height 7050 — NORMAL ------------
    {
        auto cb = miner_build_normal(7050, TOT);
        auto ctx = mk_ctx(H, 0, /*trig*/false, /*paid*/false, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7050, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("7050 Phase 2 active but non-triggered: NORMAL accepted", r.ok);
    }

    // -------- (c) Phase 2 triggered + empty (UPDATE) height 7051 --------
    {
        auto cb = miner_build_update(7051, TOT);
        auto ctx = mk_ctx(H, /*pending*/0, /*trig*/true, /*paid*/false, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("7051 UPDATE_EMPTY accepted (1-output MINER, lottery share withheld)",
             r.ok);
    }

    // -------- (d) Phase 2 triggered + non-empty (PAYOUT) height 7051 ----
    {
        const int64_t PENDING = 0;
        auto cb = miner_build_payout(7051, TOT, PENDING, g_winner_pkh);
        auto ctx = mk_ctx(H, PENDING, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("7051 PAYOUT accepted (2-output MINER + LOTTERY)", r.ok);
    }

    // -------- (e) PAYOUT with rolled-over pending ----------------------
    {
        const int64_t PENDING = SUBSIDY / 2;  // one prior UPDATE accumulated
        auto cb = miner_build_payout(7052, TOT, PENDING, g_winner_pkh);
        auto ctx = mk_ctx(H, PENDING, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7052, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("7052 PAYOUT-with-rollover accepted (lottery_share + pending)",
             r.ok);
    }
}

// ---------------------------------------------------------------------------
// §3 — Negative cases (each must FAIL with the expected error code)
// ---------------------------------------------------------------------------

static void test_negatives() {
    printf("\n== §3: negative cases (validator rejects bad coinbases) ==\n");
    const int64_t H = 7050;
    const int64_t SUBSIDY = 100'000'000;
    const int64_t FEES = 0;
    const int64_t TOT = SUBSIDY + FEES;

    // -------- old miner emits 50/25/25 on triggered block → CB11 --------
    {
        auto cb = miner_build_normal(7051, TOT);
        auto ctx = mk_ctx(H, 0, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("CB11_LOTTERY_SHAPE: NORMAL coinbase on triggered PAYOUT block rejected",
             !r.ok && r.code == TxValCode::CB11_LOTTERY_SHAPE);
    }

    // -------- payout coinbase with manipulated winner pkh → CB13 -------
    {
        auto cb = miner_build_payout(7051, TOT, /*pending*/0, g_other_pkh);
        auto ctx = mk_ctx(H, 0, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("CB13_LOTTERY_WINNER: wrong winner pkh on PAYOUT rejected",
             !r.ok && r.code == TxValCode::CB13_LOTTERY_WINNER);
    }

    // -------- payout with manipulated lottery amount → CB12 ------------
    {
        // Build the coinbase with a pending value the ctx does NOT match.
        // The miner's "lottery_amount" output ends up wrong.
        auto cb = miner_build_payout(7051, TOT, /*pending*/0, g_winner_pkh);
        // Mutate the lottery output amount directly.
        cb.outputs[1].amount += 1;
        auto ctx = mk_ctx(H, 0, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("CB12_LOTTERY_AMOUNT: tampered lottery output amount rejected",
             !r.ok && r.code == TxValCode::CB12_LOTTERY_AMOUNT);
    }

    // -------- payout with miner_share tampered → CB12 ------------------
    {
        auto cb = miner_build_payout(7051, TOT, /*pending*/0, g_winner_pkh);
        cb.outputs[0].amount -= 1;  // shave a stock from miner
        auto ctx = mk_ctx(H, 0, /*trig*/true, /*paid*/true, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("CB12_LOTTERY_AMOUNT: tampered miner amount rejected",
             !r.ok && r.code == TxValCode::CB12_LOTTERY_AMOUNT);
    }

    // -------- pending_before stale (caller-passed wrong ctx) → CB12/CB14 -
    // The validator's CB12 fires first because the lottery output amount
    // is computed against ctx.pending_before. If the miner had the right
    // pending and the validator was passed a stale (lower) pending,
    // the lottery output looks too LARGE. The error code may be CB12
    // (amount mismatch) since amount check precedes invariant check.
    {
        const int64_t REAL_PENDING = SUBSIDY / 2;
        auto cb = miner_build_payout(7051, TOT, REAL_PENDING, g_winner_pkh);
        // Tell validator pending_before == 0 (stale).
        auto ctx = mk_ctx(H, /*pending=*/0, /*trig*/true, /*paid*/true,
                          TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        // The code should be CB12 (lottery amount check fails because
        // the on-chain output (lottery_share + REAL_PENDING) does not
        // match the ctx's expected (lottery_share + 0)).
        TEST("CB12_LOTTERY_AMOUNT or CB14: stale pending in ctx → reject",
             !r.ok &&
             (r.code == TxValCode::CB12_LOTTERY_AMOUNT ||
              r.code == TxValCode::CB14_LOTTERY_INVARIANT));
    }

    // -------- UPDATE with an extra GOLD output → CB11 ------------------
    {
        auto cb = miner_build_update(7051, TOT);
        // Glue a GOLD output on top — should be CB11 (wrong shape).
        TxOutput og; og.amount = 1; og.type = OUT_COINBASE_GOLD;
        og.pubkey_hash = g_gold_pkh; cb.outputs.push_back(og);
        auto ctx = mk_ctx(H, 0, /*trig*/true, /*paid*/false, TOT, g_winner_pkh);
        auto r = ValidateCoinbaseConsensus(cb, 7051, SUBSIDY, FEES,
                                           g_gold_pkh, g_popc_pkh, &ctx);
        TEST("CB11_LOTTERY_SHAPE: extra GOLD output on UPDATE rejected",
             !r.ok && r.code == TxValCode::CB11_LOTTERY_SHAPE);
    }
}

// ---------------------------------------------------------------------------
// §4 — Schedule sanity at first 6 blocks past activation
// ---------------------------------------------------------------------------

static void test_first_six_blocks_after_7050() {
    printf("\n== §4: triggers in first 6 Phase 2 blocks ==\n");
    const int64_t H = 7050;
    int64_t triggered = 0;
    for (int64_t h = H; h < H + 6; ++h) {
        bool t = sost::lottery::is_lottery_block(h, H);
        if (t) triggered++;
    }
    // Heights 7050..7055 in bootstrap: triggered when h%3 != 0 →
    // 7051, 7052, 7054, 7055 → 4 of 6.
    TEST("4-of-6 triggered in heights 7050..7055 (bootstrap 2-of-3)",
         triggered == 4);
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

int main() {
    init_pkhs();

    printf("===== V11 Phase 2 — miner ↔ validator integration (C11) =====\n");
    test_boundary_heights_7050();
    test_validator_accepts_each_shape();
    test_negatives();
    test_first_six_blocks_after_7050();

    printf("\n=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return (g_fail == 0) ? 0 : 1;
}
