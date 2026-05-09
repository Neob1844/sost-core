// Sealed-envelope round-trip + tamper tests.
//
// Covers the cryptographic motor in src/sealed_envelope.cpp without going
// through any wallet, mempool, or capsule-header layer. The goal is to
// pin down the exact security properties before any of those layers are
// allowed to depend on them:
//
//   1. A→B happy path round-trips a 158-byte plaintext (the spec maximum).
//   2. C cannot decrypt B's envelope — wrong-key path is rejected.
//   3. PeekSealedRecipientPkh returns the right hint without doing ECDH.
//   4. Single-byte tamper on each region (header, ephemeral pubkey, nonce,
//      ciphertext, tag) makes decryption fail with a clear error.
//   5. Plaintext over the 158-byte cap is rejected by the builder.
//   6. recipient_count != 1 in the envelope is rejected on open
//      (forwards-compat with a future multi-recipient fase that we are
//      explicitly NOT building yet).
//   7. The ciphertext bytes never equal the plaintext bytes — a basic
//      "did we actually encrypt?" sanity check.

#include "sost/sealed_envelope.h"
#include "sost/tx_signer.h"

#include <secp256k1.h>
#include <openssl/rand.h>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ----- helpers ---------------------------------------------------------------

struct KeyPair {
    PrivKey    priv;
    PubKey     pub;     // compressed
    PubKeyHash pkh;
};

static KeyPair gen_keypair() {
    secp256k1_context* ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    KeyPair kp{};
    secp256k1_pubkey pk;
    for (;;) {
        if (RAND_bytes(kp.priv.data(), 32) != 1) std::exit(2);
        if (secp256k1_ec_seckey_verify(ctx, kp.priv.data()) == 1 &&
            secp256k1_ec_pubkey_create(ctx, &pk, kp.priv.data()) == 1) break;
    }
    size_t plen = 33;
    secp256k1_ec_pubkey_serialize(ctx, kp.pub.data(), &plen, &pk,
                                  SECP256K1_EC_COMPRESSED);
    kp.pkh = ComputePubKeyHash(kp.pub);
    secp256k1_context_destroy(ctx);
    return kp;
}

static std::vector<Byte> str_bytes(const std::string& s) {
    return std::vector<Byte>(s.begin(), s.end());
}

// ----- tests -----------------------------------------------------------------

static void test_roundtrip_happy_path() {
    printf("\n=== 1) Happy path A → B round-trip ===\n");
    KeyPair A = gen_keypair();
    KeyPair B = gen_keypair();

    auto pt = str_bytes("category=APP rewards distribution; ref=batch-001; period=2026-05; note=test");
    std::vector<Byte> env;
    std::string err;
    bool ok = SealSingleRecipient(
        pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);
    TEST("SealSingleRecipient succeeds", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }
    TEST("envelope size is 85 + plaintext_len",
         env.size() == 85 + pt.size());

    std::vector<Byte> recovered;
    bool ok2 = OpenSingleRecipient(env, B.priv, recovered, &err);
    TEST("OpenSingleRecipient with B's privkey succeeds", ok2);
    if (!ok2) { printf("    err: %s\n", err.c_str()); return; }
    TEST("recovered plaintext matches original",
         recovered == pt);

    // Sanity: ciphertext bytes must NOT equal plaintext bytes (we actually
    // encrypted something). Compare the ct region only.
    bool any_ct_byte_differs = false;
    for (size_t i = 0; i < pt.size(); ++i) {
        if (env[69 + i] != pt[i]) { any_ct_byte_differs = true; break; }
    }
    TEST("ciphertext is not the plaintext", any_ct_byte_differs);
}

static void test_max_plaintext() {
    printf("\n=== 2) Max plaintext (158 bytes) round-trips, 159 rejected ===\n");
    KeyPair A = gen_keypair();
    KeyPair B = gen_keypair();
    std::vector<Byte> pt158(158, 0xAB);
    std::vector<Byte> env;
    std::string err;
    TEST("158-byte plaintext seals OK",
         SealSingleRecipient(pt158,
             std::vector<Byte>(B.pub.begin(), B.pub.end()),
             B.pkh, env, &err));
    std::vector<Byte> got;
    TEST("158-byte plaintext opens OK",
         OpenSingleRecipient(env, B.priv, got, &err) && got == pt158);

    std::vector<Byte> pt159(159, 0xCD);
    env.clear(); err.clear();
    bool over_ok = SealSingleRecipient(pt159,
         std::vector<Byte>(B.pub.begin(), B.pub.end()),
         B.pkh, env, &err);
    TEST("159-byte plaintext is rejected by SealSingleRecipient", !over_ok);
    TEST("error mentions 158-byte cap",
         err.find("158") != std::string::npos);
}

static void test_wrong_key_rejected() {
    printf("\n=== 3) C cannot decrypt B's envelope ===\n");
    KeyPair B = gen_keypair();
    KeyPair C = gen_keypair();

    auto pt = str_bytes("hello B, only B should read this");
    std::vector<Byte> env;
    std::string err;
    SealSingleRecipient(pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);

    std::vector<Byte> got;
    err.clear();
    bool c_ok = OpenSingleRecipient(env, C.priv, got, &err);
    TEST("C with C's privkey CANNOT open B's envelope", !c_ok);
    TEST("error reports 'not addressed to this key'",
         err.find("not addressed") != std::string::npos);
    TEST("recovered plaintext is empty on failure", got.empty());
}

static void test_peek_pkh_no_ecdh() {
    printf("\n=== 4) PeekSealedRecipientPkh returns hint without decryption ===\n");
    KeyPair B = gen_keypair();
    auto pt = str_bytes("xx");
    std::vector<Byte> env;
    std::string err;
    SealSingleRecipient(pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);

    PubKeyHash got_pkh{};
    TEST("PeekSealedRecipientPkh succeeds", PeekSealedRecipientPkh(env, got_pkh));
    TEST("peeked pkh equals recipient pkh",
         std::equal(got_pkh.begin(), got_pkh.end(), B.pkh.begin()));

    std::vector<Byte> tiny(10, 0);
    PubKeyHash dummy{};
    TEST("Peek on too-short envelope fails",
         !PeekSealedRecipientPkh(tiny, dummy));
}

static void test_tamper_each_region() {
    printf("\n=== 5) Tampering any region makes Open fail ===\n");
    KeyPair B = gen_keypair();
    auto pt = str_bytes("authentic message");
    std::vector<Byte> env;
    std::string err;
    SealSingleRecipient(pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);

    auto try_open_after_flip = [&](size_t off, const char* region) {
        std::vector<Byte> bad = env;
        bad[off] ^= 0x01;
        std::vector<Byte> out;
        std::string e;
        bool ok = OpenSingleRecipient(bad, B.priv, out, &e);
        char buf[128];
        snprintf(buf, sizeof(buf), "tamper at offset %zu (%s) is rejected", off, region);
        TEST(buf, !ok);
    };

    try_open_after_flip(0,                "version byte");
    try_open_after_flip(1,                "recipient_count");
    try_open_after_flip(5,                "recipient_pkh");        // pkh mismatch path
    try_open_after_flip(22 + 5,           "ephemeral pubkey");      // changes shared secret
    try_open_after_flip(55 + 4,           "nonce");                 // GCM tag fails
    try_open_after_flip(69,               "ciphertext byte 0");
    try_open_after_flip(env.size() - 1,   "auth tag last byte");
}

static void test_short_envelope_rejected() {
    printf("\n=== 6) Truncated envelope is rejected ===\n");
    KeyPair B = gen_keypair();
    auto pt = str_bytes("xx");
    std::vector<Byte> env;
    std::string err;
    SealSingleRecipient(pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);

    std::vector<Byte> trunc(env.begin(), env.begin() + 60);
    std::vector<Byte> got;
    err.clear();
    TEST("opening a 60-byte truncated envelope fails",
         !OpenSingleRecipient(trunc, B.priv, got, &err));
    TEST("error mentions 'truncated'",
         err.find("truncated") != std::string::npos);
}

static void test_multi_recipient_count_rejected() {
    printf("\n=== 7) recipient_count != 1 is rejected (single-recipient fase) ===\n");
    KeyPair B = gen_keypair();
    auto pt = str_bytes("xx");
    std::vector<Byte> env;
    std::string err;
    SealSingleRecipient(pt,
        std::vector<Byte>(B.pub.begin(), B.pub.end()),
        B.pkh, env, &err);

    // Spoof recipient_count = 2. AAD covers this byte, so even if we somehow
    // bypassed the explicit check, AES-GCM would reject the tampered AAD.
    env[1] = 0x02;
    std::vector<Byte> got;
    err.clear();
    bool ok = OpenSingleRecipient(env, B.priv, got, &err);
    TEST("recipient_count=2 envelope is refused on open", !ok);
}

int main() {
    printf("\n=== Sealed envelope round-trip + tamper tests ===\n");
    test_roundtrip_happy_path();
    test_max_plaintext();
    test_wrong_key_rejected();
    test_peek_pkh_no_ecdh();
    test_tamper_each_region();
    test_short_envelope_rejected();
    test_multi_recipient_count_rejected();
    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
