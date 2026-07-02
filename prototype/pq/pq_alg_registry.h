// SOST Post-Quantum Migration V2 — algorithm-ID registry (REFERENCE ONLY)
//
// THIS FILE IS NOT COMPILED. It is not listed in CMakeLists.txt (sources are
// enumerated explicitly, not globbed) and is not included by any consensus
// unit. It exists so reviewers can see the concrete constants proposed in
// docs/PQ_TX_FORMAT_PROPOSAL.md. It defines NO behaviour, wires NO validation,
// and sets NO activation height. Mainnet is byte-identical.
//
// Author: NeoB.
#pragma once
#include <cstdint>
#include <cstddef>

namespace sost::pq_proto {

// Sentinel: PQ spend types are OFF. Same convention as
// atomic_swap_htlc_active_at() / POPC_V15_ACTIVATION_HEIGHT — a height of
// INT64_MAX means "never active", so a hypothetical validator built against
// this registry rejects every PQ tx and replays mainnet identically.
inline constexpr int64_t PQ_ACTIVATION_HEIGHT = INT64_MAX;  // DO NOT SET on mainnet

// 1-byte algorithm identifier carried in the versioned witness (tx version 2).
enum class AlgId : uint8_t {
    LEGACY_ECDSA_SECP256K1 = 0x00,  // today's 64/33 fixed layout (canonical)
    PQ_ML_DSA_44           = 0x01,  // FIPS 204, NIST L2
    PQ_ML_DSA_65           = 0x02,  // FIPS 204, NIST L3
    HYBRID_ECDSA_ML_DSA_44 = 0x10,  // BOTH ECDSA and ML-DSA-44 must verify
    HYBRID_ECDSA_ML_DSA_65 = 0x11,  // BOTH ECDSA and ML-DSA-65 must verify
    // Any other value: deterministically REJECTED by consensus (no "ignore").
};

struct AlgSizes { size_t sig_len; size_t pk_len; };

// Exact FIPS sizes (bytes). Enforced as exact equalities (no ranges) to remove
// malleability and bound DoS. ECDSA half = 64/33 (include/sost/transaction.h:72-73).
inline constexpr AlgSizes ECDSA_SIZES     { 64,   33   };
inline constexpr AlgSizes ML_DSA_44_SIZES { 2420, 1312 };  // FIPS 204
inline constexpr AlgSizes ML_DSA_65_SIZES { 3309, 1952 };  // FIPS 204

// A hybrid witness carries both, each length-prefixed; both signatures must
// validate over the same domain-separated sighash (conjunctive, never OR).

} // namespace sost::pq_proto
