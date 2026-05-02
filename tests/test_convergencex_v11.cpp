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

int main() {
    printf("\n=== ConvergenceX V11 State-Dataset Tests ===\n");
    printf("Activation height: %lld\n", (long long)CASERT_V11_HEIGHT);

    test_pre_v11_determinism();
    test_post_v11_determinism();
    test_v11_branch_diverges_from_v10();
    test_nonce_sensitivity();
    test_header_sensitivity();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
