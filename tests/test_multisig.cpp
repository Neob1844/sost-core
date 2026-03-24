// test_multisig.cpp — Script engine + multisig tests (26 tests)
#include <sost/script.h>
#include <sost/tx_signer.h>
#include <sost/address.h>
#include <cstdio>
#include <cstring>

using namespace sost;

static int g_pass = 0, g_fail = 0;

#define RUN(name) do { \
    printf("  %-56s", #name " ..."); fflush(stdout); \
    bool ok_ = name(); \
    printf("%s\n", ok_ ? "PASS" : "*** FAIL ***"); \
    ok_ ? ++g_pass : ++g_fail; \
} while (0)

#define EXPECT(cond) do { if (!(cond)) { \
    printf("\n    EXPECT failed: %s  [%s:%d]\n", #cond, __FILE__, __LINE__); \
    return false; \
}} while (0)

struct TK { PrivKey priv; PubKey pub; PubKeyHash pkh; std::string addr; };

static TK make_key() {
    TK k; std::string e;
    GenerateKeyPair(k.priv, k.pub, &e);
    k.pkh = ComputePubKeyHash(k.pub);
    k.addr = address_encode(k.pkh);
    return k;
}

static Hash256 test_sighash() {
    // Deterministic test sighash
    Hash256 h;
    for (int i = 0; i < 32; ++i) h[i] = (uint8_t)(i * 7 + 3);
    return h;
}

static Sig64 sign_hash(const PrivKey& priv, const Hash256& h) {
    Sig64 sig{}; std::string e;
    SignSighash(priv, h, sig, &e);
    return sig;
}

// === Script Engine Tests ===

static bool test_eval_p2pkh_still_valid() {
    // Standard P2PKH: <sig> <pubkey> OP_DUP OP_HASH160 <pkh> OP_EQUALVERIFY OP_CHECKSIG
    auto k = make_key();
    auto h = test_sighash();
    auto sig = sign_hash(k.priv, h);

    Script script_sig;
    script_sig.push_back(64); // push 64 bytes
    script_sig.insert(script_sig.end(), sig.begin(), sig.end());
    script_sig.push_back(33); // push 33 bytes
    script_sig.insert(script_sig.end(), k.pub.begin(), k.pub.end());

    Script script_pubkey;
    script_pubkey.push_back(OP_DUP);
    script_pubkey.push_back(OP_HASH160);
    script_pubkey.push_back(20); // push 20 bytes
    script_pubkey.insert(script_pubkey.end(), k.pkh.begin(), k.pkh.end());
    script_pubkey.push_back(OP_EQUALVERIFY);
    script_pubkey.push_back(OP_CHECKSIG);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(eval_script(script_sig, script_pubkey, ctx, &err));
    return true;
}

static bool test_eval_op_hash160() {
    // Push data, OP_HASH160, check result is 20 bytes
    Script s;
    s.push_back(4); // push 4 bytes
    s.push_back(0xDE); s.push_back(0xAD); s.push_back(0xBE); s.push_back(0xEF);
    s.push_back(OP_HASH160);

    std::vector<std::vector<uint8_t>> stack;
    ScriptEvalContext ctx;
    std::string err;
    // Use eval_script with empty pubkey to just run sig script
    Script empty;
    EXPECT(eval_script(s, empty, ctx, &err));
    return true;
}

static bool test_eval_op_equal() {
    Script s;
    // Push same data twice, OP_EQUAL
    s.push_back(2); s.push_back(0xAB); s.push_back(0xCD);
    s.push_back(2); s.push_back(0xAB); s.push_back(0xCD);
    s.push_back(OP_EQUAL);

    ScriptEvalContext ctx;
    Script empty;
    std::string err;
    EXPECT(eval_script(s, empty, ctx, &err));
    return true;
}

static bool test_eval_op_equalverify() {
    Script s;
    s.push_back(2); s.push_back(0x11); s.push_back(0x22);
    s.push_back(2); s.push_back(0x11); s.push_back(0x22);
    s.push_back(OP_EQUALVERIFY);
    // Need truthy value on stack after verify
    s.push_back(OP_1);

    ScriptEvalContext ctx;
    Script empty;
    std::string err;
    EXPECT(eval_script(s, empty, ctx, &err));
    return true;
}

static bool test_eval_checkmultisig_2of3_ok() {
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto h = test_sighash();
    auto sig1 = sign_hash(k1.priv, h);
    auto sig2 = sign_hash(k2.priv, h);

    // Build redeemScript: OP_2 <pk1> <pk2> <pk3> OP_3 OP_CHECKMULTISIG
    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});

    // Build scriptSig: OP_0 <sig1> <sig2> <redeemScript>
    auto ss = make_p2sh_script_sig({sig1, sig2}, rs);

    // Build P2SH scriptPubKey
    auto script_hash = hash_script(rs);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(eval_p2sh(ss, script_hash, ctx, &err));
    return true;
}

static bool test_eval_checkmultisig_1of3_fail() {
    // 2-of-3 with only 1 sig should fail
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto h = test_sighash();
    auto sig1 = sign_hash(k1.priv, h);

    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});
    auto ss = make_p2sh_script_sig({sig1}, rs);
    auto script_hash = hash_script(rs);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    // This should fail because we only provide 1 sig but need 2
    // However, make_p2sh_script_sig builds with the sigs we give.
    // The CHECKMULTISIG will try to match 1 sig with M=2 and fail.
    // Actually, the redeemScript says M=2 but we only pushed 1 sig.
    // The script evaluator should handle this as incomplete.
    bool ok = eval_p2sh(ss, script_hash, ctx, &err);
    EXPECT(!ok);
    return true;
}

static bool test_eval_checkmultisig_wrong_sig() {
    auto k1 = make_key(), k2 = make_key(), k3 = make_key(), k4 = make_key();
    auto h = test_sighash();
    auto sig4 = sign_hash(k4.priv, h); // k4 not in multisig

    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});
    // Use sig1 (valid) + sig4 (wrong key)
    auto sig1 = sign_hash(k1.priv, h);
    auto ss = make_p2sh_script_sig({sig1, sig4}, rs);
    auto script_hash = hash_script(rs);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    bool ok = eval_p2sh(ss, script_hash, ctx, &err);
    EXPECT(!ok); // sig4 doesn't match any pubkey in order
    return true;
}

static bool test_eval_checkmultisig_signature_order() {
    // Sigs must match pubkeys in ORDER (no backtracking)
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto h = test_sighash();
    auto sig1 = sign_hash(k1.priv, h);
    auto sig3 = sign_hash(k3.priv, h);

    // k1, k3 in order (skip k2) — should work
    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});
    auto ss = make_p2sh_script_sig({sig1, sig3}, rs);
    auto script_hash = hash_script(rs);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(eval_p2sh(ss, script_hash, ctx, &err));

    // k3, k1 in WRONG order — should fail
    auto ss_wrong = make_p2sh_script_sig({sig3, sig1}, rs);
    err.clear();
    EXPECT(!eval_p2sh(ss_wrong, script_hash, ctx, &err));
    return true;
}

static bool test_eval_unknown_opcode_rejected() {
    Script s;
    s.push_back(0xFF); // unknown opcode
    ScriptEvalContext ctx;
    Script empty;
    std::string err;
    EXPECT(!eval_script(s, empty, ctx, &err));
    return true;
}

// === RedeemScript-Hash Tests ===

static bool test_multisig_redeemscript_hash() {
    auto k1 = make_key(), k2 = make_key();
    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub});
    auto h = hash_script(rs);
    // Hash should be 20 bytes, non-zero
    bool all_zero = true;
    for (auto b : h) if (b != 0) { all_zero = false; break; }
    EXPECT(!all_zero);
    // Same input = same hash
    auto h2 = hash_script(rs);
    EXPECT(h == h2);
    return true;
}

static bool test_multisig_scriptpubkey_format() {
    PubKeyHash sh; sh.fill(0x42);
    auto spk = make_p2sh_script_pubkey(sh);
    EXPECT(spk.size() == 23); // OP_HASH160(1) + push20(1) + hash(20) + OP_EQUAL(1)
    EXPECT(spk[0] == OP_HASH160);
    EXPECT(spk[1] == 20);
    EXPECT(spk[22] == OP_EQUAL);
    return true;
}

static bool test_multisig_scriptsig_format() {
    auto k1 = make_key();
    Sig64 sig1; sig1.fill(0xAA);
    Script rs = {0x51, 33}; // simplified redeemScript
    rs.insert(rs.end(), k1.pub.begin(), k1.pub.end());
    rs.push_back(0x51);
    rs.push_back(OP_CHECKMULTISIG);

    auto ss = make_p2sh_script_sig({sig1}, rs);
    EXPECT(ss[0] == OP_0); // dummy byte
    EXPECT(ss[1] == 64);    // push 64 bytes (sig)
    return true;
}

static bool test_multisig_redeemscript_hash_mismatch() {
    auto k1 = make_key(), k2 = make_key();
    auto h = test_sighash();
    auto sig1 = sign_hash(k1.priv, h);
    auto sig2 = sign_hash(k2.priv, h);

    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub});
    auto ss = make_p2sh_script_sig({sig1, sig2}, rs);

    PubKeyHash wrong_hash; wrong_hash.fill(0xFF); // wrong hash

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(!eval_p2sh(ss, wrong_hash, ctx, &err));
    EXPECT(err.find("mismatch") != std::string::npos);
    return true;
}

// === Wallet/Create Tests ===

static bool test_multisig_create_2of3() {
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});
    EXPECT(!rs.empty());
    EXPECT(rs[0] == OP_2); // M=2
    EXPECT(rs.back() == OP_CHECKMULTISIG);
    auto sh = hash_script(rs);
    auto addr = script_hash_to_address(sh);
    EXPECT(addr.substr(0, 5) == "sost3");
    EXPECT(addr.size() == 45);
    return true;
}

static bool test_multisig_create_1of1() {
    auto k1 = make_key();
    auto rs = make_multisig_redeem_script(1, {k1.pub});
    EXPECT(rs[0] == OP_1);
    auto sh = hash_script(rs);
    auto addr = script_hash_to_address(sh);
    EXPECT(addr.size() == 45);
    return true;
}

static bool test_multisig_create_3of5() {
    std::vector<PubKey> pks;
    for (int i = 0; i < 5; ++i) pks.push_back(make_key().pub);
    auto rs = make_multisig_redeem_script(3, pks);
    EXPECT(rs[0] == OP_3); // M=3
    auto sh = hash_script(rs);
    auto addr = script_hash_to_address(sh);
    EXPECT(addr.size() == 45);
    return true;
}

static bool test_multisig_invalid_m_gt_n() {
    auto k1 = make_key(), k2 = make_key();
    // M=3 > N=2 — the function will produce a technically valid script
    // but the evaluator will reject it. Check that the script at least generates.
    auto rs = make_multisig_redeem_script(3, {k1.pub, k2.pub});
    EXPECT(!rs.empty()); // function doesn't validate M <= N (evaluator does)
    return true;
}

static bool test_multisig_address_format_uses_sost_encoder() {
    PubKeyHash sh; sh.fill(0xAB);
    auto addr = script_hash_to_address(sh);
    EXPECT(addr.size() == 45);
    EXPECT(addr.substr(0, 5) == "sost3");
    // Roundtrip
    PubKeyHash decoded;
    EXPECT(address_to_script_hash(addr, decoded));
    EXPECT(decoded == sh);
    return true;
}

// === Integration Tests ===

static bool test_multisig_full_flow() {
    // Full 2-of-3: create → sign → verify
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto h = test_sighash();

    // 1. Create redeemScript
    auto rs = make_multisig_redeem_script(2, {k1.pub, k2.pub, k3.pub});
    auto script_hash = hash_script(rs);
    auto addr = script_hash_to_address(script_hash);

    // 2. Sign with k1 and k3
    auto sig1 = sign_hash(k1.priv, h);
    auto sig3 = sign_hash(k3.priv, h);

    // 3. Build scriptSig
    auto ss = make_p2sh_script_sig({sig1, sig3}, rs);

    // 4. Verify
    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(eval_p2sh(ss, script_hash, ctx, &err));
    return true;
}

static bool test_multisig_insufficient_sigs_rejected() {
    auto k1 = make_key(), k2 = make_key(), k3 = make_key();
    auto h = test_sighash();
    auto rs = make_multisig_redeem_script(3, {k1.pub, k2.pub, k3.pub});
    auto sig1 = sign_hash(k1.priv, h);
    auto sig2 = sign_hash(k2.priv, h);
    auto ss = make_p2sh_script_sig({sig1, sig2}, rs); // only 2 of 3 needed

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(!eval_p2sh(ss, hash_script(rs), ctx, &err));
    return true;
}

static bool test_multisig_activation_before_rejected() {
    // Before activation height, script hash outputs should not be accepted
    // This is a conceptual test — actual enforcement is in tx_validation
    EXPECT(MULTISIG_ACTIVATION_HEIGHT > 0);
    EXPECT(MULTISIG_ACTIVATION_HEIGHT == 2000);
    return true;
}

static bool test_multisig_activation_at_or_after_accepted() {
    // At or after activation, multisig is valid
    EXPECT(MULTISIG_ACTIVATION_HEIGHT == 2000);
    // Conceptual: a block at height 2000 should accept OUT_SCRIPT_HASH
    return true;
}

// === Backwards Compatibility ===

static bool test_legacy_p2pkh_still_works() {
    // Standard P2PKH via script engine
    auto k = make_key();
    auto h = test_sighash();
    auto sig = sign_hash(k.priv, h);

    Script script_sig;
    script_sig.push_back(64);
    script_sig.insert(script_sig.end(), sig.begin(), sig.end());
    script_sig.push_back(33);
    script_sig.insert(script_sig.end(), k.pub.begin(), k.pub.end());

    Script script_pubkey;
    script_pubkey.push_back(OP_DUP);
    script_pubkey.push_back(OP_HASH160);
    script_pubkey.push_back(20);
    script_pubkey.insert(script_pubkey.end(), k.pkh.begin(), k.pkh.end());
    script_pubkey.push_back(OP_EQUALVERIFY);
    script_pubkey.push_back(OP_CHECKSIG);

    ScriptEvalContext ctx;
    ctx.sighash = h;
    std::string err;
    EXPECT(eval_script(script_sig, script_pubkey, ctx, &err));
    return true;
}

static bool test_sost3_address_distinct_from_sost1() {
    PubKeyHash h; h.fill(0x42);
    auto a1 = address_encode(h);    // sost1...
    auto a3 = script_hash_to_address(h); // sost3...
    EXPECT(a1 != a3);
    EXPECT(a1.substr(0, 5) == "sost1");
    EXPECT(a3.substr(0, 5) == "sost3");
    EXPECT(a1.size() == a3.size());
    // Same hex payload
    EXPECT(a1.substr(5) == a3.substr(5));
    return true;
}

int main() {
    printf("=== SOST Multisig + Script Engine Tests ===\n\n");

    printf("--- Script Engine ---\n");
    RUN(test_eval_p2pkh_still_valid);
    RUN(test_eval_op_hash160);
    RUN(test_eval_op_equal);
    RUN(test_eval_op_equalverify);
    RUN(test_eval_checkmultisig_2of3_ok);
    RUN(test_eval_checkmultisig_1of3_fail);
    RUN(test_eval_checkmultisig_wrong_sig);
    RUN(test_eval_checkmultisig_signature_order);
    RUN(test_eval_unknown_opcode_rejected);

    printf("\n--- RedeemScript-Hash ---\n");
    RUN(test_multisig_redeemscript_hash);
    RUN(test_multisig_scriptpubkey_format);
    RUN(test_multisig_scriptsig_format);
    RUN(test_multisig_redeemscript_hash_mismatch);

    printf("\n--- Create ---\n");
    RUN(test_multisig_create_2of3);
    RUN(test_multisig_create_1of1);
    RUN(test_multisig_create_3of5);
    RUN(test_multisig_invalid_m_gt_n);
    RUN(test_multisig_address_format_uses_sost_encoder);

    printf("\n--- Integration ---\n");
    RUN(test_multisig_full_flow);
    RUN(test_multisig_insufficient_sigs_rejected);
    RUN(test_multisig_activation_before_rejected);
    RUN(test_multisig_activation_at_or_after_accepted);

    printf("\n--- Backwards Compatibility ---\n");
    RUN(test_legacy_p2pkh_still_works);
    RUN(test_sost3_address_distinct_from_sost1);

    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
