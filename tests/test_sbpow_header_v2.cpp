// V11 Phase 2 — BlockHeader v2 (SbPoW) serialization tests.
//
// Scope: structural only. No consensus gate, no miner key loading, no
// signing, no validation. The v2 header is implemented at the
// serialization layer; activation in consensus lands in later commits.
//
// Mandatory test cases (matches Commit 2 spec):
//   1. v1 serialized size == 96
//   2. v1 roundtrip preserves all 7 base fields
//   3. v1 block hash unchanged vs known fixture from current logic
//   4. v2 serialized size == 193
//   5. v2 roundtrip preserves base fields + pubkey + signature
//   6. v2 hash changes when pubkey changes
//   7. v2 hash changes when signature changes
//   8. v2 deserialization rejects 96-byte buffer
//   9. v1 deserialization rejects 193-byte buffer
//  10. unknown version rejects
//  11. malformed size rejects
//  12. v1/v2 same base fields produce different block hashes

#include "sost/block.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static std::string to_hex(const std::vector<uint8_t>& v) {
    static const char H[] = "0123456789abcdef";
    std::string s; s.reserve(v.size() * 2);
    for (uint8_t b : v) { s.push_back(H[b >> 4]); s.push_back(H[b & 0xF]); }
    return s;
}
static std::string to_hex(const Hash256& h) {
    return to_hex(std::vector<uint8_t>(h.begin(), h.end()));
}

// Build a fixed v1 header A: ALL ZEROS except version=1.
// Pre-computed fixture hash (SHA256² of 96 bytes [01 00 00 00 then 92 zeros]):
//   41ace2b45dd9bd60c49b66a32df06e69255dcf5c4292440593351240f3e11286
static BlockHeader fixture_v1_zero() {
    BlockHeader h{};
    h.version = BLOCK_HEADER_VERSION_V1;
    // prev_block_hash and merkle_root default-init to all zeros.
    // timestamp/bits_q/nonce/height default to 0.
    return h;
}

// Build a fixed v1 header B with non-trivial values:
//   prev = 0xAA*32, merkle = 0xBB*32, ts=0x12345678, bits=0xDEADBEEF,
//   nonce=0x0102030405060708, height=12345.
// Pre-computed fixture hash:
//   ebcbe3442cf8aad362563c392ed1d0777f33f30afb428de6cb9637cbdee22eb7
static BlockHeader fixture_v1_nonzero() {
    BlockHeader h{};
    h.version = BLOCK_HEADER_VERSION_V1;
    h.prev_block_hash.fill(0xAA);
    h.merkle_root.fill(0xBB);
    h.timestamp = 0x12345678;
    h.bits_q    = 0xDEADBEEF;
    h.nonce     = 0x0102030405060708ULL;
    h.height    = 12345;
    return h;
}

static BlockHeader make_v2(uint8_t pubkey_seed, uint8_t sig_seed) {
    BlockHeader h = fixture_v1_nonzero();
    h.version = BLOCK_HEADER_VERSION_V2;
    for (size_t i = 0; i < SBPOW_PUBKEY_SIZE; ++i)
        h.miner_pubkey[i] = (uint8_t)(pubkey_seed + i);
    for (size_t i = 0; i < SBPOW_SIGNATURE_SIZE; ++i)
        h.miner_signature[i] = (uint8_t)(sig_seed + i);
    return h;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_v1_size_and_roundtrip() {
    printf("\n=== v1 size + roundtrip ===\n");

    auto h = fixture_v1_nonzero();
    auto bytes = h.SerializeBytes();
    TEST("v1 SerializeBytes() size == 96", bytes.size() == BLOCK_HEADER_SIZE_V1);

    auto fixed = h.Serialize();
    TEST("v1 Serialize() (fixed array) size == 96",
         fixed.size() == BLOCK_HEADER_SIZE_V1);
    TEST("v1 Serialize() bytes match SerializeBytes()",
         std::memcmp(fixed.data(), bytes.data(), BLOCK_HEADER_SIZE_V1) == 0);

    BlockHeader r;
    std::string err;
    bool ok = BlockHeader::DeserializeStandalone(bytes, r, &err);
    TEST("v1 DeserializeStandalone(96 B, version=1) succeeds", ok);
    TEST("v1 roundtrip: version preserved",         r.version == h.version);
    TEST("v1 roundtrip: prev_block_hash preserved", r.prev_block_hash == h.prev_block_hash);
    TEST("v1 roundtrip: merkle_root preserved",     r.merkle_root == h.merkle_root);
    TEST("v1 roundtrip: timestamp preserved",       r.timestamp == h.timestamp);
    TEST("v1 roundtrip: bits_q preserved",          r.bits_q == h.bits_q);
    TEST("v1 roundtrip: nonce preserved",           r.nonce == h.nonce);
    TEST("v1 roundtrip: height preserved",          r.height == h.height);
    TEST("v1 roundtrip: full operator== holds",     r == h);
}

static void test_v1_hash_fixture_unchanged() {
    printf("\n=== v1 hash fixtures (unchanged from pre-V11 logic) ===\n");

    // Fixture A — zero header.
    auto a = fixture_v1_zero();
    std::string a_hex = a.ComputeBlockHashHex();
    const char* a_expected =
        "41ace2b45dd9bd60c49b66a32df06e69255dcf5c4292440593351240f3e11286";
    TEST("v1 zero-header hash matches fixture A", a_hex == a_expected);
    if (a_hex != a_expected) {
        printf("    expected: %s\n    got:      %s\n", a_expected, a_hex.c_str());
    }

    // Fixture B — non-trivial header.
    auto b = fixture_v1_nonzero();
    std::string b_hex = b.ComputeBlockHashHex();
    const char* b_expected =
        "ebcbe3442cf8aad362563c392ed1d0777f33f30afb428de6cb9637cbdee22eb7";
    TEST("v1 non-trivial-header hash matches fixture B", b_hex == b_expected);
    if (b_hex != b_expected) {
        printf("    expected: %s\n    got:      %s\n", b_expected, b_hex.c_str());
    }
}

static void test_v2_size_and_roundtrip() {
    printf("\n=== v2 size + roundtrip ===\n");

    auto h = make_v2(/*pubkey_seed*/0x10, /*sig_seed*/0x40);
    auto bytes = h.SerializeBytes();
    TEST("v2 SerializeBytes() size == 193", bytes.size() == BLOCK_HEADER_SIZE_V2);

    BlockHeader r;
    std::string err;
    bool ok = BlockHeader::DeserializeStandalone(bytes, r, &err);
    TEST("v2 DeserializeStandalone(193 B, version=2) succeeds", ok);
    TEST("v2 roundtrip: version preserved",         r.version == h.version);
    TEST("v2 roundtrip: prev_block_hash preserved", r.prev_block_hash == h.prev_block_hash);
    TEST("v2 roundtrip: merkle_root preserved",     r.merkle_root == h.merkle_root);
    TEST("v2 roundtrip: timestamp preserved",       r.timestamp == h.timestamp);
    TEST("v2 roundtrip: bits_q preserved",          r.bits_q == h.bits_q);
    TEST("v2 roundtrip: nonce preserved",           r.nonce == h.nonce);
    TEST("v2 roundtrip: height preserved",          r.height == h.height);
    TEST("v2 roundtrip: miner_pubkey preserved",    r.miner_pubkey == h.miner_pubkey);
    TEST("v2 roundtrip: miner_signature preserved", r.miner_signature == h.miner_signature);
    TEST("v2 roundtrip: full operator== holds",     r == h);
}

static void test_v2_hash_sensitivity() {
    printf("\n=== v2 hash sensitivity to pubkey + signature ===\n");

    auto base   = make_v2(0x10, 0x40);
    auto altpk  = make_v2(0x11, 0x40);   // pubkey changed
    auto altsig = make_v2(0x10, 0x41);   // signature changed

    Hash256 h0 = base.ComputeBlockHash();
    Hash256 h1 = altpk.ComputeBlockHash();
    Hash256 h2 = altsig.ComputeBlockHash();

    TEST("v2 hash differs when miner_pubkey changes",   !(h0 == h1));
    TEST("v2 hash differs when miner_signature changes", !(h0 == h2));
}

static void test_strict_size_rejection() {
    printf("\n=== strict size + version-mismatch rejection ===\n");

    // (8) v2 deserialization rejects 96-byte buffer.
    {
        // Build a 96-byte buffer that DECLARES version=2 in its first 4 bytes.
        std::vector<uint8_t> buf(BLOCK_HEADER_SIZE_V1, 0x00);
        buf[0] = 0x02; buf[1] = 0x00; buf[2] = 0x00; buf[3] = 0x00;  // LE32(2)
        BlockHeader r; std::string err;
        bool ok = BlockHeader::DeserializeStandalone(buf, r, &err);
        TEST("96-byte buffer with version=2 is rejected", !ok);
    }

    // (9) v1 deserialization rejects 193-byte buffer.
    {
        // 193-byte buffer that DECLARES version=1 in its first 4 bytes.
        std::vector<uint8_t> buf(BLOCK_HEADER_SIZE_V2, 0x00);
        buf[0] = 0x01;  // LE32(1)
        BlockHeader r; std::string err;
        bool ok = BlockHeader::DeserializeStandalone(buf, r, &err);
        TEST("193-byte buffer with version=1 is rejected", !ok);
    }

    // (10) unknown version rejects.
    {
        // 96-byte buffer with version=99.
        std::vector<uint8_t> buf(BLOCK_HEADER_SIZE_V1, 0x00);
        buf[0] = 0x63;  // LE32(99)
        BlockHeader r; std::string err;
        bool ok = BlockHeader::DeserializeStandalone(buf, r, &err);
        TEST("standalone unknown version (99) at 96-byte buffer rejected", !ok);
    }
    {
        // 193-byte buffer with version=99.
        std::vector<uint8_t> buf(BLOCK_HEADER_SIZE_V2, 0x00);
        buf[0] = 0x63;  // LE32(99)
        BlockHeader r; std::string err;
        bool ok = BlockHeader::DeserializeStandalone(buf, r, &err);
        TEST("standalone unknown version (99) at 193-byte buffer rejected", !ok);
    }
    {
        // streaming DeserializeFrom with unknown version
        std::vector<uint8_t> buf(BLOCK_HEADER_SIZE_V1, 0x00);
        buf[0] = 0x05;  // LE32(5)
        BlockHeader r; std::string err;
        size_t off = 0;
        bool ok = BlockHeader::DeserializeFrom(buf, off, r, &err);
        TEST("streaming unknown version (5) rejected", !ok);
    }

    // (11) malformed size rejects (not exactly 96 or 193).
    {
        std::vector<uint8_t> short_buf(50, 0x00);
        short_buf[0] = 0x01;
        BlockHeader r; std::string err;
        TEST("standalone 50-byte buffer rejected",
             !BlockHeader::DeserializeStandalone(short_buf, r, &err));
    }
    {
        std::vector<uint8_t> mid_buf(150, 0x00);
        mid_buf[0] = 0x02;
        BlockHeader r; std::string err;
        TEST("standalone 150-byte buffer rejected",
             !BlockHeader::DeserializeStandalone(mid_buf, r, &err));
    }
    {
        std::vector<uint8_t> long_buf(300, 0x00);
        long_buf[0] = 0x02;
        BlockHeader r; std::string err;
        TEST("standalone 300-byte buffer rejected",
             !BlockHeader::DeserializeStandalone(long_buf, r, &err));
    }
    {
        std::vector<uint8_t> empty_buf;
        BlockHeader r; std::string err;
        TEST("standalone empty buffer rejected",
             !BlockHeader::DeserializeStandalone(empty_buf, r, &err));
    }
}

static void test_v1_v2_block_hashes_diverge() {
    printf("\n=== v1 vs v2 block hash divergence (same base fields) ===\n");

    auto v1 = fixture_v1_nonzero();
    auto v2 = make_v2(0x10, 0x40);  // same base fields, version=2 + pubkey+sig
    // Sanity: v1 base fields equal v2 base fields (we built v2 from v1 fixture).
    bool base_eq = v1.prev_block_hash == v2.prev_block_hash
                && v1.merkle_root == v2.merkle_root
                && v1.timestamp == v2.timestamp
                && v1.bits_q == v2.bits_q
                && v1.nonce == v2.nonce
                && v1.height == v2.height;
    TEST("v1 and v2 share identical base fields (sanity)", base_eq);

    Hash256 h1 = v1.ComputeBlockHash();
    Hash256 h2 = v2.ComputeBlockHash();
    TEST("v1 and v2 with same base fields produce different block hashes",
         !(h1 == h2));
}

static void test_unknown_version_serialize() {
    printf("\n=== unknown version on serialize ===\n");

    BlockHeader h = fixture_v1_nonzero();
    h.version = 99;
    auto bytes = h.SerializeBytes();
    TEST("SerializeBytes() returns empty vector for unknown version",
         bytes.empty());
}

static void test_streaming_with_trailing_bytes() {
    printf("\n=== streaming DeserializeFrom advances offset correctly ===\n");

    // Compose: v1 (96 B) + 8 trailing arbitrary bytes.
    auto v1 = fixture_v1_nonzero();
    std::vector<uint8_t> buf = v1.SerializeBytes();
    for (int i = 0; i < 8; ++i) buf.push_back((uint8_t)i);

    BlockHeader r; std::string err;
    size_t off = 0;
    bool ok = BlockHeader::DeserializeFrom(buf, off, r, &err);
    TEST("streaming v1 inside larger buffer succeeds", ok);
    TEST("streaming v1 advances offset to 96", off == BLOCK_HEADER_SIZE_V1);

    // Same with v2.
    auto v2 = make_v2(0x10, 0x40);
    std::vector<uint8_t> buf2 = v2.SerializeBytes();
    for (int i = 0; i < 8; ++i) buf2.push_back((uint8_t)i);
    BlockHeader r2; std::string err2;
    size_t off2 = 0;
    bool ok2 = BlockHeader::DeserializeFrom(buf2, off2, r2, &err2);
    TEST("streaming v2 inside larger buffer succeeds", ok2);
    TEST("streaming v2 advances offset to 193", off2 == BLOCK_HEADER_SIZE_V2);
}

int main() {
    printf("=== test_sbpow_header_v2 ===\n");
    printf("BLOCK_HEADER_SIZE_V1 = %zu\n", (size_t)BLOCK_HEADER_SIZE_V1);
    printf("BLOCK_HEADER_SIZE_V2 = %zu\n", (size_t)BLOCK_HEADER_SIZE_V2);
    printf("SBPOW_PUBKEY_SIZE    = %zu\n", (size_t)SBPOW_PUBKEY_SIZE);
    printf("SBPOW_SIGNATURE_SIZE = %zu\n", (size_t)SBPOW_SIGNATURE_SIZE);

    test_v1_size_and_roundtrip();
    test_v1_hash_fixture_unchanged();
    test_v2_size_and_roundtrip();
    test_v2_hash_sensitivity();
    test_strict_size_rejection();
    test_v1_v2_block_hashes_diverge();
    test_unknown_version_serialize();
    test_streaming_with_trailing_bytes();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
