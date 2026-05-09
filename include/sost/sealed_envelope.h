// sealed_envelope.h — single-recipient ECIES envelope for SCPv1 sealed types
// (0x02 SEALED_NOTE_INLINE, 0x04 DOC_REF_SEALED, 0x06 TEMPLATE_FIELDS_SEALED).
//
// SCOPE FOR FASE SEALED-1
// -----------------------
// Single recipient ONLY. The body layout below was sized so that, with the
// 255-byte sighash payload window (1-byte payload_len in ComputeHashOutputs),
// each sealed Capsule fits a plaintext of up to 158 bytes — comfortably above
// the policy caps for Note (80), Cert (64), Structured (128) and Doc-Ref
// (128). Multi-recipient sealed is intentionally NOT in this fase: it would
// require either a consensus change to the sighash payload_len (u8 → u16)
// or a non-standard shared-key wrap. Both are out of scope; the wallet/CLI
// guards refuse multi-recipient + sealed before any signing.
//
// FORMAT (single-recipient sealed body, 85 + N bytes total)
// ---------------------------------------------------------
//   offset  size  field
//   ----------------------------------------------------------------
//        0     1  version          0x01 (this format)
//        1     1  recipient_count  0x01 (must be 1 in this fase)
//        2    20  recipient_pkh    hash160 of the recipient's pubkey
//       22    33  ephemeral_pub    compressed secp256k1 ephemeral pubkey
//       55    12  nonce            random AES-GCM IV
//       67     2  ciphertext_len   little-endian, == plaintext length N
//       69     N  ciphertext       AES-256-GCM(plaintext)
//   69 + N    16  auth_tag         AES-GCM authentication tag
//
// ECIES STACK (RFC-aligned)
// -------------------------
//   key agreement   secp256k1 ECDH (libsecp256k1::secp256k1_ecdh)
//   key derivation  HKDF-SHA256 (RFC 5869) with
//                       salt   = ephemeral_pub_compressed (33 B)
//                       info   = "SOST_CAPSULE_SEALED_V1"
//                       L      = 32 (AES-256 key length)
//   symmetric       AES-256-GCM with 12-byte nonce, 16-byte tag
//                       AAD    = sealed body bytes [0 .. 67]
//                              (version + count + pkh + epub + nonce +
//                               ct_len), so the recipient cannot be
//                               redirected silently.
//
// SECURITY NOTES
// --------------
//   * The ephemeral keypair is freshly generated for every sealed payload
//     (no key reuse across messages).
//   * Domain separation string ties the derivation to this protocol version;
//     a future SOST_CAPSULE_SEALED_V2 would derive a different key from the
//     same ECDH secret and not roundtrip with V1.
//   * AAD covers the recipient_pkh and ephemeral_pub, so a man-in-the-middle
//     cannot rewrite either without breaking the AES-GCM tag.
//   * Plaintext is the body of the underlying sealed-* type (note text,
//     doc-ref body, structured fields blob), NOT the Capsule header.

#pragma once

#include "sost/transaction.h"   // Byte
#include "sost/tx_signer.h"     // PrivKey, PubKey, PubKeyHash
#include <cstdint>
#include <string>
#include <vector>

namespace sost {

// Hard-coded by spec — do not change without bumping the version field
// and adding migration handling in the consumer wallets.
inline constexpr uint8_t  SEALED_ENVELOPE_VERSION = 0x01;
inline constexpr size_t   SEALED_FIXED_OVERHEAD   = 85;   // header up to ct_len + tag
inline constexpr size_t   SEALED_BODY_MAX_BYTES   = 243;  // SCPv1 body cap
inline constexpr size_t   SEALED_PLAINTEXT_MAX    = SEALED_BODY_MAX_BYTES - SEALED_FIXED_OVERHEAD; // 158
inline constexpr size_t   SEALED_NONCE_BYTES      = 12;
inline constexpr size_t   SEALED_TAG_BYTES        = 16;
inline constexpr size_t   SEALED_EPUB_BYTES       = 33;
inline constexpr size_t   SEALED_PKH_BYTES        = 20;
inline constexpr size_t   SEALED_AES_KEY_BYTES    = 32;

// =============================================================================
// SealSingleRecipient — encrypt `plaintext` for the holder of recipient_pubkey.
//
// Inputs
//   plaintext         body of the underlying sealed-* capsule (note text,
//                     doc-ref body, structured fields). Caller has already
//                     enforced the per-type policy cap (e.g. note ≤ 80).
//                     Length must be ≤ SEALED_PLAINTEXT_MAX (158).
//   recipient_pubkey  33-byte compressed secp256k1 pubkey of the recipient.
//                     Caller is responsible for verifying that this pubkey
//                     hash160s to the bech32 address the user typed.
//   recipient_pkh     20-byte hash160 of the recipient pubkey. Embedded in
//                     the envelope as a hint so wallets can quickly skip
//                     envelopes that were not addressed to them without
//                     attempting an ECDH on every received tx.
//
// Output
//   out_envelope      the 85+N byte body laid out above. Caller wraps it
//                     with the SCPv1 12-byte capsule header (type = 0x02 /
//                     0x04 / 0x06, body_len = out_envelope.size()).
//
// Failure modes
//   plaintext too large       err = "sealed: plaintext exceeds 158 bytes"
//   bad recipient_pubkey      err = "sealed: invalid recipient pubkey"
//   internal crypto failure   err = "sealed: <openssl error>"
//
// Returns true on success; on failure leaves out_envelope empty.
// =============================================================================
bool SealSingleRecipient(const std::vector<Byte>&        plaintext,
                         const std::vector<Byte>&        recipient_pubkey,   // 33
                         const PubKeyHash&               recipient_pkh,
                         std::vector<Byte>&              out_envelope,
                         std::string*                    err = nullptr);

// =============================================================================
// OpenSingleRecipient — try to decrypt a sealed envelope with our private key.
//
// Inputs
//   envelope          the body bytes returned by SealSingleRecipient.
//   our_privkey       32-byte secp256k1 secret key.
//
// Output
//   out_plaintext     the original plaintext on success.
//
// Failure modes
//   envelope too short            err = "sealed: envelope truncated"
//   wrong version / count         err = "sealed: unsupported version"
//   pkh mismatch (not for us)     err = "sealed: not addressed to this key"
//   AES-GCM tag mismatch          err = "sealed: authentication failed"
//   internal crypto failure       err = "sealed: <openssl error>"
//
// Returns true on success. Constant-ish-time for our purposes — pkh is
// checked first so an envelope addressed to a different recipient never
// runs ECDH; AES-GCM tag verification is constant-time inside OpenSSL.
// =============================================================================
bool OpenSingleRecipient(const std::vector<Byte>& envelope,
                         const PrivKey&           our_privkey,
                         std::vector<Byte>&       out_plaintext,
                         std::string*             err = nullptr);

// Convenience: parse-only. Returns the recipient_pkh from the envelope
// without doing any ECDH. Wallets use this to filter incoming sealed
// capsules to "addressed to me" / "addressed to someone else" before
// attempting a decrypt. Returns false on truncated/bad envelope.
bool PeekSealedRecipientPkh(const std::vector<Byte>& envelope,
                            PubKeyHash&              out_pkh);

}  // namespace sost
