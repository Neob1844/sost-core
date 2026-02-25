// =============================================================================
// test_utxo_set.cpp — Phase 4 tests for SOST UTXO Set
// Tests: basic ops, connect/disconnect tx, block lifecycle, Phase 3 integration
// =============================================================================

#include "sost/utxo_set.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <string>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define TEST(name) \
    static void test_##name(); \
    struct reg_##name { reg_##name() { tests().push_back({#name, test_##name}); } } r_##name; \
    static void test_##name()

static std::vector<std::pair<std::string, void(*)()>>& tests() {
    static std::vector<std::pair<std::string, void(*)()>> t;
    return t;
}

#define EXPECT(cond, msg) do { \
    if (!(cond)) { \
        std::cerr << "  FAIL: " << msg << " [" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

// =============================================================================
// Helpers
// =============================================================================

static Hash256 FakeTxid(uint8_t fill) {
    Hash256 h{}; std::memset(h.data(), fill, 32); return h;
}

static PrivKey g_priv{};
static PubKey  g_pub{};
static PubKeyHash g_pkh{};
static Hash256 g_genesis{};

static PubKeyHash g_gold_pkh{};
static PubKeyHash g_popc_pkh{};

static void InitKeys() {
    std::string err;
    assert(GenerateKeyPair(g_priv, g_pub, &err));
    g_pkh = ComputePubKeyHash(g_pub);
    std::memset(g_genesis.data(), 0xAA, 32);
    std::memset(g_gold_pkh.data(), 0xBB, 20);
    std::memset(g_popc_pkh.data(), 0xCC, 20);
}

static UTXOEntry MakeEntry(int64_t amount, int64_t height = 0,
                            bool coinbase = false) {
    UTXOEntry e;
    e.amount = amount;
    e.type = OUT_TRANSFER;
    e.pubkey_hash = g_pkh;
    e.height = height;
    e.is_coinbase = coinbase;
    return e;
}

// Build a coinbase transaction at given height
static Transaction MakeCoinbase(int64_t height, int64_t subsidy) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    TxInput cbin;
    std::memset(cbin.prev_txid.data(), 0, 32);
    cbin.prev_index = 0xFFFFFFFF;
    std::memset(cbin.signature.data(), 0, 64);
    uint64_t h = (uint64_t)height;
    std::memcpy(cbin.signature.data(), &h, 8);
    std::memset(cbin.pubkey.data(), 0, 33);
    tx.inputs.push_back(cbin);

    int64_t q = subsidy / 4;
    int64_t miner = subsidy - q - q;

    TxOutput o_miner;
    o_miner.amount = miner;
    o_miner.type = OUT_COINBASE_MINER;
    o_miner.pubkey_hash = g_pkh;
    tx.outputs.push_back(o_miner);

    TxOutput o_gold;
    o_gold.amount = q;
    o_gold.type = OUT_COINBASE_GOLD;
    o_gold.pubkey_hash = g_gold_pkh;
    tx.outputs.push_back(o_gold);

    TxOutput o_popc;
    o_popc.amount = q;
    o_popc.type = OUT_COINBASE_POPC;
    o_popc.pubkey_hash = g_popc_pkh;
    tx.outputs.push_back(o_popc);

    return tx;
}

// Build a signed standard tx spending a specific UTXO
static Transaction MakeStdTx(const Hash256& prev_txid, uint32_t prev_index,
                              int64_t input_amount, int64_t output_amount) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = prev_index;
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount = output_amount;
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    tx.outputs.push_back(out);

    // Sign
    SpentOutput spent{input_amount, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err);

    return tx;
}

// =============================================================================
// U01: Basic add and get
// =============================================================================

TEST(U01_add_get) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x11), 0};
    auto entry = MakeEntry(1000000);

    std::string err;
    EXPECT(utxos.AddUTXO(op, entry, &err), "add should succeed");
    EXPECT(utxos.Size() == 1, "size should be 1");

    auto got = utxos.GetUTXO(op);
    EXPECT(got.has_value(), "should find UTXO");
    EXPECT(got->amount == 1000000, "amount match");
    EXPECT(got->pubkey_hash == g_pkh, "pkh match");
    g_pass++;
}

// =============================================================================
// U02: Duplicate add rejected
// =============================================================================

TEST(U02_duplicate_add) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x22), 0};
    auto entry = MakeEntry(500000);

    EXPECT(utxos.AddUTXO(op, entry), "first add ok");
    EXPECT(!utxos.AddUTXO(op, entry), "duplicate should fail");
    EXPECT(utxos.Size() == 1, "still size 1");
    g_pass++;
}

// =============================================================================
// U03: Spend removes UTXO
// =============================================================================

TEST(U03_spend) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x33), 0};
    utxos.AddUTXO(op, MakeEntry(1000000));

    UTXOEntry spent_entry;
    EXPECT(utxos.SpendUTXO(op, &spent_entry), "spend should succeed");
    EXPECT(spent_entry.amount == 1000000, "spent entry amount");
    EXPECT(utxos.Size() == 0, "empty after spend");
    EXPECT(!utxos.HasUTXO(op), "should not exist after spend");
    g_pass++;
}

// =============================================================================
// U04: Spend non-existent fails
// =============================================================================

TEST(U04_spend_missing) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x44), 0};
    EXPECT(!utxos.SpendUTXO(op), "should fail on missing");
    g_pass++;
}

// =============================================================================
// U05: HasUTXO
// =============================================================================

TEST(U05_has_utxo) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x55), 0};
    EXPECT(!utxos.HasUTXO(op), "not found before add");
    utxos.AddUTXO(op, MakeEntry(100));
    EXPECT(utxos.HasUTXO(op), "found after add");
    g_pass++;
}

// =============================================================================
// U06: GetTotalValue
// =============================================================================

TEST(U06_total_value) {
    UtxoSet utxos;
    utxos.AddUTXO({FakeTxid(0x01), 0}, MakeEntry(1000));
    utxos.AddUTXO({FakeTxid(0x02), 0}, MakeEntry(2000));
    utxos.AddUTXO({FakeTxid(0x03), 0}, MakeEntry(3000));

    EXPECT(utxos.GetTotalValue() == 6000, "total should be 6000");
    EXPECT(utxos.Size() == 3, "size should be 3");
    g_pass++;
}

// =============================================================================
// U07: ConnectCoinbase adds 3 outputs
// =============================================================================

TEST(U07_connect_coinbase) {
    UtxoSet utxos;
    int64_t subsidy = 785100863;
    auto cb = MakeCoinbase(0, subsidy);

    Hash256 txid;
    EXPECT(cb.ComputeTxId(txid), "compute txid");

    std::string err;
    EXPECT(utxos.ConnectCoinbase(cb, txid, 0, &err), "connect coinbase: " + err);
    EXPECT(utxos.Size() == 3, "3 coinbase outputs");

    // Check all marked as coinbase
    for (uint32_t i = 0; i < 3; ++i) {
        auto got = utxos.GetUTXO({txid, i});
        EXPECT(got.has_value(), "output " + std::to_string(i));
        EXPECT(got->is_coinbase, "should be marked coinbase");
        EXPECT(got->height == 0, "height = 0");
    }

    // Verify split: miner gets remainder
    int64_t q = subsidy / 4;
    auto miner = utxos.GetUTXO({txid, 0});
    EXPECT(miner->amount == subsidy - q - q, "miner amount");
    EXPECT(miner->type == OUT_COINBASE_MINER, "miner type");

    EXPECT(utxos.GetTotalValue() == subsidy, "total = subsidy");
    g_pass++;
}

// =============================================================================
// U08: ConnectTransaction spends inputs and adds outputs
// =============================================================================

TEST(U08_connect_standard_tx) {
    UtxoSet utxos;

    // Seed a UTXO to spend
    Hash256 prev_txid = FakeTxid(0xAA);
    utxos.AddUTXO({prev_txid, 0}, MakeEntry(1000000, 0));

    // Build tx spending it
    auto tx = MakeStdTx(prev_txid, 0, 1000000, 999500);

    Hash256 txid;
    EXPECT(tx.ComputeTxId(txid), "compute txid");

    std::vector<UndoEntry> undo;
    std::string err;
    EXPECT(utxos.ConnectTransaction(tx, txid, 10, undo, &err),
           "connect tx: " + err);

    // Old UTXO gone, new one exists
    EXPECT(!utxos.HasUTXO({prev_txid, 0}), "input spent");
    EXPECT(utxos.HasUTXO({txid, 0}), "output added");
    EXPECT(utxos.Size() == 1, "one UTXO");

    auto got = utxos.GetUTXO({txid, 0});
    EXPECT(got->amount == 999500, "output amount");
    EXPECT(got->height == 10, "height = 10");
    EXPECT(!got->is_coinbase, "not coinbase");

    // Undo data captured
    EXPECT(undo.size() == 1, "1 undo entry");
    EXPECT(undo[0].entry.amount == 1000000, "undo amount");
    g_pass++;
}

// =============================================================================
// U09: ConnectTransaction fails on missing input
// =============================================================================

TEST(U09_connect_missing_input) {
    UtxoSet utxos;
    auto tx = MakeStdTx(FakeTxid(0xBB), 0, 1000000, 999000);
    Hash256 txid;
    tx.ComputeTxId(txid);

    std::vector<UndoEntry> undo;
    std::string err;
    EXPECT(!utxos.ConnectTransaction(tx, txid, 1, undo, &err),
           "should fail on missing input");
    g_pass++;
}

// =============================================================================
// U10: DisconnectTransaction restores state
// =============================================================================

TEST(U10_disconnect_tx) {
    UtxoSet utxos;

    Hash256 prev_txid = FakeTxid(0xCC);
    auto orig_entry = MakeEntry(2000000, 5);
    utxos.AddUTXO({prev_txid, 0}, orig_entry);

    auto tx = MakeStdTx(prev_txid, 0, 2000000, 1999500);
    Hash256 txid;
    tx.ComputeTxId(txid);

    // Connect
    std::vector<UndoEntry> undo;
    EXPECT(utxos.ConnectTransaction(tx, txid, 10, undo), "connect");

    // Verify connected state
    EXPECT(!utxos.HasUTXO({prev_txid, 0}), "input gone");
    EXPECT(utxos.HasUTXO({txid, 0}), "output present");

    // Disconnect
    std::string err;
    EXPECT(utxos.DisconnectTransaction(tx, txid, undo, &err),
           "disconnect: " + err);

    // State restored exactly
    EXPECT(utxos.HasUTXO({prev_txid, 0}), "input restored");
    EXPECT(!utxos.HasUTXO({txid, 0}), "output removed");
    EXPECT(utxos.Size() == 1, "back to 1");

    auto restored = utxos.GetUTXO({prev_txid, 0});
    EXPECT(restored->amount == 2000000, "amount restored");
    EXPECT(restored->height == 5, "height restored");
    g_pass++;
}

// =============================================================================
// U11: DisconnectCoinbase removes outputs
// =============================================================================

TEST(U11_disconnect_coinbase) {
    UtxoSet utxos;
    auto cb = MakeCoinbase(100, 785100863);
    Hash256 txid;
    cb.ComputeTxId(txid);

    utxos.ConnectCoinbase(cb, txid, 100);
    EXPECT(utxos.Size() == 3, "3 after connect");

    std::string err;
    EXPECT(utxos.DisconnectCoinbase(cb, txid, &err), "disconnect: " + err);
    EXPECT(utxos.Size() == 0, "0 after disconnect");
    g_pass++;
}

// =============================================================================
// U12: ConnectBlock (coinbase + standard txs)
// =============================================================================

TEST(U12_connect_block) {
    UtxoSet utxos;

    // Seed UTXOs for standard txs in the block
    Hash256 prev1 = FakeTxid(0xD1);
    Hash256 prev2 = FakeTxid(0xD2);
    utxos.AddUTXO({prev1, 0}, MakeEntry(500000, 0));
    utxos.AddUTXO({prev2, 0}, MakeEntry(300000, 0));

    // Build block: coinbase + 2 standard txs
    int64_t subsidy = 785100863;
    auto cb = MakeCoinbase(10, subsidy);
    auto tx1 = MakeStdTx(prev1, 0, 500000, 499500);
    auto tx2 = MakeStdTx(prev2, 0, 300000, 299500);

    std::vector<Transaction> block = {cb, tx1, tx2};
    BlockUndo undo;
    std::string err;
    EXPECT(utxos.ConnectBlock(block, 10, undo, &err), "connect block: " + err);

    // Original UTXOs spent
    EXPECT(!utxos.HasUTXO({prev1, 0}), "prev1 spent");
    EXPECT(!utxos.HasUTXO({prev2, 0}), "prev2 spent");

    // Coinbase outputs (3) + tx1 output (1) + tx2 output (1) = 5
    EXPECT(utxos.Size() == 5, "5 UTXOs after block");

    // Undo data: 2 entries (one per standard tx input)
    EXPECT(undo.spent_utxos.size() == 2, "2 undo entries");
    EXPECT(undo.height == 10, "undo height");
    g_pass++;
}

// =============================================================================
// U13: DisconnectBlock restores pre-block state
// =============================================================================

TEST(U13_disconnect_block) {
    UtxoSet utxos;

    Hash256 prev1 = FakeTxid(0xE1);
    Hash256 prev2 = FakeTxid(0xE2);
    utxos.AddUTXO({prev1, 0}, MakeEntry(500000, 0));
    utxos.AddUTXO({prev2, 0}, MakeEntry(300000, 0));
    size_t pre_size = utxos.Size();
    int64_t pre_value = utxos.GetTotalValue();

    // Connect block
    int64_t subsidy = 785100863;
    auto cb = MakeCoinbase(10, subsidy);
    auto tx1 = MakeStdTx(prev1, 0, 500000, 499500);
    auto tx2 = MakeStdTx(prev2, 0, 300000, 299500);

    std::vector<Transaction> block = {cb, tx1, tx2};
    BlockUndo undo;
    utxos.ConnectBlock(block, 10, undo);

    // Disconnect
    std::string err;
    EXPECT(utxos.DisconnectBlock(block, undo, &err), "disconnect: " + err);

    // Exact pre-state restored
    EXPECT(utxos.Size() == pre_size, "size restored");
    EXPECT(utxos.GetTotalValue() == pre_value, "value restored");
    EXPECT(utxos.HasUTXO({prev1, 0}), "prev1 restored");
    EXPECT(utxos.HasUTXO({prev2, 0}), "prev2 restored");
    g_pass++;
}

// =============================================================================
// U14: Multi-block connect/disconnect cycle
// =============================================================================

TEST(U14_multi_block_cycle) {
    UtxoSet utxos;
    int64_t subsidy = 785100863;

    // Block 0: only coinbase
    auto cb0 = MakeCoinbase(0, subsidy);
    std::vector<Transaction> block0 = {cb0};
    BlockUndo undo0;
    EXPECT(utxos.ConnectBlock(block0, 0, undo0), "connect block 0");
    EXPECT(utxos.Size() == 3, "3 after block 0");

    Hash256 cb0_txid;
    cb0.ComputeTxId(cb0_txid);

    // Block 1: coinbase + tx spending miner output from block 0
    auto cb1 = MakeCoinbase(1, subsidy);
    // Miner output is index 0, type OUT_COINBASE_MINER
    int64_t miner_amount = utxos.GetUTXO({cb0_txid, 0})->amount;
    auto tx1 = MakeStdTx(cb0_txid, 0, miner_amount, miner_amount - 500);

    std::vector<Transaction> block1 = {cb1, tx1};
    BlockUndo undo1;
    std::string err;
    EXPECT(utxos.ConnectBlock(block1, 1, undo1, &err), "connect block 1: " + err);

    // block0: gold(1) + popc(1) still there + block1: cb(3) + tx1 output(1) = 6
    EXPECT(utxos.Size() == 6, "6 after block 1, got " + std::to_string(utxos.Size()));

    // Disconnect block 1
    EXPECT(utxos.DisconnectBlock(block1, undo1), "disconnect block 1");
    EXPECT(utxos.Size() == 3, "back to 3 after undo block 1");
    EXPECT(utxos.HasUTXO({cb0_txid, 0}), "miner output restored");

    // Disconnect block 0
    EXPECT(utxos.DisconnectBlock(block0, undo0), "disconnect block 0");
    EXPECT(utxos.Size() == 0, "empty after full undo");
    g_pass++;
}

// =============================================================================
// U15: Double-spend detection (same output spent twice)
// =============================================================================

TEST(U15_double_spend) {
    UtxoSet utxos;
    Hash256 prev = FakeTxid(0xF1);
    utxos.AddUTXO({prev, 0}, MakeEntry(1000000));

    // First spend succeeds
    auto tx1 = MakeStdTx(prev, 0, 1000000, 999500);
    Hash256 txid1;
    tx1.ComputeTxId(txid1);
    std::vector<UndoEntry> undo1;
    EXPECT(utxos.ConnectTransaction(tx1, txid1, 1, undo1), "first spend ok");

    // Second spend of same input fails (UTXO already removed)
    auto tx2 = MakeStdTx(prev, 0, 1000000, 999500);
    Hash256 txid2;
    tx2.ComputeTxId(txid2);
    std::vector<UndoEntry> undo2;
    EXPECT(!utxos.ConnectTransaction(tx2, txid2, 1, undo2), "double spend fails");
    g_pass++;
}

// =============================================================================
// U16: Coinbase outputs marked correctly (is_coinbase, type, height)
// =============================================================================

TEST(U16_coinbase_metadata) {
    UtxoSet utxos;
    auto cb = MakeCoinbase(42, 785100863);
    Hash256 txid;
    cb.ComputeTxId(txid);
    utxos.ConnectCoinbase(cb, txid, 42);

    auto miner = utxos.GetUTXO({txid, 0});
    EXPECT(miner->is_coinbase == true, "is_coinbase");
    EXPECT(miner->type == OUT_COINBASE_MINER, "type miner");
    EXPECT(miner->height == 42, "height 42");

    auto gold = utxos.GetUTXO({txid, 1});
    EXPECT(gold->type == OUT_COINBASE_GOLD, "type gold");
    EXPECT(gold->pubkey_hash == g_gold_pkh, "gold pkh");
    g_pass++;
}

// =============================================================================
// U17: Phase 3 integration — validate tx against UTXO set
// =============================================================================

TEST(U17_phase3_validation_integration) {
    UtxoSet utxos;

    // Seed a UTXO
    Hash256 prev = FakeTxid(0x77);
    utxos.AddUTXO({prev, 0}, MakeEntry(5000000, 0));

    // Build and sign a valid tx
    auto tx = MakeStdTx(prev, 0, 5000000, 4999500);

    // Validate with Phase 3 using UtxoSet as IUtxoView
    TxValidationContext ctx;
    ctx.genesis_hash = g_genesis;
    ctx.spend_height = 200;
    ctx.capsule_activation_height = 5000;

    auto result = ValidateTransactionConsensus(tx, utxos, ctx);
    EXPECT(result.ok, "Phase 3 validation via UtxoSet: " + result.message);
    g_pass++;
}

// =============================================================================
// U18: Phase 3 integration — coinbase maturity via UTXO set
// =============================================================================

TEST(U18_coinbase_maturity_integration) {
    UtxoSet utxos;

    // Create coinbase at height 50
    auto cb = MakeCoinbase(50, 785100863);
    Hash256 cb_txid;
    cb.ComputeTxId(cb_txid);
    utxos.ConnectCoinbase(cb, cb_txid, 50);

    int64_t miner_amount = utxos.GetUTXO({cb_txid, 0})->amount;

    // Try to spend miner output at height 100 (only 50 confirmations < 100)
    // Must sign with correct spent type (OUT_COINBASE_MINER, not OUT_TRANSFER)
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;
    TxInput in;
    in.prev_txid = cb_txid;
    in.prev_index = 0;
    tx.inputs.push_back(in);
    TxOutput out;
    out.amount = miner_amount - 500;
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    tx.outputs.push_back(out);
    // Sign with correct spent type
    SpentOutput spent{miner_amount, OUT_COINBASE_MINER};
    std::string err;
    SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err);

    TxValidationContext ctx;
    ctx.genesis_hash = g_genesis;
    ctx.spend_height = 100;  // 100 - 50 = 50 < COINBASE_MATURITY(100)
    ctx.capsule_activation_height = 5000;

    auto r1 = ValidateTransactionConsensus(tx, utxos, ctx);
    EXPECT(!r1.ok, "should fail: immature coinbase");
    EXPECT(r1.code == TxValCode::S10_COINBASE_IMMATURE, "S10 code");

    // Now try at height 151 (151 - 50 = 101 >= 100)
    ctx.spend_height = 151;
    auto r2 = ValidateTransactionConsensus(tx, utxos, ctx);
    EXPECT(r2.ok, "should pass: mature coinbase: " + r2.message);
    g_pass++;
}

// =============================================================================
// U19: Multiple outputs per tx
// =============================================================================

TEST(U19_multi_output_tx) {
    UtxoSet utxos;
    Hash256 prev = FakeTxid(0x88);
    utxos.AddUTXO({prev, 0}, MakeEntry(10000000, 0));

    // Build tx with 3 outputs
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev;
    in.prev_index = 0;
    tx.inputs.push_back(in);

    for (int i = 0; i < 3; ++i) {
        TxOutput out;
        out.amount = 3000000;
        out.type = OUT_TRANSFER;
        out.pubkey_hash = g_pkh;
        tx.outputs.push_back(out);
    }

    SpentOutput spent{10000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err);

    Hash256 txid;
    tx.ComputeTxId(txid);

    std::vector<UndoEntry> undo;
    EXPECT(utxos.ConnectTransaction(tx, txid, 5, undo, &err), "connect: " + err);
    EXPECT(utxos.Size() == 3, "3 outputs");

    for (uint32_t i = 0; i < 3; ++i) {
        auto got = utxos.GetUTXO({txid, i});
        EXPECT(got.has_value(), "output " + std::to_string(i));
        EXPECT(got->amount == 3000000, "amount");
    }
    g_pass++;
}

// =============================================================================
// U20: Clear resets everything
// =============================================================================

TEST(U20_clear) {
    UtxoSet utxos;
    utxos.AddUTXO({FakeTxid(0x01), 0}, MakeEntry(100));
    utxos.AddUTXO({FakeTxid(0x02), 0}, MakeEntry(200));
    EXPECT(utxos.Size() == 2, "2 before clear");

    utxos.Clear();
    EXPECT(utxos.Size() == 0, "0 after clear");
    EXPECT(utxos.GetTotalValue() == 0, "value 0");
    g_pass++;
}

// =============================================================================
// U21: Payload preserved in UTXO entry
// =============================================================================

TEST(U21_payload_preserved) {
    UtxoSet utxos;
    OutPoint op{FakeTxid(0x99), 0};

    UTXOEntry entry = MakeEntry(1000);
    entry.payload = {0x53, 0x43, 0x01, 0x01, 0x00};
    entry.payload_len = 5;

    utxos.AddUTXO(op, entry);
    auto got = utxos.GetUTXO(op);
    EXPECT(got.has_value(), "found");
    EXPECT(got->payload.size() == 5, "payload size");
    EXPECT(got->payload[0] == 0x53, "payload byte 0");
    EXPECT(got->payload_len == 5, "payload_len");
    g_pass++;
}

// =============================================================================
// U22: ConnectBlock empty rejected
// =============================================================================

TEST(U22_empty_block_rejected) {
    UtxoSet utxos;
    std::vector<Transaction> empty;
    BlockUndo undo;
    EXPECT(!utxos.ConnectBlock(empty, 0, undo), "empty block fails");
    g_pass++;
}

// =============================================================================
// main
// =============================================================================

int main() {
    InitKeys();

    std::cout << "=== Phase 4: utxo_set tests ===\n\n";

    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev = g_pass, prev_f = g_fail;
        fn();
        if (g_pass > prev) std::cout << "PASS\n";
        else if (g_fail == prev_f) std::cout << "SKIP\n";
    }

    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail << " failed"
              << " out of " << (g_pass + g_fail) << " ===\n";
    return g_fail > 0 ? 1 : 0;
}
