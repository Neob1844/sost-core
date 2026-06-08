// gv_g5.h — V15 Gold Vault governance G5: transitional Guardian veto.
//
// G5 is the LAST and most sensitive layer of Gold Vault governance: a strictly
// TEMPORARY developer/genesis veto over Gold Vault spends. It is deliberately
// boxed in so it can never become a permanent control door:
//
//   * silence = accept  — a G4-approved spend stands UNLESS an explicit, valid
//     veto lands in the grace window. The Guardian cannot *force* a spend, only
//     *block* one.
//   * grace window       — GV_G5_GRACE_BLOCKS (10) blocks preceding the spend.
//   * AUTO-DISCONNECT     — at height GV_G5_AUTO_DISCONNECT_HEIGHT (100,000) the
//     Guardian turns OFF forever: gv_g5_active_at() returns false and any veto
//     is ignored. No key, no flag, no vote can re-enable it.
//   * signed              — a veto is an ECDSA pronouncement by the hardcoded
//     Guardian key (see gv_g5.cpp); a coinbase marker alone is NOT enough.
//   * replay-safe         — the signed digest commits to (vetoed destination pkh
//     + expiry height) under a domain tag, so a veto cannot be reused for a
//     different destination or after it expires.
//
// Gate: DEFERRED on mainnet (INT64_MAX); ACTIVE on the testnet build
// (-DSOST_TESTNET_FORKS, at V15_HEIGHT) to dry-run. This is part of the V15
// automation bundle (block 20,000), NOT V14. See docs/V14_EXECUTION_PLAN.md.
#pragma once
#include "sost/params.h"
#include "sost/crypto.h"        // sha256
#include "sost/transaction.h"   // PubKeyHash via tx types
#include "sost/tx_signer.h"     // PubKeyHash
#include <cstdint>
#include <climits>
#include <array>
#include <vector>
#include <string>

namespace sost {

inline constexpr int32_t GV_G5_GRACE_BLOCKS          = 10;       // veto grace window (preceding blocks)
inline constexpr int64_t GV_G5_AUTO_DISCONNECT_HEIGHT = 100000;  // Guardian dies here, forever

// Coinbase marker pkh that CARRIES a veto (the signature + expiry live in the
// marker output's payload; see the W4 wiring). 20 ASCII bytes, unspendable.
inline constexpr std::array<uint8_t,20> GV_G5_VETO_PKH = {
    'G','V','-','G','5','-','V','E','T','O','-','M','A','R','K','E','R','-','0','1' };

// Activation gate. Testnet active @ V15_HEIGHT; mainnet deferred (INT64_MAX → V15
// in the final commit). ALWAYS false at/after the auto-disconnect height — that
// cut-off is unconditional and is the whole point of a *transitional* Guardian.
#ifdef SOST_TESTNET_FORKS
inline constexpr int64_t GV_G5_ACTIVATION_HEIGHT = V15_HEIGHT;
#else
inline constexpr int64_t GV_G5_ACTIVATION_HEIGHT = INT64_MAX;  // -> V15_HEIGHT in final commit
#endif

inline constexpr bool gv_g5_active_at(int64_t height) {
    return height >= GV_G5_ACTIVATION_HEIGHT
        && height <  GV_G5_AUTO_DISCONNECT_HEIGHT;   // auto-disconnect: hard, unconditional
}

// Domain tag — keeps a G5 veto signature from ever being valid in any other
// context (beacon, tx sighash, G4, etc.).
inline constexpr char GV_G5_DOMAIN[] = "SOST/GV-G5-VETO/v1";

// Deterministic digest the Guardian signs to veto spends to `dest_pkh` up to and
// including block `expiry_height`:  sha256( DOMAIN || dest_pkh(20) || expiry(8 LE) ).
inline Bytes32 gv_g5_veto_digest(const PubKeyHash& dest_pkh, int64_t expiry_height) {
    std::vector<uint8_t> m;
    m.reserve(sizeof(GV_G5_DOMAIN) - 1 + 20 + 8);
    for (size_t i = 0; i + 1 < sizeof(GV_G5_DOMAIN); ++i) m.push_back((uint8_t)GV_G5_DOMAIN[i]);
    for (uint8_t b : dest_pkh) m.push_back(b);
    for (int i = 0; i < 8; ++i) m.push_back((uint8_t)((uint64_t)expiry_height >> (8 * i)));
    return sha256(m.data(), m.size());
}

// Pure decision (silence = accept). `valid_veto_present` is true iff the wiring
// found a Guardian-signed, unexpired veto for this spend's destination in the
// grace window. Returns true iff the spend MUST be blocked.
inline constexpr bool gv_g5_spend_blocked(bool g5_active, bool valid_veto_present) {
    return g5_active && valid_veto_present;   // no veto → not blocked (silence = accept)
}

// Is the marker output a G5 veto carrier? (0-value output to GV_G5_VETO_PKH whose
// payload is at least an 8-byte expiry + a signature.) Pure shape check; the
// signature itself is verified in gv_g5.cpp.
inline bool gv_g5_is_veto_output(const TxOutput& o) {
    return o.amount == 0 && o.pubkey_hash == GV_G5_VETO_PKH && o.payload.size() >= 8 + 8;
}

// ---- signature verification lives in gv_g5.cpp (needs secp256k1) -------------
// Verify a Guardian veto: the payload is [expiry_height u64 LE][ECDSA sig...].
// Returns true iff (a) G5 is active at `spend_height`, (b) expiry_height >=
// spend_height (not expired), and (c) the signature over gv_g5_veto_digest(
// dest_pkh, expiry_height) verifies against the Guardian pubkey. `guardian_pubkey_hex`
// defaults to the hardcoded Guardian key; overridable for tests.
extern const char* GV_G5_GUARDIAN_PUBKEY;  // defined in gv_g5.cpp (= Beacon II-A operator key)

bool gv_g5_verify_veto_payload(const PubKeyHash& dest_pkh,
                               int64_t spend_height,
                               const std::vector<uint8_t>& payload,
                               const std::string& guardian_pubkey_hex);
bool gv_g5_verify_veto_payload(const PubKeyHash& dest_pkh,
                               int64_t spend_height,
                               const std::vector<uint8_t>& payload);  // default Guardian key

} // namespace sost
