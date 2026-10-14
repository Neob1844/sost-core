// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once

// =============================================================================
// type_registry.h — canonical registry of transaction-type and output-type codes
//
// NON-CONSENSUS. This header is a compile-time inventory only: no production
// translation unit includes it, it defines no runtime state, and it changes no
// validation rule. Its purpose is to make every numeric allocation in the two
// one-byte namespaces explicit and machine-checked:
//
//   * Transaction.tx_type  (u8 after the version)        -> TX namespace
//   * TxOutput.type        (u8 after the amount)         -> OUTPUT namespace
//
// The static_asserts below fail the build of any target that includes this
// header (the `type-registry` ctest) if
//   - two entries in one namespace share a code,
//   - a registry entry drifts from the constant in transaction.h,
//   - an allocated code lands inside a reserved range it does not belong to,
//   - a NEW code reuses a value already allocated in the other namespace
//     (the existing overlaps are grandfathered and listed exactly),
//   - anything is allocated in the TX namespace range 0x50-0x5F.
//
// Normative reference: docs/v40000/NATIVE_MULTISIG_SPEC_40000.md §2 and
// docs/v40000/MULTISIG_OPEN_DECISIONS_CLOSED.md (item D13).
//
// Deleted legacy code: the former script engine (include/sost/script.h) defined
// OUT_SCRIPT_HASH = 0x30, colliding with the LIVE output type OUT_NODE_PROTOCOL =
// 0x30. It was removed together with the PSBT library (spec §2.3 step 3); 0x30
// keeps its only meaning, OUT_NODE_PROTOCOL. The `type-registry` ctest asserts the
// files are absent and that nothing references them.
// =============================================================================

#include "sost/transaction.h"

#include <cstddef>
#include <cstdint>

namespace sost {
namespace type_registry {

enum class Status : uint8_t {
    ACTIVE            = 1,  // valid on mainnet at some reachable height
    DORMANT           = 2,  // defined and wired, mainnet activation INT64_MAX
    RESERVED_INACTIVE = 3,  // defined constant, never valid (R11 rejects it); must not be activated
};

struct Entry {
    uint8_t     code;
    const char* name;
    Status      status;
};

struct Range {
    uint8_t     lo;
    uint8_t     hi;
    const char* purpose;
};

// ---- TX namespace (Transaction.tx_type) ------------------------------------
inline constexpr Entry TX_TYPES[] = {
    {TX_TYPE_STANDARD,       "TX_TYPE_STANDARD",       Status::ACTIVE},
    {TX_TYPE_COINBASE,       "TX_TYPE_COINBASE",       Status::ACTIVE},
    {TX_TYPE_JACKPOT,        "TX_TYPE_JACKPOT",        Status::ACTIVE},   // V15 jackpot heights
    {TX_TYPE_HTLC_CLAIM,     "TX_TYPE_HTLC_CLAIM",     Status::ACTIVE},   // >= V14_5_HEIGHT
    {TX_TYPE_HTLC_REFUND,    "TX_TYPE_HTLC_REFUND",    Status::ACTIVE},   // >= V14_5_HEIGHT
    {TX_TYPE_NODE_BIND,      "TX_TYPE_NODE_BIND",      Status::ACTIVE},   // >= HIST_JACKPOT_V2_HEIGHT
    {TX_TYPE_NODE_HEARTBEAT, "TX_TYPE_NODE_HEARTBEAT", Status::ACTIVE},   // >= HIST_JACKPOT_V2_HEIGHT
    {TX_TYPE_ASSET_GENESIS,  "TX_TYPE_ASSET_GENESIS",  Status::DORMANT},
    {TX_TYPE_ASSET_ISSUE,    "TX_TYPE_ASSET_ISSUE",    Status::DORMANT},
    {TX_TYPE_ASSET_TRANSFER, "TX_TYPE_ASSET_TRANSFER", Status::DORMANT},
    {TX_TYPE_ASSET_BURN,     "TX_TYPE_ASSET_BURN",     Status::DORMANT},
};

// ---- OUTPUT namespace (TxOutput.type) --------------------------------------
inline constexpr Entry OUTPUT_TYPES[] = {
    {OUT_TRANSFER,           "OUT_TRANSFER",           Status::ACTIVE},
    {OUT_COINBASE_MINER,     "OUT_COINBASE_MINER",     Status::ACTIVE},
    {OUT_COINBASE_GOLD,      "OUT_COINBASE_GOLD",      Status::ACTIVE},
    {OUT_COINBASE_POPC,      "OUT_COINBASE_POPC",      Status::ACTIVE},
    {OUT_COINBASE_LOTTERY,   "OUT_COINBASE_LOTTERY",   Status::ACTIVE},   // coinbase only
    {OUT_COINBASE_JACKPOT,   "OUT_COINBASE_JACKPOT",   Status::ACTIVE},   // coinbase only, >= V17_HEIGHT (J-funded jackpot part)
    {OUT_BOND_LOCK,          "OUT_BOND_LOCK",          Status::ACTIVE},
    {OUT_ESCROW_LOCK,        "OUT_ESCROW_LOCK",        Status::ACTIVE},
    {OUT_HTLC_LOCK,          "OUT_HTLC_LOCK",          Status::ACTIVE},
    {OUT_HTLC_CLAIM_WITNESS, "OUT_HTLC_CLAIM_WITNESS", Status::ACTIVE},
    // Native SOST is never burned: OUT_BURN stays reserved and inactive forever.
    {OUT_BURN,               "OUT_BURN",               Status::RESERVED_INACTIVE},
    {OUT_NODE_PROTOCOL,      "OUT_NODE_PROTOCOL",      Status::ACTIVE},   // node txs only, never in the UTXO set
    {OUT_ASSET_TRANSFER,     "OUT_ASSET_TRANSFER",     Status::DORMANT},
    {OUT_ASSET_ISSUE_AUTH,   "OUT_ASSET_ISSUE_AUTH",   Status::DORMANT},
    {OUT_ASSET_BURN,         "OUT_ASSET_BURN",         Status::DORMANT},  // issued assets only, never native SOST
    {OUT_ASSET_GENESIS_DEF,  "OUT_ASSET_GENESIS_DEF",  Status::DORMANT},
    {OUT_MULTISIG,           "OUT_MULTISIG",           Status::ACTIVE},   // >= MULTISIG_HEIGHT (V17, mainnet 40000)
};

// Codes that must never be allocated (documentation hazard): 0x14 was named
// OUT_HTLC_REFUND in older branch documents.
inline constexpr uint8_t OUTPUT_DO_NOT_USE[] = {0x14};

// ---- Reserved ranges -------------------------------------------------------
inline constexpr Range OUTPUT_RESERVED[] = {
    {0x40, 0x4F, "native assets (0x40-0x43 allocated, dormant)"},
    {0x50, 0x5F, "custody: 0x50 = OUT_MULTISIG (V17), 0x51-0x5F reserved (no meaning, R11 rejects)"},
};
inline constexpr Range TX_RESERVED[] = {
    {0x30, 0x3F, "native assets (0x30-0x33 allocated, dormant)"},
};
// The multisig output code, allocated by the V17 implementation (active from
// MULTISIG_HEIGHT). Kept as an alias so the allocation stays pinned to 0x50.
inline constexpr uint8_t OUT_MULTISIG_PLANNED = 0x50;

// Cross-namespace numeric overlaps that already exist. They are not parse
// ambiguities (the two fields sit at different offsets) but every NEW allocation
// must avoid adding to this list.
inline constexpr uint8_t GRANDFATHERED_CROSS_NAMESPACE[] = {0x00, 0x01, 0x02, 0x10, 0x11, 0x20, 0x30};

// ---- constexpr helpers -----------------------------------------------------
template <size_t N>
constexpr bool unique_codes(const Entry (&e)[N]) {
    for (size_t i = 0; i < N; ++i)
        for (size_t j = i + 1; j < N; ++j)
            if (e[i].code == e[j].code) return false;
    return true;
}
template <size_t N>
constexpr bool contains(const Entry (&e)[N], uint8_t code) {
    for (size_t i = 0; i < N; ++i) if (e[i].code == code) return true;
    return false;
}
template <size_t N>
constexpr bool contains_u8(const uint8_t (&a)[N], uint8_t v) {
    for (size_t i = 0; i < N; ++i) if (a[i] == v) return true;
    return false;
}
template <size_t N>
constexpr size_t count_in_range(const Entry (&e)[N], uint8_t lo, uint8_t hi) {
    size_t c = 0;
    for (size_t i = 0; i < N; ++i) if (e[i].code >= lo && e[i].code <= hi) ++c;
    return c;
}
// Every overlap between the two namespaces must be grandfathered, and every
// grandfathered value must still be a real overlap (the list is exact).
constexpr bool cross_namespace_exact() {
    for (const auto& t : TX_TYPES)
        if (contains(OUTPUT_TYPES, t.code) && !contains_u8(GRANDFATHERED_CROSS_NAMESPACE, t.code))
            return false;
    for (uint8_t g : GRANDFATHERED_CROSS_NAMESPACE)
        if (!(contains(TX_TYPES, g) && contains(OUTPUT_TYPES, g))) return false;
    return true;
}
constexpr Status output_status(uint8_t code) {
    for (const auto& o : OUTPUT_TYPES) if (o.code == code) return o.status;
    return Status::RESERVED_INACTIVE;
}

// ---- compile-time invariants -----------------------------------------------
static_assert(unique_codes(TX_TYPES),     "duplicate code in the TX namespace");
static_assert(unique_codes(OUTPUT_TYPES), "duplicate code in the OUTPUT namespace");
static_assert(cross_namespace_exact(),
              "a new allocation reuses a code from the other namespace (or the grandfather list is stale)");

// Reserved output ranges hold only their own allocations.
static_assert(count_in_range(OUTPUT_TYPES, 0x40, 0x4F) == 4, "0x40-0x4F is reserved for native assets (0x40-0x43)");
static_assert(count_in_range(OUTPUT_TYPES, 0x50, 0x5F) == 1, "0x50-0x5F is custody: only 0x50 = OUT_MULTISIG is allocated");
static_assert(OUT_MULTISIG == OUT_MULTISIG_PLANNED && contains(OUTPUT_TYPES, OUT_MULTISIG), "OUT_MULTISIG is 0x50");
static_assert(count_in_range(TX_TYPES, 0x30, 0x3F) == 4, "tx 0x30-0x3F is reserved for native assets (0x30-0x33)");
static_assert(count_in_range(TX_TYPES, 0x50, 0x5F) == 0, "no tx type may use 0x50-0x5F (custody uses tx version 2, not a tx type)");
static_assert(!contains(OUTPUT_TYPES, OUTPUT_DO_NOT_USE[0]), "0x14 must never be allocated");

// Literal pins: renumbering any constant in transaction.h is a consensus change
// and must fail here first.
static_assert(TX_TYPE_STANDARD == 0x00 && TX_TYPE_COINBASE == 0x01 && TX_TYPE_JACKPOT == 0x02 &&
              TX_TYPE_HTLC_CLAIM == 0x10 && TX_TYPE_HTLC_REFUND == 0x11 &&
              TX_TYPE_NODE_BIND == 0x20 && TX_TYPE_NODE_HEARTBEAT == 0x21 &&
              TX_TYPE_ASSET_GENESIS == 0x30 && TX_TYPE_ASSET_ISSUE == 0x31 &&
              TX_TYPE_ASSET_TRANSFER == 0x32 && TX_TYPE_ASSET_BURN == 0x33,
              "tx type literal drift");
static_assert(OUT_TRANSFER == 0x00 && OUT_COINBASE_MINER == 0x01 && OUT_COINBASE_GOLD == 0x02 &&
              OUT_COINBASE_POPC == 0x03 && OUT_COINBASE_LOTTERY == 0x04 &&
              OUT_COINBASE_JACKPOT == 0x05 &&
              OUT_BOND_LOCK == 0x10 && OUT_ESCROW_LOCK == 0x11 &&
              OUT_HTLC_LOCK == 0x12 && OUT_HTLC_CLAIM_WITNESS == 0x13 &&
              OUT_BURN == 0x20 && OUT_NODE_PROTOCOL == 0x30 &&
              OUT_ASSET_TRANSFER == 0x40 && OUT_ASSET_ISSUE_AUTH == 0x41 &&
              OUT_ASSET_BURN == 0x42 && OUT_ASSET_GENESIS_DEF == 0x43 && OUT_MULTISIG == 0x50,
              "output type literal drift");

// Pinned statuses that matter for safety.
static_assert(OUT_BURN == 0x20 && output_status(OUT_BURN) == Status::RESERVED_INACTIVE,
              "OUT_BURN 0x20 must stay RESERVED_INACTIVE: native SOST is never burned");
static_assert(OUT_NODE_PROTOCOL == 0x30 && output_status(OUT_NODE_PROTOCOL) == Status::ACTIVE,
              "OUT_NODE_PROTOCOL 0x30 is live on mainnet");
static_assert(TX_TYPE_ASSET_GENESIS == 0x30, "TX_TYPE_ASSET_GENESIS sits in the TX namespace only");

} // namespace type_registry
} // namespace sost
