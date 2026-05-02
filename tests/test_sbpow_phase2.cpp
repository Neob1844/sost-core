// V11 Phase 2 — SbPoW test stubs.
//
// Spec: docs/V11_SPEC.md §3
// Status: PHASE 2 — implementation pending. Each test below documents
// a property that must hold once src/sbpow.cpp is implemented. They
// fail intentionally (EXPECT_TRUE(false /* TODO PHASE 2 */)) so the
// scaffold cannot be silently shipped as "green tests".
//
// Wire-up: this file is NOT added to CMakeLists.txt yet — the tests
// would abort at runtime today. Wire it in the same patch that lands
// the real implementation (see V11_SPEC.md §6 gates G3.1-G3.4).
#include "sost/sbpow.h"

#include <cstdio>

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)
#define EXPECT_TRUE(c)  TEST(#c, (c))

int main() {
    printf("=== test_sbpow_phase2 (PHASE 2 SKELETON) ===\n");

    // ---- §3.3 seed binding ---------------------------------------
    printf("[seed binding]\n");
    EXPECT_TRUE(false /* TODO PHASE 2: derive_seed_v11 must match
                         sha256(MAGIC || "SEED2" || header_core || block_key
                                || nonce || extra_nonce || miner_pubkey) */);
    EXPECT_TRUE(false /* TODO PHASE 2: switching miner_pubkey changes the
                         seed (and therefore re-runs the full inner loop) */);

    // ---- §3.4 signature ------------------------------------------
    printf("[signature]\n");
    EXPECT_TRUE(false /* TODO PHASE 2: sig_message tag must be
                         "SOST/POW-SIG/v11" and bind commit||height */);
    EXPECT_TRUE(false /* TODO PHASE 2: BIP-340 Schnorr roundtrip
                         (sign then verify) succeeds */);
    EXPECT_TRUE(false /* TODO PHASE 2: tampered signature must fail verify */);
    EXPECT_TRUE(false /* TODO PHASE 2: signature over wrong height
                         must fail verify */);

    // ---- §3.5 validation -----------------------------------------
    printf("[validation]\n");
    EXPECT_TRUE(false /* TODO PHASE 2: malformed pubkey (not on curve)
                         rejected */);
    EXPECT_TRUE(false /* TODO PHASE 2: seed used for commit must equal
                         seed_v11 recomputed from miner_pubkey */);
    EXPECT_TRUE(false /* TODO PHASE 2: coinbase miner-subsidy output must
                         pay address derived from miner_pubkey */);
    EXPECT_TRUE(false /* TODO PHASE 2: block valid iff (1)+(2)+(3)+(4)
                         all hold (no individual rule is sufficient) */);

    // ---- §3.6 scope guard ----------------------------------------
    printf("[scope]\n");
    EXPECT_TRUE(false /* TODO PHASE 2: pre-V11 blocks (height <
                         V11_PHASE2_HEIGHT) must keep using the legacy
                         "SEED" tag and must not require a signature */);

    printf("\n=== SbPoW Phase 2: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
