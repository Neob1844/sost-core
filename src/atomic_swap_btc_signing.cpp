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

#include <string>

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
extern "C" {
#include <wally_core.h>
#include <wally_crypto.h>
}
#endif

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

// =============================================================================
// Phase C.5 — libwally-backed leaf helpers (test-vector scope only)
// =============================================================================
//
// These three helpers are the first piece of the BTC signing backend
// that performs real cryptographic work in production source. They
// stay fail-closed when SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY is not
// defined (the default build path), and call libwally directly when
// it is. None of them touches a wallet, an RPC, or a network socket.
// None of them constructs a Bitcoin transaction. They are
// pure-function leaf operations (key derivation, ECDSA sign, ECDSA
// verify) over caller-supplied test inputs.

namespace {

BtcBytesResult disabled_bytes_result() {
    BtcBytesResult r;
    r.ok = false;
    r.error = BtcSigningDisabledErrorMessage();
    r.bytes.clear();
    return r;
}

BtcVerifyResult disabled_verify_result() {
    BtcVerifyResult r;
    r.ok = false;
    r.error = BtcSigningDisabledErrorMessage();
    return r;
}

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
// Idempotent and thread-safe per libwally's documentation. We call it
// once per public entry point so callers do not need to remember to
// initialise the library before using these helpers.
void ensure_wally_init() {
    static bool initialised = false;
    if (!initialised) {
        wally_init(0);
        initialised = true;
    }
}
#endif

}  // namespace

BtcBytesResult DeriveBtcCompressedPubkey(
    const std::array<uint8_t, 32>& private_key)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    ensure_wally_init();
    BtcBytesResult r;
    // wally_ec_private_key_verify returns WALLY_OK only for keys in
    // the secp256k1 scalar range. An all-zero key is rejected here,
    // not at the signing step, so the error message is unambiguous.
    int rc = wally_ec_private_key_verify(
        private_key.data(), private_key.size());
    if (rc != 0) {
        r.ok = false;
        r.error = "DeriveBtcCompressedPubkey: invalid secp256k1 "
                  "private key (rc=" + std::to_string(rc) + ")";
        return r;
    }
    r.bytes.resize(EC_PUBLIC_KEY_LEN);
    rc = wally_ec_public_key_from_private_key(
        private_key.data(), private_key.size(),
        r.bytes.data(), r.bytes.size());
    if (rc != 0) {
        r.ok = false;
        r.bytes.clear();
        r.error = "DeriveBtcCompressedPubkey: "
                  "wally_ec_public_key_from_private_key failed (rc="
                  + std::to_string(rc) + ")";
        return r;
    }
    r.ok = true;
    return r;
#else
    (void)private_key;
    return disabled_bytes_result();
#endif
}

BtcBytesResult SignBtcEcdsaTestVector(
    const std::array<uint8_t, 32>& private_key,
    const uint8_t* sighash32,
    std::size_t    sighash32_len)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    ensure_wally_init();
    BtcBytesResult r;
    if (sighash32 == nullptr || sighash32_len != 32) {
        r.ok = false;
        r.error = "SignBtcEcdsaTestVector: sighash must be exactly 32 "
                  "bytes (got " + std::to_string(sighash32_len) + ")";
        return r;
    }
    // Pre-check the private key so the error path is the same as
    // DeriveBtcCompressedPubkey: a meaningful message instead of a
    // generic sign failure.
    int rc = wally_ec_private_key_verify(
        private_key.data(), private_key.size());
    if (rc != 0) {
        r.ok = false;
        r.error = "SignBtcEcdsaTestVector: invalid secp256k1 private "
                  "key (rc=" + std::to_string(rc) + ")";
        return r;
    }
    // Sign with EC_FLAG_ECDSA + EC_FLAG_GRIND_R. The GRIND_R flag
    // enforces Low-R / Low-S deterministic output, so signing the
    // same key+message twice produces identical bytes — a property
    // the Phase C.5 test verifies.
    unsigned char compact[EC_SIGNATURE_LEN] = {0};
    rc = wally_ec_sig_from_bytes(
        private_key.data(), private_key.size(),
        sighash32, sighash32_len,
        EC_FLAG_ECDSA | EC_FLAG_GRIND_R,
        compact, sizeof(compact));
    if (rc != 0) {
        r.ok = false;
        r.error = "SignBtcEcdsaTestVector: wally_ec_sig_from_bytes "
                  "failed (rc=" + std::to_string(rc) + ")";
        return r;
    }
    unsigned char der[EC_SIGNATURE_DER_MAX_LEN] = {0};
    std::size_t   der_len = 0;
    rc = wally_ec_sig_to_der(
        compact, sizeof(compact),
        der, sizeof(der), &der_len);
    if (rc != 0 || der_len == 0 || der_len > EC_SIGNATURE_DER_MAX_LEN) {
        r.ok = false;
        r.error = "SignBtcEcdsaTestVector: wally_ec_sig_to_der "
                  "failed (rc=" + std::to_string(rc) + ", len="
                  + std::to_string(der_len) + ")";
        return r;
    }
    r.bytes.assign(der, der + der_len);
    r.ok = true;
    return r;
#else
    (void)private_key;
    (void)sighash32;
    (void)sighash32_len;
    return disabled_bytes_result();
#endif
}

BtcVerifyResult VerifyBtcEcdsaTestVector(
    const uint8_t* pub,     std::size_t pub_len,
    const uint8_t* msg,     std::size_t msg_len,
    const uint8_t* der_sig, std::size_t der_sig_len)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    ensure_wally_init();
    BtcVerifyResult r;
    if (pub == nullptr || msg == nullptr || der_sig == nullptr) {
        r.ok = false;
        r.error = "VerifyBtcEcdsaTestVector: null input pointer";
        return r;
    }
    if (msg_len != 32) {
        r.ok = false;
        r.error = "VerifyBtcEcdsaTestVector: message must be 32 bytes "
                  "(got " + std::to_string(msg_len) + ")";
        return r;
    }
    // wally_ec_sig_verify wants the 64-byte compact form, so convert
    // from DER first.
    unsigned char compact[EC_SIGNATURE_LEN] = {0};
    int rc = wally_ec_sig_from_der(
        der_sig, der_sig_len,
        compact, sizeof(compact));
    if (rc != 0) {
        r.ok = false;
        r.error = "VerifyBtcEcdsaTestVector: wally_ec_sig_from_der "
                  "failed (rc=" + std::to_string(rc) + ")";
        return r;
    }
    rc = wally_ec_sig_verify(
        pub, pub_len,
        msg, msg_len,
        EC_FLAG_ECDSA,
        compact, sizeof(compact));
    if (rc != 0) {
        r.ok = false;
        r.error = "VerifyBtcEcdsaTestVector: signature did NOT verify "
                  "(rc=" + std::to_string(rc) + ")";
        return r;
    }
    r.ok = true;
    return r;
#else
    (void)pub;
    (void)pub_len;
    (void)msg;
    (void)msg_len;
    (void)der_sig;
    (void)der_sig_len;
    return disabled_verify_result();
#endif
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
