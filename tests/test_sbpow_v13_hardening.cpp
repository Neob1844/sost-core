// V13 SbPoW hardening — regression tests for the height-gated v13 preimage.
//
// Closes the four pre-existing pre-image gaps documented in
// docs/V13_SBPOW_HARDENING.md:
//
//   1. timestamp   — pool cannot re-stamp the same PoW commit with
//                    different timestamps.
//   2. bits_q      — pool cannot fork the same PoW across difficulty
//                    adjustments.
//   3. merkle_root — pool cannot serve the same PoW with a different
//                    transaction set.
//   4. genesis_hash — signatures from one chain (e.g. testnet) cannot
//                    be replayed on another (e.g. mainnet).
//
// Activation is height-gated by the new ValidationInputs::v13_height
// field. Tests inject a synthetic v13_height so they exercise the active
// path without needing the chain to reach block 12 000.

#include "sost/sbpow.h"
#include "sost/crypto.h"
#include "sost/serialize.h"
#include "sost/tx_signer.h"

#include <climits>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace sost;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

static MinerPrivkey fixture_priv() {
    MinerPrivkey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(0x10 + i);
    return p;
}

static Bytes32 fixture_genesis_mainnet() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0xC0 ^ i);
    return h;
}

static Bytes32 fixture_genesis_testnet() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0x77 ^ i);
    return h;
}

static Bytes32 fixture_prev() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0xAA ^ i);
    return h;
}

static Bytes32 fixture_commit() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0x55 ^ i);
    return h;
}

static Bytes32 fixture_merkle() {
    Bytes32 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (uint8_t)(0x33 ^ (i * 7));
    return h;
}

// Builds a fully-prepared ValidationInputs at a height >= v13_height with
// a freshly-signed v13 message. Tests then mutate one field and verify
// the validator rejects the tampered input.
struct V13Fixture {
    int64_t       v13_height{1000};
    int64_t       phase2_height{1000};
    int64_t       height{1500};
    int64_t       timestamp{1700000000};
    uint32_t      bits_q{0x18000000};
    uint32_t      nonce{42};
    uint32_t      extra_nonce{7};
    Bytes32       prev_hash{fixture_prev()};
    Bytes32       commit{fixture_commit()};
    Bytes32       merkle_root{fixture_merkle()};
    Bytes32       genesis_hash{fixture_genesis_mainnet()};
    MinerPrivkey  priv{fixture_priv()};
    MinerPubkey   pub{};
};

static bool prepare_signed_v13(V13Fixture& f, ValidationInputs& out) {
    if (!derive_compressed_pubkey_from_privkey(f.priv, f.pub)) return false;
    Bytes32 msg = build_sbpow_message_v13(
        f.genesis_hash, f.prev_hash, f.height,
        f.timestamp, f.bits_q, f.commit, f.merkle_root,
        f.nonce, f.extra_nonce, f.pub);
    MinerSignature sig{};
    if (!sign_sbpow_commitment(f.priv, msg, sig)) return false;

    out.header_version     = 2;
    out.prev_hash          = f.prev_hash;
    out.height             = f.height;
    out.commit             = f.commit;
    out.nonce              = f.nonce;
    out.extra_nonce        = f.extra_nonce;
    out.miner_pubkey       = f.pub;
    out.miner_signature    = sig;
    out.coinbase_miner_pkh = derive_pkh_from_pubkey(f.pub);
    out.phase2_height      = f.phase2_height;
    out.v13_height         = f.v13_height;
    out.timestamp          = f.timestamp;
    out.bits_q             = f.bits_q;
    out.merkle_root        = f.merkle_root;
    out.genesis_hash       = f.genesis_hash;
    return true;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// 1) Sanity: v13 preimage differs from v11 for the same shared inputs.
static void t01_v13_vs_v11_differ() {
    printf("\n=== 1) v13 message differs from v11 for same shared inputs ===\n");
    V13Fixture f;
    MinerPubkey pub{};
    TEST("derive pubkey", derive_compressed_pubkey_from_privkey(f.priv, pub));
    Bytes32 msg_v11 = build_sbpow_message(
        f.prev_hash, f.height, f.commit, f.nonce, f.extra_nonce, pub);
    Bytes32 msg_v13 = build_sbpow_message_v13(
        f.genesis_hash, f.prev_hash, f.height,
        f.timestamp, f.bits_q, f.commit, f.merkle_root,
        f.nonce, f.extra_nonce, pub);
    TEST("v11 message != v13 message", msg_v11 != msg_v13);
}

// 2) Happy path: a freshly signed v13 block validates OK.
static void t02_v13_happy_path() {
    printf("\n=== 2) v13 block with all new fields signed -> OK ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare", prepare_signed_v13(f, in));
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("OK", r == ValidationResult::OK);
    if (r != ValidationResult::OK) printf("    err: %s\n", err.c_str());
}

// 3) Timestamp binding.
static void t03_timestamp_binding() {
    printf("\n=== 3) v13 timestamp mutation -> SIGNATURE_INVALID ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare", prepare_signed_v13(f, in));
    in.timestamp += 1;
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("rejects on timestamp tamper", r == ValidationResult::SIGNATURE_INVALID);
}

// 4) bits_q binding.
static void t04_bits_q_binding() {
    printf("\n=== 4) v13 bits_q mutation -> SIGNATURE_INVALID ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare", prepare_signed_v13(f, in));
    in.bits_q ^= 0x1;
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("rejects on bits_q tamper", r == ValidationResult::SIGNATURE_INVALID);
}

// 5) merkle_root binding.
static void t05_merkle_root_binding() {
    printf("\n=== 5) v13 merkle_root mutation -> SIGNATURE_INVALID ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare", prepare_signed_v13(f, in));
    in.merkle_root[0] ^= 0xFF;
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("rejects on merkle_root tamper", r == ValidationResult::SIGNATURE_INVALID);
}

// 6) genesis_hash binding (cross-chain replay).
static void t06_cross_chain_replay() {
    printf("\n=== 6) cross-chain replay -> SIGNATURE_INVALID ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare on mainnet genesis", prepare_signed_v13(f, in));
    in.genesis_hash = fixture_genesis_testnet();
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("rejects on chain-id swap", r == ValidationResult::SIGNATURE_INVALID);
}

// 7) Pre-V13 backwards compatibility.
static void t07_pre_v13_uses_v11_preimage() {
    printf("\n=== 7) pre-v13 height uses v11 preimage (backwards compat) ===\n");
    V13Fixture f;
    f.v13_height   = 1000;
    f.phase2_height = 100;
    f.height       = 500;
    MinerPubkey pub{};
    TEST("derive", derive_compressed_pubkey_from_privkey(f.priv, pub));
    Bytes32 msg = build_sbpow_message(
        f.prev_hash, f.height, f.commit, f.nonce, f.extra_nonce, pub);
    MinerSignature sig{};
    TEST("sign", sign_sbpow_commitment(f.priv, msg, sig));

    ValidationInputs in;
    in.header_version     = 2;
    in.prev_hash          = f.prev_hash;
    in.height             = f.height;
    in.commit             = f.commit;
    in.nonce              = f.nonce;
    in.extra_nonce        = f.extra_nonce;
    in.miner_pubkey       = pub;
    in.miner_signature    = sig;
    in.coinbase_miner_pkh = derive_pkh_from_pubkey(pub);
    in.phase2_height      = f.phase2_height;
    in.v13_height         = f.v13_height;
    // Bogus v13 fields on purpose: pre-v13 path must NOT read them.
    in.timestamp          = 0x7FFFFFFF;
    in.bits_q             = 0xDEADBEEF;
    in.merkle_root        = fixture_merkle();
    in.genesis_hash       = fixture_genesis_testnet();
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("v11 preimage accepted below v13_height", r == ValidationResult::OK);
    if (r != ValidationResult::OK) printf("    err: %s\n", err.c_str());
}

// 8) Boundary at v13_height: equality already uses the v13 preimage.
static void t08_boundary_at_v13_height() {
    printf("\n=== 8) at v13_height (boundary) -> v11 preimage rejected ===\n");
    V13Fixture f;
    f.v13_height = 1000;
    f.height     = 1000;
    MinerPubkey pub{};
    TEST("derive", derive_compressed_pubkey_from_privkey(f.priv, pub));
    Bytes32 msg_v11 = build_sbpow_message(
        f.prev_hash, f.height, f.commit, f.nonce, f.extra_nonce, pub);
    MinerSignature sig{};
    TEST("sign", sign_sbpow_commitment(f.priv, msg_v11, sig));

    ValidationInputs in;
    in.header_version     = 2;
    in.prev_hash          = f.prev_hash;
    in.height             = f.height;
    in.commit             = f.commit;
    in.nonce              = f.nonce;
    in.extra_nonce        = f.extra_nonce;
    in.miner_pubkey       = pub;
    in.miner_signature    = sig;
    in.coinbase_miner_pkh = derive_pkh_from_pubkey(pub);
    in.phase2_height      = f.phase2_height;
    in.v13_height         = f.v13_height;
    in.timestamp          = f.timestamp;
    in.bits_q             = f.bits_q;
    in.merkle_root        = f.merkle_root;
    in.genesis_hash       = f.genesis_hash;
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("v11 sig at boundary rejected", r == ValidationResult::SIGNATURE_INVALID);
}

// 9) Coinbase binding still enforced under v13.
static void t09_coinbase_mismatch_under_v13() {
    printf("\n=== 9) v13 + coinbase pkh mismatch -> COINBASE_MISMATCH ===\n");
    V13Fixture f;
    ValidationInputs in;
    TEST("prepare", prepare_signed_v13(f, in));
    PubKeyHash zero{}; std::memset(zero.data(), 0, zero.size());
    in.coinbase_miner_pkh = zero;
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("rejects mismatched coinbase under v13",
         r == ValidationResult::COINBASE_MISMATCH);
}

// 10) Field-by-field independence under v13.
static void t10_all_fields_committed() {
    printf("\n=== 10) every v13 field is part of the preimage ===\n");
    V13Fixture f;
    MinerPubkey pub{};
    TEST("derive", derive_compressed_pubkey_from_privkey(f.priv, pub));
    Bytes32 base = build_sbpow_message_v13(
        f.genesis_hash, f.prev_hash, f.height,
        f.timestamp, f.bits_q, f.commit, f.merkle_root,
        f.nonce, f.extra_nonce, pub);

    auto check_diff = [&](const char* name, Bytes32 mutated) {
        TEST(name, mutated != base);
    };

    {
        Bytes32 g = f.genesis_hash; g[0] ^= 0x01;
        check_diff("genesis_hash bound",
                   build_sbpow_message_v13(g, f.prev_hash, f.height, f.timestamp, f.bits_q,
                                           f.commit, f.merkle_root, f.nonce, f.extra_nonce, pub));
    }
    {
        Bytes32 p = f.prev_hash; p[0] ^= 0x01;
        check_diff("prev_hash bound",
                   build_sbpow_message_v13(f.genesis_hash, p, f.height, f.timestamp, f.bits_q,
                                           f.commit, f.merkle_root, f.nonce, f.extra_nonce, pub));
    }
    check_diff("height bound",
               build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height + 1, f.timestamp,
                                       f.bits_q, f.commit, f.merkle_root, f.nonce, f.extra_nonce, pub));
    check_diff("timestamp bound",
               build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp + 1,
                                       f.bits_q, f.commit, f.merkle_root, f.nonce, f.extra_nonce, pub));
    check_diff("bits_q bound",
               build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                       f.bits_q ^ 0x1u, f.commit, f.merkle_root, f.nonce, f.extra_nonce, pub));
    {
        Bytes32 c = f.commit; c[0] ^= 0x01;
        check_diff("commit bound",
                   build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                           f.bits_q, c, f.merkle_root, f.nonce, f.extra_nonce, pub));
    }
    {
        Bytes32 m = f.merkle_root; m[0] ^= 0x01;
        check_diff("merkle_root bound",
                   build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                           f.bits_q, f.commit, m, f.nonce, f.extra_nonce, pub));
    }
    check_diff("nonce bound",
               build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                       f.bits_q, f.commit, f.merkle_root, f.nonce + 1, f.extra_nonce, pub));
    check_diff("extra_nonce bound",
               build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                       f.bits_q, f.commit, f.merkle_root, f.nonce, f.extra_nonce + 1, pub));
    {
        MinerPubkey alt = pub; alt[1] ^= 0x01;
        check_diff("miner_pubkey bound",
                   build_sbpow_message_v13(f.genesis_hash, f.prev_hash, f.height, f.timestamp,
                                           f.bits_q, f.commit, f.merkle_root, f.nonce, f.extra_nonce, alt));
    }
}

// 11) Signature scoped to genesis_hash (cross-chain isolation).
static void t11_signature_does_not_cross_genesis() {
    printf("\n=== 11) signature scoped to genesis_hash (cross-chain isolation) ===\n");
    V13Fixture mn;
    mn.genesis_hash = fixture_genesis_mainnet();
    ValidationInputs in;
    TEST("prepare mainnet", prepare_signed_v13(mn, in));
    in.genesis_hash = fixture_genesis_testnet();
    std::string err;
    auto r = validate_sbpow_for_block(in, &err);
    TEST("replay across chains rejected", r == ValidationResult::SIGNATURE_INVALID);
}

// 12) v13 output is exactly 32 bytes and bit-stable across two calls.
static void t12_message_is_32_bytes_and_stable() {
    printf("\n=== 12) v13 output is 32-byte SHA-256 and bit-stable ===\n");
    V13Fixture f;
    MinerPubkey pub{};
    TEST("derive", derive_compressed_pubkey_from_privkey(f.priv, pub));
    Bytes32 a = build_sbpow_message_v13(
        f.genesis_hash, f.prev_hash, f.height,
        f.timestamp, f.bits_q, f.commit, f.merkle_root,
        f.nonce, f.extra_nonce, pub);
    Bytes32 b = build_sbpow_message_v13(
        f.genesis_hash, f.prev_hash, f.height,
        f.timestamp, f.bits_q, f.commit, f.merkle_root,
        f.nonce, f.extra_nonce, pub);
    TEST("output is 32 bytes (Bytes32)", a.size() == 32);
    TEST("deterministic across two calls", a == b);
}

// ---------------------------------------------------------------------------

int main() {
    printf("=========================================\n");
    printf("V13 SbPoW hardening regression tests\n");
    printf("=========================================\n");

    t01_v13_vs_v11_differ();
    t02_v13_happy_path();
    t03_timestamp_binding();
    t04_bits_q_binding();
    t05_merkle_root_binding();
    t06_cross_chain_replay();
    t07_pre_v13_uses_v11_preimage();
    t08_boundary_at_v13_height();
    t09_coinbase_mismatch_under_v13();
    t10_all_fields_committed();
    t11_signature_does_not_cross_genesis();
    t12_message_is_32_bytes_and_stable();

    printf("\n=========================================\n");
    printf("Results: %d passed, %d failed\n", g_pass, g_fail);
    printf("=========================================\n");
    return g_fail == 0 ? 0 : 1;
}
