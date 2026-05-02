// sbpow.h — V11 Phase 2 component C: Signature-bound Proof of Work
//
// Spec: docs/V11_SPEC.md §3 + docs/V11_PHASE2_DESIGN.md §1
// Status (C3 — miner integration):
//   IMPLEMENTED:  build_sbpow_message, derive_compressed_pubkey_from_privkey,
//                 sign_sbpow_commitment, verify_sbpow_signature,
//                 derive_pkh_from_pubkey, secure_memzero.
//   STILL STUB:   derive_seed_v11, validate (consensus validator — C4 territory).
//
// IMPORTANT (no circularity):
//   The Schnorr signature signs the SbPoW *message* derived from the
//   ConvergenceX `commit` (and the surrounding header context); it does
//   NOT sign the block_id. block_id of a v2 header includes the signature
//   inside the hashed bytes, so signing block_id would be circular. See
//   docs/V11_PHASE2_DESIGN.md §1.4 / §1.5 for the full rationale and the
//   exact message layout.
//
// Phase 2 is gated behind G3.1 (verification), G3.2 (simulation),
// G3.3 (testnet) and G3.4 (adversarial) before any production height
// is set. With V11_PHASE2_HEIGHT = INT64_MAX, none of these functions
// are reached on real chain heights — only by C3 unit tests.
#pragma once

#include "sost/types.h"
#include "sost/tx_signer.h"   // PrivKey, PubKey, PubKeyHash
#include <array>
#include <cstdint>
#include <vector>

namespace sost::sbpow {

// Wire-format type aliases (also used by BlockHeader v2 in include/sost/block.h).
using MinerPrivkey   = std::array<uint8_t, 32>;
using MinerPubkey    = std::array<uint8_t, 33>;   // secp256k1 compressed
using MinerSignature = std::array<uint8_t, 64>;   // BIP-340 Schnorr

// Header v2 extension fields appended to the legacy 96-byte header at
// heights >= V11_PHASE2_HEIGHT. Total growth: 97 bytes.
struct HeaderV2Ext {
    MinerPubkey    miner_pubkey{};
    MinerSignature miner_signature{};
};

// Domain-separation tag for the signed message. Treated as raw bytes,
// not a C string — the trailing NUL is NOT included.
inline constexpr char    SBPOW_DOMAIN_TAG[]   = "SOST/POW-SIG/v11";
inline constexpr size_t  SBPOW_DOMAIN_TAG_LEN = sizeof(SBPOW_DOMAIN_TAG) - 1;

// ===========================================================================
// Message construction
// ===========================================================================

// Build the SbPoW signing message:
//
//   sbpow_message = SHA256(
//       SBPOW_DOMAIN_TAG ||
//       prev_hash       (32 B) ||
//       height          ( 8 B, LE) ||
//       commit          (32 B) ||
//       nonce           ( 4 B, LE) ||
//       extra_nonce     ( 4 B, LE) ||
//       miner_pubkey    (33 B)
//   )
//
// Notes for implementers:
//   - The message binds the PoW commit AND its surrounding context
//     (prev_hash, height, nonce, extra_nonce, pubkey) so a signature is
//     non-replayable across blocks, heights, or pubkeys.
//   - This is the message we Schnorr-sign. NOT the block_id. The block_id
//     of a v2 header includes the signature in its hashed bytes; signing
//     the block_id would be circular.
//
// Cross-platform determinism: all integer fields are written little-endian
// via the sost::serialize helpers. Result is bit-identical on x86 / ARM.
Bytes32 build_sbpow_message(
    const Bytes32&      prev_hash,
    int64_t             height,
    const Bytes32&      commit,
    uint32_t            nonce,
    uint32_t            extra_nonce,
    const MinerPubkey&  miner_pubkey);

// ===========================================================================
// Key derivation
// ===========================================================================

// Derive the 33-byte compressed secp256k1 pubkey from a 32-byte privkey.
// Returns false if `privkey` is zero or out-of-range. Uses the existing
// libsecp256k1 context (DerivePublicKey in tx_signer); the wrapper here
// gives sbpow callers a stable namespace + the MinerPubkey type.
bool derive_compressed_pubkey_from_privkey(
    const MinerPrivkey& privkey,
    MinerPubkey&        out_pubkey);

// Derive the address PubKeyHash (RIPEMD160(SHA256(pubkey))) from a 33-byte
// compressed pubkey. Pure helper that reuses tx_signer::ComputePubKeyHash.
PubKeyHash derive_pkh_from_pubkey(const MinerPubkey& pubkey);

// ===========================================================================
// Schnorr signing / verification (BIP-340)
// ===========================================================================

// Sign the SbPoW message under a 32-byte privkey using BIP-340 Schnorr.
// Uses a separate libsecp256k1 context (NOT the tx-signer one) so SbPoW
// changes never touch the transaction-signing path.
//
// Returns false if:
//   - privkey is invalid (zero / out-of-range),
//   - libsecp256k1 was not built with the schnorrsig module (in that
//     case the build itself should have failed, but the runtime check
//     stays as defence in depth).
//
// Schnorr signing in libsecp256k1 is deterministic by default (RFC 6979
// nonce derivation): same (privkey, msg) → bit-identical signature on
// any platform.
bool sign_sbpow_commitment(
    const MinerPrivkey&    privkey,
    const Bytes32&         message,
    MinerSignature&        out_signature);

// Verify a Schnorr signature against a message and a 33-byte compressed
// pubkey. Returns true iff the signature is well-formed AND verifies.
//
// Strictly speaking, validator-side verification is C4 work. We expose
// this helper now so the C3 sign tests can do a sign+verify roundtrip
// (the strongest evidence the signing path is correct).
bool verify_sbpow_signature(
    const MinerPubkey&     pubkey,
    const Bytes32&         message,
    const MinerSignature&  signature);

// ===========================================================================
// Memory hygiene
// ===========================================================================

// Best-effort secure zero of `len` bytes at `ptr`. Used to wipe in-memory
// privkey copies on shutdown. Backed by OPENSSL_cleanse (already linked
// for SHA256), which is implemented to resist dead-store elimination.
void secure_memzero(void* ptr, size_t len);

// ===========================================================================
// Miner-key selection (CLI flag resolver — testable without a live miner)
// ===========================================================================

// `Wallet` is forward-declared here to keep this header light. The full
// definition (and hence find_key_by_label) is needed only by the .cpp.
} // namespace sost::sbpow
namespace sost { class Wallet; }
namespace sost::sbpow {

struct MinerKeyResolution {
    enum class Status {
        // Pre-Phase 2 legacy path: caller provided neither --wallet nor
        // --mining-key-label. The miner falls back to the existing
        // --address-only flow. No signing key is loaded.
        OK_PRE_PHASE2_LEGACY,

        // Wallet + label resolved successfully to a concrete WalletKey.
        // The caller can sign SbPoW messages with it.
        OK_SIGNING_KEY,

        // Resolution failed. See `error` for a human-readable reason.
        ERROR,
    };

    Status      status{Status::ERROR};
    std::string error;

    // Populated iff status == OK_SIGNING_KEY:
    PubKey      pubkey{};
    PubKeyHash  pkh{};
    std::string address;          // "sost1..."
    std::string label;             // selected label
};

// Resolve which signing key the miner should use, given the CLI flags.
//
// Inputs:
//   wallet              — pre-loaded Wallet object (may be empty/zero keys
//                         when the user does not pass --wallet).
//   mining_key_label    — value of --mining-key-label (may be empty).
//   explicit_address    — value of --address (may be empty).
//   phase2_required     — true if mining at a height >= V11_PHASE2_HEIGHT
//                         (i.e. SbPoW signing is mandatory). The caller
//                         computes this from the chain tip.
//
// Decision matrix:
//   label empty AND address empty :
//       phase2_required ? ERROR("Phase 2 requires --wallet + --mining-key-label")
//                       : OK_PRE_PHASE2_LEGACY
//
//   label set                     :
//       wallet has no key with that label  → ERROR
//       --address also set AND mismatches  → ERROR
//       otherwise                          → OK_SIGNING_KEY
//
//   label empty AND address set   :
//       phase2_required ? ERROR("Phase 2 requires --mining-key-label")
//                       : OK_PRE_PHASE2_LEGACY
MinerKeyResolution resolve_miner_key(
    const ::sost::Wallet& wallet,
    const std::string&    mining_key_label,
    const std::string&    explicit_address,
    bool                  phase2_required);

// ===========================================================================
// C4 territory — still aborting stubs (do NOT call from C3 code paths)
// ===========================================================================

// PoW seed binding (`seed_v11` with miner_pubkey mixed in).
// PHASE 2 — NOT IMPLEMENTED in C3.
Bytes32 derive_seed_v11(
    const uint8_t* header_core, size_t header_core_len,
    const Bytes32& block_key,
    uint32_t nonce, uint32_t extra_nonce,
    const MinerPubkey& miner_pubkey);

// Consensus validator entry point (C4).
// PHASE 2 — NOT IMPLEMENTED in C3.
struct ValidationContext {
    int64_t              height;
    Bytes32              commit;
    Bytes32              expected_seed;
    Bytes32              provided_seed;
    std::vector<uint8_t> miner_subsidy_address;
    std::vector<uint8_t> miner_pubkey_address;
};

bool validate(const HeaderV2Ext& ext, const ValidationContext& ctx);

} // namespace sost::sbpow
