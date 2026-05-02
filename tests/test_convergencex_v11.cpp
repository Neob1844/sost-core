// ConvergenceX V11 — state-dependent dataset access tests
//
// V11 changes the dataset index per inner-loop round from a predictable
// `r % dataset_size` to `read_u32_le(state.data() + 8) % dataset_size`,
// closing the prefetch optimization gap.
//
// These tests verify:
//   1. Pre-V11 (height < CASERT_V11_HEIGHT): determinism of attempt commits.
//   2. Post-V11 (height >= CASERT_V11_HEIGHT): determinism of attempt commits.
//   3. Pre-V11 vs post-V11 with the same nonce/header MUST produce
//      DIFFERENT commits (proves the V11 branch is actually taken).
//   4. Same height + same nonce + same header → same commit (determinism).
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/params.h"
#include "sost/emission.h"      // get_consensus_params
#include "sost/sostcompact.h"   // pow_meets_target
#include <cstdio>
#include <cstring>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Build a deterministic 72-byte header_core with a non-trivial prev_hash.
static void build_test_header(uint8_t hc[72], uint8_t seed_byte) {
    std::memset(hc, 0, 72);
    for (int i = 0; i < 32; ++i) hc[i] = (uint8_t)(seed_byte ^ (i * 7));      // prev_hash
    for (int i = 32; i < 64; ++i) hc[i] = (uint8_t)((i + seed_byte) & 0xFF);  // merkle_root
    // ts u32 LE
    hc[64] = 0x00; hc[65] = 0x10; hc[66] = 0x00; hc[67] = 0x00;
    // bitsQ u32 LE — keep low so attempts succeed quickly in tests
    hc[68] = (uint8_t)(GENESIS_BITSQ & 0xFF);
    hc[69] = (uint8_t)((GENESIS_BITSQ >> 8) & 0xFF);
    hc[70] = (uint8_t)((GENESIS_BITSQ >> 16) & 0xFF);
    hc[71] = (uint8_t)((GENESIS_BITSQ >> 24) & 0xFF);
}

static ConsensusParams test_params() {
    // Minimal cx_rounds to keep tests fast; the V11 branch executes per round
    // regardless of count, so a low value is enough to verify behaviour.
    ConsensusParams p{};
    p.cx_n = 32;
    p.cx_rounds = 64;          // small for test speed
    p.cx_scratch_mb = 4;       // 4 MB minimal scratchpad
    p.cx_lr_shift = 18;
    p.cx_lam = 100;
    p.cx_checkpoint_interval = 16;
    p.stab_scale = 1;
    p.stab_k = 4;
    p.stab_margin = 185;
    p.stab_steps = 4;
    p.stab_lr_shift = 20;
    p.stab_profile_index = 0;
    return p;
}

static CXAttemptResult run_attempt(int64_t height, uint8_t header_seed,
                                   uint32_t nonce) {
    auto params = test_params();
    uint8_t hc[72]; build_test_header(hc, header_seed);
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), hc, 32);
    Bytes32 bk = compute_block_key(prev_hash);
    Bytes32 skey = epoch_scratch_key(0, nullptr);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);
    return convergencex_attempt(
        scratch.data(), scratch.size(), bk,
        nonce, /*extra*/0, params, hc,
        /*epoch*/0, height);
}

// ---------------------------------------------------------------------
// Test 1 — Pre-V11 determinism: same inputs → same commit
// ---------------------------------------------------------------------
static void test_pre_v11_determinism() {
    printf("\n=== Pre-V11 (height %lld) determinism ===\n",
           (long long)(CASERT_V11_HEIGHT - 1));
    auto a = run_attempt(CASERT_V11_HEIGHT - 1, 0xAB, 42);
    auto b = run_attempt(CASERT_V11_HEIGHT - 1, 0xAB, 42);
    TEST("same inputs at h=6999 → identical commit", a.commit == b.commit);
    TEST("same inputs at h=6999 → identical checkpoints_root",
         a.checkpoints_root == b.checkpoints_root);
}

// ---------------------------------------------------------------------
// Test 2 — Post-V11 determinism: same inputs → same commit
// ---------------------------------------------------------------------
static void test_post_v11_determinism() {
    printf("\n=== Post-V11 (height %lld) determinism ===\n",
           (long long)CASERT_V11_HEIGHT);
    auto a = run_attempt(CASERT_V11_HEIGHT, 0xAB, 42);
    auto b = run_attempt(CASERT_V11_HEIGHT, 0xAB, 42);
    TEST("same inputs at h=7000 → identical commit", a.commit == b.commit);
    TEST("same inputs at h=7000 → identical checkpoints_root",
         a.checkpoints_root == b.checkpoints_root);
}

// ---------------------------------------------------------------------
// Test 3 — V11 branch is actually taken
// Same nonce + same header_core, different height across the V11 boundary.
// Pre-V11 uses ds_idx = r % size; Post-V11 uses ds_idx = state-derived.
// Different access pattern → different commits guaranteed (probability of
// collision is 2^-256).
// ---------------------------------------------------------------------
static void test_v11_branch_diverges_from_v10() {
    printf("\n=== V11 branch produces a different commit than V10 ===\n");
    auto pre  = run_attempt(CASERT_V11_HEIGHT - 1, 0xCD, 7);
    auto post = run_attempt(CASERT_V11_HEIGHT,     0xCD, 7);
    TEST("h=6999 commit != h=7000 commit (V11 branch active)",
         !(pre.commit == post.commit));
    TEST("h=6999 checkpoints_root != h=7000 checkpoints_root",
         !(pre.checkpoints_root == post.checkpoints_root));
}

// ---------------------------------------------------------------------
// Test 4 — Different nonces produce different commits at any height
// ---------------------------------------------------------------------
static void test_nonce_sensitivity() {
    printf("\n=== Nonce sensitivity at V11 height ===\n");
    auto a = run_attempt(CASERT_V11_HEIGHT, 0xEF, 100);
    auto b = run_attempt(CASERT_V11_HEIGHT, 0xEF, 101);
    TEST("nonce 100 != nonce 101 → different commits at h=7000",
         !(a.commit == b.commit));
}

// ---------------------------------------------------------------------
// Test 5 — Different prev_hash produces different commits at any height
// (Sanity check that header_seed actually flows through)
// ---------------------------------------------------------------------
static void test_header_sensitivity() {
    printf("\n=== Header sensitivity at V11 height ===\n");
    auto a = run_attempt(CASERT_V11_HEIGHT, 0x11, 42);
    auto b = run_attempt(CASERT_V11_HEIGHT, 0x22, 42);
    TEST("different header_seed → different commits at h=7000",
         !(a.commit == b.commit));
}

// ---------------------------------------------------------------------
// Test 6 — Full miner→witnesses→verifier roundtrip at the V11 boundary
//
// This is the regression test for the bug where verify_cx_proof()
// hard-coded the V10 dataset index (`r % size`) while the miner and
// generate_transcript_witnesses() honoured the V11 state-derived index.
// Without this test an honest post-V11 block would be silently rejected
// by every node — a chain split at activation.
//
// The test uses Profile::DEV (low difficulty, short rounds) so a
// winning attempt is found in milliseconds. We then run the verifier
// at three height contexts and assert the exact expected outcome:
//
//   1. Pre-V11 attempt + verifier(h=6999)   → MUST pass.
//   2. Post-V11 attempt + verifier(h=7000)  → MUST pass.   ← the fix
//   3. Post-V11 attempt + verifier(h=0/V10) → MUST fail.   ← the bug
// ---------------------------------------------------------------------
static bool mine_and_verify_at_height(int64_t mine_h, int64_t verify_h,
                                      const char* label, bool expect_valid) {
    ACTIVE_PROFILE = Profile::DEV;
    ConsensusParams params = get_consensus_params(Profile::DEV, 0);

    // Deterministic header. Vary one byte by mine_h so different heights
    // get distinct seeds and we don't reuse cached datasets across tests.
    Bytes32 prev{}; prev.fill(0); prev[0] = (uint8_t)(mine_h & 0xFF);
    Bytes32 merkle{}; merkle.fill(0x11);
    uint8_t hc72[72];
    std::memcpy(hc72, prev.data(), 32);
    std::memcpy(hc72 + 32, merkle.data(), 32);
    write_u32_le(hc72 + 64, (uint32_t)GENESIS_TIME);
    write_u32_le(hc72 + 68, GENESIS_BITSQ);

    Bytes32 bk = compute_block_key(prev);
    Bytes32 skey = epoch_scratch_key(0, nullptr);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);

    CXAttemptResult res{};
    uint32_t found_nonce = 0;
    bool found = false;
    for (uint32_t nonce = 0; nonce < 200000; ++nonce) {
        res = convergencex_attempt(scratch.data(), scratch.size(), bk,
                                   nonce, /*extra*/0, params, hc72,
                                   /*epoch*/0, mine_h);
        if (res.is_stable && pow_meets_target(res.commit, GENESIS_BITSQ)) {
            found_nonce = nonce; found = true; break;
        }
    }
    if (!found) {
        printf("  *** SKIP: %s (no winning nonce in 200k tries — DEV profile changed?)\n",
               label);
        return false;
    }

    generate_transcript_witnesses(res, scratch.data(), scratch.size(), bk,
                                  found_nonce, /*extra*/0, params, hc72,
                                  /*epoch*/0, mine_h);

    bool valid = verify_cx_proof(
        hc72, found_nonce, /*extra*/0,
        res.commit, res.checkpoints_root, res.segments_root, res.final_state,
        res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
        res.checkpoint_leaves, res.segment_proofs, res.round_witnesses,
        params, verify_h);

    return valid == expect_valid;
}

static void test_v11_roundtrip() {
    printf("\n=== V11 miner→witnesses→verifier roundtrip ===\n");
    TEST("pre-V11 honest block (mine h=6999, verify h=6999) passes",
         mine_and_verify_at_height(CASERT_V11_HEIGHT - 1, CASERT_V11_HEIGHT - 1,
                                   "pre-V11 roundtrip", /*expect_valid=*/true));
    TEST("post-V11 honest block (mine h=7000, verify h=7000) passes  [FIX]",
         mine_and_verify_at_height(CASERT_V11_HEIGHT, CASERT_V11_HEIGHT,
                                   "post-V11 roundtrip", /*expect_valid=*/true));
    TEST("post-V11 block verified with V10 rule (h=0) MUST be rejected  [BUG REGRESSION]",
         mine_and_verify_at_height(CASERT_V11_HEIGHT, /*verify_h=*/0,
                                   "post-V11 mined / V10 verifier", /*expect_valid=*/false));
}

int main() {
    printf("\n=== ConvergenceX V11 State-Dataset Tests ===\n");
    printf("Activation height: %lld\n", (long long)CASERT_V11_HEIGHT);

    test_pre_v11_determinism();
    test_post_v11_determinism();
    test_v11_branch_diverges_from_v10();
    test_nonce_sensitivity();
    test_header_sensitivity();
    test_v11_roundtrip();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
