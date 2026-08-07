// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap — canonical cross-chain POLICY layer (OTC-5)
// =============================================================================
//
// PURE, DETERMINISTIC, NON-CUSTODIAL. This module is the SINGLE SOURCE OF
// TRUTH for the cross-cutting safety policies that were previously scattered
// across the coordinator (booleans), the orderbook (raw heights) and the
// watcher. Nothing here signs, broadcasts, reads a key, or opens a socket.
//
// It centralises six things a production SOST<->EVM swap needs:
//
//   1. EvaluateTimeoutOrder — the canonical timeout-ordering rule
//      (T1_initiator > T2_responder + margin), returning machine-checkable
//      validity AND human-readable deadlines for the UI. This is the ONE
//      place the rule lives; the orderbook/coordinator express the same
//      invariant, and this function is what a wallet should call to render
//      the safety verdict and the "refund opens at ..." strings.
//
//   2. DeriveSwapId — a collision-resistant swapId derived from
//      (participants + chain + asset + hashlock + nonce). This closes the
//      swapId-squatting DoS (an attacker front-running a fixed swapId to
//      force DUPLICATE_SWAP_ID on the victim's lock). The byte layout is
//      IDENTICAL to AtomicSwapHTLC.computeSwapId(...) so the SOST-side id and
//      the EVM-side id match bit-for-bit (both sha256 over the same packed
//      encoding).
//
//   3. ClassifyFunding — a funding/confirmation-depth classifier so the
//      wallet treats a lock as real only once it has enough confirmations
//      (never act on a 0-conf / mempool-only observation).
//
//   4. ExtractPreimageFromEvmClaim{Calldata,EventData} — pull the 32-byte
//      preimage out of an EVM claim() transaction (calldata) or a Claimed
//      event's data, verifying sha256(preimage)==hashlock before trusting
//      it. This is how the SOST-side responder learns the secret revealed
//      on the EVM side.
//
//   5. DecideRpcRecovery — an RPC-failure / network-interruption policy so
//      an auto-pilot NEVER acts on a stale or unavailable chain view (e.g.
//      never broadcasts a time-sensitive claim/refund off an outdated tip).
//
//   6. EvmAssetStatus — the TRUTHFUL per-asset EVM support classification
//      (Available / Testing / Disabled) derived from what the deployed
//      AtomicSwapHTLC contract can actually do, so config never over-claims.
//
// No consensus gate is touched; ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT and
// SOST_BTC_HTLC_SIGNING are irrelevant to this pure policy layer.
// =============================================================================
#pragma once

#include "sost/atomic_swap_orderbook.h"   // Asset, Role
#include "sost/types.h"                   // Bytes32
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace policy {

using coordinator::Role;

// -----------------------------------------------------------------------------
// 1. Canonical timeout-ordering policy
// -----------------------------------------------------------------------------
//
// The atomic-swap anti-grief discipline, stated once, on a common normalised
// block axis (the wallet normalises across chains before filling these):
//
//   * The INITIATOR locks first; their refund window (T1) must open LAST.
//   * The RESPONDER locks second; their refund window (T2) must open FIRST.
//   * Gap: T1 - T2 >= safety_margin_min_blocks.
//   * Both refund heights must be strictly in the future relative to the
//     lock height (a refund that already opened is unsafe to enter).
//
// This is the SAME invariant enforced structurally in ValidateOffer and
// expressed as booleans in the coordinator; EvaluateTimeoutOrder is the
// canonical numeric evaluator that also produces the human-readable strings.

struct TimeoutPolicyInput {
    // Absolute normalised heights (T1 = initiator/SOST-last, T2 = responder-first).
    int64_t initiator_refund_height = 0;   // T1 (opens LAST)
    int64_t responder_refund_height = 0;   // T2 (opens FIRST)
    int64_t current_height          = 0;   // normalised tip at evaluation time
    int64_t safety_margin_min_blocks = 6;  // required T1 - T2 minimum

    // Optional: seconds-per-block on the normalised axis, ONLY used to render
    // human-readable "~2h from now" strings. 0 disables the time estimate.
    int64_t seconds_per_block = 0;
};

struct TimeoutPolicyResult {
    bool ok = false;                          // true iff safe to proceed
    std::vector<std::string> errors;          // hard failures (reject the swap)
    std::vector<std::string> warnings;        // non-fatal cautions
    int64_t refund_gap = 0;                   // T1 - T2 (informational)

    // Human-readable deadline lines for the UI (always populated).
    std::string responder_deadline_human;     // when T2 opens
    std::string initiator_deadline_human;     // when T1 opens
    std::string summary_human;                // one-line verdict
};

// Evaluate the canonical timeout ordering. Pure. `ok` is true iff there are
// no errors. Always fills the human-readable fields (even on failure) so the
// UI can explain the verdict.
TimeoutPolicyResult EvaluateTimeoutOrder(const TimeoutPolicyInput& in);

// Convenience adapter: evaluate directly from an Offer (uses its heights /
// margin, and current_height from the caller). Mirrors ValidateOffer's
// ordering check but returns the richer policy result.
TimeoutPolicyResult EvaluateOfferTimeout(const Offer& o, int64_t current_height,
                                         int64_t seconds_per_block = 0);

// -----------------------------------------------------------------------------
// 2. Collision-resistant swapId derivation (anti-squatting)
// -----------------------------------------------------------------------------
//
// Byte layout is IDENTICAL to AtomicSwapHTLC.computeSwapId (Solidity
// abi.encodePacked), so DeriveSwapId(...) == computeSwapId(...) bit-for-bit:
//
//   sha256(
//     "SOST-ATOMIC-SWAP-ID-v1"     // 22 ASCII bytes, no length prefix
//     locker    (20)  claimer (20)  refunder (20)  token (20)
//     amount    (uint256, 32 BE)
//     hashlock  (32)
//     refundTime(uint256, 32 BE)
//     chainId   (uint256, 32 BE)
//     nonce     (32)
//   )
//
// `token` is all-zero (address(0)) for a native ETH/BNB leg. `nonce` MUST be
// locally-random 32 bytes NOT revealed before the lock is broadcast — that is
// what prevents an attacker from pre-registering (front-running) the id.

Bytes32 DeriveSwapId(
    const std::array<uint8_t, 20>& locker,
    const std::array<uint8_t, 20>& claimer,
    const std::array<uint8_t, 20>& refunder,
    const std::array<uint8_t, 20>& token,
    uint64_t amount,
    const Bytes32& hashlock,
    uint64_t refund_time,
    uint64_t chain_id,
    const Bytes32& nonce);

// Lowercase hex (no 0x) of a Bytes32 — small helper for ids/logging.
std::string ToHex(const Bytes32& b);

// -----------------------------------------------------------------------------
// 3. Funding / confirmation-depth classification
// -----------------------------------------------------------------------------
//
// A lock is only "real" once it has enough confirmations. The wallet feeds
// the observed depth; this classifier decides how the coordinator should
// treat it. Never advance a swap on a mempool-only (0-conf) sighting.

enum class FundingStatus : uint8_t {
    Unseen,      // no sign of the funding/lock tx at all
    InMempool,   // seen unconfirmed (0-conf) — do NOT treat as locked
    Confirming,  // included in a block but < min_confirmations deep
    Confirmed    // >= min_confirmations — safe to treat as locked
};
const char* FundingStatusName(FundingStatus s);

// current_confirmations: 0 if only in mempool / not yet mined.
FundingStatus ClassifyFunding(bool seen_in_mempool,
                              bool included_in_block,
                              int64_t current_confirmations,
                              int64_t min_confirmations);

// True iff the status is safe to treat as a completed lock (== Confirmed).
bool FundingIsSettled(FundingStatus s);

// -----------------------------------------------------------------------------
// 4. Preimage extraction from an EVM claim
// -----------------------------------------------------------------------------
//
// claim(bytes32 swapId, bytes32 preimage) — selector 0x84cc9dfb. The calldata
// is 4 + 32 + 32 = 68 bytes: [selector][swapId][preimage]. The Claimed event
// data (non-indexed) is [preimage(32)][claimer(32, left-padded addr)].
//
// Both extractors verify sha256(preimage) == expected_hashlock before
// returning success; a mismatch (or a malformed input) returns false and does
// not touch `out`.

struct PreimageExtraction {
    bool ok = false;
    std::string error;
    Bytes32 preimage{};
};

// From the raw claim() calldata hex (with or without a leading "0x").
PreimageExtraction ExtractPreimageFromEvmClaimCalldata(
    const std::string& calldata_hex,
    const Bytes32& expected_hashlock);

// From a Claimed event's `data` field hex (non-indexed args; preimage first).
PreimageExtraction ExtractPreimageFromEvmClaimEventData(
    const std::string& event_data_hex,
    const Bytes32& expected_hashlock);

// -----------------------------------------------------------------------------
// 5. RPC-failure / network-interruption recovery policy
// -----------------------------------------------------------------------------
//
// A non-custodial auto-pilot must FAIL SAFE when it cannot see the chain:
// never broadcast a time-sensitive claim/refund off a stale or unavailable
// tip, and never assume "no lock seen" == "no lock exists" when the node is
// down. This pure policy tells the caller what to do.

enum class RpcRecovery : uint8_t {
    Proceed,        // chain view is fresh and healthy — safe to act
    RetryBackoff,   // transient failure(s) — retry with backoff, do not act yet
    HaltDoNotAct    // stale/unavailable view — surface to operator, take NO action
};
const char* RpcRecoveryName(RpcRecovery r);

struct RpcHealthInput {
    int32_t consecutive_failures      = 0;   // consecutive failed RPC round-trips
    int32_t max_failures_before_halt  = 5;   // >= this many => halt
    int64_t seconds_since_last_success = 0;  // age of the freshest chain view
    int64_t max_stale_seconds         = 120; // older than this => view is stale
    bool    have_time_sensitive_action = false; // a pending claim/refund near a deadline
};

RpcRecovery DecideRpcRecovery(const RpcHealthInput& in);

// -----------------------------------------------------------------------------
// 6. Truthful per-asset EVM support matrix
// -----------------------------------------------------------------------------
//
// Classification of what the AtomicSwapHTLC contract can ACTUALLY do for the
// EVM counterparty leg, so no config over-claims support. SOST is the native
// consensus leg and is not classified here (it is the always-present side).

enum class EvmAssetStatus : uint8_t {
    Disabled,    // mechanically broken / unsupported — do NOT offer
    Testing,     // mechanically supported + unit-tested, NOT yet audited/deployed/E2E
    Available    // production-ready: audited + deployed + on-chain E2E verified
};
const char* EvmAssetStatusName(EvmAssetStatus s);

// The EVM-side status for a counterparty asset (pass the non-SOST leg).
EvmAssetStatus EvmAssetStatusFor(Asset a);
// Human-readable reason / caveat for the classification.
std::string EvmAssetStatusReason(Asset a);

}  // namespace policy
}  // namespace atomic_swap
}  // namespace sost
