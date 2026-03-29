// =============================================================================
// test_popc_tx.cpp — Tests for PoPC TX builder and reward calculations
// =============================================================================
//
// Tests cover:
//   Reward math (TX01-TX04), Bond release (TX05-TX06),
//   Reward TX builder (TX07-TX08), Slash marker (TX09-TX10),
//   Lifecycle (TX11-TX12)
// =============================================================================

#include "sost/popc_tx_builder.h"
#include "sost/popc.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/utxo_set.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>

using namespace sost;

// =============================================================================
// Test infrastructure (same pattern as test_bond_lock.cpp)
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

// =============================================================================
// Mock UTXO view (same pattern as test_bond_lock.cpp)
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

static PrivKey    g_test_privkey{};
static PubKey     g_test_pubkey{};
static PubKeyHash g_test_pkh{};
static Hash256    g_genesis_hash{};

static Hash256 MakeFakeTxid(uint8_t fill) {
    Hash256 h{};
    std::memset(h.data(), fill, 32);
    return h;
}

static Hash256 MakeCommitmentId(uint8_t fill) {
    Hash256 h{};
    std::memset(h.data(), fill, 32);
    return h;
}

// Build a valid PoPCCommitment for testing
static PoPCCommitment MakeCommitment(uint8_t fill_id, uint16_t duration_months,
                                      int64_t bond_stocks = 100000000) {
    PoPCCommitment c{};
    std::memset(c.commitment_id.data(), fill_id, 32);
    c.user_pkh          = g_test_pkh;
    c.eth_wallet        = "0xd38955822b88867CD010946F0Ba25680B9DfC7a6";
    c.gold_token        = "XAUT";
    c.gold_amount_mg    = 31103;            // 1 oz
    c.bond_sost_stocks  = bond_stocks;
    c.duration_months   = duration_months;
    c.start_height      = 6000;
    // approximate end_height (4320 blocks/month @ 10 min/block)
    c.end_height        = 6000 + (int64_t)duration_months * 4320;
    c.bond_pct_bps      = 1200;
    c.reward_pct_bps    = compute_reward_pct(duration_months);
    c.status            = PoPCStatus::ACTIVE;
    c.sost_price_usd_micro  = 100000;
    c.gold_price_usd_micro  = 2000000000;
    return c;
}

// =============================================================================
// TX01: calculate_reward_stocks — 1% (100 bps) of 1 SOST = 1,000,000 stocks
// =============================================================================
TEST(TX01_calculate_reward_1pct) {
    // 100 bps = 1% of 100,000,000 stocks = 1,000,000 stocks
    int64_t reward = calculate_reward_stocks(100000000LL, 100);
    EXPECT(reward == 1000000LL,
           "expected 1000000 stocks, got " + std::to_string(reward));
}

// =============================================================================
// TX02: calculate_reward_stocks — 22% (2200 bps) of 1 SOST = 22,000,000 stocks
// =============================================================================
TEST(TX02_calculate_reward_22pct) {
    // 2200 bps = 22% of 100,000,000 stocks = 22,000,000 stocks
    int64_t reward = calculate_reward_stocks(100000000LL, 2200);
    EXPECT(reward == 22000000LL,
           "expected 22000000 stocks, got " + std::to_string(reward));
}

// =============================================================================
// TX03: calculate_reward_stocks — zero bond → 0 reward
// =============================================================================
TEST(TX03_calculate_reward_zero) {
    int64_t reward = calculate_reward_stocks(0LL, 2200);
    EXPECT(reward == 0LL,
           "expected 0 stocks for zero bond, got " + std::to_string(reward));
}

// =============================================================================
// TX04: calculate_reward_stocks — overflow guard
// Very large bond: must not crash, must return 0 or a capped value (not negative)
// =============================================================================
TEST(TX04_calculate_reward_overflow_guard) {
    // Use INT64_MAX as the bond — reward_pct_bps * bond would overflow int64
    int64_t very_large_bond = (int64_t)9223372036854775807LL; // INT64_MAX
    int64_t reward = calculate_reward_stocks(very_large_bond, 2200);
    // Must not be negative (no undefined overflow)
    EXPECT(reward >= 0,
           "overflow guard: reward must be >= 0, got " + std::to_string(reward));
    // Implementation returns 0 on overflow guard
    EXPECT(reward == 0LL,
           "overflow guard: expected 0, got " + std::to_string(reward));
}

// =============================================================================
// TX05: build_bond_release_tx — valid (lock expired)
// =============================================================================
TEST(TX05_build_release_valid) {
    // Create a BOND_LOCK UTXO with lock_until=10000, created at height=6000
    Hash256 bond_txid = MakeFakeTxid(0xAA);
    OutPoint bond_op{bond_txid, 0};

    UTXOEntry bond_utxo;
    bond_utxo.amount     = 100000000LL;  // 1 SOST
    bond_utxo.type       = OUT_BOND_LOCK;
    bond_utxo.pubkey_hash = g_test_pkh;
    bond_utxo.height     = 6000;
    bond_utxo.is_coinbase = false;
    WriteLockUntil(bond_utxo.payload, 10000);
    bond_utxo.payload_len = 8;

    // Build release TX at current_height=10000 (exactly at expiry — valid)
    Transaction tx;
    std::string err;
    bool ok = build_bond_release_tx(tx, bond_op, bond_utxo, 10000,
                                     g_genesis_hash, g_test_privkey, &err);
    EXPECT(ok, "build_bond_release_tx failed: " + err);

    // Verify structure: 1 input, 1 output
    EXPECT(tx.inputs.size() == 1,
           "expected 1 input, got " + std::to_string(tx.inputs.size()));
    EXPECT(tx.outputs.size() == 1,
           "expected 1 output, got " + std::to_string(tx.outputs.size()));

    // Output must be OUT_TRANSFER
    EXPECT(tx.outputs[0].type == OUT_TRANSFER,
           "output type must be OUT_TRANSFER");

    // Amount = bond - fee, must be > 0
    EXPECT(tx.outputs[0].amount > 0,
           "output amount must be > 0");

    // Fee must be positive (output < bond)
    int64_t fee = bond_utxo.amount - tx.outputs[0].amount;
    EXPECT(fee > 0, "fee must be > 0, got " + std::to_string(fee));

    // Input references the bond outpoint
    EXPECT(tx.inputs[0].prev_txid == bond_txid, "input prev_txid mismatch");
    EXPECT(tx.inputs[0].prev_index == 0, "input prev_index mismatch");
}

// =============================================================================
// TX06: build_bond_release_tx — early (lock not yet expired)
// =============================================================================
TEST(TX06_build_release_early) {
    Hash256 bond_txid = MakeFakeTxid(0xBB);
    OutPoint bond_op{bond_txid, 0};

    UTXOEntry bond_utxo;
    bond_utxo.amount      = 100000000LL;
    bond_utxo.type        = OUT_BOND_LOCK;
    bond_utxo.pubkey_hash = g_test_pkh;
    bond_utxo.height      = 6000;
    bond_utxo.is_coinbase = false;
    WriteLockUntil(bond_utxo.payload, 10000);
    bond_utxo.payload_len = 8;

    // Attempt release at current_height=9999 (before expiry)
    Transaction tx;
    std::string err;
    bool ok = build_bond_release_tx(tx, bond_op, bond_utxo, 9999,
                                     g_genesis_hash, g_test_privkey, &err);
    EXPECT(!ok, "build_bond_release_tx should fail before lock_until");
    EXPECT(!err.empty(), "error message should be non-empty on early release");
}

// =============================================================================
// TX07: build_reward_tx — valid pool with sufficient funds
// =============================================================================
TEST(TX07_build_reward_valid) {
    // Build a pool key pair (separate from the test user keys)
    PrivKey pool_privkey;
    PubKey  pool_pubkey;
    std::string err;
    bool key_ok = GenerateKeyPair(pool_privkey, pool_pubkey, &err);
    EXPECT(key_ok, "GenerateKeyPair for pool failed: " + err);
    PubKeyHash pool_pkh = ComputePubKeyHash(pool_pubkey);

    // Create 3 pool UTXOs: 50M + 30M + 20M = 100M stocks total
    std::vector<std::pair<OutPoint, UTXOEntry>> pool_utxos;
    int64_t amounts[] = {50000000LL, 30000000LL, 20000000LL};
    for (int i = 0; i < 3; ++i) {
        OutPoint op{MakeFakeTxid((uint8_t)(0xC0 + i)), 0};
        UTXOEntry utxo;
        utxo.amount      = amounts[i];
        utxo.type        = OUT_TRANSFER;
        utxo.pubkey_hash = pool_pkh;
        utxo.height      = 1000 + i * 100;
        utxo.is_coinbase = false;
        pool_utxos.push_back({op, utxo});
    }

    // Request 10M stocks reward to the test user
    int64_t reward_amount = 10000000LL;

    Transaction tx;
    err.clear();
    bool ok = build_reward_tx(tx, pool_utxos, g_test_pkh, reward_amount,
                               pool_pkh, g_genesis_hash, pool_privkey, &err);
    EXPECT(ok, "build_reward_tx failed: " + err);

    // Must have at least 1 input and at least 1 output
    EXPECT(tx.inputs.size() >= 1, "expected at least 1 input");
    EXPECT(tx.outputs.size() >= 1, "expected at least 1 output");

    // First output must deliver exactly reward_amount to recipient
    EXPECT(tx.outputs[0].amount == reward_amount,
           "recipient output amount mismatch: expected " +
           std::to_string(reward_amount) + " got " +
           std::to_string(tx.outputs[0].amount));
    EXPECT(tx.outputs[0].pubkey_hash == g_test_pkh,
           "recipient pubkey_hash mismatch");

    // If there is a change output, it goes to the pool
    if (tx.outputs.size() >= 2) {
        EXPECT(tx.outputs[1].pubkey_hash == pool_pkh,
               "change output pubkey_hash must be pool_pkh");
        EXPECT(tx.outputs[1].amount > 0,
               "change output amount must be > 0");
    }
}

// =============================================================================
// TX08: build_reward_tx — insufficient pool balance
// =============================================================================
TEST(TX08_build_reward_insufficient) {
    PrivKey pool_privkey;
    PubKey  pool_pubkey;
    std::string err;
    GenerateKeyPair(pool_privkey, pool_pubkey, &err);
    PubKeyHash pool_pkh = ComputePubKeyHash(pool_pubkey);

    // Pool has only 5M stocks
    std::vector<std::pair<OutPoint, UTXOEntry>> pool_utxos;
    OutPoint op{MakeFakeTxid(0xD0), 0};
    UTXOEntry utxo;
    utxo.amount      = 5000000LL;
    utxo.type        = OUT_TRANSFER;
    utxo.pubkey_hash = pool_pkh;
    utxo.height      = 1000;
    utxo.is_coinbase = false;
    pool_utxos.push_back({op, utxo});

    // Request 10M stocks reward — exceeds pool balance
    int64_t reward_amount = 10000000LL;

    Transaction tx;
    err.clear();
    bool ok = build_reward_tx(tx, pool_utxos, g_test_pkh, reward_amount,
                               pool_pkh, g_genesis_hash, pool_privkey, &err);
    EXPECT(!ok, "build_reward_tx should fail when pool is insufficient");
    EXPECT(!err.empty(), "error message should be non-empty on insufficient funds");
}

// =============================================================================
// TX09: build_slash_marker — valid active commitment → SLASHED
// =============================================================================
TEST(TX09_build_slash_marker) {
    PoPCRegistry reg;
    auto c = MakeCommitment(0xE0, 3);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "register_commitment failed: " + err);

    // Commitment is ACTIVE — slash it
    err.clear();
    bool ok = build_slash_marker(reg, c.commitment_id, "audit_failure", &err);
    EXPECT(ok, "build_slash_marker failed: " + err);

    // Registry must show SLASHED status
    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after slash");
    EXPECT(found->status == PoPCStatus::SLASHED,
           "commitment status must be SLASHED after build_slash_marker");
}

// =============================================================================
// TX10: build_slash_marker — already COMPLETED → should fail
// =============================================================================
TEST(TX10_build_slash_already_completed) {
    PoPCRegistry reg;
    auto c = MakeCommitment(0xE1, 3);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "register_commitment failed: " + err);

    // Complete the commitment first
    EXPECT(reg.complete(c.commitment_id, &err), "complete failed: " + err);

    // Now try to slash — must fail (already completed)
    err.clear();
    bool ok = build_slash_marker(reg, c.commitment_id, "too_late", &err);
    EXPECT(!ok, "build_slash_marker should fail on COMPLETED commitment");
    EXPECT(!err.empty(), "error message should be non-empty");

    // Status should remain COMPLETED
    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found");
    EXPECT(found->status == PoPCStatus::COMPLETED,
           "status should remain COMPLETED after failed slash");
}

// =============================================================================
// TX11: Full lifecycle — register → release (after lock) → reward → complete
//        → try release again → fail (already completed means registry check)
// =============================================================================
TEST(TX11_lifecycle_register_complete_reward) {
    PoPCRegistry reg;

    // Step 1: register a 3-month commitment
    auto c = MakeCommitment(0xF0, 3, 100000000LL); // 1 SOST bond
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "register failed: " + err);
    EXPECT(reg.active_count() == 1, "expected 1 active commitment");

    // Step 2: build bond release TX at height = end_height (lock expired)
    Hash256 bond_txid = MakeFakeTxid(0xF1);
    OutPoint bond_op{bond_txid, 0};
    UTXOEntry bond_utxo;
    bond_utxo.amount      = 100000000LL;
    bond_utxo.type        = OUT_BOND_LOCK;
    bond_utxo.pubkey_hash = g_test_pkh;
    bond_utxo.height      = c.start_height;
    bond_utxo.is_coinbase = false;
    WriteLockUntil(bond_utxo.payload, (uint64_t)c.end_height);
    bond_utxo.payload_len = 8;

    Transaction release_tx;
    err.clear();
    bool release_ok = build_bond_release_tx(release_tx, bond_op, bond_utxo,
                                             c.end_height, g_genesis_hash,
                                             g_test_privkey, &err);
    EXPECT(release_ok, "bond release TX failed: " + err);
    EXPECT(release_tx.outputs[0].amount > 0, "release output amount must be > 0");

    // Step 3: calculate reward = 4% of 1 SOST = 4,000,000 stocks
    int64_t reward = calculate_reward_stocks(c.bond_sost_stocks, c.reward_pct_bps);
    EXPECT(reward == 4000000LL,
           "expected 4000000 stocks (4% of 1 SOST), got " + std::to_string(reward));

    // Step 4: mark commitment as completed in registry
    err.clear();
    EXPECT(reg.complete(c.commitment_id, &err), "complete failed: " + err);
    EXPECT(reg.active_count() == 0, "active_count should be 0 after complete");

    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after complete");
    EXPECT(found->status == PoPCStatus::COMPLETED,
           "status must be COMPLETED");

    // Step 5: try to complete again → must fail
    err.clear();
    bool double_complete = reg.complete(c.commitment_id, &err);
    EXPECT(!double_complete, "double complete must fail");
    EXPECT(!err.empty(), "error message should be non-empty on double complete");
}

// =============================================================================
// TX12: Full lifecycle — register → slash → try complete → fail (slashed)
// =============================================================================
TEST(TX12_lifecycle_register_slash) {
    PoPCRegistry reg;

    // Register a 6-month commitment
    auto c = MakeCommitment(0xF2, 6, 50000000LL);
    std::string err;
    EXPECT(reg.register_commitment(c, &err), "register failed: " + err);
    EXPECT(reg.active_count() == 1, "expected 1 active commitment");

    // Slash the commitment
    err.clear();
    bool slashed = build_slash_marker(reg, c.commitment_id, "missed_audit", &err);
    EXPECT(slashed, "slash failed: " + err);

    // Active count drops to 0
    EXPECT(reg.active_count() == 0, "active_count should be 0 after slash");

    const PoPCCommitment* found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after slash");
    EXPECT(found->status == PoPCStatus::SLASHED, "status must be SLASHED");

    // Try to complete a slashed commitment → must fail
    err.clear();
    bool complete_ok = reg.complete(c.commitment_id, &err);
    EXPECT(!complete_ok, "complete on SLASHED commitment must fail");
    EXPECT(!err.empty(), "error message should be non-empty");

    // Status must remain SLASHED
    found = reg.find(c.commitment_id);
    EXPECT(found != nullptr, "commitment not found after failed complete");
    EXPECT(found->status == PoPCStatus::SLASHED,
           "status must remain SLASHED after failed complete");
}

// =============================================================================
// main
// =============================================================================

int main() {
    // Generate test keys
    sost::PrivKey privkey; sost::PubKey pubkey; sost::PubKeyHash pkh;
    std::string err;
    sost::GenerateKeyPair(privkey, pubkey, &err);
    pkh = sost::ComputePubKeyHash(pubkey);
    g_test_privkey = privkey;
    g_test_pubkey  = pubkey;
    g_test_pkh     = pkh;
    std::memset(g_genesis_hash.data(), 0xAA, 32);

    std::cout << "=== PoPC TX Builder Tests ===" << std::endl;

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
