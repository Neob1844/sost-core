// sbpow.cpp — V11 Phase 2 component C: Signature-bound Proof of Work
//
// Spec: docs/V11_SPEC.md §3 + docs/V11_PHASE2_DESIGN.md §1
// Status (C4.1): real BIP-340 Schnorr signing/verification + message
// construction + privkey→pubkey derivation + secure_memzero +
// height-gated validate_sbpow_for_block. PoW seed binding
// (derive_seed_v11) remains an aborting stub — it is a follow-up.
//
// Schnorr context is private to this translation unit and never shared
// with the existing tx-signer ECDSA context (src/tx_signer.cpp) — by
// design, so changes here cannot regress transaction signing.
//
// Build-time gating: the Schnorr-dependent code below is wrapped in
// #ifdef SOST_HAVE_SCHNORRSIG. When the macro is undefined (default
// build with -DSOST_ENABLE_PHASE2_SBPOW=OFF):
//   - sign_sbpow_commitment / verify_sbpow_signature return false.
//   - is_well_formed_compressed_pubkey degrades to a prefix-only check
//     (still rejects 0x00 / 0x04 / arbitrary bytes; no curve test).
//   - validate_sbpow_for_block stays correct: pre-activation it never
//     reaches Schnorr verify (legacy v1 headers); the version check
//     still fires and rejects premature v2 blocks. Post-activation
//     (height >= V11_PHASE2_HEIGHT = 10000) it MUST be built with the
//     full BIP-340 path; OFF builds are TEST-ONLY and not deployable.
//   - Schnorr-only test binaries are NOT built (CMake gates them).
// When SOST_HAVE_SCHNORRSIG is defined the full BIP-340 path is live.
#include "sost/sbpow.h"

#include "sost/crypto.h"      // sha256()
#include "sost/serialize.h"   // append, append_u32_le, append_u64_le
#include "sost/tx_signer.h"   // DerivePublicKey, ComputePubKeyHash
#include "sost/wallet.h"      // Wallet, find_key_by_label

#include <openssl/crypto.h>   // OPENSSL_cleanse
#include <openssl/rand.h>     // RAND_bytes
#include <secp256k1.h>

#ifdef SOST_HAVE_SCHNORRSIG
#  include <secp256k1_schnorrsig.h>
#endif

#include <cstdio>
#include <cstdlib>
#include <mutex>

namespace sost::sbpow {

// ============================================================================
// Schnorr context — separate from the tx-signer ECDSA context
// ============================================================================

#ifdef SOST_HAVE_SCHNORRSIG

namespace {

std::once_flag g_schnorr_ctx_once;
secp256k1_context* g_schnorr_ctx = nullptr;

void init_schnorr_ctx() {
    g_schnorr_ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    if (!g_schnorr_ctx) {
        std::fprintf(stderr,
            "FATAL sbpow: secp256k1_context_create failed\n");
        std::abort();
    }
    // Optional but recommended: randomize the context to harden against
    // side-channel attacks during signing. Use OPENSSL randomness.
    // The randomize call CAN fail (e.g., if the system randomization
    // primitive is unavailable); falling back to an unrandomised context
    // is a known acceptable failure mode — Schnorr signing remains
    // correct, only side-channel resistance is reduced.
    unsigned char rnd[32];
    if (RAND_bytes(rnd, 32) == 1) {
        int rc = secp256k1_context_randomize(g_schnorr_ctx, rnd);
        (void)rc;  // explicit ignore — see comment above
        OPENSSL_cleanse(rnd, sizeof(rnd));
    }
}

secp256k1_context* GetSchnorrCtx() {
    std::call_once(g_schnorr_ctx_once, init_schnorr_ctx);
    return g_schnorr_ctx;
}

} // namespace

#endif  // SOST_HAVE_SCHNORRSIG

// ============================================================================
// Message construction
// ============================================================================
//
// CRITICAL: the SbPoW signature signs THIS message, NOT the block_id.
// The v2 block_id of a Phase-2 header includes the signature inside
// the hashed bytes (see BlockHeader::ComputeBlockHash for v2 in
// src/block.cpp). Signing the block_id would be circular: signature
// depends on block_id which depends on signature. This message ties
// the signature to the ConvergenceX commit and its surrounding header
// context, which IS hash-stable before the signature exists.
//
// Layout (binary concatenation, little-endian for integer fields):
//
//   "SOST/POW-SIG/v11"         16 B   (no NUL)
//   prev_hash                  32 B
//   height (i64 LE)             8 B
//   commit                     32 B
//   nonce (u32 LE)              4 B
//   extra_nonce (u32 LE)        4 B
//   miner_pubkey               33 B
//                          ─────
//                            129 B → SHA-256 → 32 B output
//
// ============================================================================

Bytes32 build_sbpow_message(
    const Bytes32&      prev_hash,
    int64_t             height,
    const Bytes32&      commit,
    uint32_t            nonce,
    uint32_t            extra_nonce,
    const MinerPubkey&  miner_pubkey)
{
    std::vector<uint8_t> buf;
    buf.reserve(SBPOW_DOMAIN_TAG_LEN + 32 + 8 + 32 + 4 + 4 + 33);

    // Domain tag — written verbatim, no trailing NUL.
    buf.insert(buf.end(),
               reinterpret_cast<const uint8_t*>(SBPOW_DOMAIN_TAG),
               reinterpret_cast<const uint8_t*>(SBPOW_DOMAIN_TAG) + SBPOW_DOMAIN_TAG_LEN);

    // prev_hash, height, commit, nonce, extra_nonce, miner_pubkey.
    append(buf, prev_hash);
    append_u64_le(buf, (uint64_t)height);
    append(buf, commit);
    append_u32_le(buf, nonce);
    append_u32_le(buf, extra_nonce);
    buf.insert(buf.end(), miner_pubkey.begin(), miner_pubkey.end());

    return sha256(buf);
}

// ============================================================================
// Key derivation
// ============================================================================

bool derive_compressed_pubkey_from_privkey(
    const MinerPrivkey& privkey,
    MinerPubkey&        out_pubkey)
{
    // Reuse the existing tx_signer DerivePublicKey path. Its context is
    // initialised separately, but DerivePublicKey only needs SECP256K1
    // arithmetic (no Schnorr-specific state), so calling it here is safe
    // and avoids duplicating the curve maths.
    PrivKey  pk{};
    PubKey   pub{};
    static_assert(std::tuple_size<PrivKey>::value == 32, "PrivKey size");
    static_assert(std::tuple_size<PubKey>::value  == 33, "PubKey size");
    static_assert(std::tuple_size<MinerPrivkey>::value == 32, "MinerPrivkey size");
    static_assert(std::tuple_size<MinerPubkey>::value  == 33, "MinerPubkey size");

    std::memcpy(pk.data(), privkey.data(), 32);
    bool ok = DerivePublicKey(pk, pub, /*err=*/nullptr);
    secure_memzero(pk.data(), pk.size());

    if (!ok) {
        out_pubkey.fill(0);
        return false;
    }
    std::memcpy(out_pubkey.data(), pub.data(), 33);
    return true;
}

PubKeyHash derive_pkh_from_pubkey(const MinerPubkey& pubkey) {
    PubKey pub{};
    std::memcpy(pub.data(), pubkey.data(), 33);
    return ComputePubKeyHash(pub);
}

// ============================================================================
// Schnorr signing / verification (BIP-340)
// ============================================================================

bool sign_sbpow_commitment(
    const MinerPrivkey&    privkey,
    const Bytes32&         message,
    MinerSignature&        out_signature)
{
#ifdef SOST_HAVE_SCHNORRSIG
    secp256k1_context* ctx = GetSchnorrCtx();

    // Build the keypair from privkey. Failure modes: privkey == 0 or >= n.
    secp256k1_keypair keypair;
    if (!secp256k1_keypair_create(ctx, &keypair, privkey.data())) {
        out_signature.fill(0);
        return false;
    }

    // BIP-340 Schnorr sign. With aux_rand32 == nullptr libsecp256k1 uses
    // RFC-6979-style deterministic nonce derivation, so the signature is
    // bit-identical for the same (privkey, message) on every platform.
    // The trade-off: a leak of the same message under different aux_rand
    // does not weaken security; determinism eases cross-node consensus
    // testing.
    //
    // We use `secp256k1_schnorrsig_sign` (the original 32-byte-message
    // entry point). Newer libsecp256k1 versions also expose
    // `_schnorrsig_sign32` with identical semantics. Sticking to the
    // older name maximises compatibility with the libsecp256k1 versions
    // currently shipped in mainstream Linux distros (Debian 12 = 0.1).
    int rc = secp256k1_schnorrsig_sign(
        ctx,
        out_signature.data(),
        message.data(),
        &keypair,
        /*aux_rand32=*/nullptr);

    // Wipe the keypair-derived material before returning.
    OPENSSL_cleanse(&keypair, sizeof(keypair));

    if (rc != 1) {
        out_signature.fill(0);
        return false;
    }
    return true;
#else
    (void)privkey; (void)message;
    // Build was configured without SOST_HAVE_SCHNORRSIG. Production
    // builds MUST enable SOST_ENABLE_PHASE2_SBPOW before block 10000.
    // Pre-activation (height < 10000) miners never reach this path
    // because the v1 header is selected by version-gating logic; this
    // assertion only protects against a misbuilt deployment that still
    // produces v2 headers.
    out_signature.fill(0);
    return false;
#endif
}

bool verify_sbpow_signature(
    const MinerPubkey&     pubkey,
    const Bytes32&         message,
    const MinerSignature&  signature)
{
#ifdef SOST_HAVE_SCHNORRSIG
    secp256k1_context* ctx = GetSchnorrCtx();

    // BIP-340 uses 32-byte x-only pubkeys. Convert from the 33-byte
    // compressed pubkey by parsing then x-only-extracting.
    secp256k1_pubkey full_pk;
    if (!secp256k1_ec_pubkey_parse(ctx, &full_pk, pubkey.data(), pubkey.size())) {
        return false;
    }
    secp256k1_xonly_pubkey xonly_pk;
    int parity_unused = 0;
    if (!secp256k1_xonly_pubkey_from_pubkey(ctx, &xonly_pk, &parity_unused, &full_pk)) {
        return false;
    }

    int rc = secp256k1_schnorrsig_verify(
        ctx,
        signature.data(),
        message.data(),
        message.size(),
        &xonly_pk);
    return rc == 1;
#else
    (void)pubkey; (void)message; (void)signature;
    // Without SOST_HAVE_SCHNORRSIG, verify always returns false.
    // validate_sbpow_for_block guarantees this is only called on the
    // Phase 2 active path. Production builds MUST be compiled with
    // SOST_ENABLE_PHASE2_SBPOW=ON before block 10000 (V11_PHASE2_HEIGHT).
    return false;
#endif
}

// ============================================================================
// Memory hygiene
// ============================================================================

void secure_memzero(void* ptr, size_t len) {
    if (ptr == nullptr || len == 0) return;
    OPENSSL_cleanse(ptr, len);
}

// ============================================================================
// Miner-key selection helper
// ============================================================================

MinerKeyResolution resolve_miner_key(
    const ::sost::Wallet& wallet,
    const std::string&    mining_key_label,
    const std::string&    explicit_address,
    bool                  phase2_required)
{
    MinerKeyResolution out{};

    const bool have_label   = !mining_key_label.empty();
    const bool have_address = !explicit_address.empty();

    // Case 1: no wallet selector at all.
    //   Phase 2 → MUST have label/wallet → error.
    //   Pre-Phase 2 → legacy --address-only flow.
    if (!have_label) {
        if (phase2_required) {
            out.status = MinerKeyResolution::Status::ERROR;
            out.error  = have_address
                ? "V11 Phase 2 active: --mining-key-label is required "
                  "(--address alone is not enough — SbPoW needs the "
                  "signing privkey, which lives in your wallet)."
                : "V11 Phase 2 active: pass --wallet <path> and "
                  "--mining-key-label <label>.";
            return out;
        }
        out.status = MinerKeyResolution::Status::OK_PRE_PHASE2_LEGACY;
        return out;
    }

    // Case 2: label given. Look up in wallet.
    const ::sost::WalletKey* wk = wallet.find_key_by_label(mining_key_label);
    if (wk == nullptr) {
        out.status = MinerKeyResolution::Status::ERROR;
        out.error  = "wallet has no key with label '" + mining_key_label +
                     "' (check --wallet path and --mining-key-label).";
        return out;
    }

    // Case 3: --address also given → must match the address derived from
    // the selected key. This catches the foot-gun where a user passes an
    // address belonging to a different key.
    if (have_address && explicit_address != wk->address) {
        out.status = MinerKeyResolution::Status::ERROR;
        out.error  = "--address (" + explicit_address +
                     ") does not match the address derived from "
                     "--mining-key-label '" + mining_key_label +
                     "' (which is " + wk->address + ")";
        return out;
    }

    out.status   = MinerKeyResolution::Status::OK_SIGNING_KEY;
    out.pubkey   = wk->pubkey;
    out.pkh      = wk->pkh;
    out.address  = wk->address;
    out.label    = wk->label;
    return out;
}

// ============================================================================
// Consensus validator (C4) — height-gated SbPoW check
// ============================================================================

const char* to_string(ValidationResult r) {
    switch (r) {
        case ValidationResult::OK:                  return "OK";
        case ValidationResult::SBPOW_NOT_REQUIRED:  return "SBPOW_NOT_REQUIRED";
        case ValidationResult::VERSION_MISMATCH:    return "VERSION_MISMATCH";
        case ValidationResult::MALFORMED_PUBKEY:    return "MALFORMED_PUBKEY";
        case ValidationResult::SIGNATURE_INVALID:   return "SIGNATURE_INVALID";
        case ValidationResult::COINBASE_MISMATCH:   return "COINBASE_MISMATCH";
    }
    return "UNKNOWN";
}

bool is_well_formed_compressed_pubkey(const MinerPubkey& pubkey) {
    // BIP-340 / SEC1 prefix check first — cheap rejection.
    const uint8_t prefix = pubkey[0];
    if (prefix != 0x02 && prefix != 0x03) return false;

#ifdef SOST_HAVE_SCHNORRSIG
    // Curve membership check via libsecp256k1 (requires the Schnorr
    // context, which is only initialised when SOST_HAVE_SCHNORRSIG is
    // defined). This catches "valid prefix, off-curve x-coordinate"
    // attacks.
    secp256k1_context* ctx = GetSchnorrCtx();
    secp256k1_pubkey full;
    if (!secp256k1_ec_pubkey_parse(ctx, &full, pubkey.data(), pubkey.size())) {
        return false;
    }
#endif
    // Without SOST_HAVE_SCHNORRSIG, the curve-membership check is
    // skipped. The Phase 2 active path is unreachable in OFF builds,
    // so the degraded prefix-only check has no effect on production
    // chains compiled with SOST_ENABLE_PHASE2_SBPOW=ON. Adversarial
    // tests for off-curve points run only with -DSOST_ENABLE_PHASE2_SBPOW=ON.
    return true;
}

ValidationResult validate_sbpow_for_block(
    const ValidationInputs& in,
    std::string*            error_msg)
{
    auto set_err = [&](const std::string& s) {
        if (error_msg) *error_msg = s;
    };

    const bool phase2_active = (in.height >= in.phase2_height);

    // ---- Step 1 — version gate (always) ------------------------------------
    // Pre-Phase 2 must be v1; Phase 2 must be v2. Anything else is a hard
    // reject. Pre-activation (height < V11_PHASE2_HEIGHT = 10000) a
    // premature v2 block is rejected here even though the signature
    // path below is skipped on the legacy v1 branch.
    if (!phase2_active) {
        if (in.header_version != 1) {
            set_err("SbPoW: pre-Phase 2 height " +
                    std::to_string((long long)in.height) +
                    " requires header.version == 1, got " +
                    std::to_string((unsigned)in.header_version));
            return ValidationResult::VERSION_MISMATCH;
        }
        // Pre-Phase 2 short-circuit: NO signature/pubkey/coinbase checks.
        return ValidationResult::SBPOW_NOT_REQUIRED;
    }

    if (in.header_version != 2) {
        set_err("SbPoW: Phase 2 height " +
                std::to_string((long long)in.height) +
                " requires header.version == 2, got " +
                std::to_string((unsigned)in.header_version));
        return ValidationResult::VERSION_MISMATCH;
    }

    // ---- Step 2 — pubkey well-formedness ----------------------------------
    if (!is_well_formed_compressed_pubkey(in.miner_pubkey)) {
        char hexbuf[5];
        std::snprintf(hexbuf, sizeof(hexbuf), "0x%02x", (unsigned)in.miner_pubkey[0]);
        set_err("SbPoW: miner_pubkey is not a valid compressed secp256k1 point "
                "(prefix " + std::string(hexbuf) + ", or not on curve)");
        return ValidationResult::MALFORMED_PUBKEY;
    }

    // ---- Step 3 — signature ----------------------------------------------
    // Recompute the message ourselves; never trust a caller-supplied
    // message field. Binds prev_hash, height, commit, nonce, extra_nonce
    // and pubkey (see build_sbpow_message comment block above).
    const Bytes32 expected_msg = build_sbpow_message(
        in.prev_hash, in.height, in.commit,
        in.nonce, in.extra_nonce, in.miner_pubkey);

    if (!verify_sbpow_signature(in.miner_pubkey, expected_msg, in.miner_signature)) {
        set_err("SbPoW: BIP-340 Schnorr signature verification failed for "
                "the recomputed message at height " +
                std::to_string((long long)in.height));
        return ValidationResult::SIGNATURE_INVALID;
    }

    // ---- Step 4 — coinbase miner-output binding ---------------------------
    const PubKeyHash derived_pkh = derive_pkh_from_pubkey(in.miner_pubkey);
    if (derived_pkh != in.coinbase_miner_pkh) {
        set_err("SbPoW: coinbase miner-output pkh does not match "
                "PubKeyHash derived from miner_pubkey (derived = " +
                HexStr(derived_pkh.data(), derived_pkh.size()) +
                ", coinbase = " +
                HexStr(in.coinbase_miner_pkh.data(),
                       in.coinbase_miner_pkh.size()) + ")");
        return ValidationResult::COINBASE_MISMATCH;
    }

    return ValidationResult::OK;
}

// ============================================================================
// Still aborting — follow-up territory (NOT part of C4)
// ============================================================================

Bytes32 derive_seed_v11(
    const uint8_t* /*header_core*/, size_t /*header_core_len*/,
    const Bytes32& /*block_key*/,
    uint32_t /*nonce*/, uint32_t /*extra_nonce*/,
    const MinerPubkey& /*miner_pubkey*/)
{
    std::fprintf(stderr,
        "FATAL: sost::sbpow::derive_seed_v11 called before its follow-up "
        "implementation lands. PoW seed binding requires parallel changes "
        "inside src/pow/convergencex.cpp and is gated separately from C4.\n");
    std::abort();
}

} // namespace sost::sbpow
