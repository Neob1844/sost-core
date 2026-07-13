// V15 Final Decentralization Fork — consensus unit tests.
// Spec: docs/V15_FINAL_DECENTRALIZATION_SPEC.md
//
// Exercises the PURE, consensus-critical primitives that BOTH the block
// template (miner) and the submitblock validator go through, so the coinbase
// shape they agree on can never diverge:
//   1. sost::lottery::dtd_block_triggered  — from V15_HEIGHT every block is
//      "triggered" (routes through the DTD accumulate/payout machinery),
//      while only lottery-cadence blocks (is_lottery_block) may pay out.
//   2. compute_lottery_eligibility_set with the new sliding recency window
//      (recent_miner_window): only recently-active miners are eligible;
//      dormant addresses are dropped; the [h-window, h-1] boundary is exact.
//   3. phase2_coinbase_split — the 50/50 miner/DTD split (redirected 50%).
//   4. The deprecated PoPC / Gold-Vault automation gates are RETIRED on
//      mainnet (never auto-activate at 20000/25000).
//
// Pure functions; no Schnorr; built unconditionally.

#include "sost/lottery.h"
#include "sost/params.h"
#include "sost/popc_v15.h"

#include <cstdio>
#include <vector>

using namespace sost;
using namespace sost::lottery;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static PubKeyHash mk_pkh(uint8_t seed) {
    PubKeyHash p{};
    for (size_t i = 0; i < p.size(); ++i) p[i] = (uint8_t)(seed ^ (i * 11));
    return p;
}
static LotteryMinedBlockView mk_block(int64_t height, const PubKeyHash& m) {
    LotteryMinedBlockView b; b.height = height; b.miner_pkh = m; b.block_hash = Bytes32{};
    return b;
}

int main() {
    const int64_t P2 = 7100;      // V11_PHASE2_HEIGHT (production)
    const int64_t V15 = 20000;    // V15_HEIGHT (mainnet)

    printf("== §1  dtd_block_triggered — V15 routes EVERY block through DTD ==\n");
    // Pre-V15 steady state (>= 12100): only 1-of-3 (height%3==0) is triggered.
    TEST("pre-V15 lottery block (15000%3==0) is triggered",
         dtd_block_triggered(15000, P2, V15) == true && (15000 % 3 == 0));
    TEST("pre-V15 non-lottery block (15001) is NOT triggered",
         dtd_block_triggered(15001, P2, V15) == false);
    TEST("pre-V15 non-lottery block (15002) is NOT triggered",
         dtd_block_triggered(15002, P2, V15) == false);
    // V15: EVERY block >= V15_HEIGHT is triggered (accumulate or pay).
    TEST("V15 non-lottery block (20000, %3==2) IS triggered (accumulate)",
         dtd_block_triggered(20000, P2, V15) == true && (20000 % 3 != 0));
    TEST("V15 lottery block (20001, %3==0) IS triggered (pay)",
         dtd_block_triggered(20001, P2, V15) == true && (20001 % 3 == 0));
    TEST("V15 non-lottery block (20002) IS triggered (accumulate)",
         dtd_block_triggered(20002, P2, V15) == true);
    // Only lottery-cadence blocks may PAY OUT — the distinction that makes
    // non-lottery V15 blocks accumulate rather than pay.
    TEST("V15 non-lottery block: triggered but NOT a payout block",
         dtd_block_triggered(20000, P2, V15) == true &&
         is_lottery_block(20000, P2) == false);
    TEST("V15 lottery block: triggered AND a payout block",
         dtd_block_triggered(20001, P2, V15) == true &&
         is_lottery_block(20001, P2) == true);
    // Below phase2: nothing triggered.
    TEST("below phase2 (5000) is never triggered",
         dtd_block_triggered(5000, P2, V15) == false);
    // v15 disabled sentinel → falls back to is_lottery_block exactly.
    TEST("v15_height==INT64_MAX falls back to is_lottery_block (20000 -> false)",
         dtd_block_triggered(20000, P2, INT64_MAX) == is_lottery_block(20000, P2));
    TEST("v15_height==INT64_MAX falls back to is_lottery_block (20001 -> true)",
         dtd_block_triggered(20001, P2, INT64_MAX) == is_lottery_block(20001, P2));

    printf("== §2  sliding recency window — dormant addresses dropped ==\n");
    // Test at height 8000: past phase2 (7100) but BELOW the dominance gate
    // (12100) and the SbPoW gate, so ONLY cooldown + the sliding window apply
    // — isolating the new rule. window = 2016 -> [8000-2016, 7999] = [5984,7999].
    const int64_t H = 8000;
    const int64_t W = DTD_RECENT_MINER_WINDOW;   // 2016
    const PubKeyHash A = mk_pkh(0x1A);  // recent
    const PubKeyHash B = mk_pkh(0x2B);  // within window
    const PubKeyHash C = mk_pkh(0x3C);  // dormant (outside window)
    const PubKeyHash D = mk_pkh(0x4D);  // exactly on the window edge (h-2016)
    const PubKeyHash E = mk_pkh(0x5E);  // one block older than the edge

    std::vector<LotteryMinedBlockView> hist;
    hist.push_back(mk_block(7990, A));      // last=7990  (>= 5984) eligible
    hist.push_back(mk_block(6000, B));      // last=6000  (>= 5984) eligible
    hist.push_back(mk_block(5000, C));      // last=5000  (<  5984) dormant
    hist.push_back(mk_block(H - W, D));     // last=5984  (== edge) eligible
    hist.push_back(mk_block(H - W - 1, E)); // last=5983  (<  edge) excluded

    auto has = [](const std::vector<LotteryEligibilityEntry>& v, const PubKeyHash& p) {
        for (const auto& e : v) if (e.pkh == p) return true;
        return false;
    };

    // Pre-V15 behaviour (window = 0): "mined ever" — all five are eligible.
    auto pre = compute_lottery_eligibility_set(hist, H, PubKeyHash{}, 5, 0);
    TEST("window=0: recent A eligible", has(pre, A));
    TEST("window=0: dormant C eligible (pre-V15 'mined ever')", has(pre, C));
    TEST("window=0: old E eligible (pre-V15 'mined ever')", has(pre, E));
    TEST("window=0: all five eligible", pre.size() == 5);

    // V15 behaviour (window = 2016): dormant addresses dropped, edge exact.
    auto v15 = compute_lottery_eligibility_set(hist, H, PubKeyHash{}, 5, W);
    TEST("window=2016: recent A eligible", has(v15, A));
    TEST("window=2016: in-window B eligible", has(v15, B));
    TEST("window=2016: edge D (last==h-2016) eligible", has(v15, D));
    TEST("window=2016: dormant C (last<h-2016) EXCLUDED", !has(v15, C));
    TEST("window=2016: one-older E (last==h-2017) EXCLUDED", !has(v15, E));
    TEST("window=2016: exactly 3 eligible (A,B,D)", v15.size() == 3);

    printf("== §3  phase2_coinbase_split — 50/50 miner/DTD ==\n");
    {
        auto s4 = phase2_coinbase_split(4);
        TEST("split(4): miner=2", s4.miner_share == 2);
        TEST("split(4): dtd=2", s4.lottery_share == 2);
        auto sOdd = phase2_coinbase_split(785100863);  // subsidy at h0 (odd)
        TEST("odd split: dtd = total/2 (floor)", sOdd.lottery_share == 785100863 / 2);
        TEST("odd split: miner gets the remainder (odd stock to miner)",
             sOdd.miner_share == 785100863 - 785100863 / 2);
        TEST("split conserves total", sOdd.miner_share + sOdd.lottery_share == 785100863);
    }

    printf("== §4  v15 fork activation boundary ==\n");
    TEST("v15_dtd_fork_active(19999) == false", v15_dtd_fork_active(19999) == false);
    TEST("v15_dtd_fork_active(20000) == true",  v15_dtd_fork_active(20000) == true);
    TEST("DTD_RECENT_MINER_WINDOW == 2016", DTD_RECENT_MINER_WINDOW == 2016);

#ifndef SOST_TESTNET_FORKS
    printf("== §5  deprecated PoPC / Gold-Vault gates RETIRED on mainnet ==\n");
    TEST("POPC_V15_ACTIVATION_HEIGHT == INT64_MAX (PoPC never auto-activates)",
         POPC_V15_ACTIVATION_HEIGHT == INT64_MAX);
    TEST("popc_v15_active_at(20000) == false", popc_v15_active_at(20000) == false);
    TEST("popc_v15_active_at(25000) == false", popc_v15_active_at(25000) == false);
    TEST("POPC_SINGLE_MODEL_HEIGHT == INT64_MAX", POPC_SINGLE_MODEL_HEIGHT == INT64_MAX);
    TEST("DTD_POPC_ELIGIBILITY_HEIGHT == INT64_MAX", DTD_POPC_ELIGIBILITY_HEIGHT == INT64_MAX);
    TEST("DTD_POPC_GATE_CONSENSUS_ACTIVE == false", DTD_POPC_GATE_CONSENSUS_ACTIVE == false);
    TEST("popc_eligibility_enforced never fires (25000)",
         popc_eligibility_enforced(25000, DTD_POPC_GATE_CONSENSUS_ACTIVE) == false);
    TEST("popc_eligibility_enforced never fires (1000000)",
         popc_eligibility_enforced(1000000, DTD_POPC_GATE_CONSENSUS_ACTIVE) == false);
#endif

    printf("\n== V15 tests: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
