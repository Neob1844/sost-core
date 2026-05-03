// V11 Phase 2 — SbPoW signing tests (Commit 3 scope).
//
// Covers the signing-side API only:
//   - build_sbpow_message (determinism + sensitivity to every input)
//   - derive_compressed_pubkey_from_privkey
//   - sign_sbpow_commitment + verify_sbpow_signature roundtrip
//   - secure_memzero
//
// Validator-side adversarial tests (tampered-sig rejection,
// pubkey-mismatch rejection, malformed pubkey, etc.) are C4 territory.
//
// schnorrsig availability: if libsecp256k1 was built without the
// schnorrsig module, the build fails earlier (configure-time) — by
// the time this binary runs, signing/verification must work. Any
// failure here therefore means a real bug, not a missing module.

#include "sost/sbpow.h"
#include "sost/crypto.h"

#include <cstdio>
#include <cstring>
#include <vector>

using namespace sost;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

// A privkey that is unambiguously valid: in [1, n-1], deterministic.
static MinerPrivkey fixture_privkey_a() {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(0x10 + i);
    return p;
}

static MinerPrivkey fixture_privkey_b() {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(0x80 + i);
    return p;
}

static Bytes32 fixture_prev_hash() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0xAA ^ i);
    return h;
}

static Bytes32 fixture_commit() {
    Bytes32 c{};
    for (size_t i = 0; i < 32; ++i) c[i] = (uint8_t)(0xCC ^ (i * 3));
    return c;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_pubkey_derivation_deterministic() {
    printf("\n=== pubkey derivation: deterministic ===\n");
    auto pk = fixture_privkey_a();
    MinerPubkey pub1{}, pub2{};
    bool ok1 = derive_compressed_pubkey_from_privkey(pk, pub1);
    bool ok2 = derive_compressed_pubkey_from_privkey(pk, pub2);
    TEST("derive_compressed_pubkey_from_privkey succeeds", ok1 && ok2);
    TEST("same privkey -> identical pubkey", pub1 == pub2);
    TEST("pubkey is 33 B compressed (prefix 02 or 03)",
         pub1[0] == 0x02 || pub1[0] == 0x03);

    // Different privkey -> different pubkey.
    auto pk_b = fixture_privkey_b();
    MinerPubkey pub_b{};
    TEST("second privkey derives", derive_compressed_pubkey_from_privkey(pk_b, pub_b));
    TEST("different privkey -> different pubkey", !(pub1 == pub_b));

    // Zero privkey is rejected.
    MinerPrivkey zero{};
    MinerPubkey pub_z{};
    TEST("zero privkey is rejected",
         !derive_compressed_pubkey_from_privkey(zero, pub_z));
}

static void test_message_construction_deterministic() {
    printf("\n=== build_sbpow_message: determinism ===\n");

    auto prev   = fixture_prev_hash();
    auto commit = fixture_commit();
    MinerPubkey pub{};
    derive_compressed_pubkey_from_privkey(fixture_privkey_a(), pub);

    Bytes32 m1 = build_sbpow_message(prev, /*height*/7000, commit,
                                     /*nonce*/12345, /*extra*/678, pub);
    Bytes32 m2 = build_sbpow_message(prev, /*height*/7000, commit,
                                     /*nonce*/12345, /*extra*/678, pub);
    TEST("same inputs -> identical message", m1 == m2);

    // Length sanity: SHA-256 output is always 32 bytes; non-zero in practice.
    bool any_nonzero = false;
    for (auto b : m1) if (b != 0) { any_nonzero = true; break; }
    TEST("message hash is non-zero", any_nonzero);
}

static void test_message_sensitivity_to_each_field() {
    printf("\n=== build_sbpow_message: sensitivity to each input ===\n");

    auto prev   = fixture_prev_hash();
    auto commit = fixture_commit();
    MinerPubkey pub_a{}, pub_b{};
    derive_compressed_pubkey_from_privkey(fixture_privkey_a(), pub_a);
    derive_compressed_pubkey_from_privkey(fixture_privkey_b(), pub_b);

    Bytes32 base = build_sbpow_message(prev, 7000, commit, 100, 200, pub_a);

    // Changing prev_hash.
    Bytes32 prev2 = prev; prev2[0] ^= 1;
    TEST("changing prev_hash changes message",
         !(base == build_sbpow_message(prev2, 7000, commit, 100, 200, pub_a)));

    // Changing height.
    TEST("changing height changes message",
         !(base == build_sbpow_message(prev, 7001, commit, 100, 200, pub_a)));

    // Changing commit.
    Bytes32 commit2 = commit; commit2[0] ^= 1;
    TEST("changing commit changes message",
         !(base == build_sbpow_message(prev, 7000, commit2, 100, 200, pub_a)));

    // Changing nonce.
    TEST("changing nonce changes message",
         !(base == build_sbpow_message(prev, 7000, commit, 101, 200, pub_a)));

    // Changing extra_nonce.
    TEST("changing extra_nonce changes message",
         !(base == build_sbpow_message(prev, 7000, commit, 100, 201, pub_a)));

    // Changing pubkey.
    TEST("changing pubkey changes message",
         !(base == build_sbpow_message(prev, 7000, commit, 100, 200, pub_b)));
}

static void test_signing_succeeds_and_is_deterministic() {
    printf("\n=== sign_sbpow_commitment: success + determinism ===\n");

    auto pk = fixture_privkey_a();
    MinerPubkey pub{};
    TEST("derive pubkey ok", derive_compressed_pubkey_from_privkey(pk, pub));

    Bytes32 msg = build_sbpow_message(fixture_prev_hash(), 7000,
                                      fixture_commit(), 42, 7, pub);
    MinerSignature sig1{}, sig2{};
    bool ok1 = sign_sbpow_commitment(pk, msg, sig1);
    bool ok2 = sign_sbpow_commitment(pk, msg, sig2);
    TEST("sign returns true", ok1 && ok2);

    // BIP-340 with aux_rand=null is RFC-6979 deterministic.
    TEST("same (privkey, msg) -> identical signature", sig1 == sig2);

    // Sanity: signature is not all zeros.
    bool any_nonzero = false;
    for (auto b : sig1) if (b != 0) { any_nonzero = true; break; }
    TEST("signature has non-zero bytes", any_nonzero);
}

static void test_zero_privkey_signing_rejected() {
    printf("\n=== sign_sbpow_commitment: zero privkey rejected ===\n");
    MinerPrivkey zero{};
    Bytes32 msg{}; msg.fill(0x42);
    MinerSignature sig{};
    bool ok = sign_sbpow_commitment(zero, msg, sig);
    TEST("zero privkey -> sign returns false", !ok);
}

static void test_sign_verify_roundtrip() {
    printf("\n=== sign + verify roundtrip ===\n");

    auto pk = fixture_privkey_a();
    MinerPubkey pub{};
    derive_compressed_pubkey_from_privkey(pk, pub);

    Bytes32 msg = build_sbpow_message(fixture_prev_hash(), 7000,
                                      fixture_commit(), 42, 7, pub);
    MinerSignature sig{};
    TEST("sign ok", sign_sbpow_commitment(pk, msg, sig));
    TEST("verify with correct pubkey + msg -> true",
         verify_sbpow_signature(pub, msg, sig));

    // Wrong pubkey -> verify fails.
    MinerPubkey pub_other{};
    derive_compressed_pubkey_from_privkey(fixture_privkey_b(), pub_other);
    TEST("verify with wrong pubkey -> false",
         !verify_sbpow_signature(pub_other, msg, sig));

    // Wrong message -> verify fails.
    Bytes32 msg_tampered = msg;
    msg_tampered[0] ^= 1;
    TEST("verify with tampered msg -> false",
         !verify_sbpow_signature(pub, msg_tampered, sig));

    // Tampered signature -> verify fails.
    MinerSignature sig_tampered = sig;
    sig_tampered[0] ^= 1;
    TEST("verify with tampered signature -> false",
         !verify_sbpow_signature(pub, msg, sig_tampered));
}

static void test_pkh_derivation() {
    printf("\n=== derive_pkh_from_pubkey ===\n");
    MinerPubkey pub{};
    derive_compressed_pubkey_from_privkey(fixture_privkey_a(), pub);

    PubKeyHash pkh1 = derive_pkh_from_pubkey(pub);
    PubKeyHash pkh2 = derive_pkh_from_pubkey(pub);
    TEST("same pubkey -> identical pkh", pkh1 == pkh2);

    bool any_nonzero = false;
    for (auto b : pkh1) if (b != 0) { any_nonzero = true; break; }
    TEST("pkh is non-zero", any_nonzero);

    MinerPubkey pub_b{};
    derive_compressed_pubkey_from_privkey(fixture_privkey_b(), pub_b);
    PubKeyHash pkh_b = derive_pkh_from_pubkey(pub_b);
    TEST("different pubkey -> different pkh", !(pkh1 == pkh_b));
}

static void test_secure_memzero() {
    printf("\n=== secure_memzero ===\n");

    uint8_t buf[64];
    for (size_t i = 0; i < sizeof(buf); ++i) buf[i] = (uint8_t)(0x55 ^ i);

    bool any_nonzero_before = false;
    for (auto b : buf) if (b != 0) { any_nonzero_before = true; break; }
    TEST("buffer has non-zero data before zeroing", any_nonzero_before);

    secure_memzero(buf, sizeof(buf));

    bool all_zero = true;
    for (auto b : buf) if (b != 0) { all_zero = false; break; }
    TEST("buffer is fully zeroed after secure_memzero", all_zero);

    // Edge cases: nullptr / zero len must not crash.
    secure_memzero(nullptr, 0);
    secure_memzero(buf, 0);
    TEST("secure_memzero(nullptr, 0) and (ptr, 0) survive", true);
}

int main() {
    printf("=== test_sbpow_signing (V11 Phase 2 C3) ===\n");

    test_pubkey_derivation_deterministic();
    test_message_construction_deterministic();
    test_message_sensitivity_to_each_field();
    test_signing_succeeds_and_is_deterministic();
    test_zero_privkey_signing_rejected();
    test_sign_verify_roundtrip();
    test_pkh_derivation();
    test_secure_memzero();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
