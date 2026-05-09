// sealed_envelope_fixture.cpp — deterministic vectors for cross-language
// validation between C++ and JS implementations of Fase Sealed-1.
//
// This program prints fixed-input/fixed-output hex strings the JS side
// must reproduce exactly. Anything else means JS and C++ disagree, and
// sealed broadcast must remain disabled (Fase Sealed-1.C-1 stays in
// "prepared, not active" mode until JS matches byte-for-byte).
//
// Output format (one key=value line per row, machine-parseable):
//
//   plaintext_hex=...
//   recipient_priv_hex=...
//   recipient_pub_hex=...
//   recipient_pkh_hex=...
//   eph_priv_hex=...
//   eph_pub_hex=...
//   nonce_hex=...
//   envelope_hex=...
//
// The JS test must read this output and produce a byte-equal envelope_hex
// from the same recipient_pub + recipient_pkh + eph_priv + nonce + plaintext.

#include "sost/sealed_envelope.h"
#include "sost/tx_signer.h"

#include <secp256k1.h>

#include <array>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static std::string hex(const uint8_t* d, size_t n) {
    static const char* x = "0123456789abcdef";
    std::string s; s.reserve(n*2);
    for (size_t i = 0; i < n; ++i) {
        s.push_back(x[d[i] >> 4]);
        s.push_back(x[d[i] & 0xF]);
    }
    return s;
}

static std::string hex_v(const std::vector<uint8_t>& v) {
    return hex(v.data(), v.size());
}

struct Vector {
    std::string  label;
    std::string  plaintext;
    PrivKey      recipient_priv;
    Byte         eph_priv[32];
    Byte         nonce[12];
};

static Vector V1() {
    Vector v;
    v.label     = "v1_open_note_short";
    v.plaintext = "hi";
    // Recipient priv = repeating 0x11
    for (int i = 0; i < 32; ++i) v.recipient_priv[i] = 0x11;
    // Ephemeral priv = repeating 0x22
    for (int i = 0; i < 32; ++i) v.eph_priv[i] = 0x22;
    // Nonce = 0x01..0x0c
    for (int i = 0; i < 12; ++i) v.nonce[i] = (uint8_t)(0x01 + i);
    return v;
}

static Vector V2() {
    Vector v;
    v.label     = "v2_structured_with_03_pubkey";
    v.plaintext = "category=APP rewards distribution; ref=batch-001; period=2026-05";
    // Recipient priv chosen so that its compressed pubkey starts with 0x03
    // (odd-y). Picked by trying small monotonically-incremented values
    // until the parity byte is 0x03 — gives JS a chance to expose the
    // libsecp256k1-vs-noble parity-byte hash divergence.
    for (int i = 0; i < 32; ++i) v.recipient_priv[i] = 0x33;
    for (int i = 0; i < 32; ++i) v.eph_priv[i] = 0x44;
    for (int i = 0; i < 12; ++i) v.nonce[i] = (uint8_t)(0xA0 + i);
    return v;
}

static void emit(const Vector& v) {
    secp256k1_context* ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);

    // Derive recipient pub + pkh.
    secp256k1_pubkey rp;
    if (secp256k1_ec_pubkey_create(ctx, &rp, v.recipient_priv.data()) != 1) {
        fprintf(stderr, "[%s] BAD recipient priv\n", v.label.c_str());
        std::exit(2);
    }
    PubKey rp_arr;
    size_t plen = 33;
    secp256k1_ec_pubkey_serialize(ctx, rp_arr.data(), &plen, &rp,
                                  SECP256K1_EC_COMPRESSED);
    PubKeyHash rp_pkh = ComputePubKeyHash(rp_arr);

    // Build envelope deterministically.
    std::vector<Byte> pt(v.plaintext.begin(), v.plaintext.end());
    std::vector<Byte> rp_vec(rp_arr.begin(), rp_arr.end());
    std::vector<Byte> envelope;
    std::string err;
    bool ok = SealSingleRecipientWithSeeds(pt, v.eph_priv,
                                           rp_vec, rp_pkh,
                                           v.nonce, envelope, &err);
    if (!ok) {
        fprintf(stderr, "[%s] FAIL %s\n", v.label.c_str(), err.c_str());
        std::exit(2);
    }

    // Derive ephemeral pubkey for the dump (also visible at envelope[22..55]).
    secp256k1_pubkey ep;
    secp256k1_ec_pubkey_create(ctx, &ep, v.eph_priv);
    Byte ep_pub[33]; size_t epl = 33;
    secp256k1_ec_pubkey_serialize(ctx, ep_pub, &epl, &ep, SECP256K1_EC_COMPRESSED);

    printf("---- %s ----\n", v.label.c_str());
    printf("plaintext_hex=%s\n",
           hex(reinterpret_cast<const uint8_t*>(v.plaintext.data()),
               v.plaintext.size()).c_str());
    printf("recipient_priv_hex=%s\n", hex(v.recipient_priv.data(), 32).c_str());
    printf("recipient_pub_hex=%s\n",  hex(rp_arr.data(), 33).c_str());
    printf("recipient_pkh_hex=%s\n",  hex(rp_pkh.data(), 20).c_str());
    printf("eph_priv_hex=%s\n",       hex(v.eph_priv, 32).c_str());
    printf("eph_pub_hex=%s\n",        hex(ep_pub, 33).c_str());
    printf("nonce_hex=%s\n",          hex(v.nonce, 12).c_str());
    printf("envelope_hex=%s\n",       hex_v(envelope).c_str());

    // Roundtrip self-test: open the envelope with recipient_priv and
    // confirm we recover the original plaintext.
    std::vector<Byte> recovered;
    err.clear();
    if (!OpenSingleRecipient(envelope, v.recipient_priv, recovered, &err)) {
        fprintf(stderr, "[%s] selftest open failed: %s\n",
                v.label.c_str(), err.c_str());
        std::exit(2);
    }
    if (recovered != pt) {
        fprintf(stderr, "[%s] selftest plaintext mismatch\n", v.label.c_str());
        std::exit(2);
    }
    printf("selftest=ok\n\n");

    secp256k1_context_destroy(ctx);
}

int main() {
    emit(V1());
    emit(V2());
    return 0;
}
