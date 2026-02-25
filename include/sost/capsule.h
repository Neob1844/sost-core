#pragma once

// =============================================================================
// capsule.h — SOST Capsule Protocol v1 (SCPv1)
//
// Binary payload format for structured metadata in SOST transaction outputs.
// Consensus only validates payload size (<=255). Capsule structure is validated
// at policy/mempool level. Capsule semantics are interpreted by wallet/explorer.
//
// Design: SOST Capsule Protocol v1 Draft
// =============================================================================

#include "sost/transaction.h"
#include <cstdint>
#include <string>
#include <vector>

namespace sost {

// =============================================================================
// Constants
// =============================================================================

inline constexpr uint8_t  CAPSULE_MAGIC_0       = 0x53;  // 'S'
inline constexpr uint8_t  CAPSULE_MAGIC_1       = 0x43;  // 'C'
inline constexpr uint8_t  CAPSULE_VERSION_1     = 0x01;
inline constexpr size_t   CAPSULE_HEADER_SIZE   = 12;
inline constexpr size_t   CAPSULE_MAX_BODY      = 243;   // 255 - 12

// =============================================================================
// Enums — capsule_type (u8)
// =============================================================================

enum class CapsuleType : uint8_t {
    NONE                    = 0x00,
    OPEN_NOTE_INLINE        = 0x01,
    SEALED_NOTE_INLINE      = 0x02,
    DOC_REF_OPEN            = 0x03,
    DOC_REF_SEALED          = 0x04,
    TEMPLATE_FIELDS_OPEN    = 0x05,
    TEMPLATE_FIELDS_SEALED  = 0x06,
    CERT_INSTRUCTION        = 0x07,
    // 0x08..0x7F = reserved (SOST)
    // 0x80..0xFF = experimental/local
};

inline bool IsStandardCapsuleType(uint8_t t) {
    return t >= 0x01 && t <= 0x07;
}

// =============================================================================
// Enums — template_id (u8)
// =============================================================================

enum class TemplateId : uint8_t {
    NONE                    = 0x00,
    INVOICE_V1              = 0x01,
    CONTRACT_REF_V1         = 0x02,
    PAYMENT_RECEIPT_V1      = 0x03,
    TRANSFER_INSTRUCTION_V1 = 0x04,
    ESCROW_NOTE_V1          = 0x05,
    COMPLIANCE_RECORD_V1    = 0x06,
    WARRANTY_RECORD_V1      = 0x07,
    SHIPMENT_RECORD_V1      = 0x08,
    GOLD_CERT_NOTE_V1       = 0x09,
    CUSTOM_KV_V1            = 0x0A,
    // 0x0B..0x7F = reserved (SOST)
    // 0x80..0xFF = experimental/local
};

// =============================================================================
// Enums — flags (u8 bitmask)
// =============================================================================

namespace CapsuleFlags {
    inline constexpr uint8_t ENCRYPTED      = 0x01;
    inline constexpr uint8_t COMPRESSED     = 0x02;
    inline constexpr uint8_t ACK_REQUIRED   = 0x04;
    inline constexpr uint8_t HAS_EXPIRES    = 0x08;
    inline constexpr uint8_t HAS_TEMPLATE   = 0x10;
    inline constexpr uint8_t MULTIPART_HINT = 0x20;
    inline constexpr uint8_t RESERVED_6     = 0x40;
    inline constexpr uint8_t RESERVED_7     = 0x80;

    // v1 standard: only these bits may be set
    inline constexpr uint8_t V1_ALLOWED_MASK = 0x3F;  // bits 0-5
}

// =============================================================================
// Enums — locator_type (u8)
// =============================================================================

enum class LocatorType : uint8_t {
    NONE        = 0x00,
    HTTPS_PATH  = 0x01,
    HTTPS_URL   = 0x02,
    IPFS_CID    = 0x03,
    OPAQUE_ID   = 0x04,
    P2P_HINT    = 0x05,
    // 0x06..0xFF = reserved
};

// =============================================================================
// Enums — hash_alg (u8)
// =============================================================================

enum class HashAlg : uint8_t {
    NONE    = 0x00,
    SHA256  = 0x01,
    BLAKE3  = 0x02,   // future/policy
};

// =============================================================================
// Enums — enc_alg (u8)
// =============================================================================

enum class EncAlg : uint8_t {
    NONE                        = 0x00,
    ECIES_SECP256K1_AES256_GCM  = 0x01,
    X25519_AES256_GCM           = 0x02,  // future
};

// =============================================================================
// CapsuleHeader — 12 bytes fixed, present in every capsule payload
// =============================================================================
//
// Offset  Size  Field
//   0      2    magic          = "SC" (0x53, 0x43)
//   2      1    capsule_version = 0x01
//   3      1    capsule_type
//   4      1    flags
//   5      1    template_id
//   6      1    locator_type
//   7      1    hash_alg
//   8      1    enc_alg
//   9      1    body_len
//  10      2    reserved       = 0x0000

struct CapsuleHeader {
    uint8_t capsule_version{0};
    uint8_t capsule_type{0};
    uint8_t flags{0};
    uint8_t template_id{0};
    uint8_t locator_type{0};
    uint8_t hash_alg{0};
    uint8_t enc_alg{0};
    uint8_t body_len{0};
    uint16_t reserved{0};
};

// =============================================================================
// Capsule validation error codes
// =============================================================================

enum class CapsuleValCode : int {
    OK = 0,

    // Header errors
    BAD_MAGIC           = 1,
    BAD_VERSION         = 2,
    BAD_CAPSULE_TYPE    = 3,
    BAD_BODY_LEN        = 4,
    RESERVED_NONZERO    = 5,
    PAYLOAD_TOO_SHORT   = 6,
    PAYLOAD_TOO_LONG    = 7,
    RESERVED_FLAGS      = 8,

    // Body errors (per-type)
    NOTE_TOO_LONG       = 10,
    DOC_ZERO_HASH       = 11,
    DOC_ZERO_LOCATOR    = 12,
    DOC_LOCATOR_TOO_LONG= 13,
    DOC_BODY_TOO_SHORT  = 14,
    SEALED_NOT_ENCRYPTED= 15,
    TEMPLATE_NO_ID      = 16,
    TEMPLATE_NO_FLAG    = 17,
    TEMPLATE_BODY_SHORT = 18,
    CERT_BODY_SHORT     = 19,
    CERT_NOTE_TOO_LONG  = 20,

    // Generic
    UNSUPPORTED_TYPE    = 99,
};

struct CapsuleValResult {
    bool ok{false};
    CapsuleValCode code{CapsuleValCode::UNSUPPORTED_TYPE};
    std::string message;

    static CapsuleValResult Ok() { return {true, CapsuleValCode::OK, "ok"}; }
    static CapsuleValResult Fail(CapsuleValCode c, const std::string& msg) {
        return {false, c, msg};
    }
};

// =============================================================================
// Policy limits (per-type, for mempool standardness)
// =============================================================================

inline constexpr uint8_t CAPSULE_OPEN_NOTE_MAX_TEXT  = 80;
inline constexpr uint8_t CAPSULE_DOC_REF_MAX_LOCATOR = 96;
inline constexpr uint8_t CAPSULE_TEMPLATE_MAX_FIELDS = 128;
inline constexpr uint8_t CAPSULE_CERT_MAX_NOTE       = 64;

// =============================================================================
// Core API
// =============================================================================

// Decode header from raw payload bytes (must be >= 12 bytes).
// Returns false if payload is too short or magic is wrong.
bool DecodeCapsuleHeader(
    const std::vector<Byte>& payload,
    CapsuleHeader& out_header,
    std::string* err = nullptr);

// Encode header into first 12 bytes of output buffer.
// Caller must append body bytes after this.
void EncodeCapsuleHeader(
    const CapsuleHeader& header,
    std::vector<Byte>& out);

// Validate capsule header structure (magic, version, body_len match, reserved).
// Does NOT validate body contents per-type.
CapsuleValResult ValidateCapsuleHeader(
    const std::vector<Byte>& payload);

// Validate capsule body contents per-type (policy-level checks).
// Must call ValidateCapsuleHeader first and pass decoded header.
CapsuleValResult ValidateCapsuleBody(
    const CapsuleHeader& header,
    const std::vector<Byte>& payload);

// Full policy validation: header + body.
// Call this from mempool/standardness checks when payload is non-empty.
CapsuleValResult ValidateCapsulePolicy(
    const std::vector<Byte>& payload);

// =============================================================================
// Convenience: build OPEN_NOTE_INLINE payload
// =============================================================================

// Builds a complete capsule payload for a short open note.
// Returns false if text is too long (> CAPSULE_MAX_BODY - 1 = 242 bytes).
bool BuildOpenNotePayload(
    const std::string& text,
    std::vector<Byte>& out_payload,
    std::string* err = nullptr);

// =============================================================================
// Convenience: build DOC_REF_OPEN payload
// =============================================================================

struct DocRefParams {
    uint64_t capsule_id{0};
    uint32_t file_size_bytes{0};
    Hash256  file_hash{};
    Hash256  manifest_hash{};     // zero if unused
    LocatorType locator_type{LocatorType::NONE};
    std::vector<Byte> locator_ref;
};

// Builds a complete DOC_REF_OPEN capsule payload.
// Minimum body = 8+4+32+32+1 = 77 bytes (no locator).
bool BuildDocRefOpenPayload(
    const DocRefParams& params,
    std::vector<Byte>& out_payload,
    std::string* err = nullptr);

} // namespace sost
