// =============================================================================
// SOST — Phase 5: Block Header + Block Implementation
// =============================================================================

#include <sost/block.h>
#include <openssl/sha.h>
#include <cstdio>
#include <cstdlib>
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
// BlockHeader::SerializeTo — version-aware
//   v1 → writes 96 bytes
//   v2 → writes 96 v1 bytes + 33-byte miner_pubkey + 64-byte miner_signature
//        = 193 bytes total
//   other version → no-op (debug log to stderr); SerializeBytes() / Serialize()
//        surface the error.
// ---------------------------------------------------------------------------

void BlockHeader::SerializeTo(std::vector<Byte>& out) const {
    if (version != BLOCK_HEADER_VERSION_V1 && version != BLOCK_HEADER_VERSION_V2) {
        std::fprintf(stderr,
            "BlockHeader::SerializeTo: unknown version %u — refusing to serialize\n",
            version);
        return;
    }

    const size_t needed = (version == BLOCK_HEADER_VERSION_V2)
                          ? BLOCK_HEADER_SIZE_V2
                          : BLOCK_HEADER_SIZE_V1;
    out.reserve(out.size() + needed);

    // V1 base — written for both versions, identical bit-for-bit.
    WriteLE32(out, version);
    out.insert(out.end(), prev_block_hash.begin(), prev_block_hash.end());
    out.insert(out.end(), merkle_root.begin(), merkle_root.end());
    WriteLE64_i(out, timestamp);
    WriteLE32(out, bits_q);
    WriteLE64(out, nonce);
    WriteLE64_i(out, height);

    // V2 SbPoW extension — only when version == 2.
    if (version == BLOCK_HEADER_VERSION_V2) {
        out.insert(out.end(), miner_pubkey.begin(),    miner_pubkey.end());
        out.insert(out.end(), miner_signature.begin(), miner_signature.end());
    }
}

// ---------------------------------------------------------------------------
// BlockHeader::Serialize (fixed 96-byte array — raw V1 layout)
//
// Always emits the 7 base fields in v1 layout regardless of `version`. This
// is a byte-layout helper used by tests (test_merkle_block.cpp B08, B10,
// B11) that inspect the wire format at fixed offsets and pass arbitrary
// version values to verify LE encoding.
//
// The v2 SbPoW extension is NOT included by this overload. New code that
// needs the version-aware payload (96 or 193 bytes) must call
// SerializeBytes() instead. ComputeBlockHash() also uses SerializeBytes()
// so v2 hashes the full 193-byte body.
// ---------------------------------------------------------------------------

std::array<Byte, BLOCK_HEADER_SIZE> BlockHeader::Serialize() const {
    std::vector<Byte> buf;
    buf.reserve(BLOCK_HEADER_SIZE_V1);

    // Inline v1 layout — independent of `version` so this helper is safe
    // for byte-level layout tests that probe with arbitrary version values.
    WriteLE32(buf, version);
    buf.insert(buf.end(), prev_block_hash.begin(), prev_block_hash.end());
    buf.insert(buf.end(), merkle_root.begin(), merkle_root.end());
    WriteLE64_i(buf, timestamp);
    WriteLE32(buf, bits_q);
    WriteLE64(buf, nonce);
    WriteLE64_i(buf, height);

    std::array<Byte, BLOCK_HEADER_SIZE> result{};
    std::memcpy(result.data(), buf.data(), BLOCK_HEADER_SIZE_V1);
    return result;
}

// ---------------------------------------------------------------------------
// BlockHeader::SerializeBytes — version-aware general-purpose serializer.
// Returns empty vector on unknown version so DeserializeStandalone tests can
// detect the rejection cleanly.
// ---------------------------------------------------------------------------

std::vector<Byte> BlockHeader::SerializeBytes() const {
    std::vector<Byte> buf;
    if (version != BLOCK_HEADER_VERSION_V1 && version != BLOCK_HEADER_VERSION_V2) {
        return buf;  // empty signals failure
    }
    SerializeTo(buf);
    return buf;
}

// ---------------------------------------------------------------------------
// BlockHeader::DeserializeFrom — streaming, version-aware
// Reads version first, then 92 v1 bytes (for v1) or 92 v1 bytes + 97 v2
// extension bytes (for v2). Advances `offset` by 96 or 193. Used by
// Block::DeserializeFrom which expects more data (txs) afterwards.
// ---------------------------------------------------------------------------

bool BlockHeader::DeserializeFrom(
    const std::vector<Byte>& data,
    size_t& offset,
    BlockHeader& out,
    std::string* err)
{
    // Minimum size for ANY valid header is the v1 size (96 B). Buffers
    // shorter than that cannot carry either v1 or v2 — surface this
    // before reading the version field so the error message is the
    // legacy "insufficient" wording (test_merkle_block B05 string-matches
    // on this).
    if (offset + BLOCK_HEADER_SIZE_V1 > data.size()) {
        if (err) *err = "BlockHeader: insufficient bytes (need at least 96)";
        return false;
    }

    const uint8_t* base = data.data() + offset;
    uint32_t v = ReadLE32(base);

    size_t need;
    if (v == BLOCK_HEADER_VERSION_V1) {
        need = BLOCK_HEADER_SIZE_V1;
    } else if (v == BLOCK_HEADER_VERSION_V2) {
        need = BLOCK_HEADER_SIZE_V2;
    } else {
        if (err) *err = "BlockHeader: unknown version " + std::to_string(v);
        return false;
    }

    if (offset + need > data.size()) {
        if (err) *err = "BlockHeader: insufficient bytes for version " +
                        std::to_string(v) + " (need " + std::to_string(need) + ")";
        return false;
    }

    const uint8_t* p = base;

    out.version = ReadLE32(p); p += 4;
    std::memcpy(out.prev_block_hash.data(), p, 32); p += 32;
    std::memcpy(out.merkle_root.data(), p, 32); p += 32;
    out.timestamp = ReadLE64_i(p); p += 8;
    out.bits_q = ReadLE32(p); p += 4;
    out.nonce = ReadLE64(p); p += 8;
    out.height = ReadLE64_i(p); p += 8;

    if (v == BLOCK_HEADER_VERSION_V2) {
        std::memcpy(out.miner_pubkey.data(),    p, SBPOW_PUBKEY_SIZE);
        p += SBPOW_PUBKEY_SIZE;
        std::memcpy(out.miner_signature.data(), p, SBPOW_SIGNATURE_SIZE);
        p += SBPOW_SIGNATURE_SIZE;
    } else {
        out.miner_pubkey.fill(0);
        out.miner_signature.fill(0);
    }

    offset += need;
    return true;
}

// ---------------------------------------------------------------------------
// BlockHeader::DeserializeStandalone — strict size + version match
// Accepts ONLY:
//   buffer.size() == 96  AND first 4 bytes encode version 1.
//   buffer.size() == 193 AND first 4 bytes encode version 2.
// Anything else (96-byte buffer with version=2, 193-byte buffer with
// version=1, unknown version, mismatched size) is rejected.
// Used by standalone-buffer tests in test_sbpow_header_v2.cpp.
// ---------------------------------------------------------------------------

bool BlockHeader::DeserializeStandalone(
    const std::vector<Byte>& buffer,
    BlockHeader& out,
    std::string* err)
{
    if (buffer.size() != BLOCK_HEADER_SIZE_V1 &&
        buffer.size() != BLOCK_HEADER_SIZE_V2) {
        if (err) *err = "BlockHeader::DeserializeStandalone: unsupported size " +
                        std::to_string(buffer.size()) +
                        " (must be 96 or 193)";
        return false;
    }

    if (buffer.size() < 4) {
        if (err) *err = "BlockHeader::DeserializeStandalone: short for version";
        return false;
    }

    uint32_t v = ReadLE32(buffer.data());
    if (buffer.size() == BLOCK_HEADER_SIZE_V1 && v != BLOCK_HEADER_VERSION_V1) {
        if (err) *err = "BlockHeader::DeserializeStandalone: 96-byte buffer "
                        "must declare version 1, got " + std::to_string(v);
        return false;
    }
    if (buffer.size() == BLOCK_HEADER_SIZE_V2 && v != BLOCK_HEADER_VERSION_V2) {
        if (err) *err = "BlockHeader::DeserializeStandalone: 193-byte buffer "
                        "must declare version 2, got " + std::to_string(v);
        return false;
    }

    // Delegate to the streaming path for the actual byte-level read.
    size_t offset = 0;
    if (!DeserializeFrom(buffer, offset, out, err)) return false;
    if (offset != buffer.size()) {
        if (err) *err = "BlockHeader::DeserializeStandalone: trailing bytes "
                        "after header (consumed " + std::to_string(offset) +
                        " of " + std::to_string(buffer.size()) + ")";
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// BlockHeader::ComputeBlockHash — version-aware
// Hashes the version-appropriate serialization (96 B for v1, 193 B for v2).
// V1 path is bit-for-bit identical to pre-V11 logic.
// SbPoW signature signs the ConvergenceX commit, NOT the block_id, because
// the block_id of a v2 header already includes the signature in the hashed
// bytes. See docs/V11_PHASE2_DESIGN.md §1.4 and §1.5.
// ---------------------------------------------------------------------------

Hash256 BlockHeader::ComputeBlockHash() const {
    std::vector<Byte> buf = SerializeBytes();

    Hash256 intermediate{};
    SHA256(buf.data(), buf.size(), intermediate.data());

    Hash256 result{};
    SHA256(intermediate.data(), 32, result.data());
    return result;
}

std::string BlockHeader::ComputeBlockHashHex() const {
    return HexStr(ComputeBlockHash());
}

// ---------------------------------------------------------------------------
// BlockHeader::operator==
// V1 fields are always compared. V2 fields (miner_pubkey, miner_signature)
// are compared only when both headers are version 2.
// ---------------------------------------------------------------------------

bool BlockHeader::operator==(const BlockHeader& o) const {
    bool base = version == o.version
        && prev_block_hash == o.prev_block_hash
        && merkle_root == o.merkle_root
        && timestamp == o.timestamp
        && bits_q == o.bits_q
        && nonce == o.nonce
        && height == o.height;
    if (!base) return false;
    if (version == BLOCK_HEADER_VERSION_V2) {
        return miner_pubkey == o.miner_pubkey
            && miner_signature == o.miner_signature;
    }
    return true;
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

// ---------------------------------------------------------------------------
// BlockHeaderToCore72 — bridge between 96-byte internal header and
// 72-byte PoW consensus header_core (Python-compatible format)
// ---------------------------------------------------------------------------

void BlockHeaderToCore72(const BlockHeader& hdr, uint8_t out[72]) {
    std::memcpy(out,      hdr.prev_block_hash.data(), 32);
    std::memcpy(out + 32, hdr.merkle_root.data(),     32);
    // timestamp: truncate i64 → u32 LE (safe until year 2106)
    uint32_t ts_u32 = (uint32_t)(hdr.timestamp & 0xFFFFFFFF);
    out[64] = (uint8_t)(ts_u32      );
    out[65] = (uint8_t)(ts_u32 >>  8);
    out[66] = (uint8_t)(ts_u32 >> 16);
    out[67] = (uint8_t)(ts_u32 >> 24);
    // bits_q: already u32
    out[68] = (uint8_t)(hdr.bits_q      );
    out[69] = (uint8_t)(hdr.bits_q >>  8);
    out[70] = (uint8_t)(hdr.bits_q >> 16);
    out[71] = (uint8_t)(hdr.bits_q >> 24);
}

} // namespace sost
