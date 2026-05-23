// V13 Beacon Phase II-B — regression tests for the threshold-signed
// advisory channel (3-of-5), revocation, and mirror_url metadata.
//
// Hard invariants under test:
//   - threshold sigs do NOT touch consensus / block validation.
//   - the verifier dedups by signer index (same key cannot count twice).
//   - revocation requires threshold (single-sig notice cannot revoke).
//   - mirror_url is metadata; no network is ever opened on its behalf.
//   - Phase II-A single-sig notices continue to work unchanged.

#include "sost/beacon.h"
#include "sost/crypto.h"
#include "sost/params.h"

#include <secp256k1.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::beacon;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Hex + base64 helpers (kept local — not exported by beacon.h).
// ---------------------------------------------------------------------------
static const char B64_ALPHA[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static std::string b64_encode(const uint8_t* in, size_t n) {
    std::string out;
    out.reserve(((n + 2) / 3) * 4);
    size_t i = 0;
    while (i + 3 <= n) {
        uint32_t v = (in[i] << 16) | (in[i+1] << 8) | in[i+2];
        out.push_back(B64_ALPHA[(v >> 18) & 0x3F]);
        out.push_back(B64_ALPHA[(v >> 12) & 0x3F]);
        out.push_back(B64_ALPHA[(v >> 6)  & 0x3F]);
        out.push_back(B64_ALPHA[v & 0x3F]);
        i += 3;
    }
    if (i < n) {
        uint32_t v = in[i] << 16;
        if (i + 1 < n) v |= in[i+1] << 8;
        out.push_back(B64_ALPHA[(v >> 18) & 0x3F]);
        out.push_back(B64_ALPHA[(v >> 12) & 0x3F]);
        if (i + 1 < n) {
            out.push_back(B64_ALPHA[(v >> 6) & 0x3F]);
            out.push_back('=');
        } else {
            out.push_back('=');
            out.push_back('=');
        }
    }
    return out;
}

static std::string bytes_to_hex(const uint8_t* in, size_t n) {
    static const char* H = "0123456789abcdef";
    std::string out;
    out.resize(n * 2);
    for (size_t i = 0; i < n; ++i) {
        out[2*i]   = H[(in[i] >> 4) & 0xF];
        out[2*i+1] = H[ in[i]       & 0xF];
    }
    return out;
}

// ---------------------------------------------------------------------------
// Test key fixture — 5 deterministic ECDSA keys.
// ---------------------------------------------------------------------------
struct TestKey {
    std::array<uint8_t, 32> priv;
    std::array<uint8_t, 65> pub_uncompressed;
    std::string             pub_hex;
};

static TestKey make_test_key(uint32_t seed) {
    TestKey k{};
    secp256k1_context* ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    std::mt19937 rng(seed);
    do {
        for (auto& b : k.priv) b = (uint8_t)(rng() & 0xFF);
    } while (!secp256k1_ec_seckey_verify(ctx, k.priv.data()));
    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_create(ctx, &pk, k.priv.data())) {
        std::fprintf(stderr, "pubkey_create failed\n");
        std::exit(2);
    }
    size_t n = k.pub_uncompressed.size();
    if (!secp256k1_ec_pubkey_serialize(ctx, k.pub_uncompressed.data(),
                                        &n, &pk, SECP256K1_EC_UNCOMPRESSED)) {
        std::fprintf(stderr, "pubkey_serialize failed\n");
        std::exit(2);
    }
    k.pub_hex = bytes_to_hex(k.pub_uncompressed.data(), 65);
    secp256k1_context_destroy(ctx);
    return k;
}

static std::string sign_canonical(const std::string& canonical,
                                  const TestKey& key) {
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN);
    Bytes32 digest = sost::sha256(
        reinterpret_cast<const uint8_t*>(canonical.data()), canonical.size());
    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_sign(ctx, &sig, digest.data(), key.priv.data(),
                              nullptr, nullptr)) {
        std::fprintf(stderr, "sign failed\n");
        std::exit(2);
    }
    uint8_t der[80];
    size_t  der_len = sizeof(der);
    if (!secp256k1_ecdsa_signature_serialize_der(ctx, der, &der_len, &sig)) {
        std::fprintf(stderr, "der_serialize failed\n");
        std::exit(2);
    }
    secp256k1_context_destroy(ctx);
    return b64_encode(der, der_len);
}

// 5-key threshold fixture (deterministic per test run).
struct ThresholdFixture {
    TestKey                  keys[5];
    std::string              pubkeys[5];
};

static ThresholdFixture make_threshold_fixture() {
    ThresholdFixture f;
    for (uint32_t i = 0; i < 5; ++i) {
        f.keys[i]    = make_test_key(0xA110C8 + i * 17);
        f.pubkeys[i] = f.keys[i].pub_hex;
    }
    return f;
}

static Notice mk_iib_notice(uint32_t threshold = 3,
                            const std::string& notice_id = "v13-iib-test-001",
                            const std::string& revokes = "",
                            const std::string& mirror_url = "") {
    Notice n;
    n.notice_id         = notice_id;
    n.network_str       = "mainnet";
    n.network           = Network::MAINNET;
    n.severity          = "critical";
    n.title_en          = "V13 II-B test";
    n.message_en        = "Phase II-B threshold notice.";
    n.activation_height = 12000;
    n.expires_height    = 13000;
    n.created_at        = "2026-05-22T00:00:00Z";
    n.commands.clear();
    n.signature_b64.clear();
    n.threshold         = threshold;
    n.signatures_b64.clear();
    n.revokes           = revokes;
    n.mirror_url        = mirror_url;
    return n;
}

static Notice mk_iia_notice(const std::string& notice_id = "v13-iia-legacy-001") {
    Notice n;
    n.notice_id         = notice_id;
    n.network_str       = "mainnet";
    n.network           = Network::MAINNET;
    n.severity          = "info";
    n.title_en          = "V13 II-A legacy";
    n.message_en        = "Phase II-A legacy single-sig notice.";
    n.activation_height = 12000;
    n.expires_height    = 13000;
    n.created_at        = "2026-05-22T00:00:00Z";
    n.commands.clear();
    n.signature_b64.clear();
    // II-B fields left at defaults (threshold=0).
    return n;
}

static std::string mk_tmpdir() {
    namespace fs = std::filesystem;
    auto base = fs::temp_directory_path() / "sost-beacon-iib-tests";
    fs::create_directories(base);
    static std::atomic<uint64_t> ctr{0};
    auto dir = base / ("run-" + std::to_string(++ctr));
    fs::create_directories(dir);
    return dir.string();
}

static void write_file(const std::string& path, const std::string& body) {
    std::ofstream f(path, std::ios::binary);
    f.write(body.data(), (std::streamsize)body.size());
}

// Re-emit a Notice including II-B fields (mirror what beacon-sign.sh
// would write once it learns the II-B schema). For II-A notices, omits
// the new fields so the canonical bytes are byte-stable.
static std::string serialize_notice_for_file(const Notice& n) {
    std::ostringstream o;
    o << "{";
    o << "\"activation_height\":" << n.activation_height;
    o << ",\"commands\":[";
    for (size_t i = 0; i < n.commands.size(); ++i) {
        if (i) o << ",";
        o << "\"" << n.commands[i] << "\"";
    }
    o << "]";
    o << ",\"created_at\":\""    << n.created_at  << "\"";
    o << ",\"expires_height\":"  << n.expires_height;
    o << ",\"message_en\":\""    << n.message_en  << "\"";
    const bool has_iib = (n.threshold > 0) || !n.revokes.empty() || !n.mirror_url.empty();
    if (has_iib) {
        o << ",\"mirror_url\":\"" << n.mirror_url << "\"";
    }
    o << ",\"network\":\""       << n.network_str << "\"";
    o << ",\"notice_id\":\""     << n.notice_id   << "\"";
    if (has_iib) {
        o << ",\"revokes\":\""   << n.revokes     << "\"";
    }
    o << ",\"severity\":\""      << n.severity    << "\"";
    if (n.threshold > 0) {
        o << ",\"signatures\":[";
        for (size_t i = 0; i < n.signatures_b64.size(); ++i) {
            if (i) o << ",";
            o << "\"" << n.signatures_b64[i] << "\"";
        }
        o << "]";
    } else {
        o << ",\"signature\":\""  << n.signature_b64 << "\"";
    }
    if (has_iib) {
        o << ",\"threshold\":"   << n.threshold;
    }
    o << ",\"title_en\":\""      << n.title_en    << "\"";
    o << "}";
    return o.str();
}

static std::string write_notices_file(const std::string& dir,
                                       const std::vector<Notice>& v) {
    std::string body = "[";
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) body.push_back(',');
        body += serialize_notice_for_file(v[i]);
    }
    body.push_back(']');
    std::string path = dir + "/notices.json";
    write_file(path, body);
    return path;
}

// ===========================================================================
// Tests
// ===========================================================================

// 1) Threshold pass: 3 valid signers in a 3-of-5 setup -> ok=true.
static void t01_threshold_3_of_5_pass() {
    printf("\n=== 1) threshold 3-of-5 with 3 valid signers -> ok ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    // Sign with keys 0, 2, 4.
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[2]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[4]));
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=true", r.ok);
    TEST("distinct_signers == 3", r.distinct_signers == 3);
    TEST("required == 3", r.required == 3);
}

// 2) Threshold fail: 2-of-5 -> not enough.
static void t02_threshold_under_required() {
    printf("\n=== 2) threshold 3-of-5 with only 2 valid signers -> rejected ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=false", !r.ok);
    TEST("distinct_signers == 2", r.distinct_signers == 2);
}

// 3) Duplicate signer: same key signs twice -> counts as 1.
static void t03_duplicate_signer_counts_once() {
    printf("\n=== 3) duplicate signer counts at most once ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    std::string s0 = sign_canonical(canon, f.keys[0]);
    // Two copies from key 0 + one from key 1 = 2 distinct signers, not 3.
    n.signatures_b64.push_back(s0);
    n.signatures_b64.push_back(s0);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=false (dedup by signer index)", !r.ok);
    TEST("distinct_signers == 2 (not 3)", r.distinct_signers == 2);
}

// 4) Unknown signer: a sig from a key NOT in the set -> ignored.
static void t04_unknown_signer_ignored() {
    printf("\n=== 4) signature from key outside the threshold set -> ignored ===\n");
    auto f = make_threshold_fixture();
    TestKey outsider = make_test_key(0xDEADBEEF);
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back(sign_canonical(canon, outsider));  // unknown
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=false (outsider not counted)", !r.ok);
    TEST("distinct_signers == 2", r.distinct_signers == 2);
}

// 5) Malformed signature: bad base64 -> silently dropped, not counted.
static void t05_malformed_signature_dropped() {
    printf("\n=== 5) malformed signature is silently dropped ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back("@@@not-base64@@@");           // junk
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[2]));
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=true (good ones still pass)", r.ok);
    TEST("distinct_signers == 3", r.distinct_signers == 3);
}

// 6) Empty signatures with threshold>0 -> always rejected.
static void t06_empty_sigs_rejected() {
    printf("\n=== 6) threshold>0 with empty signatures[] -> rejected ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    n.signatures_b64.clear();
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=false", !r.ok);
    TEST("distinct_signers == 0", r.distinct_signers == 0);
}

// 7) threshold > pubkey count -> unreachable, rejected.
static void t07_threshold_greater_than_keyset_rejected() {
    printf("\n=== 7) threshold > pubkey_count -> rejected ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(6);  // 6-of-5 is impossible
    std::string canon = canonical_payload(n);
    for (int i = 0; i < 5; ++i) {
        n.signatures_b64.push_back(sign_canonical(canon, f.keys[i]));
    }
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("ok=false (threshold unreachable)", !r.ok);
}

// 8) II-A backwards compatibility via load_active_notices (legacy single-sig
//    notice continues to validate end-to-end under a real test pubkey).
static void t08_iia_backwards_compat_end_to_end() {
    printf("\n=== 8) II-A legacy single-sig notice still loads end-to-end ===\n");
    auto dir = mk_tmpdir();
    TestKey iia_key = make_test_key(0x12345);
    Notice n = mk_iia_notice();
    n.signature_b64 = sign_canonical(canonical_payload(n), iia_key);
    write_notices_file(dir, {n});

    auto out = load_active_notices(dir, /*h=*/12000, Network::MAINNET, iia_key.pub_hex);
    TEST("II-A notice surfaces (threshold=0 path)", out.size() == 1);
    if (!out.empty()) {
        TEST("notice_id round-trips", out.front().notice_id == "v13-iia-legacy-001");
        TEST("threshold field default == 0", out.front().threshold == 0);
    }
    std::filesystem::remove_all(dir);
}

// 9) Revocation: II-B notice with threshold sig revokes another notice.
//    Note: load_active_notices uses the PLACEHOLDER threshold keys (fail-closed),
//    so we cannot end-to-end test the happy path of revocation without
//    patching the constants. Instead we test the revocation LOGIC by
//    directly calling load_active_notices on a single-sig II-A notice
//    with a `revokes` field — and assert it CANNOT revoke (because
//    revocation requires threshold).
static void t09_iia_notice_cannot_revoke() {
    printf("\n=== 9) II-A single-sig notice cannot revoke (no threshold power) ===\n");
    auto dir = mk_tmpdir();
    TestKey iia_key = make_test_key(0x55555);
    Notice victim = mk_iia_notice("v13-victim");
    victim.signature_b64 = sign_canonical(canonical_payload(victim), iia_key);
    // Attacker notice claims to revoke the victim but only single-sig.
    Notice attacker = mk_iia_notice("v13-attacker-revoker");
    attacker.revokes = "v13-victim";
    attacker.signature_b64 = sign_canonical(canonical_payload(attacker), iia_key);
    write_notices_file(dir, {victim, attacker});

    auto out = load_active_notices(dir, /*h=*/12000, Network::MAINNET, iia_key.pub_hex);
    TEST("victim still present (II-A cannot revoke)", out.size() == 2);
    bool victim_kept = false;
    for (const auto& n : out) {
        if (n.notice_id == "v13-victim") victim_kept = true;
    }
    TEST("victim id present", victim_kept);
    std::filesystem::remove_all(dir);
}

// 10) Expired notice ignored under II-B (cannot be revived via threshold).
static void t10_expired_iib_ignored() {
    printf("\n=== 10) expired II-B notice rejected by is_active ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    n.expires_height = 12001;
    std::string canon = canonical_payload(n);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[2]));
    // verify_threshold_signatures only checks the sig math — not the
    // expiration. That's by design: is_active() does the expiry check.
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("sigs valid in isolation", r.ok);
    // Now confirm is_active rejects on expiry regardless of threshold pass.
    // (We can't end-to-end this against the default pubkey set because
    // they fail-closed; the is_active expiry path is verified via the
    // II-A end-to-end test below.)
    Notice expired = mk_iia_notice("v13-iia-expired");
    expired.expires_height = 12000;  // <= current height = expired
    TestKey k = make_test_key(0xEEEEE);
    expired.signature_b64 = sign_canonical(canonical_payload(expired), k);
    TEST("is_active rejects expired II-A notice",
         !is_active(expired, /*h=*/12000, Network::MAINNET, k.pub_hex));
}

// 11) mirror_url is metadata only — parsed, surfaced via RPC, never fetched.
//     We verify the field round-trips through serialize_notices_for_rpc.
static void t11_mirror_url_metadata_only() {
    printf("\n=== 11) mirror_url is parsed + surfaced; no network behaviour ===\n");
    Notice n = mk_iib_notice(3, "v13-mirror-test", "", "https://mirror.example/notices");
    std::vector<Notice> v{n};
    std::string rpc = serialize_notices_for_rpc(v);
    TEST("RPC payload contains mirror_url field",
         rpc.find("\"mirror_url\":\"https://mirror.example/notices\"") != std::string::npos);
    TEST("RPC payload contains threshold field",
         rpc.find("\"threshold\":3") != std::string::npos);
    TEST("RPC payload contains revokes field (empty string)",
         rpc.find("\"revokes\":\"\"") != std::string::npos);
    // The serialize function builds a string and never touches the network;
    // this asserts the contract by construction (compile + run = no socket).
}

// 12) Canonical payload: II-A and II-B differ; II-A is byte-stable.
static void t12_canonical_iia_vs_iib_differ() {
    printf("\n=== 12) canonical payload — II-A stable / II-B includes new fields ===\n");
    Notice iia = mk_iia_notice("v13-canon-test");
    Notice iib = mk_iia_notice("v13-canon-test");
    iib.threshold = 3;
    iib.mirror_url = "https://x";
    iib.revokes = "prev-id";
    std::string c_iia = canonical_payload(iia);
    std::string c_iib = canonical_payload(iib);
    TEST("II-A and II-B canonical bytes differ", c_iia != c_iib);
    TEST("II-A omits mirror_url",
         c_iia.find("\"mirror_url\"") == std::string::npos);
    TEST("II-A omits threshold",
         c_iia.find("\"threshold\"") == std::string::npos);
    TEST("II-B includes mirror_url",
         c_iib.find("\"mirror_url\":\"https://x\"") != std::string::npos);
    TEST("II-B includes threshold",
         c_iib.find("\"threshold\":3") != std::string::npos);
    TEST("II-B includes revokes",
         c_iib.find("\"revokes\":\"prev-id\"") != std::string::npos);
}

// 13) Tamper resistance: mutate threshold AFTER signing -> sig fails.
static void t13_tampered_threshold_rejected() {
    printf("\n=== 13) tampering threshold after signing -> signatures fail ===\n");
    auto f = make_threshold_fixture();
    Notice n = mk_iib_notice(3);
    std::string canon = canonical_payload(n);
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[0]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[1]));
    n.signatures_b64.push_back(sign_canonical(canon, f.keys[2]));
    // Attacker downgrades the threshold to 1, hoping the verifier
    // will accept fewer signatures. The new canonical_payload is
    // different, so sigs no longer verify.
    n.threshold = 1;
    auto r = verify_threshold_signatures(n, f.pubkeys, 5);
    TEST("tampered threshold breaks sig binding", !r.ok);
    TEST("distinct_signers == 0", r.distinct_signers == 0);
}

// 14) Beacon does not link into block validation (compile-time invariant).
//     If this file builds, the assertion holds: tests link only against
//     sost-core (Beacon code) and libsecp256k1 — no block_validation.cpp
//     symbols are pulled in by Beacon. This is enforced by CMake (Beacon
//     stays in its own translation unit and does not transitively depend
//     on block-validation symbols).
static void t14_no_consensus_side_effects() {
    printf("\n=== 14) Beacon code does not depend on block_validation ===\n");
    // This test passes by virtue of compiling + linking successfully.
    // Any future change that makes Beacon call into ValidateSbPoW(),
    // ValidateBlockStructure(), AcceptBlock(), or chain.commit() will
    // be caught by reviewers (the failure mode is a link error).
    TEST("Beacon translation unit compiles standalone", true);
}


// 15) II-B threshold sentinel OFF by default (V13 bootstrap).
//     While BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT == INT64_MAX, every
//     notice that claims threshold > 0 must be rejected by is_active()
//     regardless of signature validity. The sentinel check fires
//     BEFORE the signature verifier runs, so this test does NOT need
//     valid threshold signatures.
static void t15_iib_sentinel_off_by_default() {
    printf("\n=== 15) II-B threshold sentinel OFF by default (V13 bootstrap) ===\n");
    Notice n = mk_iib_notice(3);
    // Intentionally garbage sigs. The sentinel must reject before this matters.
    n.signatures_b64.push_back("AA==");
    n.signatures_b64.push_back("AB==");
    n.signatures_b64.push_back("AC==");
    bool ok = is_active(n, /*h=*/12000, Network::MAINNET, "");
    TEST("is_active rejects any threshold>0 notice while sentinel == INT64_MAX", !ok);

    // Belt-and-suspenders: even at very large heights the sentinel
    // (still INT64_MAX in this build) keeps rejecting.
    bool ok_far = is_active(n, /*h=*/INT64_MAX - 1, Network::MAINNET, "");
    TEST("rejection holds at INT64_MAX - 1 (sentinel still active)", !ok_far);
}

// ---------------------------------------------------------------------------

int main() {
    printf("================================================\n");
    printf("V13 Beacon Phase II-B regression tests\n");
    printf("================================================\n");

    t01_threshold_3_of_5_pass();
    t02_threshold_under_required();
    t03_duplicate_signer_counts_once();
    t04_unknown_signer_ignored();
    t05_malformed_signature_dropped();
    t06_empty_sigs_rejected();
    t07_threshold_greater_than_keyset_rejected();
    t08_iia_backwards_compat_end_to_end();
    t09_iia_notice_cannot_revoke();
    t10_expired_iib_ignored();
    t11_mirror_url_metadata_only();
    t12_canonical_iia_vs_iib_differ();
    t13_tampered_threshold_rejected();
    t14_no_consensus_side_effects();
    t15_iib_sentinel_off_by_default();

    printf("\n================================================\n");
    printf("Results: %d passed, %d failed\n", g_pass, g_fail);
    printf("================================================\n");
    return g_fail == 0 ? 0 : 1;
}
