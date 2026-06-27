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
#include "sost/transaction.h"   // TxOutput (for the on-chain carrier)
#include <cstdint>
#include <climits>
#include <array>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <utility>

namespace sost {

// ---- activation gate (part of the V15 bundle) -------------------------------
// V15 MAINNET ACTIVATION (2026-06-27, after testnet soak PASS + carrier tx-validation
// fix PR #24): the PoPC V15 on-chain carrier subsystem + single-model settle go live
// at V15_HEIGHT on BOTH profiles (testnet 300 / mainnet 20000). DTD-PoPC lottery
// eligibility additionally requires an OPEN PoPC from DTD_POPC_ELIGIBILITY_HEIGHT
// (= V15_HEIGHT + grace; mainnet 25000). Gold Boost (POPC_GOLD_BOOST_HEIGHT) and
// Gold Vault governance (GV_*) stay DEFERRED at INT64_MAX.
inline constexpr int64_t POPC_V15_ACTIVATION_HEIGHT = V15_HEIGHT;
inline constexpr bool popc_v15_active_at(int64_t height) { return height >= POPC_V15_ACTIVATION_HEIGHT; }

// ---- deterministic constants ----------------------------------------------
inline constexpr int64_t POPC_V15_MIN_BOND_STOCKS   = 10 * STOCKS_PER_SOST; // 10 SOST minimum bond
inline constexpr int64_t POPC_V15_AUDIT_GRACE_BLOCKS = 288;  // ~48h at 10min/block to answer a challenge
inline constexpr int64_t POPC_V15_MIN_TERM_BLOCKS    = 4320; // ~30 days minimum commitment term

enum class PopcModel  : uint8_t { A = 0, B = 1 };   // A=personal custody, B=supervised
enum class PopcV15Status : uint8_t {
    Pending   = 0,   // registered, before start_height / first activation
    Active    = 1,   // live commitment
    Expired   = 2,   // reached end_height in good standing, awaiting settle
    Slashed   = 3,   // failed an audit challenge → bond forfeited (terminal)
    Settled   = 4,   // bond released + reward paid (terminal)
    Suspended = 5,   // temporarily out of the active set (Activate can restore)
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

// ============================================================================
// P2 — chain_active_popc_set: PURE, reorg-safe recompute of the active set.
//
// A pure fold over the canonical PoPC events of the ACTIVE chain. It replaces
// popc_registry.json (and, later, the has_active_canonical_popc stub) as the
// source of truth. It is NOT wired into process_block or the DTD gate in P2 —
// it is the deterministic brain only. Because it is a pure function of the
// supplied event list, two nodes on the same chain compute the identical set,
// and a reorg (a different event list) simply recomputes — no cached state.
// ============================================================================

enum class PopcEventType : uint8_t {
    Register = 0,   // a commitment is registered (carries owner, model, end_height)
    Activate = 1,   // Pending -> Active
    Renew    = 2,   // extend end_height (only while non-terminal)
    Expire   = 3,   // mark Expired (leaves the active set)
    Suspend  = 4,   // mark Suspended (leaves the active set; Activate can restore)
    Slash    = 5,   // TERMINAL: bond forfeited
    Settle   = 6,   // TERMINAL: bond released + reward paid
};

struct PopcV15Event {
    PopcEventType type{PopcEventType::Register};
    Bytes32       commitment_id{};
    PubKeyHash    owner_pkh{};
    uint8_t       model{0};
    int64_t       height{0};       // block height the event occurred at
    int64_t       end_height{0};   // for Register / Renew
};

struct PopcActiveEntry {
    Bytes32    commitment_id{};
    PubKeyHash owner_pkh{};
    uint8_t    model{0};
    int64_t    end_height{0};
};

// P4c — authorization digest for the NON-attest state-changing carriers
// (Register / Renew / Suspend). The commitment owner signs this digest; the node
// rejects any such carrier whose signature is missing, invalid, or not by the
// owner key (pkh != owner_pkh). This stops a third party from emitting events on
// a commitment they do not own just by posting a marker output. Domain-separated
// and bound to (type, model, commitment_id, owner_pkh, end_height).
inline constexpr char POPC_V15_EVENT_AUTH_DOMAIN[] = "SOST/POPC-V15-EVENT-AUTH/v1";
inline Bytes32 popc_v15_event_digest(PopcEventType type, const Bytes32& commitment_id,
                                     const PubKeyHash& owner, uint8_t model, int64_t end_height) {
    std::vector<uint8_t> m;
    for (size_t i = 0; i + 1 < sizeof(POPC_V15_EVENT_AUTH_DOMAIN); ++i) m.push_back((uint8_t)POPC_V15_EVENT_AUTH_DOMAIN[i]);
    m.push_back((uint8_t)type); m.push_back(model);
    for (uint8_t b : commitment_id) m.push_back(b);
    for (uint8_t b : owner)         m.push_back(b);
    _put_le64(m, end_height);
    return sha256(m.data(), m.size());
}

// Which event types may ride on-chain as a carrier (P4c). Slash & Settle are
// NEVER carried — they are derived deterministically (auto-slash / auto-settle),
// so no manual/forged Slash or Settle can ever enter the chain. Expire is also
// not carried (expiry is implied by end_height).
inline constexpr bool popc_v15_event_is_carriable(PopcEventType t) {
    return t == PopcEventType::Register || t == PopcEventType::Activate ||
           t == PopcEventType::Renew    || t == PopcEventType::Suspend;
}

// P4c — verify a NON-attest carrier's owner authorization: the compact-ECDSA
// signature must be valid over popc_v15_event_digest(...) AND `pubkey` must hash
// to `owner` (the owner self-authorizes Register/Renew/Suspend). Pure crypto;
// declared here, implemented in popc_v15.cpp (needs secp256k1).
bool popc_v15_verify_event_auth(PopcEventType type, const Bytes32& commitment_id, const PubKeyHash& owner,
                                uint8_t model, int64_t end_height,
                                const std::vector<uint8_t>& pubkey, const std::vector<uint8_t>& sig_compact);

// Audit cadence (protocol-wide, deterministic): an ACTIVATED commitment must be
// re-attested by its owner at least once per interval. Missing a scheduled audit
// by more than the grace window (POPC_V15_AUDIT_GRACE_BLOCKS) makes it
// auto-slashable. Per-commitment audit intervals are reserved for a future
// carrier extension; P4b uses this single protocol-wide cadence so every node
// computes identical audit deadlines.
inline constexpr int64_t POPC_V15_AUDIT_INTERVAL_BLOCKS = 1440;

// ============================================================================
// P4b — full per-commitment lifecycle, INCLUDING the deterministic
// auto-transitions. There is NO Guardian, NO signature and NO mandatory oracle:
// every node recomputes the identical state purely from the chain's events at
// `at_height`, so it is reorg-safe by construction (a different event list just
// recomputes — no cached state survives).
//
//   * auto-slash — an activated commitment whose latest scheduled audit went
//     unanswered past the grace window is slashed (popc_v15_slash_eligible). The
//     owner's periodic re-attestation is an Activate event (self-attested under
//     bond) whose on-chain height is the audit response. Only commitments that
//     have actually been Activated carry an audit clock; a bare Register has no
//     attestation obligation and is never auto-slashed.
//   * auto-settle — a live commitment that reaches end_height in good standing
//     (no missed audit) settles automatically. No manual Settle carrier needed.
//
// auto-slash takes precedence over auto-settle: a term that lapsed an audit is
// slashed, not settled. Explicit Slash/Settle carriers remain terminal and are
// never overridden. Pre-V15 / mainnet the caller supplies an empty event list,
// so this is a pure no-op (empty result) and replay stays byte-identical.
// ============================================================================
struct PopcV15Rec {
    PubKeyHash    owner{};
    uint8_t       model{0};
    int64_t       end{0};
    PopcV15Status status{PopcV15Status::Pending};
    int           order{0};
    bool          activated{false};      // saw at least one Activate (attestation)
    int64_t       activation_height{0};  // height of the FIRST Activate
    int64_t       last_attest{0};        // height of the LATEST Activate (re-attest)
    bool          auto_slashed{false};   // derived: not from an explicit carrier
    bool          auto_settled{false};   // derived: not from an explicit carrier
};

// Fold the explicit events (chain order; only height <= at_height), then apply
// the deterministic auto-slash / auto-settle transitions. Returns every
// commitment seen, keyed by id. PURE.
inline std::map<Bytes32, PopcV15Rec> chain_popc_recompute(
        const std::vector<PopcV15Event>& events, int64_t at_height) {
    std::map<Bytes32, PopcV15Rec> by_id;
    int seq = 0;
    for (const auto& e : events) {
        if (e.height > at_height) continue;                 // event in the future of the query
        auto it = by_id.find(e.commitment_id);
        bool exists = (it != by_id.end());
        if (exists && (it->second.status == PopcV15Status::Slashed ||
                       it->second.status == PopcV15Status::Settled)) continue;  // terminal: frozen
        switch (e.type) {
            case PopcEventType::Register:
                // P4c — Register only DECLARES the commitment (Pending). It does
                // NOT count as custody until a valid Activate attestation lands.
                if (!exists) { PopcV15Rec r; r.owner=e.owner_pkh; r.model=e.model; r.end=e.end_height;
                               r.status=PopcV15Status::Pending; r.order=seq++; by_id.emplace(e.commitment_id, r); }
                // duplicate Register is idempotent (first wins) — deterministic
                break;
            case PopcEventType::Activate:
                if (exists) {
                    if (it->second.status==PopcV15Status::Pending || it->second.status==PopcV15Status::Suspended)
                        it->second.status = PopcV15Status::Active;
                    it->second.activated = true;                       // starts/keeps the audit clock
                    if (it->second.activation_height == 0) it->second.activation_height = e.height;
                    if (e.height > it->second.last_attest) it->second.last_attest = e.height;
                }
                break;
            case PopcEventType::Renew:
                if (exists && it->second.status==PopcV15Status::Active && e.end_height > it->second.end)
                    it->second.end = e.end_height;
                break;
            case PopcEventType::Expire:
                if (exists) it->second.status = PopcV15Status::Expired;
                break;
            case PopcEventType::Suspend:
                if (exists && it->second.status==PopcV15Status::Active) it->second.status = PopcV15Status::Suspended;
                break;
            case PopcEventType::Slash:
                if (exists) it->second.status = PopcV15Status::Slashed;     // terminal (explicit)
                break;
            case PopcEventType::Settle:
                if (exists) it->second.status = PopcV15Status::Settled;     // terminal (explicit)
                break;
        }
    }
    // P4b — deterministic auto-transitions on still-live commitments.
    for (auto& kv : by_id) {
        PopcV15Rec& r = kv.second;
        if (r.status != PopcV15Status::Active) continue;     // only live commitments transition
        // auto-slash: an activated commitment has an audit clock. Audits fall due
        // every interval from activation, but only within the term [.., end).
        if (r.activated && r.activation_height > 0) {
            int64_t horizon = (at_height < r.end) ? at_height : (r.end - 1);
            if (horizon >= r.activation_height + POPC_V15_AUDIT_INTERVAL_BLOCKS) {
                int64_t k = (horizon - r.activation_height) / POPC_V15_AUDIT_INTERVAL_BLOCKS;
                int64_t last_due_audit = r.activation_height + k * POPC_V15_AUDIT_INTERVAL_BLOCKS;
                if (popc_v15_slash_eligible(last_due_audit, r.last_attest, at_height)) {
                    r.status = PopcV15Status::Slashed; r.auto_slashed = true;
                    continue;                                 // slash wins over settle
                }
            }
        }
        // auto-settle: reached end_height in good standing.
        if (at_height >= r.end) { r.status = PopcV15Status::Settled; r.auto_settled = true; }
    }
    return by_id;
}

// Recompute the active commitment set as of `at_height`. A commitment is ACTIVE
// iff its (auto-transition-aware) latest state is Active AND at_height < end.
inline std::vector<PopcActiveEntry> chain_active_popc_set(
        const std::vector<PopcV15Event>& events, int64_t at_height) {
    auto by_id = chain_popc_recompute(events, at_height);
    std::vector<std::pair<int,PopcActiveEntry>> tmp;
    for (const auto& kv : by_id) {
        const PopcV15Rec& r = kv.second;
        if (r.status == PopcV15Status::Active && at_height < r.end)
            tmp.push_back({r.order, PopcActiveEntry{kv.first, r.owner, r.model, r.end}});
    }
    std::sort(tmp.begin(), tmp.end(), [](const auto&a, const auto&b){ return a.first < b.first; });
    std::vector<PopcActiveEntry> out; out.reserve(tmp.size());
    for (auto& p : tmp) out.push_back(p.second);
    return out;   // deterministic order = registration order
}

// P4b — canonical lifecycle status of one commitment at `at_height`, INCLUDING
// the deterministic auto-slash / auto-settle. Unknown id -> Pending. PURE.
inline PopcV15Status popc_v15_commitment_status(
        const std::vector<PopcV15Event>& events, const Bytes32& commitment_id, int64_t at_height) {
    auto by_id = chain_popc_recompute(events, at_height);
    auto it = by_id.find(commitment_id);
    return (it == by_id.end()) ? PopcV15Status::Pending : it->second.status;
}

// Does `owner_pkh` hold ANY active commitment at `at_height`? This is the pure
// replacement that has_active_canonical_popc will call once wired (P4), instead
// of ever touching popc_registry.json. NOT wired to the DTD gate in P2.
inline bool popc_v15_owner_active(const std::vector<PopcV15Event>& events,
                                  const PubKeyHash& owner_pkh, int64_t at_height) {
    for (const auto& e : chain_active_popc_set(events, at_height))
        if (e.owner_pkh == owner_pkh) return true;
    return false;
}

// ============================================================================
// P3 — on-chain carriers: the deterministic encoding of PoPC events in blocks.
//
// A PoPC event rides in a NORMAL transaction as a 0-value output to the fixed,
// unspendable POPC_V15_MARKER_PKH, whose payload is a versioned, domain-separated
// binary blob. P1's set engine (P2) consumes the decoded events; P3 only DEFINES
// and DECODES the bytes — it is NOT wired into process_block or the DTD gate.
// The decoder is PURE (byte parsing only); the gate (popc_v15_active_at) and the
// attestation signature check (popc_v15_verify_attestation) are applied by the
// caller in P4. Malformed / wrong-magic / wrong-version / wrong-length payloads
// decode to ok=false, so pre-activation and normal txs are unaffected.
// ============================================================================

inline constexpr uint8_t POPC_V15_CARRIER_VERSION = 1;
inline constexpr std::array<uint8_t,4> POPC_V15_MAGIC = { 'P','1','5', 0xC0 };
// 20 ASCII bytes, unspendable (no private key) — the recognised carrier address.
inline constexpr std::array<uint8_t,20> POPC_V15_MARKER_PKH = {
    'P','O','P','C','-','V','1','5','-','M','A','R','K','E','R','-','0','0','0','1' };

// Carrier layout v1 (base = 67 bytes):
//   magic(4) | version(1) | event_type(1) | model(1) | commitment_id(32) | owner_pkh(20) | end_height(i64 LE,8)
// For Activate (= attestation response), append (total 180):
//   balance_mg(i64 LE,8) | attest_height(i64 LE,8) | pubkey(33, compressed) | sig(64, compact)
inline constexpr size_t POPC_V15_CARRIER_BASE_LEN   = 67;
inline constexpr size_t POPC_V15_CARRIER_ATTEST_LEN = 67 + 8 + 8 + 33 + 64;  // 180
// P4c — owner-authorized non-attest carrier (Register/Renew/Suspend):
//   base(67) | pubkey(33, compressed) | sig(64, compact over popc_v15_event_digest)
inline constexpr size_t POPC_V15_CARRIER_SIGNED_LEN = 67 + 33 + 64;          // 164

struct PopcV15Carrier {
    bool        ok{false};
    PopcV15Event event{};
    bool        has_attest{false};  // Activate carrier carries a balance attestation
    bool        has_sig{false};     // P4c: carrier carries an owner-authorization signature
    int64_t     balance_mg{0};
    int64_t     attest_height{0};
    std::vector<uint8_t> pubkey;   // 33-byte compressed (Activate or signed event)
    std::vector<uint8_t> sig;      // 64-byte compact   (Activate or signed event)
};

inline int64_t _get_le64(const std::vector<uint8_t>& b, size_t off) {
    int64_t v = 0; for (int i = 0; i < 8; ++i) v |= (int64_t)b[off + (size_t)i] << (8 * i); return v;
}

// Encode a non-attest event (Register/Renew/Suspend/Slash/Settle/Expire).
inline std::vector<uint8_t> popc_v15_encode_event(PopcEventType type, const Bytes32& cid,
                                                  const PubKeyHash& owner, uint8_t model, int64_t end_height) {
    std::vector<uint8_t> p;
    p.insert(p.end(), POPC_V15_MAGIC.begin(), POPC_V15_MAGIC.end());
    p.push_back(POPC_V15_CARRIER_VERSION);
    p.push_back((uint8_t)type);
    p.push_back(model);
    p.insert(p.end(), cid.begin(), cid.end());
    p.insert(p.end(), owner.begin(), owner.end());
    _put_le64(p, end_height);
    return p;
}
// P4c — encode an owner-authorized non-attest carrier (Register/Renew/Suspend):
// base event + the owner's pubkey + the compact signature over popc_v15_event_digest.
inline std::vector<uint8_t> popc_v15_encode_signed_event(PopcEventType type, const Bytes32& cid,
                                                         const PubKeyHash& owner, uint8_t model, int64_t end_height,
                                                         const std::vector<uint8_t>& pubkey33, const std::vector<uint8_t>& sig64) {
    auto p = popc_v15_encode_event(type, cid, owner, model, end_height);
    p.insert(p.end(), pubkey33.begin(), pubkey33.end());
    p.insert(p.end(), sig64.begin(), sig64.end());
    return p;
}
// Encode an Activate (attestation response) carrier with the signed claim.
inline std::vector<uint8_t> popc_v15_encode_attest(const Bytes32& cid, const PubKeyHash& owner, uint8_t model,
                                                   int64_t end_height, int64_t balance_mg, int64_t attest_height,
                                                   const std::vector<uint8_t>& pubkey33, const std::vector<uint8_t>& sig64) {
    auto p = popc_v15_encode_event(PopcEventType::Activate, cid, owner, model, end_height);
    _put_le64(p, balance_mg);
    _put_le64(p, attest_height);
    p.insert(p.end(), pubkey33.begin(), pubkey33.end());
    p.insert(p.end(), sig64.begin(), sig64.end());
    return p;
}

// Pure decode: payload bytes (+ the block height the carrier was seen at) → event.
// ok=false on any malformed / wrong-magic / wrong-version / wrong-length payload.
inline PopcV15Carrier popc_v15_decode_carrier(const std::vector<uint8_t>& p, int64_t block_height) {
    PopcV15Carrier c;
    if (p.size() < POPC_V15_CARRIER_BASE_LEN) return c;
    for (size_t i = 0; i < 4; ++i) if (p[i] != POPC_V15_MAGIC[i]) return c;   // domain separation
    if (p[4] != POPC_V15_CARRIER_VERSION) return c;                          // version
    uint8_t type = p[5], model = p[6];
    if (type > (uint8_t)PopcEventType::Settle) return c;                     // unknown event type
    if (model > 1) return c;                                                 // model A=0 / B=1
    PopcV15Event e;
    e.type = (PopcEventType)type; e.model = model; e.height = block_height;
    for (int i = 0; i < 32; ++i) e.commitment_id[(size_t)i] = p[7 + (size_t)i];
    for (int i = 0; i < 20; ++i) e.owner_pkh[(size_t)i]     = p[39 + (size_t)i];
    e.end_height = _get_le64(p, 59);
    c.event = e;
    if ((PopcEventType)type == PopcEventType::Activate) {
        if (p.size() != POPC_V15_CARRIER_ATTEST_LEN) return c;              // attest needs exact length
        c.has_attest = true;
        c.balance_mg    = _get_le64(p, 67);
        c.attest_height = _get_le64(p, 75);
        c.pubkey.assign(p.begin() + 83,  p.begin() + 83 + 33);
        c.sig.assign(   p.begin() + 116, p.begin() + 116 + 64);
    } else if (p.size() == POPC_V15_CARRIER_SIGNED_LEN) {
        // P4c — owner-authorized non-attest carrier: base + pubkey(33) + sig(64).
        c.has_sig = true;
        c.pubkey.assign(p.begin() + 67, p.begin() + 67 + 33);
        c.sig.assign(   p.begin() + 100, p.begin() + 100 + 64);
    } else {
        if (p.size() != POPC_V15_CARRIER_BASE_LEN) return c;                // otherwise must be exact base
    }
    c.ok = true;
    return c;
}

// Is this output a PoPC V15 carrier? (0-value, marker pkh, magic prefix.)
inline bool popc_v15_is_carrier_output(const TxOutput& o) {
    return o.amount == 0 && o.pubkey_hash == POPC_V15_MARKER_PKH && o.payload.size() >= 4
        && o.payload[0] == POPC_V15_MAGIC[0] && o.payload[1] == POPC_V15_MAGIC[1]
        && o.payload[2] == POPC_V15_MAGIC[2] && o.payload[3] == POPC_V15_MAGIC[3];
}
inline PopcV15Carrier popc_v15_decode_output(const TxOutput& o, int64_t block_height) {
    if (!popc_v15_is_carrier_output(o)) return PopcV15Carrier{};
    return popc_v15_decode_carrier(o.payload, block_height);
}

} // namespace sost
