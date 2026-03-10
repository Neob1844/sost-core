// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace sost {

// -----------------------------------------------------------------------------
// Basic byte/hash types
// -----------------------------------------------------------------------------

using Byte = uint8_t;
using Hash256 = std::array<Byte, 32>;

// -----------------------------------------------------------------------------
// Tx / Output type constants (v1)
// -----------------------------------------------------------------------------

constexpr uint8_t TX_TYPE_STANDARD = 0x00;
constexpr uint8_t TX_TYPE_COINBASE = 0x01;

constexpr uint8_t OUT_TRANSFER      = 0x00;
constexpr uint8_t OUT_COINBASE_MINER= 0x01;
constexpr uint8_t OUT_COINBASE_GOLD = 0x02;
constexpr uint8_t OUT_COINBASE_POPC = 0x03;

// Reserved (inactive in v1, activation by height in consensus validation)
constexpr uint8_t OUT_BOND_LOCK     = 0x10;
constexpr uint8_t OUT_ESCROW_LOCK   = 0x11;
// Reserved. NOT activated. SOST supply is immutable — no token destruction
// mechanism exists or is planned. All slashing redistributes funds (50% PoPC
// Pool, 50% Gold Funding Vault); nothing is ever burned.
constexpr uint8_t OUT_BURN          = 0x20;

// -----------------------------------------------------------------------------
// TxInput
// -----------------------------------------------------------------------------

struct TxInput {
    Hash256 prev_txid{};                 // 32 bytes raw
    uint32_t prev_index{0};              // u32 LE
    std::array<Byte, 64> signature{};    // compact ECDSA (r||s), or coinbase field
    std::array<Byte, 33> pubkey{};       // compressed pubkey (or 0x00*33 for coinbase)

    void SerializeTo(std::vector<Byte>& out) const;

    static bool DeserializeFrom(
        const std::vector<Byte>& in,
        size_t& offset,
        TxInput& out_txin,
        std::string* err = nullptr);
};

// -----------------------------------------------------------------------------
// TxOutput
// -----------------------------------------------------------------------------

struct TxOutput {
    int64_t amount{0};                   // i64 LE (stocks)
    uint8_t type{OUT_TRANSFER};          // typed output
    std::array<Byte, 20> pubkey_hash{};  // RIPEMD160(SHA256(pubkey))
    std::vector<Byte> payload;           // typed metadata (empty in v1 active types)

    // payload_len is serialized as uint16 LE, so payload.size() must be <= 512.
    bool SerializeTo(std::vector<Byte>& out, std::string* err = nullptr) const;

    static bool DeserializeFrom(
        const std::vector<Byte>& in,
        size_t& offset,
        TxOutput& out_txout,
        std::string* err = nullptr);
};

// -----------------------------------------------------------------------------
// Transaction
// -----------------------------------------------------------------------------

struct Transaction {
    uint32_t version{1};                 // u32 LE
    uint8_t tx_type{TX_TYPE_STANDARD};   // 0x00 standard, 0x01 coinbase
    std::vector<TxInput> inputs;
    std::vector<TxOutput> outputs;

    // Canonical serialization used by txid and relay/storage
    bool Serialize(std::vector<Byte>& out, std::string* err = nullptr) const;

    // Parse full transaction from bytes; rejects trailing bytes
    static bool Deserialize(
        const std::vector<Byte>& in,
        Transaction& out_tx,
        std::string* err = nullptr);

    // Parse transaction at offset within a larger buffer (for block parsing).
    // Advances offset past the consumed bytes. Does NOT reject trailing bytes.
    static bool DeserializeFrom(
        const std::vector<Byte>& in,
        size_t& offset,
        Transaction& out_tx,
        std::string* err = nullptr);

    // txid = SHA256(SHA256(serialized_tx))
    bool ComputeTxId(Hash256& out_txid, std::string* err = nullptr) const;

    // Hex of raw txid bytes (no byte-reversal)
    std::string ComputeTxIdHex(std::string* err = nullptr) const;
};

// -----------------------------------------------------------------------------
// Utility helpers
// -----------------------------------------------------------------------------

// Lock payload helpers for BOND_LOCK (0x10) and ESCROW_LOCK (0x11)
// BOND_LOCK payload:   [0..7]  = lock_until (uint64_t LE, block height)
// ESCROW_LOCK payload: [0..7]  = lock_until (uint64_t LE, block height)
//                      [8..27] = beneficiary pubkey hash (20 bytes)

inline uint64_t ReadLockUntil(const std::vector<Byte>& payload) {
    if (payload.size() < 8) return 0;
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v |= (static_cast<uint64_t>(payload[i]) << (8 * i));
    return v;
}

inline void WriteLockUntil(std::vector<Byte>& payload, uint64_t lock_until) {
    payload.resize(payload.size() < 8 ? 8 : payload.size());
    for (int i = 0; i < 8; ++i)
        payload[i] = static_cast<Byte>((lock_until >> (8 * i)) & 0xFF);
}

inline std::array<Byte, 20> ReadBeneficiaryPkh(const std::vector<Byte>& payload) {
    std::array<Byte, 20> pkh{};
    if (payload.size() >= 28)
        std::copy(payload.begin() + 8, payload.begin() + 28, pkh.begin());
    return pkh;
}

// CompactSize (Bitcoin varint) encode/decode (canonical)
void WriteCompactSize(std::vector<Byte>& out, uint64_t n);

bool ReadCompactSize(
    const std::vector<Byte>& in,
    size_t& offset,
    uint64_t& out_n,
    std::string* err = nullptr);

// Hex helper (raw byte order, no reversal)
std::string HexStr(const uint8_t* data, size_t len);

// Convenience
inline std::string HexStr(const Hash256& h) { return HexStr(h.data(), h.size()); }

} // namespace sost
