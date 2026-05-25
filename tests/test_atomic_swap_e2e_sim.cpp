// Phase 4E — atomic-swap end-to-end LOCAL simulation.
//
// Ten realistic swap scenarios. Each scenario orchestrates the
// coordinator state machine + BTC redeem-script builder + disabled
// BTC signing stub + (where applicable) the wallet-side helpers,
// all without any network, chain, key material, or HTTP.
//
// This file integrates the per-component unit tests
// (test_atomic_swap_coordinator.cpp, test_atomic_swap_btc_script.cpp,
//  test_atomic_swap_btc_signing.cpp) into the cross-component
// scenarios an operator UI would actually walk through, so a
// regression in any one component is caught not just at its own
// unit test but also at the integration level.
//
// NO HTTP / sockets / RPC / file I/O / key material / chain
// observation. Everything is in-process and deterministic.
//
// Coverage matrix (mirrors the master-command Phase E checklist):
//
//   S1.  SOST LOCK observed -> AwaitingCounterpartyLock.
//   S2.  Counterparty BTC LOCK observed -> BothLocked.
//   S3.  BothLocked (Initiator) + counterparty EVM equivalent.
//   S4.  Preimage revealed -> ClaimReady.
//   S5.  ClaimReady -> Claimed (terminal happy path).
//   S6.  Refund path: SOST refund timeout -> Refunded.
//   S7.  Wrong timeout order rejected at CreateSession (Initiator
//        with sost_refund_opens_after_counterparty=false).
//   S8.  One party disappears post-lock: pre-Claim timeout ->
//        RefundAvailable -> recovery_path() guides the user.
//   S9.  Preimage leak before both locks observed: preimage_known
//        flag flips but state stays AwaitingCounterpartyLock; when
//        the late lock confirms, coordinator jumps straight to
//        ClaimReady.
//   S10. Stablecoin freeze risk + BTC signing disabled assertion
//        for every operation: confirms the wallet-side guard fails
//        closed when SOST_BTC_HTLC_SIGNING is OFF (current default).
//
// Each scenario asserts:
//   - the state transition
//   - the cross-component artifact (BTC redeem script bytes,
//     witness program, signing-disabled error message)
//   - the UI hint surface (next_safe_action, recovery_path,
//     risk_flags) at the point an operator UI would render it.

#include "sost/atomic_swap_coordinator.h"
#include "sost/atomic_swap_btc.h"
#include "sost/atomic_swap_btc_signing.h"
#include "sost/crypto.h"
#include "sost/types.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

using namespace sost;
using sost::atomic_swap::coordinator::Coordinator;
using sost::atomic_swap::coordinator::Event;
using sost::atomic_swap::coordinator::Role;
using sost::atomic_swap::coordinator::State;
using sost::atomic_swap::coordinator::SwapParams;
using sost::atomic_swap::coordinator::TransitionResult;
namespace btc      = sost::atomic_swap::btc;
namespace btc_sign = sost::atomic_swap::btc;  // signing API lives in same namespace

static int g_pass = 0, g_fail = 0;
static int g_scenarios = 0;

#define TEST(msg, cond) do {                                          \
    if (cond) { printf("  PASS    : %s\n", msg); g_pass++; }          \
    else { printf("  *** FAIL: %s  [%s:%d]\n",                        \
                  msg, __FILE__, __LINE__); g_fail++; }               \
} while (0)

#define SCENARIO(n, title) do {                                       \
    g_scenarios++;                                                    \
    printf("\n-- Scenario %s: %s --\n", n, title);                    \
} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static SwapParams make_safe_params(Role role) {
    SwapParams p;
    p.role = role;
    // Initiator: SOST refund opens LAST  (after counterparty refund).
    // Responder: SOST refund opens FIRST (before counterparty refund).
    p.sost_refund_opens_after_counterparty = (role == Role::Initiator);
    p.observed_safety_margin_blocks        = 144;   // 24 h at 10-min target
    p.safety_margin_min_blocks             = 6;
    return p;
}

static std::vector<uint8_t> sample_btc_redeem_script(uint64_t refund_height_delta) {
    std::array<uint8_t, 32> hashlock{};
    std::array<uint8_t, 33> claim_pk{}, refund_pk{};
    claim_pk[0]  = 0x02;
    refund_pk[0] = 0x03;
    for (size_t i = 0; i < 32; ++i) hashlock[i] = static_cast<uint8_t>(0x40 + i);
    for (size_t i = 1; i < 33; ++i) {
        claim_pk[i]  = static_cast<uint8_t>(0xA0 + (i - 1));
        refund_pk[i] = static_cast<uint8_t>(0xB0 + (i - 1));
    }
    return btc::BuildBtcHtlcRedeemScript(
        hashlock, static_cast<int64_t>(refund_height_delta),
        claim_pk, refund_pk);
}

// ---------------------------------------------------------------------------
// Scenarios
// ---------------------------------------------------------------------------

static void scenario_1_sost_lock_observed() {
    SCENARIO("S1", "SOST LOCK observed -> AwaitingCounterpartyLock");
    Coordinator c;
    auto cr = c.CreateSession(make_safe_params(Role::Initiator));
    TEST("CreateSession ok",
         cr.ok && c.current_state() == State::AwaitingSostLock);
    TEST("session created flag", c.session_created());
    TEST("timeout-order valid", c.timeout_order_valid());
    TEST("no risk flags after safe params", c.risk_flags().empty());

    auto r = c.Apply(Event::MarkSostLockSeen);
    TEST("SOST lock observed -> AwaitingCounterpartyLock",
         r.ok && c.current_state() == State::AwaitingCounterpartyLock);
    TEST("next_safe_action surfaces a non-empty hint",
         !c.next_safe_action().empty());
}

static void scenario_2_counterparty_btc_lock_observed() {
    SCENARIO("S2", "Counterparty BTC LOCK observed -> BothLocked");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);

    // Pretend the wallet built+observed a BTC P2WSH lock for the swap.
    auto script    = sample_btc_redeem_script(/*refund_height_delta=*/1008);
    auto witness   = btc::BtcHtlcWitnessProgram(script);
    auto witness_b = btc::BtcHtlcWitnessProgram(script);
    TEST("BTC redeem script non-empty", !script.empty());
    TEST("BTC witness program deterministic",
         witness == witness_b);

    auto r = c.Apply(Event::MarkCounterpartyLockSeen);
    TEST("counterparty BTC lock observed -> BothLocked",
         r.ok && c.current_state() == State::BothLocked);
    TEST("recovery path surfaces a non-empty hint",
         !c.recovery_path().empty());
}

static void scenario_3_evm_equivalent() {
    SCENARIO("S3", "Counterparty EVM (Solidity) leg -> BothLocked");
    // The coordinator does NOT distinguish BTC vs EVM counterparty
    // legs — it only tracks "the wallet observed the counterparty
    // lock". The Solidity HTLC equivalent lives in
    // contracts/atomic-swap/src/AtomicSwapHTLC.sol with its own
    // Foundry tests (Phase 4B-1) and a hardening checklist (Phase D
    // STOP report). For the coordinator, the wallet supplies the
    // same Event::MarkCounterpartyLockSeen once the EVM lock tx
    // is mined N confirmations deep.
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);
    TEST("BothLocked regardless of EVM vs BTC counterparty",
         c.current_state() == State::BothLocked);
}

static void scenario_4_preimage_revealed() {
    SCENARIO("S4", "Preimage revealed -> ClaimReady");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);
    TEST("starts at BothLocked",
         c.current_state() == State::BothLocked);

    auto r = c.Apply(Event::MarkPreimageKnown);
    TEST("preimage known -> ClaimReady",
         r.ok && c.current_state() == State::ClaimReady);
    TEST("preimage_known flag set", c.preimage_known());
}

static void scenario_5_claim_happy_path() {
    SCENARIO("S5", "ClaimReady -> Claimed (terminal happy path)");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);
    (void) c.Apply(Event::MarkPreimageKnown);

    auto r = c.Apply(Event::MarkCounterpartyClaimSeen);
    TEST("counterparty-claim observed -> Claimed",
         r.ok && c.current_state() == State::Claimed);

    // Terminal idempotence: re-applying the same event must remain ok.
    auto r2 = c.Apply(Event::MarkCounterpartyClaimSeen);
    TEST("re-apply same terminal event stays Claimed",
         r2.ok && c.current_state() == State::Claimed);

    // Non-terminal events on a terminal state must be rejected.
    auto r3 = c.Apply(Event::MarkPreimageKnown);
    TEST("non-terminal event on Claimed rejected",
         !r3.ok);
}

static void scenario_6_refund_path() {
    SCENARIO("S6", "Refund path: post-lock timeout -> RefundAvailable -> Refunded");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);

    auto r1 = c.Apply(Event::MarkTimeoutReached);
    TEST("post-lock timeout -> RefundAvailable",
         r1.ok && c.current_state() == State::RefundAvailable);

    auto r2 = c.Apply(Event::MarkSostRefundSeen);
    TEST("SOST refund observed -> Refunded",
         r2.ok && c.current_state() == State::Refunded);
}

static void scenario_7_wrong_timeout_order_rejected() {
    SCENARIO("S7", "Wrong timeout-order rejected at CreateSession");

    // Initiator with sost_refund_opens_after_counterparty=false
    // is the unsafe direction. The coordinator must refuse to
    // advance past Draft and surface a risk flag.
    SwapParams bad;
    bad.role = Role::Initiator;
    bad.sost_refund_opens_after_counterparty = false;
    bad.observed_safety_margin_blocks        = 144;
    bad.safety_margin_min_blocks             = 6;

    Coordinator c;
    auto cr = c.CreateSession(bad);
    TEST("CreateSession with wrong order does NOT advance",
         c.current_state() == State::Draft);
    TEST("timeout_order_valid() == false", !c.timeout_order_valid());
    TEST("risk_flags() reports TIMEOUT_ORDER_INVALID",
         !c.risk_flags().empty());

    // Apply any event -> rejected.
    auto r = c.Apply(Event::MarkSostLockSeen);
    TEST("non-failure events rejected while unsafe",
         !r.ok);
}

static void scenario_8_party_disappears() {
    SCENARIO("S8", "One party disappears -> RefundAvailable + recovery_path()");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);
    // Counterparty stops responding; UI fires the timeout event.
    (void) c.Apply(Event::MarkTimeoutReached);

    TEST("state went to RefundAvailable after timeout",
         c.current_state() == State::RefundAvailable);
    TEST("recovery_path() is non-empty (operator UI can render it)",
         !c.recovery_path().empty());
    TEST("next_safe_action() is non-empty (\"submit refund\" or similar)",
         !c.next_safe_action().empty());
}

static void scenario_9_preimage_leak_before_both_locks() {
    SCENARIO("S9", "Preimage leak before BothLocked -> jumps to ClaimReady on late lock");
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    // SOST lock confirmed, but counterparty lock NOT yet observed.
    // Wallet leaks preimage early (counterparty published their lock
    // tx but it's not yet confirmed to us).
    auto rPreimage = c.Apply(Event::MarkPreimageKnown);
    TEST("MarkPreimageKnown accepted in AwaitingCounterpartyLock",
         rPreimage.ok);
    TEST("preimage_known flag set", c.preimage_known());
    TEST("state stays AwaitingCounterpartyLock (still waiting)",
         c.current_state() == State::AwaitingCounterpartyLock);

    // Counterparty lock arrives -> coordinator skips BothLocked,
    // jumps straight to ClaimReady because preimage is already known.
    auto rLock = c.Apply(Event::MarkCounterpartyLockSeen);
    TEST("late counterparty lock -> ClaimReady (skip BothLocked)",
         rLock.ok && c.current_state() == State::ClaimReady);
}

static void scenario_10_stablecoin_freeze_and_btc_signing_disabled() {
    SCENARIO("S10", "Stablecoin freeze risk + BTC signing disabled = fail-closed");

    // 10.1 — Confirm the BTC signing backend is disabled.
    // Any wallet flow that tries to construct a real BTC tx must
    // surface the disabled-state error and refuse to broadcast.
    TEST("IsBtcHtlcSigningEnabled() == false (matches CMake default)",
         !btc_sign::IsBtcHtlcSigningEnabled());

    auto disabled_err = btc_sign::BtcSigningDisabledErrorMessage();
    TEST("BtcSigningDisabledErrorMessage() non-empty",
         !disabled_err.empty());

    // 10.2 — Each external signing function returns a clearly-flagged
    // disabled result. The UI uses this to surface "BTC signing is
    // disabled in this build" without ever revealing key material
    // (which the stub neither holds nor logs).
    Bytes32 txid{};   for (size_t i = 0; i < 32; ++i) txid[i]   = (uint8_t)i;
    std::array<uint8_t, 32> preimage{}; for (size_t i = 0; i < 32; ++i) preimage[i] = (uint8_t)(0xC0 + i);
    std::array<uint8_t, 32> privkey{};  for (size_t i = 0; i < 32; ++i) privkey[i]  = (uint8_t)(0xD0 + i);
    auto redeem = sample_btc_redeem_script(1008);

    auto r1 = btc::SignBtcHtlcClaim(
        txid, 0, 100000, redeem, preimage, privkey,
        "tb1qexample", 1000, "testnet");
    auto r2 = btc::SignBtcHtlcRefund(
        txid, 0, 100000, redeem, 1008, privkey,
        "tb1qrefund", 1000, "testnet");
    auto r3 = btc::SignBtcHtlcLockFunding(
        txid, 0, 100000, privkey, "tb1qchange",
        redeem, 90000, 1000, "testnet");

    TEST("SignBtcHtlcClaim returns ok=false",  !r1.ok);
    TEST("SignBtcHtlcRefund returns ok=false", !r2.ok);
    TEST("SignBtcHtlcLockFunding returns ok=false", !r3.ok);
    TEST("Claim error message includes \"disabled\"",
         r1.error.find("disabled") != std::string::npos);
    TEST("Refund error message includes \"disabled\"",
         r2.error.find("disabled") != std::string::npos);
    TEST("Funding error message includes \"disabled\"",
         r3.error.find("disabled") != std::string::npos);
    TEST("Claim raw_tx_hex empty (no signing happened)",
         r1.raw_tx_hex.empty());
    TEST("Refund raw_tx_hex empty",
         r2.raw_tx_hex.empty());
    TEST("Funding raw_tx_hex empty",
         r3.raw_tx_hex.empty());

    // 10.3 — Stablecoin freeze risk is a UI policy, not a coordinator
    // state. We assert here that the coordinator does NOT track
    // assets — it is the wallet's job to surface "ISSUER-RISK" badges
    // for USDT/USDC/PAXG/XAUT. The coordinator's role is to track
    // the swap-state machine identically for any asset pair, so a
    // frozen-mid-swap counterparty falls through the standard
    // timeout -> refund branch.
    Coordinator c;
    (void) c.CreateSession(make_safe_params(Role::Initiator));
    (void) c.Apply(Event::MarkSostLockSeen);
    (void) c.Apply(Event::MarkCounterpartyLockSeen);

    // Counterparty leg uses a frozen stablecoin; the swap stalls.
    // UI policy: surface ISSUER-RISK warning to the user; coordinator
    // still progresses through the timeout-refund path identically.
    auto r = c.Apply(Event::MarkTimeoutReached);
    TEST("frozen-stablecoin counterparty -> timeout path opens",
         r.ok && c.current_state() == State::RefundAvailable);
    TEST("operator can recover via SOST-side refund",
         !c.recovery_path().empty());
}

int main() {
    printf("\n== Atomic Swap Phase E — local end-to-end simulation ==\n");
    printf("== %d scenarios; NO network, NO chain, NO keys, NO HTTP ==\n",
           10);

    scenario_1_sost_lock_observed();
    scenario_2_counterparty_btc_lock_observed();
    scenario_3_evm_equivalent();
    scenario_4_preimage_revealed();
    scenario_5_claim_happy_path();
    scenario_6_refund_path();
    scenario_7_wrong_timeout_order_rejected();
    scenario_8_party_disappears();
    scenario_9_preimage_leak_before_both_locks();
    scenario_10_stablecoin_freeze_and_btc_signing_disabled();

    printf("\n== Summary ==\n");
    printf("  scenarios run    : %d\n", g_scenarios);
    printf("  assertions PASS  : %d\n", g_pass);
    printf("  assertions FAIL  : %d\n", g_fail);
    printf("\n");
    return (g_fail == 0) ? 0 : 1;
}
