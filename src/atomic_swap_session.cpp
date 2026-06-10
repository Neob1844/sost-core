// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// OTC-4 — end-to-end swap session coordinator (pure, non-custodial).

#include "sost/atomic_swap_session.h"
#include "sost/crypto.h"     // sha256
#include <sstream>
#include <algorithm>

namespace sost {
namespace atomic_swap {
namespace session {

// ----------------------------------------------------------------------------
// Small local hex helpers (no external dep).
// ----------------------------------------------------------------------------
namespace {
const char* HEX = "0123456789abcdef";
std::string to_hex(const uint8_t* d, size_t n) {
    std::string s; s.reserve(n * 2);
    for (size_t i = 0; i < n; ++i) { s.push_back(HEX[d[i] >> 4]); s.push_back(HEX[d[i] & 0xf]); }
    return s;
}
int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
bool from_hex(const std::string& s, uint8_t* out, size_t n) {
    if (s.size() != n * 2) return false;
    for (size_t i = 0; i < n; ++i) {
        int hi = hexval(s[2 * i]), lo = hexval(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}
bool is_zero(const std::array<uint8_t, 32>& a) {
    for (uint8_t b : a) if (b) return false;
    return true;
}
}  // namespace

// ----------------------------------------------------------------------------
// Names / parsers
// ----------------------------------------------------------------------------
const char* CounterpartyChainName(CounterpartyChain c) {
    switch (c) {
        case CounterpartyChain::BTC:   return "BTC";
        case CounterpartyChain::ETH:   return "ETH";
        case CounterpartyChain::BNB:   return "BNB";
        case CounterpartyChain::ERC20: return "ERC20";
    }
    return "BTC";
}
bool CounterpartyChainParse(const std::string& s, CounterpartyChain& out) {
    std::string u; u.reserve(s.size());
    for (char c : s) u.push_back((char)std::toupper((unsigned char)c));
    if (u == "BTC")   { out = CounterpartyChain::BTC;   return true; }
    if (u == "ETH")   { out = CounterpartyChain::ETH;   return true; }
    if (u == "BNB")   { out = CounterpartyChain::BNB;   return true; }
    if (u == "ERC20") { out = CounterpartyChain::ERC20; return true; }
    return false;
}

const char* SwapPhaseName(SwapPhase p) {
    switch (p) {
        case SwapPhase::Created:            return "Created";
        case SwapPhase::Offered:            return "Offered";
        case SwapPhase::Accepted:           return "Accepted";
        case SwapPhase::SostLocked:         return "SostLocked";
        case SwapPhase::CounterpartyLocked: return "CounterpartyLocked";
        case SwapPhase::ClaimSeen:          return "ClaimSeen";
        case SwapPhase::Claimed:            return "Claimed";
        case SwapPhase::Completed:          return "Completed";
        case SwapPhase::RefundReady:        return "RefundReady";
        case SwapPhase::Refunded:           return "Refunded";
        case SwapPhase::Expired:            return "Expired";
        case SwapPhase::Failed:             return "Failed";
        case SwapPhase::RecoveryNeeded:     return "RecoveryNeeded";
    }
    return "Created";
}
bool SwapPhaseIsTerminal(SwapPhase p) {
    return p == SwapPhase::Completed || p == SwapPhase::Refunded ||
           p == SwapPhase::Expired   || p == SwapPhase::Failed;
}
static bool ParsePhase(const std::string& n, SwapPhase& out) {
    for (int i = 0; i <= (int)SwapPhase::RecoveryNeeded; ++i) {
        auto p = (SwapPhase)i;
        if (n == SwapPhaseName(p)) { out = p; return true; }
    }
    return false;
}

const char* ObservationName(Observation o) {
    switch (o) {
        case Observation::OfferPublished:             return "OfferPublished";
        case Observation::OfferAccepted:              return "OfferAccepted";
        case Observation::SostLockConfirmed:          return "SostLockConfirmed";
        case Observation::CounterpartyLockConfirmed:  return "CounterpartyLockConfirmed";
        case Observation::PreimageRevealed:           return "PreimageRevealed";
        case Observation::SostClaimConfirmed:         return "SostClaimConfirmed";
        case Observation::CounterpartyClaimConfirmed: return "CounterpartyClaimConfirmed";
        case Observation::SostRefundConfirmed:        return "SostRefundConfirmed";
        case Observation::CounterpartyRefundConfirmed:return "CounterpartyRefundConfirmed";
        case Observation::TimeoutReached:             return "TimeoutReached";
        case Observation::Failure:                    return "Failure";
        case Observation::Corruption:                 return "Corruption";
    }
    return "Failure";
}

const char* NextActionName(NextAction a) {
    switch (a) {
        case NextAction::Wait:               return "Wait";
        case NextAction::PublishOffer:       return "PublishOffer";
        case NextAction::AcceptOffer:        return "AcceptOffer";
        case NextAction::LockSost:           return "LockSost";
        case NextAction::LockCounterparty:   return "LockCounterparty";
        case NextAction::ClaimCounterparty:  return "ClaimCounterparty";
        case NextAction::ClaimSost:          return "ClaimSost";
        case NextAction::RefundSost:         return "RefundSost";
        case NextAction::RefundCounterparty: return "RefundCounterparty";
        case NextAction::Done:               return "Done";
        case NextAction::Abort:              return "Abort";
        case NextAction::ManualRecovery:     return "ManualRecovery";
    }
    return "Wait";
}

bool GivesSost(const Session& s) { return s.give == Asset::SOST; }

// ----------------------------------------------------------------------------
// CreateSession
// ----------------------------------------------------------------------------
SessionInit CreateSession(const Offer& offer,
                          Role role,
                          CounterpartyChain cp_chain,
                          const std::array<uint8_t, 32>* secret) {
    SessionInit init;
    OfferValidation v = ValidateOffer(offer);
    init.warnings = v.warnings;
    if (!v.ok) { init.errors = v.errors; return init; }

    Session s;
    s.swap_id  = offer.id;
    s.role     = role;
    s.cp_chain = cp_chain;
    // Perspective: the maker (Initiator) sees give/want as in the offer; the
    // taker (Responder) sees them reversed.
    if (role == Role::Initiator) { s.give = offer.give; s.want = offer.want; }
    else                         { s.give = offer.want; s.want = offer.give; }
    s.give_amount = (role == Role::Initiator) ? offer.give_amount : offer.want_amount;
    s.want_amount = (role == Role::Initiator) ? offer.want_amount : offer.give_amount;
    s.hashlock                = offer.hashlock;
    s.initiator_refund_height = offer.initiator_refund_height;
    s.responder_refund_height = offer.responder_refund_height;
    s.safety_margin_min_blocks= offer.safety_margin_min_blocks;
    s.phase = SwapPhase::Created;

    // Issuer-freeze: NEVER promise atomicity for freezable tokens.
    if (AssetHasIssuerFreeze(s.give) || AssetHasIssuerFreeze(s.want)) {
        s.issuer_freeze_risk = true;
        Asset frz = AssetHasIssuerFreeze(s.give) ? s.give : s.want;
        std::string w = IssuerFreezeWarning(frz);
        if (!w.empty()) s.warnings.push_back(w);
    }
    for (const auto& w : v.warnings) s.warnings.push_back(w);

    // The Initiator (maker) must hold the secret and it must match the hashlock.
    if (role == Role::Initiator) {
        if (!secret) {
            init.errors.push_back("Initiator must supply the swap secret (the maker holds it)");
            return init;
        }
        Bytes32 h = sost::sha256(secret->data(), secret->size());
        for (int i = 0; i < 32; ++i) {
            if (h[i] != offer.hashlock[i]) {
                init.errors.push_back("secret does not match offer hashlock (sha256 mismatch)");
                return init;
            }
        }
        s.have_secret = true;
        s.secret = *secret;
    } else {
        if (secret) {
            init.errors.push_back("Responder must NOT supply a secret (it is learned on reveal)");
            return init;
        }
        s.have_secret = false;
    }

    init.ok = true;
    init.warnings = s.warnings;
    init.session = s;
    return init;
}

// ----------------------------------------------------------------------------
// Ingest
// ----------------------------------------------------------------------------
static StepResult err(const Session& s, const std::string& m) {
    StepResult r; r.ok = false; r.error = m; r.phase = s.phase; return r;
}
static StepResult ok(Session& s, SwapPhase p) {
    s.phase = p; StepResult r; r.ok = true; r.phase = p; return r;
}

// Recompute the phase after a claim/refund flag change.
static SwapPhase reconcile_after_settlement(const Session& s) {
    if (s.sost_claimed && s.cp_claimed)   return SwapPhase::Completed;
    if (s.sost_refunded || s.cp_refunded) return SwapPhase::Refunded;
    // This wallet's receiving leg:
    bool my_leg_claimed = GivesSost(s) ? s.cp_claimed : s.sost_claimed;
    if (my_leg_claimed) return SwapPhase::Claimed;
    return SwapPhase::ClaimSeen;
}

StepResult Ingest(Session& s, Observation obs) {
    // Global terminals.
    if (obs == Observation::Failure)    return ok(s, SwapPhase::Failed);
    if (obs == Observation::Corruption) return ok(s, SwapPhase::RecoveryNeeded);

    switch (s.phase) {
        case SwapPhase::Created:
            if (obs == Observation::OfferPublished) return ok(s, SwapPhase::Offered);
            if (obs == Observation::TimeoutReached) return ok(s, SwapPhase::Expired);
            return err(s, "expected OfferPublished in Created");
        case SwapPhase::Offered:
            if (obs == Observation::OfferAccepted)  return ok(s, SwapPhase::Accepted);
            if (obs == Observation::TimeoutReached) return ok(s, SwapPhase::Expired);
            return err(s, "expected OfferAccepted in Offered");
        case SwapPhase::Accepted:
            if (obs == Observation::SostLockConfirmed) return ok(s, SwapPhase::SostLocked);
            if (obs == Observation::TimeoutReached)    return ok(s, SwapPhase::Expired);  // pre-lock
            return err(s, "expected SostLockConfirmed in Accepted");
        case SwapPhase::SostLocked:
            if (obs == Observation::CounterpartyLockConfirmed) return ok(s, SwapPhase::CounterpartyLocked);
            if (obs == Observation::TimeoutReached)            return ok(s, SwapPhase::RefundReady);
            // Defensive: a preimage reveal here means the counterparty acted
            // out of the modelled order — surface for inspection.
            if (obs == Observation::PreimageRevealed)          return ok(s, SwapPhase::RecoveryNeeded);
            return err(s, "expected CounterpartyLockConfirmed in SostLocked");
        case SwapPhase::CounterpartyLocked:
            if (obs == Observation::PreimageRevealed)           return ok(s, SwapPhase::ClaimSeen);
            if (obs == Observation::SostClaimConfirmed)         { s.sost_claimed = true; return ok(s, reconcile_after_settlement(s)); }
            if (obs == Observation::CounterpartyClaimConfirmed) { s.cp_claimed   = true; return ok(s, reconcile_after_settlement(s)); }
            if (obs == Observation::TimeoutReached)             return ok(s, SwapPhase::RefundReady);
            return err(s, "expected PreimageRevealed / claim in CounterpartyLocked");
        case SwapPhase::ClaimSeen:
        case SwapPhase::Claimed:
            if (obs == Observation::SostClaimConfirmed)         { s.sost_claimed = true; return ok(s, reconcile_after_settlement(s)); }
            if (obs == Observation::CounterpartyClaimConfirmed) { s.cp_claimed   = true; return ok(s, reconcile_after_settlement(s)); }
            if (obs == Observation::TimeoutReached)             return err(s, "preimage already public; claim, do not refund");
            return err(s, "expected a claim confirmation in ClaimSeen/Claimed");
        case SwapPhase::RefundReady:
            if (obs == Observation::SostRefundConfirmed)        { s.sost_refunded = true; return ok(s, SwapPhase::Refunded); }
            if (obs == Observation::CounterpartyRefundConfirmed){ s.cp_refunded   = true; return ok(s, SwapPhase::Refunded); }
            // A late claim can still happen if the preimage appears before our
            // refund confirms — allow the swap to complete instead.
            if (obs == Observation::PreimageRevealed)           return ok(s, SwapPhase::ClaimSeen);
            if (obs == Observation::SostClaimConfirmed)         { s.sost_claimed = true; return ok(s, reconcile_after_settlement(s)); }
            if (obs == Observation::CounterpartyClaimConfirmed) { s.cp_claimed   = true; return ok(s, reconcile_after_settlement(s)); }
            return err(s, "expected a refund confirmation in RefundReady");
        case SwapPhase::Completed:
        case SwapPhase::Refunded:
        case SwapPhase::Expired:
        case SwapPhase::Failed:
            return err(s, "session is terminal");
        case SwapPhase::RecoveryNeeded:
            return err(s, "session needs manual recovery");
    }
    return err(s, "unhandled phase");
}

StepResult IngestPreimage(Session& s, const std::array<uint8_t, 32>& preimage) {
    // Verify sha256(preimage) == hashlock before trusting it (watcher discipline).
    Bytes32 h = sost::sha256(preimage.data(), preimage.size());
    for (int i = 0; i < 32; ++i) {
        if (h[i] != s.hashlock[i]) return err(s, "revealed preimage does not match hashlock");
    }
    s.have_secret = true;
    s.secret = preimage;
    return Ingest(s, Observation::PreimageRevealed);
}

// ----------------------------------------------------------------------------
// DecideNextStep
// ----------------------------------------------------------------------------
static NextStep step(NextAction a, const std::string& d, bool confirm = false) {
    NextStep n; n.action = a; n.detail = d; n.needs_confirmation = confirm; return n;
}

NextStep DecideNextStep(const Session& s, int64_t current_sost_height) {
    const bool initiator = (s.role == Role::Initiator);
    const int64_t T1 = s.initiator_refund_height;  // SOST refund opens (last)
    const int64_t T2 = s.responder_refund_height;  // counterparty refund opens (first)

    switch (s.phase) {
        case SwapPhase::RecoveryNeeded: {
            NextStep n = step(NextAction::ManualRecovery,
                "Observed facts are inconsistent with the modelled flow. Inspect both "
                "legs on-chain before acting.");
            n.recovery = "Check whether either leg locked/claimed/refunded out of order; "
                         "do NOT lock new funds until reconciled.";
            return n;
        }
        case SwapPhase::Failed:    return step(NextAction::Abort, "Swap failed; no funds were committed beyond what the chains already show.");
        case SwapPhase::Expired:   return step(NextAction::Abort, "Offer/lock window expired before both legs locked; nothing to settle.");
        case SwapPhase::Completed: return step(NextAction::Done, "Both legs settled by claim. Swap complete.");
        case SwapPhase::Refunded:  return step(NextAction::Done, "Refund settled. Swap closed without an exchange.");
        case SwapPhase::Claimed:
            // This wallet already claimed its receiving leg; the counterparty
            // can now claim theirs with the public preimage.
            return step(NextAction::Done, "You claimed your leg; the counterparty can claim theirs with the now-public preimage.");
        default: break;
    }

    if (initiator) {
        switch (s.phase) {
            case SwapPhase::Created:  return step(NextAction::PublishOffer, "Publish the validated offer off-chain (no custody).");
            case SwapPhase::Offered:  return step(NextAction::Wait, "Waiting for a taker to accept the offer.");
            case SwapPhase::Accepted: return step(NextAction::LockSost, "Lock the SOST leg first (you are the initiator).", true);
            case SwapPhase::SostLocked:
                if (current_sost_height >= T1)
                    return step(NextAction::RefundSost, "Counterparty never locked and T1 is reached — refund your SOST lock.", true);
                return step(NextAction::Wait, "SOST locked. Waiting for the responder to lock the counterparty leg.");
            case SwapPhase::CounterpartyLocked: {
                NextStep n = step(NextAction::ClaimCounterparty,
                    "Both legs locked. Claim the counterparty leg with your secret (this reveals the preimage).", true);
                if (current_sost_height >= T2)
                    n.detail += " WARNING: T2 has passed — the responder may refund; claim immediately.";
                return n;
            }
            case SwapPhase::ClaimSeen:
                return step(NextAction::ClaimCounterparty, "Preimage public. Ensure your counterparty-leg claim is confirmed.", true);
            case SwapPhase::RefundReady:
                return step(NextAction::RefundSost, "Refund window open — refund your SOST lock.", true);
            default: break;
        }
    } else {  // Responder
        switch (s.phase) {
            case SwapPhase::Created:  return step(NextAction::Wait, "Waiting for the maker to publish the offer.");
            case SwapPhase::Offered:  return step(NextAction::AcceptOffer, "Review the offer (incl. issuer-freeze warnings) and accept.");
            case SwapPhase::Accepted: return step(NextAction::Wait, "Waiting for the initiator to lock the SOST leg first.");
            case SwapPhase::SostLocked: {
                if (current_sost_height >= T2)
                    return step(NextAction::Wait, "T2 is already reached — do NOT lock; the timeout margin is gone. Abort the swap.");
                NextStep n = step(NextAction::LockCounterparty,
                    "SOST lock confirmed. Lock the counterparty leg (your refund T2 must open before T1).", true);
                return n;
            }
            case SwapPhase::CounterpartyLocked:
                if (current_sost_height >= T2)
                    return step(NextAction::RefundCounterparty, "Initiator never claimed and T2 is reached — refund your counterparty lock.", true);
                return step(NextAction::Wait, "Both legs locked. Waiting for the initiator to claim (revealing the preimage).");
            case SwapPhase::ClaimSeen: {
                if (!s.have_secret)
                    return step(NextAction::Wait, "A claim was seen but the preimage is not ingested yet — read it from the counterparty claim, then claim SOST.");
                NextStep n = step(NextAction::ClaimSost, "Preimage revealed. Claim the SOST leg with it.", true);
                if (current_sost_height >= T1)
                    n.detail += " WARNING: T1 has passed — the initiator may refund SOST; claim immediately.";
                return n;
            }
            case SwapPhase::RefundReady:
                return step(NextAction::RefundCounterparty, "Refund window open — refund your counterparty lock.", true);
            default: break;
        }
    }
    return step(NextAction::Wait, "No action required right now.");
}

// ----------------------------------------------------------------------------
// Persistence (key=value lines; no private keys; secret flagged/optional)
// ----------------------------------------------------------------------------
std::string SerializeSession(const Session& s, bool include_secret) {
    std::ostringstream o;
    o << "# SOST OTC swap session (OTC-4). Local, non-custodial. NO private keys.\n";
    if (include_secret && s.have_secret)
        o << "# WARNING: this record contains the raw swap secret (preimage). "
             "Protect this file; share only the redacted form.\n";
    o << "swap_id=" << s.swap_id << "\n";
    o << "role=" << (s.role == Role::Initiator ? "Initiator" : "Responder") << "\n";
    o << "cp_chain=" << CounterpartyChainName(s.cp_chain) << "\n";
    o << "give=" << AssetName(s.give) << "\n";
    o << "want=" << AssetName(s.want) << "\n";
    o << "give_amount=" << s.give_amount << "\n";
    o << "want_amount=" << s.want_amount << "\n";
    o << "hashlock=" << to_hex(s.hashlock.data(), 32) << "\n";
    o << "initiator_refund_height=" << s.initiator_refund_height << "\n";
    o << "responder_refund_height=" << s.responder_refund_height << "\n";
    o << "safety_margin_min_blocks=" << s.safety_margin_min_blocks << "\n";
    o << "phase=" << SwapPhaseName(s.phase) << "\n";
    o << "issuer_freeze_risk=" << (s.issuer_freeze_risk ? 1 : 0) << "\n";
    o << "sost_claimed=" << (s.sost_claimed ? 1 : 0) << "\n";
    o << "cp_claimed=" << (s.cp_claimed ? 1 : 0) << "\n";
    o << "sost_refunded=" << (s.sost_refunded ? 1 : 0) << "\n";
    o << "cp_refunded=" << (s.cp_refunded ? 1 : 0) << "\n";
    o << "have_secret=" << (s.have_secret ? 1 : 0) << "\n";
    o << "secret=" << ((include_secret && s.have_secret) ? to_hex(s.secret.data(), 32)
                                                          : "REDACTED") << "\n";
    return o.str();
}

bool ParseSession(const std::string& text, Session& out) {
    Session s;
    std::istringstream in(text);
    std::string line;
    bool got_id = false, got_phase = false, got_hashlock = false;
    std::string secret_hex; bool have_secret = false;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        auto eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = line.substr(0, eq), v = line.substr(eq + 1);
        if      (k == "swap_id")  { s.swap_id = v; got_id = true; }
        else if (k == "role")     s.role = (v == "Responder") ? Role::Responder : Role::Initiator;
        else if (k == "cp_chain") { CounterpartyChain c; if (CounterpartyChainParse(v, c)) s.cp_chain = c; }
        else if (k == "give")     { Asset a; if (AssetParse(v, a)) s.give = a; }
        else if (k == "want")     { Asset a; if (AssetParse(v, a)) s.want = a; }
        else if (k == "give_amount") { try { s.give_amount = std::stoll(v); } catch (...) { return false; } }
        else if (k == "want_amount") { try { s.want_amount = std::stoll(v); } catch (...) { return false; } }
        else if (k == "hashlock")    { if (!from_hex(v, s.hashlock.data(), 32)) return false; got_hashlock = true; }
        else if (k == "initiator_refund_height") { try { s.initiator_refund_height = std::stoll(v); } catch (...) { return false; } }
        else if (k == "responder_refund_height") { try { s.responder_refund_height = std::stoll(v); } catch (...) { return false; } }
        else if (k == "safety_margin_min_blocks"){ try { s.safety_margin_min_blocks = std::stoll(v); } catch (...) { return false; } }
        else if (k == "phase")       { SwapPhase p; if (!ParsePhase(v, p)) return false; s.phase = p; got_phase = true; }
        else if (k == "issuer_freeze_risk") s.issuer_freeze_risk = (v == "1");
        else if (k == "sost_claimed")  s.sost_claimed  = (v == "1");
        else if (k == "cp_claimed")    s.cp_claimed    = (v == "1");
        else if (k == "sost_refunded") s.sost_refunded = (v == "1");
        else if (k == "cp_refunded")   s.cp_refunded   = (v == "1");
        else if (k == "have_secret")   have_secret = (v == "1");
        else if (k == "secret")        secret_hex = v;
    }
    if (!got_id || !got_phase || !got_hashlock) return false;
    if (have_secret && secret_hex != "REDACTED") {
        if (!from_hex(secret_hex, s.secret.data(), 32)) return false;
        // Trust-but-verify: the stored secret must still match the hashlock.
        Bytes32 h = sost::sha256(s.secret.data(), s.secret.size());
        for (int i = 0; i < 32; ++i) if (h[i] != s.hashlock[i]) return false;
        s.have_secret = true;
    } else {
        s.have_secret = false;  // redacted / absent -> resume without the secret
    }
    if (is_zero(s.hashlock)) return false;
    out = s;
    return true;
}

}  // namespace session
}  // namespace atomic_swap
}  // namespace sost
