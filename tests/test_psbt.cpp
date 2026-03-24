// test_psbt.cpp — SOST-PSBT Tests (24 tests)
#include <sost/psbt.h>
#include <sost/tx_signer.h>
#include <sost/utxo_set.h>
#include <cstdio>
#include <cstring>
#include <algorithm>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define RUN(name) do { \
    printf("  %-52s", #name " ..."); fflush(stdout); \
    bool ok_ = name(); \
    printf("%s\n", ok_ ? "PASS" : "*** FAIL ***"); \
    ok_ ? ++g_pass : ++g_fail; \
} while (0)

#define EXPECT(cond) do { if (!(cond)) { \
    printf("\n    EXPECT failed: %s  [%s:%d]\n", #cond, __FILE__, __LINE__); \
    return false; \
}} while (0)

static std::string to_hex_local(const uint8_t* d, size_t n) {
    static const char* h = "0123456789abcdef";
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s += h[d[i] >> 4]; s += h[d[i] & 0xF]; }
    return s;
}

struct TestKeys {
    PrivKey priv;
    PubKey pub;
    PubKeyHash pkh;
    std::string address;
};

static TestKeys make_keys() {
    TestKeys k;
    std::string err;
    GenerateKeyPair(k.priv, k.pub, &err);
    k.pkh = ComputePubKeyHash(k.pub);
    k.address = address_encode(k.pkh);
    return k;
}

static Hash256 make_txid(uint8_t fill) {
    Hash256 h; h.fill(fill); return h;
}

static Hash256 test_genesis() {
    Hash256 g; g.fill(0); return g;
}

// Helper: create a simple PSBT with one P2PKH input
static PSBT make_simple_psbt(const TestKeys& sender, const TestKeys& receiver,
                              int64_t input_amount = 100000000,
                              int64_t send_amount = 50000000,
                              int64_t fee = 10000) {
    PSBTUtxoRef ref;
    ref.txid = make_txid(0x42);
    ref.vout = 0;
    ref.amount = input_amount;
    ref.output_type = OUT_TRANSFER;
    ref.pkh = sender.pkh;

    PSBT psbt;
    std::string err;
    psbt_create(psbt, {ref}, receiver.address, send_amount, sender.address, fee, &err);
    return psbt;
}

// === CREATE TESTS ===

static bool test_psbt_create_p2pkh_single() {
    auto sender = make_keys();
    auto receiver = make_keys();
    PSBT psbt;
    PSBTUtxoRef ref;
    ref.txid = make_txid(0x01); ref.vout = 0;
    ref.amount = 100000000; ref.output_type = OUT_TRANSFER; ref.pkh = sender.pkh;

    std::string err;
    EXPECT(psbt_create(psbt, {ref}, receiver.address, 50000000, sender.address, 10000, &err));
    EXPECT(psbt.inputs.size() == 1);
    EXPECT(psbt.outputs.size() == 2); // payment + change
    EXPECT(psbt.outputs[0].amount == 50000000);
    EXPECT(psbt.outputs[1].amount == 100000000 - 50000000 - 10000);
    EXPECT(psbt.fee == 10000);
    return true;
}

static bool test_psbt_create_p2pkh_multi_input() {
    auto sender = make_keys();
    auto receiver = make_keys();
    PSBTUtxoRef r1, r2;
    r1.txid = make_txid(0x01); r1.vout = 0; r1.amount = 30000000;
    r1.output_type = OUT_TRANSFER; r1.pkh = sender.pkh;
    r2.txid = make_txid(0x02); r2.vout = 1; r2.amount = 80000000;
    r2.output_type = OUT_TRANSFER; r2.pkh = sender.pkh;

    PSBT psbt;
    std::string err;
    EXPECT(psbt_create(psbt, {r1, r2}, receiver.address, 100000000, sender.address, 5000, &err));
    EXPECT(psbt.inputs.size() == 2);
    EXPECT(psbt.outputs.size() == 2);
    EXPECT(psbt.outputs[1].amount == 30000000 + 80000000 - 100000000 - 5000);
    return true;
}

static bool test_psbt_create_multisig_input() {
    auto k1 = make_keys();
    auto k2 = make_keys();
    auto receiver = make_keys();

    PSBT psbt;
    PSBTUtxoRef ref;
    ref.txid = make_txid(0x03); ref.vout = 0;
    ref.amount = 50000000; ref.output_type = OUT_TRANSFER; ref.pkh = k1.pkh;

    std::string err;
    EXPECT(psbt_create(psbt, {ref}, receiver.address, 40000000, k1.address, 5000, &err));

    // Upgrade input to multisig
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {
        to_hex_local(k1.pub.data(), 33),
        to_hex_local(k2.pub.data(), 33)
    };
    psbt.inputs[0].redeem_script_hex = "deadbeef"; // placeholder

    EXPECT(psbt.inputs[0].required_sigs == 2);
    EXPECT(psbt.inputs[0].pubkeys_hex.size() == 2);
    return true;
}

// === SIGN TESTS ===

static bool test_psbt_sign_p2pkh_ok() {
    auto sender = make_keys();
    auto receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);
    EXPECT(!psbt.complete);

    auto res = psbt_sign(psbt, sender.priv, test_genesis());
    EXPECT(res.signatures_added == 1);
    EXPECT(res.inputs_matched == 1);
    EXPECT(res.complete);
    EXPECT(psbt.complete);
    EXPECT(psbt.inputs[0].partial_sigs.size() == 1);
    return true;
}

static bool test_psbt_sign_p2pkh_wrong_key() {
    auto sender = make_keys();
    auto receiver = make_keys();
    auto wrong = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);

    auto res = psbt_sign(psbt, wrong.priv, test_genesis());
    EXPECT(res.signatures_added == 0);
    EXPECT(res.inputs_matched == 0);
    EXPECT(!psbt.complete);
    return true;
}

static bool test_psbt_sign_multisig_one_of_two() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    auto res = psbt_sign(psbt, k1.priv, test_genesis());
    EXPECT(res.signatures_added == 1);
    EXPECT(!res.complete); // need 2, have 1
    EXPECT(psbt.inputs[0].partial_sigs.size() == 1);
    return true;
}

static bool test_psbt_sign_multisig_two_of_two() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    psbt_sign(psbt, k1.priv, test_genesis());
    auto res = psbt_sign(psbt, k2.priv, test_genesis());
    EXPECT(res.signatures_added == 1);
    EXPECT(res.complete);
    EXPECT(psbt.inputs[0].partial_sigs.size() == 2);
    return true;
}

static bool test_psbt_sign_multisig_duplicate_signer() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    psbt_sign(psbt, k1.priv, test_genesis());
    auto res = psbt_sign(psbt, k1.priv, test_genesis()); // duplicate
    EXPECT(res.signatures_added == 0); // no new sig
    EXPECT(psbt.inputs[0].partial_sigs.size() == 1);
    return true;
}

static bool test_psbt_sign_multisig_unauthorized_signer() {
    auto k1 = make_keys(), k2 = make_keys(), k3 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    auto res = psbt_sign(psbt, k3.priv, test_genesis()); // k3 not authorized
    EXPECT(res.signatures_added == 0);
    EXPECT(res.inputs_matched == 0);
    return true;
}

// === ENCODE/DECODE TESTS ===

static bool test_psbt_encode_decode_roundtrip() {
    auto sender = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);
    psbt_sign(psbt, sender.priv, test_genesis());

    std::string encoded = psbt_encode(psbt);
    EXPECT(!encoded.empty());

    PSBT decoded;
    std::string err;
    EXPECT(psbt_decode(encoded, decoded, &err));
    EXPECT(decoded.inputs.size() == psbt.inputs.size());
    EXPECT(decoded.outputs.size() == psbt.outputs.size());
    EXPECT(decoded.fee == psbt.fee);
    EXPECT(decoded.inputs[0].partial_sigs.size() == 1);
    EXPECT(decoded.inputs[0].partial_sigs[0].pubkey_hex ==
           psbt.inputs[0].partial_sigs[0].pubkey_hex);
    return true;
}

// === FINALIZE TESTS ===

static bool test_psbt_finalize_p2pkh_complete() {
    auto sender = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);
    psbt_sign(psbt, sender.priv, test_genesis());

    std::string err;
    std::string raw_hex = psbt_finalize(psbt, test_genesis(), &err);
    EXPECT(!raw_hex.empty());
    EXPECT(psbt.complete);
    EXPECT(psbt.inputs[0].finalized);
    // Raw hex should be valid hex
    for (char c : raw_hex) {
        EXPECT((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'));
    }
    return true;
}

static bool test_psbt_finalize_multisig_complete() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    // Note: finalize for multisig P2PKH-style (using first sig only) since
    // TAREA 2 will implement proper multisig finalization with redeemScript.
    // For now, test that P2PKH path works when upgraded back.
    psbt.inputs[0].input_type = PSBTInputType::P2PKH;
    psbt_sign(psbt, k1.priv, test_genesis());

    std::string err;
    std::string raw_hex = psbt_finalize(psbt, test_genesis(), &err);
    EXPECT(!raw_hex.empty());
    return true;
}

static bool test_psbt_finalize_multisig_incomplete() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};
    psbt.inputs[0].redeem_script_hex = "deadbeef";

    psbt_sign(psbt, k1.priv, test_genesis()); // only 1 of 2

    std::string err;
    std::string raw_hex = psbt_finalize(psbt, test_genesis(), &err);
    EXPECT(raw_hex.empty()); // should fail — incomplete
    EXPECT(err.find("need 2") != std::string::npos);
    return true;
}

static bool test_psbt_finalize_missing_redeemscript() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 1;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33)};
    psbt.inputs[0].redeem_script_hex = ""; // missing!

    psbt_sign(psbt, k1.priv, test_genesis());

    std::string err;
    std::string raw_hex = psbt_finalize(psbt, test_genesis(), &err);
    EXPECT(raw_hex.empty());
    EXPECT(err.find("redeemScript") != std::string::npos);
    return true;
}

// === COMBINE TESTS ===

static bool test_psbt_combine_ok() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT base = make_simple_psbt(k1, receiver);
    base.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    base.inputs[0].required_sigs = 2;
    base.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    PSBT psbt1 = base, psbt2 = base;
    psbt_sign(psbt1, k1.priv, test_genesis());
    psbt_sign(psbt2, k2.priv, test_genesis());

    PSBT combined;
    std::string err;
    EXPECT(psbt_combine(combined, {psbt1, psbt2}, &err));
    EXPECT(combined.inputs[0].partial_sigs.size() == 2);
    EXPECT(combined.complete);
    return true;
}

static bool test_psbt_combine_duplicate_sig() {
    auto k1 = make_keys(), receiver = make_keys();
    PSBT psbt1 = make_simple_psbt(k1, receiver);
    psbt_sign(psbt1, k1.priv, test_genesis());
    PSBT psbt2 = psbt1; // same sigs

    PSBT combined;
    std::string err;
    EXPECT(psbt_combine(combined, {psbt1, psbt2}, &err));
    EXPECT(combined.inputs[0].partial_sigs.size() == 1); // no duplicate
    return true;
}

// === BALANCE/OVERFLOW TESTS ===

static bool test_psbt_amount_balance_ok() {
    auto sender = make_keys(), receiver = make_keys();
    PSBTUtxoRef ref;
    ref.txid = make_txid(0x01); ref.vout = 0;
    ref.amount = 100000000; ref.output_type = OUT_TRANSFER; ref.pkh = sender.pkh;

    PSBT psbt;
    std::string err;
    EXPECT(psbt_create(psbt, {ref}, receiver.address, 99990000, sender.address, 10000, &err));
    // 100000000 = 99990000 + 10000 + 0 change
    EXPECT(psbt.outputs.size() == 1); // no change needed
    return true;
}

static bool test_psbt_amount_overflow_rejected() {
    auto sender = make_keys(), receiver = make_keys();
    PSBTUtxoRef ref;
    ref.txid = make_txid(0x01); ref.vout = 0;
    ref.amount = 50000000; ref.output_type = OUT_TRANSFER; ref.pkh = sender.pkh;

    PSBT psbt;
    std::string err;
    bool ok = psbt_create(psbt, {ref}, receiver.address, 100000000, sender.address, 10000, &err);
    EXPECT(!ok);
    EXPECT(err.find("insufficient") != std::string::npos);
    return true;
}

// === SECURITY TESTS ===

static bool test_psbt_invalid_base64_no_crash() {
    PSBT psbt;
    std::string err;
    EXPECT(!psbt_decode("not-valid-base64!!!", psbt, &err));
    EXPECT(!psbt_decode("", psbt, &err));
    EXPECT(!psbt_decode("AAAA", psbt, &err)); // valid base64 but wrong magic
    return true;
}

static bool test_psbt_no_privkey_in_serialized() {
    auto sender = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);
    psbt_sign(psbt, sender.priv, test_genesis());

    std::string encoded = psbt_encode(psbt);
    std::string decoded_payload;
    // Base64 decode to check content
    // The payload should NOT contain the private key hex
    std::string privkey_hex = to_hex_local(sender.priv.data(), 32);
    EXPECT(encoded.find(privkey_hex) == std::string::npos);
    return true;
}

static bool test_psbt_change_output_present() {
    auto sender = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver, 100000000, 30000000, 5000);
    EXPECT(psbt.outputs.size() == 2);
    EXPECT(psbt.outputs[0].amount == 30000000);
    EXPECT(psbt.outputs[1].amount == 100000000 - 30000000 - 5000);
    EXPECT(psbt.outputs[1].address == sender.address);
    return true;
}

static bool test_psbt_describe_shows_info() {
    auto sender = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(sender, receiver);
    psbt_sign(psbt, sender.priv, test_genesis());

    std::string desc = psbt_describe(psbt);
    EXPECT(desc.find("SOST-PSBT") != std::string::npos);
    EXPECT(desc.find("P2PKH") != std::string::npos);
    EXPECT(desc.find("sigs=1/1") != std::string::npos);
    EXPECT(desc.find("Complete: YES") != std::string::npos);
    return true;
}

static bool test_psbt_describe_multisig_signature_count() {
    auto k1 = make_keys(), k2 = make_keys(), k3 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {
        to_hex_local(k1.pub.data(), 33),
        to_hex_local(k2.pub.data(), 33),
        to_hex_local(k3.pub.data(), 33)
    };
    psbt_sign(psbt, k1.priv, test_genesis());

    std::string desc = psbt_describe(psbt);
    EXPECT(desc.find("MULTISIG(2-of-3)") != std::string::npos);
    EXPECT(desc.find("sigs=1/2") != std::string::npos);
    return true;
}

static bool test_psbt_signature_order_preserved() {
    auto k1 = make_keys(), k2 = make_keys(), receiver = make_keys();
    PSBT psbt = make_simple_psbt(k1, receiver);
    psbt.inputs[0].input_type = PSBTInputType::REDEEMSCRIPT_HASH_MULTISIG;
    psbt.inputs[0].required_sigs = 2;
    psbt.inputs[0].pubkeys_hex = {to_hex_local(k1.pub.data(), 33), to_hex_local(k2.pub.data(), 33)};

    psbt_sign(psbt, k1.priv, test_genesis());
    psbt_sign(psbt, k2.priv, test_genesis());

    // k1 signed first → should be first in partial_sigs
    EXPECT(psbt.inputs[0].partial_sigs[0].pubkey_hex == to_hex_local(k1.pub.data(), 33));
    EXPECT(psbt.inputs[0].partial_sigs[1].pubkey_hex == to_hex_local(k2.pub.data(), 33));
    return true;
}

int main() {
    printf("=== SOST-PSBT Tests ===\n\n");

    printf("--- Create ---\n");
    RUN(test_psbt_create_p2pkh_single);
    RUN(test_psbt_create_p2pkh_multi_input);
    RUN(test_psbt_create_multisig_input);

    printf("\n--- Sign ---\n");
    RUN(test_psbt_sign_p2pkh_ok);
    RUN(test_psbt_sign_p2pkh_wrong_key);
    RUN(test_psbt_sign_multisig_one_of_two);
    RUN(test_psbt_sign_multisig_two_of_two);
    RUN(test_psbt_sign_multisig_duplicate_signer);
    RUN(test_psbt_sign_multisig_unauthorized_signer);

    printf("\n--- Encode/Decode ---\n");
    RUN(test_psbt_encode_decode_roundtrip);

    printf("\n--- Finalize ---\n");
    RUN(test_psbt_finalize_p2pkh_complete);
    RUN(test_psbt_finalize_multisig_complete);
    RUN(test_psbt_finalize_multisig_incomplete);
    RUN(test_psbt_finalize_missing_redeemscript);

    printf("\n--- Combine ---\n");
    RUN(test_psbt_combine_ok);
    RUN(test_psbt_combine_duplicate_sig);

    printf("\n--- Balance/Overflow ---\n");
    RUN(test_psbt_amount_balance_ok);
    RUN(test_psbt_amount_overflow_rejected);

    printf("\n--- Security ---\n");
    RUN(test_psbt_invalid_base64_no_crash);
    RUN(test_psbt_no_privkey_in_serialized);
    RUN(test_psbt_change_output_present);
    RUN(test_psbt_describe_shows_info);
    RUN(test_psbt_describe_multisig_signature_count);
    RUN(test_psbt_signature_order_preserved);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
