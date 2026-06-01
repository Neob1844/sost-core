#pragma once

// =============================================================================
// dtd_control.h — DTD Lottery Emergency Pause / Resume control signal
//
// Consensus-safe, signature-verified, replay-protected, height-gated and
// reorg-safe control object for pausing / resuming the DTD lottery
// redistribution. Full rationale and the activation procedure are in
// docs/DTD_EMERGENCY_PAUSE_RESUME_DESIGN.md.
//
// STATUS — shipped DEFERRED. The consensus gate
// (sost::DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE in params.h) is false, so
// is_dtd_emergency_paused_at() returns false for every height and
// is_dtd_lottery_active_at() reduces EXACTLY to
// sost::lottery::is_lottery_block(). Nothing in this header changes
// consensus while the flag is false. The functions below are PURE (no I/O,
// no chain-state access, no secp context) and exist so the pause/resume
// logic — message canonicalisation, nonce supersede, reorg undo and the
// single lottery chokepoint — is unit-tested before the flag is ever
// flipped.
//
// Signature verification is deliberately SEPARATE from the state machine:
// apply_dtd_control() consumes a `signature_valid` boolean computed by the
// verify layer (which, at activation, reuses the Beacon 3-of-5 secp256k1
// custody — see beacon.h). Keeping the compiled module crypto-free keeps the
// deferred surface minimal and the state transition exhaustively testable
// (including the invalid-signature rejection path).
// =============================================================================

#include "sost/types.h"
#include "sost/params.h"
#include "sost/lottery.h"   // is_lottery_block (the existing DTD trigger schedule)

#include <cstdint>
#include <string>

namespace sost::dtd_control {

// Canonical magic string committed inside every signed payload.
inline constexpr char DTD_CONTROL_MAGIC[]   = "SOST_DTD_CONTROL_V1";
inline constexpr uint32_t DTD_CONTROL_VERSION = 1;

// Control action. Values are committed inside the signed payload as text
// ("PAUSE_DTD" / "RESUME_DTD") so the on-wire form is human-auditable.
enum class DTDAction : uint8_t {
    NONE       = 0x00,
    PAUSE_DTD  = 0x01,
    RESUME_DTD = 0x02,
};

const char* action_str(DTDAction a);

// -----------------------------------------------------------------------------
// Signed control message (SOST_DTD_CONTROL_V1).
//
//   chain_tag         — binds the message to ONE chain. At activation this is
//                       sha256 over the network MAGIC bytes (params.h
//                       MAGIC_*). A message minted for the wrong network is
//                       rejected deterministically.
//   action            — PAUSE_DTD | RESUME_DTD.
//   effective_height  — height from which the action takes EFFECT. The brake
//                       is applied by is_dtd_emergency_paused_core() only at
//                       height >= effective_height, so a signal can be
//                       published ahead of the height it bites at.
//   nonce             — strictly-increasing replay counter. A message is only
//                       accepted if nonce > DTDControlState::last_nonce.
//   reason_hash       — 32-byte hash of an off-chain human reason note
//                       (advisory; surfaced by explorer/app).
//   created_at_height — height at which the operator minted the message
//                       (audit only).
//   expiry_height     — message is rejected once tip >= expiry_height
//                       (0 = never expires).
//   key_id            — index into the operator custody set (diagnostics).
// -----------------------------------------------------------------------------
struct DTDControlMessage {
    uint32_t  version{DTD_CONTROL_VERSION};
    Bytes32   chain_tag{};
    DTDAction action{DTDAction::NONE};
    int64_t   effective_height{0};
    uint64_t  nonce{0};
    Bytes32   reason_hash{};
    int64_t   created_at_height{0};
    int64_t   expiry_height{0};       // 0 = no expiry
    uint8_t   key_id{0};
};

// Deterministic, byte-stable serialisation of the signed fields. This is the
// exact preimage the operator signs and every node hashes (sha256) before
// verifying against the custody set. Field order and encodings are fixed:
// identical bytes on x86 and ARM for identical input.
std::string canonical_payload(const DTDControlMessage& m);

// -----------------------------------------------------------------------------
// Consensus-visible control state. Persisted in chain state at activation,
// with the pre-block snapshot kept as undo data for reorg safety.
// -----------------------------------------------------------------------------
struct DTDControlState {
    bool      paused{false};
    uint64_t  last_nonce{0};
    int64_t   last_effective_height{0};
    Bytes32   last_reason_hash{};
    DTDAction last_action{DTDAction::NONE};
};

enum class DTDApplyCode : int {
    ACCEPTED_PAUSE        = 0,
    ACCEPTED_RESUME       = 1,
    REJECTED_BAD_SIG      = 2,
    REJECTED_WRONG_CHAIN  = 3,
    REJECTED_BAD_ACTION   = 4,
    REJECTED_BELOW_MIN    = 5,   // effective_height < DTD_EMERGENCY_CONTROL_MIN_HEIGHT
    REJECTED_EXPIRED      = 6,
    REJECTED_REPLAY_NONCE = 7,   // nonce <= last_nonce
};

// Result of applying one control message. `prev` is the full pre-apply state
// snapshot; undo_dtd_control() restores it on reorg. `state_changed` is true
// iff the message was accepted and mutated the state.
struct DTDApplyResult {
    DTDApplyCode    code{DTDApplyCode::REJECTED_BAD_SIG};
    bool            state_changed{false};
    DTDControlState prev{};

    bool accepted() const {
        return code == DTDApplyCode::ACCEPTED_PAUSE ||
               code == DTDApplyCode::ACCEPTED_RESUME;
    }
};

// Apply a control message to `state` deterministically.
//
//   signature_valid     — result of the verify layer (custody-set check).
//                         When false the message is rejected with
//                         REJECTED_BAD_SIG and `state` is untouched.
//   expected_chain_tag  — this chain's tag (sha256 of MAGIC bytes).
//   current_tip_height  — used only for the expiry check.
//
// Rejection order is fixed (signature → chain → action → min-height →
// expiry → nonce). On acceptance the prior state is captured in
// result.prev (undo data) before `state` is updated.
DTDApplyResult apply_dtd_control(DTDControlState&         state,
                                 const DTDControlMessage& m,
                                 bool                     signature_valid,
                                 const Bytes32&           expected_chain_tag,
                                 int64_t                  current_tip_height);

// Reorg undo: restore the pre-apply state captured in `applied`. A no-op when
// the apply did not change state. Symmetric with apply_dtd_control().
void undo_dtd_control(DTDControlState& state, const DTDApplyResult& applied);

// -----------------------------------------------------------------------------
// Effect layer.
// -----------------------------------------------------------------------------

// Pure pause predicate, FLAG-INDEPENDENT: true iff a PAUSE is in force at
// `height` (paused AND height >= last_effective_height). Exposed so the
// state-machine logic is testable regardless of the shipped consensus flag.
bool is_dtd_emergency_paused_core(const DTDControlState& state, int64_t height);

// Consensus-facing pause predicate. While
// sost::DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE is false this ALWAYS returns
// false (no-op), so consensus is unaffected and replay stays bit-identical.
inline bool is_dtd_emergency_paused_at(const DTDControlState& state, int64_t height) {
    if (!sost::DTD_EMERGENCY_CONTROL_CONSENSUS_ACTIVE) return false;
    return is_dtd_emergency_paused_core(state, height);
}

// THE single DTD lottery chokepoint. A block pays out the DTD lottery iff it
// is a scheduled DTD block AND no emergency pause is in force. While the
// consensus flag is false this is identically sost::lottery::is_lottery_block.
//
// Both miner and validator MUST route the DTD payout decision through this
// helper at activation.
inline bool is_dtd_lottery_active_at(int64_t                height,
                                     int64_t                phase2_height,
                                     const DTDControlState& state) {
    return sost::lottery::is_lottery_block(height, phase2_height) &&
           !is_dtd_emergency_paused_at(state, height);
}

} // namespace sost::dtd_control
