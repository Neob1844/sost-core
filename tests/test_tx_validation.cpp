// =============================================================================
// test_tx_validation.cpp — Phase 3 tests for SOST Transaction Validation
// Tests: R1-R14, S1-S12, CB1-CB10, Policy checks
// =============================================================================

#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>

using namespace sost;

// =============================================================================
// Test infrastructure
// =============================================================================

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
        std::cerr << "  FAIL: " << msg << " [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

#define EXPECT_OK(result) do { \
    auto _r = (result); \
    if (!_r.ok) { \
        std::cerr << "  FAIL: expected OK, got " << (int)_r.code << ": " << _r.message \
                  << " [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

#define EXPECT_FAIL(result, expected_code) do { \
    auto _r = (result); \
    if (_r.ok) { \
        std::cerr << "  FAIL: expected " << (int)expected_code << " but got OK" \
                  << " [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
    if (_r.code != expected_code) { \
        std::cerr << "  FAIL: expected code " << (int)expected_code << ", got " \
                  << (int)_r.code << ": " << _r.message \
                  << " [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

// =============================================================================
// Mock UTXO view
// =============================================================================

class MapUtxoView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> db;

    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = db.find(op);
        if (it == db.end()) return std::nullopt;
        return it->second;
    }

    void Add(const Hash256& txid, uint32_t index, const UTXOEntry& entry) {
        OutPoint op{txid, index};
        db[op] = entry;
    }
};

// =============================================================================
// Test helpers — build valid transactions for mutation testing
// =============================================================================

static Hash256 g_genesis_hash{};
static PrivKey g_privkey{};
static PubKey  g_pubkey{};
static PubKeyHash g_pkh{};

// Constitutional addresses for coinbase tests
static PubKeyHash g_gold_vault_pkh{};
static PubKeyHash g_popc_pool_pkh{};

static Hash256 MakeFakeTxid(uint8_t fill) {
    Hash256 h{};
    std::memset(h.data(), fill, 32);
    return h;
}

static void InitTestKeys() {
    // Generate a test keypair
    std::string err;
    bool ok = GenerateKeyPair(g_privkey, g_pubkey, &err);
    assert(ok && "GenerateKeyPair failed in test init");
    g_pkh = ComputePubKeyHash(g_pubkey);

    // Genesis hash: SHA256(SHA256("SOST_TEST_GENESIS"))
    std::memset(g_genesis_hash.data(), 0xAA, 32);

    // Constitutional addresses (arbitrary for tests)
    std::memset(g_gold_vault_pkh.data(), 0xBB, 20);
    std::memset(g_popc_pool_pkh.data(), 0xCC, 20);
}

// Build a valid 1-in-1-out standard transaction and matching UTXO
struct TestTxBundle {
    Transaction tx;
    MapUtxoView utxos;
    TxValidationContext ctx;
    int64_t utxo_amount;
};

static TestTxBundle MakeValidStdTx(int64_t utxo_amount = 1000000,
                                    int64_t output_amount = 0,
                                    int64_t utxo_height = 0) {
    TestTxBundle b;
    b.utxo_amount = utxo_amount;

    // Context
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = 200;  // well above maturity for non-coinbase

    // Create UTXO
    Hash256 prev_txid = MakeFakeTxid(0x11);
    UTXOEntry utxo;
    utxo.amount = utxo_amount;
    utxo.type = OUT_TRANSFER;
    utxo.pubkey_hash = g_pkh;
    utxo.height = utxo_height;
    utxo.is_coinbase = false;
    b.utxos.Add(prev_txid, 0, utxo);

    // Build tx
    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = 0;
    b.tx.inputs.push_back(in);

    // Output: leave room for fee (size * 1 stockshi/byte minimum)
    // Estimate: ~163 bytes for 1-in-1-out tx → fee ~163
    if (output_amount == 0) {
        output_amount = utxo_amount - 300;  // generous fee
    }
    TxOutput out;
    out.amount = output_amount;
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out);

    // Sign
    SpentOutput spent{utxo_amount, OUT_TRANSFER};
    std::string err;
    bool ok = SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    assert(ok && "SignTransactionInput failed in MakeValidStdTx");

    return b;
}

static Transaction MakeValidCoinbase(int64_t height, int64_t subsidy, int64_t fees) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    TxInput cbin;
    // prev_txid = 0x00*32, prev_index = 0xFFFFFFFF
    std::memset(cbin.prev_txid.data(), 0, 32);
    cbin.prev_index = 0xFFFFFFFF;
    // signature = height(8 LE) + zeros(56)
    std::memset(cbin.signature.data(), 0, 64);
    uint64_t h = (uint64_t)height;
    std::memcpy(cbin.signature.data(), &h, 8);
    // pubkey = 0x00*33
    std::memset(cbin.pubkey.data(), 0, 33);
    tx.inputs.push_back(cbin);

    // 50/25/25 split
    int64_t total = subsidy + fees;
    int64_t quarter = total / 4;
    int64_t gold = quarter;
    int64_t popc = quarter;
    int64_t miner = total - gold - popc;

    TxOutput o_miner;
    o_miner.amount = miner;
    o_miner.type = OUT_COINBASE_MINER;
    // miner pkh can be anything
    std::memset(o_miner.pubkey_hash.data(), 0xDD, 20);
    tx.outputs.push_back(o_miner);

    TxOutput o_gold;
    o_gold.amount = gold;
    o_gold.type = OUT_COINBASE_GOLD;
    o_gold.pubkey_hash = g_gold_vault_pkh;
    tx.outputs.push_back(o_gold);

    TxOutput o_popc;
    o_popc.amount = popc;
    o_popc.type = OUT_COINBASE_POPC;
    o_popc.pubkey_hash = g_popc_pool_pkh;
    tx.outputs.push_back(o_popc);

    return tx;
}

// =============================================================================
// T01: Valid standard transaction passes consensus
// =============================================================================

TEST(T01_valid_standard_tx) {
    auto b = MakeValidStdTx();
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
    g_pass++;
}

// =============================================================================
// T02: Valid standard transaction passes policy
// =============================================================================

TEST(T02_valid_policy) {
    auto b = MakeValidStdTx();
    EXPECT_OK(ValidateTransactionPolicy(b.tx, b.utxos, b.ctx));
    g_pass++;
}

// =============================================================================
// T03: R1 — bad version
// =============================================================================

TEST(T03_R1_bad_version) {
    auto b = MakeValidStdTx();
    b.tx.version = 2;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R1_BAD_VERSION);
    g_pass++;
}

// =============================================================================
// T04: R2 — coinbase rejected by standard validator
// =============================================================================

TEST(T04_R2_coinbase_in_std_validator) {
    auto b = MakeValidStdTx();
    b.tx.tx_type = TX_TYPE_COINBASE;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R2_BAD_TX_TYPE);
    g_pass++;
}

// =============================================================================
// T05: R3 — zero inputs
// =============================================================================

TEST(T05_R3_zero_inputs) {
    auto b = MakeValidStdTx();
    b.tx.inputs.clear();
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R3_INPUT_COUNT);
    g_pass++;
}

// =============================================================================
// T06: R4 — zero outputs
// =============================================================================

TEST(T06_R4_zero_outputs) {
    auto b = MakeValidStdTx();
    b.tx.outputs.clear();
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R4_OUTPUT_COUNT);
    g_pass++;
}

// =============================================================================
// T07: R5 — zero amount output
// =============================================================================

TEST(T07_R5_zero_amount) {
    auto b = MakeValidStdTx();
    b.tx.outputs[0].amount = 0;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R5_ZERO_AMOUNT);
    g_pass++;
}

// =============================================================================
// T08: R6 — amount exceeds supply max
// =============================================================================

TEST(T08_R6_amount_overflow) {
    auto b = MakeValidStdTx();
    b.tx.outputs[0].amount = SUPPLY_MAX_STOCKSHIS + 1;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R6_AMOUNT_OVERFLOW);
    g_pass++;
}

// =============================================================================
// T09: R7 — sum of outputs overflows
// =============================================================================

TEST(T09_R7_sum_overflow) {
    auto b = MakeValidStdTx(SUPPLY_MAX_STOCKSHIS, 1);
    // Add a second output that pushes sum over SUPPLY_MAX_STOCKSHIS
    TxOutput out2;
    out2.amount = SUPPLY_MAX_STOCKSHIS;
    out2.type = OUT_TRANSFER;
    out2.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out2);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R7_SUM_OVERFLOW);
    g_pass++;
}

// =============================================================================
// T10: R8 — duplicate input
// =============================================================================

TEST(T10_R8_duplicate_input) {
    auto b = MakeValidStdTx(2000000, 1999000);
    // Duplicate first input
    b.tx.inputs.push_back(b.tx.inputs[0]);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R8_DUPLICATE_INPUT);
    g_pass++;
}

// =============================================================================
// T11: R11 — inactive output type
// =============================================================================

TEST(T11_R11_inactive_type) {
    auto b = MakeValidStdTx();
    b.tx.outputs[0].type = OUT_BOND_LOCK;  // 0x10 — inactive in v1
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R11_INACTIVE_TYPE);
    g_pass++;
}

// =============================================================================
// T12: R14 — payload on active type
// =============================================================================

TEST(T12_R14_payload_forbidden) {
    auto b = MakeValidStdTx();
    b.tx.outputs[0].payload = {0x01, 0x02, 0x03};
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R14_PAYLOAD_FORBIDDEN);
    g_pass++;
}

// =============================================================================
// T13: S1 — UTXO not found
// =============================================================================

TEST(T13_S1_utxo_not_found) {
    auto b = MakeValidStdTx();
    b.utxos.db.clear();  // remove all UTXOs
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S1_UTXO_NOT_FOUND);
    g_pass++;
}

// =============================================================================
// T14: S2 — pubkey hash mismatch
// =============================================================================

TEST(T14_S2_pkh_mismatch) {
    auto b = MakeValidStdTx();
    // Corrupt the UTXO's pubkey_hash so it no longer matches
    auto it = b.utxos.db.begin();
    it->second.pubkey_hash[0] ^= 0xFF;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S2_PKH_MISMATCH);
    g_pass++;
}

// =============================================================================
// T15: S4 — zero signature
// =============================================================================

TEST(T15_S4_zero_signature) {
    auto b = MakeValidStdTx();
    std::memset(b.tx.inputs[0].signature.data(), 0, 64);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S4_ZERO_SIGNATURE);
    g_pass++;
}

// =============================================================================
// T16: S6 — invalid signature (corrupted)
// =============================================================================

TEST(T16_S6_verify_fail) {
    auto b = MakeValidStdTx();
    // Flip a bit in the signature
    b.tx.inputs[0].signature[10] ^= 0x01;
    // Could be S5 or S6 depending on which bit flipped — accept either
    auto r = ValidateTransactionConsensus(b.tx, b.utxos, b.ctx);
    EXPECT(!r.ok, "corrupted sig should fail");
    EXPECT(r.code == TxValCode::S5_HIGH_S || r.code == TxValCode::S6_VERIFY_FAIL,
           "expected S5 or S6 error code");
    g_pass++;
}

// =============================================================================
// T17: S7 — inputs < outputs
// =============================================================================

TEST(T17_S7_inputs_lt_outputs) {
    // Create with output larger than input — but we need signing to work
    // So create valid tx, then mutate output amount after signing
    auto b = MakeValidStdTx(1000000, 999700);
    // After signing, boost output beyond input
    b.tx.outputs[0].amount = 1000001;
    // Sig will be invalid too, but S7 is checked after S1-S6...
    // Actually S1-S6 runs first. We need to handle this differently.
    // Create an UTXO with small amount and large output in structure
    auto b2 = MakeValidStdTx(500, 100);  // 500 input, 100 output + fee ok
    // Now manually set output above input — structure passes but fee fails
    // Actually with 500 input and output > 500, sum check catches it
    // The trick: we need valid signatures, so we set up matching correctly
    // Let's use 2 outputs that sum > input
    auto b3 = MakeValidStdTx(1000000, 500000);
    TxOutput extra;
    extra.amount = 500001;
    extra.type = OUT_TRANSFER;
    extra.pubkey_hash = g_pkh;
    b3.tx.outputs.push_back(extra);
    // Sighash doesn't include individual output amounts for S7 to trigger
    // We need to re-sign because hashOutputs changed
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b3.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionConsensus(b3.tx, b3.utxos, b3.ctx), TxValCode::S7_INPUTS_LT_OUTPUTS);
    g_pass++;
}

// =============================================================================
// T18: S8 — fee too low
// =============================================================================

TEST(T18_S8_fee_too_low) {
    // Create tx where fee is exactly 0 (output = input)
    // But we can't set output == input due to S7 requiring fee >= size*1
    // So set output = input - 1 (fee=1, but size>1)
    auto b = MakeValidStdTx(1000000, 999999);
    // Re-sign with correct hashOutputs
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S8_FEE_TOO_LOW);
    g_pass++;
}

// =============================================================================
// T19: S9 — standard tx with non-TRANSFER output
// =============================================================================

TEST(T19_S9_bad_std_output_type) {
    auto b = MakeValidStdTx();
    // Change output type to coinbase miner — invalid in standard tx
    b.tx.outputs[0].type = OUT_COINBASE_MINER;
    // Re-sign (hashOutputs changes)
    SpentOutput spent{b.utxo_amount, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S9_BAD_STD_OUTPUT_TYPE);
    g_pass++;
}

// =============================================================================
// T20: S10 — coinbase maturity
// =============================================================================

TEST(T20_S10_coinbase_immature) {
    auto b = MakeValidStdTx();
    // Make the UTXO a coinbase output from height 150
    auto it = b.utxos.db.begin();
    it->second.is_coinbase = true;
    it->second.height = 150;
    // spend_height = 200, so confirmations = 200-150 = 50 < 100
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::S10_COINBASE_IMMATURE);
    g_pass++;
}

// =============================================================================
// T21: S10 — coinbase MATURE (should pass)
// =============================================================================

TEST(T21_S10_coinbase_mature) {
    auto b = MakeValidStdTx();
    auto it = b.utxos.db.begin();
    it->second.is_coinbase = true;
    it->second.height = 50;
    // spend_height = 200, confirmations = 150 >= 100 → ok
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
    g_pass++;
}

// =============================================================================
// T22: Valid coinbase passes
// =============================================================================

TEST(T22_valid_coinbase) {
    int64_t subsidy = 785100863;
    int64_t fees = 50000;
    auto tx = MakeValidCoinbase(100, subsidy, fees);
    EXPECT_OK(ValidateCoinbaseConsensus(tx, 100, subsidy, fees,
              g_gold_vault_pkh, g_popc_pool_pkh));
    g_pass++;
}

// =============================================================================
// T23: CB1 — not coinbase type
// =============================================================================

TEST(T23_CB1_not_coinbase) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.tx_type = TX_TYPE_STANDARD;
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB1_MISSING_COINBASE);
    g_pass++;
}

// =============================================================================
// T24: CB2 — bad coinbase prev_txid
// =============================================================================

TEST(T24_CB2_bad_prev_txid) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.inputs[0].prev_txid[0] = 0x01;  // not all zeros
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB2_BAD_CB_INPUT);
    g_pass++;
}

// =============================================================================
// T25: CB2 — bad prev_index
// =============================================================================

TEST(T25_CB2_bad_prev_index) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.inputs[0].prev_index = 0;
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB2_BAD_CB_INPUT);
    g_pass++;
}

// =============================================================================
// T26: CB3 — height mismatch in sig field
// =============================================================================

TEST(T26_CB3_height_mismatch) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    // Encode wrong height
    uint64_t wrong = 999;
    std::memcpy(tx.inputs[0].signature.data(), &wrong, 8);
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB3_BAD_CB_SIG_FIELD);
    g_pass++;
}

// =============================================================================
// T27: CB4 — wrong output order
// =============================================================================

TEST(T27_CB4_wrong_output_order) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    // Swap gold and popc
    std::swap(tx.outputs[1], tx.outputs[2]);
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB4_CB_OUTPUT_ORDER);
    g_pass++;
}

// =============================================================================
// T28: CB5 — amount mismatch (miner gets too much)
// =============================================================================

TEST(T28_CB5_amount_mismatch) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.outputs[0].amount += 1;  // miner takes extra
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB5_CB_AMOUNT_MISMATCH);
    g_pass++;
}

// =============================================================================
// T29: CB6 — gold vault address mismatch
// =============================================================================

TEST(T29_CB6_vault_mismatch) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.outputs[1].pubkey_hash[0] ^= 0xFF;
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB6_CB_VAULT_MISMATCH);
    g_pass++;
}

// =============================================================================
// T30: CB7 — wrong output count (4 outputs)
// =============================================================================

TEST(T30_CB7_wrong_output_count) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    TxOutput extra;
    extra.amount = 1;
    extra.type = OUT_TRANSFER;
    tx.outputs.push_back(extra);
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB7_CB_OUTPUT_COUNT);
    g_pass++;
}

// =============================================================================
// T31: CB9 — non-zero coinbase pubkey
// =============================================================================

TEST(T31_CB9_nonzero_pubkey) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.inputs[0].pubkey[0] = 0x02;
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB9_CB_PUBKEY_NONZERO);
    g_pass++;
}

// =============================================================================
// T32: CB10 — coinbase output with payload
// =============================================================================

TEST(T32_CB10_payload) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.outputs[0].payload = {0x01};
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB10_CB_PAYLOAD);
    g_pass++;
}

// =============================================================================
// T33: CB5 — coinbase split with fees (verify 50/25/25 remainder)
// =============================================================================

TEST(T33_CB5_split_with_fees) {
    int64_t subsidy = 785100863;
    int64_t fees = 3;  // total = 785100866, quarter = 196275216
    // miner = 785100866 - 196275216 - 196275216 = 392550434
    auto tx = MakeValidCoinbase(100, subsidy, fees);
    EXPECT_OK(ValidateCoinbaseConsensus(tx, 100, subsidy, fees,
              g_gold_vault_pkh, g_popc_pool_pkh));

    // Verify the actual amounts
    int64_t total = subsidy + fees;
    int64_t q = total / 4;
    EXPECT(tx.outputs[0].amount == total - q - q, "miner gets remainder");
    EXPECT(tx.outputs[1].amount == q, "gold gets quarter");
    EXPECT(tx.outputs[2].amount == q, "popc gets quarter");
    g_pass++;
}

// =============================================================================
// T34: Policy — tx too large
// =============================================================================

TEST(T34_P_tx_too_large) {
    auto b = MakeValidStdTx();
    // Add many outputs to push over 16KB standard limit
    // Each output ~30 bytes, need ~530 outputs for 16KB
    // But consensus max is 256, so this hits R4 first in consensus.
    // For policy test, we test at 129 inputs (> 128 standard)
    // Re-use the valid tx but pretend it's huge by checking policy independently
    // Simplest: add outputs up to 32 (standard max) and check beyond
    auto b2 = MakeValidStdTx(100000000, 1000000);
    for (int i = 0; i < 32; ++i) {
        TxOutput extra;
        extra.amount = 100000;
        extra.type = OUT_TRANSFER;
        extra.pubkey_hash = g_pkh;
        b2.tx.outputs.push_back(extra);
    }
    // 33 outputs > MAX_OUTPUTS_STANDARD=32
    EXPECT_FAIL(ValidateTransactionPolicy(b2.tx, b2.utxos, b2.ctx), TxValCode::P_TOO_MANY_OUTPUTS);
    g_pass++;
}

// =============================================================================
// T35: Policy — dust output
// =============================================================================

TEST(T35_P_dust_output) {
    auto b = MakeValidStdTx(1000000, 100);  // 100 stockshis < 10000 dust
    // Re-sign
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionPolicy(b.tx, b.utxos, b.ctx), TxValCode::P_DUST_OUTPUT);
    g_pass++;
}

// =============================================================================
// T36: Policy — valid standard tx passes policy
// =============================================================================

TEST(T36_P_valid_passes_policy) {
    auto b = MakeValidStdTx(1000000, 990000);
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_OK(ValidateTransactionPolicy(b.tx, b.utxos, b.ctx));
    g_pass++;
}

// =============================================================================
// T37: EstimateTxSerializedSize matches actual serialization
// =============================================================================

TEST(T37_size_estimate_matches) {
    auto b = MakeValidStdTx();
    size_t estimate = EstimateTxSerializedSize(b.tx);

    std::vector<Byte> raw;
    std::string err;
    bool ok = b.tx.Serialize(raw, &err);
    EXPECT(ok, "serialize should succeed");
    EXPECT(estimate == raw.size(),
           "estimate " + std::to_string(estimate) + " != actual " + std::to_string(raw.size()));
    g_pass++;
}

// =============================================================================
// T38: Multi-input, multi-output valid tx
// =============================================================================

TEST(T38_multi_input_output) {
    // 3 inputs, 2 outputs
    int64_t per_input = 1000000;
    Hash256 txid1 = MakeFakeTxid(0x21);
    Hash256 txid2 = MakeFakeTxid(0x22);
    Hash256 txid3 = MakeFakeTxid(0x23);

    MapUtxoView utxos;
    UTXOEntry entry;
    entry.amount = per_input;
    entry.type = OUT_TRANSFER;
    entry.pubkey_hash = g_pkh;
    entry.height = 0;
    entry.is_coinbase = false;

    utxos.Add(txid1, 0, entry);
    utxos.Add(txid2, 0, entry);
    utxos.Add(txid3, 0, entry);

    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    for (auto* tid : {&txid1, &txid2, &txid3}) {
        TxInput in;
        in.prev_txid = *tid;
        in.prev_index = 0;
        tx.inputs.push_back(in);
    }

    // 2 outputs: 1.5M + 1M = 2.5M, fee = 0.5M (generous)
    TxOutput o1;
    o1.amount = 1500000;
    o1.type = OUT_TRANSFER;
    o1.pubkey_hash = g_pkh;
    tx.outputs.push_back(o1);

    TxOutput o2;
    o2.amount = 1000000;
    o2.type = OUT_TRANSFER;
    o2.pubkey_hash = g_pkh;
    tx.outputs.push_back(o2);

    // Sign all inputs
    SpentOutput spent{per_input, OUT_TRANSFER};
    std::string err;
    for (size_t i = 0; i < 3; ++i) {
        bool ok = SignTransactionInput(tx, i, spent, g_genesis_hash, g_privkey, &err);
        EXPECT(ok, "sign input " + std::to_string(i) + " failed: " + err);
    }

    TxValidationContext ctx;
    ctx.genesis_hash = g_genesis_hash;
    ctx.spend_height = 200;

    EXPECT_OK(ValidateTransactionConsensus(tx, utxos, ctx));
    EXPECT_OK(ValidateTransactionPolicy(tx, utxos, ctx));
    g_pass++;
}

// =============================================================================
// T39: R2 — invalid tx_type value
// =============================================================================

TEST(T39_R2_invalid_tx_type) {
    auto b = MakeValidStdTx();
    b.tx.tx_type = 0x05;  // completely invalid
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R2_BAD_TX_TYPE);
    g_pass++;
}

// =============================================================================
// T40: CB6 — popc pool address mismatch
// =============================================================================

TEST(T40_CB6_popc_mismatch) {
    auto tx = MakeValidCoinbase(100, 785100863, 0);
    tx.outputs[2].pubkey_hash[0] ^= 0xFF;
    EXPECT_FAIL(ValidateCoinbaseConsensus(tx, 100, 785100863, 0,
                g_gold_vault_pkh, g_popc_pool_pkh), TxValCode::CB6_CB_VAULT_MISMATCH);
    g_pass++;
}

// =============================================================================
// T41: Coinbase at height 0 (genesis)
// =============================================================================

TEST(T41_coinbase_genesis_height) {
    int64_t subsidy = 785100863;
    auto tx = MakeValidCoinbase(0, subsidy, 0);
    EXPECT_OK(ValidateCoinbaseConsensus(tx, 0, subsidy, 0,
              g_gold_vault_pkh, g_popc_pool_pkh));
    g_pass++;
}

// =============================================================================
// T42: R5 — negative amount
// =============================================================================

TEST(T42_R5_negative_amount) {
    auto b = MakeValidStdTx();
    b.tx.outputs[0].amount = -1;
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx), TxValCode::R5_ZERO_AMOUNT);
    g_pass++;
}

// =============================================================================
// main
// =============================================================================

int main() {
    InitTestKeys();

    std::cout << "=== Phase 3: tx_validation tests ===\n\n";

    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev_pass = g_pass;
        int prev_fail = g_fail;
        fn();
        if (g_pass > prev_pass) {
            std::cout << "PASS\n";
        } else if (g_fail == prev_fail) {
            std::cout << "SKIP\n";
        }
        // FAIL is printed by EXPECT macros
    }

    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail << " failed"
              << " out of " << (g_pass + g_fail) << " ===\n";

    return g_fail > 0 ? 1 : 0;
}
