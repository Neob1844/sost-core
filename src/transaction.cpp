// =============================================================================
// transaction.cpp — SOST Transaction Serialization (consensus-critical)
// =============================================================================
//
// Implements canonical byte-level serialization for TxInput, TxOutput, and
// Transaction as specified in Design Document v1.2a, Section 5.
//
// All integers are little-endian. CompactSize uses Bitcoin's varint encoding.
// txid = SHA256(SHA256(serialized_tx)).
//
// This file is consensus-critical: any deviation in serialization order,
// endianness, or field layout will cause chain forks between nodes.
//
// =============================================================================

#include "sost/transaction.h"

#include <openssl/sha.h>
#include <cstring>
#include <sstream>
#include <iomanip>
#include <utility>

namespace sost {

// =============================================================================
// Little-endian integer helpers (consensus-critical byte order)
// =============================================================================

static void WriteU32LE(std::vector<Byte>& out, uint32_t v) {
    out.push_back(static_cast<Byte>(v & 0xFF));
    out.push_back(static_cast<Byte>((v >> 8) & 0xFF));
    out.push_back(static_cast<Byte>((v >> 16) & 0xFF));
    out.push_back(static_cast<Byte>((v >> 24) & 0xFF));
}

static void WriteU64LE(std::vector<Byte>& out, uint64_t v) {
    for (int i = 0; i < 8; ++i) {
        out.push_back(static_cast<Byte>(v & 0xFF));
        v >>= 8;
    }
}

static void WriteI64LE(std::vector<Byte>& out, int64_t v) {
    uint64_t u = static_cast<uint64_t>(v);
    for (int i = 0; i < 8; ++i) {
        out.push_back(static_cast<Byte>(u & 0xFF));
        u >>= 8;
    }
}

static bool ReadU32LE(const std::vector<Byte>& in, size_t& offset,
                      uint32_t& out_val, std::string* err) {
    if (offset + 4 > in.size()) {
        if (err) *err = "ReadU32LE: unexpected end of data";
        return false;
    }
    out_val = static_cast<uint32_t>(in[offset])
            | (static_cast<uint32_t>(in[offset + 1]) << 8)
            | (static_cast<uint32_t>(in[offset + 2]) << 16)
            | (static_cast<uint32_t>(in[offset + 3]) << 24);
    offset += 4;
    return true;
}

static bool ReadU64LE(const std::vector<Byte>& in, size_t& offset,
                      uint64_t& out_val, std::string* err) {
    if (offset + 8 > in.size()) {
        if (err) *err = "ReadU64LE: unexpected end of data";
        return false;
    }
    uint64_t u = 0;
    for (int i = 0; i < 8; ++i) {
        u |= (static_cast<uint64_t>(in[offset + i]) << (8 * i));
    }
    out_val = u;
    offset += 8;
    return true;
}

static bool ReadI64LE(const std::vector<Byte>& in, size_t& offset,
                      int64_t& out_val, std::string* err) {
    if (offset + 8 > in.size()) {
        if (err) *err = "ReadI64LE: unexpected end of data";
        return false;
    }
    uint64_t u = 0;
    for (int i = 0; i < 8; ++i) {
        u |= static_cast<uint64_t>(in[offset + i]) << (8 * i);
    }
    out_val = static_cast<int64_t>(u);
    offset += 8;
    return true;
}

static bool ReadU8(const std::vector<Byte>& in, size_t& offset,
                   uint8_t& out_val, std::string* err) {
    if (offset >= in.size()) {
        if (err) *err = "ReadU8: unexpected end of data";
        return false;
    }
    out_val = in[offset++];
    return true;
}

static bool ReadBytes(const std::vector<Byte>& in, size_t& offset,
                      Byte* dst, size_t count, std::string* err) {
    if (offset + count > in.size()) {
        if (err) *err = "ReadBytes: unexpected end of data";
        return false;
    }
    std::memcpy(dst, in.data() + offset, count);
    offset += count;
    return true;
}

static void WriteBytes(std::vector<Byte>& out, const Byte* src, size_t count) {
    out.insert(out.end(), src, src + count);
}

// =============================================================================
// CompactSize (Bitcoin varint) — canonical encoding
// =============================================================================
//
// Encoding rules:
//   0x00-0xFC:           1 byte  (value itself)
//   0xFD-0xFFFF:         3 bytes (0xFD + uint16_le)
//   0x10000-0xFFFFFFFF:  5 bytes (0xFE + uint32_le)
//   larger:              9 bytes (0xFF + uint64_le)
//
// Canonical means: the shortest possible encoding MUST be used.
// Non-canonical encodings (e.g., 0xFD for values < 0xFD) are invalid.

void WriteCompactSize(std::vector<Byte>& out, uint64_t n) {
    if (n < 0xFD) {
        out.push_back(static_cast<Byte>(n));
    } else if (n <= 0xFFFF) {
        out.push_back(0xFD);
        out.push_back(static_cast<Byte>(n & 0xFF));
        out.push_back(static_cast<Byte>((n >> 8) & 0xFF));
    } else if (n <= 0xFFFFFFFFULL) {
        out.push_back(0xFE);
        WriteU32LE(out, static_cast<uint32_t>(n));
    } else {
        out.push_back(0xFF);
        WriteU64LE(out, n);
    }
}

bool ReadCompactSize(const std::vector<Byte>& in, size_t& offset,
                     uint64_t& out_n, std::string* err) {
    uint8_t first = 0;
    if (!ReadU8(in, offset, first, err)) return false;

    if (first < 0xFD) {
        out_n = first;
        return true;
    }

    if (first == 0xFD) {
        if (offset + 2 > in.size()) {
            if (err) *err = "ReadCompactSize: truncated u16";
            return false;
        }
        out_n = static_cast<uint64_t>(in[offset])
              | (static_cast<uint64_t>(in[offset + 1]) << 8);
        offset += 2;

        // Canonical check: must be >= 0xFD
        if (out_n < 0xFD) {
            if (err) *err = "ReadCompactSize: non-canonical encoding (u16 < 0xFD)";
            return false;
        }
        return true;
    }

    if (first == 0xFE) {
        uint32_t v = 0;
        if (!ReadU32LE(in, offset, v, err)) return false;
        out_n = v;

        // Canonical check: must be > 0xFFFF
        if (out_n <= 0xFFFF) {
            if (err) *err = "ReadCompactSize: non-canonical encoding (u32 <= 0xFFFF)";
            return false;
        }
        return true;
    }

    // first == 0xFF
    uint64_t v = 0;
    if (!ReadU64LE(in, offset, v, err)) return false;
    out_n = v;

    // Canonical check: must be > 0xFFFFFFFF
    if (out_n <= 0xFFFFFFFFULL) {
        if (err) *err = "ReadCompactSize: non-canonical encoding (u64 <= 0xFFFFFFFF)";
        return false;
    }
    return true;
}

// =============================================================================
// TxInput serialization
// =============================================================================
//
// Layout (133 bytes fixed):
//   prev_txid     32 bytes  raw
//   prev_index     4 bytes  u32 LE
//   signature     64 bytes  raw (r[32] big-endian || s[32] big-endian)
//   pubkey        33 bytes  raw (compressed, 02/03 prefix)

void TxInput::SerializeTo(std::vector<Byte>& out) const {
    WriteBytes(out, prev_txid.data(), 32);
    WriteU32LE(out, prev_index);
    WriteBytes(out, signature.data(), 64);
    WriteBytes(out, pubkey.data(), 33);
}

bool TxInput::DeserializeFrom(const std::vector<Byte>& in, size_t& offset,
                              TxInput& out_txin, std::string* err) {
    if (!ReadBytes(in, offset, out_txin.prev_txid.data(), 32, err)) return false;
    if (!ReadU32LE(in, offset, out_txin.prev_index, err)) return false;
    if (!ReadBytes(in, offset, out_txin.signature.data(), 64, err)) return false;
    if (!ReadBytes(in, offset, out_txin.pubkey.data(), 33, err)) return false;
    return true;
}

// =============================================================================
// TxOutput serialization
// =============================================================================
//
// Layout (30 + payload_len bytes):
//   amount         8 bytes  i64 LE
//   type           1 byte
//   pubkey_hash   20 bytes  raw
//   payload_len    1 byte   u8 (0..255)
//   payload        N bytes  raw (N = payload_len)

bool TxOutput::SerializeTo(std::vector<Byte>& out, std::string* err) const {
    // Validate payload size fits in uint8
    if (payload.size() > 255) {
        if (err) *err = "TxOutput::Serialize: payload_len exceeds 255 bytes";
        return false;
    }

    WriteI64LE(out, amount);
    out.push_back(type);
    WriteBytes(out, pubkey_hash.data(), 20);
    out.push_back(static_cast<Byte>(payload.size()));
    if (!payload.empty()) {
        WriteBytes(out, payload.data(), payload.size());
    }
    return true;
}

bool TxOutput::DeserializeFrom(const std::vector<Byte>& in, size_t& offset,
                               TxOutput& out_txout, std::string* err) {
    if (!ReadI64LE(in, offset, out_txout.amount, err)) return false;
    if (!ReadU8(in, offset, out_txout.type, err)) return false;
    if (!ReadBytes(in, offset, out_txout.pubkey_hash.data(), 20, err)) return false;

    uint8_t plen = 0;
    if (!ReadU8(in, offset, plen, err)) return false;

    if (plen > 0) {
        if (offset + plen > in.size()) {
            if (err) *err = "TxOutput::Deserialize: payload truncated";
            return false;
        }
        out_txout.payload.resize(plen);
        if (!ReadBytes(in, offset, out_txout.payload.data(), plen, err)) return false;
    } else {
        out_txout.payload.clear();
    }
    return true;
}

// =============================================================================
// Transaction serialization
// =============================================================================
//
// Layout (Section 5, Design v1.2a):
//   version        4 bytes   u32 LE
//   tx_type        1 byte
//   num_inputs     CompactSize
//   inputs[]       133 bytes each (fixed per input)
//   num_outputs    CompactSize
//   outputs[]      30 + payload_len bytes each
//
// txid = SHA256(SHA256(entire serialized bytes))

bool Transaction::Serialize(std::vector<Byte>& out, std::string* err) const {
    // Produce exact canonical serialization (never append to caller buffer)
    out.clear();

    // Validate structural constraints before serializing
    if (inputs.empty()) {
        if (err) *err = "Transaction::Serialize: no inputs";
        return false;
    }
    if (outputs.empty()) {
        if (err) *err = "Transaction::Serialize: no outputs";
        return false;
    }
    if (inputs.size() > 256) {
        if (err) *err = "Transaction::Serialize: too many inputs (max 256)";
        return false;
    }
    if (outputs.size() > 256) {
        if (err) *err = "Transaction::Serialize: too many outputs (max 256)";
        return false;
    }

    WriteU32LE(out, version);
    out.push_back(tx_type);

    WriteCompactSize(out, static_cast<uint64_t>(inputs.size()));
    for (const auto& txin : inputs) {
        txin.SerializeTo(out);
    }

    WriteCompactSize(out, static_cast<uint64_t>(outputs.size()));
    for (const auto& txout : outputs) {
        if (!txout.SerializeTo(out, err)) return false;
    }

    return true;
}

bool Transaction::Deserialize(const std::vector<Byte>& in,
                              Transaction& out_tx, std::string* err) {
    // Parse into temporary object to avoid partially-mutated output on failure
    Transaction tmp{};
    size_t offset = 0;

    // Version
    if (!ReadU32LE(in, offset, tmp.version, err)) return false;

    // tx_type
    if (!ReadU8(in, offset, tmp.tx_type, err)) return false;

    // Inputs
    uint64_t num_inputs = 0;
    if (!ReadCompactSize(in, offset, num_inputs, err)) return false;
    if (num_inputs == 0) {
        if (err) *err = "Transaction::Deserialize: zero inputs";
        return false;
    }
    if (num_inputs > 256) {
        if (err) *err = "Transaction::Deserialize: too many inputs (max 256)";
        return false;
    }

    tmp.inputs.resize(static_cast<size_t>(num_inputs));
    for (size_t i = 0; i < num_inputs; ++i) {
        if (!TxInput::DeserializeFrom(in, offset, tmp.inputs[i], err)) {
            if (err && err->empty()) {
                *err = "Transaction::Deserialize: failed at input " + std::to_string(i);
            }
            return false;
        }
    }

    // Outputs
    uint64_t num_outputs = 0;
    if (!ReadCompactSize(in, offset, num_outputs, err)) return false;
    if (num_outputs == 0) {
        if (err) *err = "Transaction::Deserialize: zero outputs";
        return false;
    }
    if (num_outputs > 256) {
        if (err) *err = "Transaction::Deserialize: too many outputs (max 256)";
        return false;
    }

    tmp.outputs.resize(static_cast<size_t>(num_outputs));
    for (size_t i = 0; i < num_outputs; ++i) {
        if (!TxOutput::DeserializeFrom(in, offset, tmp.outputs[i], err)) {
            if (err && err->empty()) {
                *err = "Transaction::Deserialize: failed at output " + std::to_string(i);
            }
            return false;
        }
    }

    // Reject trailing bytes (canonical: no extra data after last output)
    if (offset != in.size()) {
        if (err) {
            *err = "Transaction::Deserialize: trailing bytes ("
                 + std::to_string(in.size() - offset) + " extra)";
        }
        return false;
    }

    out_tx = std::move(tmp);
    return true;
}

// ---------------------------------------------------------------------------
// Transaction::DeserializeFrom (offset-based, for block parsing)
// Same as Deserialize but takes external offset and allows trailing bytes.
// ---------------------------------------------------------------------------

bool Transaction::DeserializeFrom(const std::vector<Byte>& in,
                                   size_t& offset,
                                   Transaction& out_tx, std::string* err) {
    // Version
    if (!ReadU32LE(in, offset, out_tx.version, err)) return false;

    // tx_type
    if (!ReadU8(in, offset, out_tx.tx_type, err)) return false;

    // Inputs
    uint64_t num_inputs = 0;
    if (!ReadCompactSize(in, offset, num_inputs, err)) return false;
    if (num_inputs == 0) {
        if (err) *err = "Transaction::DeserializeFrom: zero inputs";
        return false;
    }
    if (num_inputs > 256) {
        if (err) *err = "Transaction::DeserializeFrom: too many inputs (max 256)";
        return false;
    }

    out_tx.inputs.resize(static_cast<size_t>(num_inputs));
    for (size_t i = 0; i < num_inputs; ++i) {
        if (!TxInput::DeserializeFrom(in, offset, out_tx.inputs[i], err)) {
            if (err && err->empty()) {
                *err = "Transaction::DeserializeFrom: failed at input " + std::to_string(i);
            }
            return false;
        }
    }

    // Outputs
    uint64_t num_outputs = 0;
    if (!ReadCompactSize(in, offset, num_outputs, err)) return false;
    if (num_outputs == 0) {
        if (err) *err = "Transaction::DeserializeFrom: zero outputs";
        return false;
    }
    if (num_outputs > 256) {
        if (err) *err = "Transaction::DeserializeFrom: too many outputs (max 256)";
        return false;
    }

    out_tx.outputs.resize(static_cast<size_t>(num_outputs));
    for (size_t i = 0; i < num_outputs; ++i) {
        if (!TxOutput::DeserializeFrom(in, offset, out_tx.outputs[i], err)) {
            if (err && err->empty()) {
                *err = "Transaction::DeserializeFrom: failed at output " + std::to_string(i);
            }
            return false;
        }
    }

    // No trailing bytes check — offset advances for caller to continue
    return true;
}

// =============================================================================
// txid computation — SHA256(SHA256(serialized_tx))
// =============================================================================
//
// Double SHA256 as specified in Design v1.2a, Section 5.
// Consistent with sighash and Merkle tree hashing.

bool Transaction::ComputeTxId(Hash256& out_txid, std::string* err) const {
    // Serialize to canonical bytes
    std::vector<Byte> buf;
    if (!Serialize(buf, err)) return false;

    // First SHA256 pass
    Hash256 intermediate{};
    SHA256(buf.data(), buf.size(), intermediate.data());

    // Second SHA256 pass
    SHA256(intermediate.data(), intermediate.size(), out_txid.data());

    return true;
}

std::string Transaction::ComputeTxIdHex(std::string* err) const {
    Hash256 txid{};
    if (!ComputeTxId(txid, err)) return "";
    return HexStr(txid);
}

// =============================================================================
// Hex helper — raw byte order (no reversal)
// =============================================================================

std::string HexStr(const uint8_t* data, size_t len) {
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (size_t i = 0; i < len; ++i) {
        oss << std::setw(2) << static_cast<int>(data[i]);
    }
    return oss.str();
}

} // namespace sost
