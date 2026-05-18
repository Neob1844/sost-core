// gold_vault_slice1.cpp — Slice 1 mirror whitelist + cross-check + lookup helper
//
// Companion to include/sost/gold_vault_slice1.h. Defines:
//   - GV_SLICE1_WHITELIST_MIRROR_DATA (the mirror whitelist content)
//   - gv_slice1_whitelists_agree() (G2 cross-check)
//   - gv_slice1_destination_allowed() (G1 + G2 destination check)
//
// Default state: both whitelists empty, agreement vacuously true, every
// destination check returns false (no destination is "in" an empty list).
// Combined with GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX in the header,
// the validator wiring is a complete no-op until the operator commits
// real values.
//
// Safety contract:
//   - No private keys, no signing, no wallet, no broadcast.
//   - No network, no I/O, no shell.
//   - Pure functions only; the only file-scope state is the const arrays
//     baked at compile time by the operator's future commit.
//
#include "sost/gold_vault_slice1.h"
#include "sost/consensus_constants.h"

#include <cstring>

namespace sost {

// =========================================================================
// MIRROR whitelist content (G2 dual source of truth)
// =========================================================================
//
// Default: empty. The follow-up commit that activates Slice 1 fills this
// in, AND fills GV_SLICE1_WHITELIST_PRIMARY in the header with the SAME
// set in the SAME order, AND sets GV_SLICE1_WHITELIST_MIRROR_LEN.
//
// Why this is a separate translation unit: G2's "dual whitelist" defense
// requires that two independent constant tables exist in two independent
// files. If one is edited and the other is forgotten, the validator
// rejects every vault spend until the mismatch is fixed.
//
// The empty definition below compiles cleanly with
// GV_SLICE1_WHITELIST_MIRROR_LEN == 0; the [1] is a placeholder so the
// array is well-formed (a zero-length array is not allowed in C++).
// The .agree() function only iterates over GV_SLICE1_WHITELIST_MIRROR_LEN
// entries, so the placeholder row at index 0 is never read at len = 0.
//
const unsigned char GV_SLICE1_WHITELIST_MIRROR_DATA[][20] = {
    // intentionally empty until the operator commits real values
    { 0,0,0,0,0,0,0,0,0,0, 0,0,0,0,0,0,0,0,0,0 }   // placeholder; never read at len=0
};

// =========================================================================
// G2: do the primary and mirror whitelists agree?
// =========================================================================
bool gv_slice1_whitelists_agree() {
    // Length must match.
    if (GV_SLICE1_WHITELIST_PRIMARY_LEN != GV_SLICE1_WHITELIST_MIRROR_LEN) {
        return false;
    }
    // Element-by-element comparison.
    for (std::size_t i = 0; i < GV_SLICE1_WHITELIST_PRIMARY_LEN; ++i) {
        if (std::memcmp(
                GV_SLICE1_WHITELIST_PRIMARY[i].data(),
                GV_SLICE1_WHITELIST_MIRROR_DATA[i],
                GV_SLICE1_PKH_LEN) != 0) {
            return false;
        }
    }
    return true;
}

// =========================================================================
// G1 + G2: is `dest` in the (agreed) whitelist?
// =========================================================================
bool gv_slice1_destination_allowed(const PubKeyHash& dest) {
    // Fail-closed: if the two whitelists disagree, every destination is
    // rejected. This catches operator misconfiguration (PRIMARY edited
    // but MIRROR forgotten, or vice versa) before it becomes a silent
    // consensus split.
    if (!gv_slice1_whitelists_agree()) {
        return false;
    }
    // Empty whitelist: nothing is in it. The validator wiring MUST gate
    // on gv_slice1_active_at(height) FIRST so this empty-whitelist case
    // only matters if the operator has activated Slice 1 without filling
    // the whitelist (a misconfiguration — fail closed).
    for (std::size_t i = 0; i < GV_SLICE1_WHITELIST_PRIMARY_LEN; ++i) {
        if (dest == GV_SLICE1_WHITELIST_PRIMARY[i]) {
            return true;
        }
    }
    return false;
}

} // namespace sost
