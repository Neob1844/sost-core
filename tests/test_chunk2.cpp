#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/emission.h"
#include "sost/sostcompact.h"
#include <cstdio>
#include <cstring>

using namespace sost;
static int pass = 0, fail = 0;
#define T(name, cond) do { if(cond){pass++;printf("  PASS: %s\n",name);}else{fail++;printf("  FAIL: %s\n",name);} } while(0)

void test_block_key() {
    printf("\n=== Block Key ===\n");
    Bytes32 prev{}; prev.fill(0);
    Bytes32 bk = compute_block_key(prev);
    T("block_key not zero", !is_zero(bk));
    // Deterministic
    Bytes32 bk2 = compute_block_key(prev);
    T("block_key deterministic", bk == bk2);
    // Different prev -> different key
    Bytes32 prev2{}; prev2.fill(0xAA);
    Bytes32 bk3 = compute_block_key(prev2);
    T("different prev -> different key", bk != bk3);
}

void test_derive_problem() {
    printf("\n=== Problem Derivation ===\n");
    Bytes32 bk{}; bk.fill(0x42);
    auto prob = derive_M_and_b(bk, 32, 100);
    T("M not all zero", prob.M[0][0] != 0 || prob.M[1][1] != 0 || prob.M[15][15] != 0);
    T("lam = 100", prob.lam == 100);
    // Deterministic
    auto prob2 = derive_M_and_b(bk, 32, 100);
    T("problem deterministic", std::memcmp(prob.M, prob2.M, sizeof(prob.M)) == 0);
}

void test_matvec() {
    printf("\n=== MatVec A(x) ===\n");
    Bytes32 bk{}; bk.fill(0x42);
    auto prob = derive_M_and_b(bk, 32, 100);
    int32_t x[32]; for (int i=0;i<32;++i) x[i]=i*10;
    int32_t out[32];
    matvec_A(prob, x, out, 32);
    T("A(x) produces non-zero", out[0] != 0 || out[1] != 0);
}

void test_gradient_step() {
    printf("\n=== Gradient Step ===\n");
    Bytes32 bk{}; bk.fill(0x42);
    auto prob = derive_M_and_b(bk, 32, 100);
    int32_t x[32]; for (int i=0;i<32;++i) x[i] = 1000*i;
    int32_t y[32];
    one_gradient_step(x, prob, 32, 18, y);
    T("gradient changes x", std::memcmp(x, y, 128) != 0);
}

void test_scratchpad() {
    printf("\n=== Scratchpad ===\n");
    Bytes32 key = epoch_scratch_key(0);
    T("epoch key not zero", !is_zero(key));
    auto sp = build_scratchpad(key, 1); // 1MB for test
    T("scratchpad size = 1MB", sp.size() == 1024*1024);
    // Deterministic
    auto sp2 = build_scratchpad(key, 1);
    T("scratchpad deterministic", sp == sp2);
}

void test_checkpoint_merkle() {
    printf("\n=== Checkpoints ===\n");
    Bytes32 sh{}; sh.fill(0x11);
    Bytes32 xh{}; xh.fill(0x22);
    Bytes32 leaf = checkpoint_leaf(sh, xh, 6250, 999);
    T("leaf not zero", !is_zero(leaf));
    std::vector<Bytes32> leaves(16, leaf);
    Bytes32 root = merkle_root_16(leaves);
    T("merkle root not zero", !is_zero(root));
    // Deterministic
    Bytes32 root2 = merkle_root_16(leaves);
    T("merkle deterministic", root == root2);
}

void test_stability() {
    printf("\n=== Stability Basin ===\n");
    Bytes32 bk{}; bk.fill(0x42);
    auto prob = derive_M_and_b(bk, 32, 100);
    // Run a few gradient steps to get a semi-converged x
    int32_t x[32]; for(int i=0;i<32;++i) x[i] = 0;
    for(int r = 0; r < 100; ++r) {
        int32_t y[32];
        one_gradient_step(x, prob, 32, 18, y);
        std::memcpy(x, y, 128);
    }
    Bytes32 stctx{}; stctx.fill(0x33);
    uint64_t metric = 0;
    bool stable = verify_stability_basin(x, prob, 32, 18, stctx, 1, 1, 2048, 1, 20, metric);
    T("stability runs without crash", true);
    printf("    stable=%d metric=%lu\n", stable, (unsigned long)metric);
}

void test_full_attempt() {
    printf("\n=== Full CX Attempt (dev) ===\n");
    // Dev params
    ConsensusParams p = get_consensus_params(Profile::DEV, 0);
    Bytes32 prev{}; prev.fill(0);
    Bytes32 mrkl{}; mrkl.fill(0x11);
    auto hc = build_header_core(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ);
    Bytes32 bk = compute_block_key(prev);
    Bytes32 skey = epoch_scratch_key(0);
    auto scratch = build_scratchpad(skey, p.cx_scratch_mb);
    auto res = convergencex_attempt(
        scratch.data(), scratch.size(),
        bk, 0, 0, p, hc.data(), 0);
    T("commit not zero", !is_zero(res.commit));
    T("cp_root not zero", !is_zero(res.checkpoints_root));
    T("x_bytes correct size", (int)res.x_bytes.size() == p.cx_n * 4);
    printf("    stable=%d metric=%lu commit=%s\n",
        res.is_stable, (unsigned long)res.stability_metric, hex(res.commit).substr(0,16).c_str());
    // Deterministic
    auto res2 = convergencex_attempt(
        scratch.data(), scratch.size(),
        bk, 0, 0, p, hc.data(), 0);
    T("attempt deterministic", res.commit == res2.commit);
    T("cp_root deterministic", res.checkpoints_root == res2.checkpoints_root);
    T("metric deterministic", res.stability_metric == res2.stability_metric);
}

int main() {
    printf("SOST Chunk 2 Tests - ConvergenceX Engine\n");
    printf("=========================================\n");
    test_block_key();
    test_derive_problem();
    test_matvec();
    test_gradient_step();
    test_scratchpad();
    test_checkpoint_merkle();
    test_stability();
    test_full_attempt();
    printf("\n=========================================\n");
    printf("Results: %d passed, %d failed\n", pass, fail);
    return fail > 0 ? 1 : 0;
}
