// SOST Post-Quantum Migration V3 — witness structs, canonical (de)serialization
// and a safe, deterministic parser. REFERENCE / PROTOTYPE ONLY.
//
// NOT COMPILED INTO THE MAINNET NODE OR MINER. Header-only, self-contained
// C++17 (no secp256k1 / no liboqs dependency) so it can be exercised by the
// standalone prototype tests in tests/pq_vectors/ without touching the
// production build. It defines NO consensus rule and activates nothing.
//
// The wire format below is a PROPOSAL (docs/PQ_TX_FORMAT_V3.md). It rides a NEW
// tx version (pq_proto::PQ_WITNESS_TX_VERSION = 2) so that today's mainnet
// clients — which only accept tx version 1 — reject it by version check rather
// than mis-parsing it. Nothing here changes the version-1 serialization used by
// src/transaction.cpp.
//
// Author: NeoB.
#pragma once
#include <cstdint>
#include <cstddef>
#include <vector>
#include <string>
#include "pq_alg_registry.h"

namespace sost::pq_proto {

using Byte = uint8_t;
using Bytes = std::vector<Byte>;

// ---------------------------------------------------------------------------
// Parse result codes. Every rejection is DETERMINISTIC and enumerated: a given
// byte string always maps to the same code on every node. There is no
// "unknown id => ignore" or "extra bytes => tolerate" path.
// ---------------------------------------------------------------------------
enum class PqParseCode {
    OK = 0,
    ERR_EMPTY,                 // no bytes at all
    ERR_UNKNOWN_ALGID,         // alg_id not in the active/reserved set
    ERR_RESERVED_ALGID,        // alg_id reserved (0x03/0x04/0x10) — not yet valid
    ERR_INVALID_ALGID,         // alg_id == 0xFF sentinel
    ERR_TRUNCATED,             // ran out of bytes mid-component
    ERR_BAD_LENGTH_PREFIX,     // length prefix not canonical / out of range
    ERR_WRONG_COMPONENT_LEN,   // component length != exact expected size for alg_id
    ERR_TRAILING_BYTES,        // extra bytes after a complete witness
    ERR_DUP_OR_MISORDERED,     // hybrid halves duplicated / out of order
};

inline const char* pq_parse_code_str(PqParseCode c) {
    switch (c) {
        case PqParseCode::OK:                    return "OK";
        case PqParseCode::ERR_EMPTY:             return "ERR_EMPTY";
        case PqParseCode::ERR_UNKNOWN_ALGID:     return "ERR_UNKNOWN_ALGID";
        case PqParseCode::ERR_RESERVED_ALGID:    return "ERR_RESERVED_ALGID";
        case PqParseCode::ERR_INVALID_ALGID:     return "ERR_INVALID_ALGID";
        case PqParseCode::ERR_TRUNCATED:         return "ERR_TRUNCATED";
        case PqParseCode::ERR_BAD_LENGTH_PREFIX: return "ERR_BAD_LENGTH_PREFIX";
        case PqParseCode::ERR_WRONG_COMPONENT_LEN: return "ERR_WRONG_COMPONENT_LEN";
        case PqParseCode::ERR_TRAILING_BYTES:    return "ERR_TRAILING_BYTES";
        case PqParseCode::ERR_DUP_OR_MISORDERED: return "ERR_DUP_OR_MISORDERED";
    }
    return "ERR_UNSPECIFIED";
}

// ---------------------------------------------------------------------------
// Parsed witness. Components are copied out verbatim; interpretation (actual
// signature verification) is a SEPARATE conceptual step (see pq_validate.h).
// ---------------------------------------------------------------------------
struct PqWitness {
    AlgId alg_id = AlgId::INVALID;
    // LEGACY / PQ single-scheme halves:
    Bytes sig;      // primary signature
    Bytes pubkey;   // primary public key
    // HYBRID second (ML-DSA) half — empty unless alg_id == HYBRID_ECDSA_ML_DSA_44:
    Bytes pq_sig;
    Bytes pq_pubkey;
};

// ---------------------------------------------------------------------------
// Canonical length prefix. To keep the prototype fully self-contained (no
// dependency on src/transaction.cpp's CompactSize), the prototype uses a FIXED
// 2-byte big-endian length prefix. Values above 0xFFFF are impossible here
// because the largest component (ML-DSA-87, reserved) is 4627 bytes. A fixed
// width removes the non-canonical-varint attack surface entirely: there is
// exactly one encoding of each length.
// ---------------------------------------------------------------------------
inline void put_len_be16(Bytes& out, size_t n) {
    out.push_back(static_cast<Byte>((n >> 8) & 0xFF));
    out.push_back(static_cast<Byte>(n & 0xFF));
}

// Returns false on truncation. Advances off by 2 on success.
inline bool get_len_be16(const Bytes& in, size_t& off, size_t& out_len) {
    if (off + 2 > in.size()) return false;
    out_len = (static_cast<size_t>(in[off]) << 8) | static_cast<size_t>(in[off + 1]);
    off += 2;
    return true;
}

// ---------------------------------------------------------------------------
// SERIALIZE — deterministic. Given a well-formed PqWitness, emit its canonical
// bytes. (Callers building invalid vectors do so by hand-editing the output.)
// ---------------------------------------------------------------------------
inline Bytes serialize_witness(const PqWitness& w) {
    Bytes out;
    out.push_back(static_cast<Byte>(w.alg_id));
    auto emit = [&](const Bytes& comp) {
        put_len_be16(out, comp.size());
        out.insert(out.end(), comp.begin(), comp.end());
    };
    switch (w.alg_id) {
        case AlgId::LEGACY_ECDSA_SECP256K1:
        case AlgId::PQ_ML_DSA_44:
            emit(w.sig);
            emit(w.pubkey);
            break;
        case AlgId::HYBRID_ECDSA_ML_DSA_44:
            emit(w.sig);        // ECDSA sig
            emit(w.pubkey);     // ECDSA pubkey
            emit(w.pq_sig);     // ML-DSA-44 sig
            emit(w.pq_pubkey);  // ML-DSA-44 pubkey
            break;
        default:
            // RESERVED / INVALID never serialize a body.
            break;
    }
    return out;
}

// ---------------------------------------------------------------------------
// Exact expected component sizes for a given (active) alg_id.
// ---------------------------------------------------------------------------
inline bool expected_sizes(AlgId id, AlgSizes& primary, bool& is_hybrid, AlgSizes& secondary) {
    is_hybrid = false;
    switch (id) {
        case AlgId::LEGACY_ECDSA_SECP256K1: primary = ECDSA_SIZES;     return true;
        case AlgId::PQ_ML_DSA_44:           primary = ML_DSA_44_SIZES; return true;
        case AlgId::HYBRID_ECDSA_ML_DSA_44:
            primary   = HYBRID_44_ECDSA_HALF;
            secondary = HYBRID_44_MLDSA_HALF;
            is_hybrid = true;
            return true;
        default: return false;  // reserved / invalid / unknown
    }
}

// ---------------------------------------------------------------------------
// SAFE PARSER — the core defensive routine. Rejects, deterministically:
//   - empty input
//   - unknown / reserved / invalid alg_id
//   - truncation at any component
//   - a length prefix that disagrees with the exact expected size (this also
//     catches duplicated / mis-ordered hybrid halves, since a swapped half
//     yields the wrong declared length for its position)
//   - any trailing bytes after a complete witness
// It never allocates based on an attacker-declared length before checking it
// against the fixed expected size, bounding memory use.
// ---------------------------------------------------------------------------
inline PqParseCode parse_witness(const Bytes& in, PqWitness& out) {
    out = PqWitness{};
    if (in.empty()) return PqParseCode::ERR_EMPTY;

    const Byte raw_id = in[0];
    // Classify the id explicitly. Reserved and invalid are distinct rejections.
    AlgId id = static_cast<AlgId>(raw_id);
    switch (id) {
        case AlgId::LEGACY_ECDSA_SECP256K1:
        case AlgId::PQ_ML_DSA_44:
        case AlgId::HYBRID_ECDSA_ML_DSA_44:
            break;  // active — continue
        case AlgId::ML_DSA_65_RESERVED:
        case AlgId::ML_DSA_87_RESERVED:
        case AlgId::SLH_DSA_RESERVED:
            return PqParseCode::ERR_RESERVED_ALGID;
        case AlgId::INVALID:
            return PqParseCode::ERR_INVALID_ALGID;
        default:
            return PqParseCode::ERR_UNKNOWN_ALGID;
    }

    AlgSizes primary{}, secondary{};
    bool is_hybrid = false;
    if (!expected_sizes(id, primary, is_hybrid, secondary)) {
        return PqParseCode::ERR_UNKNOWN_ALGID;  // defensive; unreachable given switch above
    }

    size_t off = 1;

    // Reads one component that MUST be exactly `want` bytes long.
    auto read_exact = [&](size_t want, Bytes& dst) -> PqParseCode {
        size_t declared = 0;
        if (!get_len_be16(in, off, declared)) return PqParseCode::ERR_TRUNCATED;
        if (declared != want) return PqParseCode::ERR_WRONG_COMPONENT_LEN;
        if (off + declared > in.size()) return PqParseCode::ERR_TRUNCATED;
        dst.assign(in.begin() + off, in.begin() + off + declared);
        off += declared;
        return PqParseCode::OK;
    };

    out.alg_id = id;
    PqParseCode rc;
    if ((rc = read_exact(primary.sig_len, out.sig))    != PqParseCode::OK) return rc;
    if ((rc = read_exact(primary.pk_len,  out.pubkey)) != PqParseCode::OK) return rc;
    if (is_hybrid) {
        if ((rc = read_exact(secondary.sig_len, out.pq_sig))    != PqParseCode::OK) return rc;
        if ((rc = read_exact(secondary.pk_len,  out.pq_pubkey)) != PqParseCode::OK) return rc;
    }

    // No trailing bytes tolerated — a witness must consume its input exactly.
    if (off != in.size()) return PqParseCode::ERR_TRAILING_BYTES;
    return PqParseCode::OK;
}

} // namespace sost::pq_proto
