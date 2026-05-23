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
// Atomic Swap HTLC tx types — reserved for Phase 3A spending paths
// (CLAIM consumes an OUT_HTLC_LOCK by revealing the preimage;
// REFUND consumes the same output after the timeout). The validation
// rules for these tx types are gated by atomic_swap_htlc_active_at()
// in include/sost/atomic_swap.h. With the gate at INT64_MAX (sentinel
// OFF) the validator never accepts these tx types. Phase 3A scope-B
// reserves the values but does NOT yet implement the spending-path
// validation — that is a follow-up sprint.
constexpr uint8_t TX_TYPE_HTLC_CLAIM  = 0x10;
constexpr uint8_t TX_TYPE_HTLC_REFUND = 0x11;

constexpr uint8_t OUT_TRANSFER      = 0x00;
constexpr uint8_t OUT_COINBASE_MINER= 0x01;
constexpr uint8_t OUT_COINBASE_GOLD = 0x02;
constexpr uint8_t OUT_COINBASE_POPC = 0x03;
// V11 Phase 2 — lottery winner output, only emitted on triggered+non-empty
// (PAYOUT) coinbase blocks at heights >= V11_PHASE2_HEIGHT. The amount
// equals lottery_share + pending_lottery_before (jackpot rollover §10.5).
// Phase 2 activates at V11_PHASE2_HEIGHT = 10000 (params.h, set by C10);
// this output type appears on triggered chain blocks from height 10000.
constexpr uint8_t OUT_COINBASE_LOTTERY = 0x04;

// Reserved (inactive in v1, activation by height in consensus validation)
constexpr uint8_t OUT_BOND_LOCK     = 0x10;
constexpr uint8_t OUT_ESCROW_LOCK   = 0x11;
// Atomic Swap HTLC LOCK output. Payload layout is
// [hashlock(32) | refund_height(8 LE) | claim_pkh(20) | refund_pkh(20)]
// = HTLC_LOCK_PAYLOAD_LEN = 80 bytes. Activation is gated by
// atomic_swap_htlc_active_at() in include/sost/atomic_swap.h. With the
// gate at INT64_MAX the validator rejects this output type as inactive
// (R11). Pre-activation chain replay is bit-identical because this type
// has never been mined.
constexpr uint8_t OUT_HTLC_LOCK     = 0x12;
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

// -----------------------------------------------------------------------------
// HTLC_LOCK payload helpers (OUT_HTLC_LOCK = 0x12)
//
// Payload layout (HTLC_LOCK_PAYLOAD_LEN = 80 bytes, fixed):
//   [ 0..31]  hashlock       (32 bytes, sha256(preimage))
//   [32..39]  refund_height  (uint64 LE, absolute block height)
//   [40..59]  claim_pkh      (20 bytes, RIPEMD160(SHA256(claim_pubkey)))
//   [60..79]  refund_pkh     (20 bytes, RIPEMD160(SHA256(refund_pubkey)))
//
// All readers tolerate short payloads by returning a zero-filled value so
// the structural rule R17 in src/tx_validation.cpp can produce the right
// error code without segfaulting on malformed inputs.
// -----------------------------------------------------------------------------

inline constexpr size_t HTLC_LOCK_PAYLOAD_LEN = 80;

inline std::array<Byte, 32> ReadHtlcHashlock(const std::vector<Byte>& payload) {
    std::array<Byte, 32> h{};
    if (payload.size() >= 32)
        std::copy(payload.begin(), payload.begin() + 32, h.begin());
    return h;
}

inline uint64_t ReadHtlcRefundHeight(const std::vector<Byte>& payload) {
    if (payload.size() < 40) return 0;
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v |= (static_cast<uint64_t>(payload[32 + i]) << (8 * i));
    return v;
}

inline std::array<Byte, 20> ReadHtlcClaimPkh(const std::vector<Byte>& payload) {
    std::array<Byte, 20> pkh{};
    if (payload.size() >= 60)
        std::copy(payload.begin() + 40, payload.begin() + 60, pkh.begin());
    return pkh;
}

inline std::array<Byte, 20> ReadHtlcRefundPkh(const std::vector<Byte>& payload) {
    std::array<Byte, 20> pkh{};
    if (payload.size() >= 80)
        std::copy(payload.begin() + 60, payload.begin() + 80, pkh.begin());
    return pkh;
}

inline void WriteHtlcLockPayload(
    std::vector<Byte>& payload,
    const std::array<Byte, 32>& hashlock,
    uint64_t refund_height,
    const std::array<Byte, 20>& claim_pkh,
    const std::array<Byte, 20>& refund_pkh)
{
    payload.assign(HTLC_LOCK_PAYLOAD_LEN, 0);
    std::copy(hashlock.begin(), hashlock.end(), payload.begin());
    for (int i = 0; i < 8; ++i)
        payload[32 + i] = static_cast<Byte>((refund_height >> (8 * i)) & 0xFF);
    std::copy(claim_pkh.begin(), claim_pkh.end(), payload.begin() + 40);
    std::copy(refund_pkh.begin(), refund_pkh.end(), payload.begin() + 60);
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
