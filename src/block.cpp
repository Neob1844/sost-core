// =============================================================================
// SOST — Phase 5: Block Header + Block Implementation
// =============================================================================

#include <sost/block.h>
#include <openssl/sha.h>
#include <cstring>

namespace sost {

// ---------------------------------------------------------------------------
// Little-endian helpers (local, for header serialization only)
// ---------------------------------------------------------------------------

static void WriteLE32(std::vector<Byte>& out, uint32_t v) {
    out.push_back((Byte)(v      ));
    out.push_back((Byte)(v >>  8));
    out.push_back((Byte)(v >> 16));
    out.push_back((Byte)(v >> 24));
}

static void WriteLE64(std::vector<Byte>& out, uint64_t v) {
    for (int i = 0; i < 8; ++i) {
        out.push_back((Byte)(v >> (i * 8)));
    }
}

static void WriteLE64_i(std::vector<Byte>& out, int64_t v) {
    WriteLE64(out, (uint64_t)v);
}

static uint32_t ReadLE32(const uint8_t* p) {
    return (uint32_t)p[0]
         | ((uint32_t)p[1] << 8)
         | ((uint32_t)p[2] << 16)
         | ((uint32_t)p[3] << 24);
}

static uint64_t ReadLE64(const uint8_t* p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v |= ((uint64_t)p[i]) << (i * 8);
    return v;
}

static int64_t ReadLE64_i(const uint8_t* p) {
    return (int64_t)ReadLE64(p);
}

// ---------------------------------------------------------------------------
// BlockHeader::SerializeTo
// ---------------------------------------------------------------------------

void BlockHeader::SerializeTo(std::vector<Byte>& out) const {
    out.reserve(out.size() + BLOCK_HEADER_SIZE);

    WriteLE32(out, version);
    out.insert(out.end(), prev_block_hash.begin(), prev_block_hash.end());
    out.insert(out.end(), merkle_root.begin(), merkle_root.end());
    WriteLE64_i(out, timestamp);
    WriteLE32(out, bits_q);
    WriteLE64(out, nonce);
    WriteLE64_i(out, height);
}

// ---------------------------------------------------------------------------
// BlockHeader::Serialize (fixed array)
// ---------------------------------------------------------------------------

std::array<Byte, BLOCK_HEADER_SIZE> BlockHeader::Serialize() const {
    std::vector<Byte> buf;
    buf.reserve(BLOCK_HEADER_SIZE);
    SerializeTo(buf);

    std::array<Byte, BLOCK_HEADER_SIZE> result{};
    std::memcpy(result.data(), buf.data(), BLOCK_HEADER_SIZE);
    return result;
}

// ---------------------------------------------------------------------------
// BlockHeader::DeserializeFrom
// ---------------------------------------------------------------------------

bool BlockHeader::DeserializeFrom(
    const std::vector<Byte>& data,
    size_t& offset,
    BlockHeader& out,
    std::string* err)
{
    if (offset + BLOCK_HEADER_SIZE > data.size()) {
        if (err) *err = "BlockHeader: insufficient bytes (need 96)";
        return false;
    }

    const uint8_t* p = data.data() + offset;

    out.version = ReadLE32(p); p += 4;
    std::memcpy(out.prev_block_hash.data(), p, 32); p += 32;
    std::memcpy(out.merkle_root.data(), p, 32); p += 32;
    out.timestamp = ReadLE64_i(p); p += 8;
    out.bits_q = ReadLE32(p); p += 4;
    out.nonce = ReadLE64(p); p += 8;
    out.height = ReadLE64_i(p); p += 8;

    offset += BLOCK_HEADER_SIZE;
    return true;
}

// ---------------------------------------------------------------------------
// BlockHeader::ComputeBlockHash
// ---------------------------------------------------------------------------

Hash256 BlockHeader::ComputeBlockHash() const {
    auto hdr = Serialize();

    Hash256 intermediate{};
    SHA256(hdr.data(), BLOCK_HEADER_SIZE, intermediate.data());

    Hash256 result{};
    SHA256(intermediate.data(), 32, result.data());
    return result;
}

std::string BlockHeader::ComputeBlockHashHex() const {
    return HexStr(ComputeBlockHash());
}

// ---------------------------------------------------------------------------
// BlockHeader::operator==
// ---------------------------------------------------------------------------

bool BlockHeader::operator==(const BlockHeader& o) const {
    return version == o.version
        && prev_block_hash == o.prev_block_hash
        && merkle_root == o.merkle_root
        && timestamp == o.timestamp
        && bits_q == o.bits_q
        && nonce == o.nonce
        && height == o.height;
}

// ---------------------------------------------------------------------------
// Block::ComputeAndSetMerkleRoot
// ---------------------------------------------------------------------------

bool Block::ComputeAndSetMerkleRoot(std::string* err) {
    return ComputeMerkleRootFromTxs(txs, header.merkle_root, err);
}

// ---------------------------------------------------------------------------
// Block::VerifyMerkleRoot
// ---------------------------------------------------------------------------

bool Block::VerifyMerkleRoot(std::string* err) const {
    Hash256 computed{};
    if (!ComputeMerkleRootFromTxs(txs, computed, err)) return false;

    if (computed != header.merkle_root) {
        if (err) *err = "VerifyMerkleRoot: mismatch — computed " +
                        HexStr(computed) + " vs header " +
                        HexStr(header.merkle_root);
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Block::SerializeTo
// ---------------------------------------------------------------------------

bool Block::SerializeTo(std::vector<Byte>& out, std::string* err) const {
    // Header (96 bytes)
    header.SerializeTo(out);

    // tx_count (CompactSize)
    WriteCompactSize(out, txs.size());

    // Transactions — serialize each to temp buffer because
    // Transaction::Serialize() calls out.clear() (by design for txid).
    for (size_t i = 0; i < txs.size(); ++i) {
        std::vector<Byte> tx_buf;
        if (!txs[i].Serialize(tx_buf, err)) {
            if (err) *err = "Block::SerializeTo: tx[" + std::to_string(i) +
                            "] " + *err;
            return false;
        }
        out.insert(out.end(), tx_buf.begin(), tx_buf.end());
    }

    return true;
}

// ---------------------------------------------------------------------------
// Block::DeserializeFrom
// Uses Transaction::DeserializeFrom (offset-based) which shares the same
// internal helpers (ReadU32LE, ReadU8, etc.) as Transaction::Serialize,
// guaranteeing format compatibility.
// ---------------------------------------------------------------------------

bool Block::DeserializeFrom(
    const std::vector<Byte>& data,
    size_t& offset,
    Block& out,
    std::string* err)
{
    // Header
    if (!BlockHeader::DeserializeFrom(data, offset, out.header, err)) return false;

    // tx_count
    uint64_t tx_count = 0;
    if (!ReadCompactSize(data, offset, tx_count, err)) return false;

    if (tx_count == 0) {
        if (err) *err = "Block::DeserializeFrom: tx_count = 0";
        return false;
    }

    if (tx_count > 65536) {
        if (err) *err = "Block::DeserializeFrom: tx_count too large (" +
                        std::to_string(tx_count) + ")";
        return false;
    }

    // Transactions
    out.txs.resize((size_t)tx_count);
    for (size_t i = 0; i < (size_t)tx_count; ++i) {
        if (!Transaction::DeserializeFrom(data, offset, out.txs[i], err)) {
            if (err) *err = "Block::DeserializeFrom: tx[" + std::to_string(i) +
                            "] " + *err;
            return false;
        }
    }

    return true;
}

// ---------------------------------------------------------------------------
// Block::EstimateSize
// ---------------------------------------------------------------------------

size_t Block::EstimateSize() const {
    std::vector<Byte> buf;
    if (!SerializeTo(buf, nullptr)) return 0;
    return buf.size();
}

// ---------------------------------------------------------------------------
// MakeGenesisHeader
// ---------------------------------------------------------------------------

BlockHeader MakeGenesisHeader(
    const Hash256& merkle_root,
    int64_t timestamp,
    uint32_t bits_q)
{
    BlockHeader hdr;
    hdr.version = BLOCK_HEADER_VERSION;
    hdr.prev_block_hash = Hash256{};  // 0x00*32
    hdr.merkle_root = merkle_root;
    hdr.timestamp = timestamp;
    hdr.bits_q = bits_q;
    hdr.nonce = 0;
    hdr.height = 0;
    return hdr;
}

} // namespace sost
