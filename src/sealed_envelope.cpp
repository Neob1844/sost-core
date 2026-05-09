// sealed_envelope.cpp — single-recipient ECIES envelope (Fase Sealed-1.A).
// See include/sost/sealed_envelope.h for the on-the-wire layout and the
// security rationale. This file owns ONLY the cryptographic motor: it does
// not know about SCPv1 capsule headers, mempool policy, or wallet UI; the
// callers wrap the resulting body with the 12-byte capsule header and
// route the type code (0x02 / 0x04 / 0x06).

#include "sost/sealed_envelope.h"
#include "sost/tx_signer.h"     // ComputePubKeyHash

#include <secp256k1.h>
#include <secp256k1_ecdh.h>

#include <openssl/evp.h>
#include <openssl/kdf.h>
#include <openssl/rand.h>
#include <openssl/core_names.h>

#include <algorithm>
#include <cstring>
#include <mutex>

namespace sost {

namespace {

// libsecp256k1 context (sign + verify). Created once on first use; mirrors
// the singleton in tx_signer.cpp so we don't double-randomise.
static secp256k1_context* GetCtx() {
    static std::once_flag once;
    static secp256k1_context* ctx = nullptr;
    std::call_once(once, []{
        ctx = secp256k1_context_create(
            SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
        Byte seed[32];
        if (RAND_bytes(seed, 32) == 1) {
            secp256k1_context_randomize(ctx, seed);
        }
    });
    return ctx;
}

// HKDF-SHA256 (RFC 5869). OpenSSL 3.x via EVP_KDF.
static bool hkdf_sha256(const uint8_t* ikm, size_t ikm_len,
                        const uint8_t* salt, size_t salt_len,
                        const uint8_t* info, size_t info_len,
                        uint8_t* out, size_t out_len) {
    EVP_KDF*     kdf = EVP_KDF_fetch(nullptr, "HKDF", nullptr);
    if (!kdf) return false;
    EVP_KDF_CTX* ctx = EVP_KDF_CTX_new(kdf);
    EVP_KDF_free(kdf);
    if (!ctx) return false;

    OSSL_PARAM params[5];
    char digest[] = "SHA256";
    params[0] = OSSL_PARAM_construct_utf8_string(OSSL_KDF_PARAM_DIGEST, digest, 0);
    params[1] = OSSL_PARAM_construct_octet_string(OSSL_KDF_PARAM_KEY,
                    const_cast<uint8_t*>(ikm), ikm_len);
    params[2] = OSSL_PARAM_construct_octet_string(OSSL_KDF_PARAM_SALT,
                    const_cast<uint8_t*>(salt), salt_len);
    params[3] = OSSL_PARAM_construct_octet_string(OSSL_KDF_PARAM_INFO,
                    const_cast<uint8_t*>(info), info_len);
    params[4] = OSSL_PARAM_construct_end();

    int rc = EVP_KDF_derive(ctx, out, out_len, params);
    EVP_KDF_CTX_free(ctx);
    return rc == 1;
}

// AES-256-GCM with AAD. Returns false on encryption error or too-short
// output buffer. Caller pre-sizes ciphertext to plaintext_len.
static bool aes_gcm_seal(const uint8_t* key,
                         const uint8_t* nonce, size_t nonce_len,
                         const uint8_t* aad,   size_t aad_len,
                         const uint8_t* pt,    size_t pt_len,
                         uint8_t* ct_out,
                         uint8_t* tag_out) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;
    bool ok = false;
    int outlen = 0, tmplen = 0;
    do {
        if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)nonce_len, nullptr) != 1) break;
        if (EVP_EncryptInit_ex(ctx, nullptr, nullptr, key, nonce) != 1) break;
        if (aad_len > 0) {
            if (EVP_EncryptUpdate(ctx, nullptr, &outlen, aad, (int)aad_len) != 1) break;
        }
        if (EVP_EncryptUpdate(ctx, ct_out, &outlen, pt, (int)pt_len) != 1) break;
        if (EVP_EncryptFinal_ex(ctx, ct_out + outlen, &tmplen) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG,
                                (int)SEALED_TAG_BYTES, tag_out) != 1) break;
        ok = true;
    } while (false);
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

static bool aes_gcm_open(const uint8_t* key,
                         const uint8_t* nonce, size_t nonce_len,
                         const uint8_t* aad,   size_t aad_len,
                         const uint8_t* ct,    size_t ct_len,
                         const uint8_t* tag,
                         uint8_t* pt_out) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;
    bool ok = false;
    int outlen = 0, tmplen = 0;
    do {
        if (EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)nonce_len, nullptr) != 1) break;
        if (EVP_DecryptInit_ex(ctx, nullptr, nullptr, key, nonce) != 1) break;
        if (aad_len > 0) {
            if (EVP_DecryptUpdate(ctx, nullptr, &outlen, aad, (int)aad_len) != 1) break;
        }
        if (EVP_DecryptUpdate(ctx, pt_out, &outlen, ct, (int)ct_len) != 1) break;
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG,
                                (int)SEALED_TAG_BYTES,
                                const_cast<uint8_t*>(tag)) != 1) break;
        if (EVP_DecryptFinal_ex(ctx, pt_out + outlen, &tmplen) != 1) break;
        ok = true;
    } while (false);
    EVP_CIPHER_CTX_free(ctx);
    return ok;
}

// secp256k1 ECDH. libsecp256k1 by default returns SHA256(0x02||x), which is
// fine for our HKDF input — we domain-separate with the info string anyway.
static bool ecdh_shared(const uint8_t* our_privkey32,
                        const uint8_t* their_pubkey33,
                        uint8_t out[32]) {
    secp256k1_context* ctx = GetCtx();
    secp256k1_pubkey   pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, their_pubkey33, 33)) return false;
    return secp256k1_ecdh(ctx, out, &pk, our_privkey32, nullptr, nullptr) == 1;
}

// Domain-separation string for the HKDF info parameter. Bumping this in a
// future format would break compatibility with V1 envelopes — that's the
// point.
static const char* DOMAIN_SEP_V1 = "SOST_CAPSULE_SEALED_V1";

}  // anon

// =============================================================================
// SealSingleRecipientWithSeeds — deterministic core. SealSingleRecipient is a
// thin wrapper that supplies random eph_priv + nonce; tests pass fixed seeds
// to produce stable hex vectors comparable across implementations.
// =============================================================================
bool SealSingleRecipientWithSeeds(const std::vector<Byte>& plaintext,
                                  const Byte               eph_priv[32],
                                  const std::vector<Byte>& recipient_pubkey,
                                  const PubKeyHash&        recipient_pkh,
                                  const Byte               nonce[SEALED_NONCE_BYTES],
                                  std::vector<Byte>&       out_envelope,
                                  std::string*             err) {
    out_envelope.clear();
    if (plaintext.size() > SEALED_PLAINTEXT_MAX) {
        if (err) *err = "sealed: plaintext exceeds " +
                        std::to_string(SEALED_PLAINTEXT_MAX) + " bytes";
        return false;
    }
    if (recipient_pubkey.size() != SEALED_EPUB_BYTES) {
        if (err) *err = "sealed: recipient pubkey must be 33 bytes (compressed)";
        return false;
    }
    secp256k1_context* ctx = GetCtx();
    secp256k1_pubkey   _pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &_pk,
                                   recipient_pubkey.data(),
                                   recipient_pubkey.size())) {
        if (err) *err = "sealed: invalid recipient pubkey";
        return false;
    }
    // Coherence: hash160(recipient_pubkey) must equal the supplied
    // recipient_pkh. If they disagree the caller has glued the wrong
    // pubkey to the wrong address and the envelope would be sealed for a
    // recipient that the real address-holder cannot open. Reject before
    // doing any ECDH or key derivation. Belongs in the crypto motor
    // (not the wallet) so every consumer benefits.
    {
        PubKey rp_arr;
        std::memcpy(rp_arr.data(), recipient_pubkey.data(), SEALED_EPUB_BYTES);
        PubKeyHash derived = ComputePubKeyHash(rp_arr);
        if (!std::equal(derived.begin(), derived.end(), recipient_pkh.begin())) {
            if (err) *err = "sealed: recipient pubkey does not match recipient pkh";
            return false;
        }
    }

    // Validate the supplied ephemeral secret + derive its compressed pubkey.
    secp256k1_pubkey eph_pub_obj;
    if (secp256k1_ec_seckey_verify(ctx, eph_priv) != 1) {
        if (err) *err = "sealed: ephemeral priv invalid";
        return false;
    }
    if (secp256k1_ec_pubkey_create(ctx, &eph_pub_obj, eph_priv) != 1) {
        if (err) *err = "sealed: ephemeral priv invalid";
        return false;
    }
    Byte   eph_pub[SEALED_EPUB_BYTES];
    size_t pub_len = SEALED_EPUB_BYTES;
    if (!secp256k1_ec_pubkey_serialize(ctx, eph_pub, &pub_len,
                                       &eph_pub_obj, SECP256K1_EC_COMPRESSED) ||
        pub_len != SEALED_EPUB_BYTES) {
        if (err) *err = "sealed: pubkey serialise failed";
        return false;
    }

    // ECDH + HKDF-SHA256 → AES-256 key.
    Byte shared[32];
    if (!ecdh_shared(eph_priv, recipient_pubkey.data(), shared)) {
        if (err) *err = "sealed: ECDH failed";
        return false;
    }
    Byte aes_key[SEALED_AES_KEY_BYTES];
    if (!hkdf_sha256(shared, sizeof(shared),
                     eph_pub, SEALED_EPUB_BYTES,             // salt
                     reinterpret_cast<const uint8_t*>(DOMAIN_SEP_V1),
                     std::strlen(DOMAIN_SEP_V1),
                     aes_key, sizeof(aes_key))) {
        if (err) *err = "sealed: HKDF failed";
        return false;
    }

    // Lay out the AAD prefix in-place. Anything before the ciphertext is AAD.
    out_envelope.reserve(SEALED_FIXED_OVERHEAD + plaintext.size());
    out_envelope.push_back(SEALED_ENVELOPE_VERSION);
    out_envelope.push_back(0x01);  // recipient_count
    out_envelope.insert(out_envelope.end(),
                        recipient_pkh.begin(), recipient_pkh.end());
    out_envelope.insert(out_envelope.end(), eph_pub, eph_pub + SEALED_EPUB_BYTES);
    out_envelope.insert(out_envelope.end(), nonce, nonce + SEALED_NONCE_BYTES);
    uint16_t ct_len = (uint16_t)plaintext.size();
    out_envelope.push_back((uint8_t)(ct_len & 0xFF));
    out_envelope.push_back((uint8_t)((ct_len >> 8) & 0xFF));
    const size_t aad_len = out_envelope.size();   // 69 bytes

    // Append space for ciphertext + tag, then encrypt in place.
    out_envelope.resize(aad_len + plaintext.size() + SEALED_TAG_BYTES);
    Byte* ct_dst  = out_envelope.data() + aad_len;
    Byte* tag_dst = ct_dst + plaintext.size();
    if (!aes_gcm_seal(aes_key,
                      nonce, SEALED_NONCE_BYTES,
                      out_envelope.data(), aad_len,
                      plaintext.data(), plaintext.size(),
                      ct_dst, tag_dst)) {
        if (err) *err = "sealed: AES-GCM encryption failed";
        out_envelope.clear();
        return false;
    }
    return true;
}

// =============================================================================
// SealSingleRecipient — random-seeds wrapper around the deterministic core.
// =============================================================================
bool SealSingleRecipient(const std::vector<Byte>& plaintext,
                         const std::vector<Byte>& recipient_pubkey,
                         const PubKeyHash&        recipient_pkh,
                         std::vector<Byte>&       out_envelope,
                         std::string*             err) {
    Byte eph_priv[32];
    Byte nonce[SEALED_NONCE_BYTES];
    secp256k1_context* ctx = GetCtx();
    // Generate ephemeral keypair (retry until libsecp256k1 accepts the seed).
    bool ok = false;
    for (int i = 0; i < 16; ++i) {
        if (RAND_bytes(eph_priv, 32) != 1) {
            if (err) *err = "sealed: RAND_bytes failed";
            return false;
        }
        if (secp256k1_ec_seckey_verify(ctx, eph_priv) == 1) { ok = true; break; }
    }
    if (!ok) {
        if (err) *err = "sealed: could not generate ephemeral keypair";
        return false;
    }
    if (RAND_bytes(nonce, SEALED_NONCE_BYTES) != 1) {
        if (err) *err = "sealed: nonce RAND_bytes failed";
        return false;
    }
    return SealSingleRecipientWithSeeds(plaintext, eph_priv,
                                        recipient_pubkey, recipient_pkh,
                                        nonce, out_envelope, err);
}

// =============================================================================
// OpenSingleRecipient
// =============================================================================
bool OpenSingleRecipient(const std::vector<Byte>& envelope,
                         const PrivKey&           our_privkey,
                         std::vector<Byte>&       out_plaintext,
                         std::string*             err) {
    out_plaintext.clear();
    if (envelope.size() < SEALED_FIXED_OVERHEAD) {
        if (err) *err = "sealed: envelope truncated";
        return false;
    }
    if (envelope[0] != SEALED_ENVELOPE_VERSION) {
        if (err) *err = "sealed: unsupported envelope version";
        return false;
    }
    if (envelope[1] != 0x01) {
        if (err) *err = "sealed: unsupported recipient_count "
                        "(only single-recipient is wired in this fase)";
        return false;
    }
    PubKeyHash hint_pkh;
    std::memcpy(hint_pkh.data(), envelope.data() + 2, SEALED_PKH_BYTES);

    const uint8_t* eph_pub = envelope.data() + 22;
    const uint8_t* nonce   = envelope.data() + 55;
    uint16_t ct_len = (uint16_t)envelope[67] |
                      ((uint16_t)envelope[68] << 8);
    const size_t need = SEALED_FIXED_OVERHEAD + (size_t)ct_len;
    if (envelope.size() != need) {
        if (err) *err = "sealed: envelope length / ct_len mismatch";
        return false;
    }

    // Derive our pkh from the privkey to short-circuit envelopes that were
    // not addressed to us. This avoids spending an ECDH per scanned tx.
    secp256k1_context* ctx = GetCtx();
    secp256k1_pubkey   our_pub_obj;
    if (!secp256k1_ec_pubkey_create(ctx, &our_pub_obj, our_privkey.data())) {
        if (err) *err = "sealed: bad private key";
        return false;
    }
    PubKey our_pub_arr;
    size_t pub_len = 33;
    secp256k1_ec_pubkey_serialize(ctx, our_pub_arr.data(), &pub_len, &our_pub_obj,
                                  SECP256K1_EC_COMPRESSED);
    PubKeyHash our_pkh = ComputePubKeyHash(our_pub_arr);
    if (!std::equal(our_pkh.begin(), our_pkh.end(), hint_pkh.begin())) {
        if (err) *err = "sealed: not addressed to this key";
        return false;
    }

    // ECDH + HKDF.
    Byte shared[32];
    if (!ecdh_shared(our_privkey.data(), eph_pub, shared)) {
        if (err) *err = "sealed: ECDH failed";
        return false;
    }
    Byte aes_key[SEALED_AES_KEY_BYTES];
    if (!hkdf_sha256(shared, sizeof(shared),
                     eph_pub, SEALED_EPUB_BYTES,
                     reinterpret_cast<const uint8_t*>(DOMAIN_SEP_V1),
                     std::strlen(DOMAIN_SEP_V1),
                     aes_key, sizeof(aes_key))) {
        if (err) *err = "sealed: HKDF failed";
        return false;
    }

    // AAD = first 69 bytes of envelope (everything before ciphertext).
    const size_t aad_len = 69;
    const uint8_t* ct  = envelope.data() + aad_len;
    const uint8_t* tag = envelope.data() + aad_len + ct_len;

    out_plaintext.resize(ct_len);
    if (!aes_gcm_open(aes_key,
                      nonce, SEALED_NONCE_BYTES,
                      envelope.data(), aad_len,
                      ct, ct_len,
                      tag,
                      out_plaintext.data())) {
        if (err) *err = "sealed: authentication failed";
        out_plaintext.clear();
        return false;
    }
    return true;
}

// =============================================================================
// PeekSealedRecipientPkh
// =============================================================================
bool PeekSealedRecipientPkh(const std::vector<Byte>& envelope,
                            PubKeyHash&              out_pkh) {
    if (envelope.size() < 22) return false;
    if (envelope[0] != SEALED_ENVELOPE_VERSION) return false;
    if (envelope[1] != 0x01) return false;
    std::memcpy(out_pkh.data(), envelope.data() + 2, SEALED_PKH_BYTES);
    return true;
}

}  // namespace sost
