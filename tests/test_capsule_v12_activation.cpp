// V12 capsule activation tests.
//
// V12 hard fork lowers CAPSULE_ACTIVATION_HEIGHT_MAINNET from 10000 to
// V12_HEIGHT (7350). After this height, OUT_TRANSFER outputs may carry
// a non-empty payload (Capsule Protocol v1). Before this height, R14
// rejects any active-type output with a non-empty payload.
//
// Test cases:
//   - spend_height = 7349 + payload non-empty → REJECT (payload forbidden)
//   - spend_height = 7350 + payload non-empty (valid OPEN_NOTE) → ACCEPT
//   - spend_height = 10000 + payload → ACCEPT (forward compat)
//   - empty payload at any height → ACCEPT (no-op gate)
//
// We use a TxValidationContext with explicit capsule_activation_height
// = V12_HEIGHT so the test does not depend on header constants the dev/
// testnet profiles override. This is the same approach used by
// test_capsule_codec.cpp for height-gated semantics.

#include "sost/capsule.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include <cstdio>
#include <cstring>
#include <map>
#include <optional>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// =============================================================================
// Mock UTXO view — minimal in-memory IUtxoView for the consensus path.
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
        db[{txid, index}] = entry;
    }
};

// =============================================================================
// Test keys + helpers
// =============================================================================
static Hash256 g_genesis{};
static PrivKey g_priv{};
static PubKey  g_pub{};
static PubKeyHash g_pkh{};

static Hash256 FakeTxid(uint8_t fill) {
    Hash256 h{}; std::memset(h.data(), fill, 32); return h;
}

// Build a signed tx that consumes a single test UTXO and emits one
// OUT_TRANSFER carrying `payload`. The spend_height + capsule_activation
// drive the gate under test.
static bool make_and_validate(const std::vector<Byte>& payload,
                              int64_t spend_height,
                              int64_t capsule_activation,
                              std::string* err_out)
{
    TxValidationContext ctx;
    ctx.genesis_hash = g_genesis;
    ctx.spend_height = spend_height;
    ctx.capsule_activation_height = capsule_activation;

    Hash256 prev = FakeTxid(0x77);
    int64_t utxo_amount = 10000000; // 0.1 SOST

    MapUtxoView utxos;
    UTXOEntry entry;
    entry.amount = utxo_amount;
    entry.type = OUT_TRANSFER;
    entry.pubkey_hash = g_pkh;
    entry.height = 0;
    entry.is_coinbase = false;
    utxos.Add(prev, 0, entry);

    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;

    TxInput in;
    in.prev_txid = prev;
    in.prev_index = 0;
    tx.inputs.push_back(in);

    TxOutput out;
    out.amount = utxo_amount - 500; // generous fee
    out.type = OUT_TRANSFER;
    out.pubkey_hash = g_pkh;
    out.payload = payload;
    tx.outputs.push_back(out);

    // Sign the only input.
    SpentOutput spent{utxo_amount, OUT_TRANSFER};
    std::string sign_err;
    if (!SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &sign_err)) {
        if (err_out) *err_out = "sign failed: " + sign_err;
        return false;
    }

    auto res = ValidateTransactionConsensus(tx, utxos, ctx);
    if (!res.ok) {
        if (err_out) *err_out = res.message;
        return false;
    }
    return true;
}

// =============================================================================
// Tests
// =============================================================================

static void test_pre_activation_rejects_payload() {
    printf("\n=== 1. Pre-activation (height < V12_HEIGHT) rejects non-empty payload ===\n");

    std::vector<Byte> capsule;
    std::string cerr;
    if (!BuildOpenNotePayload("hi V12", capsule, &cerr)) {
        printf("  *** FAIL: BuildOpenNotePayload setup failed: %s\n", cerr.c_str());
        g_fail++;
        return;
    }

    std::string err;
    bool ok_7349 = make_and_validate(capsule, /*spend_height=*/V12_HEIGHT - 1,
                                     /*capsule_activation=*/V12_HEIGHT, &err);
    TEST("spend_height=7349 + non-empty payload → REJECT (R14 payload forbidden)",
         !ok_7349);
}

static void test_at_activation_accepts_payload() {
    printf("\n=== 2. At V12_HEIGHT accepts non-empty payload ===\n");

    std::vector<Byte> capsule;
    std::string cerr;
    if (!BuildOpenNotePayload("hello V12", capsule, &cerr)) {
        printf("  *** FAIL: BuildOpenNotePayload setup failed: %s\n", cerr.c_str());
        g_fail++;
        return;
    }

    std::string err;
    bool ok_7350 = make_and_validate(capsule, /*spend_height=*/V12_HEIGHT,
                                     /*capsule_activation=*/V12_HEIGHT, &err);
    if (!ok_7350) printf("    rejection reason: %s\n", err.c_str());
    TEST("spend_height=7350 + valid OPEN_NOTE payload → ACCEPT",
         ok_7350);
}

static void test_post_activation_accepts_payload() {
    printf("\n=== 3. Post-activation (height >> V12_HEIGHT) accepts payload ===\n");

    std::vector<Byte> capsule;
    std::string cerr;
    if (!BuildOpenNotePayload("forward compat", capsule, &cerr)) {
        printf("  *** FAIL: BuildOpenNotePayload setup failed: %s\n", cerr.c_str());
        g_fail++;
        return;
    }

    std::string err;
    bool ok_10000 = make_and_validate(capsule, /*spend_height=*/10000,
                                      /*capsule_activation=*/V12_HEIGHT, &err);
    if (!ok_10000) printf("    rejection reason: %s\n", err.c_str());
    TEST("spend_height=10000 + payload → ACCEPT (forward compat)",
         ok_10000);
}

static void test_empty_payload_any_height() {
    printf("\n=== 4. Empty payload at any height — gate is a no-op ===\n");

    std::vector<Byte> empty;

    std::string err1, err2, err3;
    bool ok_pre   = make_and_validate(empty, /*spend_height=*/0,
                                      /*capsule_activation=*/V12_HEIGHT, &err1);
    bool ok_at    = make_and_validate(empty, /*spend_height=*/V12_HEIGHT,
                                      /*capsule_activation=*/V12_HEIGHT, &err2);
    bool ok_post  = make_and_validate(empty, /*spend_height=*/100000,
                                      /*capsule_activation=*/V12_HEIGHT, &err3);

    if (!ok_pre)  printf("    pre  rejection reason: %s\n", err1.c_str());
    if (!ok_at)   printf("    at   rejection reason: %s\n", err2.c_str());
    if (!ok_post) printf("    post rejection reason: %s\n", err3.c_str());

    TEST("empty payload, height=0 (deep pre-activation) → ACCEPT", ok_pre);
    TEST("empty payload, height=V12_HEIGHT exactly → ACCEPT", ok_at);
    TEST("empty payload, height=100000 → ACCEPT", ok_post);
}

// Sanity gate: confirm the production constant matches V12_HEIGHT — the
// fork ships a single height for capsule activation across the codebase.
static void test_constant_pinned_to_v12() {
    printf("\n=== 5. CAPSULE_ACTIVATION_HEIGHT_MAINNET pinned to V12_HEIGHT ===\n");
    TEST("CAPSULE_ACTIVATION_HEIGHT_MAINNET == V12_HEIGHT",
         CAPSULE_ACTIVATION_HEIGHT_MAINNET == V12_HEIGHT);
}

int main() {
    printf("\n=== V12 capsule activation tests ===\n");
    printf("V12_HEIGHT                          = %lld\n", (long long)V12_HEIGHT);
    printf("CAPSULE_ACTIVATION_HEIGHT_MAINNET   = %lld\n",
           (long long)CAPSULE_ACTIVATION_HEIGHT_MAINNET);

    // Init keys once.
    {
        std::string err;
        if (!GenerateKeyPair(g_priv, g_pub, &err)) {
            fprintf(stderr, "FATAL: GenerateKeyPair failed: %s\n", err.c_str());
            return 2;
        }
        g_pkh = ComputePubKeyHash(g_pub);
        std::memset(g_genesis.data(), 0xAA, 32);
    }

    test_constant_pinned_to_v12();
    test_pre_activation_rejects_payload();
    test_at_activation_accepts_payload();
    test_post_activation_accepts_payload();
    test_empty_payload_any_height();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
