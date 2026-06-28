// Phase 4C-1 — Atomic Swap Coordinator state-machine tests.
//
// 30 assertions covering: linear-flow transitions, timeout fork,
// failure terminal, invalid timeout order, preimage idempotence,
// terminal-state idempotence, gate guarantees (SOST consensus gate
// stays INT64_MAX, BTC signing backend stays OFF).

#include "sost/atomic_swap_coordinator.h"
#include "sost/atomic_swap.h"
#include "sost/atomic_swap_btc_signing.h"

#include <climits>
#include <cstdio>
#include <string>

using namespace sost::atomic_swap;
using namespace sost::atomic_swap::coordinator;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

static SwapParams init_params(Role role = Role::Initiator) {
    SwapParams p;
    p.role = role;
    p.sost_refund_opens_after_counterparty = (role == Role::Initiator);
    p.observed_safety_margin_blocks = 12;
    p.safety_margin_min_blocks = 6;
    return p;
}

int main() {
    printf("\n== Atomic Swap Coordinator Phase 4C-1 ==\n\n");

    // -----------------------------------------------------------------
    // Compile-time / runtime gate guarantees
    // -----------------------------------------------------------------

    // T14. SOST consensus activation gate is the V14.5 activation height. The
    //      HTLC was originally declared at V14 (15000) but was non-functional on
    //      the block path (CLAIM/REFUND rejected as non-standard); the corrected,
    //      complete HTLC feature activates together at the dedicated V14.5
    //      milestone (mainnet 16000), SEPARATE from the V15 automation bundle.
    static_assert(sost::ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == sost::V14_5_HEIGHT,
                  "Atomic-swap gate must equal V14_5_HEIGHT (V14.5 HTLC fix activation)");
    TEST("T14 SOST consensus gate ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == V14_5_HEIGHT",
         sost::ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT == sost::V14_5_HEIGHT);

    // T15. BTC signing backend stays disabled.
    TEST("T15 BTC signing backend OFF (IsBtcHtlcSigningEnabled == false)",
         sost::atomic_swap::btc::IsBtcHtlcSigningEnabled() == false);

    // -----------------------------------------------------------------
    // T1 — Draft -> AwaitingSostLock after CreateSession (happy)
    // -----------------------------------------------------------------
    {
        Coordinator c;
        TEST("T1a fresh coordinator starts in Draft",
             c.current_state() == State::Draft);
        auto r = c.CreateSession(init_params(Role::Initiator));
        TEST("T1b CreateSession ok",
             r.ok && r.new_state == State::AwaitingSostLock);
        TEST("T1c session_created flag set", c.session_created());
        TEST("T1d timeout order valid", c.timeout_order_valid());
        TEST("T1e no risk flags", c.risk_flags().empty());
    }

    // -----------------------------------------------------------------
    // T2 — SOST lock seen -> AwaitingCounterpartyLock
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        auto r = c.Apply(Event::MarkSostLockSeen);
        TEST("T2 SOST lock seen -> AwaitingCounterpartyLock",
             r.ok && r.new_state == State::AwaitingCounterpartyLock);
    }

    // -----------------------------------------------------------------
    // T3 — both locks seen -> BothLocked
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        auto r = c.Apply(Event::MarkCounterpartyLockSeen);
        TEST("T3 both locks seen -> BothLocked",
             r.ok && r.new_state == State::BothLocked);
    }

    // -----------------------------------------------------------------
    // T4 — preimage known -> ClaimReady (only after both locks)
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        c.Apply(Event::MarkCounterpartyLockSeen);
        auto r = c.Apply(Event::MarkPreimageKnown);
        TEST("T4 preimage known after BothLocked -> ClaimReady",
             r.ok && r.new_state == State::ClaimReady);
    }

    // -----------------------------------------------------------------
    // T5 — claim path completes -> Claimed
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        c.Apply(Event::MarkCounterpartyLockSeen);
        c.Apply(Event::MarkPreimageKnown);
        auto r = c.Apply(Event::MarkCounterpartyClaimSeen);
        TEST("T5 ClaimReady -> Claimed",
             r.ok && r.new_state == State::Claimed);
    }

    // -----------------------------------------------------------------
    // T6 — refund timeout path -> RefundAvailable
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        c.Apply(Event::MarkCounterpartyLockSeen);   // BothLocked
        auto r = c.Apply(Event::MarkTimeoutReached);
        TEST("T6 BothLocked + timeout -> RefundAvailable",
             r.ok && r.new_state == State::RefundAvailable);
    }

    // -----------------------------------------------------------------
    // T7 — refund path completes -> Refunded
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        c.Apply(Event::MarkCounterpartyLockSeen);
        c.Apply(Event::MarkTimeoutReached);   // RefundAvailable
        auto r = c.Apply(Event::MarkSostRefundSeen);
        TEST("T7 RefundAvailable + SostRefundSeen -> Refunded",
             r.ok && r.new_state == State::Refunded);
    }

    // -----------------------------------------------------------------
    // T8 — wrong transition rejected
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        auto r = c.Apply(Event::MarkSostClaimSeen);  // illegal from AwaitingSostLock
        TEST("T8 illegal MarkSostClaimSeen from AwaitingSostLock rejected",
             !r.ok && r.new_state == State::AwaitingSostLock);
    }

    // -----------------------------------------------------------------
    // T9 — duplicate terminal event idempotent
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkFailure);  // Failed
        auto r1 = c.Apply(Event::MarkFailure);
        TEST("T9a MarkFailure on Failed is idempotent",
             r1.ok && r1.new_state == State::Failed);
        auto r2 = c.Apply(Event::MarkSostLockSeen);
        TEST("T9b non-failure event on Failed rejected",
             !r2.ok && c.current_state() == State::Failed);
    }

    // -----------------------------------------------------------------
    // T10 — timeout order invalid rejected
    // -----------------------------------------------------------------
    {
        // Initiator with sost_refund_opens_after_counterparty = false
        // is the classic "broken atomicity" case.
        SwapParams bad = init_params(Role::Initiator);
        bad.sost_refund_opens_after_counterparty = false;
        Coordinator c;
        auto r = c.CreateSession(bad);
        TEST("T10a CreateSession with invalid timeout returns ok but stays in Draft",
             r.ok && r.new_state == State::Draft);
        TEST("T10b timeout_order_valid() == false", !c.timeout_order_valid());
        TEST("T10c risk_flags contains TIMEOUT_ORDER_INVALID",
             !c.risk_flags().empty() &&
             c.risk_flags()[0].find("TIMEOUT_ORDER_INVALID") != std::string::npos);
        auto r2 = c.Apply(Event::MarkSostLockSeen);
        TEST("T10d Apply refused while timeout invalid",
             !r2.ok && c.current_state() == State::Draft);
    }

    // -----------------------------------------------------------------
    // T11 — preimage before both locks does not move to ClaimReady
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);  // AwaitingCounterpartyLock
        auto r = c.Apply(Event::MarkPreimageKnown);
        TEST("T11a preimage in AwaitingCounterpartyLock keeps state",
             r.ok && r.new_state == State::AwaitingCounterpartyLock);
        TEST("T11b preimage_known() flag is set", c.preimage_known());
        // Now the counterparty lock arrives; we should jump straight
        // to ClaimReady (BothLocked is skipped because we already
        // have the preimage).
        auto r2 = c.Apply(Event::MarkCounterpartyLockSeen);
        TEST("T11c counterparty lock with preimage already known -> ClaimReady",
             r2.ok && r2.new_state == State::ClaimReady);
    }

    // -----------------------------------------------------------------
    // T12 — failure state terminal
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        c.Apply(Event::MarkSostLockSeen);
        c.Apply(Event::MarkCounterpartyLockSeen);
        c.Apply(Event::MarkFailure);
        TEST("T12a MarkFailure from BothLocked -> Failed",
             c.current_state() == State::Failed);
        auto r = c.Apply(Event::MarkPreimageKnown);
        TEST("T12b further non-failure events rejected on Failed",
             !r.ok && c.current_state() == State::Failed);
    }

    // -----------------------------------------------------------------
    // T13 — coordinator API has no IO / network surface
    //       (compile-time check + presence of accessors only)
    // -----------------------------------------------------------------
    {
        Coordinator c;
        TEST("T13a current_state() returns Draft pre-session",
             c.current_state() == State::Draft);
        TEST("T13b next_safe_action() returns guidance pre-session",
             !c.next_safe_action().empty());
        TEST("T13c required_user_confirmation() initially true",
             c.required_user_confirmation());
        TEST("T13d recovery_path() returns guidance pre-session",
             !c.recovery_path().empty());
        TEST("T13e risk_flags() returns vector pre-session",
             c.risk_flags().empty());
    }

    // -----------------------------------------------------------------
    // Extra — Responder role timeout-ordering rule reversed
    // -----------------------------------------------------------------
    {
        SwapParams resp = init_params(Role::Responder);
        // For Responder: sost_refund_opens_after_counterparty must be FALSE.
        // init_params() with Role::Responder sets it to false (correct).
        Coordinator c;
        auto r = c.CreateSession(resp);
        TEST("ExtraR1 Responder with correct ordering -> AwaitingSostLock",
             r.ok && r.new_state == State::AwaitingSostLock);
        TEST("ExtraR2 timeout_order_valid for Responder", c.timeout_order_valid());

        // Responder with WRONG ordering (= sost_refund_opens_after_counterparty true)
        SwapParams resp_bad = init_params(Role::Responder);
        resp_bad.sost_refund_opens_after_counterparty = true;
        Coordinator c2;
        c2.CreateSession(resp_bad);
        TEST("ExtraR3 Responder with wrong ordering -> Draft + risk_flag",
             c2.current_state() == State::Draft &&
             !c2.timeout_order_valid());
    }

    // -----------------------------------------------------------------
    // Extra — safety margin too small
    // -----------------------------------------------------------------
    {
        SwapParams p = init_params(Role::Initiator);
        p.observed_safety_margin_blocks = 3;  // below default min 6
        Coordinator c;
        c.CreateSession(p);
        TEST("ExtraM1 small margin -> timeout_order_invalid",
             !c.timeout_order_valid());
        bool found_margin_flag = false;
        for (auto& f : c.risk_flags())
            if (f.find("TIMEOUT_MARGIN_TOO_SMALL") != std::string::npos)
                found_margin_flag = true;
        TEST("ExtraM2 risk_flags contains TIMEOUT_MARGIN_TOO_SMALL",
             found_margin_flag);
    }

    // -----------------------------------------------------------------
    // Extra — CreateSession twice rejected
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());
        auto r = c.CreateSession(init_params());
        TEST("ExtraS1 CreateSession twice rejected",
             !r.ok && r.error.find("already") != std::string::npos);
    }

    // -----------------------------------------------------------------
    // Extra — Apply before CreateSession rejected
    // -----------------------------------------------------------------
    {
        Coordinator c;
        auto r = c.Apply(Event::MarkSostLockSeen);
        TEST("ExtraA1 Apply before CreateSession rejected",
             !r.ok && r.error.find("not created") != std::string::npos);
    }

    // -----------------------------------------------------------------
    // Extra — Expired terminal (pre-lock timeout)
    // -----------------------------------------------------------------
    {
        Coordinator c;
        c.CreateSession(init_params());  // AwaitingSostLock
        auto r = c.Apply(Event::MarkTimeoutReached);
        TEST("ExtraE1 timeout in AwaitingSostLock -> Expired",
             r.ok && r.new_state == State::Expired);
        auto r2 = c.Apply(Event::MarkSostLockSeen);
        TEST("ExtraE2 Expired is terminal", !r2.ok);
    }

    printf("\n== Summary: %d passed, %d failed ==\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
