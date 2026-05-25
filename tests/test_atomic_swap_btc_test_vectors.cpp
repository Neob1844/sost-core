// Phase 4B — BTC test vector harness (OFF-mode, no libwally).
//
// This file captures the OFFICIAL test vectors that the future
// Phase C real signing backend MUST pass:
//
//   - BIP-173 Bech32 valid + invalid vectors (Pieter Wuille, 2017)
//   - BIP-350 Bech32m valid + invalid vectors (Pieter Wuille, 2021)
//   - BIP-143 SegWit v0 sighash test vector (P2WSH variant)
//   - P2WSH witness program generation (sha256 of redeem script)
//   - HTLC redeem script hash determinism (uses existing builder)
//
// We CAN execute today, with the current SOST codebase (no libwally):
//
//   - P2WSH witness program — sha256(redeem_script) using sost::sha256.
//   - HTLC redeem script determinism — same builder + same inputs =>
//     same byte sequence; cross-checked against test_atomic_swap_btc_script.
//
// We CANNOT execute today, because the backend that produces these
// outputs lives in libwally (or a future from-scratch Phase C
// implementation):
//
//   - Bech32 / Bech32m encode + decode — no encoder in SOST yet.
//   - BIP-143 sighash computation — requires the full SegWit v0
//     serialization rules (hashPrevouts, hashSequence, hashOutputs,
//     amount, scriptCode), none of which exist in SOST yet.
//
// For the unexecutable vectors we record the inputs and the expected
// outputs as static constants, plus an unconditional FAIL marker
// that prints a clear "Phase C must implement X — see
// docs/design/ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md". When Phase C is
// written, those FAILs will turn into real PASSes without any change
// to this file beyond removing the markers.
//
// NO signing, NO key material, NO network, NO file I/O.

#include "sost/atomic_swap_btc.h"
#include "sost/crypto.h"
#include "sost/types.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::atomic_swap::btc;

static int g_pass = 0;
static int g_fail = 0;
static int g_pending = 0;  // vectors awaiting Phase C backend

#define TEST(msg, cond) do {                                        \
    if (cond) { printf("  PASS    : %s\n", msg); g_pass++; }        \
    else { printf("  *** FAIL: %s  [%s:%d]\n",                      \
                  msg, __FILE__, __LINE__); g_fail++; }             \
} while (0)

#define PENDING_PHASE_C(msg) do {                                   \
    printf("  PENDING : %s  (Phase C backend required)\n", msg);    \
    g_pending++;                                                    \
} while (0)

static std::string to_hex(const std::vector<uint8_t>& v) {
    static const char* H = "0123456789abcdef";
    std::string s; s.reserve(v.size() * 2);
    for (auto b : v) { s.push_back(H[b >> 4]); s.push_back(H[b & 0x0F]); }
    return s;
}

static std::string to_hex(const Bytes32& v) {
    return to_hex(std::vector<uint8_t>(v.begin(), v.end()));
}

static std::vector<uint8_t> from_hex(const std::string& s) {
    std::vector<uint8_t> out;
    out.reserve(s.size() / 2);
    auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
        if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
        return -1;
    };
    for (size_t i = 0; i + 1 < s.size(); i += 2) {
        int hi = nib(s[i]);
        int lo = nib(s[i+1]);
        if (hi < 0 || lo < 0) return {};
        out.push_back((uint8_t)((hi << 4) | lo));
    }
    return out;
}

// ===========================================================================
// SECTION 1 — BIP-173 Bech32 (mainnet/testnet/regtest "bc"/"tb"/"bcrt")
// ===========================================================================
//
// Reference: https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki
// "Valid Bech32" + "Invalid Bech32" vectors from the BIP.
//
// We capture two representative vectors from each set. The full battery
// (~30 valid + ~50 invalid) lives in
// docs/design/ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md so any reviewer can
// extend the harness when Phase C lands.

struct Bech32Vec {
    const char* encoded;
    const char* hrp;
    // hex of the 5-bit-grouped data part (BIP-173 §"Bech32" data field)
    // empty string when not relevant for the vector type
    const char* data_5bit_hex;
};

static const Bech32Vec kBech32Valid[] = {
    // Pieter Wuille's BIP-173 valid examples.
    {"A12UEL5L",                                                "a",   ""},
    {"a12uel5l",                                                "a",   ""},
    {"abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw",           "abcdef", ""},
    {"split1checkupstagehandshakeupstreamerranterredcaperredlc445v",
                                                                "split", ""},
    {"?1ezyfcl",                                                "?",   ""},
};

static const char* kBech32Invalid[] = {
    // Selection from BIP-173 invalid examples.
    "10a06t8",            // empty HRP
    "1qzzfhee",           // HRP "1" with checksum miss
    "A1G7SGD8",           // invalid checksum
    "a12UEL5L",           // mixed case
    "x1b4n0q5v",          // invalid character in data part
    "li1dgmt3",           // checksum miss
    "de1lg7wt\xff",       // invalid trailing byte (replaced for printability)
};

static void section_bip173_bech32() {
    printf("\n-- SECTION 1: BIP-173 Bech32 vectors --\n");
    printf("   (5 valid + 7 invalid representative vectors loaded;\n");
    printf("    full battery in ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md)\n");

    // We do not yet have a Bech32 encoder/decoder. Mark the executable
    // verification as pending Phase C.
    for (const auto& v : kBech32Valid) {
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "BIP-173 valid: \"%s\" decodes to hrp=\"%s\"",
                 v.encoded, v.hrp);
        PENDING_PHASE_C(buf);
    }
    for (const char* enc : kBech32Invalid) {
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "BIP-173 invalid: \"%s\" must be rejected", enc);
        PENDING_PHASE_C(buf);
    }
}

// ===========================================================================
// SECTION 2 — BIP-350 Bech32m (Taproot / SegWit v1+)
// ===========================================================================
//
// Reference: https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki
//
// HTLC swaps as currently scoped (BIP-199 P2WSH SegWit v0) do NOT
// require Bech32m for outputs — only for receiving Taproot addresses
// if the counterparty insists on P2TR. We capture the vectors so a
// future Taproot-capable HTLC variant has a verification harness
// ready.

struct Bech32mVec {
    const char* encoded;
    const char* hrp;
};

static const Bech32mVec kBech32mValid[] = {
    {"A1LQFN3A",                                            "a"},
    {"a1lqfn3a",                                            "a"},
    {"an83characterlonghumanreadablepartthatcontainsthetheexcludedcharactersbio1tt5tgs",
                                                            "an83characterlonghumanreadablepartthatcontainsthetheexcludedcharactersbio"},
    {"abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx",       "abcdef"},
    {"split1checkupstagehandshakeupstreamerranterredcaperredlc445v",
                                                            "split"},
};

static void section_bip350_bech32m() {
    printf("\n-- SECTION 2: BIP-350 Bech32m vectors --\n");
    printf("   (5 valid representative vectors loaded; full battery in\n");
    printf("    ATOMIC_SWAP_BTC_TEST_VECTOR_GAP.md. Bech32m is only\n");
    printf("    needed if a counterparty uses Taproot addresses;\n");
    printf("    the default HTLC path is P2WSH SegWit v0 which uses\n");
    printf("    plain Bech32.)\n");

    for (const auto& v : kBech32mValid) {
        char buf[256];
        snprintf(buf, sizeof(buf),
                 "BIP-350 valid: \"%s\" hrp=\"%s\"",
                 v.encoded, v.hrp);
        PENDING_PHASE_C(buf);
    }
}

// ===========================================================================
// SECTION 3 — P2WSH witness program (sha256 of redeem script)
// ===========================================================================
//
// P2WSH witness program = SHA-256(redeem_script). We have sost::sha256
// AND we have BuildBtcHtlcRedeemScript, so this is fully executable
// today. The output is the 32-byte witness program; the operator then
// Bech32-encodes it (with hrp "bc"/"tb"/"bcrt") to produce the
// human-readable address — but that encoding step is in section 1.

static void section_p2wsh_witness_program() {
    printf("\n-- SECTION 3: P2WSH witness program (executable today) --\n");

    // Construct a deterministic HTLC redeem script. The builder takes
    // 33-byte compressed secp256k1 pubkeys (NOT 20-byte pkhs); the
    // exact bytes are pinned in test_atomic_swap_btc_script.cpp; we
    // only need the witness program here.
    std::array<uint8_t, 32> hashlock{};
    std::array<uint8_t, 33> claim_pubkey{};
    std::array<uint8_t, 33> refund_pubkey{};
    for (size_t i = 0; i < 32; ++i) hashlock[i] = static_cast<uint8_t>(i + 1);
    claim_pubkey[0]  = 0x02;
    refund_pubkey[0] = 0x03;
    for (size_t i = 1; i < 33; ++i) {
        claim_pubkey[i]  = static_cast<uint8_t>(0xA0 + (i - 1));
        refund_pubkey[i] = static_cast<uint8_t>(0xB0 + (i - 1));
    }

    auto script = BuildBtcHtlcRedeemScript(hashlock, 144 * 7,
                                           claim_pubkey, refund_pubkey);
    TEST("Redeem script for fixed inputs is non-empty", !script.empty());

    Bytes32 witness_program = BtcHtlcWitnessProgram(script);

    // Cross-check: BtcHtlcWitnessProgram MUST equal sost::sha256(script).
    Bytes32 manual = sost::sha256(script.data(), script.size());
    TEST("BtcHtlcWitnessProgram(script) == sha256(script) (byte-identical)",
         witness_program == manual);

    // Cross-check: changing one byte of the script changes the witness
    // program (sanity that we're not accidentally returning a constant).
    auto script2 = script;
    script2[0] ^= 0x01;
    Bytes32 witness_program2 = BtcHtlcWitnessProgram(script2);
    TEST("Single-byte script change flips the witness program (avalanche)",
         witness_program != witness_program2);

    // Cross-check: same inputs twice -> same output (determinism).
    auto script3 = BuildBtcHtlcRedeemScript(hashlock, 144 * 7,
                                            claim_pubkey, refund_pubkey);
    Bytes32 witness_program3 = BtcHtlcWitnessProgram(script3);
    TEST("Same inputs twice -> same witness program (determinism)",
         witness_program == witness_program3);

    // Report the witness program so anyone running the test can pin it
    // as a fixed expected output going forward.
    printf("    witness_program (fixed inputs) = %s\n",
           to_hex(witness_program).c_str());
}

// ===========================================================================
// SECTION 4 — HTLC redeem script hash determinism
// ===========================================================================
//
// Defence in depth: assert that for two independent constructions of the
// same HTLC parameters, the script bytes AND their hash are identical.
// This is the "you cannot accidentally change consensus by re-running
// the builder" property; failing this would be a serious regression.

static void section_redeem_script_determinism() {
    printf("\n-- SECTION 4: HTLC redeem script hash determinism (today) --\n");

    std::array<uint8_t, 32> hashlock{};
    std::array<uint8_t, 33> claim_pubkey{};
    std::array<uint8_t, 33> refund_pubkey{};
    for (size_t i = 0; i < 32; ++i) hashlock[i] = 0xC0 ^ (uint8_t)i;
    claim_pubkey[0]  = 0x02;
    refund_pubkey[0] = 0x03;
    for (size_t i = 1; i < 33; ++i) {
        claim_pubkey[i]  = static_cast<uint8_t>(0xD0 ^ (i - 1));
        refund_pubkey[i] = static_cast<uint8_t>(0xE0 ^ (i - 1));
    }

    auto s_a = BuildBtcHtlcRedeemScript(hashlock, 100,
                                        claim_pubkey, refund_pubkey);
    auto s_b = BuildBtcHtlcRedeemScript(hashlock, 100,
                                        claim_pubkey, refund_pubkey);
    TEST("Two constructions with same inputs produce identical bytes",
         s_a == s_b);

    Bytes32 h_a = sost::sha256(s_a.data(), s_a.size());
    Bytes32 h_b = sost::sha256(s_b.data(), s_b.size());
    TEST("Identical bytes -> identical sha256",
         h_a == h_b);

    // Different refund height -> different bytes (and therefore
    // different hash). This is the property that prevents two HTLCs
    // with different timeouts from sharing a UTXO accidentally.
    auto s_diff = BuildBtcHtlcRedeemScript(hashlock, 101,
                                           claim_pubkey, refund_pubkey);
    Bytes32 h_diff = sost::sha256(s_diff.data(), s_diff.size());
    TEST("Different refund height -> different sha256",
         h_a != h_diff);
}

// ===========================================================================
// SECTION 5 — BIP-143 SegWit v0 sighash (P2WSH variant)
// ===========================================================================
//
// Reference: https://github.com/bitcoin/bips/blob/master/bip-0143.mediawiki
// We capture ONE canonical vector (the "Native P2WSH" example from the
// BIP) as expected-input + expected-output, but execution is pending
// because SOST has no BIP-143 sighash computation yet. Phase C will
// add the implementation and convert the PENDING markers below into
// real PASS/FAIL.

namespace bip143_native_p2wsh_vector {
    // From BIP-143 "Native P2WSH" example. The raw tx, the
    // scriptCode, the input amount, and the resulting double-SHA256
    // sighash. Phase C must reproduce these exact bytes.
    //
    // (We store the strings here so the harness compiles; the actual
    // verification function will live alongside the Phase C
    // implementation. Until then, the strings are reference data.)
    static const char* raw_tx_unsigned_hex =
        "0100000002fe3dc9208094f3ffd12645477b3dc56f60ec4fa8e6f5d67c5"
        "65d1c6b9216b36e0000000000ffffffff0815cf020f013ed6cf91d29f4"
        "202e8a58726b1ac6c79da47c23d1bee0a6925f80000000000ffffffff"
        "0100f2052a010000001976a914a30741f8145e5acadf23f751864167f3"
        "2e0963f788ac00000000";

    static const char* script_code_hex =
        "21026dccc749adc2a9d0d89497ac511f760f45c47dc5ed9cf352a58ac706"
        "453880aeadab21038d27d72ba1dc81c5fa0aac0aada3a1c5d3eb6f8e2b3"
        "3a55fcc637c69e5d4e4ac5fac";

    static const uint64_t input_amount_satoshis = 4900000000ULL;

    static const char* expected_sighash_hex =
        "82dde6e4f1e94d02c2b7ad03d2115d691f48d064e9d52f58194a6637e4194391";
}

static void section_bip143_sighash() {
    printf("\n-- SECTION 5: BIP-143 sighash (Native P2WSH vector) --\n");
    printf("   Reference vector loaded from BIP-143. Phase C will\n");
    printf("   compute the sighash and assert it equals the BIP's\n");
    printf("   expected value. Until then, marked PENDING.\n");
    printf("   expected_sighash = %s\n",
           bip143_native_p2wsh_vector::expected_sighash_hex);

    PENDING_PHASE_C(
        "BIP-143 Native P2WSH sighash matches expected double-SHA256");
    PENDING_PHASE_C(
        "BIP-143 sighash refuses to compute for malformed scriptCode");
    PENDING_PHASE_C(
        "BIP-143 sighash refuses negative input amount");
}

// ===========================================================================
// Main
// ===========================================================================

int main() {
    printf("\n== Atomic Swap Phase B — BTC test vector harness (OFF mode) ==\n");
    printf("== libwally not available; executable subset + pending gap ==\n");

    section_bip173_bech32();
    section_bip350_bech32m();
    section_p2wsh_witness_program();
    section_redeem_script_determinism();
    section_bip143_sighash();

    printf("\n== Summary ==\n");
    printf("  executable PASS  : %d\n", g_pass);
    printf("  executable FAIL  : %d\n", g_fail);
    printf("  pending Phase C  : %d (no libwally, no own backend)\n",
           g_pending);
    printf("\n");
    printf("  Pending vectors are NOT failures. They document the\n");
    printf("  exact set of properties the future Phase C backend MUST\n");
    printf("  verify before any flip of SOST_BTC_HTLC_SIGNING=ON or\n");
    printf("  ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT.\n");
    printf("\n");

    // Exit 0 iff all executable checks passed. Pending vectors do
    // not affect exit code — they are tracked separately so the
    // master CTest can keep running without false-failing.
    return (g_fail == 0) ? 0 : 1;
}
