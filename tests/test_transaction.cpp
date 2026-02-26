// =============================================================================
// test_transaction.cpp — Serialization round-trip and edge case tests
// =============================================================================
//
// Tests canonical serialization of TxInput, TxOutput, and Transaction
// as specified in Design Document v1.2, Section 5.
//
// Every test validates: serialize → deserialize → re-serialize → compare bytes.
// If the bytes differ, the implementation has a consensus bug.
//
// =============================================================================

#include "sost/transaction.h"

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
// Helper: build a minimal standard transaction (1 input, 1 output)
// =============================================================================

static Transaction MakeMinimalStandardTx() {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    // Dummy prev_txid (all 0xAA)
    std::memset(in.prev_txid.data(), 0xAA, 32);
    in.prev_index = 0;
    // Dummy signature (all 0xBB)
    std::memset(in.signature.data(), 0xBB, 64);
    // Dummy pubkey (compressed, starts with 0x02)
    in.pubkey[0] = 0x02;
    std::memset(in.pubkey.data() + 1, 0xCC, 32);
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount = 785100863;  // 7.85100863 SOST in stocks
    out.type = OUT_TRANSFER;
    std::memset(out.pubkey_hash.data(), 0xDD, 20);
    // No payload (v1 standard)
    tx.outputs.push_back(out);

    return tx;
}

// =============================================================================
// Helper: build a coinbase transaction (3 typed outputs)
// =============================================================================

static Transaction MakeCoinbaseTx(int64_t height, int64_t reward) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    // Coinbase input
    TxInput in;
    std::memset(in.prev_txid.data(), 0x00, 32);      // 0x00*32
    in.prev_index = 0xFFFFFFFF;                        // sentinel
    // Signature: height (8 bytes LE) + miner_data (zeros)
    std::memset(in.signature.data(), 0x00, 64);
    uint64_t h = static_cast<uint64_t>(height);
    for (int i = 0; i < 8; ++i) {
        in.signature[i] = static_cast<Byte>(h & 0xFF);
        h >>= 8;
    }
    std::memset(in.pubkey.data(), 0x00, 33);           // 0x00*33
    tx.inputs.push_back(in);

    // Compute split: 50/25/25 with remainder to miner
    int64_t gold  = reward / 4;
    int64_t popc  = reward / 4;
    int64_t miner = reward - gold - popc;

    // Output 0: COINBASE_MINER
    TxOutput out_miner;
    out_miner.amount = miner;
    out_miner.type = OUT_COINBASE_MINER;
    std::memset(out_miner.pubkey_hash.data(), 0x11, 20);
    tx.outputs.push_back(out_miner);

    // Output 1: COINBASE_GOLD
    TxOutput out_gold;
    out_gold.amount = gold;
    out_gold.type = OUT_COINBASE_GOLD;
    std::memset(out_gold.pubkey_hash.data(), 0x22, 20);
    tx.outputs.push_back(out_gold);

    // Output 2: COINBASE_POPC
    TxOutput out_popc;
    out_popc.amount = popc;
    out_popc.type = OUT_COINBASE_POPC;
    std::memset(out_popc.pubkey_hash.data(), 0x33, 20);
    tx.outputs.push_back(out_popc);

    return tx;
}

// =============================================================================
// Tests
// =============================================================================

// --- T1: Minimal standard tx round-trip ---

TEST(minimal_standard_roundtrip) {
    Transaction tx = MakeMinimalStandardTx();

    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(tx.Serialize(buf, &err), "serialize failed: " + err);

    // Expected size:
    //   version(4) + tx_type(1) + CompactSize(1) + input(133)
    //   + CompactSize(1) + output(30) = 170 bytes
    ASSERT_EQ(buf.size(), 170u, "unexpected serialized size");

    Transaction tx2;
    ASSERT_TRUE(Transaction::Deserialize(buf, tx2, &err), "deserialize failed: " + err);

    // Re-serialize and compare bytes
    std::vector<Byte> buf2;
    ASSERT_TRUE(tx2.Serialize(buf2, &err), "re-serialize failed: " + err);
    ASSERT_EQ(buf, buf2, "round-trip bytes mismatch");

    PASS("minimal_standard_roundtrip");
}

// --- T2: Coinbase tx round-trip (3 outputs, typed) ---

TEST(coinbase_roundtrip) {
    int64_t reward = 785100863;  // Genesis block reward in stocks
    Transaction tx = MakeCoinbaseTx(0, reward);

    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(tx.Serialize(buf, &err), "serialize failed: " + err);

    // Expected: version(4) + tx_type(1) + CS(1) + input(133)
    //           + CS(1) + 3 * output(30) = 230 bytes
    ASSERT_EQ(buf.size(), 230u, "unexpected coinbase serialized size");

    Transaction tx2;
    ASSERT_TRUE(Transaction::Deserialize(buf, tx2, &err), "deserialize failed: " + err);

    // Verify typed outputs survived round-trip
    ASSERT_EQ(tx2.outputs.size(), 3u, "expected 3 outputs");
    ASSERT_EQ(tx2.outputs[0].type, OUT_COINBASE_MINER, "output[0] type mismatch");
    ASSERT_EQ(tx2.outputs[1].type, OUT_COINBASE_GOLD, "output[1] type mismatch");
    ASSERT_EQ(tx2.outputs[2].type, OUT_COINBASE_POPC, "output[2] type mismatch");

    // Verify coinbase split: 50/25/25 with remainder to miner
    int64_t gold = reward / 4;
    int64_t popc = reward / 4;
    int64_t miner = reward - gold - popc;
    ASSERT_EQ(tx2.outputs[0].amount, miner, "miner amount mismatch");
    ASSERT_EQ(tx2.outputs[1].amount, gold, "gold amount mismatch");
    ASSERT_EQ(tx2.outputs[2].amount, popc, "popc amount mismatch");

    // Verify exact conservation
    int64_t sum = tx2.outputs[0].amount + tx2.outputs[1].amount + tx2.outputs[2].amount;
    ASSERT_EQ(sum, reward, "coinbase sum != reward (conservation violation)");

    // Verify payload_len = 0 for all coinbase outputs
    for (size_t i = 0; i < 3; ++i) {
        ASSERT_EQ(tx2.outputs[i].payload.size(), 0u, "coinbase output has non-empty payload");
    }

    // Re-serialize
    std::vector<Byte> buf2;
    ASSERT_TRUE(tx2.Serialize(buf2, &err), "re-serialize failed: " + err);
    ASSERT_EQ(buf, buf2, "coinbase round-trip bytes mismatch");

    PASS("coinbase_roundtrip");
}

// --- T3: txid is double SHA256 and deterministic ---

TEST(txid_double_sha256) {
    Transaction tx = MakeMinimalStandardTx();

    Hash256 txid1{}, txid2{};
    std::string err;
    ASSERT_TRUE(tx.ComputeTxId(txid1, &err), "txid1 failed: " + err);
    ASSERT_TRUE(tx.ComputeTxId(txid2, &err), "txid2 failed: " + err);

    // Same transaction must produce same txid
    ASSERT_EQ(txid1, txid2, "txid not deterministic");

    // txid must not be all zeros (sanity check)
    Hash256 zeros{};
    ASSERT_NE(txid1, zeros, "txid is all zeros");

    // Modify one byte → txid must change
    Transaction tx_mod = tx;
    tx_mod.inputs[0].prev_index = 1;  // Change prev_index from 0 to 1
    Hash256 txid_mod{};
    ASSERT_TRUE(tx_mod.ComputeTxId(txid_mod, &err), "txid_mod failed: " + err);
    ASSERT_NE(txid1, txid_mod, "txid unchanged after modification (catastrophic)");

    PASS("txid_double_sha256");
}

// --- T4: txid hex string format ---

TEST(txid_hex_format) {
    Transaction tx = MakeMinimalStandardTx();

    std::string err;
    std::string hex = tx.ComputeTxIdHex(&err);
    ASSERT_EQ(hex.size(), 64u, "txid hex should be 64 chars");

    // Verify all chars are valid hex
    for (char c : hex) {
        bool valid = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        ASSERT_TRUE(valid, "txid hex contains non-hex char");
    }

    PASS("txid_hex_format");
}

// --- T5: Output with payload (future-ready, still deserializes) ---

TEST(output_with_payload) {
    TxOutput out;
    out.amount = 100000000;  // 1 SOST
    out.type = OUT_BOND_LOCK;  // Reserved type (inactive in v1 consensus)
    std::memset(out.pubkey_hash.data(), 0xEE, 20);

    // Simulate a bond payload: schema(1) + expiry(4) + flags(1) + reserved(2) = 8
    out.payload = {0x01, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00};

    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(out.SerializeTo(buf, &err), "serialize output with payload failed: " + err);

    // Expected: 8 + 1 + 20 + 1 + 8 = 38 bytes
    ASSERT_EQ(buf.size(), 38u, "unexpected output size with payload");

    TxOutput out2;
    size_t offset = 0;
    ASSERT_TRUE(TxOutput::DeserializeFrom(buf, offset, out2, &err),
                "deserialize output with payload failed: " + err);

    ASSERT_EQ(out2.amount, out.amount, "payload output amount mismatch");
    ASSERT_EQ(out2.type, OUT_BOND_LOCK, "payload output type mismatch");
    ASSERT_EQ(out2.payload.size(), 8u, "payload size mismatch");
    ASSERT_EQ(out2.payload[0], 0x01, "payload schema_version mismatch");

    PASS("output_with_payload");
}

// --- T6: Empty payload serializes as single zero byte ---

TEST(empty_payload_byte) {
    TxOutput out;
    out.amount = 50000000;
    out.type = OUT_TRANSFER;
    std::memset(out.pubkey_hash.data(), 0xFF, 20);
    // payload intentionally left empty

    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(out.SerializeTo(buf, &err), "serialize failed: " + err);

    // Last byte before end should be payload_len = 0x00
    ASSERT_EQ(buf.size(), 30u, "expected 30 bytes for output with empty payload");
    ASSERT_EQ(buf[29], 0x00, "payload_len byte should be 0x00");

    PASS("empty_payload_byte");
}

// --- T7: CompactSize encoding correctness ---

TEST(compact_size_encoding) {
    // Test value < 0xFD (1 byte)
    {
        std::vector<Byte> buf;
        WriteCompactSize(buf, 100);
        ASSERT_EQ(buf.size(), 1u, "CS(100) should be 1 byte");
        ASSERT_EQ(buf[0], 100, "CS(100) value mismatch");
    }

    // Test value == 0xFC (still 1 byte, boundary)
    {
        std::vector<Byte> buf;
        WriteCompactSize(buf, 0xFC);
        ASSERT_EQ(buf.size(), 1u, "CS(0xFC) should be 1 byte");
        ASSERT_EQ(buf[0], 0xFC, "CS(0xFC) value mismatch");
    }

    // Test value == 0xFD (3 bytes: 0xFD + u16)
    {
        std::vector<Byte> buf;
        WriteCompactSize(buf, 0xFD);
        ASSERT_EQ(buf.size(), 3u, "CS(0xFD) should be 3 bytes");
        ASSERT_EQ(buf[0], 0xFD, "CS(0xFD) marker mismatch");

        // Round-trip
        size_t offset = 0;
        uint64_t val = 0;
        std::string err;
        ASSERT_TRUE(ReadCompactSize(buf, offset, val, &err), "CS read failed: " + err);
        ASSERT_EQ(val, 0xFDu, "CS(0xFD) round-trip mismatch");
    }

    // Test value == 0xFFFF (3 bytes)
    {
        std::vector<Byte> buf;
        WriteCompactSize(buf, 0xFFFF);
        ASSERT_EQ(buf.size(), 3u, "CS(0xFFFF) should be 3 bytes");
    }

    // Test value == 0x10000 (5 bytes: 0xFE + u32)
    {
        std::vector<Byte> buf;
        WriteCompactSize(buf, 0x10000);
        ASSERT_EQ(buf.size(), 5u, "CS(0x10000) should be 5 bytes");
        ASSERT_EQ(buf[0], 0xFE, "CS(0x10000) marker mismatch");
    }

    PASS("compact_size_encoding");
}

// --- T8: Non-canonical CompactSize rejected ---

TEST(compact_size_non_canonical_rejected) {
    // Encode value 100 using 3-byte form (non-canonical)
    std::vector<Byte> bad = {0xFD, 100, 0x00};
    size_t offset = 0;
    uint64_t val = 0;
    std::string err;
    bool ok = ReadCompactSize(bad, offset, val, &err);
    ASSERT_TRUE(!ok, "non-canonical CompactSize should be rejected");

    PASS("compact_size_non_canonical_rejected");
}

// --- T9: Deserialize rejects trailing bytes ---

TEST(reject_trailing_bytes) {
    Transaction tx = MakeMinimalStandardTx();
    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(tx.Serialize(buf, &err), "serialize failed: " + err);

    // Append garbage byte
    buf.push_back(0xFF);

    Transaction tx2;
    bool ok = Transaction::Deserialize(buf, tx2, &err);
    ASSERT_TRUE(!ok, "should reject trailing bytes");

    PASS("reject_trailing_bytes");
}

// --- T10: Deserialize rejects zero inputs ---

TEST(reject_zero_inputs) {
    // Manually craft: version(1) + tx_type(0) + num_inputs(0)
    std::vector<Byte> buf;
    // version = 1 (LE)
    buf.push_back(0x01); buf.push_back(0x00);
    buf.push_back(0x00); buf.push_back(0x00);
    // tx_type = 0x00
    buf.push_back(0x00);
    // num_inputs = 0
    buf.push_back(0x00);

    Transaction tx;
    std::string err;
    bool ok = Transaction::Deserialize(buf, tx, &err);
    ASSERT_TRUE(!ok, "should reject zero inputs");

    PASS("reject_zero_inputs");
}

// --- T11: Deserialize rejects too many inputs ---

TEST(reject_too_many_inputs) {
    // num_inputs = 257 (CompactSize 3 bytes)
    std::vector<Byte> buf;
    buf.push_back(0x01); buf.push_back(0x00);
    buf.push_back(0x00); buf.push_back(0x00);  // version = 1
    buf.push_back(0x00);                         // tx_type = 0
    buf.push_back(0xFD);                         // CompactSize marker
    buf.push_back(0x01); buf.push_back(0x01);   // 257 in u16 LE

    Transaction tx;
    std::string err;
    bool ok = Transaction::Deserialize(buf, tx, &err);
    ASSERT_TRUE(!ok, "should reject 257 inputs");

    PASS("reject_too_many_inputs");
}

// --- T12: Multi-input/output transaction ---

TEST(multi_input_output) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    // 3 inputs
    for (int i = 0; i < 3; ++i) {
        TxInput in;
        std::memset(in.prev_txid.data(), static_cast<Byte>(0x10 + i), 32);
        in.prev_index = static_cast<uint32_t>(i);
        std::memset(in.signature.data(), static_cast<Byte>(0x20 + i), 64);
        in.pubkey[0] = 0x02;
        std::memset(in.pubkey.data() + 1, static_cast<Byte>(0x30 + i), 32);
        tx.inputs.push_back(in);
    }

    // 5 outputs (different amounts)
    for (int i = 0; i < 5; ++i) {
        TxOutput out;
        out.amount = (i + 1) * 100000000LL;  // 1, 2, 3, 4, 5 SOST
        out.type = OUT_TRANSFER;
        std::memset(out.pubkey_hash.data(), static_cast<Byte>(0x40 + i), 20);
        tx.outputs.push_back(out);
    }

    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(tx.Serialize(buf, &err), "serialize multi failed: " + err);

    // Expected: 4 + 1 + 1 + 3*133 + 1 + 5*30 = 556 bytes
    ASSERT_EQ(buf.size(), 556u, "unexpected multi tx size");

    Transaction tx2;
    ASSERT_TRUE(Transaction::Deserialize(buf, tx2, &err), "deserialize multi failed: " + err);
    ASSERT_EQ(tx2.inputs.size(), 3u, "input count mismatch");
    ASSERT_EQ(tx2.outputs.size(), 5u, "output count mismatch");

    // Verify each output amount
    for (int i = 0; i < 5; ++i) {
        ASSERT_EQ(tx2.outputs[i].amount, (i + 1) * 100000000LL, "output amount mismatch");
    }

    // Round-trip
    std::vector<Byte> buf2;
    ASSERT_TRUE(tx2.Serialize(buf2, &err), "re-serialize failed: " + err);
    ASSERT_EQ(buf, buf2, "multi tx round-trip mismatch");

    PASS("multi_input_output");
}

// --- T13: Payload > 255 bytes rejected by SerializeTo ---

TEST(reject_oversized_payload) {
    TxOutput out;
    out.amount = 100;
    out.type = OUT_TRANSFER;
    out.payload.resize(256, 0xAA);  // 256 > 255 max

    std::vector<Byte> buf;
    std::string err;
    bool ok = out.SerializeTo(buf, &err);
    ASSERT_TRUE(!ok, "should reject payload > 255 bytes");

    PASS("reject_oversized_payload");
}

// --- T14: Coinbase height encoding in signature field ---

TEST(coinbase_height_encoding) {
    int64_t height = 131553;  // End of epoch 0
    Transaction tx = MakeCoinbaseTx(height, 785100863);

    // Verify height bytes in signature[0..7]
    const auto& sig = tx.inputs[0].signature;
    uint64_t decoded = 0;
    for (int i = 0; i < 8; ++i) {
        decoded |= static_cast<uint64_t>(sig[i]) << (8 * i);
    }
    ASSERT_EQ(static_cast<int64_t>(decoded), height, "coinbase height encoding mismatch");

    // Round-trip through serialization
    std::vector<Byte> buf;
    std::string err;
    ASSERT_TRUE(tx.Serialize(buf, &err), "serialize failed: " + err);

    Transaction tx2;
    ASSERT_TRUE(Transaction::Deserialize(buf, tx2, &err), "deserialize failed: " + err);

    // Verify height survived
    uint64_t decoded2 = 0;
    for (int i = 0; i < 8; ++i) {
        decoded2 |= static_cast<uint64_t>(tx2.inputs[0].signature[i]) << (8 * i);
    }
    ASSERT_EQ(static_cast<int64_t>(decoded2), height, "height lost in round-trip");

    PASS("coinbase_height_encoding");
}

// --- T15: Different transactions produce different txids ---

TEST(different_tx_different_txid) {
    Transaction tx1 = MakeMinimalStandardTx();
    Transaction tx2 = MakeMinimalStandardTx();
    tx2.outputs[0].amount = 1;  // Different amount

    Hash256 id1{}, id2{};
    std::string err;
    ASSERT_TRUE(tx1.ComputeTxId(id1, &err), "txid1 failed");
    ASSERT_TRUE(tx2.ComputeTxId(id2, &err), "txid2 failed");
    ASSERT_NE(id1, id2, "different transactions must have different txids");

    PASS("different_tx_different_txid");
}

// =============================================================================
// Main
// =============================================================================

int main() {
    std::cout << "\n=== SOST Transaction Serialization Tests ===" << std::endl;
    std::cout << std::endl;

    // Tests are auto-registered by static constructors above.
    // By the time main() runs, all tests have already executed.

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
