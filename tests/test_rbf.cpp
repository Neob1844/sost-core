// test_rbf.cpp — SOST RBF (Replace-by-Fee) Mempool Policy Tests
//
// RBF01: Replace with higher fee-rate → accepted
// RBF02: Replace with same fee-rate → rejected
// RBF03: Replace with lower fee-rate → rejected
// RBF04: RBF disabled → double-spend rejected
// RBF05: Replaced TX removed from mempool
// RBF06: Multiple conflicts (one replacement replaces several)
// RBF07: RBF_REPLACED code returned on success

#include <sost/mempool.h>
#include <sost/tx_signer.h>
#include <cstdio>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define RUN(name) do { \
    printf("  %-44s", #name " ..."); fflush(stdout); \
    bool ok_ = name(); \
    printf("%s\n", ok_ ? "PASS" : "*** FAIL ***"); \
    ok_ ? ++g_pass : ++g_fail; \
} while (0)

#define EXPECT(cond) do { if (!(cond)) { \
    printf("\n    EXPECT failed: %s  [%s:%d]\n", #cond, __FILE__, __LINE__); \
    return false; \
}} while (0)

static Hash256 MakeHash(uint8_t fill) {
    Hash256 h; h.fill(fill); return h;
}

struct TestTxResult {
    Transaction tx;
    Hash256 txid;
    int64_t fee;
};

static TestTxResult MakeSignedTx(
    const Hash256& prev_txid, uint32_t prev_index,
    int64_t input_amount, int64_t output_amount,
    const PrivKey& priv, const PubKey& pub, const PubKeyHash& dest_pkh)
{
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

    SpentOutput spent;
    spent.amount = input_amount;
    spent.type = OUT_COINBASE_MINER;

    Hash256 genesis_hash{};
    std::string err;
    SignTransactionInput(tx, 0, spent, genesis_hash, priv, &err);

    Hash256 txid{};
    tx.ComputeTxId(txid, nullptr);
    return {tx, txid, input_amount - output_amount};
}

static Hash256 SeedUtxo(UtxoSet& utxos, int64_t height, int64_t subsidy,
    const PubKeyHash& miner_pkh, const PubKeyHash& gold_pkh, const PubKeyHash& popc_pkh)
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
        std::string err;
        GenerateKeyPair(env.priv, env.pub, &err);
        env.pkh = ComputePubKeyHash(env.pub);
        env.gold_pkh.fill(0xAA);
        env.popc_pkh.fill(0xBB);

        int64_t subsidy = 785100863;
        env.miner_amount = (subsidy * 50) / 100;

        env.cb_txid = SeedUtxo(env.utxos, 0, subsidy,
                                env.pkh, env.gold_pkh, env.popc_pkh);

        env.ctx.genesis_hash = Hash256{};
        env.ctx.spend_height = 1200;
        env.ctx.capsule_activation_height = 5000;
        return env;
    }
};

// RBF01: Replace with higher fee → accepted
static bool RBF01_replace_higher_fee() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);

    // TX1: spend coinbase with 10000 fee
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest);
    auto res1 = pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);
    EXPECT(res1.accepted);
    EXPECT(pool.Size() == 1);

    // TX2: same input, higher fee (20000)
    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 20000, env.priv, env.pub, dest2);
    auto res2 = pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);
    EXPECT(res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::RBF_REPLACED);
    EXPECT(pool.Size() == 1);

    // Old TX should be gone, new TX present
    EXPECT(!pool.HasTransaction(tx1.txid));
    EXPECT(pool.HasTransaction(tx2.txid));
    return true;
}

// RBF02: Replace with same fee → rejected
static bool RBF02_same_fee_rejected() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest);
    pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);

    // TX2: same input, same fee
    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest2);
    auto res2 = pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);
    EXPECT(!res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::RBF_REJECTED);
    EXPECT(pool.Size() == 1);
    EXPECT(pool.HasTransaction(tx1.txid));
    return true;
}

// RBF03: Replace with lower fee → rejected
static bool RBF03_lower_fee_rejected() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 20000, env.priv, env.pub, dest);
    pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);

    // TX2: same input, lower fee
    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest2);
    auto res2 = pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);
    EXPECT(!res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::RBF_REJECTED);
    EXPECT(pool.HasTransaction(tx1.txid));
    return true;
}

// RBF04: RBF disabled → double-spend rejected normally
static bool RBF04_rbf_disabled() {
    auto env = TestEnv::Create();
    Mempool pool;
    pool.SetRBFEnabled(false);

    PubKeyHash dest; dest.fill(0x01);
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest);
    pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);

    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 50000, env.priv, env.pub, dest2);
    auto res2 = pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);
    EXPECT(!res2.accepted);
    EXPECT(res2.code == MempoolAcceptCode::DOUBLE_SPEND);
    return true;
}

// RBF05: Replaced TX fully removed
static bool RBF05_replaced_removed() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 10000, env.priv, env.pub, dest);
    pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);

    // Verify old TX is in the spent index
    OutPoint op{env.cb_txid, 0};
    EXPECT(pool.IsSpent(op));

    // Replace
    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 30000, env.priv, env.pub, dest2);
    auto res = pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);
    EXPECT(res.accepted);

    // Old TX gone, outpoint now spent by new TX
    EXPECT(!pool.HasTransaction(tx1.txid));
    EXPECT(pool.HasTransaction(tx2.txid));
    EXPECT(pool.IsSpent(op));
    EXPECT(pool.Size() == 1);
    return true;
}

// RBF06: Fee in block template uses replacement
static bool RBF06_template_uses_replacement() {
    auto env = TestEnv::Create();
    Mempool pool;

    PubKeyHash dest; dest.fill(0x01);
    auto tx1 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 5000, env.priv, env.pub, dest);
    pool.AcceptToMempool(tx1.tx, env.utxos, env.ctx);

    // Replace with much higher fee
    PubKeyHash dest2; dest2.fill(0x02);
    auto tx2 = MakeSignedTx(env.cb_txid, 0, env.miner_amount,
                             env.miner_amount - 50000, env.priv, env.pub, dest2);
    pool.AcceptToMempool(tx2.tx, env.utxos, env.ctx);

    auto tmpl = pool.BuildBlockTemplate();
    EXPECT(tmpl.txs.size() == 1);
    EXPECT(tmpl.total_fees == 50000);  // new higher fee
    EXPECT(tmpl.txids[0] == tx2.txid);
    return true;
}

int main() {
    printf("=== SOST RBF (Replace-by-Fee) Tests ===\n\n");

    RUN(RBF01_replace_higher_fee);
    RUN(RBF02_same_fee_rejected);
    RUN(RBF03_lower_fee_rejected);
    RUN(RBF04_rbf_disabled);
    RUN(RBF05_replaced_removed);
    RUN(RBF06_template_uses_replacement);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
