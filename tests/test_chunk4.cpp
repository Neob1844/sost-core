#include "sost/block.h"
#include <cstdio>
#include <cstring>
using namespace sost;
static int pass=0, fail=0;
#define T(n,c) do{if(c){pass++;printf("  PASS: %s\n",n);}else{fail++;printf("  FAIL: %s\n",n);}}while(0)

void test_header_serialize() {
    printf("\n=== Header Serialization ===\n");
    Bytes32 prev{}; prev.fill(0); Bytes32 mrkl{}; mrkl.fill(0x11);
    Bytes32 cp{}; cp.fill(0x22);
    auto hdr = serialize_full_header(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ, cp, 42, 7);
    T("header length > 100", hdr.size() > 100);
    // Deterministic
    auto hdr2 = serialize_full_header(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ, cp, 42, 7);
    T("header deterministic", hdr == hdr2);
}

void test_block_id() {
    printf("\n=== Block ID ===\n");
    Bytes32 prev{}; prev.fill(0); Bytes32 mrkl{}; mrkl.fill(0x11);
    Bytes32 cp{}; cp.fill(0x22); Bytes32 commit{}; commit.fill(0x33);
    auto bid = compute_block_id_from_parts(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ, cp, 0, 0, commit);
    T("block_id not zero", !is_zero(bid));
    auto bid2 = compute_block_id_from_parts(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ, cp, 0, 0, commit);
    T("block_id deterministic", bid == bid2);
    // Different commit -> different ID
    Bytes32 commit2{}; commit2.fill(0x44);
    auto bid3 = compute_block_id_from_parts(prev, mrkl, (uint32_t)GENESIS_TIME, GENESIS_BITSQ, cp, 0, 0, commit2);
    T("different commit -> different ID", bid != bid3);
}

void test_mine_and_verify() {
    printf("\n=== Mine + Verify (dev) ===\n");
    Profile prof = Profile::DEV;
    std::vector<BlockMeta> chain;
    Bytes32 prev{}; prev.fill(0);
    Bytes32 mrkl{}; mrkl.fill(0x11);
    ConsensusParams params = get_consensus_params(prof, 0);
    // Apply CASERT overlay (must match verifier)
    auto cdec = casert_mode_from_chain(chain, 0);
    params = casert_apply_overlay(params, cdec);
    Bytes32 skey = epoch_scratch_key(0);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);
    Bytes32 bk = compute_block_key(prev);
    uint32_t powDiffQ = GENESIS_BITSQ;
    int64_t ts = GENESIS_TIME;
    // Try nonces until we find a valid block
    bool found = false;
    Block blk{};
    for (uint32_t nonce = 0; nonce < 100000; ++nonce) {
        auto hc = build_header_core(prev, mrkl, (uint32_t)ts, powDiffQ);
        auto res = convergencex_attempt(scratch.data(), scratch.size(),
            bk, nonce, 0, params, hc.data(), 0);
        if (res.is_stable && pow_meets_target(res.commit, powDiffQ)) {
            blk.height = 0;
            blk.prev_hash = prev; blk.merkle_root = mrkl;
            blk.timestamp = ts; blk.powDiffQ = powDiffQ;
            blk.nonce = nonce; blk.extra_nonce = 0;
            blk.commit = res.commit;
            blk.checkpoints_root = res.checkpoints_root;
            blk.stability_metric = res.stability_metric;
            blk.x_bytes = res.x_bytes;
            blk.subsidy_stocks = sost_subsidy_stocks(0);
            blk.block_id = compute_block_id_from_parts(
                prev, mrkl, (uint32_t)ts, powDiffQ,
                res.checkpoints_root, nonce, 0, res.commit);
            found = true;
            printf("    Found at nonce=%u\n", nonce);
            break;
        }
    }
    T("found valid block", found);
    if (!found) { printf("    Skipping verify tests\n"); return; }
    // Basic verify
    auto r1 = verify_block_basic(blk, chain, ts, prof);
    T("basic verify OK", r1.ok);
    if (!r1.ok) printf("    reason: %s\n", r1.reason.c_str());
    // Full verify
    auto r2 = verify_block_full(blk, chain, prof);
    T("full verify OK", r2.ok);
    if (!r2.ok) printf("    reason: %s\n", r2.reason.c_str());
    // Unified
    auto r3 = verify_block(blk, chain, ts, prof, true);
    T("unified verify OK", r3.ok);
    // Tamper: change nonce -> should fail full
    Block bad = blk; bad.nonce = blk.nonce + 1;
    auto r4 = verify_block_full(bad, chain, prof);
    T("tampered nonce fails full verify", !r4.ok);
    // Tamper: bad subsidy
    Block bad2 = blk; bad2.subsidy_stocks = 999;
    auto r5 = verify_block_basic(bad2, chain, ts, prof);
    T("bad subsidy fails basic verify", !r5.ok);
}

int main() {
    printf("SOST Chunk 4 Tests - Block Validation\n");
    printf("======================================\n");
    test_header_serialize();
    test_block_id();
    test_mine_and_verify();
    printf("\n======================================\n");
    printf("Results: %d passed, %d failed\n", pass, fail);
    return fail > 0 ? 1 : 0;
}
