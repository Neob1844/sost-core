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
#include <wally_address.h>
#include <wally_transaction.h>
}
#include <cstring>
#include <vector>
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

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
// Phase C.7 internal — convert "mainnet"/"testnet"/"regtest" to the
// Bech32 HRP libwally expects. Returns nullptr on unknown.
namespace {
// Forward-declared: defined later in the Phase C.5 anonymous namespace.
// Needed here so the sign_p2wsh_spend template body can reference it.
void ensure_wally_init();

static const char* hrp_for_network(const std::string& n) {
    if (n == "mainnet") return "bc";
    if (n == "testnet") return "tb";
    if (n == "regtest") return "bcrt";
    return nullptr;
}

// Phase C.7 internal — compose C.5+C.6 primitives into a signed
// P2WSH-spending tx. Used by both SignBtcHtlcClaim (witness builder =
// claim, locktime = 0, sequence = 0xFFFFFFFE) and SignBtcHtlcRefund
// (witness builder = refund, locktime = refund_height, sequence =
// 0xFFFFFFFE so CLTV enforcement engages). The witness builder
// callback is passed in so this helper does not have to know about
// the preimage vs. no-preimage distinction.
//
// All inputs are validated; on any failure the partially-allocated
// libwally state is cleaned up before returning.
template <typename WitnessBuilder>
BtcSigningResult sign_p2wsh_spend(
    const Bytes32& lock_txid,
    uint32_t       lock_vout,
    int64_t        lock_amount_sats,
    const std::vector<uint8_t>&    redeem_script,
    const std::array<uint8_t, 32>& signer_privkey,
    const std::string& destination_addr,
    int64_t        fee_sats,
    const std::string& bitcoin_network,
    uint32_t       sequence,
    uint32_t       locktime,
    WitnessBuilder build_witness)
{
    ensure_wally_init();
    BtcSigningResult r;

    if (lock_amount_sats <= 0) {
        r.error = "lock_amount_sats must be > 0";
        return r;
    }
    if (fee_sats < 0) {
        r.error = "fee_sats must be >= 0";
        return r;
    }
    if (fee_sats >= lock_amount_sats) {
        r.error = "fee_sats must be < lock_amount_sats";
        return r;
    }
    if (redeem_script.empty()) {
        r.error = "redeem_script is empty";
        return r;
    }
    if (wally_ec_private_key_verify(signer_privkey.data(), 32) != 0) {
        r.error = "invalid secp256k1 private key";
        return r;
    }
    const char* hrp = hrp_for_network(bitcoin_network);
    if (!hrp) {
        r.error = "unsupported bitcoin_network '" + bitcoin_network +
                  "' (expect mainnet|testnet|regtest)";
        return r;
    }

    // Address -> scriptPubKey (segwit script: OP_0 + push + program).
    unsigned char dest_spk[WALLY_SEGWIT_ADDRESS_PUBKEY_MAX_LEN];
    std::size_t   dest_spk_len = 0;
    int rc = wally_addr_segwit_to_bytes(
        destination_addr.c_str(), hrp, 0,
        dest_spk, sizeof(dest_spk), &dest_spk_len);
    if (rc != 0) {
        r.error = "destination_addr does not decode as a segwit address "
                  "for network '" + bitcoin_network + "' (rc=" +
                  std::to_string(rc) + ")";
        return r;
    }

    struct wally_tx* tx = nullptr;
    rc = wally_tx_init_alloc(2, locktime, 1, 1, &tx);
    if (rc != 0 || tx == nullptr) {
        r.error = "wally_tx_init_alloc failed";
        return r;
    }
    rc = wally_tx_add_raw_input(
        tx, lock_txid.data(), lock_txid.size(),
        lock_vout, sequence,
        nullptr, 0,    // empty scriptSig (segwit)
        nullptr, 0);   // witness attached later
    if (rc != 0) {
        wally_tx_free(tx);
        r.error = "wally_tx_add_raw_input failed";
        return r;
    }
    int64_t output_amount = lock_amount_sats - fee_sats;
    rc = wally_tx_add_raw_output(
        tx, (uint64_t)output_amount,
        dest_spk, dest_spk_len, 0);
    if (rc != 0) {
        wally_tx_free(tx);
        r.error = "wally_tx_add_raw_output failed";
        return r;
    }

    // BIP-143 sighash on input 0; scriptCode = the full redeem script.
    unsigned char sighash[32];
    rc = wally_tx_get_btc_signature_hash(
        tx, 0,
        redeem_script.data(), redeem_script.size(),
        (uint64_t)lock_amount_sats,
        WALLY_SIGHASH_ALL,
        WALLY_TX_FLAG_USE_WITNESS,
        sighash, sizeof(sighash));
    if (rc != 0) {
        wally_tx_free(tx);
        r.error = "wally_tx_get_btc_signature_hash failed";
        return r;
    }

    auto sig_r = SignBtcEcdsaTestVector(signer_privkey, sighash, sizeof(sighash));
    if (!sig_r.ok) {
        wally_tx_free(tx);
        r.error = "sign_p2wsh_spend: " + sig_r.error;
        return r;
    }
    // Append sighash type byte (SIGHASH_ALL = 0x01) to the DER sig.
    std::vector<uint8_t> sig_with_type = sig_r.bytes;
    sig_with_type.push_back(0x01);

    auto wit_r = build_witness(sig_with_type, redeem_script);
    if (!wit_r.ok) {
        wally_tx_free(tx);
        r.error = "sign_p2wsh_spend: " + wit_r.error;
        return r;
    }

    struct wally_tx_witness_stack* witness = nullptr;
    rc = wally_tx_witness_stack_init_alloc(wit_r.stack.size(), &witness);
    if (rc != 0 || witness == nullptr) {
        wally_tx_free(tx);
        r.error = "wally_tx_witness_stack_init_alloc failed";
        return r;
    }
    for (const auto& item : wit_r.stack) {
        rc = wally_tx_witness_stack_add(
            witness,
            item.empty() ? nullptr : item.data(), item.size());
        if (rc != 0) {
            wally_tx_witness_stack_free(witness);
            wally_tx_free(tx);
            r.error = "wally_tx_witness_stack_add failed";
            return r;
        }
    }
    rc = wally_tx_set_input_witness(tx, 0, witness);
    if (rc != 0) {
        wally_tx_witness_stack_free(witness);
        wally_tx_free(tx);
        r.error = "wally_tx_set_input_witness failed";
        return r;
    }

    char* tx_hex = nullptr;
    rc = wally_tx_to_hex(tx, WALLY_TX_FLAG_USE_WITNESS, &tx_hex);
    if (rc != 0 || tx_hex == nullptr) {
        wally_tx_witness_stack_free(witness);
        wally_tx_free(tx);
        r.error = "wally_tx_to_hex failed";
        return r;
    }
    r.raw_tx_hex = tx_hex;
    r.ok = true;

    wally_free_string(tx_hex);
    wally_tx_witness_stack_free(witness);
    wally_tx_free(tx);
    return r;
}
}  // namespace
#endif

BtcSigningResult SignBtcHtlcClaim(
    const Bytes32& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount_sats,
    const std::vector<uint8_t>& redeem_script,
    const std::array<uint8_t, 32>& preimage,
    const std::array<uint8_t, 32>& claim_privkey,
    const std::string& claim_destination_addr,
    int64_t fee_sats,
    const std::string& bitcoin_network)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    // Capture preimage by copy so the lambda closure outlives the call.
    auto preimage_copy = preimage;
    return sign_p2wsh_spend(
        lock_txid, lock_vout, lock_amount_sats,
        redeem_script, claim_privkey,
        claim_destination_addr, fee_sats, bitcoin_network,
        /* sequence = */ 0xFFFFFFFE,
        /* locktime = */ 0,
        [&preimage_copy](const std::vector<uint8_t>& sig_with_type,
                         const std::vector<uint8_t>& script) {
            return BuildBtcHtlcClaimWitness(sig_with_type, preimage_copy, script);
        });
#else
    (void)lock_txid; (void)lock_vout; (void)lock_amount_sats;
    (void)redeem_script; (void)preimage; (void)claim_privkey;
    (void)claim_destination_addr; (void)fee_sats; (void)bitcoin_network;
    return disabled_result();
#endif
}

BtcSigningResult SignBtcHtlcRefund(
    const Bytes32& lock_txid,
    uint32_t lock_vout,
    int64_t lock_amount_sats,
    const std::vector<uint8_t>& redeem_script,
    int64_t refund_height,
    const std::array<uint8_t, 32>& refund_privkey,
    const std::string& refund_destination_addr,
    int64_t fee_sats,
    const std::string& bitcoin_network)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    if (refund_height < 0 || refund_height > (int64_t)UINT32_MAX) {
        BtcSigningResult r;
        r.error = "refund_height out of range for uint32 locktime";
        return r;
    }
    return sign_p2wsh_spend(
        lock_txid, lock_vout, lock_amount_sats,
        redeem_script, refund_privkey,
        refund_destination_addr, fee_sats, bitcoin_network,
        /* sequence = */ 0xFFFFFFFE,            // < 0xFFFFFFFF -> CLTV active
        /* locktime = */ (uint32_t)refund_height,
        [](const std::vector<uint8_t>& sig_with_type,
           const std::vector<uint8_t>& script) {
            return BuildBtcHtlcRefundWitness(sig_with_type, script);
        });
#else
    (void)lock_txid; (void)lock_vout; (void)lock_amount_sats;
    (void)redeem_script; (void)refund_height; (void)refund_privkey;
    (void)refund_destination_addr; (void)fee_sats; (void)bitcoin_network;
    return disabled_result();
#endif
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
    const std::array<uint8_t, 32>& witness_program,
    const std::string& bitcoin_network)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    BtcAddressResult r;
    const char* hrp = nullptr;
    if (bitcoin_network == "mainnet")      hrp = "bc";
    else if (bitcoin_network == "testnet") hrp = "tb";
    else if (bitcoin_network == "regtest") hrp = "bcrt";
    else {
        r.ok = false;
        r.error = "EncodeP2WSHAddress: unsupported bitcoin_network '"
                  + bitcoin_network + "' (expect mainnet|testnet|regtest)";
        return r;
    }
    // libwally takes the full segwit SCRIPT: OP_0 + push(32) + program.
    unsigned char segwit_script[34];
    segwit_script[0] = 0x00;  // OP_0 (witness version 0)
    segwit_script[1] = 0x20;  // push 32 bytes
    std::memcpy(segwit_script + 2, witness_program.data(), 32);
    char* addr = nullptr;
    int rc = wally_addr_segwit_from_bytes(
        segwit_script, sizeof(segwit_script), hrp, 0, &addr);
    if (rc != 0 || addr == nullptr) {
        r.ok = false;
        r.error = "EncodeP2WSHAddress: wally_addr_segwit_from_bytes failed (rc="
                  + std::to_string(rc) + ")";
        return r;
    }
    r.address = addr;
    wally_free_string(addr);
    r.ok = true;
    return r;
#else
    (void)witness_program;
    (void)bitcoin_network;
    return disabled_address_result();
#endif
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

// =============================================================================
// Phase C.6 — witness assembly + spending-tx builders (LAB ONLY)
// =============================================================================
//
// Compose the C.5 leaf primitives into transaction-level building
// blocks. Pure functions over caller inputs: no wallet, no network,
// no broadcast. Fail-closed when libwally is not present.

namespace {

BtcWitnessResult disabled_witness_result() {
    BtcWitnessResult r;
    r.ok = false;
    r.error = BtcSigningDisabledErrorMessage();
    r.stack.clear();
    return r;
}

}  // namespace

BtcWitnessResult BuildBtcHtlcClaimWitness(
    const std::vector<uint8_t>&    der_sig_with_sighash,
    const std::array<uint8_t, 32>& preimage,
    const std::vector<uint8_t>&    redeem_script)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    BtcWitnessResult r;
    // The signature must already carry the sighash type byte appended
    // (e.g. SIGHASH_ALL = 0x01) per BIP-66 + BIP-143 conventions. We
    // do not strip or append it here; the caller controls the byte.
    if (der_sig_with_sighash.empty() || der_sig_with_sighash.size() > 73) {
        r.ok = false;
        r.error = "BuildBtcHtlcClaimWitness: DER signature length out of "
                  "range (got " + std::to_string(der_sig_with_sighash.size())
                  + ", expected 1..73 incl. sighash byte)";
        return r;
    }
    if (redeem_script.empty()) {
        r.ok = false;
        r.error = "BuildBtcHtlcClaimWitness: empty redeem script";
        return r;
    }
    // Stack ordering for the SOST HTLC redeem script:
    //   [0] sig+sighash    -> consumed by OP_CHECKSIG inside OP_IF
    //   [1] preimage       -> hashed by OP_SHA256 + OP_EQUALVERIFY
    //   [2] 0x01           -> truthy value taken by OP_IF
    //   [3] redeem_script  -> the witness program preimage
    r.stack.reserve(4);
    r.stack.push_back(der_sig_with_sighash);
    r.stack.push_back(std::vector<uint8_t>(preimage.begin(), preimage.end()));
    r.stack.push_back(std::vector<uint8_t>{0x01});
    r.stack.push_back(redeem_script);
    r.ok = true;
    return r;
#else
    (void)der_sig_with_sighash;
    (void)preimage;
    (void)redeem_script;
    return disabled_witness_result();
#endif
}

BtcWitnessResult BuildBtcHtlcRefundWitness(
    const std::vector<uint8_t>& der_sig_with_sighash,
    const std::vector<uint8_t>& redeem_script)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    BtcWitnessResult r;
    if (der_sig_with_sighash.empty() || der_sig_with_sighash.size() > 73) {
        r.ok = false;
        r.error = "BuildBtcHtlcRefundWitness: DER signature length out of "
                  "range (got " + std::to_string(der_sig_with_sighash.size())
                  + ", expected 1..73 incl. sighash byte)";
        return r;
    }
    if (redeem_script.empty()) {
        r.ok = false;
        r.error = "BuildBtcHtlcRefundWitness: empty redeem script";
        return r;
    }
    // Stack ordering for the SOST HTLC redeem script:
    //   [0] sig+sighash    -> consumed by OP_CHECKSIG inside OP_ELSE
    //   [1] empty          -> falsy value selects OP_ELSE
    //   [2] redeem_script
    r.stack.reserve(3);
    r.stack.push_back(der_sig_with_sighash);
    r.stack.push_back(std::vector<uint8_t>{});  // empty -> false
    r.stack.push_back(redeem_script);
    r.ok = true;
    return r;
#else
    (void)der_sig_with_sighash;
    (void)redeem_script;
    return disabled_witness_result();
#endif
}

BtcBytesResult BuildBtcSpendingTxUnsignedHex(
    const std::array<uint8_t, 32>& prev_txid,
    uint32_t                       prev_vout,
    int64_t                        prev_amount_sats,
    const std::vector<uint8_t>&    output_script_pubkey,
    int64_t                        fee_sats,
    uint32_t                       input_sequence,
    uint32_t                       lock_time)
{
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    ensure_wally_init();
    BtcBytesResult r;
    // Sanity-check inputs before allocating any libwally state.
    if (prev_amount_sats <= 0) {
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: prev_amount_sats must be > 0 "
                  "(got " + std::to_string(prev_amount_sats) + ")";
        return r;
    }
    if (fee_sats < 0) {
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: fee_sats must be >= 0 "
                  "(got " + std::to_string(fee_sats) + ")";
        return r;
    }
    if (fee_sats >= prev_amount_sats) {
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: fee_sats ("
                  + std::to_string(fee_sats) + ") must be strictly less than "
                  "prev_amount_sats (" + std::to_string(prev_amount_sats) + ")";
        return r;
    }
    if (output_script_pubkey.empty()) {
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: output_script_pubkey is empty";
        return r;
    }

    struct wally_tx* tx = nullptr;
    // version 2 (BIP-68 required for CHECKSEQUENCEVERIFY; harmless
    // for CHECKLOCKTIMEVERIFY); input/output counts grow with add().
    int rc = wally_tx_init_alloc(2 /* version */, lock_time, 1, 1, &tx);
    if (rc != 0 || tx == nullptr) {
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: wally_tx_init_alloc failed "
                  "(rc=" + std::to_string(rc) + ")";
        return r;
    }
    // BIP-143 segwit input: empty scriptSig, witness attached separately.
    rc = wally_tx_add_raw_input(
        tx,
        prev_txid.data(), prev_txid.size(),
        prev_vout,
        input_sequence,
        nullptr, 0,   // scriptSig (empty)
        nullptr,      // witness (NULL -> tx remains witness-marked but stack empty)
        0);
    if (rc != 0) {
        wally_tx_free(tx);
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: wally_tx_add_raw_input failed "
                  "(rc=" + std::to_string(rc) + ")";
        return r;
    }
    int64_t output_amount = prev_amount_sats - fee_sats;
    rc = wally_tx_add_raw_output(
        tx,
        (uint64_t)output_amount,
        output_script_pubkey.data(), output_script_pubkey.size(),
        0);
    if (rc != 0) {
        wally_tx_free(tx);
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: wally_tx_add_raw_output failed "
                  "(rc=" + std::to_string(rc) + ")";
        return r;
    }
    char* tx_hex = nullptr;
    // Serialise without the witness section (the tx has empty witness
    // anyway; emit the legacy form so the bytes are exactly the
    // "to-be-signed" template that BIP-143 hashes over).
    rc = wally_tx_to_hex(tx, 0 /* flags */, &tx_hex);
    if (rc != 0 || tx_hex == nullptr) {
        wally_tx_free(tx);
        r.ok = false;
        r.error = "BuildBtcSpendingTxUnsignedHex: wally_tx_to_hex failed "
                  "(rc=" + std::to_string(rc) + ")";
        return r;
    }
    // Pack the hex into r.bytes (it is ascii, but the API surface uses
    // bytes; tests can decode if needed).
    r.bytes.assign(tx_hex, tx_hex + std::strlen(tx_hex));
    wally_free_string(tx_hex);
    wally_tx_free(tx);
    r.ok = true;
    return r;
#else
    (void)prev_txid;
    (void)prev_vout;
    (void)prev_amount_sats;
    (void)output_script_pubkey;
    (void)fee_sats;
    (void)input_sequence;
    (void)lock_time;
    return disabled_bytes_result();
#endif
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
