// Capsule activation as the NODE sees it.
//
// sost-node never sets TxValidationContext::capsule_activation_height, so the
// default member initializer (CAPSULE_ACTIVATION_HEIGHT_BUILD) IS the consensus
// height. This test validates through a default-constructed context — the same
// path as the node — instead of injecting the height by hand.
//
//   normal build (mainnet params):  7349 → REJECT (R14), 7350 → ACCEPT
//   SOST_DEVNET_CAPSULE_FAST build:  299 → REJECT (R14),  300 → ACCEPT
//   both builds: CAPSULE_ACTIVATION_HEIGHT_MAINNET stays 7350 == V12_HEIGHT

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

class MapUtxoView : public IUtxoView {
public:
    std::map<OutPoint, UTXOEntry> db;
    std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override {
        auto it = db.find(op);
        if (it == db.end()) return std::nullopt;
        return it->second;
    }
};

static Hash256 g_genesis{};
static PrivKey g_priv{};
static PubKey  g_pub{};
static PubKeyHash g_pkh{};

// One OUT_TRANSFER carrying `payload`, validated with a DEFAULT context (node path).
static TxValidationResult validate_at(const std::vector<Byte>& payload, int64_t spend_height) {
    TxValidationContext ctx;                 // capsule_activation_height NOT touched
    ctx.genesis_hash = g_genesis;
    ctx.spend_height = spend_height;

    Hash256 prev{}; std::memset(prev.data(), 0x77, 32);
    const int64_t amount = 10000000;
    MapUtxoView utxos;
    UTXOEntry e; e.amount = amount; e.type = OUT_TRANSFER; e.pubkey_hash = g_pkh; e.height = 0; e.is_coinbase = false;
    utxos.db[{prev, 0}] = e;

    Transaction tx; tx.version = 1; tx.tx_type = TX_TYPE_STANDARD;
    TxInput in; in.prev_txid = prev; in.prev_index = 0; tx.inputs.push_back(in);
    TxOutput out; out.amount = amount - 500; out.type = OUT_TRANSFER; out.pubkey_hash = g_pkh; out.payload = payload;
    tx.outputs.push_back(out);
    SpentOutput spent{amount, OUT_TRANSFER};
    std::string err;
    if (!SignTransactionInput(tx, 0, spent, g_genesis, g_priv, &err))
        return TxValidationResult::Fail(TxValCode::R14_PAYLOAD_FORBIDDEN, "sign failed: " + err, -1, -1);
    return ValidateTransactionConsensus(tx, utxos, ctx);
}

int main() {
    std::string err;
    if (!GenerateKeyPair(g_priv, g_pub, &err)) { fprintf(stderr, "keygen: %s\n", err.c_str()); return 2; }
    g_pkh = ComputePubKeyHash(g_pub);
    std::memset(g_genesis.data(), 0xAA, 32);

#if defined(SOST_DEVNET_CAPSULE_FAST)
    const int64_t H = 300;
    printf("\n=== Capsule activation, node context — SOST_DEVNET_CAPSULE_FAST build ===\n");
#else
    const int64_t H = 7350;
    printf("\n=== Capsule activation, node context — normal build (mainnet value) ===\n");
#endif
    printf("CAPSULE_ACTIVATION_HEIGHT_BUILD   = %lld\n", (long long)CAPSULE_ACTIVATION_HEIGHT_BUILD);
    printf("CAPSULE_ACTIVATION_HEIGHT_MAINNET = %lld\n", (long long)CAPSULE_ACTIVATION_HEIGHT_MAINNET);

    TEST("mainnet capsule activation constant is still 7350", CAPSULE_ACTIVATION_HEIGHT_MAINNET == 7350);
    TEST("mainnet capsule activation constant == V12_HEIGHT", CAPSULE_ACTIVATION_HEIGHT_MAINNET == V12_HEIGHT);
    TEST("build activation == expected for this build", CAPSULE_ACTIVATION_HEIGHT_BUILD == H);
    TEST("default TxValidationContext uses the build activation", TxValidationContext{}.capsule_activation_height == H);

    std::vector<Byte> capsule;
    if (!BuildOpenNotePayload("capsule activation boundary", capsule, &err)) { fprintf(stderr, "capsule: %s\n", err.c_str()); return 2; }

    auto before = validate_at(capsule, H - 1);
    auto at     = validate_at(capsule, H);
    auto after  = validate_at(capsule, H + 1);
    auto empty  = validate_at({}, H - 1);
    printf("  h=%lld: %s\n", (long long)(H - 1), before.ok ? "ok" : before.message.c_str());
    printf("  h=%lld: %s\n", (long long)H, at.ok ? "ok" : at.message.c_str());
    TEST("capsule one block BEFORE activation → REJECT R14", !before.ok && before.code == TxValCode::R14_PAYLOAD_FORBIDDEN
         && before.message.find("before capsule activation") != std::string::npos);
    TEST("same capsule AT activation → ACCEPT", at.ok);
    TEST("same capsule one block AFTER activation → ACCEPT", after.ok);
    TEST("no capsule before activation → ACCEPT (gate only affects payloads)", empty.ok);
#if !defined(SOST_DEVNET_CAPSULE_FAST)
    auto at300 = validate_at(capsule, 300);
    TEST("normal build: capsule at 300 → REJECT (fast-devnet height has no effect)", !at300.ok);
#endif

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
