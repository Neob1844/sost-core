// V13 future-drift cap fork — boundary tests against the validator path.
//
// V13 hard fork @ block 12 000 tightens MAX_FUTURE_DRIFT_STAGED from 60 s
// to 10 s via the helper sost::max_future_drift_at(height) (params.h).
// Pre-V13 behaviour is byte-identical:
//
//     [0, CASERT_STAGED_RELIEF_HEIGHT) → 600 s (legacy MAX_FUTURE_DRIFT)
//     [CASERT_STAGED_RELIEF_HEIGHT,
//      V13_HEIGHT)                     →  60 s (staged-relief regime)
//     [V13_HEIGHT, ∞)                  →  10 s (V13 timestamp-gaming defence)
//
// This file exercises the validator-side reject rule:
//
//     if (block.timestamp > now + max_future_drift_at(height)) → REJECT
//
// at every regime boundary, with strict-greater-than semantics confirmed
// at ±1 s. The validator path itself lives in src/sost-node.cpp inside
// process_block(); here we re-implement the same arithmetic against the
// helper so the contract is pinned at unit level (the wire-up commit
// is what makes process_block call the helper, and a cross-test that
// exercises process_block end-to-end is out of scope for the helpers
// commit).
//
// IMPORTANT: this test does NOT spin up the full RPC node. It pins the
// helper + the validator inequality. End-to-end coverage (a candidate
// block actually rejected by process_block) is a separate concern owned
// by the integration test suite.

#include "sost/params.h"
#include <cstdio>
#include <cstdint>
#include <climits>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Mirrors the production validator's reject inequality in
// src/sost-node.cpp::process_block. A block is REJECTED iff
//     block_ts > now_ts + max_future_drift_at(height)
// i.e. accepted iff block_ts <= now_ts + cap.
static bool validator_accepts(int64_t height, int64_t now_ts, int64_t block_ts) {
    const int64_t cap = max_future_drift_at(height);
    return block_ts <= now_ts + cap;
}

// ---------------------------------------------------------------------------
// V13 boundary — at h=11999 cap=60s; at h=12000 cap=10s. ±1s strict.
// ---------------------------------------------------------------------------
static void test_v13_boundary() {
    printf("\n=== V13 boundary @ h=11999 / h=12000 ===\n");
    const int64_t now = 1'700'000'000;

    // Pre-V13 (h=11999, cap=60s)
    TEST("h=11999 accepts ts = now + 60   (boundary)",
         validator_accepts(11999, now, now + 60));
    TEST("h=11999 rejects ts = now + 61   (off-by-one above cap)",
         !validator_accepts(11999, now, now + 61));
    TEST("h=11999 rejects ts = now + 600  (legacy cap NOT in effect anymore)",
         !validator_accepts(11999, now, now + 600));
    TEST("h=11999 accepts ts = now + 0    (clock-aligned candidate)",
         validator_accepts(11999, now, now + 0));

    // Post-V13 (h=12000, cap=10s)
    TEST("h=12000 accepts ts = now + 10   (boundary)",
         validator_accepts(12000, now, now + 10));
    TEST("h=12000 rejects ts = now + 11   (off-by-one above cap)",
         !validator_accepts(12000, now, now + 11));
    TEST("h=12000 rejects ts = now + 60   (pre-V13 cap NOT in effect anymore)",
         !validator_accepts(12000, now, now + 60));
    TEST("h=12000 accepts ts = now + 0    (clock-aligned candidate)",
         validator_accepts(12000, now, now + 0));

    // h=12001 confirms post-V13 cap doesn't drift after activation
    TEST("h=12001 accepts ts = now + 10",
         validator_accepts(12001, now, now + 10));
    TEST("h=12001 rejects ts = now + 11",
         !validator_accepts(12001, now, now + 11));
}

// ---------------------------------------------------------------------------
// Staged-relief boundary — at CASERT_STAGED_RELIEF_HEIGHT - 1 cap=600s,
// at CASERT_STAGED_RELIEF_HEIGHT cap=60s. Pre-V13, must remain unchanged.
// ---------------------------------------------------------------------------
static void test_staged_boundary() {
    printf("\n=== Staged-relief boundary (pre-V13, must be byte-identical) ===\n");
    const int64_t now = 1'700'000'000;
    const int64_t pre_staged  = CASERT_STAGED_RELIEF_HEIGHT - 1;
    const int64_t at_staged   = CASERT_STAGED_RELIEF_HEIGHT;

    // Pre-staged: legacy 600 s cap.
    TEST("pre-staged accepts ts = now + 600  (boundary, legacy cap)",
         validator_accepts(pre_staged, now, now + 600));
    TEST("pre-staged rejects ts = now + 601  (off-by-one)",
         !validator_accepts(pre_staged, now, now + 601));
    TEST("pre-staged accepts ts = now + 60   (well within legacy cap)",
         validator_accepts(pre_staged, now, now + 60));

    // Staged: tightened 60 s cap.
    TEST("at-staged accepts ts = now + 60   (boundary)",
         validator_accepts(at_staged, now, now + 60));
    TEST("at-staged rejects ts = now + 61   (off-by-one)",
         !validator_accepts(at_staged, now, now + 61));
    TEST("at-staged rejects ts = now + 600  (legacy cap NOT in effect anymore)",
         !validator_accepts(at_staged, now, now + 600));
}

// ---------------------------------------------------------------------------
// Genesis-region: cap=600s (legacy), exercises the deepest pre-fork branch.
// ---------------------------------------------------------------------------
static void test_genesis_region() {
    printf("\n=== Genesis-region (h=0, h=1) — legacy 600 s cap ===\n");
    const int64_t now = 1'700'000'000;
    TEST("h=0 accepts ts = now + 600",  validator_accepts(0, now, now + 600));
    TEST("h=0 rejects ts = now + 601",  !validator_accepts(0, now, now + 601));
    TEST("h=1 accepts ts = now + 599",  validator_accepts(1, now, now + 599));
}

// ---------------------------------------------------------------------------
// Cross-regime sanity — confirm that within each regime the cap is
// constant, and between regimes the cap is monotone non-increasing.
// (Sanity, not a hard contract; documents the design intent.)
// ---------------------------------------------------------------------------
static void test_cross_regime_monotonicity() {
    printf("\n=== Cross-regime monotonicity (cap non-increasing as height grows) ===\n");
    const int64_t cap_genesis      = max_future_drift_at(0);
    const int64_t cap_pre_staged   = max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT - 1);
    const int64_t cap_post_staged  = max_future_drift_at(CASERT_STAGED_RELIEF_HEIGHT);
    const int64_t cap_pre_v13      = max_future_drift_at(V13_HEIGHT - 1);
    const int64_t cap_at_v13       = max_future_drift_at(V13_HEIGHT);
    const int64_t cap_far_future   = max_future_drift_at(INT64_MAX);

    TEST("cap(genesis)        == 600", cap_genesis == 600);
    TEST("cap(pre-staged)     == 600", cap_pre_staged == 600);
    TEST("cap(staged)         ==  60", cap_post_staged == 60);
    TEST("cap(pre-V13)        ==  60", cap_pre_v13 == 60);
    TEST("cap(V13)            ==  10", cap_at_v13 == 10);
    TEST("cap(far-future)     ==  10", cap_far_future == 10);

    TEST("cap monotone non-increasing across regime boundaries",
         cap_genesis     >= cap_pre_staged
         && cap_pre_staged  >= cap_post_staged
         && cap_post_staged >= cap_pre_v13
         && cap_pre_v13     >= cap_at_v13
         && cap_at_v13      >= cap_far_future);
}

int main() {
    printf("\n=== V13 future-drift cap — boundary tests ===\n");
    printf("V13_HEIGHT                       = %lld\n",
           (long long)V13_HEIGHT);
    printf("CASERT_STAGED_RELIEF_HEIGHT      = %lld\n",
           (long long)CASERT_STAGED_RELIEF_HEIGHT);
    printf("MAX_FUTURE_DRIFT (legacy)        = %lld s\n",
           (long long)MAX_FUTURE_DRIFT);
    printf("MAX_FUTURE_DRIFT_STAGED          = %lld s\n",
           (long long)MAX_FUTURE_DRIFT_STAGED);
    printf("V13 cap                          = 10 s\n");

    test_v13_boundary();
    test_staged_boundary();
    test_genesis_region();
    test_cross_regime_monotonicity();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
