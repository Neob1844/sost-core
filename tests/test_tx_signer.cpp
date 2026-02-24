// =============================================================================
// test_tx_signer.cpp — Sighash + ECDSA tests (Phase 2, hardened)
// =============================================================================

#include "sost/transaction.h"
#include "sost/tx_signer.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <string>

using namespace sost;

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name)                                                           \
    static void test_##name();                                               \
    static struct Register_##name {                                          \
        Register_##name() { test_##name(); }                                 \
    } reg_##name;                                                            \
    static void test_##name()

#define ASSERT_TRUE(cond, msg)                                               \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::cerr << "FAIL: " << (msg) << " [" << __FILE__               \
                      << ":" << __LINE__ << "]" << std::endl;                \
            tests_failed++;                                                  \
            return;                                                          \
        }                                                                    \
    } while (0)

#define ASSERT_EQ(a, b, msg)     ASSERT_TRUE((a) == (b), msg)
#define ASSERT_NE(a, b, msg)     ASSERT_TRUE((a) != (b), msg)

#define PASS(name)                                                           \
    do {                                                                     \
        std::cout << "  PASS: " << (name) << std::endl;                      \
        tests_passed++;                                                      \
    } while (0)

// =============================================================================
// Test genesis hash (dummy, used across all tests)
// =============================================================================

static Hash256 TestGenesisHash() {
    Hash256 gh{};
    std::memset(gh.data(), 0x42, 32);
    return gh;
}

// =============================================================================
// Helper: build a simple 1-in 1-out standard tx
// =============================================================================

static Transaction MakeSimpleTx(const PubKeyHash& sender_pkh) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    std::memset(in.prev_txid.data(), 0xAA, 32);
    in.prev_index = 0;
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount = 500000000;
    out.type = OUT_TRANSFER;
    std::memset(out.pubkey_hash.data(), 0xBB, 20);
    tx.outputs.push_back(out);

    return tx;
}

// =============================================================================
// Original Tests (T1-T15)
// =============================================================================

TEST(keygen_and_derive) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;

    ASSERT_TRUE(GenerateKeyPair(priv, pub, &err), "keygen failed: " + err);
    ASSERT_TRUE(pub[0] == 0x02 || pub[0] == 0x03, "bad pubkey prefix");

    PubKey pub2{};
    ASSERT_TRUE(DerivePublicKey(priv, pub2, &err), "derive failed: " + err);
    ASSERT_EQ(pub, pub2, "derived pubkey mismatch");

    PASS("keygen_and_derive");
}

TEST(pubkey_hash) {
    PrivKey priv{};
    PubKey pub{};
    GenerateKeyPair(priv, pub, nullptr);

    PubKeyHash pkh = ComputePubKeyHash(pub);

    bool all_zero = true;
    for (auto b : pkh) { if (b != 0) { all_zero = false; break; } }
    ASSERT_TRUE(!all_zero, "pubkey hash is all zeros");

    PubKeyHash pkh2 = ComputePubKeyHash(pub);
    ASSERT_EQ(pkh, pkh2, "pubkey hash not deterministic");

    PASS("pubkey_hash");
}

TEST(sign_and_verify) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Hash256 genesis = TestGenesisHash();
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};

    ASSERT_TRUE(SignTransactionInput(tx, 0, spent, genesis, priv, &err),
                "sign failed: " + err);
    ASSERT_TRUE(VerifyTransactionInput(tx, 0, spent, genesis, sender_pkh, &err),
                "verify failed: " + err);

    PASS("sign_and_verify");
}

TEST(low_s_enforced) {
    PrivKey priv{};
    PubKey pub{};
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    Sig64 sig{};
    std::memcpy(sig.data(), tx.inputs[0].signature.data(), 64);
    ASSERT_TRUE(IsLowS(sig), "signature not LOW-S after signing");

    PASS("low_s_enforced");
}

TEST(tampered_signature_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    tx.inputs[0].signature[10] ^= 0x01;

    bool ok = VerifyTransactionInput(tx, 0, spent, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "tampered signature should fail verification");

    PASS("tampered_signature_fails");
}

TEST(wrong_pubkey_hash_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    PubKeyHash wrong_pkh{};
    std::memset(wrong_pkh.data(), 0xFF, 20);

    bool ok = VerifyTransactionInput(tx, 0, spent, genesis, wrong_pkh, &err);
    ASSERT_TRUE(!ok, "wrong pubkey hash should fail");

    PASS("wrong_pubkey_hash_fails");
}

TEST(cross_network_replay_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis_mainnet = TestGenesisHash();
    Hash256 genesis_testnet{};
    std::memset(genesis_testnet.data(), 0x99, 32);

    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis_mainnet, priv, nullptr);

    bool ok = VerifyTransactionInput(tx, 0, spent, genesis_testnet, sender_pkh, &err);
    ASSERT_TRUE(!ok, "cross-network replay should fail");

    PASS("cross_network_replay_fails");
}

TEST(wrong_spent_amount_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent_real{1000000000, OUT_TRANSFER};
    SpentOutput spent_fake{999999999, OUT_TRANSFER};

    SignTransactionInput(tx, 0, spent_real, genesis, priv, nullptr);

    bool ok = VerifyTransactionInput(tx, 0, spent_fake, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "wrong spent amount should fail");

    PASS("wrong_spent_amount_fails");
}

TEST(wrong_spent_type_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent_real{1000000000, OUT_TRANSFER};
    SpentOutput spent_fake{1000000000, OUT_COINBASE_MINER};

    SignTransactionInput(tx, 0, spent_real, genesis, priv, nullptr);

    bool ok = VerifyTransactionInput(tx, 0, spent_fake, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "wrong spent type should fail");

    PASS("wrong_spent_type_fails");
}

TEST(tampered_output_fails) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    tx.outputs[0].amount += 1;

    bool ok = VerifyTransactionInput(tx, 0, spent, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "tampered output should fail");

    PASS("tampered_output_fails");
}

TEST(zero_signature_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 sighash{};
    std::memset(sighash.data(), 0xDE, 32);

    Sig64 zero_sig{};
    bool ok = VerifySighash(pub, sighash, zero_sig, &err);
    ASSERT_TRUE(!ok, "all-zero signature should be rejected");

    PASS("zero_signature_rejected");
}

TEST(sighash_deterministic) {
    PrivKey priv{};
    PubKey pub{};
    GenerateKeyPair(priv, pub, nullptr);

    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Hash256 genesis = TestGenesisHash();
    Transaction tx = MakeSimpleTx(sender_pkh);
    SpentOutput spent{1000000000, OUT_TRANSFER};

    Hash256 h1 = ComputeSighash(tx, 0, spent, genesis);
    Hash256 h2 = ComputeSighash(tx, 0, spent, genesis);
    ASSERT_EQ(h1, h2, "sighash not deterministic");

    tx.outputs[0].amount += 1;
    Hash256 h3 = ComputeSighash(tx, 0, spent, genesis);
    ASSERT_NE(h1, h3, "sighash unchanged after output modification");

    PASS("sighash_deterministic");
}

TEST(hash_prevouts_sensitivity) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in1;
    std::memset(in1.prev_txid.data(), 0xAA, 32);
    in1.prev_index = 0;
    tx.inputs.push_back(in1);

    Hash256 hp1 = ComputeHashPrevouts(tx);

    tx.inputs[0].prev_index = 1;
    Hash256 hp2 = ComputeHashPrevouts(tx);
    ASSERT_NE(hp1, hp2, "hashPrevouts unchanged after prev_index change");

    tx.inputs[0].prev_index = 0;
    tx.inputs[0].prev_txid[0] = 0xBB;
    Hash256 hp3 = ComputeHashPrevouts(tx);
    ASSERT_NE(hp1, hp3, "hashPrevouts unchanged after prev_txid change");

    PASS("hash_prevouts_sensitivity");
}

TEST(multi_input_signing) {
    PrivKey priv1{}, priv2{};
    PubKey pub1{}, pub2{};
    std::string err;
    GenerateKeyPair(priv1, pub1, nullptr);
    GenerateKeyPair(priv2, pub2, nullptr);

    PubKeyHash pkh1 = ComputePubKeyHash(pub1);
    PubKeyHash pkh2 = ComputePubKeyHash(pub2);

    Hash256 genesis = TestGenesisHash();

    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in0;
    std::memset(in0.prev_txid.data(), 0xAA, 32);
    in0.prev_index = 0;
    tx.inputs.push_back(in0);

    TxInput in1;
    std::memset(in1.prev_txid.data(), 0xBB, 32);
    in1.prev_index = 0;
    tx.inputs.push_back(in1);

    TxOutput out;
    out.amount = 800000000;
    out.type = OUT_TRANSFER;
    std::memset(out.pubkey_hash.data(), 0xCC, 20);
    tx.outputs.push_back(out);

    SpentOutput spent0{500000000, OUT_TRANSFER};
    SpentOutput spent1{400000000, OUT_TRANSFER};

    ASSERT_TRUE(SignTransactionInput(tx, 0, spent0, genesis, priv1, &err),
                "sign input 0 failed: " + err);
    ASSERT_TRUE(SignTransactionInput(tx, 1, spent1, genesis, priv2, &err),
                "sign input 1 failed: " + err);

    ASSERT_TRUE(VerifyTransactionInput(tx, 0, spent0, genesis, pkh1, &err),
                "verify input 0 failed: " + err);
    ASSERT_TRUE(VerifyTransactionInput(tx, 1, spent1, genesis, pkh2, &err),
                "verify input 1 failed: " + err);

    bool cross = VerifyTransactionInput(tx, 0, spent0, genesis, pkh2, &err);
    ASSERT_TRUE(!cross, "cross-key verification should fail");

    PASS("multi_input_signing");
}

TEST(wrong_key_fails) {
    PrivKey priv_owner{}, priv_attacker{};
    PubKey pub_owner{}, pub_attacker{};
    std::string err;
    GenerateKeyPair(priv_owner, pub_owner, nullptr);
    GenerateKeyPair(priv_attacker, pub_attacker, nullptr);

    PubKeyHash owner_pkh = ComputePubKeyHash(pub_owner);
    Hash256 genesis = TestGenesisHash();
    Transaction tx = MakeSimpleTx(owner_pkh);

    SpentOutput spent{1000000000, OUT_TRANSFER};
    SignTransactionInput(tx, 0, spent, genesis, priv_attacker, nullptr);

    bool ok = VerifyTransactionInput(tx, 0, spent, genesis, owner_pkh, &err);
    ASSERT_TRUE(!ok, "attacker's signature should not verify against owner's PKH");

    PASS("wrong_key_fails");
}

// =============================================================================
// Hardening Tests (T16-T21)
// =============================================================================

// --- T16: input_index out of range returns error cleanly ---

TEST(input_index_out_of_range) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Hash256 genesis = TestGenesisHash();
    Transaction tx = MakeSimpleTx(sender_pkh);
    SpentOutput spent{1000000000, OUT_TRANSFER};

    // Sign with out-of-range index
    bool ok = SignTransactionInput(tx, 99, spent, genesis, priv, &err);
    ASSERT_TRUE(!ok, "sign with index 99 should fail");

    // Verify with out-of-range index
    ok = VerifyTransactionInput(tx, 99, spent, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "verify with index 99 should fail");

    // ComputeSighash with out-of-range → returns zeroed hash (not crash)
    Hash256 h = ComputeSighash(tx, 99, spent, genesis);
    Hash256 zeros{};
    ASSERT_EQ(h, zeros, "ComputeSighash OOB should return zeroed hash");

    PASS("input_index_out_of_range");
}

// --- T17: Invalid pubkey (garbage bytes) rejected ---

TEST(invalid_pubkey_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);
    SpentOutput spent{1000000000, OUT_TRANSFER};

    // Sign legitimately first
    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    // Overwrite pubkey with garbage (invalid prefix 0x04 = uncompressed)
    tx.inputs[0].pubkey[0] = 0x04;
    std::memset(tx.inputs[0].pubkey.data() + 1, 0xDE, 32);

    // Must fail PKH check (different pubkey → different hash)
    bool ok = VerifyTransactionInput(tx, 0, spent, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "garbage pubkey should fail verification");

    PASS("invalid_pubkey_rejected");
}

// --- T18: High-S signature explicitly rejected ---

TEST(high_s_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 genesis = TestGenesisHash();
    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Transaction tx = MakeSimpleTx(sender_pkh);
    SpentOutput spent{1000000000, OUT_TRANSFER};

    SignTransactionInput(tx, 0, spent, genesis, priv, nullptr);

    // Extract valid signature
    Sig64 sig{};
    std::memcpy(sig.data(), tx.inputs[0].signature.data(), 64);
    ASSERT_TRUE(IsLowS(sig), "should start as LOW-S");

    // Force high-S by negating: s = n - s
    EnforceLowS(sig);  // This is a no-op since already low
    // Manually make it high-S: set s[32] = 0xFF (way above n/2)
    sig[32] = 0xFF;
    std::memset(sig.data() + 33, 0xFF, 31);

    ASSERT_TRUE(!IsLowS(sig), "should now be HIGH-S");

    // Verify must reject
    Hash256 sighash = ComputeSighash(tx, 0, spent, genesis);
    bool ok = VerifySighash(pub, sighash, sig, &err);
    ASSERT_TRUE(!ok, "high-S signature should be rejected");

    PASS("high_s_rejected");
}

// --- T19: Empty outputs → hashOutputs still deterministic ---

TEST(empty_outputs_hash) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    // No outputs (tx_validation will reject later, but signer shouldn't crash)
    Hash256 ho1 = ComputeHashOutputs(tx);
    Hash256 ho2 = ComputeHashOutputs(tx);
    ASSERT_EQ(ho1, ho2, "hashOutputs of empty tx not deterministic");

    PASS("empty_outputs_hash");
}

// --- T20: r=0 signature rejected ---

TEST(r_zero_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 sighash{};
    std::memset(sighash.data(), 0xAB, 32);

    // Craft signature with r=0, s=valid
    Sig64 bad_sig{};
    std::memset(bad_sig.data(), 0x00, 32);       // r = 0
    std::memset(bad_sig.data() + 32, 0x01, 1);   // s = 1 (low, valid range)

    bool ok = VerifySighash(pub, sighash, bad_sig, &err);
    ASSERT_TRUE(!ok, "r=0 signature should be rejected (E4)");

    PASS("r_zero_rejected");
}

// --- T21: s=0 signature rejected ---

TEST(s_zero_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    Hash256 sighash{};
    std::memset(sighash.data(), 0xAB, 32);

    // Craft signature with r=1, s=0
    Sig64 bad_sig{};
    bad_sig[31] = 0x01;                           // r = 1
    std::memset(bad_sig.data() + 32, 0x00, 32);   // s = 0

    bool ok = VerifySighash(pub, sighash, bad_sig, &err);
    ASSERT_TRUE(!ok, "s=0 signature should be rejected (E5)");

    PASS("s_zero_rejected");
}

// --- T22: payload >255 rejected in sign and verify (not poison hash) ---

TEST(oversized_payload_rejected) {
    PrivKey priv{};
    PubKey pub{};
    std::string err;
    GenerateKeyPair(priv, pub, nullptr);

    PubKeyHash sender_pkh = ComputePubKeyHash(pub);
    Hash256 genesis = TestGenesisHash();
    Transaction tx = MakeSimpleTx(sender_pkh);

    // Add oversized payload to output
    tx.outputs[0].payload.resize(256, 0xAA);  // 256 > 255 max

    SpentOutput spent{1000000000, OUT_TRANSFER};

    // Sign must fail explicitly
    bool ok = SignTransactionInput(tx, 0, spent, genesis, priv, &err);
    ASSERT_TRUE(!ok, "sign should reject payload >255");

    // Verify must also fail explicitly
    ok = VerifyTransactionInput(tx, 0, spent, genesis, sender_pkh, &err);
    ASSERT_TRUE(!ok, "verify should reject payload >255");

    PASS("oversized_payload_rejected");
}

// =============================================================================
// Main
// =============================================================================

int main() {
    std::cout << "\n=== SOST Transaction Signer Tests (Phase 2, hardened) ===" << std::endl;
    std::cout << std::endl;

    std::cout << "\n--- Results ---" << std::endl;
    std::cout << "  Passed: " << tests_passed << std::endl;
    std::cout << "  Failed: " << tests_failed << std::endl;
    std::cout << std::endl;

    if (tests_failed > 0) {
        std::cerr << "*** FAILURES DETECTED ***" << std::endl;
        return 1;
    }

    std::cout << "All " << tests_passed << " tests passed." << std::endl;
    return 0;
}
