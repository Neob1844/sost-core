// V11 Phase 2 — SbPoW adversarial tests (Commit 4 scope).
//
// Each test models a real attack vector against the SbPoW validator.
// All scenarios MUST be rejected.
//
// Coverage (8 cases):
//   1. replay signature from a different block — rejected
//   2. replay pubkey paired with a different coinbase pkh — rejected
//   3. signature from key A presented with pubkey B — rejected
//   4. empty all-zero signature — rejected
//   5. all-zero pubkey — rejected
//   6. compressed pubkey with wrong prefix byte — rejected
//   7. v2 pre-Phase 2 rejected even when the signature would verify
//   8. v1 Phase 2 rejected even with an otherwise-valid PoW context

#include "sost/sbpow.h"

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
// Helpers
// ---------------------------------------------------------------------------

static MinerPrivkey priv(uint8_t seed) {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(seed ^ (i * 11));
    return p;
}

static Bytes32 hash32(uint8_t seed) {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(seed ^ (i * 13));
    return h;
}

// Build (in, privkey) with a genuine signature in `in` for a Phase 2 block.
struct Setup {
    ValidationInputs in;
    MinerPrivkey     privkey;
};

static Setup signed_phase2(uint8_t priv_seed,
                           int64_t height,
                           uint32_t nonce,
                           uint32_t extra,
                           uint8_t prev_seed,
                           uint8_t commit_seed,
                           int64_t phase2_h = 100) {
    Setup s;
    s.privkey = priv(priv_seed);
    bool ok = derive_compressed_pubkey_from_privkey(s.privkey, s.in.miner_pubkey);
    (void)ok;
    s.in.header_version = 2;
    s.in.prev_hash      = hash32(prev_seed);
    s.in.height         = height;
    s.in.commit         = hash32(commit_seed);
    s.in.nonce          = nonce;
    s.in.extra_nonce    = extra;
    s.in.coinbase_miner_pkh = derive_pkh_from_pubkey(s.in.miner_pubkey);
    s.in.phase2_height  = phase2_h;
    Bytes32 msg = build_sbpow_message(
        s.in.prev_hash, s.in.height, s.in.commit,
        s.in.nonce, s.in.extra_nonce, s.in.miner_pubkey);
    sign_sbpow_commitment(s.privkey, msg, s.in.miner_signature);
    return s;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_replay_signature_from_different_block() {
    printf("\n=== 1) replay signature from different block — rejected ===\n");
    // Block A: a genuine signature.
    auto a = signed_phase2(/*priv*/0x10, /*height*/100, /*nonce*/1, /*extra*/0,
                           /*prev*/0xAA, /*commit*/0xCC);
    // Block B: same miner, different prev_hash → different message.
    auto b = signed_phase2(/*priv*/0x10, /*height*/101, /*nonce*/2, /*extra*/0,
                           /*prev*/0xBB, /*commit*/0xDD);

    // Attacker takes A's signature and pastes it into B's header.
    ValidationInputs attack = b.in;
    attack.miner_signature  = a.in.miner_signature;

    auto r = validate_sbpow_for_block(attack, nullptr);
    TEST("replayed signature on different block → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_replay_pubkey_with_different_coinbase() {
    printf("\n=== 2) replay pubkey paired with foreign coinbase — rejected ===\n");
    auto a = signed_phase2(0x10, 100, 1, 0, 0xAA, 0xCC);

    // Attacker keeps the genuine pubkey + signature but routes the
    // coinbase miner-output to their own address (different pkh).
    ValidationInputs attack = a.in;
    attack.coinbase_miner_pkh.fill(0x99);  // attacker's pkh

    auto r = validate_sbpow_for_block(attack, nullptr);
    TEST("foreign coinbase + genuine signature → COINBASE_MISMATCH",
         r == ValidationResult::COINBASE_MISMATCH);
}

static void test_signature_from_keyA_with_pubkey_B() {
    printf("\n=== 3) signature from key A, pubkey B in header — rejected ===\n");
    auto a = signed_phase2(0x10, 100, 1, 0, 0xAA, 0xCC);
    // Derive a different pubkey (key B).
    MinerPubkey pub_b{};
    derive_compressed_pubkey_from_privkey(priv(0x80), pub_b);

    ValidationInputs attack = a.in;
    attack.miner_pubkey = pub_b;
    // coinbase pkh still matches A's pubkey (a.in already set it that way),
    // so the COINBASE_MISMATCH path could fire — but we want the SIG path,
    // so also align coinbase to B.
    attack.coinbase_miner_pkh = derive_pkh_from_pubkey(pub_b);

    auto r = validate_sbpow_for_block(attack, nullptr);
    TEST("sig from A, pubkey B → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_all_zero_signature_rejected() {
    printf("\n=== 4) empty all-zero signature — rejected ===\n");
    auto s = signed_phase2(0x10, 100, 1, 0, 0xAA, 0xCC);
    s.in.miner_signature.fill(0);
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("all-zero signature → SIGNATURE_INVALID",
         r == ValidationResult::SIGNATURE_INVALID);
}

static void test_all_zero_pubkey_rejected() {
    printf("\n=== 5) all-zero pubkey — rejected ===\n");
    auto s = signed_phase2(0x10, 100, 1, 0, 0xAA, 0xCC);
    s.in.miner_pubkey.fill(0);  // prefix becomes 0x00 → invalid
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("all-zero pubkey → MALFORMED_PUBKEY",
         r == ValidationResult::MALFORMED_PUBKEY);
}

static void test_compressed_pubkey_wrong_prefix() {
    printf("\n=== 6) compressed pubkey with wrong prefix byte — rejected ===\n");
    auto s = signed_phase2(0x10, 100, 1, 0, 0xAA, 0xCC);
    // Try several invalid prefix bytes (not 0x02/0x03).
    for (uint8_t prefix : {(uint8_t)0x00, (uint8_t)0x01, (uint8_t)0x04,
                            (uint8_t)0x05, (uint8_t)0xFF}) {
        s.in.miner_pubkey[0] = prefix;
        auto r = validate_sbpow_for_block(s.in, nullptr);
        char buf[80];
        std::snprintf(buf, sizeof(buf), "prefix 0x%02x → MALFORMED_PUBKEY", prefix);
        TEST(buf, r == ValidationResult::MALFORMED_PUBKEY);
    }
}

static void test_v2_pre_phase2_rejected_even_if_signature_valid() {
    printf("\n=== 7) v2 pre-Phase 2 rejected even with valid signature ===\n");
    auto s = signed_phase2(/*priv*/0x10,
                           /*height*/50,
                           /*nonce*/1, /*extra*/0,
                           /*prev*/0xAA, /*commit*/0xCC,
                           /*phase2_h*/100);
    // Signature is genuine, header_version=2, height=50 < phase2=100.
    // Should be rejected purely on the version gate, no signature
    // examination.
    s.in.header_version = 2;
    auto r = validate_sbpow_for_block(s.in, nullptr);
    TEST("v2 pre-Phase 2 → VERSION_MISMATCH (early rejection, sig untouched)",
         r == ValidationResult::VERSION_MISMATCH);
}

static void test_v1_phase2_rejected_even_with_valid_pow_context() {
    printf("\n=== 8) v1 Phase 2 rejected even if PoW context is otherwise valid ===\n");
    // Phase 2 active. header.version = 1. Reject regardless of any
    // signature fields the attacker would also try to provide.
    ValidationInputs in{};
    in.header_version = 1;
    in.height         = 100;
    in.phase2_height  = 100;
    auto r = validate_sbpow_for_block(in, nullptr);
    TEST("v1 Phase 2 → VERSION_MISMATCH",
         r == ValidationResult::VERSION_MISMATCH);
}

int main() {
    printf("=== test_sbpow_adversarial (V11 Phase 2 C4) ===\n");

    test_replay_signature_from_different_block();
    test_replay_pubkey_with_different_coinbase();
    test_signature_from_keyA_with_pubkey_B();
    test_all_zero_signature_rejected();
    test_all_zero_pubkey_rejected();
    test_compressed_pubkey_wrong_prefix();
    test_v2_pre_phase2_rejected_even_if_signature_valid();
    test_v1_phase2_rejected_even_with_valid_pow_context();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
