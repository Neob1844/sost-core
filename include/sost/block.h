#pragma once
// =============================================================================
// SOST — Phase 5: Block Header
//
// V1 — Block Header (96 bytes, pre-V11 Phase 2):
//   version         : uint32_t  LE (4)   — protocol version (1 for v1)
//   prev_block_hash : Hash256       (32)  — SHA256² of previous block header
//   merkle_root     : Hash256       (32)  — merkle root of transaction IDs
//   timestamp       : int64_t   LE (8)   — Unix epoch seconds
//   bits_q          : uint32_t  LE (4)   — SOSTCompact Q16.16 difficulty target
//   nonce           : uint64_t  LE (8)   — ConvergenceX search nonce
//   height          : int64_t   LE (8)   — explicit block height
//                                ─────
//                                 96 bytes
//
// V2 — Block Header (193 bytes, V11 Phase 2 = SbPoW signature-bound PoW):
//   ... 96 v1 bytes above ...
//   miner_pubkey    : (33)                — secp256k1 compressed pubkey
//   miner_signature : (64)                — BIP-340 Schnorr over sig_message
//                                ─────
//                                193 bytes
//
// Block hash = SHA256(SHA256(serialized_header))
//   v1 hash: SHA256² of 96 bytes  (UNCHANGED from pre-V11 logic)
//   v2 hash: SHA256² of 193 bytes (includes pubkey + signature)
//
// IMPORTANT (SbPoW): the Schnorr signature signs the ConvergenceX `commit`,
// NOT the block_id. block_id of a v2 header includes the signature inside
// the hashed bytes — signing block_id would be circular. See sig_message
// definition in docs/V11_PHASE2_DESIGN.md §1.4.
//
// Key differences from Bitcoin (80-byte header):
//   - timestamp:  int64 (future-proof, 2038-safe)
//   - bits_q:     SOSTCompact Q16.16 (cASERT primary hardness)
//   - nonce:      uint64 (ConvergenceX needs larger search space)
//   - height:     explicit in header (simplifies SPV, checkpoint validation)
//
// Genesis block: prev_block_hash = 0x00*32, height = 0, version = 1
// =============================================================================

#include <sost/transaction.h>
#include <sost/merkle.h>
#include <array>
#include <cstdint>

namespace sost {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Default protocol version for new blocks at pre-Phase 2 heights.
inline constexpr uint32_t BLOCK_HEADER_VERSION    = 1;
inline constexpr uint32_t BLOCK_HEADER_VERSION_V1 = 1;
inline constexpr uint32_t BLOCK_HEADER_VERSION_V2 = 2;

// Serialized sizes. BLOCK_HEADER_SIZE is the v1 size for backward compat
// with existing callers (tests/test_merkle_block.cpp uses Serialize() which
// returns a fixed std::array<Byte, BLOCK_HEADER_SIZE>).
inline constexpr size_t   BLOCK_HEADER_SIZE       = 96;
inline constexpr size_t   BLOCK_HEADER_SIZE_V1    = 96;
inline constexpr size_t   BLOCK_HEADER_SIZE_V2    = 193;

// SbPoW v2 extension fields.
inline constexpr size_t   SBPOW_PUBKEY_SIZE       = 33;   // secp256k1 compressed
inline constexpr size_t   SBPOW_SIGNATURE_SIZE    = 64;   // BIP-340 Schnorr
inline constexpr size_t   SBPOW_HEADER_EXT_SIZE   =
    SBPOW_PUBKEY_SIZE + SBPOW_SIGNATURE_SIZE;             // 97 bytes

// ---------------------------------------------------------------------------
// BlockHeader
// ---------------------------------------------------------------------------

struct BlockHeader {
    uint32_t version{BLOCK_HEADER_VERSION};
    Hash256  prev_block_hash{};       // 0x00*32 for genesis
    Hash256  merkle_root{};
    int64_t  timestamp{0};            // Unix seconds
    uint32_t bits_q{0};               // SOSTCompact Q16.16 target
    uint64_t nonce{0};                // ConvergenceX nonce
    int64_t  height{0};               // explicit block height

    // V11 Phase 2 — SbPoW v2 extension (used iff version == 2).
    // For v1 headers these are zero-filled and ignored by serialization.
    std::array<uint8_t, SBPOW_PUBKEY_SIZE>     miner_pubkey{};
    std::array<uint8_t, SBPOW_SIGNATURE_SIZE>  miner_signature{};

    // -----------------------------------------------------------------------
    // Serialization (for hashing and wire protocol)
    // -----------------------------------------------------------------------

    /// Append the wire-format serialization of this header to `out`.
    /// Version-aware:
    ///   version == 1 → writes 96 bytes (legacy v1 layout).
    ///   version == 2 → writes 193 bytes (96 v1 bytes + 97-byte SbPoW ext).
    /// Any other version is a programming error and the call is a no-op
    /// (the standalone Serialize* helpers will then surface the error).
    void SerializeTo(std::vector<Byte>& out) const;

    /// V1-only convenience returning the fixed 96-byte array.
    /// Aborts if version != 1 — kept for backward compat with existing
    /// callers that use a v1 header. New code should prefer SerializeBytes().
    std::array<Byte, BLOCK_HEADER_SIZE> Serialize() const;

    /// Version-aware general-purpose byte serializer.
    /// Returns 96 bytes for v1 and 193 bytes for v2; empty vector for an
    /// unknown version (the v2 tests assert this rejection).
    std::vector<Byte> SerializeBytes() const;

    /// Streaming deserialize from `data` starting at `offset`.
    /// Reads the version field first, then 96 or 193 bytes accordingly.
    /// Used by Block::DeserializeFrom which expects more bytes after the
    /// header (tx_count + transactions). Returns false on:
    ///   - insufficient bytes for version field,
    ///   - unknown version,
    ///   - insufficient bytes for the chosen version's body.
    static bool DeserializeFrom(
        const std::vector<Byte>& data,
        size_t& offset,
        BlockHeader& out,
        std::string* err = nullptr);

    /// Strict standalone deserialize: `buffer.size()` MUST equal exactly
    /// 96 (and version field must be 1) or exactly 193 (and version
    /// must be 2). Any size or version mismatch fails.
    /// Used by tests that hold a single-header buffer.
    static bool DeserializeStandalone(
        const std::vector<Byte>& buffer,
        BlockHeader& out,
        std::string* err = nullptr);

    // -----------------------------------------------------------------------
    // Block hash
    // -----------------------------------------------------------------------

    /// Compute SHA256(SHA256(serialized_header)).
    /// V1 hashes 96 bytes; v2 hashes 193 bytes (signature included).
    /// IMPORTANT: SbPoW signature signs the ConvergenceX commit, NOT the
    /// block_id, because block_id of a v2 header already includes the
    /// signature inside the hashed bytes — signing block_id would be
    /// circular. See docs/V11_PHASE2_DESIGN.md §1.4.
    Hash256 ComputeBlockHash() const;

    /// Hex string of block hash.
    std::string ComputeBlockHashHex() const;

    // -----------------------------------------------------------------------
    // Comparison
    // -----------------------------------------------------------------------

    bool operator==(const BlockHeader& o) const;
    bool operator!=(const BlockHeader& o) const { return !(*this == o); }
};

// ---------------------------------------------------------------------------
// Block (header + transactions)
// ---------------------------------------------------------------------------

struct Block {
    BlockHeader header;
    std::vector<Transaction> txs;  // txs[0] = coinbase

    /// Compute merkle root from txs and store in header.merkle_root.
    /// Returns false if txid computation fails.
    bool ComputeAndSetMerkleRoot(std::string* err = nullptr);

    /// Verify that header.merkle_root matches the actual txs.
    bool VerifyMerkleRoot(std::string* err = nullptr) const;

    /// Serialize the full block (header + tx_count + transactions).
    bool SerializeTo(std::vector<Byte>& out, std::string* err = nullptr) const;

    /// Deserialize a full block from buffer.
    static bool DeserializeFrom(
        const std::vector<Byte>& data,
        size_t& offset,
        Block& out,
        std::string* err = nullptr);

    /// Total serialized size (header + compact_size + txs).
    size_t EstimateSize() const;
};

// ---------------------------------------------------------------------------
// Genesis block helper
// ---------------------------------------------------------------------------

/// Create the genesis block header with given parameters.
/// Caller must set nonce after mining.
BlockHeader MakeGenesisHeader(
    const Hash256& merkle_root,
    int64_t timestamp,
    uint32_t bits_q);

/// Bridge: extract the 72-byte PoW header_core from a BlockHeader.
/// Layout: prev_hash(32) || merkle_root(32) || ts_u32(4 LE) || bits_q(4 LE)
/// Used by ConvergenceX mining/verification layer.
void BlockHeaderToCore72(const BlockHeader& hdr, uint8_t out[72]);

} // namespace sost
