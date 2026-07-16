// SOST Post-Quantum Migration V3 — algorithm-ID registry (REFERENCE ONLY)
//
// THIS FILE IS NOT COMPILED INTO THE MAINNET NODE OR MINER.
// It is not listed in CMakeLists.txt (sources are enumerated explicitly, never
// globbed) and is not #included by any consensus, wallet, mempool, or block
// translation unit. It defines NO behaviour, wires NO validation, registers NO
// spend type, and sets NO activation height. The mainnet build is byte-identical
// with or without this file present.
//
// It exists so reviewers can read the concrete constants proposed in
// docs/PQ_TX_FORMAT_V3.md as compilable C++ rather than prose.
//
// V3 supersedes the V2 registry (prototype/pq/pq_alg_registry.h on branch
// draft/pq-migration-v2 / PR #37). V3 REASSIGNS the 1-byte ids (see the enum
// note below). Because PQ_ACTIVATION_HEIGHT == INT64_MAX in both iterations, no
// value here is used by consensus, so the reassignment causes no protocol
// conflict. All ids are PROVISIONAL until a future, separately-audited proposal.
//
// Author: NeoB.
#pragma once
#include <cstdint>
#include <cstddef>

namespace sost::pq_proto {

// ---------------------------------------------------------------------------
// Activation sentinel. Mirrors the established SOST convention used by
// POPC_V15_ACTIVATION_HEIGHT and atomic_swap_htlc_active_at(): a height of
// INT64_MAX means "never active", so a hypothetical validator built against
// this registry rejects every PQ transaction and replays mainnet identically.
// DO NOT set a real height here. Any real height is a consensus change and must
// come from a separate, reviewed, audited, announced proposal — not this PR.
// ---------------------------------------------------------------------------
inline constexpr int64_t PQ_ACTIVATION_HEIGHT = INT64_MAX;  // never active

// ---------------------------------------------------------------------------
// 1-byte algorithm identifier carried in the versioned witness (proposed tx
// version 2; today's mainnet tx version is 1 — include/sost/transaction.h:109).
//
//   V3 id map (PROVISIONAL — supersedes V2):
//     0x00 LEGACY_ECDSA_SECP256K1   today's 64/33 fixed layout (canonical)
//     0x01 PQ_ML_DSA_44             FIPS 204, NIST security level 2
//     0x02 HYBRID_ECDSA_ML_DSA_44   BOTH ECDSA AND ML-DSA-44 must verify (AND)
//     0x03 ML_DSA_65_RESERVED       FIPS 204, NIST L3 — reserved, not defined
//     0x04 ML_DSA_87_RESERVED       FIPS 204, NIST L5 — reserved, not defined
//     0x10 SLH_DSA_RESERVED         FIPS 205 hash-based backup — reserved
//     0xFF INVALID                  sentinel; never a valid witness
//
// Any value not explicitly ACTIVE is deterministically REJECTED by a validator
// (there is no "unknown id => ignore" path). RESERVED ids are parsed only far
// enough to reject them cleanly; they carry no semantics yet.
// ---------------------------------------------------------------------------
enum class AlgId : uint8_t {
    LEGACY_ECDSA_SECP256K1 = 0x00,
    PQ_ML_DSA_44           = 0x01,
    HYBRID_ECDSA_ML_DSA_44 = 0x02,
    ML_DSA_65_RESERVED     = 0x03,
    ML_DSA_87_RESERVED     = 0x04,
    SLH_DSA_RESERVED       = 0x10,
    INVALID                = 0xFF,
};

// ---------------------------------------------------------------------------
// Exact component sizes (bytes). Enforced as EXACT equalities (never ranges)
// to remove length malleability and to bound DoS. ECDSA half is the current
// mainnet layout (include/sost/transaction.h:72-73). ML-DSA sizes are the
// published FIPS 204 parameter sets — do not alter without a FIPS citation.
// ---------------------------------------------------------------------------
struct AlgSizes {
    size_t sig_len;   // signature length in bytes
    size_t pk_len;    // public-key length in bytes
};

inline constexpr AlgSizes ECDSA_SIZES     { 64,   33   };  // secp256k1 compact / compressed
inline constexpr AlgSizes ML_DSA_44_SIZES { 2420, 1312 };  // FIPS 204, level 2
inline constexpr AlgSizes ML_DSA_65_SIZES { 3309, 1952 };  // FIPS 204, level 3 (reserved)
inline constexpr AlgSizes ML_DSA_87_SIZES { 4627, 2592 };  // FIPS 204, level 5 (reserved)

// A HYBRID (0x02) witness carries BOTH an ECDSA half and an ML-DSA-44 half,
// each length-prefixed; BOTH signatures must validate over the SAME
// domain-separated sighash (conjunctive AND — never OR). See ADR-002.
inline constexpr AlgSizes HYBRID_44_ECDSA_HALF = ECDSA_SIZES;
inline constexpr AlgSizes HYBRID_44_MLDSA_HALF = ML_DSA_44_SIZES;

// ---------------------------------------------------------------------------
// Domain-separation tags. Every alg_id signs over a sighash that is bound to
// BOTH the SOST tx sighash AND a per-scheme domain tag, so a signature made for
// one scheme/context can never be replayed as another (algorithm-confusion and
// cross-protocol replay resistance). PROVISIONAL tag strings.
// ---------------------------------------------------------------------------
inline constexpr const char* DOMAIN_TAG_LEGACY  = "SOST/pq-v3/ecdsa-secp256k1";
inline constexpr const char* DOMAIN_TAG_ML_DSA  = "SOST/pq-v3/ml-dsa-44";
inline constexpr const char* DOMAIN_TAG_HYBRID  = "SOST/pq-v3/hybrid-ecdsa+ml-dsa-44";

// Witness envelope version this registry targets (proposed). Mainnet tx version
// stays 1; a PQ witness would ride a NEW tx version so old clients reject it by
// version check rather than mis-parsing it.
inline constexpr uint32_t PQ_WITNESS_TX_VERSION = 2;  // PROVISIONAL

// Convenience: is this id one that a (future) validator would treat as ACTIVE,
// versus RESERVED/INVALID. Pure predicate, no side effects, no consensus effect.
inline constexpr bool is_active_algid(AlgId id) {
    return id == AlgId::LEGACY_ECDSA_SECP256K1
        || id == AlgId::PQ_ML_DSA_44
        || id == AlgId::HYBRID_ECDSA_ML_DSA_44;
}

} // namespace sost::pq_proto
