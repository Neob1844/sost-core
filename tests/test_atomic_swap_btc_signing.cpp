// Phase 4A-1 — BTC signing backend disabled-stub tests.
//
// Verifies that with SOST_BTC_HTLC_SIGNING=OFF (default) the entire
// signing surface is inert: every function returns the disabled
// result, no transactions are produced, no addresses are derived, no
// private keys are touched. This is the safety guarantee while the
// real signing backend (vendored audited Bitcoin library) is not yet
// integrated.

#include "sost/atomic_swap_btc_signing.h"
#include "sost/atomic_swap.h"
#include "sost/atomic_swap_btc.h"   // Phase C.7: BuildBtcHtlcRedeemScript
#include "sost/crypto.h"            // Phase C.7: sost::sha256

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdint>
#include <climits>
#include <cstring>
#include <string>
#include <vector>

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
// Phase C.8 structural assertions parse the produced tx with libwally
// (output count / amounts / locktime / sequence). Guarded so the OFF
// build never references the vendored headers.
extern "C" {
#include <wally_core.h>
#include <wally_transaction.h>
}
#endif

using namespace sost;
using namespace sost::atomic_swap::btc;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

int main() {
    printf("\n== Atomic Swap BTC Signing Phase 4A-1 — disabled-stub tests ==\n\n");
    printf("  IsBtcHtlcSigningEnabled() = %s\n",
           IsBtcHtlcSigningEnabled() ? "true" : "false");
    printf("  ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = %lld (must be INT64_MAX)\n\n",
           (long long)ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT);

    // T1. The build flag is OFF by default.
    TEST("T1 IsBtcHtlcSigningEnabled() returns false (default OFF)",
         IsBtcHtlcSigningEnabled() == false);

    // T2. The activation gate is independent of the BTC signing flag. The gate is
    //     set to V14_5_HEIGHT (the V14.5 HTLC fix activation; EVM-only); the BTC
    //     signing flag stays OFF independently (BTC funding path is a stub).
    TEST("T2 SOST activation gate == V14_5_HEIGHT (BTC signing flag independent)",
         ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == V14_5_HEIGHT);

    // -----------------------------------------------------------------
    // Stub behavior — every gated function returns disabled result.
    // -----------------------------------------------------------------

    Bytes32 fake_txid{};
    fake_txid.fill(0xAB);
    std::array<uint8_t, 32> fake_preimage{};
    std::array<uint8_t, 32> fake_privkey{};   // deliberately zero — never read
    std::vector<uint8_t> fake_redeem_script(113, 0x63);  // arbitrary bytes
    std::string addr = "bc1qworlds_smallest_address";
    std::string network = "testnet";

    // T3. SignBtcHtlcClaim
    // Phase C.7 wired this stub. With INVALID inputs (fake_privkey is
    // all-zeros, which is outside the secp256k1 scalar range), it still
    // returns ok=false even in ON mode — but the error string is the
    // input-validation message, not "disabled". The happy-path
    // (T29-T35 below) covers the ON success branch.
    {
        auto r = SignBtcHtlcClaim(
            fake_txid, 0, 100000,
            fake_redeem_script, fake_preimage, fake_privkey,
            addr, 1000, network);
        TEST("T3 SignBtcHtlcClaim with invalid privkey returns ok=false",
             r.ok == false);
        TEST("T3 SignBtcHtlcClaim raw_tx_hex empty on failure",
             r.raw_tx_hex.empty());
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
        TEST("T3 SignBtcHtlcClaim error is a real validation message (ON)",
             !r.error.empty() &&
             r.error.find("disabled") == std::string::npos);
#else
        TEST("T3 SignBtcHtlcClaim error mentions 'disabled' (OFF)",
             r.error.find("disabled") != std::string::npos);
#endif
    }

    // T4. SignBtcHtlcRefund — same shape as T3.
    {
        auto r = SignBtcHtlcRefund(
            fake_txid, 0, 100000,
            fake_redeem_script, 15000, fake_privkey,
            addr, 1000, network);
        TEST("T4 SignBtcHtlcRefund with invalid privkey returns ok=false",
             r.ok == false);
        TEST("T4 SignBtcHtlcRefund raw_tx_hex empty on failure",
             r.raw_tx_hex.empty());
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
        TEST("T4 SignBtcHtlcRefund error is a real validation message (ON)",
             !r.error.empty() &&
             r.error.find("disabled") == std::string::npos);
#else
        TEST("T4 SignBtcHtlcRefund error mentions 'disabled' (OFF)",
             r.error.find("disabled") != std::string::npos);
#endif
    }

    // T5. SignBtcHtlcLockFunding
    // Phase C.8 wired this stub. With INVALID inputs (fake_privkey is
    // all-zeros, outside the secp256k1 scalar range), it returns ok=false
    // even in ON mode — but with the input-validation message, not
    // "disabled". The happy path (T40+ below) covers the ON success
    // branch. In OFF mode the whole function is the inert disabled stub.
    {
        auto r = SignBtcHtlcLockFunding(
            fake_txid, 0, 200000, fake_privkey, addr,
            fake_redeem_script, 100000, 1000, network);
        TEST("T5 SignBtcHtlcLockFunding returns ok=false", r.ok == false);
        TEST("T5 SignBtcHtlcLockFunding raw_tx_hex empty", r.raw_tx_hex.empty());
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
        TEST("T5 SignBtcHtlcLockFunding error is a real validation message (ON)",
             !r.error.empty() &&
             r.error.find("disabled") == std::string::npos);
#else
        TEST("T5 SignBtcHtlcLockFunding error mentions 'disabled' (OFF)",
             r.error.find("disabled") != std::string::npos);
#endif
    }

    // T6. EncodeP2WSHAddress
    // Phase C.6 wired this stub against libwally. The ON path now
    // produces a real testnet address; the OFF path still returns
    // disabled. T28 below covers the ON path comprehensively across
    // mainnet/testnet/regtest; here we only assert the OFF
    // disabled-error shape so the legacy test stays green in default
    // builds.
    {
        std::array<uint8_t, 32> witness_program{};
        for (size_t i = 0; i < 32; ++i) witness_program[i] = static_cast<uint8_t>(i);
        auto r = EncodeP2WSHAddress(witness_program, network);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
        // ON: testnet address starts with "tb1q" (witness v0, 32-byte program).
        TEST("T6 EncodeP2WSHAddress returns ok=true (ON, real backend)",
             r.ok == true);
        TEST("T6 EncodeP2WSHAddress testnet address has 'tb1q' prefix (ON)",
             r.ok && r.address.size() > 4 &&
             r.address.substr(0, 4) == "tb1q");
#else
        TEST("T6 EncodeP2WSHAddress returns ok=false (OFF)",
             r.ok == false);
        TEST("T6 EncodeP2WSHAddress error mentions 'disabled' (OFF)",
             r.error.find("disabled") != std::string::npos);
        TEST("T6 EncodeP2WSHAddress address empty (OFF)",
             r.address.empty());
#endif
    }

    // -----------------------------------------------------------------
    // T7. Error message references the STOP REPORT doc — only in OFF
    //     mode, where the disabled-result helper carries the doc path
    //     so a caller hitting the inert backend knows where to read
    //     for the integration plan. In ON mode the error is the
    //     specific input-validation message from sign_p2wsh_spend, so
    //     the STOP REPORT reference is irrelevant.
    // -----------------------------------------------------------------
    {
        auto r = SignBtcHtlcClaim(
            fake_txid, 0, 100000,
            fake_redeem_script, fake_preimage, fake_privkey,
            addr, 1000, network);
#if !defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
        TEST("T7 error references STOP REPORT doc path (OFF)",
             r.error.find("ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md") != std::string::npos);
#else
        TEST("T7 error is non-empty (ON, real validation)",
             !r.error.empty());
#endif
    }

    // =================================================================
    // Phase C.5 — libwally-backed leaf helpers (test-vector only)
    // =================================================================
    // The three helpers below were added in Phase C.5. They wrap libwally
    // ECDSA primitives. With SOST_BTC_HTLC_SIGNING=OFF (this build
    // path) they are inert and return the same disabled-error envelope
    // as the four legacy stubs above. With SOST_BTC_HTLC_SIGNING=ON
    // (a separate build documented in CMakeLists.txt) the helpers do
    // real work; the ON-mode behaviour is covered separately by Section
    // 6 of tests/test_atomic_swap_btc_test_vectors.cpp.
    //
    // The four legacy stubs (T3-T6 above) STAY disabled regardless of
    // the build flag — Phase C.5 deliberately does not wire them. So
    // the OFF-mode invariants below are the same shape as T3-T6: the
    // helpers exist, are callable, but produce no signature, no key,
    // and no verification result.

    {
        std::array<uint8_t, 32> priv_zero{};            // ignored content
        std::array<uint8_t, 32> sighash_zero{};         // ignored content

        // T8. DeriveBtcCompressedPubkey — OFF path returns disabled.
        {
            auto r = DeriveBtcCompressedPubkey(priv_zero);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            // In ON builds, an all-zero key is rejected by libwally
            // (outside the secp256k1 scalar range). Either way, ok=false.
            TEST("T8 DeriveBtcCompressedPubkey rejects all-zero key (ON)",
                 r.ok == false);
            TEST("T8 DeriveBtcCompressedPubkey error is non-empty (ON)",
                 !r.error.empty());
            TEST("T8 DeriveBtcCompressedPubkey bytes empty on failure (ON)",
                 r.bytes.empty());
#else
            TEST("T8 DeriveBtcCompressedPubkey returns ok=false (OFF)",
                 r.ok == false);
            TEST("T8 DeriveBtcCompressedPubkey error mentions 'disabled' (OFF)",
                 r.error.find("disabled") != std::string::npos);
            TEST("T8 DeriveBtcCompressedPubkey bytes empty (OFF)",
                 r.bytes.empty());
#endif
        }

        // T9. SignBtcEcdsaTestVector — OFF path returns disabled.
        {
            auto r = SignBtcEcdsaTestVector(
                priv_zero, sighash_zero.data(), sighash_zero.size());
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            // ON: still ok=false because the key is invalid; covers the
            // pre-flight rejection path before any signing is attempted.
            TEST("T9 SignBtcEcdsaTestVector rejects all-zero key (ON)",
                 r.ok == false);
            TEST("T9 SignBtcEcdsaTestVector error is non-empty (ON)",
                 !r.error.empty());
            TEST("T9 SignBtcEcdsaTestVector bytes empty on failure (ON)",
                 r.bytes.empty());
#else
            TEST("T9 SignBtcEcdsaTestVector returns ok=false (OFF)",
                 r.ok == false);
            TEST("T9 SignBtcEcdsaTestVector error mentions 'disabled' (OFF)",
                 r.error.find("disabled") != std::string::npos);
            TEST("T9 SignBtcEcdsaTestVector bytes empty (OFF)",
                 r.bytes.empty());
#endif
        }

        // T10. SignBtcEcdsaTestVector with WRONG sighash length is
        //      rejected even in ON mode (the length check fires before
        //      libwally is called).
        {
            std::array<uint8_t, 31> short_msg{};
            auto r = SignBtcEcdsaTestVector(
                priv_zero, short_msg.data(), short_msg.size());
            TEST("T10 SignBtcEcdsaTestVector rejects 31-byte sighash",
                 r.ok == false);
            TEST("T10 SignBtcEcdsaTestVector bytes empty on length error",
                 r.bytes.empty());
        }

        // T11. SignBtcEcdsaTestVector with NULL sighash pointer is
        //      rejected.
        {
            auto r = SignBtcEcdsaTestVector(priv_zero, nullptr, 32);
            TEST("T11 SignBtcEcdsaTestVector rejects null sighash pointer",
                 r.ok == false);
            TEST("T11 SignBtcEcdsaTestVector bytes empty on null pointer",
                 r.bytes.empty());
        }

        // T12. VerifyBtcEcdsaTestVector — OFF path returns disabled.
        //      ON path with garbage inputs returns ok=false (the DER
        //      parse fails on all-zero bytes).
        {
            std::array<uint8_t, 33> fake_pub{};
            std::array<uint8_t, 32> fake_msg{};
            std::array<uint8_t, 8>  fake_sig{};
            auto r = VerifyBtcEcdsaTestVector(
                fake_pub.data(), fake_pub.size(),
                fake_msg.data(), fake_msg.size(),
                fake_sig.data(), fake_sig.size());
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T12 VerifyBtcEcdsaTestVector rejects bogus inputs (ON)",
                 r.ok == false);
            TEST("T12 VerifyBtcEcdsaTestVector error is non-empty (ON)",
                 !r.error.empty());
#else
            TEST("T12 VerifyBtcEcdsaTestVector returns ok=false (OFF)",
                 r.ok == false);
            TEST("T12 VerifyBtcEcdsaTestVector error mentions 'disabled' (OFF)",
                 r.error.find("disabled") != std::string::npos);
#endif
        }

        // T13. VerifyBtcEcdsaTestVector rejects wrong-length message
        //      (32 is the only valid length for an ECDSA pre-image).
        {
            std::array<uint8_t, 33> fake_pub{};
            std::array<uint8_t, 31> short_msg{};
            std::array<uint8_t, 8>  fake_sig{};
            auto r = VerifyBtcEcdsaTestVector(
                fake_pub.data(), fake_pub.size(),
                short_msg.data(), short_msg.size(),
                fake_sig.data(), fake_sig.size());
            TEST("T13 VerifyBtcEcdsaTestVector rejects 31-byte message",
                 r.ok == false);
        }

        // T14. VerifyBtcEcdsaTestVector rejects null pointers.
        {
            std::array<uint8_t, 32> fake_msg{};
            std::array<uint8_t, 8>  fake_sig{};
            auto r = VerifyBtcEcdsaTestVector(
                nullptr, 0,
                fake_msg.data(), fake_msg.size(),
                fake_sig.data(), fake_sig.size());
            TEST("T14 VerifyBtcEcdsaTestVector rejects null pubkey pointer",
                 r.ok == false);
        }
    }

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    // =================================================================
    // T15-T18 — ON-mode happy path with the BIP-143 published key pair.
    // =================================================================
    // This is the load-bearing assertion that Phase C.5 actually does
    // cryptographic work in production source: the same published
    // BIP-143 private key produces the same published BIP-143 public
    // key, sign-then-verify is a round trip, and the DER output is
    // shaped like a real ECDSA signature.
    {
        // Hex parser inline so this test file does not depend on any
        // helper from test_atomic_swap_btc_test_vectors.cpp.
        auto from_hex = [](const std::string& s) {
            std::vector<uint8_t> out; out.reserve(s.size()/2);
            auto nib = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
                if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
                return -1;
            };
            for (size_t i = 0; i + 1 < s.size(); i += 2) {
                int hi = nib(s[i]); int lo = nib(s[i+1]);
                if (hi < 0 || lo < 0) return std::vector<uint8_t>{};
                out.push_back((uint8_t)((hi << 4) | lo));
            }
            return out;
        };

        // BIP-143 §"Native P2WSH" P2PK input — both halves published.
        const std::string priv_hex =
            "b8f28a772fccbf9b4f58a4f027e07dc2e35e7cd80529975e292ea34f84c4580c";
        const std::string pub_hex =
            "036d5c20fa14fb2f635474c1dc4ef5909d4568e5569b79fc94d3448486e14685f8";

        auto priv_v = from_hex(priv_hex);
        auto pub_v  = from_hex(pub_hex);
        std::array<uint8_t, 32> priv{};
        std::copy(priv_v.begin(), priv_v.end(), priv.begin());

        // T15. Derive pubkey from privkey matches BIP-143 published value.
        auto pub_r = DeriveBtcCompressedPubkey(priv);
        TEST("T15 DeriveBtcCompressedPubkey succeeds on valid key",
             pub_r.ok && pub_r.bytes.size() == 33);
        bool pub_match = pub_r.ok && (pub_r.bytes == pub_v);
        TEST("T15 derived pubkey matches BIP-143 published value",
             pub_match);

        // T16. Sign a 32-byte sighash with the published privkey.
        //      We use an arbitrary deterministic sighash (sha-shaped
        //      bytes 0x01..0x20) — Phase C.5 scope is the signing
        //      primitive, not BIP-143 sighash reproduction (that is
        //      Section 5 of the vector test).
        std::array<uint8_t, 32> msg{};
        for (size_t i = 0; i < 32; ++i) msg[i] = static_cast<uint8_t>(i + 1);
        auto sign_r = SignBtcEcdsaTestVector(priv, msg.data(), msg.size());
        TEST("T16 SignBtcEcdsaTestVector signs cleanly with valid key",
             sign_r.ok);
        TEST("T16 DER signature is between 8 and 72 bytes",
             sign_r.ok && sign_r.bytes.size() >= 8 && sign_r.bytes.size() <= 72);
        TEST("T16 DER signature starts with 0x30 (SEQUENCE tag)",
             sign_r.ok && !sign_r.bytes.empty() && sign_r.bytes[0] == 0x30);

        // T17. Verify the signature against the derived pubkey.
        if (sign_r.ok && pub_r.ok) {
            auto v = VerifyBtcEcdsaTestVector(
                pub_r.bytes.data(), pub_r.bytes.size(),
                msg.data(), msg.size(),
                sign_r.bytes.data(), sign_r.bytes.size());
            TEST("T17 signature verifies against derived pubkey", v.ok);
        }

        // T18. Mutate one bit of the message; verification must fail.
        if (sign_r.ok && pub_r.ok) {
            std::array<uint8_t, 32> bad_msg = msg;
            bad_msg[0] ^= 0x01;
            auto v = VerifyBtcEcdsaTestVector(
                pub_r.bytes.data(), pub_r.bytes.size(),
                bad_msg.data(), bad_msg.size(),
                sign_r.bytes.data(), sign_r.bytes.size());
            TEST("T18 verification fails when message is mutated 1 bit",
                 !v.ok && !v.error.empty());
        }

        // T19. Determinism — Low-R signing should produce the same DER
        //      bytes when re-signing the same key+message.
        if (sign_r.ok) {
            auto sign_r2 = SignBtcEcdsaTestVector(priv, msg.data(), msg.size());
            TEST("T19 signing same inputs twice produces same DER bytes",
                 sign_r2.ok && sign_r2.bytes == sign_r.bytes);
        }
    }
#endif

    // =================================================================
    // Phase C.6 — witness assembly + spending-tx builders
    // =================================================================
    {
        std::vector<uint8_t> fake_sig(72, 0xAA);   // pretend DER + sighash byte
        fake_sig[71] = 0x01;
        std::array<uint8_t, 32> fake_pre{};
        for (size_t i = 0; i < 32; ++i) fake_pre[i] = (uint8_t)i;
        std::vector<uint8_t> fake_script(100, 0xCC);

        // T20. BuildBtcHtlcClaimWitness OFF/ON shape.
        {
            auto r = BuildBtcHtlcClaimWitness(fake_sig, fake_pre, fake_script);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T20 BuildBtcHtlcClaimWitness ok (ON)", r.ok);
            TEST("T20 claim witness has 4 elements",
                 r.ok && r.stack.size() == 4);
            TEST("T20 claim witness [0] is the sig",
                 r.ok && r.stack[0] == fake_sig);
            TEST("T20 claim witness [1] is the preimage",
                 r.ok && r.stack[1].size() == 32 &&
                 std::equal(r.stack[1].begin(), r.stack[1].end(),
                            fake_pre.begin()));
            TEST("T20 claim witness [2] is 0x01 (OP_IF selector)",
                 r.ok && r.stack[2].size() == 1 && r.stack[2][0] == 0x01);
            TEST("T20 claim witness [3] is the redeem script",
                 r.ok && r.stack[3] == fake_script);
#else
            TEST("T20 BuildBtcHtlcClaimWitness disabled (OFF)",
                 r.ok == false &&
                 r.error.find("disabled") != std::string::npos);
            TEST("T20 claim witness stack empty (OFF)", r.stack.empty());
#endif
        }

        // T21. BuildBtcHtlcRefundWitness OFF/ON shape.
        {
            auto r = BuildBtcHtlcRefundWitness(fake_sig, fake_script);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T21 BuildBtcHtlcRefundWitness ok (ON)", r.ok);
            TEST("T21 refund witness has 3 elements",
                 r.ok && r.stack.size() == 3);
            TEST("T21 refund witness [0] is the sig",
                 r.ok && r.stack[0] == fake_sig);
            TEST("T21 refund witness [1] is empty (OP_ELSE selector)",
                 r.ok && r.stack[1].empty());
            TEST("T21 refund witness [2] is the redeem script",
                 r.ok && r.stack[2] == fake_script);
#else
            TEST("T21 BuildBtcHtlcRefundWitness disabled (OFF)",
                 r.ok == false &&
                 r.error.find("disabled") != std::string::npos);
            TEST("T21 refund witness stack empty (OFF)", r.stack.empty());
#endif
        }

        // T22. Witness builders reject empty sig / empty redeem script.
        {
            std::vector<uint8_t> empty_sig;
            auto r1 = BuildBtcHtlcClaimWitness(empty_sig, fake_pre, fake_script);
            TEST("T22 claim witness rejects empty sig", r1.ok == false);
            auto r2 = BuildBtcHtlcClaimWitness(fake_sig, fake_pre, {});
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T22 claim witness rejects empty redeem script",
                 r2.ok == false);
#else
            // In OFF mode the disabled-result fires before any validation.
            TEST("T22 claim witness disabled (OFF) regardless of args",
                 r2.ok == false);
#endif
            auto r3 = BuildBtcHtlcRefundWitness(empty_sig, fake_script);
            TEST("T22 refund witness rejects empty sig", r3.ok == false);
        }

        // T23. BuildBtcSpendingTxUnsignedHex shape + parse roundtrip.
        std::array<uint8_t, 32> prev_txid{};
        for (size_t i = 0; i < 32; ++i) prev_txid[i] = (uint8_t)(i + 1);
        std::vector<uint8_t> out_spk(22, 0x00);
        out_spk[0] = 0x00; out_spk[1] = 0x14;   // OP_0 push20 (fake P2WPKH)
        {
            auto r = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 100000, out_spk, 1000, 0xFFFFFFFE, 0);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T23 BuildBtcSpendingTxUnsignedHex ok (ON)", r.ok);
            TEST("T23 raw tx hex non-empty (ON)",
                 r.ok && !r.bytes.empty());
            TEST("T23 raw tx hex starts with '02' (version=2)",
                 r.ok && r.bytes.size() >= 8 &&
                 r.bytes[0] == '0' && r.bytes[1] == '2' &&
                 r.bytes[2] == '0' && r.bytes[3] == '0' &&
                 r.bytes[4] == '0' && r.bytes[5] == '0' &&
                 r.bytes[6] == '0' && r.bytes[7] == '0');
#else
            TEST("T23 BuildBtcSpendingTxUnsignedHex disabled (OFF)",
                 r.ok == false &&
                 r.error.find("disabled") != std::string::npos);
            TEST("T23 raw tx hex empty (OFF)", r.bytes.empty());
#endif
        }

        // T24. Reject fee >= amount.
        {
            auto r = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 1000, out_spk, 1000, 0xFFFFFFFE, 0);
            TEST("T24 reject fee == amount (no remaining output)",
                 r.ok == false);
            auto r2 = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 1000, out_spk, 2000, 0xFFFFFFFE, 0);
            TEST("T24 reject fee > amount",
                 r2.ok == false);
        }

        // T25. Reject negative fee.
        {
            auto r = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 100000, out_spk, -1, 0xFFFFFFFE, 0);
            TEST("T25 reject negative fee", r.ok == false);
        }

        // T26. Reject zero / negative amount.
        {
            auto r = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 0, out_spk, 1000, 0xFFFFFFFE, 0);
            TEST("T26 reject zero amount", r.ok == false);
            auto r2 = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, -1, out_spk, 1000, 0xFFFFFFFE, 0);
            TEST("T26 reject negative amount", r2.ok == false);
        }

        // T27. Reject empty output script.
        {
            auto r = BuildBtcSpendingTxUnsignedHex(
                prev_txid, 0, 100000, {}, 1000, 0xFFFFFFFE, 0);
            TEST("T27 reject empty output script", r.ok == false);
        }

        // T28. EncodeP2WSHAddress: ON path now produces real addresses
        //      (Phase C.6 wired this stub too because it is a single
        //      wally_addr_segwit_from_bytes call). Mainnet / testnet /
        //      regtest are all accepted; unknown networks rejected.
        {
            std::array<uint8_t, 32> wp{};
            for (size_t i = 0; i < 32; ++i) wp[i] = (uint8_t)i;
            auto r = EncodeP2WSHAddress(wp, "mainnet");
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            // ON: real mainnet P2WSH address starting with "bc1q".
            TEST("T28 EncodeP2WSHAddress mainnet ok (ON)", r.ok);
            TEST("T28 mainnet address has bc1q prefix (ON)",
                 r.ok && r.address.size() > 4 &&
                 r.address.substr(0, 4) == "bc1q");
            auto rt = EncodeP2WSHAddress(wp, "testnet");
            TEST("T28 EncodeP2WSHAddress testnet ok (ON)",
                 rt.ok && rt.address.substr(0, 4) == "tb1q");
            auto rb = EncodeP2WSHAddress(wp, "regtest");
            TEST("T28 EncodeP2WSHAddress regtest ok (ON)",
                 rb.ok && rb.address.substr(0, 6) == "bcrt1q");
            auto rx = EncodeP2WSHAddress(wp, "fakenet");
            TEST("T28 EncodeP2WSHAddress rejects unknown network (ON)",
                 rx.ok == false);
#else
            // OFF: stays disabled as before. (Note: T6 above already
            // asserts the OFF behaviour with a different witness program.)
            TEST("T28 EncodeP2WSHAddress disabled (OFF)",
                 r.ok == false);
#endif
        }
    }

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    // =================================================================
    // Phase C.7 — SignBtcHtlcClaim / SignBtcHtlcRefund end-to-end
    // =================================================================
    // Build a real HTLC redeem script, derive a valid destination
    // address, sign CLAIM and REFUND with the BIP-143 P2PK test key,
    // and assert observable properties of the resulting raw_tx_hex.
    // No broadcast, no wallet — the private key is a function arg.
    {
        auto from_hex = [](const std::string& s) {
            std::vector<uint8_t> out; out.reserve(s.size()/2);
            auto nib = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
                if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
                return -1;
            };
            for (size_t i = 0; i + 1 < s.size(); i += 2) {
                int hi = nib(s[i]); int lo = nib(s[i+1]);
                if (hi < 0 || lo < 0) return std::vector<uint8_t>{};
                out.push_back((uint8_t)((hi << 4) | lo));
            }
            return out;
        };

        // BIP-143 P2PK test key — both halves published.
        const std::string priv_hex =
            "b8f28a772fccbf9b4f58a4f027e07dc2e35e7cd80529975e292ea34f84c4580c";
        const std::string pub_hex =
            "036d5c20fa14fb2f635474c1dc4ef5909d4568e5569b79fc94d3448486e14685f8";
        auto priv_v = from_hex(priv_hex);
        auto pub_v  = from_hex(pub_hex);

        std::array<uint8_t, 32> claim_priv{};
        std::copy(priv_v.begin(), priv_v.end(), claim_priv.begin());
        std::array<uint8_t, 33> claim_pub{};
        std::copy(pub_v.begin(), pub_v.end(), claim_pub.begin());

        std::array<uint8_t, 32> refund_priv{};
        refund_priv[31] = 0x42;  // small valid scalar
        auto refund_pub_r = DeriveBtcCompressedPubkey(refund_priv);
        TEST("T29 refund pubkey derivation succeeded", refund_pub_r.ok);
        std::array<uint8_t, 33> refund_pub{};
        if (refund_pub_r.ok) {
            std::copy(refund_pub_r.bytes.begin(),
                      refund_pub_r.bytes.end(),
                      refund_pub.begin());
        }

        // Hashlock = sha256(preimage).
        std::array<uint8_t, 32> preimage{};
        for (size_t i = 0; i < 32; ++i) preimage[i] = (uint8_t)(0xAA ^ i);
        sost::Bytes32 hashlock_b = sost::sha256(preimage.data(), preimage.size());
        std::array<uint8_t, 32> hashlock_arr{};
        std::copy(hashlock_b.begin(), hashlock_b.end(), hashlock_arr.begin());

        int64_t refund_height = 700000;
        auto script = BuildBtcHtlcRedeemScript(
            hashlock_arr, refund_height, claim_pub, refund_pub);

        // Destination = regtest P2WSH of an arbitrary witness program.
        std::array<uint8_t, 32> dest_program{};
        for (size_t i = 0; i < 32; ++i) dest_program[i] = (uint8_t)(0x55 ^ i);
        auto dest_addr_r = EncodeP2WSHAddress(dest_program, "regtest");
        TEST("T29 destination address encode succeeded", dest_addr_r.ok);

        sost::Bytes32 lock_txid{};
        for (size_t i = 0; i < 32; ++i) lock_txid[i] = (uint8_t)(0xBC ^ i);
        int64_t lock_amount = 1000000;  // 0.01 BTC

        // T29. SignBtcHtlcClaim happy path.
        auto claim_r = SignBtcHtlcClaim(
            lock_txid, 0, lock_amount,
            script, preimage, claim_priv,
            dest_addr_r.address, 1000, "regtest");
        TEST("T29 SignBtcHtlcClaim happy path ok=true", claim_r.ok);
        TEST("T29 SignBtcHtlcClaim raw_tx_hex non-empty",
             claim_r.ok && !claim_r.raw_tx_hex.empty());
        TEST("T29 raw_tx_hex starts with '02000000' (version=2)",
             claim_r.ok && claim_r.raw_tx_hex.substr(0, 8) == "02000000");
        // BIP-144 witness marker+flag = "0001" after the 4-byte version.
        TEST("T29 raw_tx_hex contains '0001' marker+flag (witness format)",
             claim_r.ok && claim_r.raw_tx_hex.substr(8, 4) == "0001");

        // T30. Determinism — re-sign identical inputs.
        {
            auto claim_r2 = SignBtcHtlcClaim(
                lock_txid, 0, lock_amount,
                script, preimage, claim_priv,
                dest_addr_r.address, 1000, "regtest");
            TEST("T30 SignBtcHtlcClaim deterministic on identical inputs",
                 claim_r2.ok && claim_r2.raw_tx_hex == claim_r.raw_tx_hex);
        }

        // T31. Mutate preimage → hex must differ.
        {
            auto bad_pre = preimage;
            bad_pre[0] ^= 0x01;
            auto claim_r3 = SignBtcHtlcClaim(
                lock_txid, 0, lock_amount,
                script, bad_pre, claim_priv,
                dest_addr_r.address, 1000, "regtest");
            TEST("T31 mutated preimage produces different raw_tx_hex",
                 claim_r3.ok && claim_r3.raw_tx_hex != claim_r.raw_tx_hex);
        }

        // T32. SignBtcHtlcRefund happy path.
        auto refund_r = SignBtcHtlcRefund(
            lock_txid, 0, lock_amount,
            script, refund_height, refund_priv,
            dest_addr_r.address, 1000, "regtest");
        TEST("T32 SignBtcHtlcRefund happy path ok=true", refund_r.ok);
        TEST("T32 SignBtcHtlcRefund raw_tx_hex non-empty",
             refund_r.ok && !refund_r.raw_tx_hex.empty());
        TEST("T32 raw_tx_hex starts with '02000000' (version=2)",
             refund_r.ok && refund_r.raw_tx_hex.substr(0, 8) == "02000000");

        // T33. Claim and refund produce DIFFERENT signed tx (locktime
        //      + witness shape both differ).
        TEST("T33 claim and refund produce different signed tx",
             claim_r.ok && refund_r.ok &&
             claim_r.raw_tx_hex != refund_r.raw_tx_hex);

        // T34. Refund tx ends with nLockTime=refund_height LE-encoded.
        //      700000 = 0xAAE60 → LE bytes "60ae0a00".
        {
            std::string lockhex = "60ae0a00";
            bool present = refund_r.ok &&
                refund_r.raw_tx_hex.size() >= lockhex.size() &&
                refund_r.raw_tx_hex.substr(
                    refund_r.raw_tx_hex.size() - lockhex.size()) == lockhex;
            TEST("T34 refund tx ends with nLockTime=700000 LE-encoded",
                 present);
        }

        // T35. Reject malformed inputs in the wired functions.
        {
            auto bad = SignBtcHtlcClaim(
                lock_txid, 0, lock_amount,
                script, preimage, claim_priv,
                dest_addr_r.address, lock_amount, "regtest");
            TEST("T35 SignBtcHtlcClaim rejects fee == amount", !bad.ok);
            auto bad2 = SignBtcHtlcClaim(
                lock_txid, 0, lock_amount,
                script, preimage, claim_priv,
                "not-an-address", 1000, "regtest");
            TEST("T35 SignBtcHtlcClaim rejects malformed destination address",
                 !bad2.ok);
            auto bad3 = SignBtcHtlcClaim(
                lock_txid, 0, lock_amount,
                script, preimage, claim_priv,
                dest_addr_r.address, 1000, "fakenet");
            TEST("T35 SignBtcHtlcClaim rejects unknown bitcoin_network",
                 !bad3.ok);
        }
    }
#endif

    // =================================================================
    // Phase C.8 — new pure helpers: OFF/ON disabled-shape invariants.
    // =================================================================
    // ExtractBtcHtlcPreimageFromWitnessStack / FromTxHex / ComputeBtcTxid
    // must fail-closed in the default OFF build (disabled error) and, in
    // ON mode with bogus inputs, still return ok=false with a real
    // message.
    {
        std::array<uint8_t, 32> hl{};
        for (size_t i = 0; i < 32; ++i) hl[i] = (uint8_t)i;

        // T36. ExtractBtcHtlcPreimageFromWitnessStack — no matching item.
        {
            std::vector<std::vector<uint8_t>> stack;
            stack.push_back(std::vector<uint8_t>(72, 0xAA));    // sig-ish
            stack.push_back(std::vector<uint8_t>(32, 0x11));    // wrong secret
            auto r = ExtractBtcHtlcPreimageFromWitnessStack(stack, hl);
#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T36 ExtractPreimage(stack): no match -> ok=false (ON)",
                 r.ok == false && !r.error.empty() && r.bytes.empty());
#else
            TEST("T36 ExtractPreimage(stack): disabled (OFF)",
                 r.ok == false &&
                 r.error.find("disabled") != std::string::npos);
#endif
        }

        // T37. ExtractBtcHtlcPreimageFromTxHex — garbage hex.
        {
            auto r = ExtractBtcHtlcPreimageFromTxHex("zzzz", 0, hl);
            TEST("T37 ExtractPreimage(txhex): garbage -> ok=false", r.ok == false);
#if !defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T37 ExtractPreimage(txhex): disabled msg (OFF)",
                 r.error.find("disabled") != std::string::npos);
#endif
        }

        // T38. ComputeBtcTxid — garbage hex.
        {
            auto r = ComputeBtcTxid("nothex");
            TEST("T38 ComputeBtcTxid: garbage -> ok=false", r.ok == false);
#if !defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
            TEST("T38 ComputeBtcTxid: disabled msg (OFF)",
                 r.error.find("disabled") != std::string::npos);
#endif
        }
    }

#if defined(SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY)
    // =================================================================
    // Phase C.8 — funding tx + preimage extraction + txid (ON mode).
    // =================================================================
    {
        auto from_hex = [](const std::string& s) {
            std::vector<uint8_t> out; out.reserve(s.size()/2);
            auto nib = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
                if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
                return -1;
            };
            for (size_t i = 0; i + 1 < s.size(); i += 2) {
                int hi = nib(s[i]); int lo = nib(s[i+1]);
                if (hi < 0 || lo < 0) return std::vector<uint8_t>{};
                out.push_back((uint8_t)((hi << 4) | lo));
            }
            return out;
        };
        // Parse a raw tx hex with libwally for structural assertions.
        auto parse_tx = [](const std::string& hex) -> struct wally_tx* {
            struct wally_tx* tx = nullptr;
            if (wally_tx_from_hex(hex.c_str(), WALLY_TX_FLAG_USE_WITNESS, &tx) != 0)
                return nullptr;
            return tx;
        };

        // BIP-143 P2PK test key = the funder.
        const std::string priv_hex =
            "b8f28a772fccbf9b4f58a4f027e07dc2e35e7cd80529975e292ea34f84c4580c";
        const std::string pub_hex =
            "036d5c20fa14fb2f635474c1dc4ef5909d4568e5569b79fc94d3448486e14685f8";
        auto priv_v = from_hex(priv_hex);
        auto pub_v  = from_hex(pub_hex);
        std::array<uint8_t, 32> funder_priv{};
        std::copy(priv_v.begin(), priv_v.end(), funder_priv.begin());
        std::array<uint8_t, 33> claim_pub{};
        std::copy(pub_v.begin(), pub_v.end(), claim_pub.begin());

        std::array<uint8_t, 32> refund_priv{};
        refund_priv[31] = 0x42;
        auto refund_pub_r = DeriveBtcCompressedPubkey(refund_priv);
        std::array<uint8_t, 33> refund_pub{};
        std::copy(refund_pub_r.bytes.begin(), refund_pub_r.bytes.end(),
                  refund_pub.begin());

        // hashlock = sha256(preimage)
        std::array<uint8_t, 32> preimage{};
        for (size_t i = 0; i < 32; ++i) preimage[i] = (uint8_t)(0x33 ^ i);
        sost::Bytes32 hb = sost::sha256(preimage.data(), preimage.size());
        std::array<uint8_t, 32> hashlock{};
        std::copy(hb.begin(), hb.end(), hashlock.begin());

        int64_t refund_height = 700000;
        auto redeem = BuildBtcHtlcRedeemScript(
            hashlock, refund_height, claim_pub, refund_pub);

        // Expected HTLC scriptPubKey = OP_0 <sha256(redeem)>.
        sost::Bytes32 wp = BtcHtlcWitnessProgram(redeem);
        std::vector<uint8_t> htlc_spk;
        htlc_spk.push_back(0x00); htlc_spk.push_back(0x20);
        htlc_spk.insert(htlc_spk.end(), wp.begin(), wp.end());

        // Change/destination address (a valid segwit address to decode).
        std::array<uint8_t, 32> dprog{};
        for (size_t i = 0; i < 32; ++i) dprog[i] = (uint8_t)(0x77 ^ i);
        auto change_addr = EncodeP2WSHAddress(dprog, "regtest");
        TEST("T39 change address encodes", change_addr.ok);

        sost::Bytes32 prev_txid{};
        for (size_t i = 0; i < 32; ++i) prev_txid[i] = (uint8_t)(0x10 ^ i);

        // --- T40. Funding, change well above dust: 2 outputs ---
        int64_t prev_amt = 1000000, lock_amt = 600000, fee = 1000;
        int64_t expect_change = prev_amt - lock_amt - fee;  // 399000
        auto fund = SignBtcHtlcLockFunding(
            prev_txid, 0, prev_amt, funder_priv,
            change_addr.address, redeem, lock_amt, fee, "regtest");
        TEST("T40 SignBtcHtlcLockFunding happy path ok=true", fund.ok);
        TEST("T40 funding tx version=2 (02000000)",
             fund.ok && fund.raw_tx_hex.substr(0, 8) == "02000000");
        TEST("T40 funding tx witness marker 0001",
             fund.ok && fund.raw_tx_hex.substr(8, 4) == "0001");
        if (fund.ok) {
            auto* tx = parse_tx(fund.raw_tx_hex);
            TEST("T40 funding tx parses", tx != nullptr);
            if (tx) {
                TEST("T40 funding tx has 2 outputs (HTLC + change)",
                     tx->num_outputs == 2);
                TEST("T40 vout0 amount == lock_amount",
                     tx->num_outputs >= 1 &&
                     (int64_t)tx->outputs[0].satoshi == lock_amt);
                bool spk_match = tx->num_outputs >= 1 &&
                    tx->outputs[0].script_len == htlc_spk.size() &&
                    std::memcmp(tx->outputs[0].script, htlc_spk.data(),
                                htlc_spk.size()) == 0;
                TEST("T40 vout0 scriptPubKey == OP_0<sha256(redeem)> (P2WSH)",
                     spk_match);
                TEST("T40 vout1 amount == change",
                     tx->num_outputs >= 2 &&
                     (int64_t)tx->outputs[1].satoshi == expect_change);
                TEST("T40 funding input sequence is final (0xFFFFFFFF)",
                     tx->num_inputs == 1 &&
                     tx->inputs[0].sequence == 0xFFFFFFFF);
                TEST("T40 funding tx locktime == 0", tx->locktime == 0);
                // P2WPKH witness: [sig+type, 33-byte pubkey].
                TEST("T40 funding witness has 2 items",
                     tx->inputs[0].witness &&
                     tx->inputs[0].witness->num_items == 2);
                TEST("T40 funding witness[1] is the 33-byte funder pubkey",
                     tx->inputs[0].witness &&
                     tx->inputs[0].witness->num_items == 2 &&
                     tx->inputs[0].witness->items[1].witness_len == 33 &&
                     std::memcmp(tx->inputs[0].witness->items[1].witness,
                                 claim_pub.data(), 33) == 0);
                wally_tx_free(tx);
            }
        }

        // --- T41. Determinism ---
        {
            auto fund2 = SignBtcHtlcLockFunding(
                prev_txid, 0, prev_amt, funder_priv,
                change_addr.address, redeem, lock_amt, fee, "regtest");
            TEST("T41 funding deterministic on identical inputs",
                 fund2.ok && fund.ok && fund2.raw_tx_hex == fund.raw_tx_hex);
        }

        // --- T42. Sub-dust change is folded into fee -> 1 output ---
        {
            int64_t p = lock_amt + fee + 200;  // 200 <= dust(294)
            auto f = SignBtcHtlcLockFunding(
                prev_txid, 0, p, funder_priv,
                change_addr.address, redeem, lock_amt, fee, "regtest");
            TEST("T42 sub-dust funding ok", f.ok);
            auto* tx = f.ok ? parse_tx(f.raw_tx_hex) : nullptr;
            TEST("T42 sub-dust change dropped -> exactly 1 output (HTLC)",
                 tx && tx->num_outputs == 1 &&
                 (int64_t)tx->outputs[0].satoshi == lock_amt);
            if (tx) wally_tx_free(tx);
        }

        // --- T43. Exact amount (change == 0) -> 1 output ---
        {
            int64_t p = lock_amt + fee;
            auto f = SignBtcHtlcLockFunding(
                prev_txid, 0, p, funder_priv,
                change_addr.address, redeem, lock_amt, fee, "regtest");
            TEST("T43 change==0 funding ok", f.ok);
            auto* tx = f.ok ? parse_tx(f.raw_tx_hex) : nullptr;
            TEST("T43 change==0 -> exactly 1 output",
                 tx && tx->num_outputs == 1);
            if (tx) wally_tx_free(tx);
        }

        // --- T44. Insufficient prev_amount rejected ---
        {
            auto f = SignBtcHtlcLockFunding(
                prev_txid, 0, lock_amt + fee - 1, funder_priv,
                change_addr.address, redeem, lock_amt, fee, "regtest");
            TEST("T44 reject prev_amount < lock+fee", f.ok == false);
        }

        // --- T45. Bad inputs rejected ---
        {
            std::array<uint8_t, 32> zero{};
            auto f1 = SignBtcHtlcLockFunding(
                prev_txid, 0, prev_amt, zero,
                change_addr.address, redeem, lock_amt, fee, "regtest");
            TEST("T45 reject invalid funder privkey", f1.ok == false);
            auto f2 = SignBtcHtlcLockFunding(
                prev_txid, 0, prev_amt, funder_priv,
                "not-an-address", redeem, lock_amt, fee, "regtest");
            TEST("T45 reject undecodable change addr (change>dust)",
                 f2.ok == false);
            auto f3 = SignBtcHtlcLockFunding(
                prev_txid, 0, prev_amt, funder_priv,
                change_addr.address, redeem, lock_amt, fee, "fakenet");
            TEST("T45 reject unknown network", f3.ok == false);
            auto f4 = SignBtcHtlcLockFunding(
                prev_txid, 0, prev_amt, funder_priv,
                change_addr.address, {}, lock_amt, fee, "regtest");
            TEST("T45 reject empty redeem script", f4.ok == false);
        }

        // --- T46. ComputeBtcTxid on the funding tx ---
        {
            TEST("T46 ComputeBtcTxid ok on funding tx",
                 fund.ok);
            auto tid = ComputeBtcTxid(fund.raw_tx_hex);
            TEST("T46 txid is 32 bytes", tid.ok && tid.bytes.size() == 32);
            // Segwit txid is witness-independent: recompute must match.
            auto tid2 = ComputeBtcTxid(fund.raw_tx_hex);
            TEST("T46 txid deterministic", tid2.ok && tid2.bytes == tid.bytes);
        }

        // --- CLAIM + REFUND for the same HTLC, to exercise extraction ---
        sost::Bytes32 lock_txid{};
        for (size_t i = 0; i < 32; ++i) lock_txid[i] = (uint8_t)(0x21 ^ i);
        auto claim = SignBtcHtlcClaim(
            lock_txid, 0, lock_amt, redeem, preimage, funder_priv,
            change_addr.address, 1000, "regtest");
        TEST("T47 CLAIM tx built", claim.ok);
        auto refund = SignBtcHtlcRefund(
            lock_txid, 0, lock_amt, redeem, refund_height, refund_priv,
            change_addr.address, 1000, "regtest");
        TEST("T47 REFUND tx built", refund.ok);

        // --- T48. Preimage extraction from the CLAIM tx round-trips ---
        {
            auto ex = ExtractBtcHtlcPreimageFromTxHex(
                claim.raw_tx_hex, 0, hashlock);
            TEST("T48 extract preimage from CLAIM tx ok", ex.ok);
            TEST("T48 extracted preimage matches original",
                 ex.ok && ex.bytes.size() == 32 &&
                 std::memcmp(ex.bytes.data(), preimage.data(), 32) == 0);
        }

        // --- T49. Wrong hashlock -> no extraction (fund-safe) ---
        {
            std::array<uint8_t, 32> wrong = hashlock;
            wrong[0] ^= 0x01;
            auto ex = ExtractBtcHtlcPreimageFromTxHex(
                claim.raw_tx_hex, 0, wrong);
            TEST("T49 wrong hashlock -> extraction fails", ex.ok == false);
        }

        // --- T50. REFUND tx reveals NO preimage (early-refund/no-secret) ---
        {
            auto ex = ExtractBtcHtlcPreimageFromTxHex(
                refund.raw_tx_hex, 0, hashlock);
            TEST("T50 REFUND tx yields no preimage", ex.ok == false);
        }

        // --- T51. Extraction from a witness stack directly ---
        {
            std::vector<uint8_t> sig(72, 0xAB); sig[71] = 0x01;
            auto w = BuildBtcHtlcClaimWitness(sig, preimage, redeem);
            TEST("T51 claim witness built", w.ok && w.stack.size() == 4);
            auto ex = ExtractBtcHtlcPreimageFromWitnessStack(w.stack, hashlock);
            TEST("T51 extract preimage from witness stack matches",
                 ex.ok && ex.bytes.size() == 32 &&
                 std::memcmp(ex.bytes.data(), preimage.data(), 32) == 0);
            std::array<uint8_t, 32> wrong = hashlock; wrong[5] ^= 0x02;
            auto ex2 = ExtractBtcHtlcPreimageFromWitnessStack(w.stack, wrong);
            TEST("T51 wrong hashlock -> no match", ex2.ok == false);
        }

        // --- T52. Locktime/sequence: refund CANNOT settle before timeout ---
        // The refund path must set nLockTime == refund_height AND an
        // input sequence < 0xFFFFFFFF so OP_CHECKLOCKTIMEVERIFY is
        // enforced; the claim path must set nLockTime == 0. This is what
        // makes a refund-before-timeout impossible on a real node.
        {
            auto* rt = refund.ok ? parse_tx(refund.raw_tx_hex) : nullptr;
            TEST("T52 refund tx locktime == refund_height",
                 rt && rt->locktime == (uint32_t)refund_height);
            TEST("T52 refund input sequence < 0xFFFFFFFF (CLTV enforced)",
                 rt && rt->num_inputs == 1 &&
                 rt->inputs[0].sequence == 0xFFFFFFFE);
            if (rt) wally_tx_free(rt);

            auto* ct = claim.ok ? parse_tx(claim.raw_tx_hex) : nullptr;
            TEST("T52 claim tx locktime == 0 (no timelock on claim)",
                 ct && ct->locktime == 0);
            if (ct) wally_tx_free(ct);
        }
    }
#endif

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
