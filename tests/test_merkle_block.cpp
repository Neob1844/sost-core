// =============================================================================
// SOST — Phase 5: Merkle Tree + Block Header Tests
//
// M01-M12: Merkle tree
// B01-B18: Block header + block serialization
// I01-I05: Integration (Phase 3/4 + Phase 5)
// =============================================================================

#include <sost/merkle.h>
#include <sost/block.h>
#include <sost/tx_signer.h>
#include <sost/tx_validation.h>
#include <sost/utxo_set.h>
#include <sost/params.h>

#include <openssl/sha.h>
#include <cstring>
#include <cstdio>
#include <cassert>
#include <algorithm>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define RUN(name)                                                   \
    do {                                                            \
        printf("  %-44s", #name " ...");                            \
        fflush(stdout);                                             \
        bool ok_ = name();                                         \
        printf("%s\n", ok_ ? "PASS" : "*** FAIL ***");             \
        ok_ ? ++g_pass : ++g_fail;                                 \
    } while (0)

#define EXPECT(cond)                                                \
    do { if (!(cond)) {                                             \
        printf("\n    EXPECT failed: %s  [%s:%d]\n",                \
               #cond, __FILE__, __LINE__);                          \
        return false;                                               \
    }} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static Hash256 MakeHash(uint8_t fill) {
    Hash256 h;
    h.fill(fill);
    return h;
}

/// SHA256(SHA256(data))
static Hash256 DoubleSha256(const uint8_t* data, size_t len) {
    Hash256 a{}, b{};
    SHA256(data, len, a.data());
    SHA256(a.data(), 32, b.data());
    return b;
}

/// Build a minimal valid coinbase for testing
static Transaction MakeTestCoinbase(
    int64_t height,
    int64_t subsidy,  // total (miner+gold+popc)
    int64_t fees,
    const PubKeyHash& miner_pkh,
    const PubKeyHash& gold_pkh,
    const PubKeyHash& popc_pkh)
{
    Transaction cb;
    cb.version = 1;
    cb.tx_type = TX_TYPE_COINBASE;

    // Coinbase input
    TxInput cbin;
    cbin.prev_txid.fill(0x00);
    cbin.prev_index = 0xFFFFFFFF;
    // sig = height(8 LE) + miner_data(56 zeros)
    cbin.signature.fill(0x00);
    for (int i = 0; i < 8; ++i) {
        cbin.signature[i] = (uint8_t)((height >> (i * 8)) & 0xFF);
    }
    cbin.pubkey.fill(0x00);
    cb.inputs.push_back(cbin);

    int64_t total = subsidy + fees;
    int64_t miner_amt = (total * 50) / 100;
    int64_t gold_amt  = (total * 25) / 100;
    int64_t popc_amt  = total - miner_amt - gold_amt;

    // Remainder goes to miner
    if (total - miner_amt - gold_amt - popc_amt > 0) {
        miner_amt += total - miner_amt - gold_amt - popc_amt;
    }

    TxOutput out_miner;
    out_miner.amount = miner_amt;
    out_miner.type = OUT_COINBASE_MINER;
    out_miner.pubkey_hash = miner_pkh;
    cb.outputs.push_back(out_miner);

    TxOutput out_gold;
    out_gold.amount = gold_amt;
    out_gold.type = OUT_COINBASE_GOLD;
    out_gold.pubkey_hash = gold_pkh;
    cb.outputs.push_back(out_gold);

    TxOutput out_popc;
    out_popc.amount = popc_amt;
    out_popc.type = OUT_COINBASE_POPC;
    out_popc.pubkey_hash = popc_pkh;
    cb.outputs.push_back(out_popc);

    return cb;
}

// ============================================================================
// MERKLE TREE TESTS
// ============================================================================

// M01: Empty → 0x00*32
static bool M01_empty_merkle() {
    std::vector<Hash256> txids;
    Hash256 root = ComputeMerkleRoot(txids);
    EXPECT(root == Hash256{});
    return true;
}

// M02: Single txid → itself
static bool M02_single_txid() {
    Hash256 txid = MakeHash(0xAA);
    std::vector<Hash256> txids = {txid};
    Hash256 root = ComputeMerkleRoot(txids);
    EXPECT(root == txid);
    return true;
}

// M03: Two txids → MerkleHash(A, B)
static bool M03_two_txids() {
    Hash256 a = MakeHash(0x01);
    Hash256 b = MakeHash(0x02);
    std::vector<Hash256> txids = {a, b};

    Hash256 root = ComputeMerkleRoot(txids);
    Hash256 expected = MerkleHash(a, b);
    EXPECT(root == expected);
    return true;
}

// M04: Three txids → odd count, last duplicated
// Tree: [A, B, C] → layer1 = [H(A,B), H(C,C)] → root = H(layer1[0], layer1[1])
static bool M04_three_txids_odd() {
    Hash256 a = MakeHash(0x10);
    Hash256 b = MakeHash(0x20);
    Hash256 c = MakeHash(0x30);

    Hash256 root = ComputeMerkleRoot({a, b, c});

    // Manual computation
    Hash256 ab = MerkleHash(a, b);
    Hash256 cc = MerkleHash(c, c);  // duplicate last
    Hash256 expected = MerkleHash(ab, cc);

    EXPECT(root == expected);
    return true;
}

// M05: Four txids → balanced tree
static bool M05_four_txids_balanced() {
    Hash256 a = MakeHash(0x11);
    Hash256 b = MakeHash(0x22);
    Hash256 c = MakeHash(0x33);
    Hash256 d = MakeHash(0x44);

    Hash256 root = ComputeMerkleRoot({a, b, c, d});

    Hash256 ab = MerkleHash(a, b);
    Hash256 cd = MerkleHash(c, d);
    Hash256 expected = MerkleHash(ab, cd);

    EXPECT(root == expected);
    return true;
}

// M06: Five txids → unbalanced (5 → [3, 2] → etc.)
static bool M06_five_txids() {
    Hash256 a = MakeHash(0x01);
    Hash256 b = MakeHash(0x02);
    Hash256 c = MakeHash(0x03);
    Hash256 d = MakeHash(0x04);
    Hash256 e = MakeHash(0x05);

    Hash256 root = ComputeMerkleRoot({a, b, c, d, e});

    // Layer 0: [A, B, C, D, E]
    // Layer 1: [H(A,B), H(C,D), H(E,E)]
    // Layer 2: [H(H(A,B), H(C,D)), H(H(E,E), H(E,E))]
    // Root = H(layer2[0], layer2[1])
    Hash256 ab = MerkleHash(a, b);
    Hash256 cd = MerkleHash(c, d);
    Hash256 ee = MerkleHash(e, e);

    Hash256 abcd = MerkleHash(ab, cd);
    Hash256 eeee = MerkleHash(ee, ee);

    Hash256 expected = MerkleHash(abcd, eeee);
    EXPECT(root == expected);
    return true;
}

// M07: MerkleHash is deterministic
static bool M07_deterministic() {
    Hash256 a = MakeHash(0xAB);
    Hash256 b = MakeHash(0xCD);

    Hash256 h1 = MerkleHash(a, b);
    Hash256 h2 = MerkleHash(a, b);
    EXPECT(h1 == h2);

    // Order matters
    Hash256 h3 = MerkleHash(b, a);
    EXPECT(h1 != h3);
    return true;
}

// M08: MerkleHash matches manual double-SHA256
static bool M08_manual_double_sha256() {
    Hash256 a = MakeHash(0x01);
    Hash256 b = MakeHash(0x02);

    uint8_t combined[64];
    std::memcpy(combined, a.data(), 32);
    std::memcpy(combined + 32, b.data(), 32);

    Hash256 expected = DoubleSha256(combined, 64);
    Hash256 result = MerkleHash(a, b);
    EXPECT(result == expected);
    return true;
}

// M09: MerkleLayer with even count
static bool M09_layer_even() {
    Hash256 a = MakeHash(0x01);
    Hash256 b = MakeHash(0x02);
    Hash256 c = MakeHash(0x03);
    Hash256 d = MakeHash(0x04);

    auto layer = MerkleLayer({a, b, c, d});
    EXPECT(layer.size() == 2);
    EXPECT(layer[0] == MerkleHash(a, b));
    EXPECT(layer[1] == MerkleHash(c, d));
    return true;
}

// M10: MerkleLayer with odd count
static bool M10_layer_odd() {
    Hash256 a = MakeHash(0x10);
    Hash256 b = MakeHash(0x20);
    Hash256 c = MakeHash(0x30);

    auto layer = MerkleLayer({a, b, c});
    EXPECT(layer.size() == 2);
    EXPECT(layer[0] == MerkleHash(a, b));
    EXPECT(layer[1] == MerkleHash(c, c));  // duplicate
    return true;
}

// M11: ComputeMerkleRootFromTxs with real transactions
static bool M11_from_txs() {
    // Create a minimal coinbase
    PubKeyHash pkh{};
    pkh.fill(0x01);
    Transaction cb = MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh);

    Hash256 root{};
    std::string err;
    EXPECT(ComputeMerkleRootFromTxs({cb}, root, &err));

    // Single tx → root == txid
    Hash256 txid{};
    EXPECT(cb.ComputeTxId(txid, &err));
    EXPECT(root == txid);
    return true;
}

// M12: Large tree (256 txids)
static bool M12_large_tree() {
    std::vector<Hash256> txids;
    for (int i = 0; i < 256; ++i) {
        txids.push_back(MakeHash((uint8_t)i));
    }

    Hash256 root = ComputeMerkleRoot(txids);

    // Root must be non-zero, deterministic
    EXPECT(root != Hash256{});

    // Recompute → same result
    Hash256 root2 = ComputeMerkleRoot(txids);
    EXPECT(root == root2);

    // Different input → different root
    txids[0] = MakeHash(0xFF);
    Hash256 root3 = ComputeMerkleRoot(txids);
    EXPECT(root3 != root);

    return true;
}

// ============================================================================
// BLOCK HEADER TESTS
// ============================================================================

// B01: Header serialization is exactly 96 bytes
static bool B01_header_size() {
    BlockHeader hdr;
    hdr.version = 1;
    hdr.prev_block_hash = MakeHash(0xAA);
    hdr.merkle_root = MakeHash(0xBB);
    hdr.timestamp = 1773597600;
    hdr.bits_q = GENESIS_BITSQ;
    hdr.nonce = 42;
    hdr.height = 0;

    auto buf = hdr.Serialize();
    EXPECT(buf.size() == 96);

    std::vector<Byte> vec;
    hdr.SerializeTo(vec);
    EXPECT(vec.size() == 96);
    return true;
}

// B02: Header roundtrip (serialize → deserialize → equal)
static bool B02_header_roundtrip() {
    BlockHeader hdr;
    hdr.version = 1;
    hdr.prev_block_hash = MakeHash(0x11);
    hdr.merkle_root = MakeHash(0x22);
    hdr.timestamp = 1773597600;
    hdr.bits_q = GENESIS_BITSQ;
    hdr.nonce = 999999;
    hdr.height = 1000;

    std::vector<Byte> buf;
    hdr.SerializeTo(buf);

    BlockHeader hdr2;
    size_t offset = 0;
    std::string err;
    EXPECT(BlockHeader::DeserializeFrom(buf, offset, hdr2, &err));
    EXPECT(offset == 96);
    EXPECT(hdr == hdr2);
    return true;
}

// B03: Block hash is deterministic and changes with any field
static bool B03_block_hash_deterministic() {
    BlockHeader hdr;
    hdr.version = 1;
    hdr.prev_block_hash = MakeHash(0xAA);
    hdr.merkle_root = MakeHash(0xBB);
    hdr.timestamp = 1773597600;
    hdr.bits_q = GENESIS_BITSQ;
    hdr.nonce = 42;
    hdr.height = 0;

    Hash256 h1 = hdr.ComputeBlockHash();
    Hash256 h2 = hdr.ComputeBlockHash();
    EXPECT(h1 == h2);

    // Change nonce → different hash
    hdr.nonce = 43;
    Hash256 h3 = hdr.ComputeBlockHash();
    EXPECT(h3 != h1);

    // Change height → different hash
    hdr.nonce = 42;
    hdr.height = 1;
    Hash256 h4 = hdr.ComputeBlockHash();
    EXPECT(h4 != h1);
    return true;
}

// B04: Block hash matches manual SHA256²
static bool B04_hash_manual_verification() {
    BlockHeader hdr;
    hdr.version = 1;
    hdr.timestamp = 1773597600;
    hdr.bits_q = GENESIS_BITSQ;

    auto serialized = hdr.Serialize();
    Hash256 expected = DoubleSha256(serialized.data(), 96);
    Hash256 actual = hdr.ComputeBlockHash();
    EXPECT(actual == expected);
    return true;
}

// B05: Deserialize insufficient data → error
static bool B05_deserialize_short() {
    std::vector<Byte> buf(50, 0x00);  // < 96 bytes
    size_t offset = 0;
    BlockHeader hdr;
    std::string err;
    EXPECT(!BlockHeader::DeserializeFrom(buf, offset, hdr, &err));
    EXPECT(err.find("insufficient") != std::string::npos);
    return true;
}

// B06: Genesis header helper
static bool B06_genesis_header() {
    Hash256 root = MakeHash(0xAA);
    int64_t ts = 1773597600;
    uint32_t bits = GENESIS_BITSQ;

    BlockHeader hdr = MakeGenesisHeader(root, ts, bits);
    EXPECT(hdr.version == 1);
    EXPECT(hdr.prev_block_hash == Hash256{});  // all zeros
    EXPECT(hdr.merkle_root == root);
    EXPECT(hdr.timestamp == ts);
    EXPECT(hdr.bits_q == bits);
    EXPECT(hdr.nonce == 0);
    EXPECT(hdr.height == 0);
    return true;
}

// B07: Header equality / inequality
static bool B07_equality() {
    BlockHeader a, b;
    a.version = 1; a.timestamp = 100; a.bits_q = 200; a.nonce = 300; a.height = 0;
    b = a;

    EXPECT(a == b);
    b.nonce = 301;
    EXPECT(a != b);
    return true;
}

// B08: LE encoding verification (individual fields)
static bool B08_le_encoding() {
    BlockHeader hdr;
    hdr.version = 0x01020304;
    hdr.timestamp = 0x0102030405060708LL;
    hdr.bits_q = 0xAABBCCDD;
    hdr.nonce = 0x1122334455667788ULL;
    hdr.height = 0x0A0B0C0D0E0F1011LL;

    auto buf = hdr.Serialize();

    // version at offset 0: LE → 04 03 02 01
    EXPECT(buf[0] == 0x04);
    EXPECT(buf[1] == 0x03);
    EXPECT(buf[2] == 0x02);
    EXPECT(buf[3] == 0x01);

    // timestamp at offset 68: LE → 08 07 06 05 04 03 02 01
    EXPECT(buf[68] == 0x08);
    EXPECT(buf[69] == 0x07);
    EXPECT(buf[75] == 0x01);

    // bits_q at offset 76: LE → DD CC BB AA
    EXPECT(buf[76] == 0xDD);
    EXPECT(buf[77] == 0xCC);
    EXPECT(buf[78] == 0xBB);
    EXPECT(buf[79] == 0xAA);

    // nonce at offset 80: LE → 88 77 66 55 44 33 22 11
    EXPECT(buf[80] == 0x88);
    EXPECT(buf[81] == 0x77);
    EXPECT(buf[87] == 0x11);

    // height at offset 88: LE → 11 10 0F 0E 0D 0C 0B 0A
    EXPECT(buf[88] == 0x11);
    EXPECT(buf[89] == 0x10);
    EXPECT(buf[95] == 0x0A);

    return true;
}

// B09: Block hash hex string
static bool B09_hash_hex() {
    BlockHeader hdr;
    hdr.version = 1;
    hdr.timestamp = 1773597600;
    hdr.bits_q = GENESIS_BITSQ;

    std::string hex = hdr.ComputeBlockHashHex();
    EXPECT(hex.size() == 64);  // 32 bytes * 2

    // Verify hex chars
    for (char c : hex) {
        EXPECT((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
    }
    return true;
}

// B10: prev_block_hash at correct offset (bytes 4-35)
static bool B10_prev_hash_offset() {
    BlockHeader hdr;
    hdr.prev_block_hash = MakeHash(0xDE);

    auto buf = hdr.Serialize();
    for (int i = 4; i < 36; ++i) {
        EXPECT(buf[i] == 0xDE);
    }
    return true;
}

// B11: merkle_root at correct offset (bytes 36-67)
static bool B11_merkle_offset() {
    BlockHeader hdr;
    hdr.merkle_root = MakeHash(0xFE);

    auto buf = hdr.Serialize();
    for (int i = 36; i < 68; ++i) {
        EXPECT(buf[i] == 0xFE);
    }
    return true;
}

// ============================================================================
// BLOCK (FULL) TESTS
// ============================================================================

// B12: Block roundtrip (header + txs)
static bool B12_block_roundtrip() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.timestamp = 1773597600;
    blk.header.bits_q = GENESIS_BITSQ;
    blk.header.height = 0;

    // One coinbase tx
    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh));

    // Compute merkle root
    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));

    // Serialize
    std::vector<Byte> buf;
    EXPECT(blk.SerializeTo(buf, &err));

    // Deserialize
    Block blk2;
    size_t offset = 0;
    EXPECT(Block::DeserializeFrom(buf, offset, blk2, &err));
    EXPECT(offset == buf.size());

    // Verify
    EXPECT(blk2.header == blk.header);
    EXPECT(blk2.txs.size() == 1);
    EXPECT(blk2.txs[0].tx_type == TX_TYPE_COINBASE);
    return true;
}

// B13: VerifyMerkleRoot passes on correct block
static bool B13_verify_merkle_correct() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 0;
    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));
    EXPECT(blk.VerifyMerkleRoot(&err));
    return true;
}

// B14: VerifyMerkleRoot fails on tampered root
static bool B14_verify_merkle_tampered() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 0;
    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));

    // Tamper
    blk.header.merkle_root[0] ^= 0xFF;
    EXPECT(!blk.VerifyMerkleRoot(&err));
    EXPECT(err.find("mismatch") != std::string::npos);
    return true;
}

// B15: Block with multiple transactions
static bool B15_block_multi_tx() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 5;

    // Coinbase
    blk.txs.push_back(MakeTestCoinbase(5, 785100863, 1000, pkh, pkh, pkh));

    // Standard tx
    Transaction std_tx;
    std_tx.version = 1;
    std_tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = MakeHash(0xAA);
    in.prev_index = 0;
    in.signature.fill(0x01);
    in.pubkey.fill(0x02);
    std_tx.inputs.push_back(in);

    TxOutput out;
    out.amount = 50000;
    out.type = OUT_TRANSFER;
    out.pubkey_hash = pkh;
    std_tx.outputs.push_back(out);

    blk.txs.push_back(std_tx);

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));

    // Merkle root with 2 txs → H(txid0, txid1)
    Hash256 txid0{}, txid1{};
    EXPECT(blk.txs[0].ComputeTxId(txid0, &err));
    EXPECT(blk.txs[1].ComputeTxId(txid1, &err));

    Hash256 expected_root = MerkleHash(txid0, txid1);
    EXPECT(blk.header.merkle_root == expected_root);
    EXPECT(blk.VerifyMerkleRoot(&err));
    return true;
}

// B16: Deserialize zero tx_count → error
static bool B16_deserialize_zero_txs() {
    // 96 bytes header + compact_size 0
    std::vector<Byte> buf(97, 0x00);
    buf[96] = 0x00;  // tx_count = 0

    Block blk;
    size_t offset = 0;
    std::string err;
    EXPECT(!Block::DeserializeFrom(buf, offset, blk, &err));
    EXPECT(err.find("tx_count = 0") != std::string::npos);
    return true;
}

// B17: Block EstimateSize
static bool B17_estimate_size() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 0;
    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));

    size_t sz = blk.EstimateSize();
    EXPECT(sz > 96);  // header + at least some tx bytes

    // Cross-check with actual serialize
    std::vector<Byte> buf;
    EXPECT(blk.SerializeTo(buf, &err));
    EXPECT(sz == buf.size());
    return true;
}

// B18: Block hash chain (block 1's prev_hash = block 0's hash)
static bool B18_hash_chain() {
    BlockHeader blk0;
    blk0.version = 1;
    blk0.prev_block_hash = Hash256{};
    blk0.merkle_root = MakeHash(0x11);
    blk0.timestamp = 1773597600;
    blk0.bits_q = GENESIS_BITSQ;
    blk0.nonce = 42;
    blk0.height = 0;

    Hash256 hash0 = blk0.ComputeBlockHash();

    BlockHeader blk1;
    blk1.version = 1;
    blk1.prev_block_hash = hash0;
    blk1.merkle_root = MakeHash(0x22);
    blk1.timestamp = 1772237400;
    blk1.bits_q = GENESIS_BITSQ;
    blk1.nonce = 99;
    blk1.height = 1;

    // Verify chain
    EXPECT(blk1.prev_block_hash == hash0);
    EXPECT(blk1.prev_block_hash != Hash256{});

    Hash256 hash1 = blk1.ComputeBlockHash();
    EXPECT(hash1 != hash0);
    return true;
}

// ============================================================================
// INTEGRATION TESTS (Phase 3/4 + Phase 5)
// ============================================================================

// I01: Full block: coinbase → UTXO set → merkle root → block hash
static bool I01_full_block_lifecycle() {
    PubKeyHash miner_pkh, gold_pkh, popc_pkh;
    miner_pkh.fill(0x01);
    gold_pkh.fill(0x02);
    popc_pkh.fill(0x03);

    // Build block
    Block blk;
    blk.header.version = 1;
    blk.header.timestamp = 1773597600;
    blk.header.bits_q = GENESIS_BITSQ;
    blk.header.height = 0;

    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0,
                                        miner_pkh, gold_pkh, popc_pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));
    EXPECT(blk.VerifyMerkleRoot(&err));

    // Connect to UTXO set
    UtxoSet utxo;
    BlockUndo undo;
    EXPECT(utxo.ConnectBlock(blk.txs, 0, undo, &err));
    EXPECT(utxo.Size() == 3);  // 3 coinbase outputs

    // Block hash is computable
    Hash256 hash = blk.header.ComputeBlockHash();
    EXPECT(hash != Hash256{});

    // Disconnect
    EXPECT(utxo.DisconnectBlock(blk.txs, undo, &err));
    EXPECT(utxo.Size() == 0);

    return true;
}

// I02: Two-block chain with UTXO tracking
static bool I02_two_block_chain() {
    PubKeyHash miner_pkh, gold_pkh, popc_pkh;
    miner_pkh.fill(0x01);
    gold_pkh.fill(0x02);
    popc_pkh.fill(0x03);

    // Block 0
    Block blk0;
    blk0.header.version = 1;
    blk0.header.prev_block_hash = Hash256{};
    blk0.header.timestamp = 1773597600;
    blk0.header.bits_q = GENESIS_BITSQ;
    blk0.header.height = 0;
    blk0.txs.push_back(MakeTestCoinbase(0, 785100863, 0,
                                         miner_pkh, gold_pkh, popc_pkh));
    std::string err;
    EXPECT(blk0.ComputeAndSetMerkleRoot(&err));

    UtxoSet utxo;
    BlockUndo undo0;
    EXPECT(utxo.ConnectBlock(blk0.txs, 0, undo0, &err));

    Hash256 hash0 = blk0.header.ComputeBlockHash();

    // Block 1
    Block blk1;
    blk1.header.version = 1;
    blk1.header.prev_block_hash = hash0;
    blk1.header.timestamp = 1772237400;
    blk1.header.bits_q = GENESIS_BITSQ;
    blk1.header.height = 1;
    blk1.txs.push_back(MakeTestCoinbase(1, 785100863, 0,
                                         miner_pkh, gold_pkh, popc_pkh));
    EXPECT(blk1.ComputeAndSetMerkleRoot(&err));

    BlockUndo undo1;
    EXPECT(utxo.ConnectBlock(blk1.txs, 1, undo1, &err));
    EXPECT(utxo.Size() == 6);  // 3 + 3

    // Chain integrity
    EXPECT(blk1.header.prev_block_hash == hash0);
    Hash256 hash1 = blk1.header.ComputeBlockHash();
    EXPECT(hash1 != hash0);

    return true;
}

// I03: Block serialization → deserialize → verify merkle → match
static bool I03_serialize_deserialize_verify() {
    PubKeyHash pkh;
    pkh.fill(0xAA);

    Block blk;
    blk.header.version = 1;
    blk.header.timestamp = 1773597600;
    blk.header.bits_q = GENESIS_BITSQ;
    blk.header.nonce = 12345;
    blk.header.height = 42;
    blk.txs.push_back(MakeTestCoinbase(42, 785100863, 500, pkh, pkh, pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));

    // Serialize
    std::vector<Byte> wire;
    EXPECT(blk.SerializeTo(wire, &err));

    // Deserialize
    Block blk2;
    size_t offset = 0;
    EXPECT(Block::DeserializeFrom(wire, offset, blk2, &err));

    // Verify merkle root still valid
    EXPECT(blk2.VerifyMerkleRoot(&err));

    // Headers match
    EXPECT(blk2.header == blk.header);

    // Block hash matches
    EXPECT(blk2.header.ComputeBlockHash() == blk.header.ComputeBlockHash());
    return true;
}

// I04: Merkle root changes when tx is modified
static bool I04_merkle_commitment() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 0;
    blk.txs.push_back(MakeTestCoinbase(0, 785100863, 0, pkh, pkh, pkh));

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));
    Hash256 root1 = blk.header.merkle_root;

    // Modify tx (different height in coinbase sig)
    blk.txs[0].inputs[0].signature[0] = 0xFF;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));
    Hash256 root2 = blk.header.merkle_root;

    // Merkle root MUST change
    EXPECT(root1 != root2);

    // Block hash also changes
    BlockHeader hdr1 = blk.header;
    hdr1.merkle_root = root1;
    BlockHeader hdr2 = blk.header;
    hdr2.merkle_root = root2;
    EXPECT(hdr1.ComputeBlockHash() != hdr2.ComputeBlockHash());

    return true;
}

// I05: Block with 3 txids (odd count) — merkle tree handles duplication
static bool I05_odd_tx_count_block() {
    PubKeyHash pkh;
    pkh.fill(0x01);

    Block blk;
    blk.header.version = 1;
    blk.header.height = 5;

    // Coinbase + 2 standard txs = 3 total (odd)
    blk.txs.push_back(MakeTestCoinbase(5, 785100863, 2000, pkh, pkh, pkh));

    for (int i = 0; i < 2; ++i) {
        Transaction tx;
        tx.version = 1;
        tx.tx_type = TX_TYPE_STANDARD;

        TxInput in;
        in.prev_txid = MakeHash((uint8_t)(0xA0 + i));
        in.prev_index = 0;
        in.signature.fill((uint8_t)(0x10 + i));
        in.pubkey.fill(0x02);
        tx.inputs.push_back(in);

        TxOutput out;
        out.amount = 1000;
        out.type = OUT_TRANSFER;
        out.pubkey_hash = pkh;
        tx.outputs.push_back(out);

        blk.txs.push_back(tx);
    }

    std::string err;
    EXPECT(blk.ComputeAndSetMerkleRoot(&err));
    EXPECT(blk.VerifyMerkleRoot(&err));

    // Manual: 3 txids → [H(tx0,tx1), H(tx2,tx2)] → root
    Hash256 txid0{}, txid1{}, txid2{};
    EXPECT(blk.txs[0].ComputeTxId(txid0, &err));
    EXPECT(blk.txs[1].ComputeTxId(txid1, &err));
    EXPECT(blk.txs[2].ComputeTxId(txid2, &err));

    Hash256 left = MerkleHash(txid0, txid1);
    Hash256 right = MerkleHash(txid2, txid2);  // duplicated
    Hash256 expected_root = MerkleHash(left, right);

    EXPECT(blk.header.merkle_root == expected_root);
    return true;
}

// ============================================================================

int main() {
    printf("=== Phase 5: Merkle Tree + Block Header tests ===\n\n");

    // Merkle tree
    printf("--- Merkle Tree ---\n");
    RUN(M01_empty_merkle);
    RUN(M02_single_txid);
    RUN(M03_two_txids);
    RUN(M04_three_txids_odd);
    RUN(M05_four_txids_balanced);
    RUN(M06_five_txids);
    RUN(M07_deterministic);
    RUN(M08_manual_double_sha256);
    RUN(M09_layer_even);
    RUN(M10_layer_odd);
    RUN(M11_from_txs);
    RUN(M12_large_tree);

    // Block header
    printf("\n--- Block Header ---\n");
    RUN(B01_header_size);
    RUN(B02_header_roundtrip);
    RUN(B03_block_hash_deterministic);
    RUN(B04_hash_manual_verification);
    RUN(B05_deserialize_short);
    RUN(B06_genesis_header);
    RUN(B07_equality);
    RUN(B08_le_encoding);
    RUN(B09_hash_hex);
    RUN(B10_prev_hash_offset);
    RUN(B11_merkle_offset);

    // Block (full)
    printf("\n--- Block (full) ---\n");
    RUN(B12_block_roundtrip);
    RUN(B13_verify_merkle_correct);
    RUN(B14_verify_merkle_tampered);
    RUN(B15_block_multi_tx);
    RUN(B16_deserialize_zero_txs);
    RUN(B17_estimate_size);
    RUN(B18_hash_chain);

    // Integration
    printf("\n--- Integration ---\n");
    RUN(I01_full_block_lifecycle);
    RUN(I02_two_block_chain);
    RUN(I03_serialize_deserialize_verify);
    RUN(I04_merkle_commitment);
    RUN(I05_odd_tx_count_block);

    printf("\n=== Results: %d passed, %d failed out of %d ===\n",
           g_pass, g_fail, g_pass + g_fail);
    return g_fail ? 1 : 0;
}
