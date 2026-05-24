// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// See include/sost/atomic_swap_coordinator.h for the API contract and
// the hard invariants (no IO, no signing, no broadcast, no keys, no
// HTTP, no chain observation). This implementation is pure C++ with
// zero IO of any kind.

#include "sost/atomic_swap_coordinator.h"

namespace sost {
namespace atomic_swap {
namespace coordinator {

Coordinator::Coordinator() = default;

// ---------------------------------------------------------------------------
// Static helpers
// ---------------------------------------------------------------------------

const char* Coordinator::StateName(State s) {
    switch (s) {
        case State::Draft:                     return "Draft";
        case State::AwaitingSostLock:          return "AwaitingSostLock";
        case State::AwaitingCounterpartyLock:  return "AwaitingCounterpartyLock";
        case State::BothLocked:                return "BothLocked";
        case State::ClaimReady:                return "ClaimReady";
        case State::Claimed:                   return "Claimed";
        case State::RefundAvailable:           return "RefundAvailable";
        case State::Refunded:                  return "Refunded";
        case State::Expired:                   return "Expired";
        case State::Failed:                    return "Failed";
    }
    return "?";
}

const char* Coordinator::EventName(Event e) {
    switch (e) {
        case Event::CreateSession:             return "CreateSession";
        case Event::MarkSostLockSeen:          return "MarkSostLockSeen";
        case Event::MarkCounterpartyLockSeen:  return "MarkCounterpartyLockSeen";
        case Event::MarkPreimageKnown:         return "MarkPreimageKnown";
        case Event::MarkSostClaimSeen:         return "MarkSostClaimSeen";
        case Event::MarkCounterpartyClaimSeen: return "MarkCounterpartyClaimSeen";
        case Event::MarkSostRefundSeen:        return "MarkSostRefundSeen";
        case Event::MarkCounterpartyRefundSeen:return "MarkCounterpartyRefundSeen";
        case Event::MarkTimeoutReached:        return "MarkTimeoutReached";
        case Event::MarkFailure:               return "MarkFailure";
    }
    return "?";
}

// ---------------------------------------------------------------------------
// Timeout-order evaluation
// ---------------------------------------------------------------------------
//
// Rules:
//
//   Role::Initiator  -> sost_refund_opens_after_counterparty MUST be true
//                       (their SOST is T1; counterparty is T2; T1 > T2)
//   Role::Responder  -> sost_refund_opens_after_counterparty MUST be false
//                       (their counterparty is T1; SOST is T2; T2 < T1)
//
// AND observed_safety_margin_blocks MUST be >= safety_margin_min_blocks.
//
// When either condition fails we set timeout_order_valid_ = false and
// push a corresponding risk flag. Apply() then refuses to advance past
// Draft.

void Coordinator::evaluate_timeout_order_() {
    timeout_order_valid_ = true;
    risk_flags_.clear();

    if (params_.role == Role::Initiator) {
        if (!params_.sost_refund_opens_after_counterparty) {
            timeout_order_valid_ = false;
            risk_flags_.push_back(
                "TIMEOUT_ORDER_INVALID: Initiator requires SOST refund "
                "to open AFTER counterparty refund (T1_sost > T2_cp); "
                "the wallet reports the opposite.");
        }
    } else {
        if (params_.sost_refund_opens_after_counterparty) {
            timeout_order_valid_ = false;
            risk_flags_.push_back(
                "TIMEOUT_ORDER_INVALID: Responder requires SOST refund "
                "to open BEFORE counterparty refund (T2_sost < T1_cp); "
                "the wallet reports the opposite.");
        }
    }

    if (params_.observed_safety_margin_blocks < params_.safety_margin_min_blocks) {
        timeout_order_valid_ = false;
        risk_flags_.push_back(
            "TIMEOUT_MARGIN_TOO_SMALL: observed_safety_margin_blocks=" +
            std::to_string(params_.observed_safety_margin_blocks) +
            " < safety_margin_min_blocks=" +
            std::to_string(params_.safety_margin_min_blocks));
    }
}

// ---------------------------------------------------------------------------
// CreateSession
// ---------------------------------------------------------------------------

TransitionResult Coordinator::CreateSession(const SwapParams& params) {
    TransitionResult r;
    if (session_created_) {
        r.ok = false;
        r.error = "session already created; create a new Coordinator for a new swap";
        r.new_state = state_;
        return r;
    }
    session_created_ = true;
    params_ = params;
    evaluate_timeout_order_();

    if (!timeout_order_valid_) {
        // Stay in Draft; risk flags explain why. Apply() will refuse
        // any non-failure event until the wallet rebuilds the session
        // with correct params.
        state_ = State::Draft;
        r.ok = true;
        r.error.clear();
        r.new_state = state_;
        return r;
    }

    state_ = State::AwaitingSostLock;
    r.ok = true;
    r.new_state = state_;
    return r;
}

// ---------------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------------
//
// Terminal-state guards (Claimed / Refunded / Expired / Failed):
//   - Any event other than MarkFailure on Failed is rejected.
//   - Re-applying MarkFailure on Failed is idempotent (ok with same state).
//   - Same for Claimed / Refunded / Expired with their own terminal events.

static bool is_terminal(State s) {
    return s == State::Claimed || s == State::Refunded ||
           s == State::Expired || s == State::Failed;
}

TransitionResult Coordinator::Apply(Event event) {
    TransitionResult r;
    r.new_state = state_;

    // CreateSession is not allowed via Apply.
    if (event == Event::CreateSession) {
        r.ok = false;
        r.error = "CreateSession must be invoked via CreateSession(), not Apply()";
        return r;
    }

    if (!session_created_) {
        r.ok = false;
        r.error = "session not created; call CreateSession(...) first";
        return r;
    }

    // Idempotence on terminal states: re-applying the same terminal
    // event is OK; other events on terminal states are rejected.
    if (is_terminal(state_)) {
        if (event == Event::MarkFailure && state_ == State::Failed) {
            r.ok = true; return r;
        }
        if (event == Event::MarkSostClaimSeen && state_ == State::Claimed) {
            r.ok = true; return r;
        }
        if (event == Event::MarkCounterpartyClaimSeen && state_ == State::Claimed) {
            r.ok = true; return r;
        }
        if (event == Event::MarkSostRefundSeen && state_ == State::Refunded) {
            r.ok = true; return r;
        }
        if (event == Event::MarkCounterpartyRefundSeen && state_ == State::Refunded) {
            r.ok = true; return r;
        }
        if (event == Event::MarkTimeoutReached && state_ == State::Expired) {
            r.ok = true; return r;
        }
        r.ok = false;
        r.error = std::string("event ") + EventName(event) +
                  " rejected — state " + StateName(state_) + " is terminal";
        return r;
    }

    // Universal failure path: MarkFailure is always accepted (except on
    // terminal states, handled above) and moves to Failed.
    if (event == Event::MarkFailure) {
        state_ = State::Failed;
        r.ok = true;
        r.new_state = state_;
        return r;
    }

    // If timeout order is invalid, refuse any non-failure event.
    if (!timeout_order_valid_) {
        r.ok = false;
        r.error = "timeout order invalid; advance refused. See risk_flags().";
        return r;
    }

    // Timeout while still pre-Lock => Expired. Timeout in any post-Lock
    // pre-Claimed state => RefundAvailable.
    if (event == Event::MarkTimeoutReached) {
        if (state_ == State::Draft ||
            state_ == State::AwaitingSostLock) {
            state_ = State::Expired;
            r.ok = true;
            r.new_state = state_;
            return r;
        }
        if (state_ == State::AwaitingCounterpartyLock ||
            state_ == State::BothLocked ||
            state_ == State::ClaimReady) {
            state_ = State::RefundAvailable;
            r.ok = true;
            r.new_state = state_;
            return r;
        }
        // already in RefundAvailable -> idempotent
        if (state_ == State::RefundAvailable) {
            r.ok = true;
            return r;
        }
        r.ok = false;
        r.error = "MarkTimeoutReached not applicable in current state";
        return r;
    }

    // Forward-progress transitions (linear flow):
    switch (state_) {
        case State::Draft:
            // From Draft, only MarkFailure / MarkTimeoutReached above
            // are valid; nothing else.
            r.ok = false;
            r.error = std::string("event ") + EventName(event) +
                      " rejected in state Draft";
            return r;

        case State::AwaitingSostLock:
            if (event == Event::MarkSostLockSeen) {
                state_ = State::AwaitingCounterpartyLock;
                r.ok = true; r.new_state = state_; return r;
            }
            if (event == Event::MarkPreimageKnown) {
                // Record the preimage observation but DO NOT advance
                // to ClaimReady until both locks are seen.
                preimage_known_ = true;
                r.ok = true; r.new_state = state_; return r;
            }
            break;

        case State::AwaitingCounterpartyLock:
            if (event == Event::MarkCounterpartyLockSeen) {
                state_ = State::BothLocked;
                // If the preimage was already known (rare but possible
                // for the initiator), jump directly to ClaimReady.
                if (preimage_known_) state_ = State::ClaimReady;
                r.ok = true; r.new_state = state_; return r;
            }
            if (event == Event::MarkPreimageKnown) {
                preimage_known_ = true;
                r.ok = true; r.new_state = state_; return r;
            }
            break;

        case State::BothLocked:
            if (event == Event::MarkPreimageKnown) {
                preimage_known_ = true;
                state_ = State::ClaimReady;
                r.ok = true; r.new_state = state_; return r;
            }
            // Direct claim observation also implies preimage known
            // (the on-chain CLAIM tx reveals it).
            if (event == Event::MarkCounterpartyClaimSeen ||
                event == Event::MarkSostClaimSeen) {
                preimage_known_ = true;
                state_ = State::Claimed;
                r.ok = true; r.new_state = state_; return r;
            }
            break;

        case State::ClaimReady:
            if (event == Event::MarkCounterpartyClaimSeen ||
                event == Event::MarkSostClaimSeen) {
                state_ = State::Claimed;
                r.ok = true; r.new_state = state_; return r;
            }
            break;

        case State::RefundAvailable:
            if (event == Event::MarkSostRefundSeen ||
                event == Event::MarkCounterpartyRefundSeen) {
                state_ = State::Refunded;
                r.ok = true; r.new_state = state_; return r;
            }
            break;

        case State::Claimed:
        case State::Refunded:
        case State::Expired:
        case State::Failed:
            // unreachable — handled by the terminal block above
            break;
    }

    r.ok = false;
    r.error = std::string("event ") + EventName(event) +
              " rejected in state " + StateName(state_);
    return r;
}

// ---------------------------------------------------------------------------
// Accessors / UI hints
// ---------------------------------------------------------------------------

std::string Coordinator::next_safe_action() const {
    if (!session_created_) return "Call CreateSession with the swap parameters.";
    if (!timeout_order_valid_) {
        return "Fix the timeout ordering and re-create the session. "
               "See risk_flags() for details.";
    }
    switch (state_) {
        case State::Draft:
            return "Session in Draft; CreateSession returned without advancing.";
        case State::AwaitingSostLock:
            return params_.role == Role::Initiator
                ? "Build, sign, and broadcast the SOST-side HTLC LOCK transaction."
                : "Wait for the counterparty to broadcast their SOST-side LOCK.";
        case State::AwaitingCounterpartyLock:
            return params_.role == Role::Initiator
                ? "Wait for the counterparty to mirror the LOCK on the counterparty chain."
                : "Build, sign, and broadcast the counterparty-chain HTLC LOCK transaction.";
        case State::BothLocked:
            return params_.role == Role::Initiator
                ? "Reveal the preimage by claiming the counterparty side."
                : "Wait for the initiator to reveal the preimage on the counterparty chain.";
        case State::ClaimReady:
            return params_.role == Role::Initiator
                ? "Broadcast the counterparty-chain CLAIM transaction; the preimage will be revealed."
                : "Broadcast the SOST-side CLAIM transaction using the revealed preimage.";
        case State::Claimed:
            return "Swap complete on the counterparty side. If you are the responder, "
                   "use the revealed preimage to claim the SOST side too.";
        case State::RefundAvailable:
            return "Refund window open. Broadcast your refund on the chain where you locked.";
        case State::Refunded:
            return "Refund complete. No further action.";
        case State::Expired:
            return "Swap expired before locks completed. No further action.";
        case State::Failed:
            return "Swap failed. Refund any side you may have locked.";
    }
    return "";
}

bool Coordinator::required_user_confirmation() const {
    if (!session_created_)           return true;
    if (!timeout_order_valid_)       return false;
    switch (state_) {
        case State::Draft:                    return false;
        case State::AwaitingSostLock:         return params_.role == Role::Initiator;
        case State::AwaitingCounterpartyLock: return params_.role == Role::Responder;
        case State::BothLocked:               return params_.role == Role::Initiator;
        case State::ClaimReady:               return true;
        case State::RefundAvailable:          return true;
        case State::Claimed:                  return params_.role == Role::Responder;
        case State::Refunded:                 return false;
        case State::Expired:                  return false;
        case State::Failed:                   return true;
    }
    return false;
}

std::string Coordinator::recovery_path() const {
    if (!session_created_)
        return "No session yet; nothing to recover.";
    if (!timeout_order_valid_)
        return "Abandon this session and create a new one with correct timeout ordering. "
               "No funds at risk (no LOCK should have been broadcast).";
    switch (state_) {
        case State::Draft:
        case State::AwaitingSostLock:
            return "Safe to abandon. No LOCK on either chain.";
        case State::AwaitingCounterpartyLock:
            return "Your SOST LOCK is on-chain. Wait until the SOST refund_height; "
                   "the SOST-side REFUND will return your funds.";
        case State::BothLocked:
        case State::ClaimReady:
            return "Both LOCKs on-chain. Either complete the CLAIM before the "
                   "earliest refund window opens, OR wait for the appropriate "
                   "refund window and broadcast REFUND on the side you locked.";
        case State::RefundAvailable:
            return "Broadcast REFUND on whichever side you locked. Funds will return "
                   "to the refund pubkey embedded in the LOCK.";
        case State::Claimed:
            return "Counterparty claimed using the revealed preimage. If you are the "
                   "responder you can still use the same preimage to claim your side.";
        case State::Refunded:
            return "Already refunded. Nothing further.";
        case State::Expired:
            return "Pre-lock expiry. No funds were committed.";
        case State::Failed:
            return "Refund any LOCK you broadcast. If no LOCK was broadcast, abandon.";
    }
    return "";
}

} // namespace coordinator
} // namespace atomic_swap
} // namespace sost
