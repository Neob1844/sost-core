// dtd_control.cpp — pure reference implementation of the DTD lottery
// emergency pause/resume control state machine. See include/sost/dtd_control.h
// for the contract and docs/DTD_EMERGENCY_PAUSE_RESUME_DESIGN.md for rationale.
//
// PURE: no I/O, no chain-state access, no secp context. Signature
// verification is supplied by the caller (the `signature_valid` argument).

#include "sost/dtd_control.h"

#include <string>

namespace sost::dtd_control {

const char* action_str(DTDAction a) {
    switch (a) {
        case DTDAction::PAUSE_DTD:  return "PAUSE_DTD";
        case DTDAction::RESUME_DTD: return "RESUME_DTD";
        case DTDAction::NONE:       return "NONE";
    }
    return "NONE";
}

std::string canonical_payload(const DTDControlMessage& m) {
    // Fixed field order, fixed encodings. Decimal for integers, lowercase
    // hex (via sost::hex) for the 32-byte fields. Newline-separated so the
    // preimage is human-auditable and byte-stable across architectures.
    std::string s;
    s += DTD_CONTROL_MAGIC;                       s += '\n';
    s += "version=";           s += std::to_string(m.version);          s += '\n';
    s += "chain=";             s += sost::hex(m.chain_tag);             s += '\n';
    s += "action=";            s += action_str(m.action);              s += '\n';
    s += "effective_height=";  s += std::to_string(m.effective_height); s += '\n';
    s += "nonce=";             s += std::to_string(m.nonce);            s += '\n';
    s += "reason_hash=";       s += sost::hex(m.reason_hash);          s += '\n';
    s += "created_at_height="; s += std::to_string(m.created_at_height);s += '\n';
    s += "expiry_height=";     s += std::to_string(m.expiry_height);    s += '\n';
    s += "key_id=";            s += std::to_string((unsigned)m.key_id); s += '\n';
    return s;
}

DTDApplyResult apply_dtd_control(DTDControlState&         state,
                                 const DTDControlMessage& m,
                                 bool                     signature_valid,
                                 const Bytes32&           expected_chain_tag,
                                 int64_t                  current_tip_height) {
    DTDApplyResult r;
    r.prev = state;            // snapshot for undo / diagnostics
    r.state_changed = false;

    // 1) Signature. Fail-closed: an unverifiable message never moves state.
    if (!signature_valid) {
        r.code = DTDApplyCode::REJECTED_BAD_SIG;
        return r;
    }
    // 2) Chain binding.
    if (m.chain_tag != expected_chain_tag) {
        r.code = DTDApplyCode::REJECTED_WRONG_CHAIN;
        return r;
    }
    // 3) Action must be a defined control verb.
    if (m.action != DTDAction::PAUSE_DTD && m.action != DTDAction::RESUME_DTD) {
        r.code = DTDApplyCode::REJECTED_BAD_ACTION;
        return r;
    }
    // 4) Minimum activation height — a control may not take effect before the
    //    coordinated fork height the mechanism was enabled at.
    if (m.effective_height < sost::DTD_EMERGENCY_CONTROL_MIN_HEIGHT) {
        r.code = DTDApplyCode::REJECTED_BELOW_MIN;
        return r;
    }
    // 5) Expiry (0 = never). Rejected once the tip has reached expiry.
    if (m.expiry_height != 0 && current_tip_height >= m.expiry_height) {
        r.code = DTDApplyCode::REJECTED_EXPIRED;
        return r;
    }
    // 6) Replay protection: strictly-increasing nonce. Equal or lower nonce is
    //    a replay and is rejected; state is unchanged.
    if (m.nonce <= state.last_nonce) {
        r.code = DTDApplyCode::REJECTED_REPLAY_NONCE;
        return r;
    }

    // Accept. Higher valid nonce supersedes whatever came before.
    state.paused                = (m.action == DTDAction::PAUSE_DTD);
    state.last_nonce            = m.nonce;
    state.last_effective_height = m.effective_height;
    state.last_reason_hash      = m.reason_hash;
    state.last_action           = m.action;

    r.state_changed = true;
    r.code = (m.action == DTDAction::PAUSE_DTD)
                 ? DTDApplyCode::ACCEPTED_PAUSE
                 : DTDApplyCode::ACCEPTED_RESUME;
    return r;
}

void undo_dtd_control(DTDControlState& state, const DTDApplyResult& applied) {
    if (!applied.state_changed) return;   // rejected applies never mutated state
    state = applied.prev;
}

bool is_dtd_emergency_paused_core(const DTDControlState& state, int64_t height) {
    return state.paused && height >= state.last_effective_height;
}

} // namespace sost::dtd_control
