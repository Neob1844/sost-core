// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC counterparty — signing backend wrapper (Phase 4A-1)
// =============================================================================
//
// THIS HEADER DECLARES THE API. THE IMPLEMENTATION IS DISABLED.
//
// All functions in this module return BtcSigningResult{ok=false,
// error="BTC HTLC signing backend disabled"} unless the CMake option
// SOST_BTC_HTLC_SIGNING=ON is set AND a real signing backend has been
// integrated. By default the flag is OFF and no real signing,
// broadcasting, or fund movement is possible through this module.
//
// The decision rationale and the library selection plan are documented
// in docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md. Summary:
//
//   - Writing BIP-143 sighash + Bech32 + SegWit v0 tx serialization
//     from scratch is the most fund-loss-prone path in the entire
//     atomic-swap stack. A single byte wrong in the sighash domain
//     separation, or a single polymod miscalculation in Bech32, can
//     silently route funds to an address the user does not control.
//
//   - Vendoring an audited Bitcoin library (libbitcoin-system or
//     equivalent) is the responsible path. That integration is a
//     dedicated sprint of its own, not casual scaffolding work, and
//     requires external cryptographic review BEFORE the flag flips
//     to ON.
//
//   - This module's purpose right now is to FIX the public API
//     surface so future integration is a drop-in (replace the stubs
//     with library calls behind the SOST_BTC_HTLC_SIGNING=ON guard)
//     and so the wallet / coordinator layers can be written against
//     a stable interface that fails closed when the backend is
//     disabled.
//
// The atomic-swap activation gate
// (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT in include/sost/atomic_swap.h)
// remains at INT64_MAX (sentinel OFF) regardless of the value of
// SOST_BTC_HTLC_SIGNING. A future activation flip requires BOTH gates
// open AND external review sign-off.
// =============================================================================
#pragma once

#include "sost/types.h"
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// Result of any signing-backend call. On ok==false, the error string
// describes why; raw_tx_hex is empty.
struct BtcSigningResult {
    bool        ok = false;
    std::string error;
    std::string raw_tx_hex;   // hex of the signed BTC transaction on ok
};

// Returns true iff the build was compiled with SOST_BTC_HTLC_SIGNING=ON
// AND a real signing backend has been wired through. With the flag
// OFF (default) this returns false and every other function in this
// module returns BtcSigningResult{ok=false, error="...disabled..."}.
bool IsBtcHtlcSigningEnabled();

// Convenience: the disabled-error message used by every gated stub.
inline std::string BtcSigningDisabledErrorMessage() {
    return "BTC HTLC signing backend disabled. "
           "Build with -DSOST_BTC_HTLC_SIGNING=ON and integrate an "
           "audited Bitcoin signing library. See "
           "docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md for the "
           "library selection plan and audit requirements.";
}

// -----------------------------------------------------------------------------
// CLAIM signing — gated, currently stub.
// -----------------------------------------------------------------------------
//
// Builds and signs a Bitcoin tx that spends the P2WSH HTLC output via
// the claim path (revealing the preimage). Inputs:
//   - lock_txid                : the funding tx that created the P2WSH UTXO
//   - lock_vout                : output index of the HTLC UTXO
//   - lock_amount_sats         : amount locked (for sighash calculation)
//   - redeem_script            : the HTLC redeem script bytes
//   - preimage                 : 32-byte secret revealing the hashlock
//   - claim_privkey            : 32-byte secp256k1 private key for the
//                                 claim_pubkey embedded in the redeem script
//   - claim_destination_addr   : Bech32 address where the claimed
//                                 BTC should land (P2WPKH typically)
//   - fee_sats                 : transaction fee in satoshis
//   - bitcoin_network          : "mainnet" | "testnet" | "regtest"
//                                 (affects address encoding + magic bytes)
//
// Returns BtcSigningResult{ok=true, raw_tx_hex="..."} on success, or
// BtcSigningResult{ok=false, error="..."} if the backend is disabled
// or any input is invalid.
BtcSigningResult SignBtcHtlcClaim(
    const Bytes32& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount_sats,
    const std::vector<uint8_t>& redeem_script,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 32>& claim_privkey,
    const std::string& claim_destination_addr,
    int64_t fee_sats,
    const std::string& bitcoin_network);

// -----------------------------------------------------------------------------
// REFUND signing — gated, currently stub.
// -----------------------------------------------------------------------------
//
// Builds and signs a Bitcoin tx that spends the P2WSH HTLC output via
// the refund path (after timeout). Same input shape as claim but with
// refund_privkey and nLockTime set to the refund_height embedded in
// the redeem script.
BtcSigningResult SignBtcHtlcRefund(
    const Bytes32& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount_sats,
    const std::vector<uint8_t>& redeem_script,
    int64_t refund_height,
    const std::array<uint8_t, 32>& refund_privkey,
    const std::string& refund_destination_addr,
    int64_t fee_sats,
    const std::string& bitcoin_network);

// -----------------------------------------------------------------------------
// LOCK funding tx signing — gated, currently stub.
// -----------------------------------------------------------------------------
//
// Builds and signs the funding transaction that places `amount_sats`
// into the HTLC's P2WSH output. The wallet supplies the prevout to
// spend from (a UTXO it owns) and the funder's privkey.
BtcSigningResult SignBtcHtlcLockFunding(
    const Bytes32& prev_txid,
    uint32_t prev_vout,
    int64_t prev_amount_sats,
    const std::array<uint8_t, 32>& funder_privkey,
    const std::string& funder_change_addr,
    const std::vector<uint8_t>& redeem_script,
    int64_t lock_amount_sats,
    int64_t fee_sats,
    const std::string& bitcoin_network);

// -----------------------------------------------------------------------------
// Bech32 address encoding — gated, currently stub.
// -----------------------------------------------------------------------------
//
// Encodes a P2WSH witness program (32-byte sha256 of the redeem
// script) as a Bech32 segwit-v0 address. Network HRP:
//   mainnet -> "bc"
//   testnet -> "tb"
//   regtest -> "bcrt"
//
// With the signing backend disabled the address derivation is also
// disabled (it would otherwise require pulling in the Bech32 polymod
// which is in the same audit envelope).
struct BtcAddressResult {
    bool        ok = false;
    std::string error;
    std::string address;
};

BtcAddressResult EncodeP2WSHAddress(
    const std::array<uint8_t, 32>& witness_program,
    const std::string& bitcoin_network);

// =============================================================================
// Phase C.5 — minimal libwally-backed helpers (TEST VECTOR ONLY)
// =============================================================================
//
// The three helpers below are the first piece of the BTC signing backend
// that actually does cryptographic work in production source (vs the
// disabled stubs of the four functions above). They are deliberately
// named "TestVector" and exposed as small leaf operations rather than
// "Sign a real swap" so a caller cannot mistake them for a mainnet path.
//
// Behaviour:
//   - SOST_BTC_HTLC_SIGNING=OFF (default build): every helper returns
//     ok=false with the same disabled-error string as the four legacy
//     stubs. The functions exist in the binary but are inert.
//   - SOST_BTC_HTLC_SIGNING=ON AND libwally present (the macro
//     SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY is defined on sost-core):
//     real libwally calls are made; pubkey is derived, sighash is
//     signed with ECDSA Low-R (EC_FLAG_GRIND_R), signature is verified
//     against the pubkey.
//
// What these helpers do NOT do:
//   - Read any wallet file, touch any RPC, broadcast anything.
//   - Build a Bitcoin transaction (no raw tx assembly, no PSBT, no
//     witness stack construction).
//   - Move the SOST consensus gate. ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT
//     stays INT64_MAX regardless.
//   - Touch the four legacy stubs SignBtcHtlcClaim / Refund /
//     LockFunding / EncodeP2WSHAddress. Those stay disabled until a
//     later phase wires them on top of these helpers.
//
// Test-vector reference key pair (used by tests; published in BIP-143
// §"Native P2WSH" P2PK input):
//   priv: b8f28a772fccbf9b4f58a4f027e07dc2e35e7cd80529975e292ea34f84c4580c
//   pub:  036d5c20fa14fb2f635474c1dc4ef5909d4568e5569b79fc94d3448486e14685f8
// Anyone reproducing the build can derive the published pubkey from
// the published privkey via DeriveBtcCompressedPubkey and verify the
// match end-to-end without any external dependency beyond the
// vendored libwally.

// Raw-bytes result for helpers that produce keys or signatures.
struct BtcBytesResult {
    bool                 ok = false;
    std::string          error;
    std::vector<uint8_t> bytes;  // 33-byte pubkey, or DER signature, etc.
};

// Yes/no result for verify-style helpers. ok=true means the signature
// verified; ok=false with error populated means it did not.
struct BtcVerifyResult {
    bool        ok = false;
    std::string error;
};

// Derive the 33-byte compressed secp256k1 public key from a 32-byte
// private key. Inert when SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY is not
// defined.
BtcBytesResult DeriveBtcCompressedPubkey(
    const std::array<uint8_t, 32>& private_key);

// Sign a 32-byte message hash with ECDSA over secp256k1, returning the
// DER-encoded signature. Uses EC_FLAG_GRIND_R so the output is
// deterministic Low-R / Low-S. Inert when libwally is not present.
// sighash32_len MUST be 32; any other value is rejected with ok=false.
BtcBytesResult SignBtcEcdsaTestVector(
    const std::array<uint8_t, 32>& private_key,
    const uint8_t* sighash32,
    std::size_t    sighash32_len);

// Verify a DER-encoded ECDSA signature against a public key and a
// message hash. ok=true iff the signature matches. Inert when
// libwally is not present.
BtcVerifyResult VerifyBtcEcdsaTestVector(
    const uint8_t* pub,         std::size_t pub_len,
    const uint8_t* msg,         std::size_t msg_len,
    const uint8_t* der_sig,     std::size_t der_sig_len);

// =============================================================================
// Phase C.6 — witness assembly + spending-tx builders (LAB ONLY)
// =============================================================================
//
// These helpers compose the C.5 ECDSA primitives into the actual
// transaction-level building blocks needed to spend a P2WSH HTLC.
// They are pure functions over caller-supplied inputs: no wallet
// access, no network IO, no broadcast. SOST_BTC_HTLC_SIGNING=OFF
// keeps them inert (fail-closed).

// A SegWit witness stack — an ordered list of byte strings that the
// witness program executes against. Element 0 is pushed first.
struct BtcWitnessResult {
    bool                              ok = false;
    std::string                       error;
    std::vector<std::vector<uint8_t>> stack;
};

// Assemble the witness stack for spending a SOST-shaped HTLC P2WSH
// via the CLAIM branch (OP_IF). The redeem script matches
// BuildBtcHtlcRedeemScript:
//
//   OP_IF OP_SHA256 <hashlock> OP_EQUALVERIFY <claim_pub> OP_CHECKSIG
//   OP_ELSE <refund_height> OP_CHECKLOCKTIMEVERIFY OP_DROP
//           <refund_pub> OP_CHECKSIG OP_ENDIF
//
// Witness stack for CLAIM (4 items):
//   [0] DER signature || sighash_type_byte
//   [1] preimage (32 bytes — sha256(preimage) must equal <hashlock>)
//   [2] non-empty truthy byte (0x01) selecting the OP_IF branch
//   [3] redeem_script (caller's BuildBtcHtlcRedeemScript output)
//
// The helper validates lengths but does NOT verify the signature or
// the preimage's match against the script's hashlock — those are the
// caller's responsibility.
BtcWitnessResult BuildBtcHtlcClaimWitness(
    const std::vector<uint8_t>&    der_sig_with_sighash,
    const std::array<uint8_t, 32>& preimage,
    const std::vector<uint8_t>&    redeem_script);

// Witness stack for REFUND (3 items):
//   [0] DER signature || sighash_type_byte
//   [1] empty byte string (selects the OP_ELSE branch)
//   [2] redeem_script
//
// The caller is responsible for setting the spending tx nLockTime to
// >= the refund_height encoded in the redeem script; otherwise
// OP_CHECKLOCKTIMEVERIFY will fail at script execution time on a
// full Bitcoin node.
BtcWitnessResult BuildBtcHtlcRefundWitness(
    const std::vector<uint8_t>& der_sig_with_sighash,
    const std::vector<uint8_t>& redeem_script);

// Build a one-input / one-output unsigned segwit spending tx using
// libwally. The input has empty scriptSig and is left witness-empty
// (witness is attached later via the BuildBtcHtlc{Claim,Refund}Witness
// helpers above). Inputs are sanity-checked: amount must be positive,
// fee must be strictly less than amount, prev_txid must be 32 bytes,
// output scriptPubKey must be non-empty.
//
// Returned bytes = raw hex of the unsigned tx (lowercase, NUL-trimmed).
// Inert when SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY is not defined.
BtcBytesResult BuildBtcSpendingTxUnsignedHex(
    const std::array<uint8_t, 32>& prev_txid,
    uint32_t                       prev_vout,
    int64_t                        prev_amount_sats,
    const std::vector<uint8_t>&    output_script_pubkey,
    int64_t                        fee_sats,
    uint32_t                       input_sequence,
    uint32_t                       lock_time);

} // namespace btc
} // namespace atomic_swap
} // namespace sost
