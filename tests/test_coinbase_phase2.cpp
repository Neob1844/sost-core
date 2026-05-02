// V11 Phase 2 — coinbase shape + lottery accounting tests (C8).
//
// Exercises:
//   - sost::lottery::phase2_coinbase_split helper math
//   - ValidateCoinbaseConsensus with Phase2CoinbaseContext for each
//     of the four kinds the validator must recognise:
//       1. Pre-Phase-2 / Phase-2 non-triggered (3-output 50/25/25)
//       2. Phase-2 UPDATE   (1-output MINER, lottery share withheld)
//       3. Phase-2 PAYOUT   (2-output MINER + LOTTERY)
//       4. Phase-2 with phase2_ctx == nullptr (fallback to pre-Phase-2)
//   - Negative cases: wrong shape, wrong amount, wrong winner,
//     broken emission invariant.
//
// Phase 2 stays dormant in production via V11_PHASE2_HEIGHT = INT64_MAX
// (params.h). These tests inject a finite phase2_height into the
// Phase2CoinbaseContext to exercise the active path; no consensus
// behaviour change for any real chain block.
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
// Test fixtures
// ---------------------------------------------------------------------------

static PubKeyHash g_gold_vault_pkh{};
static PubKeyHash g_popc_pool_pkh{};
static PubKeyHash g_miner_pkh{};
static PubKeyHash g_winner_pkh{};

static void init_pkhs() {
    std::memset(g_gold_vault_pkh.data(), 0xBB, 20);
    std::memset(g_popc_pool_pkh.data(), 0xCC, 20);
    std::memset(g_miner_pkh.data(),     0xDD, 20);
    std::memset(g_winner_pkh.data(),    0xEE, 20);
}

// Build a coinbase header (input field) — common to every shape.
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

// Pre-Phase-2 / Phase-2 non-triggered shape: 3 outputs MINER/GOLD/POPC.
static Transaction make_legacy_coinbase(int64_t height,
                                        int64_t subsidy,
                                        int64_t fees) {
    Transaction tx;
    fill_cb_input(tx, height);
    int64_t total = subsidy + fees;
    int64_t q = total / 4;
    int64_t miner = total - q - q;

    TxOutput om; om.amount = miner; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    TxOutput og; og.amount = q; og.type = OUT_COINBASE_GOLD;
    og.pubkey_hash = g_gold_vault_pkh; tx.outputs.push_back(og);
    TxOutput op; op.amount = q; op.type = OUT_COINBASE_POPC;
    op.pubkey_hash = g_popc_pool_pkh; tx.outputs.push_back(op);
    return tx;
}

// Phase-2 UPDATE shape: 1 output MINER only.
static Transaction make_update_coinbase(int64_t height,
                                        int64_t subsidy,
                                        int64_t fees) {
    Transaction tx;
    fill_cb_input(tx, height);
    auto split = sost::lottery::phase2_coinbase_split(subsidy + fees);
    TxOutput om; om.amount = split.miner_share; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    return tx;
}

// Phase-2 PAYOUT shape: 2 outputs MINER + LOTTERY.
static Transaction make_payout_coinbase(int64_t height,
                                        int64_t subsidy,
                                        int64_t fees,
                                        int64_t pending_before) {
    Transaction tx;
    fill_cb_input(tx, height);
    auto split = sost::lottery::phase2_coinbase_split(subsidy + fees);
    TxOutput om; om.amount = split.miner_share; om.type = OUT_COINBASE_MINER;
    om.pubkey_hash = g_miner_pkh; tx.outputs.push_back(om);
    TxOutput ol; ol.amount = split.lottery_share + pending_before;
    ol.type = OUT_COINBASE_LOTTERY;
    ol.pubkey_hash = g_winner_pkh; tx.outputs.push_back(ol);
    return tx;
}

static Phase2CoinbaseContext mk_ctx_update(int64_t pending_before,
                                           int64_t total_reward,
                                           int64_t phase2_height = 100) {
    auto split = sost::lottery::phase2_coinbase_split(total_reward);
    Phase2CoinbaseContext c;
    c.phase2_height          = phase2_height;
    c.pending_before         = pending_before;
    c.triggered              = true;
    c.paid_out               = false;
    c.lottery_payout         = 0;
    c.expected_winner_pkh    = PubKeyHash{};   // unused on UPDATE
    c.expected_pending_after = pending_before + split.lottery_share;
    return c;
}

static Phase2CoinbaseContext mk_ctx_payout(int64_t pending_before,
                                           int64_t total_reward,
                                           const PubKeyHash& winner,
                                           int64_t phase2_height = 100) {
    auto split = sost::lottery::phase2_coinbase_split(total_reward);
    Phase2CoinbaseContext c;
    c.phase2_height          = phase2_height;
    c.pending_before         = pending_before;
    c.triggered              = true;
    c.paid_out               = true;
    c.lottery_payout         = split.lottery_share + pending_before;
    c.expected_winner_pkh    = winner;
    c.expected_pending_after = 0;
    return c;
}

// ---------------------------------------------------------------------------
// §1 — Phase 2 dormant in production
// ---------------------------------------------------------------------------

static void test_phase2_height_is_int64_max() {
    printf("\n== §1: V11_PHASE2_HEIGHT == INT64_MAX in params.h ==\n");
    TEST("Phase 2 stays dormant",
         V11_PHASE2_HEIGHT == INT64_MAX);
}

// ---------------------------------------------------------------------------
// §2 — phase2_coinbase_split helper
// ---------------------------------------------------------------------------

static void test_split_basic() {
    printf("\n== §2: phase2_coinbase_split math ==\n");
    auto a = sost::lottery::phase2_coinbase_split(800000000);
    TEST("even reward: miner = lottery = total/2",
         a.miner_share == 400000000 && a.lottery_share == 400000000
         && a.total_reward == 800000000);

    auto b = sost::lottery::phase2_coinbase_split(9);
    TEST("odd reward: miner gets remainder (5/4)",
         b.miner_share == 5 && b.lottery_share == 4 && b.total_reward == 9);

    auto z = sost::lottery::phase2_coinbase_split(0);
    TEST("zero reward: both zero",
         z.miner_share == 0 && z.lottery_share == 0 && z.total_reward == 0);

    auto c = sost::lottery::phase2_coinbase_split(1);
    TEST("reward=1: miner gets the whole stock, lottery zero",
         c.miner_share == 1 && c.lottery_share == 0);

    auto d = sost::lottery::phase2_coinbase_split(2);
    TEST("reward=2: 1/1 split",
         d.miner_share == 1 && d.lottery_share == 1);
}

// ---------------------------------------------------------------------------
// §3 — pre-Phase-2 path unchanged (Phase2CoinbaseContext == nullptr)
// ---------------------------------------------------------------------------

static void test_legacy_path_no_context() {
    printf("\n== §3: pre-Phase-2 path (phase2_ctx == nullptr) ==\n");
    Transaction tx = make_legacy_coinbase(50, 800000000, 0);
    auto r = ValidateCoinbaseConsensus(tx, 50, 800000000, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       /*phase2_ctx=*/nullptr);
    TEST("legacy 50/25/25 coinbase passes with null phase2_ctx", r.ok);
}

static void test_legacy_path_height_below_phase2() {
    printf("\n== §3b: phase2_ctx with height < phase2_height (still legacy) ==\n");
    Transaction tx = make_legacy_coinbase(50, 800000000, 0);
    Phase2CoinbaseContext c;
    c.phase2_height          = 100;   // height 50 < 100
    c.pending_before         = 0;
    c.triggered              = false;
    c.paid_out               = false;
    c.expected_pending_after = 0;
    auto r = ValidateCoinbaseConsensus(tx, 50, 800000000, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &c);
    TEST("pre-activation height keeps 3-output 50/25/25 path", r.ok);
}

static void test_phase2_non_triggered_block() {
    printf("\n== §3c: Phase 2 non-triggered block (still 3-output) ==\n");
    Transaction tx = make_legacy_coinbase(150, 800000000, 0);
    Phase2CoinbaseContext c;
    c.phase2_height          = 100;
    c.pending_before         = 0;
    c.triggered              = false;   // non-triggered Phase-2 block
    c.paid_out               = false;
    c.expected_pending_after = 0;
    auto r = ValidateCoinbaseConsensus(tx, 150, 800000000, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &c);
    TEST("Phase 2 non-triggered block keeps 50/25/25 shape", r.ok);
}

// ---------------------------------------------------------------------------
// §4 — UPDATE path
// ---------------------------------------------------------------------------

static void test_update_happy_path() {
    printf("\n== §4: Phase 2 UPDATE (1 output) ==\n");
    int64_t total = 800000000;
    Transaction tx = make_update_coinbase(150, total, 0);
    auto ctx = mk_ctx_update(0, total);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("UPDATE happy path passes", r.ok);
    TEST("UPDATE expected_pending_after == pending_before + lottery_share",
         ctx.expected_pending_after == 400000000);
}

static void test_update_with_existing_pending() {
    printf("\n== §4b: UPDATE on top of existing pending ==\n");
    int64_t total = 800000000;
    Transaction tx = make_update_coinbase(151, total, 0);
    auto ctx = mk_ctx_update(/*pending_before=*/12345678901234LL, total);
    auto r = ValidateCoinbaseConsensus(tx, 151, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("UPDATE accumulates pending correctly", r.ok);
    TEST("pending grows by lottery_share",
         ctx.expected_pending_after - ctx.pending_before == 400000000);
}

static void test_update_wrong_output_count() {
    printf("\n== §4c: UPDATE rejects 3-output coinbase ==\n");
    int64_t total = 800000000;
    Transaction tx = make_legacy_coinbase(150, total, 0);  // 3 outputs!
    auto ctx = mk_ctx_update(0, total);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("UPDATE rejects coinbase with 3 outputs",
         !r.ok && r.code == TxValCode::CB11_LOTTERY_SHAPE);
}

static void test_update_wrong_miner_amount() {
    printf("\n== §4d: UPDATE rejects wrong miner amount ==\n");
    int64_t total = 800000000;
    Transaction tx = make_update_coinbase(150, total, 0);
    tx.outputs[0].amount += 1;  // miner overpaid by 1
    auto ctx = mk_ctx_update(0, total);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("UPDATE rejects overpaid miner",
         !r.ok && r.code == TxValCode::CB12_LOTTERY_AMOUNT);
}

static void test_update_invariant_broken() {
    printf("\n== §4e: UPDATE rejects bad expected_pending_after ==\n");
    int64_t total = 800000000;
    Transaction tx = make_update_coinbase(150, total, 0);
    auto ctx = mk_ctx_update(0, total);
    ctx.expected_pending_after += 1;  // claim pending grew by share+1
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("UPDATE rejects mismatched expected_pending_after",
         !r.ok && r.code == TxValCode::CB14_LOTTERY_INVARIANT);
}

// ---------------------------------------------------------------------------
// §5 — PAYOUT path
// ---------------------------------------------------------------------------

static void test_payout_happy_path_no_pending() {
    printf("\n== §5: Phase 2 PAYOUT (2 outputs), pending=0 ==\n");
    int64_t total = 800000000;
    Transaction tx = make_payout_coinbase(150, total, 0, /*pending_before=*/0);
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT happy path (no pending) passes", r.ok);
    TEST("lottery_payout == lottery_share when pending_before=0",
         ctx.lottery_payout == 400000000);
    TEST("expected_pending_after == 0 after PAYOUT",
         ctx.expected_pending_after == 0);
}

static void test_payout_happy_path_with_pending() {
    printf("\n== §5b: PAYOUT clears accumulated pending ==\n");
    int64_t total = 800000000;
    int64_t pending = 1200000000LL;  // 3 prior empty triggered blocks worth
    Transaction tx = make_payout_coinbase(160, total, 0, pending);
    auto ctx = mk_ctx_payout(pending, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 160, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT with rolled-over pending passes", r.ok);
    TEST("lottery winner output == lottery_share + pending_before",
         tx.outputs[1].amount == 400000000 + pending);
    TEST("expected_pending_after resets to 0",
         ctx.expected_pending_after == 0);
}

static void test_payout_wrong_output_count() {
    printf("\n== §5c: PAYOUT rejects 1-output (UPDATE shape) ==\n");
    int64_t total = 800000000;
    Transaction tx = make_update_coinbase(150, total, 0);  // 1 output!
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT rejects coinbase with 1 output",
         !r.ok && r.code == TxValCode::CB11_LOTTERY_SHAPE);
}

static void test_payout_wrong_lottery_amount() {
    printf("\n== §5d: PAYOUT rejects miner-skimmed lottery output ==\n");
    int64_t total = 800000000;
    Transaction tx = make_payout_coinbase(150, total, 0, /*pending=*/0);
    tx.outputs[1].amount -= 1;  // attacker steals 1 stock from winner
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT rejects under-paid lottery winner",
         !r.ok && r.code == TxValCode::CB12_LOTTERY_AMOUNT);
}

static void test_payout_wrong_winner_pkh() {
    printf("\n== §5e: PAYOUT rejects wrong winner address ==\n");
    int64_t total = 800000000;
    Transaction tx = make_payout_coinbase(150, total, 0, /*pending=*/0);
    PubKeyHash impostor{}; std::memset(impostor.data(), 0x77, 20);
    tx.outputs[1].pubkey_hash = impostor;
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);  // expects g_winner_pkh
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT rejects winner pkh substitution",
         !r.ok && r.code == TxValCode::CB13_LOTTERY_WINNER);
}

static void test_payout_invariant_pending_after_nonzero() {
    printf("\n== §5f: PAYOUT requires pending_after == 0 ==\n");
    int64_t total = 800000000;
    Transaction tx = make_payout_coinbase(150, total, 0, /*pending=*/0);
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);
    ctx.expected_pending_after = 1;  // PAYOUT must reset to 0
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("PAYOUT rejects non-zero expected_pending_after",
         !r.ok && r.code == TxValCode::CB14_LOTTERY_INVARIANT);
}

// ---------------------------------------------------------------------------
// §6 — Emission invariant cross-check (sanity)
// ---------------------------------------------------------------------------
//
// The validator's CB14 enforces:
//   sum(outputs) + (pending_after - pending_before) == subsidy + fees
//
// On all three Phase-2 transitions (IDLE/UPDATE/PAYOUT), total emission
// is conserved. This is a sanity check at the test-fixture level.

static void test_invariant_holds_update() {
    printf("\n== §6: invariant holds on UPDATE ==\n");
    const int64_t total = 800000000;
    auto split = sost::lottery::phase2_coinbase_split(total);
    int64_t pending_before = 0;
    int64_t sum_outputs = split.miner_share;
    int64_t pending_after = pending_before + split.lottery_share;
    TEST("sum(outputs) + Δpending == total_reward",
         sum_outputs + (pending_after - pending_before) == total);
}

static void test_invariant_holds_payout() {
    printf("\n== §6b: invariant holds on PAYOUT ==\n");
    const int64_t total = 800000000;
    auto split = sost::lottery::phase2_coinbase_split(total);
    int64_t pending_before = 1200000000LL;
    int64_t lottery_payout = split.lottery_share + pending_before;
    int64_t sum_outputs = split.miner_share + lottery_payout;
    int64_t pending_after = 0;
    TEST("PAYOUT: sum(outputs) + Δpending == total_reward",
         sum_outputs + (pending_after - pending_before) == total);
}

// ---------------------------------------------------------------------------
// §7 — Subsidy=8 worked example from the design discussion
// ---------------------------------------------------------------------------
//
// Owner-confirmed economics: on triggered blocks the FULL protocol-side
// allocation (Gold Vault 25 % + PoPC Pool 25 %, together 50 % of the
// block reward) is redirected to lottery / pending. The PoW miner's 50 %
// share is never touched. With subsidy = 8 stocks (and zero fees, for
// arithmetic clarity):
//
//   Non-triggered:   miner = 4, gold = 2, popc = 2.
//   UPDATE empty:    miner = 4, pending += 4.
//   PAYOUT pending=4: miner = 4, lottery = 4 + 4 = 8, pending → 0.
//
// These are exactly the numbers from the design conversation.

static void test_subsidy_8_non_triggered() {
    printf("\n== §7: subsidy=8 non-triggered (4 / 2 / 2 split) ==\n");
    const int64_t total = 8;
    Transaction tx = make_legacy_coinbase(50, total, 0);
    auto r = ValidateCoinbaseConsensus(tx, 50, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       /*phase2_ctx=*/nullptr);
    TEST("non-triggered subsidy=8 passes", r.ok);
    TEST("miner = 4",  tx.outputs[0].amount == 4);
    TEST("gold  = 2",  tx.outputs[1].amount == 2);
    TEST("popc  = 2",  tx.outputs[2].amount == 2);
    TEST("sum   = 8 = subsidy + fees",
         tx.outputs[0].amount + tx.outputs[1].amount + tx.outputs[2].amount == total);
}

static void test_subsidy_8_update() {
    printf("\n== §7b: subsidy=8 UPDATE (miner=4, pending +=4) ==\n");
    const int64_t total = 8;
    Transaction tx = make_update_coinbase(150, total, 0);
    auto ctx = mk_ctx_update(/*pending_before=*/0, total);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("subsidy=8 UPDATE passes", r.ok);
    TEST("miner = 4 (only output)", tx.outputs[0].amount == 4);
    TEST("expected_pending_after = 4 (was 0, +lottery_share)",
         ctx.expected_pending_after == 4);
    // Invariant: 4 + (4 - 0) == 8
    TEST("sum(outputs) + Δpending == 8",
         tx.outputs[0].amount + (ctx.expected_pending_after - ctx.pending_before) == total);
}

static void test_subsidy_8_payout_with_pending() {
    printf("\n== §7c: subsidy=8 PAYOUT with pending_before=4 (lottery=8) ==\n");
    const int64_t total = 8;
    const int64_t pending_before = 4;
    Transaction tx = make_payout_coinbase(160, total, 0, pending_before);
    auto ctx = mk_ctx_payout(pending_before, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 160, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("subsidy=8 PAYOUT (pending=4) passes", r.ok);
    TEST("miner = 4", tx.outputs[0].amount == 4);
    TEST("lottery = 4 + 4 = 8 (current_share + pending_before)",
         tx.outputs[1].amount == 8);
    TEST("expected_pending_after = 0", ctx.expected_pending_after == 0);
    // Invariant: (4 + 8) + (0 - 4) == 8
    TEST("sum(outputs) + Δpending == 8",
         (tx.outputs[0].amount + tx.outputs[1].amount)
         + (ctx.expected_pending_after - ctx.pending_before) == total);
}

static void test_subsidy_8_payout_no_pending() {
    printf("\n== §7d: subsidy=8 PAYOUT with pending_before=0 (lottery=4) ==\n");
    const int64_t total = 8;
    Transaction tx = make_payout_coinbase(150, total, 0, /*pending_before=*/0);
    auto ctx = mk_ctx_payout(0, total, g_winner_pkh);
    auto r = ValidateCoinbaseConsensus(tx, 150, total, 0,
                                       g_gold_vault_pkh, g_popc_pool_pkh,
                                       &ctx);
    TEST("subsidy=8 PAYOUT (pending=0) passes", r.ok);
    TEST("miner = 4",   tx.outputs[0].amount == 4);
    TEST("lottery = 4", tx.outputs[1].amount == 4);
    TEST("PoW miner keeps full 50 % regardless of trigger",
         tx.outputs[0].amount == total / 2);
}

// ---------------------------------------------------------------------------
// Driver
// ---------------------------------------------------------------------------

int main() {
    printf("== test_coinbase_phase2 (C8) — V11 Phase 2 coinbase shape ==\n");
    init_pkhs();

    test_phase2_height_is_int64_max();
    test_split_basic();

    test_legacy_path_no_context();
    test_legacy_path_height_below_phase2();
    test_phase2_non_triggered_block();

    test_update_happy_path();
    test_update_with_existing_pending();
    test_update_wrong_output_count();
    test_update_wrong_miner_amount();
    test_update_invariant_broken();

    test_payout_happy_path_no_pending();
    test_payout_happy_path_with_pending();
    test_payout_wrong_output_count();
    test_payout_wrong_lottery_amount();
    test_payout_wrong_winner_pkh();
    test_payout_invariant_pending_after_nonzero();

    test_invariant_holds_update();
    test_invariant_holds_payout();

    test_subsidy_8_non_triggered();
    test_subsidy_8_update();
    test_subsidy_8_payout_with_pending();
    test_subsidy_8_payout_no_pending();

    printf("\n== summary: %d pass, %d fail ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
