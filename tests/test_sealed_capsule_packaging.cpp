// Sealed capsule packaging tests (Fase Sealed-1.B).
//
// Pins down the wrappers around the ECIES envelope from 1.A:
//   BuildSealedNotePayload      → type 0x02
//   BuildSealedDocRefPayload    → type 0x04
//   BuildSealedTemplatePayload  → type 0x06
//
// Coverage:
//   1. Each builder produces a payload that round-trips through
//      ValidateCapsulePolicy.
//   2. Header bytes are exactly what the spec requires (magic, version,
//      type, flags, template_id, enc_alg, body_len).
//   3. Envelope < 85 bytes is refused by the builder.
//   4. Envelope > 243 bytes is refused by the builder.
//   5. Sealed-template with template_id == NONE is refused.
//   6. ValidateCapsulePolicy refuses an envelope whose ct_len byte was
//      tampered to be inconsistent with body_len.
//   7. ValidateCapsulePolicy refuses an envelope with version != 1.
//   8. ValidateCapsulePolicy refuses an envelope with recipient_count != 1.
//   9. Existing public-mode capsules (Open Note, Doc Ref Open, Template,
//      Cert) still validate cleanly — no regression on the dispatch.

#include "sost/capsule.h"
#include "sost/sealed_envelope.h"
#include "sost/tx_signer.h"
#include "sost/transaction.h"

#include <secp256k1.h>
#include <openssl/rand.h>

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

struct KeyPair {
    PrivKey    priv;
    PubKey     pub;
    PubKeyHash pkh;
};

static KeyPair gen_keypair() {
    secp256k1_context* ctx = secp256k1_context_create(
        SECP256K1_CONTEXT_SIGN | SECP256K1_CONTEXT_VERIFY);
    KeyPair kp{};
    secp256k1_pubkey pk;
    for (;;) {
        if (RAND_bytes(kp.priv.data(), 32) != 1) std::exit(2);
        if (secp256k1_ec_seckey_verify(ctx, kp.priv.data()) == 1 &&
            secp256k1_ec_pubkey_create(ctx, &pk, kp.priv.data()) == 1) break;
    }
    size_t plen = 33;
    secp256k1_ec_pubkey_serialize(ctx, kp.pub.data(), &plen, &pk,
                                  SECP256K1_EC_COMPRESSED);
    kp.pkh = ComputePubKeyHash(kp.pub);
    secp256k1_context_destroy(ctx);
    return kp;
}

// Helper: build an envelope ready for packaging.
static std::vector<Byte> mk_envelope(const KeyPair& B, const std::string& msg) {
    std::vector<Byte> pt(msg.begin(), msg.end());
    std::vector<Byte> env;
    std::string err;
    if (!SealSingleRecipient(pt,
            std::vector<Byte>(B.pub.begin(), B.pub.end()),
            B.pkh, env, &err)) {
        fprintf(stderr, "mk_envelope failed: %s\n", err.c_str());
        std::exit(2);
    }
    return env;
}

// ---------------------------------------------------------------------------

static void test_sealed_note_roundtrip() {
    printf("\n=== 1) BuildSealedNotePayload + ValidateCapsulePolicy ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "hello B in private");
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildSealedNotePayload(env, payload, &err);
    TEST("BuildSealedNotePayload returns true", ok);
    TEST("payload size = 12 + envelope.size()",
         payload.size() == 12 + env.size());
    TEST("magic 'SC' at offset 0",
         payload[0] == 0x53 && payload[1] == 0x43);
    TEST("capsule_version = 1", payload[2] == 0x01);
    TEST("capsule_type = SEALED_NOTE_INLINE (0x02)", payload[3] == 0x02);
    TEST("flags = ENCRYPTED (0x01)", payload[4] == 0x01);
    TEST("enc_alg = ECIES_SECP256K1_AES256_GCM (0x01)", payload[8] == 0x01);
    TEST("body_len matches envelope", payload[9] == (uint8_t)env.size());

    auto v = ValidateCapsulePolicy(payload);
    TEST("ValidateCapsulePolicy accepts the sealed-note payload",
         v.ok);
    if (!v.ok) printf("    err: %s\n", v.message.c_str());
}

static void test_sealed_doc_ref_roundtrip() {
    printf("\n=== 2) BuildSealedDocRefPayload + ValidateCapsulePolicy ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "private doc-ref body");
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildSealedDocRefPayload(env, payload, &err);
    TEST("BuildSealedDocRefPayload returns true", ok);
    TEST("capsule_type = DOC_REF_SEALED (0x04)", payload[3] == 0x04);
    TEST("flags = ENCRYPTED (0x01)", payload[4] == 0x01);
    TEST("template_id = 0 (no template)", payload[5] == 0x00);
    TEST("ValidateCapsulePolicy accepts the sealed doc-ref payload",
         ValidateCapsulePolicy(payload).ok);
}

static void test_sealed_template_roundtrip() {
    printf("\n=== 3) BuildSealedTemplatePayload + ValidateCapsulePolicy ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B,
        "category=APP rewards; ref=batch-001; period=2026-05");
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildSealedTemplatePayload(
        (uint8_t)TemplateId::PAYMENT_RECEIPT_V1,
        env, payload, &err);
    TEST("BuildSealedTemplatePayload returns true", ok);
    TEST("capsule_type = TEMPLATE_FIELDS_SEALED (0x06)", payload[3] == 0x06);
    TEST("flags = ENCRYPTED|HAS_TEMPLATE (0x11)", payload[4] == 0x11);
    TEST("template_id = PAYMENT_RECEIPT_V1 (0x03)", payload[5] == 0x03);
    TEST("ValidateCapsulePolicy accepts the sealed template payload",
         ValidateCapsulePolicy(payload).ok);
}

static void test_envelope_too_short_rejected() {
    printf("\n=== 4) Envelope < 85 bytes is refused by the builders ===\n");
    std::vector<Byte> tiny(50, 0xAA);
    std::vector<Byte> payload;
    std::string err;
    TEST("BuildSealedNotePayload refuses tiny envelope",
         !BuildSealedNotePayload(tiny, payload, &err));
    TEST("error mentions minimum",
         err.find("minimum") != std::string::npos);
    payload.clear(); err.clear();
    TEST("BuildSealedDocRefPayload refuses tiny envelope",
         !BuildSealedDocRefPayload(tiny, payload, &err));
    payload.clear(); err.clear();
    TEST("BuildSealedTemplatePayload refuses tiny envelope",
         !BuildSealedTemplatePayload(
             (uint8_t)TemplateId::PAYMENT_RECEIPT_V1, tiny, payload, &err));
}

static void test_envelope_too_long_rejected() {
    printf("\n=== 5) Envelope > 243 bytes is refused by the builders ===\n");
    std::vector<Byte> oversized(244, 0xBB);
    std::vector<Byte> payload;
    std::string err;
    TEST("BuildSealedNotePayload refuses oversized envelope",
         !BuildSealedNotePayload(oversized, payload, &err));
    TEST("error mentions maximum",
         err.find("maximum") != std::string::npos);
}

static void test_sealed_template_id_none_rejected() {
    printf("\n=== 6) Sealed template with template_id=NONE is refused ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "x");
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildSealedTemplatePayload(
        (uint8_t)TemplateId::NONE, env, payload, &err);
    TEST("template_id = NONE is rejected", !ok);
    TEST("error mentions NONE",
         err.find("NONE") != std::string::npos);
}

static void test_validator_rejects_ct_len_mismatch() {
    printf("\n=== 7) ValidateCapsulePolicy rejects ct_len mismatch ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "consistent payload");
    std::vector<Byte> payload;
    std::string err;
    BuildSealedNotePayload(env, payload, &err);

    // Tamper ct_len to claim 1 extra byte. Body length stays the same so
    // SEALED_FIXED_OVERHEAD + ct_len != body_len.
    // Body starts at 12; ct_len lives at body offset 67 (= payload offset 79).
    payload[12 + 67] = (uint8_t)((payload[12 + 67] + 1) & 0xFF);

    auto v = ValidateCapsulePolicy(payload);
    TEST("ValidateCapsulePolicy rejects tampered ct_len", !v.ok);
    TEST("error code is SEALED_LEN_MISMATCH",
         v.code == CapsuleValCode::SEALED_LEN_MISMATCH);
}

static void test_validator_rejects_bad_envelope_version() {
    printf("\n=== 8) ValidateCapsulePolicy rejects envelope version != 1 ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "x");
    std::vector<Byte> payload;
    std::string err;
    BuildSealedNotePayload(env, payload, &err);
    payload[12 + 0] = 0x02;   // body[0] = envelope version
    auto v = ValidateCapsulePolicy(payload);
    TEST("rejected", !v.ok);
    TEST("error code is SEALED_BAD_VERSION",
         v.code == CapsuleValCode::SEALED_BAD_VERSION);
}

static void test_validator_rejects_bad_recipient_count() {
    printf("\n=== 9) ValidateCapsulePolicy rejects recipient_count != 1 ===\n");
    KeyPair B = gen_keypair();
    auto env = mk_envelope(B, "x");
    std::vector<Byte> payload;
    std::string err;
    BuildSealedNotePayload(env, payload, &err);
    payload[12 + 1] = 0x02;   // body[1] = recipient_count
    auto v = ValidateCapsulePolicy(payload);
    TEST("rejected", !v.ok);
    TEST("error code is SEALED_BAD_RECIPIENTS",
         v.code == CapsuleValCode::SEALED_BAD_RECIPIENTS);
}

static void test_public_capsules_still_pass() {
    printf("\n=== 10) Public-mode capsules still validate (no regression) ===\n");

    // Open Note.
    {
        std::vector<Byte> payload;
        std::string err;
        TEST("BuildOpenNotePayload OK",
             BuildOpenNotePayload("public memo", payload, &err));
        TEST("ValidateCapsulePolicy accepts open-note",
             ValidateCapsulePolicy(payload).ok);
    }

    // Structured.
    {
        TemplateFieldsParams p{};
        p.capsule_id  = 0;
        p.template_id = (uint8_t)TemplateId::PAYMENT_RECEIPT_V1;
        p.field_codec = 0;
        std::string fields = "category=APP rewards; ref=test";
        p.fields.assign(fields.begin(), fields.end());
        std::vector<Byte> payload;
        std::string err;
        TEST("BuildTemplateFieldsOpenPayload OK",
             BuildTemplateFieldsOpenPayload(p, payload, &err));
        TEST("ValidateCapsulePolicy accepts structured",
             ValidateCapsulePolicy(payload).ok);
    }

    // Cert.
    {
        CertInstructionParams p{};
        p.cert_kind  = 1;
        p.instr_kind = 1;
        p.cert_id    = 0xC0FFEE;
        std::vector<Byte> payload;
        std::string err;
        TEST("BuildCertInstructionPayload OK",
             BuildCertInstructionPayload(p, payload, &err));
        TEST("ValidateCapsulePolicy accepts cert",
             ValidateCapsulePolicy(payload).ok);
    }
}

// ---------------------------------------------------------------------------
// 11-12. CLI-equivalent end-to-end round-trips (Fase Sealed-1.D).
//
// Mirror what `sost-cli send --capsule-mode sealed-note/sealed-structured`
// does: build the cleartext body, ECIES-seal it with the recipient's
// pubkey, wrap the envelope in the SCPv1 header, run ValidateCapsulePolicy
// on the result, and finally decrypt with the recipient's privkey to
// recover the original plaintext.
// ---------------------------------------------------------------------------
static void test_cli_sealed_note_endtoend() {
    printf("\n=== 11) CLI-equivalent sealed-note round-trip ===\n");
    KeyPair B = gen_keypair();

    const std::string text = "private hello — only B should read this";
    std::vector<Byte> plaintext(text.begin(), text.end());

    // 1. Seal.
    std::vector<Byte> envelope;
    std::string err;
    bool ok = SealSingleRecipient(plaintext,
        std::vector<Byte>(B.pub.begin(), B.pub.end()), B.pkh, envelope, &err);
    TEST("SealSingleRecipient succeeds", ok);

    // 2. Wrap.
    std::vector<Byte> payload;
    TEST("BuildSealedNotePayload OK",
         BuildSealedNotePayload(envelope, payload, &err));

    // 3. Mempool-equivalent policy validation.
    auto v = ValidateCapsulePolicy(payload);
    TEST("ValidateCapsulePolicy accepts sealed-note payload", v.ok);

    // 4. Recipient opens the body half (drop the 12-byte SCPv1 header
    //    the way capsule-decrypt does).
    std::vector<Byte> body(payload.begin() + 12, payload.end());
    std::vector<Byte> recovered;
    bool opened = OpenSingleRecipient(body, B.priv, recovered, &err);
    TEST("Recipient privkey recovers plaintext", opened);
    TEST("recovered bytes match plaintext", recovered == plaintext);
}

static void test_cli_sealed_structured_endtoend() {
    printf("\n=== 12) CLI-equivalent sealed-structured round-trip ===\n");
    KeyPair B = gen_keypair();

    // CLI builds the same cleartext body the public TEMPLATE_FIELDS_OPEN
    // uses (capsule_id LE 8 + field_codec 1 + fields_len 1 + fields N).
    const std::string fields_text = "category=APP rewards; ref=test";
    std::vector<Byte> cleartext;
    cleartext.reserve(8 + 1 + 1 + fields_text.size());
    for (int i = 0; i < 8; ++i) cleartext.push_back(0);  // capsule_id = 0
    cleartext.push_back(0x00);                           // field_codec ASCII
    cleartext.push_back((uint8_t)fields_text.size());
    cleartext.insert(cleartext.end(), fields_text.begin(), fields_text.end());

    std::vector<Byte> envelope;
    std::string err;
    TEST("Seal with structured cleartext OK",
         SealSingleRecipient(cleartext,
            std::vector<Byte>(B.pub.begin(), B.pub.end()), B.pkh, envelope, &err));

    std::vector<Byte> payload;
    TEST("BuildSealedTemplatePayload(payment_receipt_v1, env) OK",
         BuildSealedTemplatePayload(
            (uint8_t)TemplateId::PAYMENT_RECEIPT_V1, envelope, payload, &err));
    TEST("template_id survives in the SCPv1 header (offset 5)",
         payload[5] == (uint8_t)TemplateId::PAYMENT_RECEIPT_V1);
    TEST("ValidateCapsulePolicy accepts sealed-structured payload",
         ValidateCapsulePolicy(payload).ok);

    std::vector<Byte> body(payload.begin() + 12, payload.end());
    std::vector<Byte> recovered;
    TEST("Recipient privkey recovers structured cleartext",
         OpenSingleRecipient(body, B.priv, recovered, &err));
    TEST("recovered cleartext matches sender cleartext",
         recovered == cleartext);
    // Decrypted body parses like a public TEMPLATE_FIELDS body.
    TEST("decoded fields_len matches", recovered.size() >= 10 &&
         recovered[9] == (uint8_t)fields_text.size());
}

int main() {
    printf("\n=== Sealed capsule packaging (Fase Sealed-1.B/1.D) ===\n");
    test_sealed_note_roundtrip();
    test_sealed_doc_ref_roundtrip();
    test_sealed_template_roundtrip();
    test_envelope_too_short_rejected();
    test_envelope_too_long_rejected();
    test_sealed_template_id_none_rejected();
    test_validator_rejects_ct_len_mismatch();
    test_validator_rejects_bad_envelope_version();
    test_validator_rejects_bad_recipient_count();
    test_public_capsules_still_pass();
    test_cli_sealed_note_endtoend();
    test_cli_sealed_structured_endtoend();
    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
