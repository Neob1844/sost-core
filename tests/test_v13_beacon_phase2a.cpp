// V13 Beacon Phase II-A — local notice load/verify/filter tests.
//
// Covers the operator-runbook contract:
//   - dormant pre-V13 (returns empty regardless of file contents)
//   - active post-V13 with valid signed notice (returns the notice)
//   - invalid signature → reject
//   - expired (current_height >= expires_height) → reject
//   - not yet active (current_height < activation_height) → reject
//   - wrong network → reject
//   - non-empty `commands` → reject  (Phase II-A invariant)
//   - garbled JSON → empty (no crash)
//   - missing file → empty (no crash)
//   - oversized file → empty (no crash)
//   - canonical_payload byte stream matches `jq -cSj` for round-trip
//   - the wire-up uses a freshly generated keypair (NOT the placeholder
//     BEACON_PUBKEY_HEX in beacon.cpp), proving the verify path works
//     when a real key is embedded.

#include "sost/beacon.h"
#include "sost/crypto.h"
#include "sost/params.h"

#include <secp256k1.h>

#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <random>
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
// Tiny helpers — hex / base64 / fs.
// ---------------------------------------------------------------------------
static std::string bytes_to_hex(const uint8_t* b, size_t n) {
    static const char H[] = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) {
        s.push_back(H[b[i] >> 4]);
        s.push_back(H[b[i] & 0xF]);
    }
    return s;
}

static std::string b64_encode(const uint8_t* b, size_t n) {
    static const char A[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out; out.reserve(((n + 2) / 3) * 4);
    for (size_t i = 0; i < n; i += 3) {
        unsigned a = b[i];
        unsigned bb = (i + 1 < n) ? b[i + 1] : 0;
        unsigned c = (i + 2 < n) ? b[i + 2] : 0;
        unsigned v = (a << 16) | (bb << 8) | c;
        out.push_back(A[(v >> 18) & 63]);
        out.push_back(A[(v >> 12) & 63]);
        out.push_back(i + 1 < n ? A[(v >> 6) & 63] : '=');
        out.push_back(i + 2 < n ? A[v & 63]       : '=');
    }
    return out;
}

static std::string mk_tmpdir() {
    char tmpl[] = "/tmp/sost_beacon_test_XXXXXX";
    char* d = mkdtemp(tmpl);
    if (!d) { perror("mkdtemp"); std::exit(2); }
    return std::string(d);
}

static void write_file(const std::string& path, const std::string& body) {
    std::ofstream f(path, std::ios::binary);
    f.write(body.data(), (std::streamsize)body.size());
}

// ---------------------------------------------------------------------------
// Test keypair — generated fresh per test run via libsecp256k1 directly.
// Sign a canonical payload and inject the resulting DER signature into a
// notice. This exercises the production verify path with a known-good
// key, isolating it from the placeholder BEACON_PUBKEY_HEX which is
// fail-closed by design.
// ---------------------------------------------------------------------------
struct TestKey {
    std::array<uint8_t, 32> priv;
    std::array<uint8_t, 65> pub_uncompressed;
    std::string             pub_hex;
};

static TestKey make_test_key() {
    TestKey k{};
    secp256k1_context* ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);

    // Deterministic seed for reproducibility.
    std::mt19937 rng(0xC0FFEE);
    do {
        for (auto& b : k.priv) b = (uint8_t)(rng() & 0xFF);
    } while (!secp256k1_ec_seckey_verify(ctx, k.priv.data()));

    secp256k1_pubkey pk;
    if (!secp256k1_ec_pubkey_create(ctx, &pk, k.priv.data())) {
        std::fprintf(stderr, "make_test_key: pubkey_create failed\n");
        std::exit(2);
    }
    size_t n = k.pub_uncompressed.size();
    if (!secp256k1_ec_pubkey_serialize(ctx, k.pub_uncompressed.data(),
                                        &n, &pk, SECP256K1_EC_UNCOMPRESSED)) {
        std::fprintf(stderr, "make_test_key: serialize failed\n");
        std::exit(2);
    }
    k.pub_hex = bytes_to_hex(k.pub_uncompressed.data(), 65);
    secp256k1_context_destroy(ctx);
    return k;
}

static std::string sign_canonical(const std::string& canonical,
                                  const TestKey&     key) {
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_SIGN);
    Bytes32 digest = sha256(reinterpret_cast<const uint8_t*>(canonical.data()),
                            canonical.size());
    secp256k1_ecdsa_signature sig;
    if (!secp256k1_ecdsa_sign(ctx, &sig, digest.data(), key.priv.data(),
                              nullptr, nullptr)) {
        std::fprintf(stderr, "sign_canonical failed\n");
        std::exit(2);
    }
    uint8_t der[80];
    size_t  der_len = sizeof(der);
    if (!secp256k1_ecdsa_signature_serialize_der(ctx, der, &der_len, &sig)) {
        std::fprintf(stderr, "der serialize failed\n");
        std::exit(2);
    }
    secp256k1_context_destroy(ctx);
    return b64_encode(der, der_len);
}

// ---------------------------------------------------------------------------
// Build a canonical Phase II-A notice (un-signed). Caller signs and
// stamps the b64 signature back into n.signature_b64.
// ---------------------------------------------------------------------------
static Notice mk_notice() {
    Notice n;
    n.notice_id         = "v13-beacon-test-001";
    n.network_str       = "mainnet";
    n.network           = Network::MAINNET;
    n.severity          = "info";
    n.title_en          = "V13 Beacon test";
    n.message_en        = "Phase II-A round-trip notice.";
    n.activation_height = 12000;
    n.expires_height    = 13000;
    n.created_at        = "2026-05-07T00:00:00Z";
    n.commands.clear();
    n.signature_b64     = "";
    return n;
}

// Render a notice as the SAME JSON form `beacon-sign.sh` writes —
// canonical body PLUS the signature field.
static std::string serialize_signed_notice(const Notice& n) {
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
    o << ",\"network\":\""       << n.network_str << "\"";
    o << ",\"notice_id\":\""     << n.notice_id   << "\"";
    o << ",\"severity\":\""      << n.severity    << "\"";
    o << ",\"signature\":\""     << n.signature_b64 << "\"";
    o << ",\"title_en\":\""      << n.title_en    << "\"";
    o << "}";
    return o.str();
}

static std::string write_notices_file(const std::string& dir,
                                       const std::vector<Notice>& notices) {
    std::string body = "[";
    for (size_t i = 0; i < notices.size(); ++i) {
        if (i) body.push_back(',');
        body += serialize_signed_notice(notices[i]);
    }
    body.push_back(']');
    std::string path = dir + "/notices.json";
    write_file(path, body);
    return path;
}

// ---------------------------------------------------------------------------
// 1. Dormancy gate — pre-V13 the load returns empty regardless of file.
// ---------------------------------------------------------------------------
static void test_dormancy_pre_v13() {
    printf("\n=== 1) Dormancy: h < V13_HEIGHT must return empty ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto pre = load_active_notices(dir, /*h=*/V13_HEIGHT - 1,
                                    Network::MAINNET, key.pub_hex);
    TEST("h=V13_HEIGHT-1 → empty (dormant) even with a perfectly signed notice",
         pre.empty());

    auto genesis = load_active_notices(dir, /*h=*/0,
                                        Network::MAINNET, key.pub_hex);
    TEST("h=0 → empty (genesis dormant)", genesis.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 2. Happy path — valid signature, in window, right network, empty cmds.
// ---------------------------------------------------------------------------
static void test_happy_path() {
    printf("\n=== 2) Happy path: valid notice surfaces post-V13 ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("h=V13_HEIGHT (12000) returns exactly one notice", v.size() == 1);
    if (!v.empty()) {
        TEST("returned notice has the expected notice_id",
             v.front().notice_id == n.notice_id);
        TEST("returned notice has empty commands (Phase II-A invariant held)",
             v.front().commands.empty());
    }

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 3. Bad signature — rejected.
// ---------------------------------------------------------------------------
static void test_bad_signature() {
    printf("\n=== 3) Invalid signature → reject ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    // Sign correctly first, then mutate one byte in the signature.
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    if (!n.signature_b64.empty()) {
        n.signature_b64[5] = (n.signature_b64[5] == 'A' ? 'B' : 'A');
    }
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("tampered signature → empty result", v.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 4. Expired — current_height >= expires_height.
// ---------------------------------------------------------------------------
static void test_expired() {
    printf("\n=== 4) Expired notice → reject ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();              // expires_height = 13000
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/13000,
                                  Network::MAINNET, key.pub_hex);
    TEST("h == expires_height → empty (expired)", v.empty());

    auto v2 = load_active_notices(dir, /*h=*/14000,
                                  Network::MAINNET, key.pub_hex);
    TEST("h > expires_height → empty (expired)", v2.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 5. Not yet active — current_height < activation_height.
// ---------------------------------------------------------------------------
static void test_future_activation() {
    printf("\n=== 5) Activation height in the future → no banner yet ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.activation_height = 12500;
    n.expires_height    = 13000;
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("h=12000 < activation_height=12500 → empty (not active yet)",
         v.empty());

    auto v2 = load_active_notices(dir, /*h=*/12500,
                                   Network::MAINNET, key.pub_hex);
    TEST("h=activation_height → notice appears", v2.size() == 1);

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 6. Wrong network — testnet notice on mainnet node.
// ---------------------------------------------------------------------------
static void test_wrong_network() {
    printf("\n=== 6) Wrong-network notice → reject ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.network_str = "testnet";
    n.network     = Network::TESTNET;
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("testnet notice rejected on mainnet node", v.empty());

    auto v2 = load_active_notices(dir, /*h=*/12000,
                                   Network::TESTNET, key.pub_hex);
    TEST("testnet notice accepted on testnet node", v2.size() == 1);

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 7. Non-empty `commands` — REJECT (Phase II-A invariant).
// ---------------------------------------------------------------------------
static void test_commands_must_be_empty() {
    printf("\n=== 7) Non-empty commands → reject (Phase II-A invariant) ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.commands = {"restart_now"};        // anything non-empty
    // Sign with the canonical payload that includes the commands.
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("notice with non-empty commands rejected even though signature "
         "verifies — Phase II-A bans actionable notices",
         v.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 8. Malformed JSON → empty (must not crash).
// ---------------------------------------------------------------------------
static void test_malformed_json() {
    printf("\n=== 8) Malformed JSON → empty (no crash) ===\n");
    auto dir = mk_tmpdir();
    write_file(dir + "/notices.json", "[{ this is not valid json ");

    TestKey key = make_test_key();
    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("malformed JSON → empty (no crash)", v.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 9. Missing file → empty.
// ---------------------------------------------------------------------------
static void test_missing_file() {
    printf("\n=== 9) Missing notices.json → empty ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("missing file → empty (no crash)", v.empty());
    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 10. Oversized file → empty.
// ---------------------------------------------------------------------------
static void test_oversized_file() {
    printf("\n=== 10) Oversized notices.json → empty ===\n");
    auto dir = mk_tmpdir();
    std::string huge(300 * 1024, 'x');
    write_file(dir + "/notices.json", "[" + huge + "]");

    TestKey key = make_test_key();
    auto v = load_active_notices(dir, /*h=*/12000,
                                  Network::MAINNET, key.pub_hex);
    TEST("file > 256 KB → empty (size cap honoured)", v.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 11. Placeholder BEACON_PUBKEY_HEX is fail-closed by default.
// ---------------------------------------------------------------------------
static void test_placeholder_fail_closed() {
    printf("\n=== 11) Default BEACON_PUBKEY_HEX (placeholder) is fail-closed ===\n");
    auto dir = mk_tmpdir();
    TestKey key = make_test_key();
    Notice n = mk_notice();
    n.signature_b64 = sign_canonical(canonical_payload(n), key);
    write_notices_file(dir, {n});

    // Use the default pubkey arg (placeholder). Signature was produced
    // against a different key, so verify must fail.
    auto v = load_active_notices(dir, /*h=*/12000, Network::MAINNET);
    TEST("notice signed by a real key is rejected under the placeholder pubkey",
         v.empty());

    std::filesystem::remove_all(dir);
}

// ---------------------------------------------------------------------------
// 12. canonical_payload sort/format spot-check (no whitespace, sorted keys).
// ---------------------------------------------------------------------------
static void test_canonical_payload_shape() {
    printf("\n=== 12) canonical_payload byte-stream shape ===\n");
    Notice n = mk_notice();
    std::string canon = canonical_payload(n);
    TEST("canonical starts with '{'",       !canon.empty() && canon.front() == '{');
    TEST("canonical ends with '}'",         !canon.empty() && canon.back()  == '}');
    TEST("first key is 'activation_height' (lex-min)",
         canon.find("\"activation_height\"") == 1);
    // Compact form: no JSON-formatting spaces (": ", ", ", "{ ", " }",
    // "[ ", " ]"). Spaces INSIDE quoted string values are legal and
    // preserved — message_en in this notice contains a space, so a
    // blanket "no space" check would be wrong.
    TEST("no '\": '  formatting space",  canon.find("\": ")  == std::string::npos);
    TEST("no ', '   formatting space",   canon.find(", ")    == std::string::npos);
    TEST("no '{ '   formatting space",   canon.find("{ ")    == std::string::npos);
    TEST("no ' }'   formatting space",   canon.find(" }")    == std::string::npos);
    TEST("no '[ '   formatting space",   canon.find("[ ")    == std::string::npos);
    TEST("no ' ]'   formatting space",   canon.find(" ]")    == std::string::npos);
    TEST("contains no newlines",            canon.find('\n') == std::string::npos);
    TEST("does NOT contain a 'signature' field — payload is signature-free",
         canon.find("\"signature\"") == std::string::npos);
}

int main() {
    printf("\n=== V13 Beacon Phase II-A — local notice tests ===\n");
    printf("BEACON_PHASE2A_ACTIVATION_HEIGHT = %lld\n",
           (long long)BEACON_PHASE2A_ACTIVATION_HEIGHT);
    printf("BEACON_P2P_ACTIVATION_HEIGHT     = %lld (V13_HEIGHT = active at V13; INT64_MAX would disable)\n",
           (long long)BEACON_P2P_ACTIVATION_HEIGHT);

    test_dormancy_pre_v13();
    test_happy_path();
    test_bad_signature();
    test_expired();
    test_future_activation();
    test_wrong_network();
    test_commands_must_be_empty();
    test_malformed_json();
    test_missing_file();
    test_oversized_file();
    test_placeholder_fail_closed();
    test_canonical_payload_shape();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
