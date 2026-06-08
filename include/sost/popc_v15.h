// popc_v15.h — V15 PoPC Model A/B deterministic rails (P1: PURE BASE, no enforcement).
//
// Pure, gated building blocks for the on-chain PoPC lifecycle designed in
// docs/V15_POPC_MODEL_AB_DESIGN.md. P1 ships ONLY the deterministic primitives +
// unit tests — it does NOT touch process_block, the DTD gate, or mainnet
// behaviour (gate = INT64_MAX on mainnet → every helper is inert there).
//
// Model A = self-attested personal custody under bonded liability: consensus
// verifies the holder's SIGNED attestation + timing + bond, never an external
// balance. Model B = supervised: a designated supervisor key signs. No bridge,
// no mandatory oracle, no node reading Ethereum. PoPC proves "a signed claim
// under bond, auditable and slashable", not "reserves verified".
#pragma once
#include "sost/params.h"
#include "sost/crypto.h"        // sha256, Bytes32
#include "sost/tx_signer.h"     // PubKeyHash
#include <cstdint>
#include <climits>
#include <array>
#include <vector>
#include <string>

namespace sost {

// ---- activation gate (part of the V15 bundle; mainnet DEFERRED) -------------
#ifdef SOST_TESTNET_FORKS
inline constexpr int64_t POPC_V15_ACTIVATION_HEIGHT = V15_HEIGHT;
#else
inline constexpr int64_t POPC_V15_ACTIVATION_HEIGHT = INT64_MAX;   // -> V15_HEIGHT in the final commit
#endif
inline constexpr bool popc_v15_active_at(int64_t height) { return height >= POPC_V15_ACTIVATION_HEIGHT; }

// ---- deterministic constants ----------------------------------------------
inline constexpr int64_t POPC_V15_MIN_BOND_STOCKS   = 10 * STOCKS_PER_SOST; // 10 SOST minimum bond
inline constexpr int64_t POPC_V15_AUDIT_GRACE_BLOCKS = 288;  // ~48h at 10min/block to answer a challenge
inline constexpr int64_t POPC_V15_MIN_TERM_BLOCKS    = 4320; // ~30 days minimum commitment term

enum class PopcModel  : uint8_t { A = 0, B = 1 };   // A=personal custody, B=supervised
enum class PopcV15Status : uint8_t {
    Pending  = 0,   // registered, before start_height / first activation
    Active   = 1,   // live commitment
    Expired  = 2,   // reached end_height in good standing, awaiting settle
    Slashed  = 3,   // failed an audit challenge → bond forfeited
    Settled  = 4,   // bond released + reward paid
};

// Canonical on-chain commitment (the deterministic record that REPLACES the
// per-node popc_registry.json as the source of truth once wired).
struct PopcV15Commitment {
    uint8_t      model{0};           // PopcModel
    PubKeyHash   owner_pkh{};        // SOST owner (bond + Model-A attester)
    std::string  gold_token;         // "XAUT" / "PAXG" (declared, external)
    int64_t      gold_amount_mg{0};  // declared custody, milligrams
    int64_t      bond_stocks{0};     // SOST bond locked on-chain
    int64_t      start_height{0};
    int64_t      end_height{0};
    int64_t      audit_interval{0};  // blocks between scheduled audit challenges
};

inline constexpr char POPC_V15_ID_DOMAIN[]     = "SOST/POPC-V15-ID/v1";
inline constexpr char POPC_V15_ATTEST_DOMAIN[] = "SOST/POPC-V15-ATTEST/v1";

inline void _put_le64(std::vector<uint8_t>& m, int64_t v) {
    for (int i = 0; i < 8; ++i) m.push_back((uint8_t)((uint64_t)v >> (8 * i)));
}

// Deterministic commitment id = sha256(DOMAIN || canonical fields).
inline Bytes32 popc_v15_commitment_id(const PopcV15Commitment& c) {
    std::vector<uint8_t> m;
    for (size_t i = 0; i + 1 < sizeof(POPC_V15_ID_DOMAIN); ++i) m.push_back((uint8_t)POPC_V15_ID_DOMAIN[i]);
    m.push_back(c.model);
    for (uint8_t b : c.owner_pkh) m.push_back(b);
    for (char ch : c.gold_token) m.push_back((uint8_t)ch);
    m.push_back(0);
    _put_le64(m, c.gold_amount_mg); _put_le64(m, c.bond_stocks);
    _put_le64(m, c.start_height);   _put_le64(m, c.end_height); _put_le64(m, c.audit_interval);
    return sha256(m.data(), m.size());
}

// ---- pure lifecycle helpers (no chain state; deterministic) ----------------
inline constexpr bool popc_v15_min_bond_ok(int64_t bond_stocks) {
    return bond_stocks >= POPC_V15_MIN_BOND_STOCKS;
}
inline constexpr bool popc_v15_term_ok(int64_t start_height, int64_t end_height) {
    return end_height - start_height >= POPC_V15_MIN_TERM_BLOCKS;
}
inline constexpr bool popc_v15_is_expired(const PopcV15Commitment& c, int64_t height) {
    return height >= c.end_height;
}
// Next scheduled audit challenge height strictly after `height` (interval>0).
inline constexpr int64_t popc_v15_next_audit(int64_t start_height, int64_t interval, int64_t height) {
    if (interval <= 0 || height < start_height) return start_height + (interval > 0 ? interval : 0);
    int64_t k = (height - start_height) / interval + 1;
    return start_height + k * interval;
}
inline constexpr bool popc_v15_audit_due(int64_t start_height, int64_t interval, int64_t height) {
    return interval > 0 && height >= start_height && ((height - start_height) % interval == 0) && height > start_height;
}
// A challenge posted at `audit_height` with no valid response within the grace
// window is slashable once height passes the deadline.
inline constexpr bool popc_v15_slash_eligible(int64_t audit_height, int64_t response_height, int64_t height) {
    if (audit_height <= 0) return false;                 // no open challenge
    if (response_height >= audit_height) return false;   // answered (response on/after the challenge)
    return height > audit_height + POPC_V15_AUDIT_GRACE_BLOCKS;
}
inline constexpr bool popc_v15_settle_eligible(PopcV15Status status, const PopcV15Commitment& c, int64_t height) {
    return (status == PopcV15Status::Active || status == PopcV15Status::Expired) && height >= c.end_height;
}

// ---- attestation (Model A self-signed / Model B supervisor-signed) ---------
// Digest the attester signs to claim `balance_mg` for `commitment_id` at `attest_height`.
inline Bytes32 popc_v15_attest_digest(const Bytes32& commitment_id, int64_t balance_mg, int64_t attest_height) {
    std::vector<uint8_t> m;
    for (size_t i = 0; i + 1 < sizeof(POPC_V15_ATTEST_DOMAIN); ++i) m.push_back((uint8_t)POPC_V15_ATTEST_DOMAIN[i]);
    for (uint8_t b : commitment_id) m.push_back(b);
    _put_le64(m, balance_mg); _put_le64(m, attest_height);
    return sha256(m.data(), m.size());
}

// ---- declared in popc_v15.cpp (need secp256k1 / ripemd160) -----------------
// RIPEMD160(SHA256(pubkey)) — the SOST address pkh for a (33- or 65-byte) pubkey.
PubKeyHash popc_v15_pubkey_pkh(const std::vector<uint8_t>& pubkey);
// True iff `pubkey` is the owner's key (Model A self-attestation binding).
bool popc_v15_pubkey_is_owner(const std::vector<uint8_t>& pubkey, const PubKeyHash& owner_pkh);
// Verify a compact-ECDSA attestation signature over popc_v15_attest_digest(...)
// against `pubkey`. Caller chooses the key (owner for Model A, supervisor for B)
// and is responsible for the activation gate. Pure crypto; no chain state.
bool popc_v15_verify_attestation(const Bytes32& commitment_id, int64_t balance_mg, int64_t attest_height,
                                 const std::vector<uint8_t>& pubkey, const std::vector<uint8_t>& sig_compact);

// ---- future interface (NOT wired in P1) ------------------------------------
// chain_active_popc_set(height): in a later phase, a PURE function that recomputes
// the active commitment set from chain state (registrations minus completed/
// slashed/expired up to `height`), replacing popc_registry.json AND the
// has_active_canonical_popc stub. Declared here as the agreed interface only.

} // namespace sost
