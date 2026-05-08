// Capsule build helpers — public-mode tests.
//
// Covers the two new builders added alongside the V12 capsule wire-up:
//   - BuildTemplateFieldsOpenPayload  (Structured Data, e.g. APP rewards)
//   - BuildCertInstructionPayload     (Certification, e.g. gold cert)
//
// The two existing public builders (BuildOpenNotePayload,
// BuildDocRefOpenPayload) already live in this codebase but had no
// dedicated test file; we add round-trip + adversarial coverage for all
// four here so the public-mode capsule pipeline is fully pinned before
// sost-cli starts producing them.
//
// Each test:
//   1. Builds a payload via the helper.
//   2. Asserts ValidateCapsulePolicy(payload) returns OK — same call the
//      mempool / standardness layer makes on incoming transactions.
//   3. Decodes the header back and verifies field-by-field equivalence.
//   4. Verifies body bytes after the header match the input parameters.
//
// Reject cases pin the boundary conditions (oversize, missing required
// flags / template_id, etc.) so a future change to a Build* helper that
// produces an invalid capsule is caught immediately.

#include "sost/capsule.h"
#include "sost/types.h"

#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

static uint64_t read_u64_le(const Byte* p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) v |= ((uint64_t)p[i]) << (i * 8);
    return v;
}
static uint32_t read_u32_le(const Byte* p) {
    return ((uint32_t)p[0])
         | ((uint32_t)p[1] << 8)
         | ((uint32_t)p[2] << 16)
         | ((uint32_t)p[3] << 24);
}

// =============================================================================
// 1. OPEN_NOTE — already-existing helper, pinned here too
// =============================================================================
static void test_open_note_round_trip() {
    printf("\n=== 1) OPEN_NOTE_INLINE — round-trip ===\n");

    std::string text = "APP rewards distribution batch-001";
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildOpenNotePayload(text, payload, &err);
    TEST("Build returns true on a normal note", ok);
    TEST("ValidateCapsulePolicy accepts the produced payload",
         ValidateCapsulePolicy(payload).ok);

    CapsuleHeader h{};
    TEST("Header decodes", DecodeCapsuleHeader(payload, h, &err));
    TEST("type == OPEN_NOTE_INLINE",
         h.capsule_type == (uint8_t)CapsuleType::OPEN_NOTE_INLINE);
    TEST("flags ENCRYPTED bit clear", (h.flags & CapsuleFlags::ENCRYPTED) == 0);
    TEST("body_len = 1 + text.size()",
         h.body_len == (uint8_t)(1 + text.size()));
    TEST("reserved = 0", h.reserved == 0);

    // Body: text_len(1) + text(N)
    const Byte* body = payload.data() + CAPSULE_HEADER_SIZE;
    TEST("body[0] (text_len) matches text size",
         body[0] == (uint8_t)text.size());
    TEST("body text bytes match input",
         std::memcmp(body + 1, text.data(), text.size()) == 0);
}

static void test_open_note_too_long_rejected() {
    printf("\n=== 1b) OPEN_NOTE_INLINE — oversize text rejected at build time ===\n");
    std::string text(CAPSULE_MAX_BODY, 'x'); // body would be 1 + 243 = 244 > 243
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildOpenNotePayload(text, payload, &err);
    TEST("Build refuses text that would overflow the body cap", !ok);
    TEST("Error message mentions the limit", err.find("too long") != std::string::npos);
}

// =============================================================================
// 2. DOC_REF_OPEN — already-existing helper, pinned here too
// =============================================================================
static void test_doc_ref_round_trip() {
    printf("\n=== 2) DOC_REF_OPEN — round-trip ===\n");

    DocRefParams p{};
    p.capsule_id      = 0x1122334455667788ULL;
    p.file_size_bytes = 4096;
    for (int i = 0; i < 32; ++i) p.file_hash[i]     = (Byte)(0x10 + i);
    for (int i = 0; i < 32; ++i) p.manifest_hash[i] = (Byte)(0x40 + i);
    p.locator_type = LocatorType::IPFS_CID;
    std::string locator = "ipfs://bafyTestCID";
    p.locator_ref.assign(locator.begin(), locator.end());

    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildDocRefOpenPayload(p, payload, &err);
    TEST("Build returns true", ok);
    TEST("ValidateCapsulePolicy accepts the produced payload",
         ValidateCapsulePolicy(payload).ok);

    CapsuleHeader h{};
    TEST("Header decodes", DecodeCapsuleHeader(payload, h, &err));
    TEST("type == DOC_REF_OPEN",
         h.capsule_type == (uint8_t)CapsuleType::DOC_REF_OPEN);
    TEST("locator_type == IPFS_CID",
         h.locator_type == (uint8_t)LocatorType::IPFS_CID);
    TEST("hash_alg == SHA256", h.hash_alg == (uint8_t)HashAlg::SHA256);
    TEST("enc_alg == NONE",   h.enc_alg   == (uint8_t)EncAlg::NONE);

    // Body field-by-field
    const Byte* body = payload.data() + CAPSULE_HEADER_SIZE;
    TEST("capsule_id round-trips",       read_u64_le(body)        == p.capsule_id);
    TEST("file_size_bytes round-trips",  read_u32_le(body + 8)    == p.file_size_bytes);
    TEST("file_hash bytes round-trip",   std::memcmp(body + 12, p.file_hash.data(), 32) == 0);
    TEST("manifest_hash bytes round-trip", std::memcmp(body + 44, p.manifest_hash.data(), 32) == 0);
    TEST("locator_len matches",          body[76] == (uint8_t)locator.size());
    TEST("locator bytes match input",
         std::memcmp(body + 77, locator.data(), locator.size()) == 0);
}

// =============================================================================
// 3. TEMPLATE_FIELDS_OPEN — NEW helper for Structured Data (APP rewards)
// =============================================================================
static void test_template_fields_round_trip() {
    printf("\n=== 3) TEMPLATE_FIELDS_OPEN — round-trip (APP rewards shape) ===\n");

    TemplateFieldsParams p{};
    p.capsule_id  = 0xC0FFEE00C0FFEE01ULL;
    p.template_id = (uint8_t)TemplateId::PAYMENT_RECEIPT_V1;
    p.field_codec = 0x00;  // ASCII
    std::string fields =
        "category=APP rewards distribution; ref=batch-001; period=2026-05; "
        "note=verified settlement";
    p.fields.assign(fields.begin(), fields.end());

    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildTemplateFieldsOpenPayload(p, payload, &err);
    TEST("Build returns true on the canonical APP-rewards shape", ok);
    TEST("ValidateCapsulePolicy accepts the produced payload",
         ValidateCapsulePolicy(payload).ok);

    CapsuleHeader h{};
    TEST("Header decodes", DecodeCapsuleHeader(payload, h, &err));
    TEST("type == TEMPLATE_FIELDS_OPEN",
         h.capsule_type == (uint8_t)CapsuleType::TEMPLATE_FIELDS_OPEN);
    TEST("template_id == PAYMENT_RECEIPT_V1",
         h.template_id  == (uint8_t)TemplateId::PAYMENT_RECEIPT_V1);
    TEST("flags has HAS_TEMPLATE",
         (h.flags & CapsuleFlags::HAS_TEMPLATE) != 0);
    TEST("flags ENCRYPTED bit clear (this is the OPEN variant)",
         (h.flags & CapsuleFlags::ENCRYPTED) == 0);
    TEST("enc_alg == NONE", h.enc_alg == (uint8_t)EncAlg::NONE);
    TEST("body_len = 10 + fields.size()",
         h.body_len == (uint8_t)(10 + p.fields.size()));

    // Body
    const Byte* body = payload.data() + CAPSULE_HEADER_SIZE;
    TEST("capsule_id round-trips", read_u64_le(body) == p.capsule_id);
    TEST("field_codec round-trips", body[8]  == p.field_codec);
    TEST("fields_len matches",      body[9]  == (uint8_t)p.fields.size());
    TEST("fields bytes match input",
         std::memcmp(body + 10, fields.data(), fields.size()) == 0);
}

static void test_template_fields_no_id_rejected() {
    printf("\n=== 3b) TEMPLATE_FIELDS_OPEN — template_id=NONE rejected ===\n");
    TemplateFieldsParams p{};
    p.template_id = (uint8_t)TemplateId::NONE;     // disallowed
    p.fields = {'a','b','c'};
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildTemplateFieldsOpenPayload(p, payload, &err);
    TEST("Build refuses template_id == NONE", !ok);
    TEST("Error message mentions template_id",
         err.find("template_id") != std::string::npos);
}

static void test_template_fields_oversize_rejected() {
    printf("\n=== 3c) TEMPLATE_FIELDS_OPEN — fields > policy max rejected ===\n");
    TemplateFieldsParams p{};
    p.template_id = (uint8_t)TemplateId::CUSTOM_KV_V1;
    p.fields.assign((size_t)CAPSULE_TEMPLATE_MAX_FIELDS + 1, (Byte)'x');
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildTemplateFieldsOpenPayload(p, payload, &err);
    TEST("Build refuses oversize fields blob", !ok);
}

static void test_template_fields_at_policy_max_accepted() {
    printf("\n=== 3d) TEMPLATE_FIELDS_OPEN — fields exactly at policy max accepted ===\n");
    TemplateFieldsParams p{};
    p.template_id = (uint8_t)TemplateId::CUSTOM_KV_V1;
    p.fields.assign((size_t)CAPSULE_TEMPLATE_MAX_FIELDS, (Byte)'a');  // exactly 128
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildTemplateFieldsOpenPayload(p, payload, &err);
    TEST("Build accepts fields_len == policy max", ok);
    TEST("Validator agrees", ValidateCapsulePolicy(payload).ok);
}

// =============================================================================
// 4. CERT_INSTRUCTION — NEW helper for Certification
// =============================================================================
static void test_cert_round_trip() {
    printf("\n=== 4) CERT_INSTRUCTION — round-trip ===\n");

    CertInstructionParams p{};
    p.cert_kind  = 0x01;                       // gold cert (caller-defined)
    p.instr_kind = 0x01;                       // attestation
    p.cert_id    = 0xAABBCCDDEEFF0011ULL;
    p.ref_value  = 0x0102030405060708ULL;
    p.expires_at = 1773600000u;                // some unix time
    p.short_note = "Heritage Reserve cert v1";

    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildCertInstructionPayload(p, payload, &err);
    TEST("Build returns true on a typical cert", ok);
    TEST("ValidateCapsulePolicy accepts the produced payload",
         ValidateCapsulePolicy(payload).ok);

    CapsuleHeader h{};
    TEST("Header decodes", DecodeCapsuleHeader(payload, h, &err));
    TEST("type == CERT_INSTRUCTION",
         h.capsule_type == (uint8_t)CapsuleType::CERT_INSTRUCTION);
    TEST("flags clear", h.flags == 0);
    TEST("body_len = 23 + note.size()",
         h.body_len == (uint8_t)(23 + p.short_note.size()));

    // Body
    const Byte* body = payload.data() + CAPSULE_HEADER_SIZE;
    TEST("cert_kind round-trips",  body[0] == p.cert_kind);
    TEST("instr_kind round-trips", body[1] == p.instr_kind);
    TEST("cert_id round-trips",    read_u64_le(body + 2)  == p.cert_id);
    TEST("ref_value round-trips",  read_u64_le(body + 10) == p.ref_value);
    TEST("expires_at round-trips", read_u32_le(body + 18) == p.expires_at);
    TEST("note_len matches",       body[22] == (uint8_t)p.short_note.size());
    TEST("note bytes match input",
         std::memcmp(body + 23, p.short_note.data(), p.short_note.size()) == 0);
}

static void test_cert_oversize_note_rejected() {
    printf("\n=== 4b) CERT_INSTRUCTION — note > 64 rejected ===\n");
    CertInstructionParams p{};
    p.short_note.assign((size_t)CAPSULE_CERT_MAX_NOTE + 1, 'x');  // 65 bytes
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildCertInstructionPayload(p, payload, &err);
    TEST("Build refuses note > 64", !ok);
}

static void test_cert_empty_note_accepted() {
    printf("\n=== 4c) CERT_INSTRUCTION — empty note accepted (note_len=0) ===\n");
    CertInstructionParams p{};
    p.cert_kind = 0x02;
    p.cert_id   = 0xDEADBEEFCAFEBABEULL;
    // short_note left empty
    std::vector<Byte> payload;
    std::string err;
    bool ok = BuildCertInstructionPayload(p, payload, &err);
    TEST("Build accepts empty note", ok);
    TEST("Validator accepts empty note", ValidateCapsulePolicy(payload).ok);
}

int main() {
    printf("\n=== Capsule build helpers — public modes ===\n");

    test_open_note_round_trip();
    test_open_note_too_long_rejected();

    test_doc_ref_round_trip();

    test_template_fields_round_trip();
    test_template_fields_no_id_rejected();
    test_template_fields_oversize_rejected();
    test_template_fields_at_policy_max_accepted();

    test_cert_round_trip();
    test_cert_oversize_note_rejected();
    test_cert_empty_note_accepted();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
