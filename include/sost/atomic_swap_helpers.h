// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap HTLC — wallet/RPC helpers (Phase 3C)
// =============================================================================
//
// Pure C++ API for building and decoding HTLC transactions scaffolding.
// All builders construct UNSIGNED transactions; signing remains the wallet
// owner's responsibility. None of these helpers broadcast. None of them
// contact any external chain. None of them log private keys. They never
// hold or move funds.
//
// Every user-facing helper checks atomic_swap_htlc_active_at(spend_height)
// AND additionally checks that the activation constant is not the INT64_MAX
// sentinel; if the gate is closed, the helper returns an error result with
// a clear message: "Atomic Swap HTLC is disabled until protocol activation".
//
// Internal pure-construction utilities (used by tests) are also exposed
// without the gate check so the test suite can verify the construction
// logic is correct even while the gate is closed; those utilities are
// suffixed with _Unchecked.
//
// CLAIM / REFUND validation rules R17-R24 (already implemented in
// src/tx_validation.cpp Phase 3A + 3B-1a + 3B-1b + 3B-2) enforce the
// safety properties at consensus time. These helpers only build the
// candidate transactions; the chain rejects them while the gate is
// closed (R2 / R11).
// =============================================================================
#pragma once

#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include <cstdint>
#include <optional>
#include <string>

namespace sost {
namespace atomic_swap {

// ---------------------------------------------------------------------------
// Error helper
// ---------------------------------------------------------------------------

struct HtlcResult {
    bool ok = false;
    std::string error;
    Transaction tx;  // populated when ok == true (for build helpers)
};

// Single source of truth for the "is the feature available" check. Returns
// true iff the activation gate is at a finite (non-sentinel) height — i.e.
// the operator has performed the V14 (or later) flip. Returns false while
// the gate is INT64_MAX.
bool IsAtomicSwapHtlcEnabled();

// Convenience: the disabled-error message used by every gated helper.
inline std::string DisabledErrorMessage() {
    return "Atomic Swap HTLC is disabled until protocol activation. "
           "Activation height constant is INT64_MAX (sentinel OFF). "
           "See include/sost/atomic_swap.h for the re-flip checklist.";
}

// ---------------------------------------------------------------------------
// Build helpers — all GATED (refuse when IsAtomicSwapHtlcEnabled() is false)
// ---------------------------------------------------------------------------

// Construct an UNSIGNED HTLC_LOCK transaction.
//
// Inputs (all caller-provided):
//   - prev_txid, prev_vout, prev_amount, prev_pkh
//       The funding UTXO that pays into the lock + change.
//   - hashlock      : sha256 of the secret preimage.
//   - refund_height : absolute SOST block height >= prev_amount-spend height.
//   - claim_pkh     : counterparty's pubkey hash (RIPEMD160(SHA256(pubkey))).
//   - refund_pkh    : initiator's refund pubkey hash.
//   - lock_amount   : amount to lock (stocks; must be >= DUST_THRESHOLD).
//   - fee           : tx fee (stocks).
//
// Returns an HtlcResult with the unsigned Transaction on ok, or an error
// message describing the failure. Caller signs the input before broadcast.
HtlcResult BuildHtlcLockTx(
    const Hash256& prev_txid,
    uint32_t prev_vout,
    int64_t prev_amount,
    const std::array<uint8_t, 20>& prev_pkh,
    const std::array<uint8_t, 32>& hashlock,
    uint64_t refund_height,
    const std::array<uint8_t, 20>& claim_pkh,
    const std::array<uint8_t, 20>& refund_pkh,
    int64_t lock_amount,
    int64_t fee);

// Construct an UNSIGNED HTLC_CLAIM transaction.
//
//   - lock_txid, lock_vout, lock_amount : the HTLC_LOCK UTXO to spend.
//   - preimage             : the 32-byte secret revealing the hashlock.
//   - claim_destination_pkh: where the claimed funds go (claimant's pkh).
//   - marker_dust_amount   : small amount carried by the witness marker.
//   - fee                  : tx fee (stocks).
HtlcResult BuildHtlcClaimTx(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 20>& claim_destination_pkh,
    int64_t marker_dust_amount,
    int64_t fee);

// Construct an UNSIGNED HTLC_REFUND transaction.
//
//   - lock_txid, lock_vout, lock_amount : the HTLC_LOCK UTXO to spend.
//   - refund_destination_pkh : where the refund goes (initiator's pkh).
//   - fee                    : tx fee (stocks).
HtlcResult BuildHtlcRefundTx(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 20>& refund_destination_pkh,
    int64_t fee);

// ---------------------------------------------------------------------------
// Decode helpers — GATED
// ---------------------------------------------------------------------------

struct DecodedHtlcLock {
    int64_t amount = 0;
    std::array<uint8_t, 32> hashlock{};
    uint64_t refund_height = 0;
    std::array<uint8_t, 20> claim_pkh{};
    std::array<uint8_t, 20> refund_pkh{};
};

struct DecodedHtlcClaim {
    Hash256 lock_txid{};
    uint32_t lock_vout = 0;
    std::array<uint8_t, 32> preimage{};
};

struct DecodedHtlcRefund {
    Hash256 lock_txid{};
    uint32_t lock_vout = 0;
};

// Generic decoder. Inspects the tx and returns the populated variant that
// matches the tx_type / output shape, or an error if the tx is not a
// recognised HTLC transaction.
struct DecodedHtlc {
    enum Kind { NONE, LOCK, CLAIM, REFUND };
    Kind kind = NONE;
    DecodedHtlcLock lock;
    DecodedHtlcClaim claim;
    DecodedHtlcRefund refund;
};
HtlcResult DecodeHtlc(const Transaction& tx, DecodedHtlc& out);

// ---------------------------------------------------------------------------
// Status helper — GATED
// ---------------------------------------------------------------------------

enum class HtlcStatus {
    Unknown,        // we have no information about this outpoint
    LockedClaimable, // utxo exists, current_height < refund_height
    LockedRefundable,// utxo exists, current_height >= refund_height
    Spent,          // utxo no longer present (claimed or refunded)
};

// Returns the on-chain status of an HTLC_LOCK output. Pure read from the
// supplied utxo view; no network calls.
HtlcStatus GetHtlcStatus(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t current_height,
    const IUtxoView& utxos);

// ---------------------------------------------------------------------------
// Internal unchecked builders (test-only) — bypass the gate check.
// These exist so the test suite can verify the construction logic without
// flipping the activation gate. They are NOT exposed via RPC.
// ---------------------------------------------------------------------------

Transaction BuildHtlcLockTx_Unchecked(
    const Hash256& prev_txid,
    uint32_t prev_vout,
    int64_t prev_amount,
    const std::array<uint8_t, 20>& prev_pkh,
    const std::array<uint8_t, 32>& hashlock,
    uint64_t refund_height,
    const std::array<uint8_t, 20>& claim_pkh,
    const std::array<uint8_t, 20>& refund_pkh,
    int64_t lock_amount,
    int64_t fee);

Transaction BuildHtlcClaimTx_Unchecked(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 20>& claim_destination_pkh,
    int64_t marker_dust_amount,
    int64_t fee);

Transaction BuildHtlcRefundTx_Unchecked(
    const Hash256& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount,
    const std::array<uint8_t, 20>& refund_destination_pkh,
    int64_t fee);

// ---------------------------------------------------------------------------
// RPC layer (Phase 3C-1) — testable handlers consumed by src/sost-rpc.cpp
// ---------------------------------------------------------------------------
//
// Each RPC helper takes a positional-string params vector (same shape as
// the existing src/sost-rpc.cpp dispatch), validates each parameter, and
// returns an HtlcRpcResult. On success body is a JSON object string (no
// outer JSON-RPC envelope; the RPC layer wraps it via rpc_result). On
// failure body is a human-readable error message and error_code is set
// to the JSON-RPC error code the wrapper should emit.
//
// HARD INVARIANTS:
//   - All 5 helpers refuse with the disabled message while
//     IsAtomicSwapHtlcEnabled() is false (gate at INT64_MAX).
//   - No helper signs, broadcasts, or contacts any external chain.
//   - No helper logs or returns private key material.
//   - Hex inputs are validated for length and character set before use.
//   - Numeric inputs are validated for range and non-negativity.

struct HtlcRpcResult {
    bool ok = false;
    int error_code = -32603;  // JSON-RPC internal error code (used on !ok)
    std::string body;         // JSON object on ok; error message on !ok
};

// createhtlclock — positional params (10):
//   p[0]  prev_txid (64 hex)
//   p[1]  prev_vout (uint32 decimal)
//   p[2]  prev_amount (int64 decimal, stocks)
//   p[3]  prev_pkh (40 hex)
//   p[4]  hashlock (64 hex)
//   p[5]  refund_height (int64 decimal)
//   p[6]  claim_pkh (40 hex)
//   p[7]  refund_pkh (40 hex)
//   p[8]  lock_amount (int64 decimal, stocks)
//   p[9]  fee (int64 decimal, stocks)
// On success body: {"raw_tx_hex":"<hex>","unsigned":true}
HtlcRpcResult HandleCreateHtlcLockRpc(const std::vector<std::string>& params);

// claimhtlc — positional params (7):
//   p[0]  lock_txid (64 hex)
//   p[1]  lock_vout (uint32 decimal)
//   p[2]  lock_amount (int64 decimal, stocks)
//   p[3]  preimage (64 hex)
//   p[4]  claim_destination_pkh (40 hex)
//   p[5]  marker_dust_amount (int64 decimal, stocks)
//   p[6]  fee (int64 decimal, stocks)
HtlcRpcResult HandleClaimHtlcRpc(const std::vector<std::string>& params);

// refundhtlc — positional params (5):
//   p[0]  lock_txid (64 hex)
//   p[1]  lock_vout (uint32 decimal)
//   p[2]  lock_amount (int64 decimal, stocks)
//   p[3]  refund_destination_pkh (40 hex)
//   p[4]  fee (int64 decimal, stocks)
HtlcRpcResult HandleRefundHtlcRpc(const std::vector<std::string>& params);

// decodehtlc — positional params (1):
//   p[0]  raw_tx_hex
// On success body: {"kind":"LOCK|CLAIM|REFUND", ...fields...}
HtlcRpcResult HandleDecodeHtlcRpc(const std::vector<std::string>& params);

// gethtlcstatus — positional params (2):
//   p[0]  lock_txid (64 hex)
//   p[1]  lock_vout (uint32 decimal)
// Uses the supplied chain context (current height + utxo view).
// On success body: {"status":"<Unknown|LockedClaimable|LockedRefundable|Spent>"}
HtlcRpcResult HandleGetHtlcStatusRpc(
    const std::vector<std::string>& params,
    int64_t current_height,
    const IUtxoView& utxos);

} // namespace atomic_swap
} // namespace sost
