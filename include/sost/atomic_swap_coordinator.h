// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap — local cross-chain coordinator state machine (Phase 4C-1)
// =============================================================================
//
// PURE LOCAL LOGIC. This module is a deterministic state machine that
// helps the wallet / UI keep track of where a swap currently is. It
// does NOT:
//
//   - move funds, ever
//   - sign any transaction
//   - broadcast any transaction
//   - observe BTC / Ethereum / any other chain
//   - hold or read any private key
//   - open any network socket / HTTP / RPC connection
//   - decide prices
//   - resolve disputes
//   - change SOST consensus in any way
//
// What it DOES:
//
//   - Accept events ("the wallet has observed that the SOST LOCK is
//     confirmed", "the wallet has observed the counterparty LOCK",
//     "the wallet has the preimage", ...) supplied by OTHER modules
//     that have already verified the underlying chain data.
//   - Refuse out-of-order or invalid events.
//   - Surface to the UI the current state, the next safe user action,
//     a recovery path if things go wrong, and any risk flags.
//   - Pre-compute timeout-order safety at session creation time: if
//     the wallet supplied an unsafe timeout ordering for the swap
//     role (Initiator's refund must open LAST, Responder's must open
//     FIRST), the coordinator refuses to advance past the Draft state
//     and surfaces the risk flag.
//
// The SOST consensus activation gate
// (ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT in include/sost/atomic_swap.h)
// stays at INT64_MAX (sentinel OFF). The BTC signing build flag
// SOST_BTC_HTLC_SIGNING stays OFF. The coordinator does NOT depend
// on either being flipped — it can be used for UI mock-ups, dry runs,
// and educational walk-throughs without any chain being involved.
// When the real backend(s) ship, the coordinator becomes the wiring
// between the wallet's chain observations and the user-facing flow.
// =============================================================================
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace coordinator {

// -----------------------------------------------------------------------------
// States
// -----------------------------------------------------------------------------
//
// Linear-by-default flow (Initiator perspective):
//
//   Draft
//     │ CreateSession(params)
//     ▼
//   AwaitingSostLock
//     │ MarkSostLockSeen
//     ▼
//   AwaitingCounterpartyLock
//     │ MarkCounterpartyLockSeen
//     ▼
//   BothLocked
//     │ MarkPreimageKnown
//     ▼
//   ClaimReady
//     │ MarkCounterpartyClaimSeen (initiator claims counterparty side,
//     │                            revealing the preimage on-chain)
//     ▼
//   Claimed (terminal)
//
// Refund branch — reachable from any pre-Claimed state via timeout:
//
//   * --MarkTimeoutReached--> RefundAvailable
//   RefundAvailable --MarkSostRefundSeen|MarkCounterpartyRefundSeen--> Refunded
//
// Fault branch — reachable from any non-terminal state:
//
//   * --MarkFailure--> Failed (terminal)
//   * --pre-Lock timeout--> Expired (terminal)
//
enum class State {
    Draft,
    AwaitingSostLock,
    AwaitingCounterpartyLock,
    BothLocked,
    ClaimReady,
    Claimed,                  // terminal
    RefundAvailable,
    Refunded,                 // terminal
    Expired,                  // terminal
    Failed                    // terminal
};

// -----------------------------------------------------------------------------
// Events
// -----------------------------------------------------------------------------
enum class Event {
    CreateSession,                  // initial event with SwapParams
    MarkSostLockSeen,
    MarkCounterpartyLockSeen,
    MarkPreimageKnown,
    MarkSostClaimSeen,              // someone (us or counterparty) claimed SOST
    MarkCounterpartyClaimSeen,      // someone (us or counterparty) claimed counterparty
    MarkSostRefundSeen,
    MarkCounterpartyRefundSeen,
    MarkTimeoutReached,
    MarkFailure
};

// -----------------------------------------------------------------------------
// Role + SwapParams
// -----------------------------------------------------------------------------
enum class Role { Initiator, Responder };

// Atomic-swap timeout discipline (the wallet must enforce; this struct
// records the wallet's pre-computed view so the coordinator can flag
// unsafe orderings):
//
//   - Initiator locks first; their refund window must OPEN LAST so
//     the responder has time to complete the swap.
//   - Responder locks second; their refund window must OPEN FIRST so
//     the responder has time to refund before the initiator can claim
//     unilaterally.
//
// The booleans below are the wallet's normalised statement (the
// coordinator has no view into either chain). If both chains have
// different block times, the wallet must convert to a normalised
// comparison before populating these fields.
//
struct SwapParams {
    Role role = Role::Initiator;

    // True iff the wallet has verified that the SOST refund window
    // opens AFTER the counterparty refund window (on a common time
    // axis).
    bool sost_refund_opens_after_counterparty = false;

    // The wallet's observation of the gap between the two refund
    // windows, in normalised "blocks" (the wallet's chosen
    // normalisation; conventionally the slower chain's block count).
    // The coordinator requires this to be >= safety_margin_min_blocks
    // (default 6) before allowing advance past Draft.
    int64_t observed_safety_margin_blocks = 0;

    // Minimum safety margin the coordinator will accept.
    int64_t safety_margin_min_blocks = 6;
};

// -----------------------------------------------------------------------------
// TransitionResult
// -----------------------------------------------------------------------------
struct TransitionResult {
    bool        ok = false;
    std::string error;          // non-empty when ok == false
    State       new_state = State::Draft;
};

// -----------------------------------------------------------------------------
// Coordinator
// -----------------------------------------------------------------------------
class Coordinator {
public:
    Coordinator();

    // Initialise the session. After this call the state is either
    // AwaitingSostLock (if params validate) or Draft (if params are
    // unsafe; risk_flags() will explain why). Calling CreateSession
    // twice on the same Coordinator is rejected.
    TransitionResult CreateSession(const SwapParams& params);

    // Apply an event. Returns ok=true on a legal transition; ok=false
    // with an explanatory error on any illegal or out-of-order event.
    // Idempotent for terminal events on terminal states (returns ok
    // with the same state).
    TransitionResult Apply(Event event);

    // Accessors — pure functions of the internal state.
    State                    current_state() const { return state_; }
    std::string              next_safe_action() const;
    bool                     required_user_confirmation() const;
    std::string              recovery_path() const;
    bool                     timeout_order_valid() const { return timeout_order_valid_; }
    std::vector<std::string> risk_flags() const { return risk_flags_; }
    bool                     session_created() const   { return session_created_; }
    bool                     preimage_known() const    { return preimage_known_; }

    // Static helpers — useful for UI.
    static const char* StateName(State s);
    static const char* EventName(Event e);

private:
    bool                     session_created_ = false;
    State                    state_ = State::Draft;
    SwapParams               params_{};
    bool                     timeout_order_valid_ = false;
    bool                     preimage_known_ = false;
    std::vector<std::string> risk_flags_;

    // Recompute timeout-order validity from params_.
    void evaluate_timeout_order_();
};

} // namespace coordinator
} // namespace atomic_swap
} // namespace sost
