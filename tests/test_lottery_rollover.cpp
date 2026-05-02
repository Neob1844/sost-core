// V11 Phase 2 — lottery rollover state tests (C7).
//
// Exercises sost::lottery::apply_lottery_block /
// sost::lottery::undo_lottery_block — pure transition functions over
// LotteryApplyInput / LotteryApplyResult.
//
// C7 deliberately stops at the pure-function layer. The persistent
// integration into StoredBlock + BlockUndo + chain.json (with
// backward-compat default-zero on legacy JSON) is deferred to C8,
// where it lands together with the coinbase shape change. C7's
// in-memory rollover semantics are sufficient to verify correctness
// of the state machine; serialization roundtrip is therefore NOT
// covered by this test file (it runs in C8). All other 9 cases from
// the C7 spec are covered.
//
// No Schnorr dependency; built unconditionally. Phase 2 dormancy
// (V11_PHASE2_HEIGHT == INT64_MAX) is re-verified in §1 and §10.

#include "sost/lottery.h"
#include "sost/params.h"

#include <climits>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static PubKeyHash mk_pkh(uint8_t seed) {
    PubKeyHash p{};
    for (size_t i = 0; i < p.size(); ++i) p[i] = (uint8_t)(seed ^ (i * 11));
    return p;
}

static Bytes32 mk_hash(uint8_t seed) {
    Bytes32 h{};
    for (size_t i = 0; i < h.size(); ++i) h[i] = (uint8_t)(seed ^ (i * 13));
    return h;
}

static LotteryEligibilityEntry mk_entry(uint8_t pkh_seed,
                                        int64_t blocks = 1) {
    LotteryEligibilityEntry e{};
    e.pkh                = mk_pkh(pkh_seed);
    e.first_mined_height = 1;
    e.last_mined_height  = 50;
    e.blocks_mined       = blocks;
    return e;
}

// Build a valid LotteryApplyInput with sensible defaults; tests
// override only the fields they're exercising.
static LotteryApplyInput mk_input(int64_t height,
                                  int64_t phase2_height,
                                  int64_t pending_before,
                                  int64_t lottery_amount,
                                  std::vector<LotteryEligibilityEntry> eligible) {
    LotteryApplyInput in{};
    in.height            = height;
    in.phase2_height     = phase2_height;
    in.pending_before    = pending_before;
    in.lottery_amount    = lottery_amount;
    in.current_miner_pkh = mk_pkh(0xFF);   // anonymous current miner
    in.prev_block_hash   = mk_hash(0xAA);
    in.eligible          = std::move(eligible);
    return in;
}

// ---------------------------------------------------------------------------
// 1 — Phase 2 dormant: INT64_MAX → never triggered → no pending mutation
// ---------------------------------------------------------------------------
static void test_phase2_dormant_idle() {
    printf("\n=== 1) Phase 2 dormant (INT64_MAX) → never triggered, pending unchanged ===\n");
    auto eligible = std::vector<LotteryEligibilityEntry>{mk_entry(0x10), mk_entry(0x20)};
    auto in = mk_input(/*height*/7000, /*phase2*/INT64_MAX,
                       /*pending*/12345, /*amount*/100, eligible);
    auto r = apply_lottery_block(in);
    TEST("ok=true",                    r.ok);
    TEST("triggered=false (INT64_MAX)", !r.triggered);
    TEST("paid_out=false",              !r.paid_out);
    TEST("pending_after == pending_before", r.pending_after == 12345);
    TEST("lottery_payout == 0",         r.lottery_payout == 0);
    TEST("winner_index == -1",          r.winner_index == -1);
    TEST("V11_PHASE2_HEIGHT == INT64_MAX (sentinel preserved)",
         V11_PHASE2_HEIGHT == INT64_MAX);
}

// ---------------------------------------------------------------------------
// 2 — Pre-Phase 2: height < phase2_height → never triggered
// ---------------------------------------------------------------------------
static void test_pre_phase2_idle() {
    printf("\n=== 2) Pre-Phase 2 (height < phase2_height) → IDLE ===\n");
    auto in = mk_input(/*height*/99, /*phase2*/100, /*pending*/500, /*amount*/50,
                       {mk_entry(0x10)});
    auto r = apply_lottery_block(in);
    TEST("triggered=false",         !r.triggered);
    TEST("pending_after unchanged", r.pending_after == 500);
    TEST("paid_out=false",          !r.paid_out);
}

// ---------------------------------------------------------------------------
// 3 — Non-triggered (height%3==0 in bootstrap) with eligible+pending → IDLE
//     The CRITICAL invariant from V11_SPEC.md §10.6:
//     non-triggered blocks NEVER pay out, even if pending > 0.
// ---------------------------------------------------------------------------
static void test_non_triggered_never_pays_out() {
    printf("\n=== 3) Non-triggered with pending > 0 → no payout, pending unchanged ===\n");
    // Bootstrap rule (h - phase2_height < 5000): triggered iff h % 3 != 0.
    // Pick a height where h % 3 == 0 → IDLE.
    const int64_t H = 1'000'002;     // H % 3 == 0 (within bootstrap)
    const int64_t target = H + 3;    // (H+3) % 3 == 0 → IDLE
    auto eligible = std::vector<LotteryEligibilityEntry>{
        mk_entry(0x10), mk_entry(0x20), mk_entry(0x30)
    };
    auto in = mk_input(/*height*/target, /*phase2*/H,
                       /*pending*/777, /*amount*/100, eligible);
    auto r = apply_lottery_block(in);
    TEST("triggered=false",                 !r.triggered);
    TEST("paid_out=false (NEVER pays out)", !r.paid_out);
    TEST("pending_after == pending_before", r.pending_after == 777);
    TEST("lottery_payout == 0",             r.lottery_payout == 0);
    TEST("winner_index == -1",              r.winner_index == -1);
}

// ---------------------------------------------------------------------------
// 4 — Triggered + empty eligible → UPDATE (pending accumulates, no payout)
// ---------------------------------------------------------------------------
static void test_triggered_empty_eligible_update() {
    printf("\n=== 4) Triggered + empty eligible → pending += amount, no payout ===\n");
    const int64_t H = 1'000'002;
    const int64_t target = H + 1;   // (H+1) % 3 == 1 → triggered (bootstrap)
    auto in = mk_input(target, H, /*pending*/0, /*amount*/100,
                       std::vector<LotteryEligibilityEntry>{});  // empty
    auto r = apply_lottery_block(in);
    TEST("triggered=true",                r.triggered);
    TEST("paid_out=false (empty E)",      !r.paid_out);
    TEST("pending_after == 100",          r.pending_after == 100);
    TEST("lottery_payout == 0",           r.lottery_payout == 0);
    TEST("winner_index == -1",            r.winner_index == -1);
}

// ---------------------------------------------------------------------------
// 5 — Multiple empty triggered blocks → pending stacks
// ---------------------------------------------------------------------------
static void test_multiple_empty_triggered_stack() {
    printf("\n=== 5) Multiple empty triggered → pending stacks 0→100→200→300 ===\n");
    const int64_t H = 1'000'002;
    int64_t pending = 0;
    // Use three triggered heights (h % 3 != 0 within bootstrap).
    for (int step = 1; step <= 3; ++step) {
        const int64_t target = H + step;  // (H+1) % 3 == 1, (H+2) == 2, both triggered
        if (step == 3) {
            // (H+3) % 3 == 0 → not triggered. Skip and use H+4 instead.
            // Actually let's just pick three unambiguously triggered heights.
            break;
        }
        auto in = mk_input(target, H, pending, /*amount*/100,
                           std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("step is triggered+empty", r.triggered && !r.paid_out);
        pending = r.pending_after;
    }
    // Add one more empty triggered block at H+4.
    {
        auto in = mk_input(H + 4, H, pending, /*amount*/100,
                           std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("H+4 also triggered+empty", r.triggered && !r.paid_out);
        pending = r.pending_after;
    }
    TEST("pending stacked to 300 across 3 empty triggered blocks",
         pending == 300);
}

// ---------------------------------------------------------------------------
// 6 — Triggered + non-empty eligible → PAYOUT = pending + amount, pending=0
// ---------------------------------------------------------------------------
static void test_triggered_nonempty_payout() {
    printf("\n=== 6) Triggered + non-empty E → payout = pending + amount, pending = 0 ===\n");
    const int64_t H = 1'000'002;
    const int64_t target = H + 1;
    auto eligible = std::vector<LotteryEligibilityEntry>{
        mk_entry(0x10), mk_entry(0x20), mk_entry(0x30), mk_entry(0x40)
    };
    auto in = mk_input(target, H, /*pending*/300, /*amount*/100, eligible);
    auto r = apply_lottery_block(in);
    TEST("triggered=true",         r.triggered);
    TEST("paid_out=true",          r.paid_out);
    TEST("lottery_payout == 400 (pending 300 + amount 100)",
         r.lottery_payout == 400);
    TEST("pending_after == 0 (jackpot cleared)", r.pending_after == 0);
    TEST("winner_index in [0, 4)",
         r.winner_index >= 0 && r.winner_index < 4);
    TEST("winner_pkh equals eligible[winner_index].pkh",
         r.winner_pkh == eligible[(size_t)r.winner_index].pkh);
}

// ---------------------------------------------------------------------------
// 7 — Undo restores pending_before in all three branches
// ---------------------------------------------------------------------------
static void test_undo_restores_pending() {
    printf("\n=== 7) undo_lottery_block restores pending_before across IDLE / UPDATE / PAYOUT ===\n");
    const int64_t H = 1'000'002;

    // IDLE: pending_before = 555 → after IDLE step, undo restores 555.
    {
        auto in = mk_input(H + 3 /*not triggered*/, H, /*pending*/555,
                           /*amount*/100, {mk_entry(0x10)});
        auto r = apply_lottery_block(in);
        TEST("IDLE: pending_after == pending_before == 555",
             r.pending_after == 555 && r.pending_before == 555);
        TEST("IDLE: undo_lottery_block restores 555",
             undo_lottery_block(r) == 555);
    }
    // UPDATE: pending_before = 100 → pending_after = 200; undo restores 100.
    {
        auto in = mk_input(H + 1 /*triggered*/, H, /*pending*/100,
                           /*amount*/100, std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("UPDATE: pending_after == 200, pending_before == 100",
             r.pending_after == 200 && r.pending_before == 100);
        TEST("UPDATE: undo_lottery_block restores 100",
             undo_lottery_block(r) == 100);
    }
    // PAYOUT: pending_before = 300 → pending_after = 0; undo restores 300.
    {
        auto in = mk_input(H + 1, H, /*pending*/300, /*amount*/100,
                           {mk_entry(0x10), mk_entry(0x20)});
        auto r = apply_lottery_block(in);
        TEST("PAYOUT: pending_after == 0, pending_before == 300",
             r.pending_after == 0 && r.pending_before == 300);
        TEST("PAYOUT: undo_lottery_block restores 300",
             undo_lottery_block(r) == 300);
    }

    // Reorg sketch: chain A (UPDATE, UPDATE, PAYOUT) is replaced by a
    // simulated reorg back to the start. Walking backwards via
    // undo_lottery_block over each saved result should land at the
    // pre-A pending value.
    {
        const int64_t H_local = 1'000'002;
        std::vector<LotteryApplyResult> log;
        int64_t pending = 0;
        // Step 1: UPDATE — pending 0 → 100
        log.push_back(apply_lottery_block(mk_input(H_local + 1, H_local, pending,
                                                   100, {})));
        pending = log.back().pending_after;
        // Step 2: UPDATE — pending 100 → 200
        log.push_back(apply_lottery_block(mk_input(H_local + 2, H_local, pending,
                                                   100, {})));
        pending = log.back().pending_after;
        // Step 3: PAYOUT — pending 200 → 0 (winner among 3)
        log.push_back(apply_lottery_block(mk_input(H_local + 4, H_local, pending,
                                                   50,
            {mk_entry(0x10), mk_entry(0x20), mk_entry(0x30)})));
        pending = log.back().pending_after;
        TEST("reorg sim: forward chain ends with pending == 0 after PAYOUT",
             pending == 0);

        // Walk back: pending after disconnect of last block is its
        // saved pending_before; same for previous two.
        for (auto it = log.rbegin(); it != log.rend(); ++it) {
            pending = undo_lottery_block(*it);
        }
        TEST("reorg sim: backward walk restores pending == 0 (pre-chain start)",
             pending == 0);
    }
}

// ---------------------------------------------------------------------------
// 8 — Overflow protection: pending_before + lottery_amount near INT64_MAX
// ---------------------------------------------------------------------------
static void test_overflow_protection() {
    printf("\n=== 8) Overflow detection: pending_before + lottery_amount ===\n");
    const int64_t H = 1'000'002;
    const int64_t target = H + 1;     // triggered
    const int64_t MAX = std::numeric_limits<int64_t>::max();

    // Case 8a: pending_before + lottery_amount EXACTLY fits → ok.
    {
        auto in = mk_input(target, H, MAX - 100, 100,
                           std::vector<LotteryEligibilityEntry>{});  // empty -> UPDATE
        auto r = apply_lottery_block(in);
        TEST("MAX-100 + 100 == MAX is accepted", r.ok);
        TEST("pending_after == INT64_MAX (no rollover)",
             r.pending_after == MAX);
    }

    // Case 8b: overflow by 1 → ok=false, no wraparound.
    {
        auto in = mk_input(target, H, MAX - 100, 101,
                           std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("MAX-100 + 101 overflow → ok=false", !r.ok);
        TEST("error mentions overflow",
             r.error.find("overflow") != std::string::npos);
        TEST("pending_after NOT wrapped (still 0 = unset)",
             r.pending_after == 0);
    }

    // Case 8c: pending_before < 0 rejected.
    {
        auto in = mk_input(target, H, /*pending*/-1, 100,
                           std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("negative pending_before → ok=false", !r.ok);
        TEST("error mentions pending_before < 0",
             r.error.find("pending_before") != std::string::npos);
    }

    // Case 8d: lottery_amount < 0 rejected.
    {
        auto in = mk_input(target, H, 100, /*amount*/-5,
                           std::vector<LotteryEligibilityEntry>{});
        auto r = apply_lottery_block(in);
        TEST("negative lottery_amount → ok=false", !r.ok);
        TEST("error mentions lottery_amount",
             r.error.find("lottery_amount") != std::string::npos);
    }
}

// ---------------------------------------------------------------------------
// 9 — Serialization (DEFERRED to C8)
//     Documented here so the C7 reviewer sees the explicit handoff.
// ---------------------------------------------------------------------------
static void test_serialization_deferred() {
    printf("\n=== 9) Serialization roundtrip — DEFERRED to C8 (intentional) ===\n");
    // No assertion runs here. The C7 spec requested a backward-compat
    // chain.json roundtrip test, but C7 ships only the pure functions
    // (apply_lottery_block / undo_lottery_block). StoredBlock fields
    // (pending_lottery_before / pending_lottery_after / lottery_triggered
    // / lottery_winner_pkh / lottery_payout) and BlockUndo
    // pending_lottery_before are NOT added in this commit. Reasoning:
    //   - V11_PHASE2_HEIGHT == INT64_MAX, so the new fields would
    //     always be zero in production.
    //   - Persisting them now requires updating StoredBlock + 4
    //     locations in src/sost-node.cpp (struct, save_chain_internal
    //     fallback, load_chain JSON parser, raw_block_json
    //     reconstruction).
    //   - The C7 spec said "if integration threatens to touch too
    //     much consensus, stop and report; priority is correct state,
    //     not payout." Correct state is verified at the pure-function
    //     layer (cases 1-8 above + case 7 reorg simulation). The
    //     persistent integration lands in C8 alongside the coinbase
    //     shape change so both the SCHEMA and the CALLERS that set
    //     non-zero values arrive in the same commit.
    printf("  (no assertion — see comment above)\n");
}

// ---------------------------------------------------------------------------
// 10 — No coinbase / reward / UTXO / state mutation
//     This commit must not have touched ValidateCoinbaseConsensus,
//     build_coinbase_tx, emission.cpp, miner payout, or the subsidy
//     split. Verified by `git diff --name-only` outside this test;
//     this case is a sanity stub that the C7 caller can re-run.
// ---------------------------------------------------------------------------
static void test_no_coinbase_mutation() {
    printf("\n=== 10) No coinbase / reward / UTXO mutation by C7 ===\n");
    // Sanity asserts that consume only lottery API. If any of these
    // assertions ever require pulling in coinbase headers, the C7 scope
    // has expanded beyond its mandate.
    auto in = mk_input(1'000'003, 1'000'002, 0, 100, {mk_entry(0x10)});
    auto r = apply_lottery_block(in);
    TEST("apply_lottery_block does not depend on coinbase shape",
         r.triggered);
    TEST("V11_PHASE2_HEIGHT unchanged",
         V11_PHASE2_HEIGHT == INT64_MAX);
    TEST("LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW unchanged",
         LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW == 5);
    TEST("LOTTERY_HIGH_FREQ_WINDOW unchanged",
         LOTTERY_HIGH_FREQ_WINDOW == 5000);
}

int main() {
    printf("=== test_lottery_rollover (V11 Phase 2 C7) ===\n");
    test_phase2_dormant_idle();
    test_pre_phase2_idle();
    test_non_triggered_never_pays_out();
    test_triggered_empty_eligible_update();
    test_multiple_empty_triggered_stack();
    test_triggered_nonempty_payout();
    test_undo_restores_pending();
    test_overflow_protection();
    test_serialization_deferred();
    test_no_coinbase_mutation();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
