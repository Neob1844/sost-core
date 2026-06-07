// =============================================================================
// test_v14_h3_h4.cpp — V14 (block 15000) block-validation hardening semantics
//
// Exercises the building blocks that process_block adopts for height >= V14_HEIGHT:
//   H4  — intra-block chained spends (validate against a SCRATCH UTXO view that
//         already holds earlier same-block outputs) and duplicate-txid rejection.
//   H3  — block acceptance must NOT run relay/mining policy: a consensus-VALID
//         transaction that is merely policy-NONSTANDARD must not be treated as
//         invalid on the block path.
//
// These are pure-library checks (no node/global state), so they run in this dev
// tree. The full process_block height-gating + replay 0..tip is exercised in the
// operator's VPS build pipeline (node binary + chain DB), per the V14 plan.
// =============================================================================

#include "sost/utxo_set.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"

#include <cstring>
#include <iostream>
#include <string>
#include <unordered_set>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { std::cerr << "  FAIL: " << msg << " [" << __LINE__ << "]\n"; ++g_fail; } \
    else { ++g_pass; } \
} while (0)

static PrivKey    g_priv{};
static PubKey     g_pub{};
static PubKeyHash g_pkh{};
static Hash256    g_genesis{};

static void InitKeys() {
    std::string err;
    if (!GenerateKeyPair(g_priv, g_pub, &err)) { std::cerr << "FATAL keygen: " << err << "\n"; std::abort(); }
    g_pkh = ComputePubKeyHash(g_pub);
    std::memset(g_genesis.data(), 0xAA, 32);
}

static UTXOEntry MakeEntry(int64_t amount, int64_t height = 0, bool coinbase = false) {
    UTXOEntry e; e.amount = amount; e.type = OUT_TRANSFER; e.pubkey_hash = g_pkh;
    e.height = height; e.is_coinbase = coinbase; return e;
}

// Signed standard tx spending one UTXO, paying `out_amount` split across n_out outputs.
static Transaction MakeStdTx(const Hash256& prev_txid, uint32_t prev_index,
                             int64_t input_amount, int64_t out_amount, int n_out = 1) {
    Transaction tx; tx.version = 1; tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = prev_txid; in.prev_index = prev_index; tx.inputs.push_back(in);
    int64_t per = out_amount / n_out;
    for (int i = 0; i < n_out; ++i) {
        TxOutput o; o.amount = (i == n_out - 1) ? (out_amount - per * (n_out - 1)) : per;
        o.type = OUT_TRANSFER; o.pubkey_hash = g_pkh; tx.outputs.push_back(o);
    }
    SpentOutput spent{input_amount, OUT_TRANSFER};
    std::string err;
    if (!SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err)) {
        std::cerr << "  FAIL: sign in MakeStdTx: " << err << "\n"; ++g_fail;
    }
    return tx;
}

static TxValidationContext Ctx(int64_t height) {
    TxValidationContext c; c.genesis_hash = g_genesis; c.spend_height = height; return c;
}

int main() {
    InitKeys();
    const int64_t H = 15000;            // V14_HEIGHT
    auto vctx = Ctx(H);

    // ---- H4: intra-block chained spend (tx2 spends an output created by tx1) ----
    {
        Hash256 prev0; std::memset(prev0.data(), 0x11, 32);
        UtxoSet base; std::string e;
        base.AddUTXO({prev0, 0}, MakeEntry(1000000, 0), &e);

        Transaction tx1 = MakeStdTx(prev0, 0, 1000000, 900000);
        Hash256 txid1{}; tx1.ComputeTxId(txid1);

        // Pre-V14 path validates every tx against the pre-block view: tx2 spending
        // tx1's output is REJECTED there (output not yet present). This is exactly
        // the historical behavior the height-gate preserves below V14_HEIGHT.
        Transaction tx2_pre = MakeStdTx(txid1, 0, 900000, 800000);
        auto r_pre = ValidateTransactionConsensus(tx2_pre, base, vctx);
        CHECK(!r_pre.ok, "H4: chained spend against PRE-block view is rejected (historical behavior)");

        // V14 path: validate against a scratch view, connecting tx1 first.
        UtxoSet scratch = base;
        auto r1 = ValidateTransactionConsensus(tx1, scratch, vctx);
        CHECK(r1.ok, std::string("H4: tx1 valid against scratch: ") + r1.message);
        std::vector<UndoEntry> undo; std::string cerr;
        CHECK(scratch.ConnectTransaction(tx1, txid1, H, undo, &cerr),
              std::string("H4: connect tx1 into scratch: ") + cerr);
        Transaction tx2 = MakeStdTx(txid1, 0, 900000, 800000);
        auto r2 = ValidateTransactionConsensus(tx2, scratch, vctx);
        CHECK(r2.ok, std::string("H4: tx2 spends tx1's same-block output against scratch -> VALID: ") + r2.message);
    }

    // ---- H4: duplicate txid within a block is detected ----
    {
        Hash256 prevA; std::memset(prevA.data(), 0x22, 32);
        UtxoSet base; base.AddUTXO({prevA, 0}, MakeEntry(500000, 0));
        Transaction txA = MakeStdTx(prevA, 0, 500000, 400000);
        Hash256 id1{}, id2{};
        txA.ComputeTxId(id1);
        txA.ComputeTxId(id2);
        CHECK(id1 == id2, "H4: identical tx yields identical txid (duplicate is detectable)");
        std::unordered_set<std::string> seen;
        std::string key(reinterpret_cast<const char*>(id1.data()), 32);
        bool first  = seen.insert(key).second;
        bool second = seen.insert(key).second;
        CHECK(first && !second, "H4: dedup set rejects the second occurrence of the same txid");
    }

    // ---- H3: consensus-valid but policy-nonstandard (40 outputs) ----
    // MAX_OUTPUTS_STANDARD = 32 (policy), MAX_OUTPUTS_CONSENSUS = 256 (consensus).
    {
        Hash256 prevB; std::memset(prevB.data(), 0x33, 32);
        UtxoSet base; base.AddUTXO({prevB, 0}, MakeEntry(2000000, 0));
        Transaction txN = MakeStdTx(prevB, 0, 2000000, 1900000, 40);
        auto rc = ValidateTransactionConsensus(txN, base, vctx);
        CHECK(rc.ok, std::string("H3: 40-output tx is consensus-VALID: ") + rc.message);
        auto rp = ValidateTransactionPolicy(txN, base, vctx);
        CHECK(!rp.ok, "H3: same 40-output tx is policy-NONSTANDARD (so it must NOT be run on the block path)");
    }

    std::cout << "\ntest_v14_h3_h4: pass=" << g_pass << " fail=" << g_fail << "\n";
    return g_fail ? 1 : 0;
}
