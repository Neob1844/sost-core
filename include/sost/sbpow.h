// sbpow.h — V11 Phase 2 component C: Signature-bound Proof of Work
//
// Spec: docs/V11_SPEC.md §3
// Status: SKELETON — types declared, functions not implemented.
// Activation: V11_PHASE2_HEIGHT (TBD, see params.h once Phase 2 lands).
//
// Phase 2 is gated behind G3.1 (verification), G3.2 (simulation),
// G3.3 (testnet) and G3.4 (adversarial) before any production height
// is set. This header carries the public surface that the rest of the
// codebase will eventually consume; nothing here is wired into miner
// or validator yet.
#pragma once

#include "sost/types.h"
#include <array>
#include <cstdint>
#include <vector>

namespace sost::sbpow {

// 33-byte secp256k1 compressed pubkey carried in the v2 header.
using MinerPubkey = std::array<uint8_t, 33>;

// 64-byte BIP-340 Schnorr signature carried in the v2 header.
using MinerSignature = std::array<uint8_t, 64>;

// Header v2 extension fields appended to the legacy header at heights
// >= V11_PHASE2_HEIGHT. Total growth over the v1 header: 97 bytes.
struct HeaderV2Ext {
    MinerPubkey    miner_pubkey{};
    MinerSignature miner_signature{};
};

// Compute seed_v11 = sha256(MAGIC || "SEED2" || header_core || block_key
//                           || nonce || extra_nonce || miner_pubkey).
// Used in place of the pre-fork "SEED" tag once SbPoW is active.
//
// PHASE 2 — NOT IMPLEMENTED. Returns zero-filled Bytes32 for now.
Bytes32 derive_seed_v11(
    const uint8_t* header_core, size_t header_core_len,
    const Bytes32& block_key,
    uint32_t nonce, uint32_t extra_nonce,
    const MinerPubkey& miner_pubkey);

// sig_message = sha256("SOST/POW-SIG/v11" || commit || height).
// PHASE 2 — NOT IMPLEMENTED.
Bytes32 build_sig_message(const Bytes32& commit, int64_t height);

// BIP-340 Schnorr sign / verify. Signing is miner-side, verify is
// part of consensus. Both delegate to libsecp256k1 in the final cut.
// PHASE 2 — NOT IMPLEMENTED.
bool sign(const std::array<uint8_t, 32>& privkey,
          const Bytes32& sig_message,
          MinerSignature& out);

bool verify(const MinerPubkey& pubkey,
            const Bytes32& sig_message,
            const MinerSignature& signature);

// Validation entry point. Returns true iff:
//   1. miner_pubkey is a well-formed compressed secp256k1 point,
//   2. miner_signature is valid for sig_message under miner_pubkey,
//   3. the seed used to derive `commit` was seed_v11 with this pubkey,
//   4. the coinbase miner-subsidy output pays the address derived from
//      miner_pubkey.
//
// The caller supplies `commit`, `height`, and a callback that returns
// the address paid by the miner-subsidy coinbase output. Keeping the
// coinbase lookup as a callback avoids dragging the full block type
// into this header.
//
// PHASE 2 — NOT IMPLEMENTED.
struct ValidationContext {
    int64_t   height;
    Bytes32   commit;
    Bytes32   expected_seed;          // seed_v11 recomputed by validator
    Bytes32   provided_seed;          // seed actually used to derive commit
    std::vector<uint8_t> miner_subsidy_address;  // address paid by coinbase
    std::vector<uint8_t> miner_pubkey_address;   // address derived from pubkey
};

bool validate(const HeaderV2Ext& ext, const ValidationContext& ctx);

} // namespace sost::sbpow
