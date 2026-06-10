// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-4 — end-to-end swap session tests (pure, no consensus, gate-agnostic).
//
// Two passes in one binary: (A) full-flow + resume simulations, and
// (B) adversarial paths. None of it touches a chain, signs, broadcasts, or
// reads a key — the session is a pure decision/persistence layer.

#include "sost/atomic_swap_session.h"
#include "sost/crypto.h"
#include <array>
#include <cstdio>
#include <string>

using namespace sost;
using namespace sost::atomic_swap;
using namespace sost::atomic_swap::session;

static int g_fail = 0;
#define TEST(msg, cond) do { \
    if (!(cond)) { std::printf("  FAIL: %s\n", msg); ++g_fail; } \
    else { std::printf("  ok:   %s\n", msg); } \
} while (0)

static std::array<uint8_t, 32> Secret(uint8_t fill) { std::array<uint8_t, 32> s{}; s.fill(fill); return s; }
static std::array<uint8_t, 32> Hashlock(const std::array<uint8_t, 32>& secret) {
    Bytes32 h = sost::sha256(secret.data(), secret.size());
    std::array<uint8_t, 32> out{}; for (int i = 0; i < 32; ++i) out[i] = h[i]; return out;
}

static Offer GoodOffer(const std::array<uint8_t, 32>& secret, Asset give, Asset want) {
    Offer o;
    o.id = "swap-e2e-1";
    o.maker_role = Role::Initiator;
    o.give = give; o.want = want;
    o.give_amount = 1000000; o.want_amount = 50000;
    o.hashlock = Hashlock(secret);
    o.responder_refund_height = 1000;   // T2 opens first
    o.initiator_refund_height = 1020;   // T1 opens last (gap 20 >= margin 6)
    o.safety_margin_min_blocks = 6;
    return o;
}

int main() {
    std::printf("[OTC-4 session]\n");
    auto secret = Secret(0x42);

    // ====================================================================
    // PASS A — full flows + resume
    // ====================================================================

    // ---- A1. Initiator happy path (gives SOST, receives BTC) -----------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Initiator, CounterpartyChain::BTC, &secret);
        TEST("init ok (initiator, valid secret)", init.ok && init.errors.empty());
        Session s = init.session;
        TEST("starts Created", s.phase == SwapPhase::Created);
        TEST("initiator holds secret", s.have_secret);
        TEST("next=PublishOffer", DecideNextStep(s, 0).action == NextAction::PublishOffer);

        TEST("publish -> Offered", Ingest(s, Observation::OfferPublished).ok && s.phase == SwapPhase::Offered);
        TEST("offered next=Wait", DecideNextStep(s, 0).action == NextAction::Wait);
        TEST("accept -> Accepted", Ingest(s, Observation::OfferAccepted).ok && s.phase == SwapPhase::Accepted);
        TEST("accepted next=LockSost", DecideNextStep(s, 0).action == NextAction::LockSost);
        TEST("sost lock -> SostLocked", Ingest(s, Observation::SostLockConfirmed).ok && s.phase == SwapPhase::SostLocked);
        TEST("sostlocked next=Wait (before T1)", DecideNextStep(s, 500).action == NextAction::Wait);
        TEST("cp lock -> CounterpartyLocked",
             Ingest(s, Observation::CounterpartyLockConfirmed).ok && s.phase == SwapPhase::CounterpartyLocked);
        TEST("bothlocked next=ClaimCounterparty",
             DecideNextStep(s, 500).action == NextAction::ClaimCounterparty);
        // Initiator claims counterparty -> that confirms; receiving leg settled.
        TEST("cp claim -> Claimed (my leg)",
             Ingest(s, Observation::CounterpartyClaimConfirmed).ok && s.phase == SwapPhase::Claimed);
        TEST("claimed next=Done", DecideNextStep(s, 500).action == NextAction::Done);
        // Responder then claims SOST -> both legs settled -> Completed.
        TEST("sost claim -> Completed",
             Ingest(s, Observation::SostClaimConfirmed).ok && s.phase == SwapPhase::Completed);
        TEST("completed terminal", SwapPhaseIsTerminal(s.phase));
    }

    // ---- A2. Responder happy path (gives BTC, receives SOST) -----------
    {
        // Responder takes the SOST<->BTC offer: from their perspective they
        // give BTC, want SOST. No secret until reveal.
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Responder, CounterpartyChain::BTC, nullptr);
        TEST("init ok (responder, no secret)", init.ok);
        Session s = init.session;
        TEST("responder gives BTC", s.give == Asset::BTC && s.want == Asset::SOST);
        TEST("responder lacks secret", !s.have_secret);

        Ingest(s, Observation::OfferPublished);
        TEST("responder offered next=AcceptOffer", DecideNextStep(s, 0).action == NextAction::AcceptOffer);
        Ingest(s, Observation::OfferAccepted);
        TEST("responder accepted next=Wait (initiator locks first)", DecideNextStep(s, 0).action == NextAction::Wait);
        Ingest(s, Observation::SostLockConfirmed);
        TEST("responder sostlocked next=LockCounterparty (before T2)",
             DecideNextStep(s, 500).action == NextAction::LockCounterparty);
        Ingest(s, Observation::CounterpartyLockConfirmed);
        TEST("responder bothlocked next=Wait (before T2)", DecideNextStep(s, 500).action == NextAction::Wait);
        // Initiator claims counterparty -> preimage revealed on-chain; responder ingests it.
        TEST("responder ingests revealed preimage", IngestPreimage(s, secret).ok && s.phase == SwapPhase::ClaimSeen);
        TEST("responder now has secret", s.have_secret);
        TEST("responder claimseen next=ClaimSost (before T1)",
             DecideNextStep(s, 600).action == NextAction::ClaimSost);
        // Responder claims SOST.
        TEST("responder sost claim -> Claimed", Ingest(s, Observation::SostClaimConfirmed).ok);
        TEST("responder claimed/completed", s.phase == SwapPhase::Claimed || s.phase == SwapPhase::Completed);
    }

    // ---- A3. Refund flow (counterparty never locks) --------------------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Initiator, CounterpartyChain::BTC, &secret);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);
        // Before T1, initiator just waits.
        TEST("before T1 -> Wait", DecideNextStep(s, 1000).action == NextAction::Wait);
        // At/after T1 with no counterparty lock -> refund.
        TEST("at T1 -> RefundSost", DecideNextStep(s, 1020).action == NextAction::RefundSost);
        TEST("timeout -> RefundReady", Ingest(s, Observation::TimeoutReached).ok && s.phase == SwapPhase::RefundReady);
        TEST("refundready next=RefundSost", DecideNextStep(s, 1020).action == NextAction::RefundSost);
        TEST("refund confirmed -> Refunded",
             Ingest(s, Observation::SostRefundConfirmed).ok && s.phase == SwapPhase::Refunded);
        TEST("refunded terminal", SwapPhaseIsTerminal(s.phase));
    }

    // ---- A4. Resume (serialize/parse round-trip, with + without secret)
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Initiator, CounterpartyChain::BTC, &secret);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);

        std::string withSecret = SerializeSession(s, /*include_secret*/ true);
        Session r;
        TEST("parse (with secret)", ParseSession(withSecret, r));
        TEST("resume phase", r.phase == s.phase);
        TEST("resume role", r.role == s.role);
        TEST("resume hashlock", r.hashlock == s.hashlock);
        TEST("resume secret preserved", r.have_secret && r.secret == s.secret);
        TEST("resume heights", r.initiator_refund_height == 1020 && r.responder_refund_height == 1000);
        TEST("resumed decision identical",
             DecideNextStep(r, 500).action == DecideNextStep(s, 500).action);

        std::string redacted = SerializeSession(s, /*include_secret*/ false);
        Session r2;
        TEST("parse (redacted)", ParseSession(redacted, r2));
        TEST("redacted drops secret", !r2.have_secret);
        TEST("redacted text says REDACTED", redacted.find("secret=REDACTED") != std::string::npos);
    }

    // ====================================================================
    // PASS B — adversarial
    // ====================================================================

    // ---- B1. Wrong preimage rejected (phase unchanged) -----------------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Responder, CounterpartyChain::BTC, nullptr);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);
        Ingest(s, Observation::CounterpartyLockConfirmed);
        auto wrong = Secret(0x43);
        auto before = s.phase;
        auto r = IngestPreimage(s, wrong);
        TEST("wrong preimage rejected", !r.ok);
        TEST("wrong preimage leaves phase unchanged", s.phase == before && !s.have_secret);
        TEST("correct preimage accepted afterwards", IngestPreimage(s, secret).ok && s.have_secret);
    }

    // ---- B2. Timeout mis-ordered (T2 >= T1) rejected at creation --------
    {
        Offer o = GoodOffer(secret, Asset::SOST, Asset::BTC);
        o.responder_refund_height = 1020;   // T2 == T1 -> invalid ordering
        o.initiator_refund_height = 1000;
        auto init = CreateSession(o, Role::Initiator, CounterpartyChain::BTC, &secret);
        bool hasOrderErr = false;
        for (auto& e : init.errors) if (e.find("TIMEOUT_ORDER_INVALID") != std::string::npos) hasOrderErr = true;
        TEST("mis-ordered timeouts rejected at creation", !init.ok && hasOrderErr);
    }

    // ---- B3. Counterparty (responder) locks too late -------------------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Responder, CounterpartyChain::BTC, nullptr);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);
        // At/after T2 the responder must NOT lock (margin gone).
        auto ns = DecideNextStep(s, 1000);
        TEST("responder does not LockCounterparty past T2", ns.action != NextAction::LockCounterparty);
    }

    // ---- B4. Claim seen near timeout (responder, T1 passed) ------------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Responder, CounterpartyChain::BTC, nullptr);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);
        Ingest(s, Observation::CounterpartyLockConfirmed);
        IngestPreimage(s, secret);
        auto ns = DecideNextStep(s, 1020);   // T1 reached
        TEST("claim-near-timeout still ClaimSost", ns.action == NextAction::ClaimSost);
        TEST("claim-near-timeout warns", ns.detail.find("WARNING") != std::string::npos);
    }

    // ---- B5. Out-of-order / duplicate observation rejected -------------
    {
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Initiator, CounterpartyChain::BTC, &secret);
        Session s = init.session;
        // CounterpartyLockConfirmed before any offer/accept/lock is illegal.
        auto r = Ingest(s, Observation::CounterpartyLockConfirmed);
        TEST("out-of-order observation rejected", !r.ok && s.phase == SwapPhase::Created);
        Ingest(s, Observation::OfferPublished);
        // Duplicate OfferPublished now illegal (already Offered).
        TEST("duplicate observation rejected", !Ingest(s, Observation::OfferPublished).ok);
    }

    // ---- B6. Refund-after-claim / claim-after-refund discipline --------
    {
        // Once the preimage is public (ClaimSeen), refusing to "refund" is
        // the safe behaviour — you must claim, not refund.
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Responder, CounterpartyChain::BTC, nullptr);
        Session s = init.session;
        Ingest(s, Observation::OfferPublished);
        Ingest(s, Observation::OfferAccepted);
        Ingest(s, Observation::SostLockConfirmed);
        Ingest(s, Observation::CounterpartyLockConfirmed);
        IngestPreimage(s, secret);   // ClaimSeen
        TEST("timeout after preimage-public is refused (claim instead)",
             !Ingest(s, Observation::TimeoutReached).ok);
    }

    // ---- B7. Corrupted session file rejected ---------------------------
    {
        Session r;
        TEST("garbage session rejected", !ParseSession("this is not a session", r));
        TEST("empty session rejected", !ParseSession("", r));
        // A record whose secret does not match its hashlock is rejected.
        auto init = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                                  Role::Initiator, CounterpartyChain::BTC, &secret);
        std::string good = SerializeSession(init.session, true);
        // Flip ONLY the stored secret value to a non-matching (but valid hex)
        // one, keeping the record structure intact. Match the standalone
        // "\nsecret=" line (not the "have_secret=" substring).
        std::string bad = good;
        auto pos = bad.find("\nsecret=");
        auto eol = bad.find('\n', pos + 1);
        bad = bad.substr(0, pos) + "\nsecret=" + std::string(64, 'a') + bad.substr(eol);
        Session r2;
        TEST("tampered secret (hashlock mismatch) rejected", !ParseSession(bad, r2));
    }

    // ---- B8. Issuer-freeze enforced for USDT/USDC/PAXG/XAUT ------------
    {
        for (Asset a : {Asset::USDT, Asset::USDC, Asset::PAXG, Asset::XAUT}) {
            auto init = CreateSession(GoodOffer(secret, Asset::SOST, a),
                                      Role::Initiator, CounterpartyChain::ERC20, &secret);
            bool warned = false;
            for (auto& w : init.session.warnings) if (w.find("ISSUER_FREEZE_RISK") != std::string::npos) warned = true;
            std::string label = std::string("issuer-freeze enforced for ") + AssetName(a);
            TEST(label.c_str(), init.ok && init.session.issuer_freeze_risk && warned);
        }
    }

    // ---- B9. NO issuer warning for BTC/ETH/BNB/SOST --------------------
    {
        for (Asset a : {Asset::BTC, Asset::ETH, Asset::BNB}) {
            auto init = CreateSession(GoodOffer(secret, Asset::SOST, a),
                                      Role::Initiator, CounterpartyChain::BTC, &secret);
            std::string label = std::string("no issuer-freeze for ") + AssetName(a);
            TEST(label.c_str(), init.ok && !init.session.issuer_freeze_risk);
        }
    }

    // ---- B10. Secret discipline at creation ---------------------------
    {
        // Initiator without a secret is rejected.
        auto a = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                               Role::Initiator, CounterpartyChain::BTC, nullptr);
        TEST("initiator without secret rejected", !a.ok);
        // Initiator with a NON-matching secret is rejected.
        auto wrong = Secret(0x99);
        auto b = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                               Role::Initiator, CounterpartyChain::BTC, &wrong);
        TEST("initiator with wrong secret rejected", !b.ok);
        // Responder supplying a secret is rejected.
        auto c = CreateSession(GoodOffer(secret, Asset::SOST, Asset::BTC),
                               Role::Responder, CounterpartyChain::BTC, &secret);
        TEST("responder supplying secret rejected", !c.ok);
    }

    if (g_fail == 0) std::printf("ALL SESSION TESTS PASSED\n");
    else std::printf("%d SESSION TESTS FAILED\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
