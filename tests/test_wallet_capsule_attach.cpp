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

// ---------------------------------------------------------------------------
// 5. Fee-pass regression — multi-pass build on a single-UTXO wallet must
//    not exhaust UTXOs before the final pass settles. Reproduces the
//    sost-cli bug where Wallet::create_transaction marked inputs spent
//    inline, so pass 1 consumed the only UTXO and pass 2 failed with
//    "insufficient funds." The fix is mark_spent=false on every pass plus
//    a single mark_tx_inputs_spent(tx) after broadcast.
// ---------------------------------------------------------------------------
static void test_fee_pass_no_mutation() {
    printf("\n=== 5) Fee-pass regression — single UTXO, 3 passes ===\n");

    // Wallet with EXACTLY one 10-SOST UTXO. Without the fix, pass 1
    // marks it spent and pass 2 immediately fails.
    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);
    auto cap  = build_app_rewards_capsule();
    Hash256 g = mk_genesis();
    const std::string to = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f";

    // Pass 1: mark_spent=false. Estimate fee from raw size.
    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(to, 5 * 100000000LL, /*est_fee=*/1000,
                                   g, tx, /*height=*/2000, &err,
                                   &cap, /*mark_spent=*/false);
    TEST("pass 1 succeeds with mark_spent=false", ok);
    if (!ok) { printf("    err: %s\n", err.c_str()); return; }

    // Pass 2: simulate fee bump (real_fee != est_fee). Same wallet, same
    // UTXO — must still be spendable.
    Transaction tx2;
    bool ok2 = w.create_transaction(to, 5 * 100000000LL, /*real_fee=*/2500,
                                    g, tx2, /*height=*/2000, &err,
                                    &cap, /*mark_spent=*/false);
    TEST("pass 2 succeeds (UTXO still available)", ok2);
    if (!ok2) { printf("    err: %s\n", err.c_str()); return; }

    // Pass 3: simulate one more bump.
    Transaction tx3;
    bool ok3 = w.create_transaction(to, 5 * 100000000LL, /*final_fee=*/3000,
                                    g, tx3, /*height=*/2000, &err,
                                    &cap, /*mark_spent=*/false);
    TEST("pass 3 succeeds (UTXO still available)", ok3);
    if (!ok3) { printf("    err: %s\n", err.c_str()); return; }

    // The final tx must still carry the capsule.
    TEST("final tx output[0] payload matches capsule",
         tx3.outputs[0].payload == cap);

    // Same UTXO selected across all passes (fixed wallet, fixed selector).
    TEST("all three passes selected the same prev_txid",
         tx.inputs[0].prev_txid == tx3.inputs[0].prev_txid &&
         tx.inputs[0].prev_index == tx3.inputs[0].prev_index);

    // Now mark spent explicitly (post-broadcast simulation). After this,
    // a fourth attempt MUST fail — the UTXO is committed.
    w.mark_tx_inputs_spent(tx3);
    Transaction tx4;
    bool ok4 = w.create_transaction(to, 5 * 100000000LL, 1000,
                                    g, tx4, 2000, &err,
                                    &cap, /*mark_spent=*/false);
    TEST("after mark_tx_inputs_spent, next build fails (no UTXOs left)",
         !ok4);
}

// ---------------------------------------------------------------------------
// 6. mark_spent default (true) preserves the old in-line behaviour for
//    one-shot callers — the second build must fail because pass 1 already
//    consumed the wallet's only UTXO.
// ---------------------------------------------------------------------------
static void test_default_mark_spent_still_mutates() {
    printf("\n=== 6) Default mark_spent=true still mutates (back-compat) ===\n");

    Wallet w  = make_funded_wallet(/*funding_stocks=*/10 * 100000000LL);
    Hash256 g = mk_genesis();
    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
        5 * 100000000LL, 1000, g, tx, 2000, &err);
    TEST("first call (default mark_spent=true) succeeds", ok);

    Transaction tx2;
    bool ok2 = w.create_transaction(
        "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f",
        5 * 100000000LL, 1000, g, tx2, 2000, &err);
    TEST("second call fails (UTXO already marked spent in-line)", !ok2);
}

// ---------------------------------------------------------------------------
// 7. --from-pkh source pinning — multi-key wallet, default key empty,
//    secondary key funded. Without from_pkh the build must fail (default
//    has nothing); with from_pkh pointing at the secondary key it must
//    succeed and the change output must return to that same pkh.
// ---------------------------------------------------------------------------
static void test_from_pkh_multi_key_wallet() {
    printf("\n=== 7) --from-pkh: multi-key wallet, secondary key funded ===\n");

    Wallet w;
    auto k_default = w.generate_key("default");
    auto k_phase2  = w.generate_key("phase2-miner");

    // Fund only k_phase2. k_default has nothing.
    WalletUTXO u{};
    Hash256 fake_txid{};
    for (size_t i = 0; i < 32; ++i) fake_txid[i] = (Byte)(0xB0 + (i & 0x0F));
    u.txid        = fake_txid;
    u.vout        = 0;
    u.amount      = 10 * 100000000LL;
    u.pkh         = k_phase2.pkh;
    u.height      = 100;
    u.output_type = 0x00;
    u.spent       = false;
    w.add_utxo(u);

    Hash256 g = mk_genesis();
    const std::string to = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f";

    // Without from_pkh, default behaviour walks unspent and picks any UTXO
    // whose key the wallet holds — k_phase2's UTXO is selectable, so the
    // build SUCCEEDS but the change goes to whichever key was selected
    // first (k_phase2 in this case, since it's the only funded UTXO).
    // This is the historical behaviour we want to keep when no flag is set.
    Transaction tx_no_pin;
    std::string err;
    bool ok_no_pin = w.create_transaction(to, 5 * 100000000LL, 1000,
                                          g, tx_no_pin, 2000, &err,
                                          /*capsule=*/nullptr,
                                          /*mark_spent=*/false,
                                          /*from_pkh=*/nullptr);
    TEST("no from_pkh: build succeeds (UTXO discovered via key holdings)",
         ok_no_pin);

    // Reset spent state and now pin from_pkh = k_phase2.pkh.
    Transaction tx_pinned;
    bool ok_pinned = w.create_transaction(to, 5 * 100000000LL, 1000,
                                          g, tx_pinned, 2000, &err,
                                          /*capsule=*/nullptr,
                                          /*mark_spent=*/false,
                                          /*from_pkh=*/&k_phase2.pkh);
    TEST("from_pkh=k_phase2: build succeeds", ok_pinned);
    if (!ok_pinned) { printf("    err: %s\n", err.c_str()); return; }

    // Change output must return to k_phase2 (NOT k_default).
    if (tx_pinned.outputs.size() >= 2) {
        TEST("change output (output[1]) returns to from_pkh",
             tx_pinned.outputs[1].pubkey_hash == k_phase2.pkh);
        TEST("change output does NOT leak to k_default",
             !(tx_pinned.outputs[1].pubkey_hash == k_default.pkh));
    } else {
        printf("  INFO: no change output (exact-fit selection)\n");
    }

    // Pin to k_default (no funds): build MUST fail.
    Transaction tx_bad;
    bool ok_bad = w.create_transaction(to, 5 * 100000000LL, 1000,
                                       g, tx_bad, 2000, &err,
                                       /*capsule=*/nullptr,
                                       /*mark_spent=*/false,
                                       /*from_pkh=*/&k_default.pkh);
    TEST("from_pkh=k_default (unfunded): build fails", !ok_bad);
}

// ---------------------------------------------------------------------------
// 8. --from-pkh refuses to spend other-key UTXOs even when the wallet
//    holds keys for them. Funds are split: k_a has 4 SOST, k_b has 6 SOST.
//    Asking for 5 SOST from k_a alone must fail (insufficient on that
//    key), even though the wallet TOTAL is 10 SOST. This is the whole
//    point of source pinning — no silent cross-key mixing.
// ---------------------------------------------------------------------------
static void test_from_pkh_refuses_cross_key_mixing() {
    printf("\n=== 8) --from-pkh: refuses cross-key mixing ===\n");

    Wallet w;
    auto k_a = w.generate_key("acct-a");
    auto k_b = w.generate_key("acct-b");

    auto add_utxo = [&](const PubKeyHash& pkh, int64_t amount, Byte tag) {
        WalletUTXO u{};
        Hash256 t{};
        for (size_t i = 0; i < 32; ++i) t[i] = (Byte)(tag + (i & 0x0F));
        u.txid = t; u.vout = 0; u.amount = amount; u.pkh = pkh;
        u.height = 100; u.output_type = 0x00; u.spent = false;
        w.add_utxo(u);
    };
    add_utxo(k_a.pkh, 4 * 100000000LL, 0xC0);
    add_utxo(k_b.pkh, 6 * 100000000LL, 0xD0);

    Hash256 g = mk_genesis();
    const std::string to = "sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f";

    // Need 5 SOST from k_a alone — only 4 available. Must fail even though
    // wallet total is 10 SOST.
    Transaction tx;
    std::string err;
    bool ok = w.create_transaction(to, 5 * 100000000LL, 1000,
                                   g, tx, 2000, &err,
                                   /*capsule=*/nullptr,
                                   /*mark_spent=*/false,
                                   /*from_pkh=*/&k_a.pkh);
    TEST("from_pkh=k_a wanting 5 SOST: fails (k_a only has 4)", !ok);

    // Same amount from k_b: succeeds, and the chosen input is k_b's UTXO.
    Transaction tx2;
    bool ok2 = w.create_transaction(to, 5 * 100000000LL, 1000,
                                    g, tx2, 2000, &err,
                                    /*capsule=*/nullptr,
                                    /*mark_spent=*/false,
                                    /*from_pkh=*/&k_b.pkh);
    TEST("from_pkh=k_b wanting 5 SOST: succeeds", ok2);
    if (ok2) {
        // k_b's UTXO had tag 0xD0 in its txid first byte; verify the
        // selected input matches.
        TEST("input came from k_b's UTXO (not k_a's)",
             tx2.inputs[0].prev_txid[0] == 0xD0);
    }
}

int main() {
    printf("\n=== Wallet → capsule attachment ===\n");
    test_payload_attached_when_supplied();
    test_no_payload_still_works();
    test_empty_payload_treated_as_none();
    test_cert_payload_round_trip();
    test_fee_pass_no_mutation();
    test_default_mark_spent_still_mutates();
    test_from_pkh_multi_key_wallet();
    test_from_pkh_refuses_cross_key_mixing();
    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
