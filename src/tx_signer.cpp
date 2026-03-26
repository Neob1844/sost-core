// =============================================================================
// tx_signer.cpp — SOST Sighash + ECDSA (consensus-critical)
// =============================================================================
//
// MIGRATED: OpenSSL EC_KEY/ECDSA → libsecp256k1
// KEPT:     OpenSSL SHA256/RIPEMD160 (not deprecated, standard)
//
// Implements BIP143-simplified sighash and ECDSA secp256k1 signing/verification
// as specified in Design Document v1.2a, Sections 6 and 13.
//
// Sighash preimage (146 bytes fixed):
//   version(4) || tx_type(1) || hashPrevouts(32) || prev_txid ||
//   prev_index || spent_amount || spent_type ||
//   hashOutputs(32) || genesis_hash(32)
//
// All fields use Section 5 canonical encoding (little-endian integers).
// sighash = SHA256(SHA256(preimage))
//
// ECDSA: secp256k1, compressed keys, compact 64-byte (r||s big-endian), LOW-S.
//
// =============================================================================

#include "sost/tx_signer.h"

#include <secp256k1.h>

#include <openssl/sha.h>
#include <openssl/ripemd.h>
#include <openssl/rand.h>

#include <cstring>
#include <memory>

namespace sost {

// =============================================================================
// libsecp256k1 context (module-level, created once)
// =============================================================================

static secp256k1_context* GetSecp256k1Ctx() {
    // Thread-safe initialization (C++11 guarantees)
    static secp256k1_context* ctx = []() -> secp256k1_context* {
        secp256k1_context* c = secp256k1_context_create(
            SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
        if (c) {
            // Randomize context for side-channel protection
            unsigned char seed[32];
            if (RAND_bytes(seed, 32) == 1) {
                secp256k1_context_randomize(c, seed);
            }
        }
        return c;
    }();
    return ctx;
}

// =============================================================================
// Internal: double SHA256
// =============================================================================

static Hash256 DoubleSHA256(const uint8_t* data, size_t len) {
    Hash256 h1{}, h2{};
    SHA256(data, len, h1.data());
    SHA256(h1.data(), h1.size(), h2.data());
    return h2;
}

static Hash256 DoubleSHA256(const std::vector<Byte>& data) {
    return DoubleSHA256(data.data(), data.size());
}

// =============================================================================
// Internal: little-endian serialization helpers (same as transaction.cpp §5)
// =============================================================================

static void AppendU32LE(std::vector<Byte>& out, uint32_t v) {
    out.push_back(static_cast<Byte>(v & 0xFF));
    out.push_back(static_cast<Byte>((v >> 8) & 0xFF));
    out.push_back(static_cast<Byte>((v >> 16) & 0xFF));
    out.push_back(static_cast<Byte>((v >> 24) & 0xFF));
}

static void AppendI64LE(std::vector<Byte>& out, int64_t v) {
    uint64_t u = static_cast<uint64_t>(v);
    for (int i = 0; i < 8; ++i) {
        out.push_back(static_cast<Byte>(u & 0xFF));
        u >>= 8;
    }
}

static void AppendBytes(std::vector<Byte>& out, const uint8_t* src, size_t n) {
    out.insert(out.end(), src, src + n);
}

// =============================================================================
// Internal: secp256k1 half-order for LOW-S check
// =============================================================================

// curve_order / 2 =
// 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
static const unsigned char SECP256K1_HALF_ORDER[] = {
    0x7F, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0x5D, 0x57, 0x6E, 0x73, 0x57, 0xA4, 0x50, 0x1D,
    0xDF, 0xE9, 0x2F, 0x46, 0x68, 0x1B, 0x20, 0xA0
};

// =============================================================================
// ComputeHashPrevouts
// =============================================================================

Hash256 ComputeHashPrevouts(const Transaction& tx) {
    std::vector<Byte> buf;
    buf.reserve(tx.inputs.size() * 36);

    for (const auto& in : tx.inputs) {
        AppendBytes(buf, in.prev_txid.data(), 32);
        AppendU32LE(buf, in.prev_index);
    }

    return DoubleSHA256(buf);
}

// =============================================================================
// ComputeHashOutputs
// =============================================================================

Hash256 ComputeHashOutputs(const Transaction& tx) {
    std::vector<Byte> buf;
    buf.reserve(tx.outputs.size() * 30);

    for (const auto& out : tx.outputs) {
        if (out.payload.size() > 255) {
            Hash256 poison{};
            return poison;
        }

        AppendI64LE(buf, out.amount);
        buf.push_back(out.type);
        AppendBytes(buf, out.pubkey_hash.data(), 20);
        buf.push_back(static_cast<Byte>(out.payload.size()));
        if (!out.payload.empty()) {
            AppendBytes(buf, out.payload.data(), out.payload.size());
        }
    }

    return DoubleSHA256(buf);
}

// =============================================================================
// ComputeSighash
// =============================================================================

Hash256 ComputeSighash(
    const Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash)
{
    if (input_index >= tx.inputs.size()) {
        Hash256 poison{};
        return poison;
    }

    Hash256 hp = ComputeHashPrevouts(tx);
    Hash256 ho = ComputeHashOutputs(tx);

    std::vector<Byte> preimage;
    preimage.reserve(146);

    AppendU32LE(preimage, tx.version);
    preimage.push_back(tx.tx_type);
    AppendBytes(preimage, hp.data(), 32);
    AppendBytes(preimage, tx.inputs[input_index].prev_txid.data(), 32);
    AppendU32LE(preimage, tx.inputs[input_index].prev_index);
    AppendI64LE(preimage, spent.amount);
    preimage.push_back(spent.type);
    AppendBytes(preimage, ho.data(), 32);
    AppendBytes(preimage, genesis_hash.data(), 32);

    Hash256 result = DoubleSHA256(preimage);

    // DEBUG: Print sighash preimage details
    {
        auto hex = [](const uint8_t* d, size_t n) {
            std::string s; s.reserve(n*2);
            for (size_t i=0;i<n;i++) { char buf[3]; snprintf(buf,3,"%02x",d[i]); s+=buf; }
            return s;
        };
        printf("[SIGHASH-DEBUG] input=%zu version=%u tx_type=0x%02x\n",
               input_index, tx.version, tx.tx_type);
        printf("[SIGHASH-DEBUG] prev_txid=%s prev_idx=%u\n",
               hex(tx.inputs[input_index].prev_txid.data(),32).c_str(),
               tx.inputs[input_index].prev_index);
        printf("[SIGHASH-DEBUG] spent.amount=%lld spent.type=0x%02x\n",
               (long long)spent.amount, spent.type);
        printf("[SIGHASH-DEBUG] hash_prevouts=%s\n", hex(hp.data(),32).c_str());
        printf("[SIGHASH-DEBUG] hash_outputs=%s\n", hex(ho.data(),32).c_str());
        printf("[SIGHASH-DEBUG] genesis=%s\n", hex(genesis_hash.data(),32).c_str());
        printf("[SIGHASH-DEBUG] SIGHASH=%s\n", hex(result.data(),32).c_str());
    }

    return result;
}

// =============================================================================
// IsLowS — pure byte comparison, no library needed
// =============================================================================

bool IsLowS(const Sig64& sig) {
    // s = sig[32..63], big-endian
    for (int i = 0; i < 32; ++i) {
        if (sig[32 + i] < SECP256K1_HALF_ORDER[i]) return true;
        if (sig[32 + i] > SECP256K1_HALF_ORDER[i]) return false;
    }
    return true;  // equal to half_order → still low-S
}

// =============================================================================
// EnforceLowS — libsecp256k1 normalize
// =============================================================================

bool EnforceLowS(Sig64& sig) {
    if (IsLowS(sig)) return false;  // already low-S, no change needed

    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) return false;

    secp256k1_ecdsa_signature sigobj;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sigobj, sig.data())) {
        return false;
    }

    // Normalize: if s > n/2, set s = n - s
    secp256k1_ecdsa_signature_normalize(ctx, &sigobj, &sigobj);

    // Serialize back to compact
    secp256k1_ecdsa_signature_serialize_compact(ctx, sig.data(), &sigobj);

    return true;  // negation was performed
}

// =============================================================================
// Internal: validate r and s ranges (E4, E5)
// =============================================================================

static bool ValidateRSRange(const Sig64& sig, std::string* err) {
    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) {
        if (err) *err = "ValidateRSRange: secp256k1 context not available";
        return false;
    }

    // Check all-zero signature
    bool all_zero_r = true, all_zero_s = true;
    for (int i = 0; i < 32; ++i) {
        if (sig[i] != 0) all_zero_r = false;
        if (sig[32 + i] != 0) all_zero_s = false;
    }
    if (all_zero_r) {
        if (err) *err = "ValidateRSRange: r is zero (E4)";
        return false;
    }
    if (all_zero_s) {
        if (err) *err = "ValidateRSRange: s is zero (E5)";
        return false;
    }

    // parse_compact validates r,s ∈ [1, n-1]
    secp256k1_ecdsa_signature sigobj;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sigobj, sig.data())) {
        if (err) *err = "ValidateRSRange: r or s out of valid range (E4/E5)";
        return false;
    }

    // LOW-S check
    if (!IsLowS(sig)) {
        if (err) *err = "ValidateRSRange: s > curve_order/2 (LOW-S violation, E5)";
        return false;
    }

    return true;
}

// =============================================================================
// SignSighash — libsecp256k1
// =============================================================================

bool SignSighash(
    const PrivKey& privkey,
    const Hash256& sighash,
    Sig64& out_sig,
    std::string* err)
{
    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) {
        if (err) *err = "SignSighash: secp256k1 context not available";
        return false;
    }

    // Validate private key range [1, n-1]
    if (!secp256k1_ec_seckey_verify(ctx, privkey.data())) {
        if (err) *err = "SignSighash: invalid private key";
        return false;
    }

    // Sign
    secp256k1_ecdsa_signature sigobj;
    if (!secp256k1_ecdsa_sign(ctx, &sigobj, sighash.data(), privkey.data(),
                              nullptr, nullptr)) {
        if (err) *err = "SignSighash: secp256k1_ecdsa_sign failed";
        return false;
    }

    // Enforce LOW-S (libsecp256k1 may already produce low-S, but enforce explicitly)
    secp256k1_ecdsa_signature_normalize(ctx, &sigobj, &sigobj);

    // Serialize to compact 64-byte format (r[32] || s[32])
    secp256k1_ecdsa_signature_serialize_compact(ctx, out_sig.data(), &sigobj);

    // Double-check LOW-S (belt and suspenders)
    if (!IsLowS(out_sig)) {
        if (err) *err = "SignSighash: LOW-S enforcement failed after normalize";
        return false;
    }

    return true;
}

// =============================================================================
// VerifySighash — libsecp256k1
// =============================================================================

bool VerifySighash(
    const PubKey& pubkey,
    const Hash256& sighash,
    const Sig64& sig,
    std::string* err)
{
    // Check all-zero signature
    bool all_zero = true;
    for (int i = 0; i < 64; ++i) {
        if (sig[i] != 0) { all_zero = false; break; }
    }
    if (all_zero) {
        if (err) *err = "VerifySighash: signature is all zeros (E3)";
        return false;
    }

    // Validate r/s ranges + LOW-S
    if (!ValidateRSRange(sig, err)) return false;

    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) {
        if (err) *err = "VerifySighash: secp256k1 context not available";
        return false;
    }

    // Parse public key (compressed, 33 bytes)
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &pk, pubkey.data(), 33)) {
        if (err) *err = "VerifySighash: invalid public key (E1)";
        return false;
    }

    // Parse compact signature
    secp256k1_ecdsa_signature sigobj;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sigobj, sig.data())) {
        if (err) *err = "VerifySighash: failed to parse signature";
        return false;
    }

    // Verify
    if (!secp256k1_ecdsa_verify(ctx, &sigobj, sighash.data(), &pk)) {
        // DEBUG: dump all inputs on E6 failure
        {
            auto hex = [](const uint8_t* d, size_t n) {
                std::string s; s.reserve(n*2);
                for (size_t i=0;i<n;i++) { char buf[3]; snprintf(buf,3,"%02x",d[i]); s+=buf; }
                return s;
            };
            printf("[NODE-VERIFY-E6] ECDSA verification FAILED\n");
            printf("[NODE-VERIFY-E6] sighash=%s\n", hex(sighash.data(),32).c_str());
            printf("[NODE-VERIFY-E6] pubkey=%s\n", hex(pubkey.data(),33).c_str());
            printf("[NODE-VERIFY-E6] signature=%s\n", hex(sig.data(),64).c_str());
        }
        if (err) *err = "VerifySighash: ECDSA verification failed (E6)";
        return false;
    }

    return true;
}

// =============================================================================
// GenerateKeyPair — libsecp256k1 + OpenSSL RAND_bytes
// =============================================================================

bool GenerateKeyPair(PrivKey& out_privkey, PubKey& out_pubkey, std::string* err) {
    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) {
        if (err) *err = "GenerateKeyPair: secp256k1 context not available";
        return false;
    }

    // Generate random private key (retry until valid)
    for (int attempt = 0; attempt < 100; ++attempt) {
        if (RAND_bytes(out_privkey.data(), 32) != 1) {
            if (err) *err = "GenerateKeyPair: RAND_bytes failed";
            return false;
        }

        // Verify key is in valid range [1, n-1]
        if (secp256k1_ec_seckey_verify(ctx, out_privkey.data())) {
            // Derive public key
            secp256k1_pubkey pk;
            if (!secp256k1_ec_pubkey_create(ctx, &pk, out_privkey.data())) {
                if (err) *err = "GenerateKeyPair: secp256k1_ec_pubkey_create failed";
                return false;
            }

            // Serialize compressed (33 bytes)
            size_t pub_len = 33;
            if (!secp256k1_ec_pubkey_serialize(ctx, out_pubkey.data(), &pub_len,
                                               &pk, SECP256K1_EC_COMPRESSED)) {
                if (err) *err = "GenerateKeyPair: pubkey serialization failed";
                return false;
            }
            if (pub_len != 33) {
                if (err) *err = "GenerateKeyPair: compressed pubkey not 33 bytes";
                return false;
            }

            return true;
        }
    }

    if (err) *err = "GenerateKeyPair: failed to generate valid key after 100 attempts";
    return false;
}

// =============================================================================
// DerivePublicKey — libsecp256k1
// =============================================================================

bool DerivePublicKey(const PrivKey& privkey, PubKey& out_pubkey, std::string* err) {
    secp256k1_context* ctx = GetSecp256k1Ctx();
    if (!ctx) {
        if (err) *err = "DerivePublicKey: secp256k1 context not available";
        return false;
    }

    // Validate private key range [1, n-1]
    if (!secp256k1_ec_seckey_verify(ctx, privkey.data())) {
        if (err) *err = "DerivePublicKey: invalid private key (zero or >= curve order)";
        return false;
    }

    // Derive pub = priv * G
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_create(ctx, &pk, privkey.data())) {
        if (err) *err = "DerivePublicKey: secp256k1_ec_pubkey_create failed";
        return false;
    }

    // Serialize compressed (33 bytes)
    size_t pub_len = 33;
    if (!secp256k1_ec_pubkey_serialize(ctx, out_pubkey.data(), &pub_len,
                                       &pk, SECP256K1_EC_COMPRESSED)) {
        if (err) *err = "DerivePublicKey: pubkey serialization failed";
        return false;
    }
    if (pub_len != 33) {
        if (err) *err = "DerivePublicKey: compressed pubkey not 33 bytes";
        return false;
    }

    // Validate prefix (02 or 03)
    if (out_pubkey[0] != 0x02 && out_pubkey[0] != 0x03) {
        if (err) *err = "DerivePublicKey: invalid compressed pubkey prefix";
        return false;
    }

    return true;
}

// =============================================================================
// ComputePubKeyHash — RIPEMD160(SHA256(pubkey))  [OpenSSL, not deprecated]
// =============================================================================

PubKeyHash ComputePubKeyHash(const PubKey& pubkey) {
    Hash256 sha{};
    SHA256(pubkey.data(), pubkey.size(), sha.data());

    PubKeyHash pkh{};
    RIPEMD160(sha.data(), sha.size(), pkh.data());

    return pkh;
}

// =============================================================================
// Internal: validate all outputs have payload <= 255 (Design v1.2a R13)
// =============================================================================

static bool ValidateOutputsForSighash(const Transaction& tx, std::string* err) {
    for (size_t i = 0; i < tx.outputs.size(); ++i) {
        if (tx.outputs[i].payload.size() > 255) {
            if (err) *err = "payload too large (>255 bytes) in output[" + std::to_string(i) + "]";
            return false;
        }
    }
    return true;
}

// =============================================================================
// SignTransactionInput (high-level)
// =============================================================================

bool SignTransactionInput(
    Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash,
    const PrivKey& privkey,
    std::string* err)
{
    if (input_index >= tx.inputs.size()) {
        if (err) *err = "SignTransactionInput: input_index out of range";
        return false;
    }

    if (!ValidateOutputsForSighash(tx, err)) return false;

    PubKey pubkey{};
    if (!DerivePublicKey(privkey, pubkey, err)) return false;

    Hash256 sighash = ComputeSighash(tx, input_index, spent, genesis_hash);

    Sig64 sig{};
    if (!SignSighash(privkey, sighash, sig, err)) return false;

    std::memcpy(tx.inputs[input_index].signature.data(), sig.data(), 64);
    std::memcpy(tx.inputs[input_index].pubkey.data(), pubkey.data(), 33);

    return true;
}

// =============================================================================
// VerifyTransactionInput (high-level)
// =============================================================================

bool VerifyTransactionInput(
    const Transaction& tx,
    size_t input_index,
    const SpentOutput& spent,
    const Hash256& genesis_hash,
    const PubKeyHash& expected_pkh,
    std::string* err)
{
    if (input_index >= tx.inputs.size()) {
        if (err) *err = "VerifyTransactionInput: input_index out of range";
        return false;
    }

    if (!ValidateOutputsForSighash(tx, err)) return false;

    const auto& txin = tx.inputs[input_index];

    PubKey pubkey{};
    std::memcpy(pubkey.data(), txin.pubkey.data(), 33);
    PubKeyHash actual_pkh = ComputePubKeyHash(pubkey);

    if (actual_pkh != expected_pkh) {
        if (err) *err = "VerifyTransactionInput: pubkey hash mismatch (S2)";
        return false;
    }

    // DEBUG: show what the node passes to ComputeSighash
    {
        auto hex = [](const uint8_t* d, size_t n) {
            std::string s; s.reserve(n*2);
            for (size_t i=0;i<n;i++) { char buf[3]; snprintf(buf,3,"%02x",d[i]); s+=buf; }
            return s;
        };
        printf("[NODE-VERIFY] VerifyTransactionInput input=%zu\n", input_index);
        printf("[NODE-VERIFY] spent.amount=%lld spent.type=0x%02x\n",
               (long long)spent.amount, spent.type);
        printf("[NODE-VERIFY] expected_pkh=%s\n", hex(expected_pkh.data(),20).c_str());
        printf("[NODE-VERIFY] genesis=%s\n", hex(genesis_hash.data(),32).c_str());
        printf("[NODE-VERIFY] tx.version=%u tx.tx_type=0x%02x inputs=%zu outputs=%zu\n",
               tx.version, tx.tx_type, tx.inputs.size(), tx.outputs.size());
        printf("[NODE-VERIFY] prev_txid=%s prev_idx=%u\n",
               hex(txin.prev_txid.data(),32).c_str(), txin.prev_index);
        printf("[NODE-VERIFY] pubkey=%s\n", hex(txin.pubkey.data(),33).c_str());
    }

    Hash256 sighash = ComputeSighash(tx, input_index, spent, genesis_hash);

    Sig64 sig{};
    std::memcpy(sig.data(), txin.signature.data(), 64);

    return VerifySighash(pubkey, sighash, sig, err);
}

} // namespace sost
