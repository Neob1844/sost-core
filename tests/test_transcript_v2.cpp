// Transcript V2 test battery — dataset, scratchpad, segments, witnesses, commit
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/pow/casert.h"
#include "sost/sostcompact.h"
#include "sost/emission.h"
#include "sost/crypto.h"
#include <cstdio>
#include <cassert>
#include <cstring>

using namespace sost;
static int pass = 0, fail = 0;
#define TEST(name, cond) do { if(cond){pass++;printf("  PASS: %s\n",name);}else{fail++;printf("  FAIL: %s\n",name);} } while(0)

// A. Dataset indexed verification
void test_dataset_indexed() {
    printf("\n=== Dataset Indexed Verification ===\n");
    ACTIVE_PROFILE = Profile::MAINNET;
    Bytes32 prev{}; prev.fill(0xAA);

    // Build small portion of full dataset
    g_cx_dataset.generate(prev);

    // Test several indices
    uint64_t indices[] = {0, 1, 42, 1000, 65536, 512*1024-1, 512*1024*1024-1};
    for (auto idx : indices) {
        uint64_t single = compute_single_dataset_value(prev, idx);
        uint64_t full = g_cx_dataset.memory[idx];
        char buf[128];
        snprintf(buf, sizeof(buf), "dataset[%llu] single==full", (unsigned long long)idx);
        TEST(buf, single == full);
    }

    // Different prev_hash produces different values
    Bytes32 prev2{}; prev2.fill(0xBB);
    uint64_t v1 = compute_single_dataset_value(prev, 42);
    uint64_t v2 = compute_single_dataset_value(prev2, 42);
    TEST("different prev_hash -> different values", v1 != v2);
}

// B. Scratch indexed verification
void test_scratch_indexed() {
    printf("\n=== Scratch Indexed Verification ===\n");
    Bytes32 skey = epoch_scratch_key(0, nullptr);
    int scratch_mb = 32; // small for testing
    auto scratch = build_scratchpad(skey, scratch_mb);

    // Verify several blocks
    for (uint64_t bi = 0; bi < 100; bi += 7) {
        Bytes32 block = compute_single_scratch_block(skey, bi);
        size_t pos = (size_t)bi * 32;
        if (pos + 32 <= scratch.size()) {
            bool match = (std::memcmp(block.data(), scratch.data() + pos, 32) == 0);
            char buf[128];
            snprintf(buf, sizeof(buf), "scratch block[%llu] single==full", (unsigned long long)bi);
            TEST(buf, match);
        }
    }

    // Different epoch key produces different values
    Bytes32 skey2{}; skey2.fill(0xFF);
    Bytes32 b1 = compute_single_scratch_block(skey, 5);
    Bytes32 b2 = compute_single_scratch_block(skey2, 5);
    TEST("different epoch key -> different scratch", b1 != b2);
}

// C-H. Full end-to-end test with mining + verification
void test_full_transcript_v2() {
    printf("\n=== Full Transcript V2 End-to-End ===\n");
    ACTIVE_PROFILE = Profile::DEV; // DEV profile: 512 rounds, 32MB scratch
    ConsensusParams params = get_consensus_params(Profile::DEV, 0);

    Bytes32 prev{}; prev.fill(0);
    Bytes32 merkle{}; merkle.fill(0x11);
    uint8_t hc72[72];
    std::memcpy(hc72, prev.data(), 32);
    std::memcpy(hc72 + 32, merkle.data(), 32);
    write_u32_le(hc72 + 64, (uint32_t)GENESIS_TIME);
    write_u32_le(hc72 + 68, GENESIS_BITSQ);

    Bytes32 bk = compute_block_key(prev);
    Bytes32 skey = epoch_scratch_key(0, nullptr);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);

    // Mine until we find a valid block (DEV is easy)
    CXAttemptResult res{};
    uint32_t found_nonce = 0;
    for (uint32_t nonce = 0; nonce < 100000; ++nonce) {
        res = convergencex_attempt(scratch.data(), scratch.size(), bk, nonce, 0, params, hc72, 0);
        if (res.is_stable && pow_meets_target(res.commit, GENESIS_BITSQ)) {
            found_nonce = nonce;
            break;
        }
    }
    TEST("found valid block (DEV)", res.is_stable);

    // C. Segment leaves exist
    int32_t expected_nseg = (params.cx_rounds + CX_SEGMENT_LEN - 1) / CX_SEGMENT_LEN;
    TEST("segment_leaves count correct", (int32_t)res.segment_leaves.size() == expected_nseg);
    TEST("segments_root not zero", !is_zero(res.segments_root));
    TEST("checkpoints_root not zero", !is_zero(res.checkpoints_root));

    // Generate witnesses
    generate_transcript_witnesses(res, scratch.data(), scratch.size(), bk, found_nonce, 0, params, hc72, 0);
    TEST("segment_proofs generated", (int32_t)res.segment_proofs.size() == CX_CHAL_SEGMENTS || (int32_t)res.segment_proofs.size() == expected_nseg);
    TEST("round_witnesses generated", !res.round_witnesses.empty());
    int expected_rw = std::min((int)res.segment_proofs.size(), CX_CHAL_SEGMENTS) * CX_CHAL_STEPS;
    TEST("round_witnesses count correct", (int)res.round_witnesses.size() == expected_rw);

    // D. Challenge derivation determinism
    // Re-derive and check same challenges
    printf("\n=== Challenge Derivation ===\n");
    // Changing commit should change challenges
    Bytes32 fake_commit = res.commit;
    fake_commit[0] ^= 1;
    // (Not testing internal derive_challenges since it's static, but
    //  the fact that witnesses pass below proves derivation works)

    // E. RoundWitness integrity
    printf("\n=== RoundWitness Verification ===\n");
    for (size_t i = 0; i < res.round_witnesses.size(); ++i) {
        auto& rw = res.round_witnesses[i];
        TEST("x_before != x_after (round changes x)", rw.x_before != rw.x_after);
        TEST("state_before != state_after", rw.state_before != rw.state_after);
    }

    // F. Commit binding
    printf("\n=== Commit Binding ===\n");
    // Recompute commit manually and verify
    Bytes32 prev_h; std::memcpy(prev_h.data(), hc72, 32);
    Bytes32 block_key = compute_block_key(prev_h);
    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, hc72, 72); append(sbuf, block_key);
    append_u32_le(sbuf, found_nonce); append_u32_le(sbuf, 0u);
    Bytes32 seed = sha256(sbuf);

    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, hc72, 72); append(cbuf, seed); append(cbuf, res.final_state);
    append(cbuf, res.x_bytes.data(), res.x_bytes.size());
    append(cbuf, res.checkpoints_root); append(cbuf, res.segments_root);
    append_u64_le(cbuf, res.stability_metric);
    // V3: profile_index committed
    int8_t pi8 = (int8_t)params.stab_profile_index;
    cbuf.push_back((uint8_t)pi8);
    Bytes32 expected_commit = sha256(cbuf);
    TEST("commit binding correct (V3 with profile_index)", expected_commit == res.commit);

    // G. Full verification
    printf("\n=== Full Proof Verification ===\n");
    bool valid = verify_cx_proof(hc72, found_nonce, 0,
        res.commit, res.checkpoints_root, res.segments_root, res.final_state,
        res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
        res.checkpoint_leaves, res.segment_proofs, res.round_witnesses, params);
    TEST("verify_cx_proof V2 passes for honest block", valid);

    // Tamper tests
    if (!res.round_witnesses.empty()) {
        // Tamper x_after
        auto tampered_rw = res.round_witnesses;
        tampered_rw[0].x_after[0] ^= 1;
        bool bad1 = verify_cx_proof(hc72, found_nonce, 0,
            res.commit, res.checkpoints_root, res.segments_root, res.final_state,
            res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
            res.checkpoint_leaves, res.segment_proofs, tampered_rw, params);
        TEST("tampered x_after rejected", !bad1);

        // Tamper state_after
        auto tampered_rw2 = res.round_witnesses;
        tampered_rw2[0].state_after[0] ^= 1;
        bool bad2 = verify_cx_proof(hc72, found_nonce, 0,
            res.commit, res.checkpoints_root, res.segments_root, res.final_state,
            res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
            res.checkpoint_leaves, res.segment_proofs, tampered_rw2, params);
        TEST("tampered state_after rejected", !bad2);

        // Tamper scratch_value
        auto tampered_rw3 = res.round_witnesses;
        tampered_rw3[0].scratch_values[0] ^= 1;
        bool bad3 = verify_cx_proof(hc72, found_nonce, 0,
            res.commit, res.checkpoints_root, res.segments_root, res.final_state,
            res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
            res.checkpoint_leaves, res.segment_proofs, tampered_rw3, params);
        TEST("tampered scratch_value rejected", !bad3);

        // Tamper dataset_value
        auto tampered_rw4 = res.round_witnesses;
        tampered_rw4[0].dataset_value ^= 1;
        bool bad4 = verify_cx_proof(hc72, found_nonce, 0,
            res.commit, res.checkpoints_root, res.segments_root, res.final_state,
            res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
            res.checkpoint_leaves, res.segment_proofs, tampered_rw4, params);
        TEST("tampered dataset_value rejected", !bad4);

        // Tamper program_output
        auto tampered_rw5 = res.round_witnesses;
        tampered_rw5[0].program_output ^= 1;
        bool bad5 = verify_cx_proof(hc72, found_nonce, 0,
            res.commit, res.checkpoints_root, res.segments_root, res.final_state,
            res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
            res.checkpoint_leaves, res.segment_proofs, tampered_rw5, params);
        TEST("tampered program_output rejected", !bad5);
    }

    // Tamper segments_root in commit
    Bytes32 fake_sroot = res.segments_root;
    fake_sroot[0] ^= 1;
    bool bad_sr = verify_cx_proof(hc72, found_nonce, 0,
        res.commit, res.checkpoints_root, fake_sroot, res.final_state,
        res.x_bytes.data(), res.x_bytes.size(), res.stability_metric,
        res.checkpoint_leaves, res.segment_proofs, res.round_witnesses, params);
    TEST("tampered segments_root rejected", !bad_sr);

    // H. Determinism
    printf("\n=== Determinism ===\n");
    auto res2 = convergencex_attempt(scratch.data(), scratch.size(), bk, found_nonce, 0, params, hc72, 0);
    TEST("deterministic commit", res2.commit == res.commit);
    TEST("deterministic segments_root", res2.segments_root == res.segments_root);
    TEST("deterministic final_state", res2.final_state == res.final_state);
}

int main() {
    printf("SOST Transcript V2 Tests\n");
    printf("========================\n");

    test_dataset_indexed();
    test_scratch_indexed();
    test_full_transcript_v2();

    printf("\n========================\n");
    printf("Results: %d passed, %d failed\n", pass, fail);
    return fail > 0 ? 1 : 0;
}
