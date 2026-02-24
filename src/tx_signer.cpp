// =============================================================================
// tx_signer.cpp — SOST Sighash + ECDSA (consensus-critical)
// =============================================================================
//
// Implements BIP143-simplified sighash and ECDSA secp256k1 signing/verification
// as specified in Design Document v1.2a, Sections 6 and 13.
//
// Sighash preimage (146 bytes fixed):
//   version(4) || tx_type(1) || hashPrevouts(32) || prev_txid[i](32) ||
//   prev_index[i](4) || spent_amount[i](8) || spent_type[i](1) ||
//   hashOutputs(32) || genesis_hash(32)
//
// All fields use Section 5 canonical encoding (little-endian integers).
// sighash = SHA256(SHA256(preimage))
//
// ECDSA: secp256k1, compressed keys, compact 64-byte (r||s big-endian), LOW-S.
//
// Hardening v2: payload bounds, r/s range validation, input_index bounds,
//               OpenSSL return checks.
//
// =============================================================================

#include "sost/tx_signer.h"

#include <openssl/ec.h>
#include <openssl/ecdsa.h>
#include <openssl/bn.h>
#include <openssl/obj_mac.h>
#include <openssl/sha.h>
#include <openssl/ripemd.h>
#include <openssl/rand.h>
#include <openssl/evp.h>
#include <cstring>
#include <memory>

namespace sost {

// =============================================================================
// OpenSSL RAII helpers
// =============================================================================

struct BN_CTX_Deleter { void operator()(BN_CTX* p) { if (p) BN_CTX_free(p); } };
struct BN_Deleter     { void operator()(BIGNUM* p)  { if (p) BN_free(p); } };
struct EC_KEY_Deleter { void operator()(EC_KEY* p)  { if (p) EC_KEY_free(p); } };
struct ECDSA_SIG_Deleter { void operator()(ECDSA_SIG* p) { if (p) ECDSA_SIG_free(p); } };

using BN_CTX_ptr     = std::unique_ptr<BN_CTX, BN_CTX_Deleter>;
using BN_ptr         = std::unique_ptr<BIGNUM, BN_Deleter>;
using EC_KEY_ptr     = std::unique_ptr<EC_KEY, EC_KEY_Deleter>;
using ECDSA_SIG_ptr  = std::unique_ptr<ECDSA_SIG, ECDSA_SIG_Deleter>;

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
// Internal: get secp256k1 curve order as BIGNUM
// =============================================================================

static bool GetCurveOrder(BIGNUM* order, std::string* err) {
    EC_KEY_ptr key(EC_KEY_new_by_curve_name(NID_secp256k1));
    if (!key) {
        if (err) *err = "GetCurveOrder: EC_KEY_new_by_curve_name failed";
        return false;
    }
    const EC_GROUP* group = EC_KEY_get0_group(key.get());
    if (!group) {
        if (err) *err = "GetCurveOrder: EC_KEY_get0_group failed";
        return false;
    }
    BN_CTX_ptr ctx(BN_CTX_new());
    if (!ctx) {
        if (err) *err = "GetCurveOrder: BN_CTX_new failed";
        return false;
    }
    if (EC_GROUP_get_order(group, order, ctx.get()) != 1) {
        if (err) *err = "GetCurveOrder: EC_GROUP_get_order failed";
        return false;
    }
    return true;
}

// =============================================================================
// ComputeHashPrevouts
// =============================================================================

Hash256 ComputeHashPrevouts(const Transaction& tx) {
    // SHA256(SHA256( prev_txid[0] || prev_index[0] || prev_txid[1] || ... ))
    // All fields use Section 5 canonical encoding (prev_index as u32 LE)
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
    // SHA256(SHA256( amount[0]||type[0]||pkh[0]||plen[0]||payload[0] || ... ))
    // All fields use Section 5 canonical encoding (amount as i64 LE, etc.)
    //
    // HARDENING: payload.size() is validated <= 255 before casting to uint8.
    // If any output violates this, the function returns a zeroed hash
    // (which will cause sighash mismatch → signature failure → safe rejection).
    std::vector<Byte> buf;
    buf.reserve(tx.outputs.size() * 30);

    for (const auto& out : tx.outputs) {
        // FIX #1: Validate payload fits in uint8 (Design v1.2a R13)
        if (out.payload.size() > 255) {
            // Return deterministic "poison" hash — will cause verify to fail
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
    // FIX #3: Bounds check input_index
    if (input_index >= tx.inputs.size()) {
        // Return zeroed hash (will cause signature mismatch → safe failure)
        Hash256 poison{};
        return poison;
    }

    // Preimage (146 bytes fixed):
    //   version(4) || tx_type(1) || hashPrevouts(32) || prev_txid[i](32) ||
    //   prev_index[i](4) || spent_amount[i](8) || spent_type[i](1) ||
    //   hashOutputs(32) || genesis_hash(32)

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

    return DoubleSHA256(preimage);
}

// =============================================================================
// IsLowS / EnforceLowS
// =============================================================================

bool IsLowS(const Sig64& sig) {
    // s = sig[32..63], big-endian
    for (int i = 0; i < 32; ++i) {
        if (sig[32 + i] < SECP256K1_HALF_ORDER[i]) return true;
        if (sig[32 + i] > SECP256K1_HALF_ORDER[i]) return false;
    }
    return true;  // Equal is still valid
}

bool EnforceLowS(Sig64& sig) {
    if (IsLowS(sig)) return false;

    BN_ptr s_bn(BN_bin2bn(sig.data() + 32, 32, nullptr));
    if (!s_bn) return false;

    BN_ptr order(BN_new());
    if (!order) return false;

    // FIX #4: Check return of GetCurveOrder
    if (!GetCurveOrder(order.get(), nullptr)) return false;

    // s = order - s
    if (BN_sub(s_bn.get(), order.get(), s_bn.get()) != 1) return false;

    // Write back to sig[32..63], zero-padded big-endian
    std::memset(sig.data() + 32, 0, 32);
    int s_len = BN_num_bytes(s_bn.get());
    if (s_len > 32) return false;
    if (BN_bn2bin(s_bn.get(), sig.data() + 32 + (32 - s_len)) != s_len) return false;

    return true;
}

// =============================================================================
// Internal: validate r and s ranges (E4, E5)
// =============================================================================

static bool ValidateRSRange(const Sig64& sig, std::string* err) {
    BN_ptr r_bn(BN_bin2bn(sig.data(), 32, nullptr));
    BN_ptr s_bn(BN_bin2bn(sig.data() + 32, 32, nullptr));
    if (!r_bn || !s_bn) {
        if (err) *err = "ValidateRSRange: failed to parse r/s";
        return false;
    }

    // E3: neither r nor s can be zero
    if (BN_is_zero(r_bn.get())) {
        if (err) *err = "ValidateRSRange: r is zero (E4)";
        return false;
    }
    if (BN_is_zero(s_bn.get())) {
        if (err) *err = "ValidateRSRange: s is zero (E5)";
        return false;
    }

    // FIX #2: Validate r < curve_order (E4: r in [1, n-1])
    BN_ptr order(BN_new());
    if (!order) {
        if (err) *err = "ValidateRSRange: BN_new failed";
        return false;
    }
    if (!GetCurveOrder(order.get(), err)) return false;

    if (BN_cmp(r_bn.get(), order.get()) >= 0) {
        if (err) *err = "ValidateRSRange: r >= curve_order (E4)";
        return false;
    }

    // E5: s <= curve_order / 2 (LOW-S)
    if (!IsLowS(sig)) {
        if (err) *err = "ValidateRSRange: s > curve_order/2 (LOW-S violation, E5)";
        return false;
    }

    return true;
}

// =============================================================================
// SignSighash
// =============================================================================

bool SignSighash(
    const PrivKey& privkey,
    const Hash256& sighash,
    Sig64& out_sig,
    std::string* err)
{
    EC_KEY_ptr key(EC_KEY_new_by_curve_name(NID_secp256k1));
    if (!key) {
        if (err) *err = "SignSighash: failed to create EC_KEY";
        return false;
    }

    BN_ptr priv_bn(BN_bin2bn(privkey.data(), 32, nullptr));
    if (!priv_bn) {
        if (err) *err = "SignSighash: failed to create BIGNUM from privkey";
        return false;
    }

    if (EC_KEY_set_private_key(key.get(), priv_bn.get()) != 1) {
        if (err) *err = "SignSighash: failed to set private key";
        return false;
    }

    // Derive and set public key (required by OpenSSL for signing)
    const EC_GROUP* group = EC_KEY_get0_group(key.get());
    if (!group) {
        if (err) *err = "SignSighash: EC_KEY_get0_group failed";
        return false;
    }

    EC_POINT* pub_point = EC_POINT_new(group);
    if (!pub_point) {
        if (err) *err = "SignSighash: failed to create EC_POINT";
        return false;
    }

    BN_CTX_ptr ctx(BN_CTX_new());
    if (!ctx) {
        EC_POINT_free(pub_point);
        if (err) *err = "SignSighash: BN_CTX_new failed";
        return false;
    }

    if (EC_POINT_mul(group, pub_point, priv_bn.get(), nullptr, nullptr, ctx.get()) != 1) {
        EC_POINT_free(pub_point);
        if (err) *err = "SignSighash: failed to derive public key";
        return false;
    }

    // FIX #4: Check return of EC_KEY_set_public_key
    if (EC_KEY_set_public_key(key.get(), pub_point) != 1) {
        EC_POINT_free(pub_point);
        if (err) *err = "SignSighash: EC_KEY_set_public_key failed";
        return false;
    }
    EC_POINT_free(pub_point);

    // Sign
    ECDSA_SIG_ptr sig_obj(ECDSA_do_sign(sighash.data(), 32, key.get()));
    if (!sig_obj) {
        if (err) *err = "SignSighash: ECDSA_do_sign failed";
        return false;
    }

    // Extract r and s as big-endian 32 bytes each
    const BIGNUM* r_bn = nullptr;
    const BIGNUM* s_bn = nullptr;
    ECDSA_SIG_get0(sig_obj.get(), &r_bn, &s_bn);

    if (!r_bn || !s_bn) {
        if (err) *err = "SignSighash: ECDSA_SIG_get0 returned null";
        return false;
    }

    std::memset(out_sig.data(), 0, 64);

    int r_len = BN_num_bytes(r_bn);
    int s_len = BN_num_bytes(s_bn);
    if (r_len > 32 || s_len > 32) {
        if (err) *err = "SignSighash: r or s exceeds 32 bytes";
        return false;
    }
    BN_bn2bin(r_bn, out_sig.data() + (32 - r_len));
    BN_bn2bin(s_bn, out_sig.data() + 32 + (32 - s_len));

    // Enforce LOW-S (Design v1.2a Section 13 E5)
    if (!IsLowS(out_sig)) {
        if (!EnforceLowS(out_sig)) {
            if (err) *err = "SignSighash: failed to enforce LOW-S";
            return false;
        }
        if (!IsLowS(out_sig)) {
            if (err) *err = "SignSighash: LOW-S enforcement did not produce low-S";
            return false;
        }
    }

    return true;
}

// =============================================================================
// VerifySighash
// =============================================================================

bool VerifySighash(
    const PubKey& pubkey,
    const Hash256& sighash,
    const Sig64& sig,
    std::string* err)
{
    // E3: signature must not be all zeros
    bool all_zero = true;
    for (int i = 0; i < 64; ++i) {
        if (sig[i] != 0) { all_zero = false; break; }
    }
    if (all_zero) {
        if (err) *err = "VerifySighash: signature is all zeros (E3)";
        return false;
    }

    // FIX #2: Full r/s range validation (E4, E5)
    if (!ValidateRSRange(sig, err)) return false;

    // Create EC_KEY and set public key
    EC_KEY_ptr key(EC_KEY_new_by_curve_name(NID_secp256k1));
    if (!key) {
        if (err) *err = "VerifySighash: failed to create EC_KEY";
        return false;
    }

    // E1/E2: pubkey must be a valid compressed point (not infinity)
    const EC_GROUP* group = EC_KEY_get0_group(key.get());
    if (!group) {
        if (err) *err = "VerifySighash: EC_KEY_get0_group failed";
        return false;
    }

    EC_POINT* point = EC_POINT_new(group);
    if (!point) {
        if (err) *err = "VerifySighash: failed to create EC_POINT";
        return false;
    }

    if (EC_POINT_oct2point(group, point, pubkey.data(), 33, nullptr) != 1) {
        EC_POINT_free(point);
        if (err) *err = "VerifySighash: invalid public key point (E1)";
        return false;
    }
    if (EC_POINT_is_at_infinity(group, point)) {
        EC_POINT_free(point);
        if (err) *err = "VerifySighash: public key is point at infinity (E2)";
        return false;
    }

    // FIX #4: Check return of EC_KEY_set_public_key
    if (EC_KEY_set_public_key(key.get(), point) != 1) {
        EC_POINT_free(point);
        if (err) *err = "VerifySighash: EC_KEY_set_public_key failed";
        return false;
    }
    EC_POINT_free(point);

    // Build ECDSA_SIG from r, s
    ECDSA_SIG* sig_obj = ECDSA_SIG_new();
    if (!sig_obj) {
        if (err) *err = "VerifySighash: failed to create ECDSA_SIG";
        return false;
    }

    // FIX #4: Check BN_dup returns
    BN_ptr r_bn(BN_bin2bn(sig.data(), 32, nullptr));
    BN_ptr s_bn(BN_bin2bn(sig.data() + 32, 32, nullptr));
    BIGNUM* r_copy = BN_dup(r_bn.get());
    BIGNUM* s_copy = BN_dup(s_bn.get());
    if (!r_copy || !s_copy) {
        ECDSA_SIG_free(sig_obj);
        if (r_copy) BN_free(r_copy);
        if (s_copy) BN_free(s_copy);
        if (err) *err = "VerifySighash: BN_dup failed";
        return false;
    }

    if (ECDSA_SIG_set0(sig_obj, r_copy, s_copy) != 1) {
        ECDSA_SIG_free(sig_obj);
        // set0 takes ownership only on success; on failure we must free
        BN_free(r_copy);
        BN_free(s_copy);
        if (err) *err = "VerifySighash: failed to set r/s in ECDSA_SIG";
        return false;
    }

    // E6: ECDSA_verify
    int result = ECDSA_do_verify(sighash.data(), 32, sig_obj, key.get());
    ECDSA_SIG_free(sig_obj);

    if (result != 1) {
        if (err) *err = "VerifySighash: ECDSA verification failed (E6)";
        return false;
    }

    return true;
}

// =============================================================================
// GenerateKeyPair
// =============================================================================

bool GenerateKeyPair(PrivKey& out_privkey, PubKey& out_pubkey, std::string* err) {
    EC_KEY_ptr key(EC_KEY_new_by_curve_name(NID_secp256k1));
    if (!key) {
        if (err) *err = "GenerateKeyPair: failed to create EC_KEY";
        return false;
    }

    if (EC_KEY_generate_key(key.get()) != 1) {
        if (err) *err = "GenerateKeyPair: key generation failed";
        return false;
    }

    const BIGNUM* priv_bn = EC_KEY_get0_private_key(key.get());
    if (!priv_bn) {
        if (err) *err = "GenerateKeyPair: EC_KEY_get0_private_key returned null";
        return false;
    }

    std::memset(out_privkey.data(), 0, 32);
    int priv_len = BN_num_bytes(priv_bn);
    if (priv_len > 32) {
        if (err) *err = "GenerateKeyPair: private key exceeds 32 bytes";
        return false;
    }
    BN_bn2bin(priv_bn, out_privkey.data() + (32 - priv_len));

    EC_KEY_set_conv_form(key.get(), POINT_CONVERSION_COMPRESSED);
    const EC_POINT* pub_point = EC_KEY_get0_public_key(key.get());
    const EC_GROUP* group = EC_KEY_get0_group(key.get());

    if (!pub_point || !group) {
        if (err) *err = "GenerateKeyPair: failed to get public key/group";
        return false;
    }

    size_t pub_len = EC_POINT_point2oct(group, pub_point,
                                         POINT_CONVERSION_COMPRESSED,
                                         out_pubkey.data(), 33, nullptr);
    if (pub_len != 33) {
        if (err) *err = "GenerateKeyPair: compressed pubkey not 33 bytes";
        return false;
    }

    return true;
}

// =============================================================================
// DerivePublicKey
// =============================================================================

bool DerivePublicKey(const PrivKey& privkey, PubKey& out_pubkey, std::string* err) {
    EC_KEY_ptr key(EC_KEY_new_by_curve_name(NID_secp256k1));
    if (!key) {
        if (err) *err = "DerivePublicKey: failed to create EC_KEY";
        return false;
    }

    BN_ptr priv_bn(BN_bin2bn(privkey.data(), 32, nullptr));
    if (!priv_bn || EC_KEY_set_private_key(key.get(), priv_bn.get()) != 1) {
        if (err) *err = "DerivePublicKey: invalid private key";
        return false;
    }

    const EC_GROUP* group = EC_KEY_get0_group(key.get());
    if (!group) {
        if (err) *err = "DerivePublicKey: EC_KEY_get0_group failed";
        return false;
    }

    EC_POINT* pub_point = EC_POINT_new(group);
    if (!pub_point) {
        if (err) *err = "DerivePublicKey: EC_POINT_new failed";
        return false;
    }

    BN_CTX_ptr ctx(BN_CTX_new());
    if (!ctx) {
        EC_POINT_free(pub_point);
        if (err) *err = "DerivePublicKey: BN_CTX_new failed";
        return false;
    }

    if (EC_POINT_mul(group, pub_point, priv_bn.get(), nullptr, nullptr, ctx.get()) != 1) {
        EC_POINT_free(pub_point);
        if (err) *err = "DerivePublicKey: point multiplication failed";
        return false;
    }

    size_t len = EC_POINT_point2oct(group, pub_point,
                                     POINT_CONVERSION_COMPRESSED,
                                     out_pubkey.data(), 33, nullptr);
    EC_POINT_free(pub_point);

    if (len != 33) {
        if (err) *err = "DerivePublicKey: compressed key not 33 bytes";
        return false;
    }

    return true;
}

// =============================================================================
// ComputePubKeyHash — RIPEMD160(SHA256(pubkey))
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

    // Reject if any output has oversized payload (explicit, not poison-hash)
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

    // Reject if any output has oversized payload (explicit, not poison-hash)
    if (!ValidateOutputsForSighash(tx, err)) return false;

    const auto& txin = tx.inputs[input_index];

    PubKey pubkey{};
    std::memcpy(pubkey.data(), txin.pubkey.data(), 33);
    PubKeyHash actual_pkh = ComputePubKeyHash(pubkey);

    if (actual_pkh != expected_pkh) {
        if (err) *err = "VerifyTransactionInput: pubkey hash mismatch (S2)";
        return false;
    }

    Hash256 sighash = ComputeSighash(tx, input_index, spent, genesis_hash);

    Sig64 sig{};
    std::memcpy(sig.data(), txin.signature.data(), 64);

    return VerifySighash(pubkey, sighash, sig, err);
}

} // namespace sost
