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

} // namespace btc
} // namespace atomic_swap
} // namespace sost
