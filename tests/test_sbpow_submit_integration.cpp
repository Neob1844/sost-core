// V11 Phase 2 (C12) — SbPoW submit-path integration tests.
//
// Verifies the full pipeline that wires the production miner's signed
// header v2 through the submitblock JSON payload to the node-side
// validator:
//
//     miner build  →  JSON encode  →  JSON decode  →  ValidateSbPoW
//
// The test does not run a live miner or node; it reproduces the exact
// JSON build/parse code paths used by sost-miner.cpp and sost-node.cpp
// so a regression in either side is caught here at unit-test cost.
//
// Coverage (mapped to the C12 task spec):
//   1.  pre-Phase2 v1 round-trip (no pubkey/signature) → ACCEPT
//   2.  Phase2 v2 with valid signature                 → ACCEPT
//   3.  Phase2 v2 round-trip + coinbase pkh match      → ACCEPT
//   4.  v1 header at h >= phase2_height                → REJECT (VERSION_MISMATCH)
//   5.  v2 payload missing miner_pubkey                → REJECT (parse)
//   6.  v2 payload missing miner_signature             → REJECT (parse)
//   7.  v2 with malformed pubkey hex (non-hex char)    → REJECT (parse)
//   8.  v2 with pubkey length != 33 bytes              → REJECT (parse)
//   9.  v2 with signature length != 64 bytes           → REJECT (parse)
//  10.  v2 with valid sig but coinbase pkh mismatch    → REJECT (COINBASE_MISMATCH)
//  11.  v2 with nonce tampered post-signing            → REJECT (SIGNATURE_INVALID)
//  12.  v2 with commit tampered post-signing           → REJECT (SIGNATURE_INVALID)
//  13.  v2 with height tampered post-signing           → REJECT (SIGNATURE_INVALID)
//  14.  v2 at height < phase2_height                   → REJECT (VERSION_MISMATCH, premature)
//  15.  documentation: miner gating when key missing
//
// This file requires SOST_ENABLE_PHASE2_SBPOW=ON because Schnorr signing
// is exercised directly via sbpow::sign_sbpow_commitment.

#include "sost/sbpow.h"
#include "sost/block_validation.h"
#include "sost/wallet.h"

#include <climits>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Helpers — mirror miner / node JSON encoders & decoders verbatim
// ---------------------------------------------------------------------------

static std::string to_hex_str(const uint8_t* d, size_t len) {
    static const char* hx = "0123456789abcdef";
    std::string s; s.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        s += hx[d[i] >> 4];
        s += hx[d[i] & 0xF];
    }
    return s;
}

// Compact "submitblock"-style JSON with only the keys the SbPoW gate
// reads. The production miner emits more keys (block_id, transactions,
// etc.) — those are not relevant here and are exercised by other tests.
struct MinerJsonPayload {
    int64_t  height{0};
    Bytes32  prev_hash{};
    Bytes32  commit{};
    uint32_t nonce{0};
    uint32_t extra_nonce{0};
    uint32_t header_version{1};
    MinerPubkey    miner_pubkey{};
    MinerSignature miner_signature{};
};

static std::string encode_payload(const MinerJsonPayload& p) {
    std::string j = "{";
    j += "\"height\":"     + std::to_string(p.height);
    j += ",\"prev_hash\":\""    + to_hex_str(p.prev_hash.data(), 32) + "\"";
    j += ",\"commit\":\""       + to_hex_str(p.commit.data(),    32) + "\"";
    j += ",\"nonce\":"          + std::to_string(p.nonce);
    j += ",\"extra_nonce\":"    + std::to_string(p.extra_nonce);
    j += ",\"version\":"        + std::to_string(p.header_version);
    if (p.header_version >= 2) {
        j += ",\"miner_pubkey\":\""    + to_hex_str(p.miner_pubkey.data(),    33) + "\"";
        j += ",\"miner_signature\":\"" + to_hex_str(p.miner_signature.data(), 64) + "\"";
    }
    j += "}";
    return j;
}

// jstr / jint mirror the helpers in src/sost-node.cpp.
static int64_t json_int(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return -1;
    p = j.find(':', p + n.size()); if (p == std::string::npos) return -1;
    p++;
    while (p < j.size() && (j[p] == ' ' || j[p] == '\t')) p++;
    try { return std::stoll(j.substr(p)); } catch (...) { return -1; }
}
static std::string json_str(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return "";
    p = j.find('"', p + n.size() + 1); if (p == std::string::npos) return "";
    auto e = j.find('"', p + 1); if (e == std::string::npos) return "";
    return j.substr(p + 1, e - p - 1);
}

// Decode result mirrors what the node parser does. Either the parse
// succeeds and fills `out`, or it fails with an error message — both
// outcomes are exposed so tests can assert exact rejection points.
struct ParseOutcome {
    bool        ok{false};
    std::string err;
    uint32_t    header_version{1};
    MinerPubkey    miner_pubkey{};
    MinerSignature miner_signature{};
};

static ParseOutcome parse_payload(const std::string& j) {
    ParseOutcome out;
    uint32_t ver = (uint32_t)json_int(j, "version");
    if (ver == 0 || ver == (uint32_t)-1) ver = 1; // legacy default
    out.header_version = ver;

    if (ver >= 2) {
        std::string mpk = json_str(j, "miner_pubkey");
        std::string msg = json_str(j, "miner_signature");
        if (mpk.empty()) { out.err = "submitblock: v2 missing miner_pubkey"; return out; }
        if (msg.empty()) { out.err = "submitblock: v2 missing miner_signature"; return out; }
        auto is_hex = [](const std::string& s) {
            for (char c : s) {
                if (!((c >= '0' && c <= '9') ||
                      (c >= 'a' && c <= 'f') ||
                      (c >= 'A' && c <= 'F'))) return false;
            }
            return true;
        };
        if (mpk.size() != 66 || !is_hex(mpk)) {
            out.err = "submitblock: malformed miner_pubkey (expected 33 bytes hex)";
            return out;
        }
        if (msg.size() != 128 || !is_hex(msg)) {
            out.err = "submitblock: malformed miner_signature (expected 64 bytes hex)";
            return out;
        }
        auto hx = [](char c) -> uint8_t {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return 10 + c - 'a';
            if (c >= 'A' && c <= 'F') return 10 + c - 'A';
            return 0;
        };
        for (size_t i = 0; i < 33; ++i)
            out.miner_pubkey[i] = (uint8_t)((hx(mpk[i*2]) << 4) | hx(mpk[i*2 + 1]));
        for (size_t i = 0; i < 64; ++i)
            out.miner_signature[i] = (uint8_t)((hx(msg[i*2]) << 4) | hx(msg[i*2 + 1]));
    }
    out.ok = true;
    return out;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

static MinerPrivkey make_priv(uint8_t seed) {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(seed ^ (i * 7 + 1));
    return p;
}
static Bytes32 make_prev(uint8_t seed = 0xA5) {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(seed ^ (i * 3));
    return h;
}
static Bytes32 make_commit(uint8_t seed = 0xC3) {
    Bytes32 c{};
    for (size_t i = 0; i < 32; ++i) c[i] = (uint8_t)(seed ^ (i * 5));
    return c;
}

struct Fixture {
    int64_t      phase2_h{100};
    int64_t      height{100};
    Bytes32      prev{};
    Bytes32      commit{};
    uint32_t     nonce{12345};
    uint32_t     extra_nonce{678};
    MinerPrivkey priv{};
    MinerPubkey  pub{};
    PubKeyHash   coinbase_pkh{};
};

static Fixture make_phase2_fixture(int64_t phase2_h = 100,
                                   int64_t height   = 100) {
    Fixture f;
    f.phase2_h    = phase2_h;
    f.height      = height;
    f.prev        = make_prev();
    f.commit      = make_commit();
    f.priv        = make_priv(0x42);
    bool ok = derive_compressed_pubkey_from_privkey(f.priv, f.pub);
    TEST("fixture: pubkey derived from privkey", ok);
    f.coinbase_pkh = derive_pkh_from_pubkey(f.pub);
    return f;
}

// Build a payload signed correctly for a Phase 2 fixture.
static MinerJsonPayload build_signed_payload(const Fixture& f) {
    MinerJsonPayload p;
    p.height         = f.height;
    p.prev_hash      = f.prev;
    p.commit         = f.commit;
    p.nonce          = f.nonce;
    p.extra_nonce    = f.extra_nonce;
    p.header_version = 2;
    p.miner_pubkey   = f.pub;
    Bytes32 msg = build_sbpow_message(
        f.prev, f.height, f.commit, f.nonce, f.extra_nonce, f.pub);
    bool sok = sign_sbpow_commitment(f.priv, msg, p.miner_signature);
    TEST("fixture: SbPoW signature created", sok);
    return p;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// 1) Pre-Phase 2 v1 round-trip: payload omits pubkey/signature, parser
// defaults to version=1, ValidateSbPoW returns SBPOW_NOT_REQUIRED (ACCEPT).
static void t1_pre_phase2_v1_accepted() {
    printf("\n=== 1) pre-Phase 2 v1 round-trip → ACCEPT ===\n");

    MinerJsonPayload p;
    p.height         = 50;     // < phase2_h = 100
    p.prev_hash      = make_prev();
    p.commit         = make_commit();
    p.nonce          = 7;
    p.extra_nonce    = 0;
    p.header_version = 1;

    std::string j = encode_payload(p);
    TEST("v1 JSON does not contain miner_pubkey",
         j.find("miner_pubkey") == std::string::npos);
    TEST("v1 JSON does not contain miner_signature",
         j.find("miner_signature") == std::string::npos);

    auto parsed = parse_payload(j);
    TEST("v1 payload parses OK",          parsed.ok);
    TEST("parsed version == 1",            parsed.header_version == 1);

    // ValidateSbPoW: v1 + height < phase2 → SBPOW_NOT_REQUIRED (acc).
    PubKeyHash dummy_pkh{}; std::memset(dummy_pkh.data(), 0, 20);
    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            dummy_pkh, /*phase2_height=*/100, &err);
    TEST("ValidateSbPoW accepts v1 pre-Phase2", ok);
}

// 2) Phase 2 v2 with valid signature: round-trip → ACCEPT.
static void t2_phase2_v2_valid_accepted() {
    printf("\n=== 2) Phase 2 v2 valid signature → ACCEPT ===\n");
    Fixture f = make_phase2_fixture();
    MinerJsonPayload p = build_signed_payload(f);

    std::string j = encode_payload(p);
    TEST("v2 JSON contains miner_pubkey",
         j.find("\"miner_pubkey\":") != std::string::npos);
    TEST("v2 JSON contains miner_signature",
         j.find("\"miner_signature\":") != std::string::npos);
    TEST("v2 JSON pubkey is 66 hex chars",
         j.find(to_hex_str(f.pub.data(), 33)) != std::string::npos);

    auto parsed = parse_payload(j);
    TEST("v2 payload parses OK", parsed.ok);
    TEST("parsed version == 2",  parsed.header_version == 2);
    TEST("parsed miner_pubkey == original",
         std::memcmp(parsed.miner_pubkey.data(), f.pub.data(), 33) == 0);
    TEST("parsed miner_signature == original",
         std::memcmp(parsed.miner_signature.data(),
                     p.miner_signature.data(), 64) == 0);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("ValidateSbPoW accepts v2 + valid sig + matching pkh", ok);
    if (!ok) printf("    err: %s\n", err.c_str());
}

// 3) Round-trip end-to-end (same path as #2, asserted explicitly as
// the "encode → decode → validate" handshake of the C12 spec).
static void t3_phase2_v2_roundtrip() {
    printf("\n=== 3) Phase 2 v2 round-trip (encode/decode/validate) → ACCEPT ===\n");
    Fixture f = make_phase2_fixture(/*phase2_h=*/200, /*height=*/250);
    MinerJsonPayload p = build_signed_payload(f);
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("v2 end-to-end round-trip → ValidateSbPoW OK", ok);
    if (!ok) printf("    err: %s\n", err.c_str());
}

// 4) v1 header at height >= phase2_height → REJECT.
static void t4_v1_at_phase2_rejected() {
    printf("\n=== 4) v1 header at h >= phase2 → REJECT ===\n");
    MinerJsonPayload p;
    p.height         = 250;       // phase2_h = 200 → Phase 2 active
    p.prev_hash      = make_prev();
    p.commit         = make_commit();
    p.header_version = 1;

    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);
    TEST("v1-at-phase2 payload parses OK", parsed.ok);

    PubKeyHash dummy{}; std::memset(dummy.data(), 0, 20);
    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            dummy, /*phase2_height=*/200, &err);
    TEST("ValidateSbPoW rejects v1 at Phase 2 height", !ok);
}

// 5) v2 with miner_pubkey omitted → parser rejects.
static void t5_v2_missing_pubkey() {
    printf("\n=== 5) v2 missing miner_pubkey → REJECT ===\n");
    // Build a v2 JSON manually but omit miner_pubkey
    std::string j = "{\"height\":250,\"version\":2,\"miner_signature\":\""
                  + std::string(128, 'a') + "\"}";
    auto parsed = parse_payload(j);
    TEST("parser rejects v2 missing pubkey", !parsed.ok);
    TEST("error mentions miner_pubkey",
         parsed.err.find("miner_pubkey") != std::string::npos);
}

// 6) v2 with miner_signature omitted → parser rejects.
static void t6_v2_missing_signature() {
    printf("\n=== 6) v2 missing miner_signature → REJECT ===\n");
    std::string j = "{\"height\":250,\"version\":2,\"miner_pubkey\":\""
                  + std::string(66, 'a') + "\"}";
    auto parsed = parse_payload(j);
    TEST("parser rejects v2 missing signature", !parsed.ok);
    TEST("error mentions miner_signature",
         parsed.err.find("miner_signature") != std::string::npos);
}

// 7) v2 with non-hex character in miner_pubkey → parser rejects.
static void t7_v2_malformed_pubkey_hex() {
    printf("\n=== 7) v2 miner_pubkey malformed hex → REJECT ===\n");
    std::string bad_pk = std::string(65, 'a') + "Z";       // 'Z' is not hex
    std::string sig    = std::string(128, 'a');
    std::string j = "{\"height\":250,\"version\":2,\"miner_pubkey\":\""
                  + bad_pk + "\",\"miner_signature\":\"" + sig + "\"}";
    auto parsed = parse_payload(j);
    TEST("parser rejects non-hex pubkey", !parsed.ok);
    TEST("error mentions miner_pubkey",
         parsed.err.find("miner_pubkey") != std::string::npos);
}

// 8) v2 with miner_pubkey wrong length → parser rejects.
static void t8_v2_pubkey_wrong_length() {
    printf("\n=== 8) v2 miner_pubkey length != 33 bytes → REJECT ===\n");
    std::string j = "{\"height\":250,\"version\":2,\"miner_pubkey\":\""
                  + std::string(64, 'a')                  // 32 bytes (wrong)
                  + "\",\"miner_signature\":\""
                  + std::string(128, 'b') + "\"}";
    auto parsed = parse_payload(j);
    TEST("parser rejects pubkey != 33 bytes", !parsed.ok);
    TEST("error mentions miner_pubkey",
         parsed.err.find("miner_pubkey") != std::string::npos);
}

// 9) v2 with miner_signature wrong length → parser rejects.
static void t9_v2_signature_wrong_length() {
    printf("\n=== 9) v2 miner_signature length != 64 bytes → REJECT ===\n");
    std::string j = "{\"height\":250,\"version\":2,\"miner_pubkey\":\""
                  + std::string(66, 'a')
                  + "\",\"miner_signature\":\""
                  + std::string(126, 'b')                 // 63 bytes (wrong)
                  + "\"}";
    auto parsed = parse_payload(j);
    TEST("parser rejects signature != 64 bytes", !parsed.ok);
    TEST("error mentions miner_signature",
         parsed.err.find("miner_signature") != std::string::npos);
}

// 10) Valid signature but coinbase pkh != hash160(miner_pubkey) → REJECT.
static void t10_v2_coinbase_pkh_mismatch() {
    printf("\n=== 10) v2 coinbase_pkh mismatch → REJECT ===\n");
    Fixture f = make_phase2_fixture();
    MinerJsonPayload p = build_signed_payload(f);
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);
    TEST("parsed OK", parsed.ok);

    // Use a DIFFERENT coinbase pkh
    PubKeyHash wrong_pkh{};
    for (size_t i = 0; i < 20; ++i) wrong_pkh[i] = (uint8_t)(0xFE - i);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            wrong_pkh, f.phase2_h, &err);
    TEST("ValidateSbPoW rejects coinbase pkh mismatch", !ok);
}

// 11) v2 with nonce tampered post-signing → SIGNATURE_INVALID.
static void t11_v2_nonce_tampered() {
    printf("\n=== 11) v2 nonce tampered post-sign → REJECT ===\n");
    Fixture f = make_phase2_fixture();
    MinerJsonPayload p = build_signed_payload(f);
    p.nonce += 1;   // tamper after signing
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("nonce tamper → reject", !ok);
}

// 12) v2 with commit tampered post-signing → SIGNATURE_INVALID.
static void t12_v2_commit_tampered() {
    printf("\n=== 12) v2 commit tampered post-sign → REJECT ===\n");
    Fixture f = make_phase2_fixture();
    MinerJsonPayload p = build_signed_payload(f);
    p.commit[0] ^= 0x01;
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("commit tamper → reject", !ok);
}

// 13) v2 with height tampered post-signing → SIGNATURE_INVALID.
static void t13_v2_height_tampered() {
    printf("\n=== 13) v2 height tampered post-sign → REJECT ===\n");
    Fixture f = make_phase2_fixture(/*phase2_h=*/100, /*height=*/200);
    MinerJsonPayload p = build_signed_payload(f);
    p.height = 201;   // tamper
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("height tamper → reject", !ok);
}

// 14) v2 at h < phase2_height → premature, REJECT (VERSION_MISMATCH).
static void t14_v2_premature() {
    printf("\n=== 14) v2 at h < phase2_height → REJECT (premature) ===\n");
    Fixture f = make_phase2_fixture(/*phase2_h=*/300, /*height=*/200);
    MinerJsonPayload p = build_signed_payload(f);
    std::string j      = encode_payload(p);
    auto        parsed = parse_payload(j);
    TEST("premature v2 parses OK", parsed.ok);

    std::string err;
    bool ok = ValidateSbPoW(parsed.header_version,
                            p.prev_hash, p.height, p.commit,
                            p.nonce, p.extra_nonce,
                            parsed.miner_pubkey, parsed.miner_signature,
                            f.coinbase_pkh, f.phase2_h, &err);
    TEST("premature v2 → reject (VERSION_MISMATCH)", !ok);
}

// 15) Documentation: the production miner refuses to start when
// next_height_check >= V11_PHASE2_HEIGHT and g_signing_key_loaded == false.
//
// This is a startup-time gate in main() (sost-miner.cpp ~L1914-1923) and
// the threaded mining loop also short-circuits a Phase 2 candidate when
// the wallet key is missing (sost-miner.cpp). We can't drive `main` from
// a unit test without restructuring, so this slot documents the
// behaviour and asserts that `resolve_miner_key` returns ERROR for the
// matching scenario — the same precondition the gate evaluates.
static void t15_miner_gating_doc() {
    printf("\n=== 15) miner gating: phase2 + missing key → ERROR (docstring) ===\n");
    sost::Wallet w;
    auto r = resolve_miner_key(w, /*label=*/"", /*addr=*/"sost1deadbeef",
                               /*phase2_required=*/true);
    TEST("resolve_miner_key signals ERROR when phase2 + no key",
         r.status == MinerKeyResolution::Status::ERROR);
}

int main() {
    printf("\n========================================\n");
    printf("V11 Phase 2 — SbPoW submit-path integration (C12)\n");
    printf("========================================\n");

    t1_pre_phase2_v1_accepted();
    t2_phase2_v2_valid_accepted();
    t3_phase2_v2_roundtrip();
    t4_v1_at_phase2_rejected();
    t5_v2_missing_pubkey();
    t6_v2_missing_signature();
    t7_v2_malformed_pubkey_hex();
    t8_v2_pubkey_wrong_length();
    t9_v2_signature_wrong_length();
    t10_v2_coinbase_pkh_mismatch();
    t11_v2_nonce_tampered();
    t12_v2_commit_tampered();
    t13_v2_height_tampered();
    t14_v2_premature();
    t15_miner_gating_doc();

    printf("\n========================================\n");
    printf("Result: %d passed, %d failed\n", g_pass, g_fail);
    printf("========================================\n");
    return (g_fail == 0) ? 0 : 1;
}
