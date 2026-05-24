// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC signing backend — DISABLED STUB IMPLEMENTATION (Phase 4A-1)
// =============================================================================
//
// Every external function in this translation unit returns the
// "disabled" result. No signing is performed. No transactions are
// broadcast. No private keys are used (the privkey parameters are
// silently ignored after a fail-fast gate check). No network I/O.
// No file I/O.
//
// When SOST_BTC_HTLC_SIGNING is later flipped ON (a separate sprint
// that vendors libbitcoin-system or an equivalent audited library),
// these stubs are replaced one-by-one with the real implementations.
// The public API in include/sost/atomic_swap_btc_signing.h is the
// fixed contract; the wallet / coordinator layers should be written
// against it now so the future activation is a drop-in.
//
// See docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md for the
// library selection plan, the test-vector requirements, and the
// activation prerequisites.
// =============================================================================

#include "sost/atomic_swap_btc_signing.h"

namespace sost {
namespace atomic_swap {
namespace btc {

bool IsBtcHtlcSigningEnabled() {
    // The build flag SOST_BTC_HTLC_SIGNING controls this. When the
    // CMake option is ON, the build defines the macro
    // SOST_BTC_HTLC_SIGNING_ENABLED. With the option OFF (default)
    // the macro is undefined and this function returns false.
#ifdef SOST_BTC_HTLC_SIGNING_ENABLED
    // Even with the build flag ON, the function still returns false
    // until a real signing backend has been wired AND the operator
    // explicitly toggles a runtime acknowledgement. That runtime
    // toggle does NOT exist in this commit; activating it is part
    // of the future sprint that ships the real backend.
    return false;
#else
    return false;
#endif
}

// Common stub helpers ------------------------------------------------

namespace {
BtcSigningResult disabled_result() {
    BtcSigningResult r;
    r.ok = false;
    r.error = BtcSigningDisabledErrorMessage();
    r.raw_tx_hex.clear();
    return r;
}

BtcAddressResult disabled_address_result() {
    BtcAddressResult r;
    r.ok = false;
    r.error = BtcSigningDisabledErrorMessage();
    r.address.clear();
    return r;
}
}  // namespace

// Stub implementations ------------------------------------------------
//
// All parameters are accepted to fix the API surface, but none of
// them are used. The fail-fast check returns immediately. Privkey
// parameters in particular are NOT read, NOT copied, NOT logged.

BtcSigningResult SignBtcHtlcClaim(
    const Bytes32& /*lock_txid*/,
    uint32_t /*lock_vout*/,
    int64_t /*lock_amount_sats*/,
    const std::vector<uint8_t>& /*redeem_script*/,
    const std::array<uint8_t, 32>& /*preimage*/,
    const std::array<uint8_t, 32>& /*claim_privkey*/,
    const std::string& /*claim_destination_addr*/,
    int64_t /*fee_sats*/,
    const std::string& /*bitcoin_network*/)
{
    return disabled_result();
}

BtcSigningResult SignBtcHtlcRefund(
    const Bytes32& /*lock_txid*/,
    uint32_t /*lock_vout*/,
    int64_t /*lock_amount_sats*/,
    const std::vector<uint8_t>& /*redeem_script*/,
    int64_t /*refund_height*/,
    const std::array<uint8_t, 32>& /*refund_privkey*/,
    const std::string& /*refund_destination_addr*/,
    int64_t /*fee_sats*/,
    const std::string& /*bitcoin_network*/)
{
    return disabled_result();
}

BtcSigningResult SignBtcHtlcLockFunding(
    const Bytes32& /*prev_txid*/,
    uint32_t /*prev_vout*/,
    int64_t /*prev_amount_sats*/,
    const std::array<uint8_t, 32>& /*funder_privkey*/,
    const std::string& /*funder_change_addr*/,
    const std::vector<uint8_t>& /*redeem_script*/,
    int64_t /*lock_amount_sats*/,
    int64_t /*fee_sats*/,
    const std::string& /*bitcoin_network*/)
{
    return disabled_result();
}

BtcAddressResult EncodeP2WSHAddress(
    const std::array<uint8_t, 32>& /*witness_program*/,
    const std::string& /*bitcoin_network*/)
{
    return disabled_address_result();
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
