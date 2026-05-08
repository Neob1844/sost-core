// Wallet → capsule attachment integration test.
//
// Verifies that Wallet::create_transaction(...) honours the new optional
// capsule_payload parameter end-to-end:
//
//   1. The returned Transaction's output[0] (payment) carries the bytes
//      we passed in.
//   2. The change output (output[1] when present) carries an empty payload.
//   3. The attached payload still parses as a valid capsule via the same
//      ValidateCapsulePolicy() path the mempool will run.
//   4. Calling without the payload parameter yields a tx with all outputs'
//      payload empty (backwards-compatibility check — existing callers
//      unchanged).
//   5. Inputs are still signed; the tx's inputs[i].sig field is not empty.
//      (Actual sighash equality is verified by tx_validation tests; here
//      we only confirm signing happened so the tx-builder code path that
//      includes the payload bytes in the sighash was reached.)
//
// We use the canonical "APP rewards distribution" Structured Data shape
// to mirror the user-facing flow that sost-cli will produce.

#include "sost/capsule.h"
#include "sost/wallet.h"
#include "sost/transaction.h"
#include "sost/types.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// Synthetic genesis hash — not validated against any real chain in this
// test; the wallet uses it only as a sighash domain separator.
static Hash256 mk_genesis() {
    Hash256 h{};
    for (size_t i = 0; i < 32; ++i) h[i] = (Byte)(0x10 + i);
    return h;
}

// Build a wallet with one address that already holds enough to fund a
// 5 SOST send + fee. We seed the wallet by importing a private key and
// then injecting a synthetic UTXO via the ledger-import path — see
// existing wallet tests for the same pattern.
static Wallet make_funded_wallet(int64_t funding_stocks) {
    Wallet w;
    // Generate a fresh key (label is informational; default_address()
    // returns keys_[0].address).
    (void)w.generate_key("test-mining");
    auto addr = w.default_address();
    PubKeyHash pkh{};
    if (!address_decode(addr, pkh)) { fprintf(stderr, "address_decode failed\n"); std::exit(2); }

    // Fabricate a synthetic OUT_TRANSFER UTXO. height=100 and the test
    // calls create_transaction with chain_height=2000, so this UTXO is
    // well past the COINBASE_MATURITY window (it's also not coinbase, but
    // the maturity filter is conservative on the safe side).
    WalletUTXO u{};
    Hash256 fake_txid{};
    for (size_t i = 0; i < 32; ++i) fake_txid[i] = (Byte)(0xA0 + (i & 0x0F));
    u.txid        = fake_txid;
    u.vout        = 0;
    u.amount      = funding_stocks;
    u.pkh         = pkh;
    u.height      = 100;
    u.output_type = 0x00;        // OUT_TRANSFER
    u.spent       = false;
    w.add_utxo(u);
    return w;
}

static std::vector<Byte> build_app_rewards_capsule() {
    TemplateFieldsParams p{};
    p.capsule_id  = 0x42;
    p.template_id = (uint8_t)TemplateId::PAYMENT_RECEIPT_V1;
    p.field_codec = 0x00;
    std::string fields = "category=APP rewards distribution; ref=batch-001; period=2026-05";
    p.fields.assign(fields.begin(), fields.end());

    std::vector<Byte> out;
    std::string err;
    if (!BuildTemplateFieldsOpenPayload(p, out, &err)) {
        fprintf(stderr, "build capsule failed: %s\n", err.c_str());
        std::exit(2);
    }
    return out;
}

// ---------------------------------------------------------------------------
// 1. Payload is attached to output[0] when supplied.
// ---------------------------------------------------------------------------
static void test_payload_attached_when_supplied() {
    printf("\n=== 1) Capsule payload attached to payment output ===\n");

    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);  // 10 SOST
    auto cap  = build_app_rewards_capsule();
    Hash256 g = mk_genesis();

    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(
        /*to=*/"sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",  // PoPC pool addr (any valid addr is fine here)
        /*amount=*/5 * 100000000LL,
        /*fee=*/1000,
        g, tx, /*chain_height=*/2000, &err, &cap);
    TEST("create_transaction returns true with payload", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }

    TEST("tx has at least one output", tx.outputs.size() >= 1);
    TEST("output[0] payload size matches input capsule",
         tx.outputs[0].payload.size() == cap.size());
    TEST("output[0] payload bytes match input capsule byte-for-byte",
         std::memcmp(tx.outputs[0].payload.data(), cap.data(), cap.size()) == 0);

    // The change output (when present) MUST NOT carry the payload.
    if (tx.outputs.size() >= 2) {
        TEST("change output (output[1]) has empty payload",
             tx.outputs[1].payload.empty());
    } else {
        printf("  INFO: no change output produced (exact-fit selection)\n");
    }

    // The attached payload still validates as a capsule.
    auto v = ValidateCapsulePolicy(tx.outputs[0].payload);
    TEST("ValidateCapsulePolicy accepts the attached payload", v.ok);

    // Sanity: every input has a non-zero signature. The signature field is
    // a fixed-size array<Byte,64>; "all-zero" would mean the wallet never
    // reached the signing pass, since real ECDSA r and s are non-zero.
    bool all_signed = true;
    for (const auto& in : tx.inputs) {
        bool any = false;
        for (auto b : in.signature) { if (b != 0) { any = true; break; } }
        if (!any) { all_signed = false; break; }
    }
    TEST("every input is signed (signature has non-zero bytes)", all_signed);
}

// ---------------------------------------------------------------------------
// 2. Backwards compatibility: omitting the payload parameter still works,
//    and the produced tx has empty payloads on all outputs.
// ---------------------------------------------------------------------------
static void test_no_payload_still_works() {
    printf("\n=== 2) Backwards compat — calling without payload ===\n");

    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);
    Hash256 g = mk_genesis();
    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
        5 * 100000000LL, 1000, g, tx, 2000, &err);
    TEST("create_transaction works without capsule_payload param", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }

    bool all_empty = true;
    for (const auto& o : tx.outputs) {
        if (!o.payload.empty()) { all_empty = false; break; }
    }
    TEST("all outputs have empty payload (no capsule attached)", all_empty);
}

// ---------------------------------------------------------------------------
// 3. Empty payload pointer is treated as "no payload" (defensive).
// ---------------------------------------------------------------------------
static void test_empty_payload_treated_as_none() {
    printf("\n=== 3) Empty payload pointer behaves like no-payload ===\n");

    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);
    Hash256 g = mk_genesis();
    std::vector<Byte> empty_cap;     // explicitly empty

    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
        5 * 100000000LL, 1000, g, tx, 2000, &err, &empty_cap);
    TEST("create_transaction accepts an empty payload vector", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }
    TEST("output[0] payload is empty", tx.outputs[0].payload.empty());
}

// ---------------------------------------------------------------------------
// 4. Cert capsule path — different builder, same wallet entry point.
// ---------------------------------------------------------------------------
static void test_cert_payload_round_trip() {
    printf("\n=== 4) Cert capsule attached + round-trips ===\n");

    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);
    Hash256 g = mk_genesis();

    CertInstructionParams p{};
    p.cert_kind  = 0x01;
    p.instr_kind = 0x01;
    p.cert_id    = 0xC0FFEE0042ULL;
    p.short_note = "gold cert v1";
    std::vector<Byte> cap;
    std::string err;
    if (!BuildCertInstructionPayload(p, cap, &err)) {
        fprintf(stderr, "cert build failed: %s\n", err.c_str()); std::exit(2);
    }

    Transaction tx;
    bool ok = w.create_transaction(
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
        5 * 100000000LL, 1000, g, tx, 2000, &err, &cap);
    TEST("create_transaction with cert payload OK", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }
    TEST("output[0] payload matches cert capsule",
         tx.outputs[0].payload == cap);
    TEST("ValidateCapsulePolicy accepts attached cert capsule",
         ValidateCapsulePolicy(tx.outputs[0].payload).ok);
}

int main() {
    printf("\n=== Wallet → capsule attachment ===\n");
    test_payload_attached_when_supplied();
    test_no_payload_still_works();
    test_empty_payload_treated_as_none();
    test_cert_payload_round_trip();
    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
