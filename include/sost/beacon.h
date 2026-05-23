// SOST Beacon Phase II-A — local signed-notice channel for the C++ node.
//
// Hard invariants (do NOT relax without re-review):
//   - Beacon does not, and cannot, change consensus, mining, P2P sync,
//     or RPC validation behaviour. It is informational only.
//   - Beacon Phase II-A is GATED at BEACON_PHASE2A_ACTIVATION_HEIGHT
//     (= V13_HEIGHT = 12 000 in the current build). At any height below
//     this, every public entry point returns silence / empty / disabled
//     regardless of file contents.
//   - The C++ Beacon path NEVER opens an HTTP socket. Notices arrive as
//     a local JSON file at <datadir>/notices.json that the operator
//     places out-of-band. All other layers (P2P gossip, web fetch) live
//     in separate scaffolds and are DISABLED by default in Phase II-A.
//   - The Beacon public key is hardcoded in BEACON_PUBKEY_HEX. Never
//     read from a file at runtime. The shipped value is a placeholder
//     producing fail-closed behaviour (rejects every signature).
//   - `commands` MUST be the empty array. A non-empty `commands` field
//     causes the notice to be rejected — Beacon Phase II-A never
//     surfaces actionable commands.
//   - Any failure mode at any step => `load_active_notices` returns an
//     empty vector. Beacon never throws to a caller.

#pragma once

#include "sost/types.h"

#include <cstdint>
#include <string>
#include <vector>

namespace sost::beacon {

// Network discriminator. Notices for the wrong network are dropped at
// the filter layer, not at parse, so the audit can see what was rejected.
enum class Network { MAINNET, TESTNET, OTHER };

// Hardcoded Beacon public key — uncompressed (65 bytes, 130 hex chars).
// This value is a placeholder syntactically valid as a curve point but
// owned by no one; every real signature fails to verify against it.
// The operator replaces this constant with the output of
// `scripts/beacon-keygen.sh` at production rollout. See
// docs/V13_SPEC.md for the rotation procedure.
extern const std::string BEACON_PUBKEY_HEX;

// Schema for a Phase II-A notice. Mirrors the JSON shape produced by
// `scripts/beacon-sign.sh` and consumed by the Phase 1 explorer
// (website/js/beacon.js).
struct Notice {
    std::string              notice_id;
    std::string              network_str;          // raw text from JSON
    Network                  network;              // parsed enum
    std::string              severity;             // info / warn / critical
    std::string              title_en;
    std::string              message_en;
    int64_t                  activation_height;
    int64_t                  expires_height;
    std::string              created_at;
    std::vector<std::string> commands;             // MUST be empty (advisory-only)
    std::string              signature_b64;        // Phase II-A single-sig (legacy)

    // ----- Phase II-B (additive, backwards-compatible) ----------------
    // All four fields below default to "absent" so a pre-II-B notice
    // (legacy single-sig) parses unchanged.
    //
    // threshold == 0  =>  legacy single-signature path (Phase II-A).
    // threshold >= 1  =>  N-of-M threshold path (Phase II-B). The notice
    //                     must carry at least `threshold` valid
    //                     signatures from DISTINCT keys in
    //                     BEACON_THRESHOLD_PUBKEYS. The default
    //                     deployment uses 3-of-5 (BEACON_THRESHOLD_REQUIRED).
    //                     OFF by default in V13 — gated by
    //                     BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT
    //                     (= INT64_MAX). See docs/BEACON_CUSTODY_STATUS.md.
    uint32_t                 threshold{0};
    std::vector<std::string> signatures_b64;       // base64 DER, one per signer
    std::string              revokes;              // notice_id this notice retires ("" = none)
    std::string              mirror_url;           // metadata ONLY — never fetched
};

// ===========================================================================
// Phase II-B — threshold-signed notice support (advisory only)
// ===========================================================================
//
// Hard invariants (do NOT relax without re-review):
//   - threshold sigs do NOT touch consensus, mining, or block validity.
//   - A notice that fails the threshold check is silently dropped (same
//     fail-closed default as single-sig). The chain never branches on it.
//   - mirror_url is metadata ONLY. The node never opens an HTTP socket
//     because of it. No DNS lookups. No file downloads. The field is
//     surfaced via RPC for off-chain UI consumption only.
//   - Revocation is itself a threshold operation: a notice may revoke
//     another notice ONLY if the revoking notice itself passes the
//     threshold check. Single-sig notices cannot revoke anything.
//
// BEACON_THRESHOLD_PUBKEYS is an immutable 5-element array of hardcoded
// operator pubkeys. The placeholder values below are syntactically
// valid curve points owned by no one, so every signature fails closed
// at runtime until the operator replaces them as part of the V13
// release ceremony. See docs/V13_BEACON_PHASE_II_B.md for the rotation
// procedure.

inline constexpr uint32_t BEACON_THRESHOLD_REQUIRED = 3;  // 3-of-5
inline constexpr uint32_t BEACON_THRESHOLD_KEY_COUNT = 5;

extern const std::string BEACON_THRESHOLD_PUBKEYS[BEACON_THRESHOLD_KEY_COUNT];

// Result of attempting a threshold verification on a single notice.
struct ThresholdVerifyResult {
    bool     ok{false};            // true iff distinct_signers >= threshold
    uint32_t distinct_signers{0};  // unique keys that produced a valid sig
    uint32_t required{0};          // copy of n.threshold for diagnostics
};

// Verify a Phase II-B notice against the BEACON_THRESHOLD_PUBKEYS set.
// Counts each pubkey at most once even if it appears in multiple
// signatures (dedup by signer-index). Rejects signatures that fail to
// verify under ANY threshold pubkey. Returns ok=true iff the count of
// distinct valid signers is >= n.threshold AND n.threshold > 0.
//
// Caller can pass an alternate `pubkeys`/`count` pair for tests; the
// default reads the hardcoded BEACON_THRESHOLD_PUBKEYS.
ThresholdVerifyResult verify_threshold_signatures(
    const Notice& n,
    const std::string* pubkeys = nullptr,
    uint32_t           pubkey_count = 0);


// Parse a top-level JSON array of notices. Returns true on success and
// populates `out` with every parsed element. Malformed input ⇒ false
// and out is left untouched. Errors are intentionally NOT made fatal at
// this layer; the caller should treat any false return as "no notices".
bool parse_notices_array(const std::string& json,
                         std::vector<Notice>& out,
                         std::string* err = nullptr);

// Convert a `Notice` back into the canonical signed-payload bytes. The
// output is byte-identical to `jq -cSj 'del(.signature)' <signed.json>`
// for any notice the shell pipeline produces — that property is what
// makes the C++ verifier interoperable with the explorer JS verifier
// and the shell verifier.
std::string canonical_payload(const Notice& n);

// Verify the ECDSA-SHA256 signature on `n` under `pubkey_hex_uncompressed`
// (the 130-character uncompressed-point hex emitted by `beacon-keygen.sh`).
// Defaults to the hardcoded BEACON_PUBKEY_HEX. Returns false on any
// failure (bad hex, malformed signature, hash mismatch, etc.). lowS is
// NOT enforced — openssl produces both low-S and high-S signatures and
// Beacon's single-pinned-key trust model does not need malleability
// resistance.
bool verify_signature(const Notice& n,
                      const std::string& pubkey_hex_uncompressed = BEACON_PUBKEY_HEX);

// Map a network string to the enum. Anything that is not exactly
// "mainnet" or "testnet" maps to Network::OTHER (rejected by filters).
Network parse_network(const std::string& s);

// Schema filter. Returns true iff every condition holds:
//   - signature verifies under `pubkey_hex_uncompressed`
//   - notice.network == current_network
//   - notice.activation_height <= current_height < notice.expires_height
//   - notice.commands.empty()
// Any failure ⇒ false. No exceptions.
bool is_active(const Notice& n,
               int64_t current_height,
               Network current_network,
               const std::string& pubkey_hex_uncompressed = BEACON_PUBKEY_HEX);

// Compose the entire load → parse → verify → filter pipeline.
//
//   1. If current_height < BEACON_PHASE2A_ACTIVATION_HEIGHT, return {}
//      (Phase II-A dormancy — explicit silence pre-fork).
//   2. Read <datadir>/notices.json. Missing file or any I/O failure ⇒
//      return {}.
//   3. Parse the array. Any parse failure ⇒ return {}.
//   4. For each notice, drop those that fail `is_active(...)`.
//   5. Return the surviving notices in input order.
//
// Never throws. Never blocks. Cap on file size enforced internally to
// guard against an oversized notices.json (256 KB).
std::vector<Notice> load_active_notices(const std::string& datadir,
                                        int64_t            current_height,
                                        Network            current_network,
                                        const std::string& pubkey_hex_uncompressed = BEACON_PUBKEY_HEX);

// Serialize a vector of notices back to a JSON-array string suitable
// for an RPC response. The output is human-readable JSON (compact, no
// pretty-print). Useful for `getbeaconnotices`. Empty input ⇒ "[]".
std::string serialize_notices_for_rpc(const std::vector<Notice>& notices);

} // namespace sost::beacon
