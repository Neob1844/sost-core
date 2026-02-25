// =============================================================================
// SOST — Phase 6: Mempool Tests
//
// MP01-MP08: Accept / reject
// MP09-MP12: Removal & block processing
// MP13-MP17: Block template building
// MP18-MP22: Queries, capacity, eviction
// MP23-MP25: Integration (Phase 3-5 + mempool)
// =============================================================================

#include <sost/mempool.h>
#include <sost/tx_signer.h>
#include <sost/block.h>

#include <cstdio>
#include <cstring>
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
// Test helpers
// ---------------------------------------------------------------------------

static Hash256 MakeHash(uint8_t fill) {
    Hash256 h;
    h.fill(fill);
    return h;
}

/// Build a signed standard tx spending one UTXO.
/// Returns the fee paid.
struct TestTxResult {
    Transaction tx;
    Hash256 txid;
    int64_t fee;
};

static TestTxResult MakeSignedTx(
    const Hash256& prev_txid, uint32_t prev_index,
    int64_t input_amount,
    int64_t output_amount,
    const PrivKey& priv,
    const PubKey& pub,
    const PubKeyHash& dest_pkh)
{
    // Build unsigned tx
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev_txid;
    in.prev_index = prev_index;
    in.pubkey = pub;
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount = output_amount;
    out.type = OUT_TRANSFER;
    out.pubkey_hash = dest_pkh;
    tx.outputs.push_back(out);

    // Sign
    SpentOutput spent;
    spent.amount = input_amount;
    spent.type = OUT_COINBASE_MINER;  // spending coinbase miner output

    Hash256 genesis_hash{};  // use zero for testing
    std::string err;
    bool ok = SignTransactionInput(tx, 0, spent, genesis_hash, priv, &err);
    (void)ok;

    Hash256 txid{};
    tx.ComputeTxId(txid, nullptr);

    return {tx, txid, input_amount - output_amount};
}

/// Create a coinbase and connect it to UTXO set (gives us spendable outputs).
static Hash256 SeedUtxo(
    UtxoSet& utxos,
    int64_t height,
    int64_t subsidy,
    const PubKeyHash& miner_pkh,
    const PubKeyHash& gold_pkh,
    const PubKeyHash& popc_pkh)
{
    Transaction cb;
    cb.version = 1;
    cb.tx_type = TX_TYPE_COINBASE;

    TxInput cbin;
    cbin.prev_txid.fill(0x00);
    cbin.prev_index = 0xFFFFFFFF;
    cbin.signature.fill(0x00);
    for (int i = 0; i < 8; ++i)
        cbin.signature[i] = (uint8_t)((height >> (i * 8)) & 0xFF);
    cbin.pubkey.fill(0x00);
    cb.inputs.push_back(cbin);

    int64_t miner_amt = (subsidy * 50) / 100;
    int64_t gold_amt  = (subsidy * 25) / 100;
    int64_t popc_amt  = subsidy - miner_amt - gold_amt;

    TxOutput om; om.amount = miner_amt; om.type = OUT_COINBASE_MINER; om.pubkey_hash = miner_pkh;
    TxOutput og; og.amount = gold_amt;  og.type = OUT_COINBASE_GOLD;  og.pubkey_hash = gold_pkh;
    TxOutput op; op.amount = popc_amt;  op.type = OUT_COINBASE_POPC;  op.pubkey_hash = popc_pkh;
    cb.outputs = {om, og, op};

    Hash256 txid{};
    cb.ComputeTxId(txid, nullptr);
    utxos.ConnectCoinbase(cb, txid, height, nullptr);
    return txid;
}

/// Set up a standard test environment:
/// - keypair
/// - utxo set with matured coinbase at height 0 (confirmed at height 101+)
/// - validation context at spend_height = 200
struct TestEnv {
    PrivKey priv;
    PubKey pub;
    PubKeyHash pkh;
    PubKeyHash gold_pkh;
    PubKeyHash popc_pkh;
    UtxoSet utxos;
    TxValidationContext ctx;
    Hash256 cb_txid;
    int64_t miner_amount;

    static TestEnv Create() {
        TestEnv env;

        // Generate keypair
        std::string err;
        GenerateKeyPair(env.priv, env.pub, &err);
        env.pkh = ComputePubKeyHash(env.pub);
        env.gold_pkh.fill(0xAA);
        env.popc_pkh.fill(0xBB);

        int64_t subsidy = 785100863;
        env.miner_amount = (subsidy * 50) / 100;

        // Seed coinbase at height 0
        env.cb_txid = SeedUtxo(env.utxos, 0, subsidy,
                                env.pkh, env.gold_pkh, env.popc_pkh);

        // Context: spend_height=200 (well past coinbase maturity of 100)
        env.ctx.spend_height = 200;
        env.ctx.capsule_activation_height = 5000;  // mainnet default

        return env;
    }
};

// ============================================================================
// ACCEPT / REJECT TESTS
// ============================================================================

// MP01: Accept a valid transaction
static bool MP01_accept_valid() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    int64_t send = env.miner_amount - 10000;  // fee = 10000
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, send, env.priv, env.pub, dest);

    auto res = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(res.accepted);
    EXPECT(res.code == MempoolAcceptCode::ACCEPTED);
    EXPECT(res.txid == txid);
    EXPECT(res.fee == fee);
    EXPECT(res.fee_rate_per_kb > 0);
    EXPECT(pool.Size() == 1);
    return true;
}

// MP02: Reject coinbase
static bool MP02_reject_coinbase() {
    auto env = TestEnv::Create();
    Mempool pool;

    Transaction cb;
    cb.version = 1;
    cb.tx_type = TX_TYPE_COINBASE;
    TxInput cbin; cbin.prev_txid.fill(0x00); cbin.prev_index = 0xFFFFFFFF;
    cbin.signature.fill(0x00); cbin.pubkey.fill(0x00);
    cb.inputs.push_back(cbin);
    TxOutput out; out.amount = 100; out.type = OUT_COINBASE_MINER; out.pubkey_hash = env.pkh;
    cb.outputs.push_back(out);

    auto res = pool.AcceptToMempool(cb, env.utxos, env.ctx);
    EXPECT(!res.accepted);
    EXPECT(res.code == MempoolAcceptCode::COINBASE_REJECT);
    EXPECT(pool.Size() == 0);
    return true;
}

// MP03: Reject duplicate
static bool MP03_reject_duplicate() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    auto res1 = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(res1.accepted);

    auto res2 = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(!res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::ALREADY_IN_POOL);
    EXPECT(pool.Size() == 1);
    return true;
}

// MP04: Reject double-spend within mempool
static bool MP04_double_spend_mempool() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest1; dest1.fill(0x01);
    PubKeyHash dest2; dest2.fill(0x02);

    // tx1 spends cb:0
    auto [tx1, txid1, fee1] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest1);

    auto res1 = pool.AcceptToMempool(tx1, env.utxos, env.ctx);
    EXPECT(res1.accepted);

    // tx2 also tries to spend cb:0
    auto [tx2, txid2, fee2] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 20000,
        env.priv, env.pub, dest2);

    auto res2 = pool.AcceptToMempool(tx2, env.utxos, env.ctx);
    EXPECT(!res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::DOUBLE_SPEND);
    EXPECT(pool.Size() == 1);
    return true;
}

// MP05: Reject consensus failure (bad version)
static bool MP05_consensus_fail() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    tx.version = 999;  // invalid

    auto res = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(!res.accepted);
    EXPECT(res.code == MempoolAcceptCode::CONSENSUS_FAIL);
    return true;
}

// MP06: Reject missing input (UTXO not found)
static bool MP06_missing_input() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    // Spend a non-existent UTXO
    auto [tx, txid, fee] = MakeSignedTx(
        MakeHash(0xFF), 0, 100000, 90000,
        env.priv, env.pub, dest);

    auto res = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(!res.accepted);
    EXPECT(res.code == MempoolAcceptCode::CONSENSUS_FAIL);
    return true;
}

// MP07: Reject fee too low (policy)
static bool MP07_fee_too_low() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    // Send almost all — fee = 1 stockshi (below min relay)
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 1,
        env.priv, env.pub, dest);

    auto res = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(!res.accepted);
    // Could be consensus S8 or policy P_FEE_BELOW_RELAY
    EXPECT(res.code == MempoolAcceptCode::CONSENSUS_FAIL ||
           res.code == MempoolAcceptCode::POLICY_FAIL);
    return true;
}

// MP08: Accept multiple non-conflicting txs
static bool MP08_multiple_txs() {
    auto env = TestEnv::Create();
    Mempool pool;

    // We have 3 coinbase outputs (miner:0, gold:1, popc:2)
    // But gold/popc pkh don't match our key... so seed 2 more coinbases
    // Actually let's just use separate coinbases at different heights
    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);
    int64_t send = env.miner_amount - 10000;

    auto [tx1, txid1, fee1] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, send, env.priv, env.pub, dest);
    auto [tx2, txid2, fee2] = MakeSignedTx(
        cb2, 0, env.miner_amount, send, env.priv, env.pub, dest);

    auto res1 = pool.AcceptToMempool(tx1, env.utxos, env.ctx);
    EXPECT(res1.accepted);
    auto res2 = pool.AcceptToMempool(tx2, env.utxos, env.ctx);
    EXPECT(res2.accepted);
    EXPECT(pool.Size() == 2);
    return true;
}

// ============================================================================
// REMOVAL & BLOCK PROCESSING
// ============================================================================

// MP09: Remove by txid
static bool MP09_remove_by_txid() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(pool.Size() == 1);

    EXPECT(pool.RemoveTransaction(txid));
    EXPECT(pool.Size() == 0);
    EXPECT(!pool.HasTransaction(txid));

    // Double-remove returns false
    EXPECT(!pool.RemoveTransaction(txid));
    return true;
}

// MP10: RemoveForBlock removes confirmed tx
static bool MP10_remove_for_block_confirmed() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(pool.Size() == 1);

    // Simulate block with this tx
    std::vector<Transaction> block_txs = {tx};
    size_t removed = pool.RemoveForBlock(block_txs);
    EXPECT(removed == 1);
    EXPECT(pool.Size() == 0);
    return true;
}

// MP11: RemoveForBlock removes conflicting tx (same input, different output)
static bool MP11_remove_for_block_conflict() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest1; dest1.fill(0x01);
    PubKeyHash dest2; dest2.fill(0x02);

    // Mempool tx spends cb:0 → dest1
    auto [tx1, txid1, _] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest1);
    pool.AcceptToMempool(tx1, env.utxos, env.ctx);

    // Block contains a DIFFERENT tx spending cb:0 → dest2
    auto [tx2, txid2, __] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 20000,
        env.priv, env.pub, dest2);

    size_t removed = pool.RemoveForBlock({tx2});
    EXPECT(removed == 1);
    EXPECT(pool.Size() == 0);
    EXPECT(!pool.HasTransaction(txid1));
    return true;
}

// MP12: RemoveForBlock preserves non-conflicting txs
static bool MP12_remove_preserves_others() {
    auto env = TestEnv::Create();
    Mempool pool;

    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);
    int64_t send = env.miner_amount - 10000;

    auto [tx1, txid1, fee1] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, send, env.priv, env.pub, dest);
    auto [tx2, txid2, fee2] = MakeSignedTx(
        cb2, 0, env.miner_amount, send, env.priv, env.pub, dest);

    pool.AcceptToMempool(tx1, env.utxos, env.ctx);
    pool.AcceptToMempool(tx2, env.utxos, env.ctx);
    EXPECT(pool.Size() == 2);

    // Block confirms only tx1
    size_t removed = pool.RemoveForBlock({tx1});
    EXPECT(removed == 1);
    EXPECT(pool.Size() == 1);
    EXPECT(!pool.HasTransaction(txid1));
    EXPECT(pool.HasTransaction(txid2));
    return true;
}

// ============================================================================
// BLOCK TEMPLATE
// ============================================================================

// MP13: BuildBlockTemplate returns txs ordered by fee-rate descending
static bool MP13_template_fee_order() {
    auto env = TestEnv::Create();
    Mempool pool;

    // Create 3 coinbases to spend
    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);
    Hash256 cb3 = SeedUtxo(env.utxos, 2, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);

    // Different fees (same size ≈ same, so fee ∝ fee-rate)
    auto [txLow, _, feeLow] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);
    auto [txMed, __, feeMed] = MakeSignedTx(
        cb2, 0, env.miner_amount, env.miner_amount - 50000,
        env.priv, env.pub, dest);
    auto [txHigh, ___, feeHigh] = MakeSignedTx(
        cb3, 0, env.miner_amount, env.miner_amount - 100000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(txLow, env.utxos, env.ctx, 1);
    pool.AcceptToMempool(txMed, env.utxos, env.ctx, 2);
    pool.AcceptToMempool(txHigh, env.utxos, env.ctx, 3);
    EXPECT(pool.Size() == 3);

    auto tmpl = pool.BuildBlockTemplate();
    EXPECT(tmpl.txs.size() == 3);
    EXPECT(tmpl.total_fees == feeLow + feeMed + feeHigh);

    // First tx should have highest fee-rate
    EXPECT(tmpl.txs[0].outputs[0].amount == env.miner_amount - 100000);
    EXPECT(tmpl.txs[2].outputs[0].amount == env.miner_amount - 10000);
    return true;
}

// MP14: BuildBlockTemplate respects max_txs
static bool MP14_template_max_txs() {
    auto env = TestEnv::Create();
    Mempool pool;

    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);
    Hash256 cb3 = SeedUtxo(env.utxos, 2, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);

    auto [tx1, _, __] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);
    auto [tx2, _2, __2] = MakeSignedTx(
        cb2, 0, env.miner_amount, env.miner_amount - 20000,
        env.priv, env.pub, dest);
    auto [tx3, _3, __3] = MakeSignedTx(
        cb3, 0, env.miner_amount, env.miner_amount - 30000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx1, env.utxos, env.ctx);
    pool.AcceptToMempool(tx2, env.utxos, env.ctx);
    pool.AcceptToMempool(tx3, env.utxos, env.ctx);

    auto tmpl = pool.BuildBlockTemplate(2);  // max 2
    EXPECT(tmpl.txs.size() == 2);
    // Should pick highest 2 by fee-rate
    return true;
}

// MP15: Empty mempool → empty template
static bool MP15_template_empty() {
    Mempool pool;
    auto tmpl = pool.BuildBlockTemplate();
    EXPECT(tmpl.txs.empty());
    EXPECT(tmpl.total_fees == 0);
    EXPECT(tmpl.total_size == 0);
    return true;
}

// MP16: Template total_fees matches sum
static bool MP16_template_total_fees() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    int64_t fee_amount = 25000;
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - fee_amount,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    auto tmpl = pool.BuildBlockTemplate();
    EXPECT(tmpl.txs.size() == 1);
    EXPECT(tmpl.total_fees == fee_amount);
    return true;
}

// MP17: Template respects max_block_size
static bool MP17_template_max_size() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);

    // Set max_block_size to 1 byte — tx won't fit
    auto tmpl = pool.BuildBlockTemplate(4096, 1);
    EXPECT(tmpl.txs.empty());
    EXPECT(tmpl.total_fees == 0);
    return true;
}

// ============================================================================
// QUERIES, CAPACITY, EVICTION
// ============================================================================

// MP18: HasTransaction + GetEntry
static bool MP18_queries() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    EXPECT(!pool.HasTransaction(txid));
    EXPECT(pool.GetEntry(txid) == nullptr);

    pool.AcceptToMempool(tx, env.utxos, env.ctx, 42);

    EXPECT(pool.HasTransaction(txid));
    auto* entry = pool.GetEntry(txid);
    EXPECT(entry != nullptr);
    EXPECT(entry->txid == txid);
    EXPECT(entry->fee == fee);
    EXPECT(entry->time_added == 42);
    EXPECT(entry->size > 0);
    return true;
}

// MP19: IsSpent tracks spent outpoints
static bool MP19_is_spent() {
    auto env = TestEnv::Create();
    Mempool pool;

    OutPoint op{env.cb_txid, 0};
    EXPECT(!pool.IsSpent(op));

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(pool.IsSpent(op));

    // Remove → no longer spent
    pool.RemoveTransaction(txid);
    EXPECT(!pool.IsSpent(op));
    return true;
}

// MP20: TotalFees and TotalSize
static bool MP20_totals() {
    auto env = TestEnv::Create();
    Mempool pool;

    EXPECT(pool.TotalFees() == 0);
    EXPECT(pool.TotalSize() == 0);

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 15000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(pool.TotalFees() == 15000);
    EXPECT(pool.TotalSize() > 0);
    return true;
}

// MP21: Pool capacity limit + eviction
static bool MP21_capacity_eviction() {
    auto env = TestEnv::Create();
    Mempool pool(2);  // max 2 entries

    // Create 3 coinbases
    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);
    Hash256 cb3 = SeedUtxo(env.utxos, 2, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);

    // Low fee
    auto [txLow, txidLow, _] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 1000,
        env.priv, env.pub, dest);
    // Medium fee
    auto [txMed, txidMed, __] = MakeSignedTx(
        cb2, 0, env.miner_amount, env.miner_amount - 5000,
        env.priv, env.pub, dest);
    // High fee
    auto [txHigh, txidHigh, ___] = MakeSignedTx(
        cb3, 0, env.miner_amount, env.miner_amount - 50000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(txLow, env.utxos, env.ctx);
    pool.AcceptToMempool(txMed, env.utxos, env.ctx);
    EXPECT(pool.Size() == 2);

    // Adding high-fee tx should evict lowest (txLow)
    auto res = pool.AcceptToMempool(txHigh, env.utxos, env.ctx);
    EXPECT(res.accepted);
    EXPECT(pool.Size() == 2);
    EXPECT(!pool.HasTransaction(txidLow));  // evicted
    EXPECT(pool.HasTransaction(txidMed));
    EXPECT(pool.HasTransaction(txidHigh));
    return true;
}

// MP22: Pool full, low fee-rate rejected
static bool MP22_pool_full_reject() {
    auto env = TestEnv::Create();
    Mempool pool(1);  // max 1

    Hash256 cb2 = SeedUtxo(env.utxos, 1, 785100863,
                            env.pkh, env.gold_pkh, env.popc_pkh);

    PubKeyHash dest; dest.fill(0x01);

    // High fee first
    auto [txHigh, _, __] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 50000,
        env.priv, env.pub, dest);
    // Low fee tries to enter
    auto [txLow, _2, __2] = MakeSignedTx(
        cb2, 0, env.miner_amount, env.miner_amount - 500,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(txHigh, env.utxos, env.ctx);
    EXPECT(pool.Size() == 1);

    auto res = pool.AcceptToMempool(txLow, env.utxos, env.ctx);
    EXPECT(!res.accepted);
    EXPECT(res.code == MempoolAcceptCode::POOL_FULL);
    EXPECT(pool.Size() == 1);
    return true;
}

// ============================================================================
// INTEGRATION TESTS
// ============================================================================

// MP23: Clear
static bool MP23_clear() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest);

    pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(pool.Size() == 1);

    pool.Clear();
    EXPECT(pool.Size() == 0);
    EXPECT(pool.TotalFees() == 0);
    EXPECT(!pool.HasTransaction(txid));
    EXPECT(!pool.IsSpent({env.cb_txid, 0}));
    return true;
}

// MP24: Full lifecycle — accept → template → connect block → remove
static bool MP24_full_lifecycle() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    int64_t fee_amt = 25000;
    auto [tx, txid, fee] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - fee_amt,
        env.priv, env.pub, dest);

    // 1. Accept
    auto res = pool.AcceptToMempool(tx, env.utxos, env.ctx);
    EXPECT(res.accepted);

    // 2. Build template
    auto tmpl = pool.BuildBlockTemplate();
    EXPECT(tmpl.txs.size() == 1);
    EXPECT(tmpl.total_fees == fee_amt);

    // 3. Simulate: connect block would include this tx
    // (In real code, miner builds coinbase + template txs → Block)
    // For now, just remove for block
    size_t removed = pool.RemoveForBlock(tmpl.txs);
    EXPECT(removed == 1);
    EXPECT(pool.Size() == 0);

    return true;
}

// MP25: After removal, outpoints freed for re-use
static bool MP25_outpoint_reuse_after_remove() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest1; dest1.fill(0x01);
    PubKeyHash dest2; dest2.fill(0x02);

    // Accept tx1 spending cb:0
    auto [tx1, txid1, _] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 10000,
        env.priv, env.pub, dest1);
    pool.AcceptToMempool(tx1, env.utxos, env.ctx);
    EXPECT(pool.IsSpent({env.cb_txid, 0}));

    // Remove tx1
    pool.RemoveTransaction(txid1);
    EXPECT(!pool.IsSpent({env.cb_txid, 0}));

    // Now tx2 can spend the same outpoint
    auto [tx2, txid2, __] = MakeSignedTx(
        env.cb_txid, 0, env.miner_amount, env.miner_amount - 20000,
        env.priv, env.pub, dest2);
    auto res = pool.AcceptToMempool(tx2, env.utxos, env.ctx);
    EXPECT(res.accepted);
    EXPECT(pool.Size() == 1);
    return true;
}

// ============================================================================

int main() {
    printf("=== Phase 6: Mempool tests ===\n\n");

    printf("--- Accept / Reject ---\n");
    RUN(MP01_accept_valid);
    RUN(MP02_reject_coinbase);
    RUN(MP03_reject_duplicate);
    RUN(MP04_double_spend_mempool);
    RUN(MP05_consensus_fail);
    RUN(MP06_missing_input);
    RUN(MP07_fee_too_low);
    RUN(MP08_multiple_txs);

    printf("\n--- Removal & Block Processing ---\n");
    RUN(MP09_remove_by_txid);
    RUN(MP10_remove_for_block_confirmed);
    RUN(MP11_remove_for_block_conflict);
    RUN(MP12_remove_preserves_others);

    printf("\n--- Block Template ---\n");
    RUN(MP13_template_fee_order);
    RUN(MP14_template_max_txs);
    RUN(MP15_template_empty);
    RUN(MP16_template_total_fees);
    RUN(MP17_template_max_size);

    printf("\n--- Queries & Capacity ---\n");
    RUN(MP18_queries);
    RUN(MP19_is_spent);
    RUN(MP20_totals);
    RUN(MP21_capacity_eviction);
    RUN(MP22_pool_full_reject);

    printf("\n--- Integration ---\n");
    RUN(MP23_clear);
    RUN(MP24_full_lifecycle);
    RUN(MP25_outpoint_reuse_after_remove);

    printf("\n=== Results: %d passed, %d failed out of %d ===\n",
           g_pass, g_fail, g_pass + g_fail);
    return g_fail ? 1 : 0;
}
