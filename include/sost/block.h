#pragma once
// =============================================================================
// SOST — Phase 5: Block Header
//
// SOST Block Header (96 bytes):
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
// Block hash = SHA256(SHA256(header_bytes))
//
// Key differences from Bitcoin (80-byte header):
//   - timestamp:  int64 (future-proof, 2038-safe)
//   - bits_q:     SOSTCompact Q16.16 (fine-grained ASERT adjustment)
//   - nonce:      uint64 (ConvergenceX needs larger search space)
//   - height:     explicit in header (simplifies SPV, checkpoint validation)
//
// Genesis block: prev_block_hash = 0x00*32, height = 0
// =============================================================================

#include <sost/transaction.h>
#include <sost/merkle.h>

namespace sost {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

inline constexpr uint32_t BLOCK_HEADER_VERSION = 1;
inline constexpr size_t   BLOCK_HEADER_SIZE    = 96;  // bytes

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

    // -----------------------------------------------------------------------
    // Serialization (for hashing and wire protocol)
    // -----------------------------------------------------------------------

    /// Serialize header to exactly 96 bytes.
    void SerializeTo(std::vector<Byte>& out) const;

    /// Serialize header to a fixed 96-byte array.
    std::array<Byte, BLOCK_HEADER_SIZE> Serialize() const;

    /// Deserialize from buffer at given offset.
    /// Returns false if not enough bytes.
    static bool DeserializeFrom(
        const std::vector<Byte>& data,
        size_t& offset,
        BlockHeader& out,
        std::string* err = nullptr);

    // -----------------------------------------------------------------------
    // Block hash
    // -----------------------------------------------------------------------

    /// Compute SHA256(SHA256(serialized_header)).
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

} // namespace sost
