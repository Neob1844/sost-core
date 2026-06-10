// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap — end-to-end swap SESSION coordinator (OTC-4)
// =============================================================================
//
// PURE, NON-CUSTODIAL, DETERMINISTIC. This is the top-level orchestrator that
// ties the three already-built legs into one end-to-end swap flow:
//
//   1. SOST HTLC        (OTC-1 consensus + OTC-2 builders + OTC-2.5 RPC)
//   2. BTC HTLC         (OTC-3a libwally signing, regtest)
//   3. EVM HTLC         (OTC-3b AtomicSwapHTLC.sol, anvil/testnet)
//
// It composes the existing modules — it adds NO consensus rule and does NOT
// duplicate their logic:
//   - orderbook  : ValidateOffer (timeout ordering T2<T1, issuer-freeze flags)
//   - coordinator: the core lock/claim/refund state discipline
//   - watcher    : IngestRevealedPreimage (real sha256 check), DecideWatchAction
//
// What the session DOES:
//   - drive the full lifecycle (offer -> accept -> lock both legs -> claim ->
//     opposite-leg auto-claim -> refund) as a deterministic phase machine;
//   - ingest OBSERVATIONS that the wallet/watcher already verified on-chain;
//   - emit the NEXT SAFE ACTION for THIS wallet (the operator/wallet executes
//     it — the session never signs, never broadcasts, never holds keys);
//   - persist to a local session record and RESUME after a restart;
//   - surface recovery when the observed facts are inconsistent.
//
// What the session does NOT do (hard invariants):
//   - move funds, sign, or broadcast anything;
//   - hold or read a private key;
//   - open a socket / RPC / HTTP connection;
//   - require a central order book;
//   - act as a custodian;
//   - promise perfect atomicity for issuer tokens (USDT/USDC/PAXG/XAUT) — those
//     always carry an issuer-freeze warning;
//   - depend on any gate being flipped. ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT stays
//     INT64_MAX and SOST_BTC_HTLC_SIGNING stays OFF; the session is usable for
//     dry runs / testnet walk-throughs with no chain involved.
// =============================================================================
#pragma once

#include "sost/atomic_swap_orderbook.h"   // Asset, Offer, ValidateOffer, Role
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace session {

using coordinator::Role;   // Initiator (maker, knows the secret) / Responder

// The counterparty chain this swap's non-SOST leg lives on.
enum class CounterpartyChain : uint8_t { BTC, ETH, BNB, ERC20 };
const char* CounterpartyChainName(CounterpartyChain c);
bool        CounterpartyChainParse(const std::string& s, CounterpartyChain& out);

// -----------------------------------------------------------------------------
// Lifecycle phase (richer than the core coordinator State; OTC-4 vocabulary).
// -----------------------------------------------------------------------------
enum class SwapPhase : uint8_t {
    Created,             // session built from params; no offer published yet
    Offered,            // maker published the validated offer
    Accepted,           // taker accepted; both committed to params
    SostLocked,         // the SOST HTLC lock is confirmed
    CounterpartyLocked, // the BTC/EVM HTLC lock is confirmed (both legs live)
    ClaimSeen,          // a claim was observed -> the preimage is now revealed
    Claimed,            // THIS wallet's claim of its receiving leg is confirmed
    Completed,          // both legs settled by claim (terminal success)
    RefundReady,        // a refund timeout opened; refund is available
    Refunded,           // a refund settled (terminal)
    Expired,            // pre-lock timeout; nothing locked (terminal)
    Failed,             // hard failure (terminal)
    RecoveryNeeded      // observed facts are inconsistent; operator must inspect
};
const char* SwapPhaseName(SwapPhase p);
bool        SwapPhaseIsTerminal(SwapPhase p);

// -----------------------------------------------------------------------------
// Observations — facts the wallet/watcher has ALREADY verified on-chain and
// feeds to the session. The session never observes a chain itself.
// -----------------------------------------------------------------------------
enum class Observation : uint8_t {
    OfferPublished,
    OfferAccepted,
    SostLockConfirmed,
    CounterpartyLockConfirmed,
    PreimageRevealed,             // secret now known (a claim revealed it)
    SostClaimConfirmed,
    CounterpartyClaimConfirmed,
    SostRefundConfirmed,
    CounterpartyRefundConfirmed,
    TimeoutReached,               // current height >= the relevant refund height
    Failure,
    Corruption                    // session record / observed data inconsistent
};
const char* ObservationName(Observation o);

// -----------------------------------------------------------------------------
// NextAction — the single next safe step for THIS wallet. The operator/wallet
// executes it with the OTC-1/3a/3b builders; the session only decides.
// -----------------------------------------------------------------------------
enum class NextAction : uint8_t {
    Wait,                 // nothing to do; waiting on counterparty / a timeout
    PublishOffer,         // maker: publish the validated offer
    AcceptOffer,          // taker: accept the offer
    LockSost,             // build + submit the SOST HTLC lock
    LockCounterparty,     // build + submit the BTC/EVM HTLC lock
    ClaimCounterparty,    // claim the counterparty leg (reveals the preimage)
    ClaimSost,            // claim the SOST leg (with the revealed preimage)
    RefundSost,           // refund the SOST leg after T1
    RefundCounterparty,   // refund the counterparty leg after T2
    Done,                 // terminal success — nothing more to do
    Abort,                // terminal failure / expired
    ManualRecovery        // inconsistent state; operator must inspect
};
const char* NextActionName(NextAction a);

// -----------------------------------------------------------------------------
// Session record — the full persistable state of one swap.
// -----------------------------------------------------------------------------
struct Session {
    std::string swap_id;
    Role        role = Role::Initiator;     // Initiator = maker (knows secret)
    CounterpartyChain cp_chain = CounterpartyChain::BTC;

    Asset   give = Asset::SOST;             // asset this wallet gives
    Asset   want = Asset::BTC;              // asset this wallet wants
    int64_t give_amount = 0;
    int64_t want_amount = 0;

    std::array<uint8_t, 32> hashlock{};     // sha256(secret)
    bool                    have_secret = false;   // Initiator: true; Responder: after reveal
    std::array<uint8_t, 32> secret{};       // SENSITIVE — only meaningful if have_secret

    int64_t initiator_refund_height = 0;    // T1 — opens LAST
    int64_t responder_refund_height = 0;    // T2 — opens FIRST (< T1 - margin)
    int64_t safety_margin_min_blocks = 6;

    SwapPhase                phase = SwapPhase::Created;
    bool                     issuer_freeze_risk = false;
    std::vector<std::string> warnings;      // includes ISSUER_FREEZE_RISK when applicable

    // Leg-settlement tracking (so the phase machine can distinguish "my leg
    // claimed" (Claimed) from "both legs claimed" (Completed), and surface a
    // clean refund terminal). Updated by Ingest; serialized for resume.
    bool sost_claimed   = false;
    bool cp_claimed     = false;
    bool sost_refunded  = false;
    bool cp_refunded    = false;
};

// True iff this wallet GIVES the SOST leg (gives SOST, receives the
// counterparty asset) — derived from the wallet-perspective `give`.
bool GivesSost(const Session& s);
// The on-chain claim that settles THIS wallet's RECEIVING leg.
//   gives SOST  -> receives counterparty -> CounterpartyClaimConfirmed
//   wants SOST  -> receives SOST         -> SostClaimConfirmed

// -----------------------------------------------------------------------------
// CreateSession — build + validate a session from an offer.
//   - Runs ValidateOffer: structural sanity + timeout ordering (T2<T1, margin)
//     + issuer-freeze flags. ok=false (with errors) on any hard failure.
//   - `secret` is REQUIRED for the Initiator (maker) and must be nullptr for
//     the Responder (who only learns it on reveal). For the Initiator the
//     session checks sha256(secret)==offer.hashlock and refuses on mismatch.
// -----------------------------------------------------------------------------
struct SessionInit {
    bool                     ok = false;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    Session                  session;
};
SessionInit CreateSession(const Offer& offer,
                          Role role,
                          CounterpartyChain cp_chain,
                          const std::array<uint8_t, 32>* secret);

// -----------------------------------------------------------------------------
// Ingest — apply an observation; advance (or refuse) the phase. Pure.
//   - PreimageRevealed verifies sha256(preimage)==hashlock before accepting it
//     (delegates to the watcher's discipline); a mismatch is rejected and the
//     phase is unchanged.
//   - Out-of-order / illegal observations are refused with an error and leave
//     the phase unchanged; genuinely inconsistent facts move to RecoveryNeeded.
// -----------------------------------------------------------------------------
struct StepResult {
    bool        ok = false;
    std::string error;
    SwapPhase   phase = SwapPhase::Created;
};
StepResult Ingest(Session& s, Observation obs);
// Overload: PreimageRevealed carries the revealed 32-byte secret.
StepResult IngestPreimage(Session& s, const std::array<uint8_t, 32>& preimage);

// -----------------------------------------------------------------------------
// DecideNextStep — the next safe action for THIS wallet, given the phase, the
// role and the current SOST tip height (for timeout decisions). Pure.
// -----------------------------------------------------------------------------
struct NextStep {
    NextAction  action = NextAction::Wait;
    std::string detail;             // human-facing description
    bool        needs_confirmation = false;
    std::string recovery;           // populated when action == ManualRecovery
};
NextStep DecideNextStep(const Session& s, int64_t current_sost_height);

// -----------------------------------------------------------------------------
// Persistence — deterministic, human-readable "key=value" lines, one session
// per record. No private keys are ever stored. The secret IS stored (the
// Initiator needs it across restarts to claim) but only when include_secret is
// true; it is preceded by an explicit risk marker, and SerializeSession(.,false)
// redacts it for sharing/inspection.
// -----------------------------------------------------------------------------
std::string SerializeSession(const Session& s, bool include_secret);
bool        ParseSession(const std::string& text, Session& out);

}  // namespace session
}  // namespace atomic_swap
}  // namespace sost
