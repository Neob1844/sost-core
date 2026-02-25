// =============================================================================
// capsule.cpp — SOST Capsule Protocol v1 (SCPv1)
// Encode, decode, and validate capsule payloads.
// =============================================================================

#include "sost/capsule.h"
#include <cstring>

namespace sost {

// =============================================================================
// DecodeCapsuleHeader
// =============================================================================

bool DecodeCapsuleHeader(
    const std::vector<Byte>& payload,
    CapsuleHeader& out_header,
    std::string* err)
{
    if (payload.size() < CAPSULE_HEADER_SIZE) {
        if (err) *err = "payload too short for capsule header ("
                        + std::to_string(payload.size()) + " < 12)";
        return false;
    }

    // Check magic
    if (payload[0] != CAPSULE_MAGIC_0 || payload[1] != CAPSULE_MAGIC_1) {
        if (err) *err = "bad capsule magic (expected 0x5343)";
        return false;
    }

    out_header.capsule_version = payload[2];
    out_header.capsule_type    = payload[3];
    out_header.flags           = payload[4];
    out_header.template_id     = payload[5];
    out_header.locator_type    = payload[6];
    out_header.hash_alg        = payload[7];
    out_header.enc_alg         = payload[8];
    out_header.body_len        = payload[9];
    out_header.reserved        = (uint16_t)(payload[10]) | ((uint16_t)(payload[11]) << 8);

    return true;
}

// =============================================================================
// EncodeCapsuleHeader
// =============================================================================

void EncodeCapsuleHeader(
    const CapsuleHeader& h,
    std::vector<Byte>& out)
{
    out.push_back(CAPSULE_MAGIC_0);
    out.push_back(CAPSULE_MAGIC_1);
    out.push_back(h.capsule_version);
    out.push_back(h.capsule_type);
    out.push_back(h.flags);
    out.push_back(h.template_id);
    out.push_back(h.locator_type);
    out.push_back(h.hash_alg);
    out.push_back(h.enc_alg);
    out.push_back(h.body_len);
    out.push_back((uint8_t)(h.reserved & 0xFF));
    out.push_back((uint8_t)((h.reserved >> 8) & 0xFF));
}

// =============================================================================
// ValidateCapsuleHeader
// =============================================================================

CapsuleValResult ValidateCapsuleHeader(const std::vector<Byte>& payload) {
    if (payload.size() < CAPSULE_HEADER_SIZE) {
        return CapsuleValResult::Fail(CapsuleValCode::PAYLOAD_TOO_SHORT,
            "payload " + std::to_string(payload.size()) + " < header 12");
    }

    if (payload.size() > 255) {
        return CapsuleValResult::Fail(CapsuleValCode::PAYLOAD_TOO_LONG,
            "payload " + std::to_string(payload.size()) + " > 255");
    }

    // Magic
    if (payload[0] != CAPSULE_MAGIC_0 || payload[1] != CAPSULE_MAGIC_1) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_MAGIC,
            "expected magic 'SC' (0x53,0x43)");
    }

    // Version
    if (payload[2] != CAPSULE_VERSION_1) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_VERSION,
            "unsupported capsule version " + std::to_string(payload[2]));
    }

    // Capsule type — must be standard for policy
    if (!IsStandardCapsuleType(payload[3])) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_CAPSULE_TYPE,
            "non-standard capsule_type 0x" + HexStr(&payload[3], 1));
    }

    // body_len must match actual remaining bytes
    uint8_t body_len = payload[9];
    size_t expected_total = CAPSULE_HEADER_SIZE + body_len;
    if (payload.size() != expected_total) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_BODY_LEN,
            "body_len=" + std::to_string(body_len) +
            " implies total=" + std::to_string(expected_total) +
            " but payload=" + std::to_string(payload.size()));
    }

    // Reserved must be zero
    uint16_t reserved = (uint16_t)(payload[10]) | ((uint16_t)(payload[11]) << 8);
    if (reserved != 0) {
        return CapsuleValResult::Fail(CapsuleValCode::RESERVED_NONZERO,
            "reserved field must be 0x0000");
    }

    // Reserved flag bits (6,7) must not be set in v1
    uint8_t flags = payload[4];
    if (flags & ~CapsuleFlags::V1_ALLOWED_MASK) {
        return CapsuleValResult::Fail(CapsuleValCode::RESERVED_FLAGS,
            "reserved flag bits set in v1");
    }

    return CapsuleValResult::Ok();
}

// =============================================================================
// ValidateCapsuleBody — per-type policy checks
// =============================================================================

static CapsuleValResult ValidateOpenNoteBody(
    const CapsuleHeader& h, const Byte* body, size_t body_len)
{
    // OPEN_NOTE body: text_len(1) + text(N)
    if (body_len < 1) {
        return CapsuleValResult::Fail(CapsuleValCode::NOTE_TOO_LONG,
            "OPEN_NOTE body too short");
    }

    uint8_t text_len = body[0];
    if ((size_t)(1 + text_len) != body_len) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_BODY_LEN,
            "OPEN_NOTE text_len=" + std::to_string(text_len) +
            " mismatches body_len=" + std::to_string(body_len));
    }

    // flags.ENCRYPTED must be 0
    if (h.flags & CapsuleFlags::ENCRYPTED) {
        return CapsuleValResult::Fail(CapsuleValCode::SEALED_NOT_ENCRYPTED,
            "OPEN_NOTE must not have ENCRYPTED flag");
    }

    // Policy: text_len <= 80
    if (text_len > CAPSULE_OPEN_NOTE_MAX_TEXT) {
        return CapsuleValResult::Fail(CapsuleValCode::NOTE_TOO_LONG,
            "OPEN_NOTE text_len=" + std::to_string(text_len) +
            " exceeds policy max " + std::to_string(CAPSULE_OPEN_NOTE_MAX_TEXT));
    }

    return CapsuleValResult::Ok();
}

static bool IsHashZero(const Byte* data, size_t len) {
    for (size_t i = 0; i < len; ++i)
        if (data[i] != 0) return false;
    return true;
}

static CapsuleValResult ValidateDocRefBody(
    const CapsuleHeader& h, const Byte* body, size_t body_len, bool sealed)
{
    // DOC_REF body: capsule_id(8) + file_size(4) + file_hash(32)
    //             + manifest_hash(32) + locator_len(1) + locator(N)
    // Minimum: 8+4+32+32+1 = 77 bytes (locator_len=0)
    if (body_len < 77) {
        return CapsuleValResult::Fail(CapsuleValCode::DOC_BODY_TOO_SHORT,
            "DOC_REF body " + std::to_string(body_len) + " < minimum 77");
    }

    // file_hash at offset 12 (relative to body start)
    const Byte* file_hash = body + 12;
    if (IsHashZero(file_hash, 32)) {
        return CapsuleValResult::Fail(CapsuleValCode::DOC_ZERO_HASH,
            "DOC_REF file_hash is all zeros");
    }

    // locator_len at offset 76
    uint8_t locator_len = body[76];
    if ((size_t)(77 + locator_len) != body_len) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_BODY_LEN,
            "DOC_REF locator_len=" + std::to_string(locator_len) +
            " mismatches body");
    }

    // Policy: locator_len <= 96
    if (locator_len > CAPSULE_DOC_REF_MAX_LOCATOR) {
        return CapsuleValResult::Fail(CapsuleValCode::DOC_LOCATOR_TOO_LONG,
            "DOC_REF locator_len=" + std::to_string(locator_len) +
            " exceeds policy max " + std::to_string(CAPSULE_DOC_REF_MAX_LOCATOR));
    }

    // Sealed mode: must have ENCRYPTED flag and enc_alg != NONE
    if (sealed) {
        if (!(h.flags & CapsuleFlags::ENCRYPTED)) {
            return CapsuleValResult::Fail(CapsuleValCode::SEALED_NOT_ENCRYPTED,
                "DOC_REF_SEALED must have ENCRYPTED flag");
        }
        if (h.enc_alg == (uint8_t)EncAlg::NONE) {
            return CapsuleValResult::Fail(CapsuleValCode::SEALED_NOT_ENCRYPTED,
                "DOC_REF_SEALED enc_alg must not be NONE");
        }
    }

    // hash_alg must be supported
    if (h.hash_alg != (uint8_t)HashAlg::SHA256 &&
        h.hash_alg != (uint8_t)HashAlg::BLAKE3) {
        return CapsuleValResult::Fail(CapsuleValCode::DOC_ZERO_HASH,
            "DOC_REF unsupported hash_alg");
    }

    return CapsuleValResult::Ok();
}

static CapsuleValResult ValidateTemplateBody(
    const CapsuleHeader& h, const Byte* body, size_t body_len, bool sealed)
{
    // TEMPLATE_FIELDS body: capsule_id(8) + field_codec(1) + fields_len(1) + fields(N)
    if (body_len < 10) {
        return CapsuleValResult::Fail(CapsuleValCode::TEMPLATE_BODY_SHORT,
            "TEMPLATE body too short");
    }

    // template_id must not be NONE
    if (h.template_id == (uint8_t)TemplateId::NONE) {
        return CapsuleValResult::Fail(CapsuleValCode::TEMPLATE_NO_ID,
            "TEMPLATE_FIELDS requires template_id != NONE");
    }

    // HAS_TEMPLATE flag must be set
    if (!(h.flags & CapsuleFlags::HAS_TEMPLATE)) {
        return CapsuleValResult::Fail(CapsuleValCode::TEMPLATE_NO_FLAG,
            "TEMPLATE_FIELDS requires HAS_TEMPLATE flag");
    }

    // fields_len at offset 9
    uint8_t fields_len = body[9];
    if ((size_t)(10 + fields_len) != body_len) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_BODY_LEN,
            "TEMPLATE fields_len mismatch");
    }

    // Policy: fields_len <= 128
    if (fields_len > CAPSULE_TEMPLATE_MAX_FIELDS) {
        return CapsuleValResult::Fail(CapsuleValCode::TEMPLATE_BODY_SHORT,
            "TEMPLATE fields_len=" + std::to_string(fields_len) + " exceeds max");
    }

    if (sealed) {
        if (!(h.flags & CapsuleFlags::ENCRYPTED)) {
            return CapsuleValResult::Fail(CapsuleValCode::SEALED_NOT_ENCRYPTED,
                "TEMPLATE_SEALED must have ENCRYPTED flag");
        }
    }

    return CapsuleValResult::Ok();
}

static CapsuleValResult ValidateCertInstructionBody(
    const CapsuleHeader& h, const Byte* body, size_t body_len)
{
    // CERT_INSTRUCTION body:
    // cert_kind(1) + instr_kind(1) + cert_id(8) + ref_value(8)
    // + expires_at(4) + note_len(1) + short_note(N)
    // Minimum = 1+1+8+8+4+1 = 23
    if (body_len < 23) {
        return CapsuleValResult::Fail(CapsuleValCode::CERT_BODY_SHORT,
            "CERT_INSTRUCTION body too short");
    }

    uint8_t note_len = body[22];
    if ((size_t)(23 + note_len) != body_len) {
        return CapsuleValResult::Fail(CapsuleValCode::BAD_BODY_LEN,
            "CERT_INSTRUCTION note_len mismatch");
    }

    if (note_len > CAPSULE_CERT_MAX_NOTE) {
        return CapsuleValResult::Fail(CapsuleValCode::CERT_NOTE_TOO_LONG,
            "CERT_INSTRUCTION note_len=" + std::to_string(note_len) + " exceeds max");
    }

    return CapsuleValResult::Ok();
}

CapsuleValResult ValidateCapsuleBody(
    const CapsuleHeader& h,
    const std::vector<Byte>& payload)
{
    if (payload.size() < CAPSULE_HEADER_SIZE) {
        return CapsuleValResult::Fail(CapsuleValCode::PAYLOAD_TOO_SHORT, "no body");
    }

    const Byte* body = payload.data() + CAPSULE_HEADER_SIZE;
    size_t body_len = payload.size() - CAPSULE_HEADER_SIZE;

    switch ((CapsuleType)h.capsule_type) {
        case CapsuleType::OPEN_NOTE_INLINE:
            return ValidateOpenNoteBody(h, body, body_len);

        case CapsuleType::SEALED_NOTE_INLINE:
            // Sealed note: must have ENCRYPTED flag
            if (!(h.flags & CapsuleFlags::ENCRYPTED)) {
                return CapsuleValResult::Fail(CapsuleValCode::SEALED_NOT_ENCRYPTED,
                    "SEALED_NOTE must have ENCRYPTED flag");
            }
            // Body structure validated at wallet level (epk+nonce+ct+tag)
            return CapsuleValResult::Ok();

        case CapsuleType::DOC_REF_OPEN:
            return ValidateDocRefBody(h, body, body_len, false);

        case CapsuleType::DOC_REF_SEALED:
            return ValidateDocRefBody(h, body, body_len, true);

        case CapsuleType::TEMPLATE_FIELDS_OPEN:
            return ValidateTemplateBody(h, body, body_len, false);

        case CapsuleType::TEMPLATE_FIELDS_SEALED:
            return ValidateTemplateBody(h, body, body_len, true);

        case CapsuleType::CERT_INSTRUCTION:
            return ValidateCertInstructionBody(h, body, body_len);

        default:
            return CapsuleValResult::Fail(CapsuleValCode::UNSUPPORTED_TYPE,
                "unknown capsule_type");
    }
}

// =============================================================================
// ValidateCapsulePolicy — full header + body
// =============================================================================

CapsuleValResult ValidateCapsulePolicy(const std::vector<Byte>& payload) {
    auto hdr_result = ValidateCapsuleHeader(payload);
    if (!hdr_result.ok) return hdr_result;

    CapsuleHeader h;
    DecodeCapsuleHeader(payload, h);

    return ValidateCapsuleBody(h, payload);
}

// =============================================================================
// BuildOpenNotePayload
// =============================================================================

bool BuildOpenNotePayload(
    const std::string& text,
    std::vector<Byte>& out_payload,
    std::string* err)
{
    if (text.size() > CAPSULE_MAX_BODY - 1) {  // -1 for text_len byte
        if (err) *err = "text too long (" + std::to_string(text.size()) +
                        " > " + std::to_string(CAPSULE_MAX_BODY - 1) + ")";
        return false;
    }

    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type    = (uint8_t)CapsuleType::OPEN_NOTE_INLINE;
    h.flags           = 0;
    h.template_id     = 0;
    h.locator_type    = 0;
    h.hash_alg        = 0;
    h.enc_alg         = 0;
    h.body_len        = (uint8_t)(1 + text.size());  // text_len(1) + text(N)
    h.reserved        = 0;

    out_payload.clear();
    EncodeCapsuleHeader(h, out_payload);

    // Body: text_len + text bytes
    out_payload.push_back((uint8_t)text.size());
    out_payload.insert(out_payload.end(), text.begin(), text.end());

    return true;
}

// =============================================================================
// BuildDocRefOpenPayload
// =============================================================================

bool BuildDocRefOpenPayload(
    const DocRefParams& p,
    std::vector<Byte>& out_payload,
    std::string* err)
{
    // Body: capsule_id(8) + file_size(4) + file_hash(32) + manifest_hash(32)
    //     + locator_len(1) + locator(N) = 77 + N
    size_t body_size = 77 + p.locator_ref.size();
    if (body_size > CAPSULE_MAX_BODY) {
        if (err) *err = "DOC_REF body too large";
        return false;
    }

    CapsuleHeader h{};
    h.capsule_version = CAPSULE_VERSION_1;
    h.capsule_type    = (uint8_t)CapsuleType::DOC_REF_OPEN;
    h.flags           = 0;
    h.template_id     = 0;
    h.locator_type    = (uint8_t)p.locator_type;
    h.hash_alg        = (uint8_t)HashAlg::SHA256;
    h.enc_alg         = (uint8_t)EncAlg::NONE;
    h.body_len        = (uint8_t)body_size;
    h.reserved        = 0;

    out_payload.clear();
    EncodeCapsuleHeader(h, out_payload);

    // capsule_id (8 bytes LE)
    for (int i = 0; i < 8; ++i)
        out_payload.push_back((uint8_t)((p.capsule_id >> (i * 8)) & 0xFF));

    // file_size_bytes (4 bytes LE)
    for (int i = 0; i < 4; ++i)
        out_payload.push_back((uint8_t)((p.file_size_bytes >> (i * 8)) & 0xFF));

    // file_hash (32 bytes)
    out_payload.insert(out_payload.end(), p.file_hash.begin(), p.file_hash.end());

    // manifest_hash (32 bytes)
    out_payload.insert(out_payload.end(), p.manifest_hash.begin(), p.manifest_hash.end());

    // locator_len (1 byte) + locator_ref (N bytes)
    out_payload.push_back((uint8_t)p.locator_ref.size());
    out_payload.insert(out_payload.end(), p.locator_ref.begin(), p.locator_ref.end());

    return true;
}

} // namespace sost
