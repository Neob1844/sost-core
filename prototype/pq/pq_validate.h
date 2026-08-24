// SOST Post-Quantum Migration V3 — CONCEPTUAL validation of a parsed witness.
// REFERENCE / PROTOTYPE ONLY. NOT COMPILED INTO THE MAINNET NODE OR MINER.
//
// This header shows how a (future, separately-audited) validator would combine
// the safe parser (pq_witness.h) with per-scheme signature verification and
// domain separation. It deliberately does NOT link secp256k1 or liboqs so it
// stays buildable anywhere; the actual cryptographic verify calls are marked
// with clearly-labelled stubs / hooks. It changes no consensus rule.
//
//   LEGACY  (0x00): verify ECDSA over the domain-separated sighash.
//   PQ      (0x01): verify ML-DSA-44 over the domain-separated sighash.
//   HYBRID  (0x02): verify BOTH (AND). Reject if EITHER fails. Never OR.
//
// Author: NeoB.
#pragma once
#include <cstdint>
#include <string>
#include <functional>
#include "pq_witness.h"

namespace sost::pq_proto {

// A 32-byte SOST sighash (as produced by the version-1 signer today,
// src/tx_signer.cpp). In the prototype it is just an opaque 32-byte blob.
using Sighash32 = std::array<Byte, 32>;

// ---------------------------------------------------------------------------
// Domain-separated message. Every scheme signs over
//     H( domain_tag || sighash )
// so a signature produced for one scheme/context can never be replayed as
// another (algorithm-confusion, downgrade and cross-context replay resistance).
// The prototype returns the concatenation for a caller-supplied hash; it does
// NOT itself hash (keeps the prototype hash-library-free).
// ---------------------------------------------------------------------------
inline Bytes domain_message(const char* domain_tag, const Sighash32& sighash) {
    Bytes m;
    const char* p = domain_tag;
    while (*p) m.push_back(static_cast<Byte>(*p++));
    m.push_back(0x00);  // explicit separator between tag and payload
    m.insert(m.end(), sighash.begin(), sighash.end());
    return m;
}

// ---------------------------------------------------------------------------
// Verifier hooks. In a real build these are backed by libsecp256k1 (ECDSA) and
// an ML-DSA implementation (liboqs / NIST reference) behind an abstract
// interface (ADR-004). In the prototype the caller injects them so tests can
// supply deterministic fakes. A hook returns true iff the signature is valid.
// ---------------------------------------------------------------------------
struct Verifiers {
    // ECDSA secp256k1, compact 64-byte, LOW-S enforced by the caller's hook.
    std::function<bool(const Bytes& sig, const Bytes& pk, const Bytes& msg)> ecdsa_verify;
    // ML-DSA-44 (FIPS 204).
    std::function<bool(const Bytes& sig, const Bytes& pk, const Bytes& msg)> ml_dsa_verify;
};

enum class PqVerifyCode {
    OK = 0,
    ERR_PARSE,             // witness did not parse (see PqParseCode)
    ERR_NO_VERIFIER,       // required hook not supplied
    ERR_ECDSA_FAIL,        // ECDSA signature invalid
    ERR_ML_DSA_FAIL,       // ML-DSA signature invalid
    ERR_UNSUPPORTED,       // active id with no verification path wired (should not happen)
};

// ---------------------------------------------------------------------------
// verify_parsed — conceptual. Assumes `w` already came from parse_witness()
// returning OK, so sizes/ids are structurally sound. Applies domain separation
// and the AND rule for hybrid.
// ---------------------------------------------------------------------------
inline PqVerifyCode verify_parsed(const PqWitness& w,
                                  const Sighash32& sighash,
                                  const Verifiers& v) {
    switch (w.alg_id) {
        case AlgId::LEGACY_ECDSA_SECP256K1: {
            if (!v.ecdsa_verify) return PqVerifyCode::ERR_NO_VERIFIER;
            const Bytes msg = domain_message(DOMAIN_TAG_LEGACY, sighash);
            return v.ecdsa_verify(w.sig, w.pubkey, msg)
                       ? PqVerifyCode::OK : PqVerifyCode::ERR_ECDSA_FAIL;
        }
        case AlgId::PQ_ML_DSA_44: {
            if (!v.ml_dsa_verify) return PqVerifyCode::ERR_NO_VERIFIER;
            const Bytes msg = domain_message(DOMAIN_TAG_ML_DSA, sighash);
            return v.ml_dsa_verify(w.sig, w.pubkey, msg)
                       ? PqVerifyCode::OK : PqVerifyCode::ERR_ML_DSA_FAIL;
        }
        case AlgId::HYBRID_ECDSA_ML_DSA_44: {
            if (!v.ecdsa_verify || !v.ml_dsa_verify) return PqVerifyCode::ERR_NO_VERIFIER;
            // AND semantics: BOTH must pass over the SAME hybrid-tagged sighash.
            const Bytes msg = domain_message(DOMAIN_TAG_HYBRID, sighash);
            if (!v.ecdsa_verify(w.sig, w.pubkey, msg))       return PqVerifyCode::ERR_ECDSA_FAIL;
            if (!v.ml_dsa_verify(w.pq_sig, w.pq_pubkey, msg)) return PqVerifyCode::ERR_ML_DSA_FAIL;
            return PqVerifyCode::OK;
        }
        default:
            return PqVerifyCode::ERR_UNSUPPORTED;
    }
}

// Convenience: parse + verify in one call.
inline PqVerifyCode parse_and_verify(const Bytes& wire,
                                     const Sighash32& sighash,
                                     const Verifiers& v,
                                     PqParseCode* parse_out = nullptr) {
    PqWitness w;
    PqParseCode pc = parse_witness(wire, w);
    if (parse_out) *parse_out = pc;
    if (pc != PqParseCode::OK) return PqVerifyCode::ERR_PARSE;
    return verify_parsed(w, sighash, v);
}

} // namespace sost::pq_proto
