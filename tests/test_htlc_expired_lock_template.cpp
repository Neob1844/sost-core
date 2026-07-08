// =============================================================================
// SOST — V14.7 companion regtest: EXPIRED HTLC LOCK must not poison the template
//
// Reproduces the mainnet incident (13× "[BLOCK] REJECTED: R17: HTLC_LOCK
// refund_height 16259 must be > current height" between blocks 16294–16374) and
// proves the companion fix:
//
//   1. An HTLC LOCK with refund_height R is accepted while the chain is below R.
//   2. When the chain advances past R the lock EXPIRES (consensus R17).
//   3. BEFORE the fix, the block template still carried the expired lock, so
//      every block the miner produced was consensus-rejected (R17).
//   4. AFTER the fix, BuildBlockTemplate(next_height) SKIPS the expired lock
//      (clean block) and RemoveExpiredHtlcLocks() evicts it from the mempool.
//
// Runs on the testnet build (SOST_TESTNET_FORKS): V14_5_HEIGHT=30, V14_7_HEIGHT=40,
// so the relay gate is active at the test heights (1200+).
// =============================================================================

#include <sost/mempool.h>
#include <sost/tx_signer.h>
#include <sost/atomic_swap.h>

#include <cstdio>
#include <array>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        bool ok_ = (cond);                                                   \
        printf("  %-62s %s\n", msg, ok_ ? "PASS" : "*** FAIL ***");          \
        ok_ ? ++g_pass : ++g_fail;                                           \
    } while (0)

// Seed a coinbase and connect it to the UTXO set (spendable after maturity).
static Hash256 SeedUtxo(UtxoSet& utxos, int64_t height, int64_t subsidy,
                        const PubKeyHash& miner_pkh, const PubKeyHash& gold_pkh,
                        const PubKeyHash& popc_pkh) {
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

// Build a signed STANDARD tx whose single output is an OUT_HTLC_LOCK.
static Transaction MakeSignedHtlcLock(const Hash256& prev_txid, uint32_t prev_index,
                                      int64_t input_amount, int64_t output_amount,
                                      const PrivKey& priv, const PubKey& pub,
                                      uint64_t refund_height) {
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
    out.type = OUT_HTLC_LOCK;
    out.pubkey_hash.fill(0);
    std::array<uint8_t, 32> hashlock;   hashlock.fill(0x11);
    std::array<uint8_t, 20> claim_pkh;  claim_pkh.fill(0x22);
    std::array<uint8_t, 20> refund_pkh; refund_pkh.fill(0x33);
    WriteHtlcLockPayload(out.payload, hashlock, refund_height, claim_pkh, refund_pkh);
    tx.outputs.push_back(out);

    SpentOutput spent;
    spent.amount = input_amount;
    spent.type = OUT_COINBASE_MINER;
    Hash256 genesis{};
    std::string err;
    SignTransactionInput(tx, 0, spent, genesis, priv, &err);
    return tx;
}

int main() {
    printf("\n== V14.7 companion — expired HTLC LOCK must not poison the block template ==\n\n");

    // Sanity: on the testnet build the relay gate is active at the test heights.
    CHECK(atomic_swap_relay_active_at(1200), "V14.7 relay gate active at test height 1200");

    // Environment: keypair + a matured coinbase UTXO.
    PrivKey priv; PubKey pub; std::string err;
    GenerateKeyPair(priv, pub, &err);
    PubKeyHash pkh = ComputePubKeyHash(pub), gold, popc;
    gold.fill(0xAA); popc.fill(0xBB);
    int64_t subsidy = 785100863;
    int64_t miner_amt = (subsidy * 50) / 100;
    UtxoSet utxos;
    Hash256 cb_txid = SeedUtxo(utxos, 0, subsidy, pkh, gold, popc);

    const int64_t H_VALID   = 1200;   // chain height while the lock is valid
    const uint64_t REFUND_H = 1210;   // the lock's refund_height
    const int64_t H_EXPIRED = 1215;   // chain height after the lock expired

    // Signed lock spending the coinbase, refund_height 1210.
    Transaction lock = MakeSignedHtlcLock(cb_txid, 0, miner_amt, miner_amt - 100000,
                                          priv, pub, REFUND_H);

    // Context at the valid height (capsule check active at 100, so the lock also
    // exercises the PR#63 relay capsule exemption).
    TxValidationContext ctx;
    ctx.genesis_hash = Hash256{};
    ctx.spend_height = H_VALID;
    ctx.capsule_activation_height = 100;

    // 1) Accept the lock while still valid (refund_height 1210 > height 1200).
    Mempool pool;
    auto res = pool.AcceptToMempool(lock, utxos, ctx);
    CHECK(res.accepted, "lock accepted at height 1200 (refund_height 1210, before expiry)");
    CHECK(pool.Size() == 1, "mempool holds the lock");

    // 2) At the valid height the template correctly includes the lock.
    auto t_valid = pool.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 1000000, H_VALID);
    CHECK(t_valid.txs.size() == 1, "template at 1200 includes the still-valid lock");

    // 3) Chain advances past refund_height -> the lock is now EXPIRED.
    TxValidationContext ctx_exp = ctx;
    ctx_exp.spend_height = H_EXPIRED;

    // 3a) REPRODUCTION of the mainnet bug: the OLD ungated builder (next_height=0
    //     => no expiry filter) keeps the lock in the template, and mining it at
    //     1215 is rejected by consensus R17 — exactly the 13 mainnet rejections.
    auto t_ungated = pool.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 1000000, /*next_height=*/0);
    auto cons = ValidateTransactionConsensus(lock, utxos, ctx_exp);
    CHECK(t_ungated.txs.size() == 1 && !cons.ok &&
          cons.code == TxValCode::R17_HTLC_PAYLOAD_INVALID,
          "REPRO: old builder keeps expired lock -> block REJECTED by R17");

    // 3b) THE FIX: passing next_height=1215 makes the builder SKIP the expired
    //     lock, so the produced block is clean and never rejected.
    auto t_fixed = pool.BuildBlockTemplate(MAX_BLOCK_TX_COUNT, 1000000, H_EXPIRED);
    CHECK(t_fixed.txs.size() == 0, "FIX: template at 1215 skips the expired lock -> clean block");

    // 4) THE FIX (eviction): the stale, un-mineable lock is removed from the pool.
    size_t evicted = pool.RemoveExpiredHtlcLocks(H_EXPIRED);
    CHECK(evicted == 1 && pool.Size() == 0, "FIX: mempool evicts the expired lock");

    // 5) No-op guarantee: before V14.7 the eviction does nothing.
    CHECK(!atomic_swap_relay_active_at(39) && pool.RemoveExpiredHtlcLocks(39) == 0,
          "no-op below V14.7 (relay gate closed)");

    printf("\n  %d passed, %d failed\n\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
