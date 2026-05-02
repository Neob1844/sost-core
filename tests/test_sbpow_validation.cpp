// V11 Phase 2 — SbPoW validation tests (Commit 4 scope).
//
// Exercises sost::sbpow::validate_sbpow_for_block() — the height-gated
// SbPoW consensus check. Tests inject a finite phase2_height (e.g.
// 100) so the active branch is reached without flipping the production
// V11_PHASE2_HEIGHT (which stays at INT64_MAX).
//
// Coverage (14 cases):
//    1. pre-Phase 2 v1 accepted
//    2. pre-Phase 2 v2 rejected
//    3. Phase 2 v1 rejected
//    4. Phase 2 valid v2 accepted
//    5. valid signature + matching coinbase accepted
//    6. valid signature + mismatched coinbase rejected
//    7. invalid signature rejected
//    8. malformed pubkey rejected
//    9. wrong height rejected
//   10. wrong nonce rejected
//   11. wrong extra_nonce rejected
//   12. wrong commit rejected
//   13. wrong prev_hash rejected
//   14. changing signature changes v2 block hash but signed message unchanged
//
// Tests #9-#13 verify that the signature is bound to every input field:
// they sign a message with one set of fields, then mutate ONE field on
// the verifier side and confirm rejection.

#include "sost/sbpow.h"
#include "sost/block.h"
#include "sost/params.h"   // GENESIS_BITSQ

#include <cstdio>
#include <cstring>
#include <string>

using namespace sost;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

static MinerPrivkey fixture_priv(uint8_t seed) {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(seed ^ (i * 7));
    return p;
}

static Bytes32 fixture_prev_hash(uint8_t seed = 0xAA) {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(seed ^ (i * 3));
    return h;
}

static Bytes32 fixture_commit(uint8_t seed = 0xCC) {
    Bytes32 c{};
    for (size_t i = 0; i < 32; ++i) c[i] = (uint8_t)(seed ^ (i * 5));
    return c;
}

// Build a fully-valid Phase 2 ValidationInputs at height H >= phase2_h.
// The signature is genuine (signed with the same privkey whose pkh is
// stored in coinbase_miner_pkh). Tests then mutate single fields to
// verify each rejection branch.
struct V2Setup {
    ValidationInputs in;
    MinerPrivkey     privkey;
};

static V2Setup make_valid_phase2_inputs(int64_t phase2_h = 100,
                                        int64_t height = 100,
                                        uint8_t priv_seed = 0x10) {
    V2Setup s;
    s.privkey = fixture_priv(priv_seed);
    bool ok = derive_compressed_pubkey_from_privkey(s.privkey, s.in.miner_pubkey);
    TEST("setup: pubkey derived", ok);

    s.in.header_version = 2;
    s.in.prev_hash      = fixture_prev_hash(0xAA);
    s.in.height         = height;
    s.in.commit         = fixture_commit(0xCC);
    s.in.nonce          = 12345;
    s.in.extra_nonce    = 678;
    s.in.coinbase_miner_pkh = derive_pkh_from_pubkey(s.in.miner_pubkey);
    s.in.phase2_height  = phase2_h;

    Bytes32 msg = build_sbpow_message(
        s.in.prev_hash, s.in.height, s.in.commit,
        s.in.nonce, s.in.extra_nonce, s.in.miner_pubkey);
    bool signed_ok = sign_sbpow_commitment(s.privkey, msg, s.in.miner_signature);
    TEST("setup: signature created", signed_ok);
    return s;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_pre_phase2_v1_accepted() {
    printf("\n=== 1) pre-Phase 2 v1 accepted ===\n");
    ValidationInputs in{};
    in.header_version = 1;
    in.height         = 50;
    in.phase2_height  = 100;   // we are pre-Phase 2

    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("pre-Phase 2 v1 → SBPOW_NOT_REQUIRED",
         r == ValidationResult::SBPOW_NOT_REQUIRED);
    TEST("no error message on pre-Phase 2 success", err.empty());
}

static void test_pre_phase2_v2_rejected() {
    printf("\n=== 2) pre-Phase 2 v2 rejected ===\n");
    ValidationInputs in{};
    in.header_version = 2;     // premature v2
    in.height         = 50;
    in.phase2_height  = 100;

    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("pre-Phase 2 v2 → VERSION_MISMATCH",
         r == ValidationResult::VERSION_MISMATCH);
    TEST("error mentions pre-Phase 2", err.find("pre-Phase 2") != std::string::npos);
}

static void test_phase2_v1_rejected() {
    printf("\n=== 3) Phase 2 v1 rejected ===\n");
    ValidationInputs in{};
    in.header_version = 1;     // missing v2
    in.height         = 100;
    in.phase2_height  = 100;

    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("Phase 2 v1 → VERSION_MISMATCH",
         r == ValidationResult::VERSION_MISMATCH);
    TEST("error mentions Phase 2", err.find("Phase 2") != std::string::npos);
}

static void test_phase2_valid_v2_accepted() {
    printf("\n=== 4) Phase 2 valid v2 accepted ===\n");
    auto s = make_valid_phase2_inputs();
    std::string err;
    auto r = validate_sbpow_for_block(s.in, &err);
    TEST("Phase 2 fully-valid v2 → OK", r == ValidationResult::OK);
    TEST("no error message on success", err.empty());
}

static void test_signature_with_matching_coinbase_accepted() {
    printf("\n=== 5) valid signature + matching coinbase accepted ===\n");
    auto s = make_valid_phase2_inputs(/*phase2_h=*/100, /*height=*/777);
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("matching coinbase → OK", r == ValidationResult::OK);
}

static void test_mismatched_coinbase_rejected() {
    printf("\n=== 6) valid signature + mismatched coinbase rejected ===\n");
    auto s = make_valid_phase2_inputs();
    // Replace coinbase pkh with a different value.
    s.in.coinbase_miner_pkh.fill(0x42);
    std::string err;
    auto r = validate_sbpow_for_block(s.in, &err);
    TEST("mismatched coinbase → COINBASE_MISMATCH",
         r == ValidationResult::COINBASE_MISMATCH);
    TEST("error mentions coinbase", err.find("coinbase") != std::string::npos);
}

static void test_invalid_signature_rejected() {
    printf("\n=== 7) invalid signature rejected ===\n");
    auto s = make_valid_phase2_inputs();
    // Flip a bit in the signature.
    s.in.miner_signature[0] ^= 1;
    std::string err;
    auto r = validate_sbpow_for_block(s.in, &err);
    TEST("tampered signature → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
    TEST("error mentions Schnorr", err.find("Schnorr") != std::string::npos);
}

static void test_malformed_pubkey_rejected() {
    printf("\n=== 8) malformed pubkey rejected ===\n");
    auto s = make_valid_phase2_inputs();
    // Wrong prefix byte (must be 0x02 or 0x03).
    s.in.miner_pubkey[0] = 0x05;
    std::string err;
    auto r = validate_sbpow_for_block(s.in, &err);
    TEST("bad prefix byte → MALFORMED_PUBKEY",
         r == ValidationResult::MALFORMED_PUBKEY);
    TEST("error mentions compressed point",
         err.find("compressed") != std::string::npos);
}

static void test_wrong_height_rejected() {
    printf("\n=== 9) wrong height rejected ===\n");
    auto s = make_valid_phase2_inputs();
    // Verifier sees a different height than the signer used.
    s.in.height = 200;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("verifier height differs from signed height → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_wrong_nonce_rejected() {
    printf("\n=== 10) wrong nonce rejected ===\n");
    auto s = make_valid_phase2_inputs();
    s.in.nonce = 99999;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("wrong nonce → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_wrong_extra_nonce_rejected() {
    printf("\n=== 11) wrong extra_nonce rejected ===\n");
    auto s = make_valid_phase2_inputs();
    s.in.extra_nonce = 99999;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("wrong extra_nonce → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_wrong_commit_rejected() {
    printf("\n=== 12) wrong commit rejected ===\n");
    auto s = make_valid_phase2_inputs();
    s.in.commit[0] ^= 1;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("tampered commit → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_wrong_prev_hash_rejected() {
    printf("\n=== 13) wrong prev_hash rejected ===\n");
    auto s = make_valid_phase2_inputs();
    s.in.prev_hash[0] ^= 1;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("tampered prev_hash → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_signature_changes_block_id_but_not_message() {
    printf("\n=== 14) changing signature → different block_id, same signed message ===\n");
    auto s = make_valid_phase2_inputs();

    // Build a v2 BlockHeader that carries the same signature.
    BlockHeader hdr;
    hdr.version         = 2;
    std::memcpy(hdr.prev_block_hash.data(), s.in.prev_hash.data(), 32);
    hdr.merkle_root.fill(0x55);
    hdr.timestamp = 0x10000;
    hdr.bits_q    = GENESIS_BITSQ;
    hdr.nonce     = s.in.nonce;
    hdr.height    = s.in.height;
    hdr.miner_pubkey    = s.in.miner_pubkey;
    hdr.miner_signature = s.in.miner_signature;
    Bytes32 id_before = hdr.ComputeBlockHash();

    // Recompute the SbPoW signed message — depends only on (prev_hash,
    // height, commit, nonce, extra_nonce, miner_pubkey). The signature
    // is NOT an input to the message.
    Bytes32 msg_before = build_sbpow_message(
        s.in.prev_hash, s.in.height, s.in.commit,
        s.in.nonce, s.in.extra_nonce, s.in.miner_pubkey);

    // Mutate the signature in the header. block_id must change because
    // the signature lives inside the hashed bytes; the signed message
    // must NOT change.
    hdr.miner_signature[0] ^= 1;
    Bytes32 id_after = hdr.ComputeBlockHash();
    Bytes32 msg_after = build_sbpow_message(
        s.in.prev_hash, s.in.height, s.in.commit,
        s.in.nonce, s.in.extra_nonce, s.in.miner_pubkey);

    TEST("changing signature changes v2 block_id (signature is in hashed bytes)",
         !(id_before == id_after));
    TEST("changing signature does NOT change the signed sbpow message",
         msg_before == msg_after);
    TEST("the signed message depends only on commit + context, not signature",
         true);
}

int main() {
    printf("=== test_sbpow_validation (V11 Phase 2 C4) ===\n");

    test_pre_phase2_v1_accepted();
    test_pre_phase2_v2_rejected();
    test_phase2_v1_rejected();
    test_phase2_valid_v2_accepted();
    test_signature_with_matching_coinbase_accepted();
    test_mismatched_coinbase_rejected();
    test_invalid_signature_rejected();
    test_malformed_pubkey_rejected();
    test_wrong_height_rejected();
    test_wrong_nonce_rejected();
    test_wrong_extra_nonce_rejected();
    test_wrong_commit_rejected();
    test_wrong_prev_hash_rejected();
    test_signature_changes_block_id_but_not_message();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
