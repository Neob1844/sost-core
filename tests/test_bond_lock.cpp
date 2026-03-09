// =============================================================================
// test_bond_lock.cpp — Tests for BOND_LOCK (0x10) and ESCROW_LOCK (0x11)
// =============================================================================

#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"
#include "sost/utxo_set.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>

using namespace sost;

// =============================================================================
// Test infrastructure (same pattern as test_tx_validation.cpp)
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
        std::cerr << "  EXPECT failed: " << msg << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

#define EXPECT_OK(result) do { \
    auto _r = (result); \
    if (!_r.ok) { \
        std::cerr << "  EXPECT_OK failed: " << (int)_r.code << ": " << _r.message \
                  << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
} while(0)

#define EXPECT_FAIL(result, expected_code) do { \
    auto _r = (result); \
    if (_r.ok) { \
        std::cerr << "  EXPECT_FAIL: expected " << (int)expected_code << " but got OK" \
                  << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
        g_fail++; return; \
    } \
    if (_r.code != expected_code) { \
        std::cerr << "  EXPECT_FAIL: expected code " << (int)expected_code << ", got " \
                  << (int)_r.code << ": " << _r.message \
                  << "  [" << __FILE__ << ":" << __LINE__ << "]\n"; \
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
// Globals
// =============================================================================

static Hash256 g_genesis_hash{};
static PrivKey g_privkey{};
static PubKey  g_pubkey{};
static PubKeyHash g_pkh{};

static Hash256 MakeFakeTxid(uint8_t fill) {
    Hash256 h{};
    std::memset(h.data(), fill, 32);
    return h;
}

static void InitTestKeys() {
    std::string err;
    bool ok = GenerateKeyPair(g_privkey, g_pubkey, &err);
    assert(ok && "GenerateKeyPair failed");
    g_pkh = ComputePubKeyHash(g_pubkey);
    std::memset(g_genesis_hash.data(), 0xAA, 32);
}

// =============================================================================
// Helper: build a standard tx that creates a BOND_LOCK output
// =============================================================================

struct BondTxBundle {
    Transaction tx;
    MapUtxoView utxos;
    TxValidationContext ctx;
};

static BondTxBundle MakeBondCreateTx(
    uint64_t lock_until,
    int64_t bond_amount = 500000,
    int64_t utxo_amount = 1000000,
    int64_t spend_height = 6000,   // post-activation
    int64_t bond_activation = BOND_ACTIVATION_HEIGHT_MAINNET)
{
    BondTxBundle b;
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = spend_height;
    b.ctx.bond_activation_height = bond_activation;

    // Source UTXO (normal transfer)
    Hash256 prev_txid = MakeFakeTxid(0x22);
    UTXOEntry utxo;
    utxo.amount = utxo_amount;
    utxo.type = OUT_TRANSFER;
    utxo.pubkey_hash = g_pkh;
    utxo.height = 100;
    utxo.is_coinbase = false;
    b.utxos.Add(prev_txid, 0, utxo);

    // Build tx
    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = 0;
    b.tx.inputs.push_back(in);

    // Output 0: BOND_LOCK
    TxOutput bond_out;
    bond_out.amount = bond_amount;
    bond_out.type = OUT_BOND_LOCK;
    bond_out.pubkey_hash = g_pkh;
    WriteLockUntil(bond_out.payload, lock_until);
    b.tx.outputs.push_back(bond_out);

    // Output 1: change (OUT_TRANSFER)
    int64_t change = utxo_amount - bond_amount - 300;  // fee
    if (change > 0) {
        TxOutput change_out;
        change_out.amount = change;
        change_out.type = OUT_TRANSFER;
        change_out.pubkey_hash = g_pkh;
        b.tx.outputs.push_back(change_out);
    }

    // Sign
    SpentOutput spent{utxo_amount, OUT_TRANSFER};
    std::string err;
    bool ok = SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    assert(ok && "SignTransactionInput failed");

    return b;
}

// Helper: build a tx that spends a BOND_LOCK UTXO
static BondTxBundle MakeBondSpendTx(
    uint64_t lock_until,
    int64_t bond_amount = 500000,
    int64_t spend_height = 10000,
    int64_t bond_activation = BOND_ACTIVATION_HEIGHT_MAINNET)
{
    BondTxBundle b;
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = spend_height;
    b.ctx.bond_activation_height = bond_activation;

    // Source UTXO (BOND_LOCK with lock_until)
    Hash256 prev_txid = MakeFakeTxid(0x33);
    UTXOEntry utxo;
    utxo.amount = bond_amount;
    utxo.type = OUT_BOND_LOCK;
    utxo.pubkey_hash = g_pkh;
    utxo.height = 6000;
    utxo.is_coinbase = false;
    WriteLockUntil(utxo.payload, lock_until);
    utxo.payload_len = (uint16_t)utxo.payload.size();
    b.utxos.Add(prev_txid, 0, utxo);

    // Build spending tx
    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = 0;
    b.tx.inputs.push_back(in);

    TxOutput out;
    out.amount = bond_amount - 300;  // fee
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out);

    // Sign with BOND_LOCK spent type
    SpentOutput spent{bond_amount, OUT_BOND_LOCK};
    std::string err;
    bool ok = SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    assert(ok && "SignTransactionInput failed");

    return b;
}

// =============================================================================
// BL01: Create BOND_LOCK output — valid (post-activation)
// =============================================================================
TEST(BL01_create_bond_valid) {
    auto b = MakeBondCreateTx(10000);  // lock until height 10000, created at 6000
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// BL02: Create BOND_LOCK before activation height → R11 FAIL
// =============================================================================
TEST(BL02_create_bond_before_activation) {
    auto b = MakeBondCreateTx(10000, 500000, 1000000, 4999);  // height 4999 < 5000
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::R11_INACTIVE_TYPE);
}

// =============================================================================
// BL03: Spend BOND_LOCK before lock_until → S11 FAIL
// =============================================================================
TEST(BL03_spend_bond_before_unlock) {
    auto b = MakeBondSpendTx(10000, 500000, 8000);  // lock=10000, spend at 8000
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::S11_BOND_LOCKED);
}

// =============================================================================
// BL04: Spend BOND_LOCK at exactly lock_until → OK
// =============================================================================
TEST(BL04_spend_bond_at_unlock) {
    auto b = MakeBondSpendTx(10000, 500000, 10000);  // lock=10000, spend at 10000
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// BL05: Spend BOND_LOCK after lock_until → OK
// =============================================================================
TEST(BL05_spend_bond_after_unlock) {
    auto b = MakeBondSpendTx(10000, 500000, 15000);  // lock=10000, spend at 15000
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// BL06: Create BOND_LOCK with wrong payload size → R12 FAIL
// =============================================================================
TEST(BL06_bond_bad_payload_size) {
    auto b = MakeBondCreateTx(10000);
    b.tx.outputs[0].payload.resize(4);  // wrong: should be 8
    // Re-sign
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::R12_PAYLOAD_MISMATCH);
}

// =============================================================================
// BL07: Create BOND_LOCK with lock_until <= current height → R12 FAIL
// =============================================================================
TEST(BL07_bond_lock_in_past) {
    auto b = MakeBondCreateTx(5000, 500000, 1000000, 6000);  // lock=5000, height=6000
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::R12_PAYLOAD_MISMATCH);
}

// =============================================================================
// BL08: Create ESCROW_LOCK output — valid
// =============================================================================
TEST(BL08_create_escrow_valid) {
    auto b = MakeBondCreateTx(10000);
    // Convert output to ESCROW_LOCK with 28-byte payload
    b.tx.outputs[0].type = OUT_ESCROW_LOCK;
    b.tx.outputs[0].payload.resize(28);
    WriteLockUntil(b.tx.outputs[0].payload, 10000);
    // Beneficiary PKH (bytes 8-27)
    std::memset(b.tx.outputs[0].payload.data() + 8, 0xDD, 20);
    // Re-sign
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// BL09: ESCROW_LOCK with wrong payload size → R12 FAIL
// =============================================================================
TEST(BL09_escrow_bad_payload_size) {
    auto b = MakeBondCreateTx(10000);
    b.tx.outputs[0].type = OUT_ESCROW_LOCK;
    b.tx.outputs[0].payload.resize(8);  // wrong: should be 28
    WriteLockUntil(b.tx.outputs[0].payload, 10000);
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);
    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::R12_PAYLOAD_MISMATCH);
}

// =============================================================================
// BL10: Spend ESCROW_LOCK before lock_until → S11 FAIL
// =============================================================================
TEST(BL10_spend_escrow_before_unlock) {
    BondTxBundle b;
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = 8000;
    b.ctx.bond_activation_height = BOND_ACTIVATION_HEIGHT_MAINNET;

    Hash256 prev_txid = MakeFakeTxid(0x44);
    UTXOEntry utxo;
    utxo.amount = 500000;
    utxo.type = OUT_ESCROW_LOCK;
    utxo.pubkey_hash = g_pkh;
    utxo.height = 6000;
    utxo.is_coinbase = false;
    utxo.payload.resize(28);
    WriteLockUntil(utxo.payload, 10000);
    std::memset(utxo.payload.data() + 8, 0xDD, 20);
    utxo.payload_len = 28;
    b.utxos.Add(prev_txid, 0, utxo);

    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = prev_txid; in.prev_index = 0;
    b.tx.inputs.push_back(in);
    TxOutput out; out.amount = 499700; out.type = OUT_TRANSFER; out.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out);
    SpentOutput spent{500000, OUT_ESCROW_LOCK};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);

    EXPECT_FAIL(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx),
                TxValCode::S11_BOND_LOCKED);
}

// =============================================================================
// BL11: Spend ESCROW_LOCK after lock_until → OK
// =============================================================================
TEST(BL11_spend_escrow_after_unlock) {
    BondTxBundle b;
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = 10000;
    b.ctx.bond_activation_height = BOND_ACTIVATION_HEIGHT_MAINNET;

    Hash256 prev_txid = MakeFakeTxid(0x55);
    UTXOEntry utxo;
    utxo.amount = 500000;
    utxo.type = OUT_ESCROW_LOCK;
    utxo.pubkey_hash = g_pkh;
    utxo.height = 6000;
    utxo.is_coinbase = false;
    utxo.payload.resize(28);
    WriteLockUntil(utxo.payload, 10000);
    std::memset(utxo.payload.data() + 8, 0xDD, 20);
    utxo.payload_len = 28;
    b.utxos.Add(prev_txid, 0, utxo);

    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = prev_txid; in.prev_index = 0;
    b.tx.inputs.push_back(in);
    TxOutput out; out.amount = 499700; out.type = OUT_TRANSFER; out.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out);
    SpentOutput spent{500000, OUT_ESCROW_LOCK};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);

    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// BL12: Serialization round-trip for BOND_LOCK payload
// =============================================================================
TEST(BL12_serialization_roundtrip) {
    auto b = MakeBondCreateTx(12345);

    // Serialize
    std::vector<Byte> raw;
    std::string err;
    EXPECT(b.tx.Serialize(raw, &err), "Serialize failed: " + err);

    // Deserialize
    Transaction tx2;
    EXPECT(Transaction::Deserialize(raw, tx2, &err), "Deserialize failed: " + err);

    // Verify output type and payload preserved
    EXPECT(tx2.outputs[0].type == OUT_BOND_LOCK, "output type not preserved");
    EXPECT(tx2.outputs[0].payload.size() == 8, "payload size not preserved");
    uint64_t lock = ReadLockUntil(tx2.outputs[0].payload);
    EXPECT(lock == 12345, "lock_until not preserved: " + std::to_string(lock));
}

// =============================================================================
// BL13: UTXO set connect/disconnect with BOND_LOCK
// =============================================================================
TEST(BL13_utxo_connect_disconnect) {
    auto b = MakeBondCreateTx(10000);
    UtxoSet utxo_set;

    // Add source UTXO
    Hash256 prev_txid = MakeFakeTxid(0x22);
    UTXOEntry src_utxo;
    src_utxo.amount = 1000000;
    src_utxo.type = OUT_TRANSFER;
    src_utxo.pubkey_hash = g_pkh;
    src_utxo.height = 100;
    src_utxo.is_coinbase = false;
    utxo_set.AddUTXO({prev_txid, 0}, src_utxo);

    // Compute txid
    Hash256 txid;
    b.tx.ComputeTxId(txid);

    // Connect
    std::vector<UndoEntry> undo;
    std::string err;
    bool ok = utxo_set.ConnectTransaction(b.tx, txid, 6000, undo, &err);
    EXPECT(ok, "ConnectTransaction failed: " + err);

    // Source UTXO consumed
    EXPECT(!utxo_set.HasUTXO({prev_txid, 0}), "source UTXO not spent");

    // Bond output exists
    auto bond = utxo_set.GetUTXO({txid, 0});
    EXPECT(bond.has_value(), "bond UTXO not found");
    EXPECT(bond->type == OUT_BOND_LOCK, "bond output type wrong");
    EXPECT(bond->payload.size() == 8, "bond payload size wrong");
    EXPECT(ReadLockUntil(bond->payload) == 10000, "lock_until wrong");

    // Disconnect
    ok = utxo_set.DisconnectTransaction(b.tx, txid, undo, &err);
    EXPECT(ok, "DisconnectTransaction failed: " + err);

    // Source UTXO restored
    EXPECT(utxo_set.HasUTXO({prev_txid, 0}), "source UTXO not restored");

    // Bond output removed
    EXPECT(!utxo_set.HasUTXO({txid, 0}), "bond UTXO not removed");
}

// =============================================================================
// BL14: Normal transactions still work post-activation
// =============================================================================
TEST(BL14_normal_tx_still_works) {
    BondTxBundle b;
    b.ctx.genesis_hash = g_genesis_hash;
    b.ctx.spend_height = 6000;
    b.ctx.bond_activation_height = BOND_ACTIVATION_HEIGHT_MAINNET;

    Hash256 prev_txid = MakeFakeTxid(0x66);
    UTXOEntry utxo;
    utxo.amount = 1000000;
    utxo.type = OUT_TRANSFER;
    utxo.pubkey_hash = g_pkh;
    utxo.height = 100;
    utxo.is_coinbase = false;
    b.utxos.Add(prev_txid, 0, utxo);

    b.tx.version = 1;
    b.tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = prev_txid; in.prev_index = 0;
    b.tx.inputs.push_back(in);
    TxOutput out; out.amount = 999700; out.type = OUT_TRANSFER; out.pubkey_hash = g_pkh;
    b.tx.outputs.push_back(out);
    SpentOutput spent{1000000, OUT_TRANSFER};
    std::string err;
    SignTransactionInput(b.tx, 0, spent, g_genesis_hash, g_privkey, &err);

    EXPECT_OK(ValidateTransactionConsensus(b.tx, b.utxos, b.ctx));
}

// =============================================================================
// main
// =============================================================================

int main() {
    InitTestKeys();

    std::cout << "=== BOND_LOCK / ESCROW_LOCK Tests ===" << std::endl;

    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev_fail = g_fail;
        fn();
        if (g_fail == prev_fail) {
            g_pass++;
            std::cout << "PASS" << std::endl;
        } else {
            std::cout << "*** FAIL ***" << std::endl;
        }
    }

    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail
              << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;

    return g_fail > 0 ? 1 : 0;
}
