// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// btc_watch.cpp — BTC-leg watch decision + restart-recovery store.
// Decision is pure; store does file I/O; reconcile reads a (possibly Null)
// BitcoinBackend. See the header for the fund-safety contract.

#include "sost/btc_watch.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace sost {
namespace atomic_swap {
namespace btc {

const char* BtcWatchActionName(BtcWatchAction a) {
    switch (a) {
        case BtcWatchAction::Wait:              return "Wait";
        case BtcWatchAction::WaitConfirmations: return "WaitConfirmations";
        case BtcWatchAction::Claim:             return "Claim";
        case BtcWatchAction::Refund:            return "Refund";
        case BtcWatchAction::Done:              return "Done";
        case BtcWatchAction::Failed:            return "Failed";
    }
    return "?";
}

// --------------------------------------------------------------------------
// Pure decision
// --------------------------------------------------------------------------

BtcWatchAction DecideBtcWatchAction(const BtcSwapRecord& r, const BtcChainFacts& f) {
    if (r.state == BtcSwapState::Failed)   return BtcWatchAction::Failed;
    if (r.state == BtcSwapState::Redeemed ||
        r.state == BtcSwapState::Refunded) return BtcWatchAction::Done;

    // The HTLC output is already spent (claimed or refunded, by us or the
    // counterparty): nothing left to broadcast.
    if (f.htlc_output_spent) return BtcWatchAction::Done;

    int64_t min_conf = f.min_confirmations < 1 ? 1 : f.min_confirmations;
    bool funded = (f.funding_state == BtcTxState::Confirmed) &&
                  (f.funding_confirmations >= min_conf);

    if (!funded) {
        // Nothing on chain expected before we broadcast funding.
        if (r.state == BtcSwapState::Created) return BtcWatchAction::Wait;
        // Broadcast/seen but not (yet / still) min-confirmed — includes reorg.
        return BtcWatchAction::WaitConfirmations;
    }

    // Funded and locked on BTC.
    if (r.party == BtcParty::Claimant) {
        if (r.have_preimage && f.current_height >= 0 && f.current_height < r.refund_height)
            return BtcWatchAction::Claim;
        if (f.current_height >= 0 && f.current_height >= r.refund_height)
            return BtcWatchAction::Done;   // window closed; claimant cannot claim/refund
        return BtcWatchAction::Wait;       // funded, window open, no preimage yet
    } else {  // Funder
        if (f.current_height >= 0 && f.current_height >= r.refund_height)
            return BtcWatchAction::Refund;
        return BtcWatchAction::Wait;       // funded, timeout not reached
    }
}

// --------------------------------------------------------------------------
// Store — file-backed, 0600
// --------------------------------------------------------------------------

bool BtcSwapStore::Load(const std::string& path) {
    std::ifstream f(path);
    if (!f) return true;  // missing file → empty store (not an error)
    std::stringstream ss;
    ss << f.rdbuf();
    if (f.bad()) return false;
    ParseBtcSwapList(ss.str(), records_);
    return true;
}

bool BtcSwapStore::Save(const std::string& path) const {
    std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp, std::ios::trunc);
        if (!f) return false;
        f << SerializeBtcSwapList(records_);
        f.flush();
        if (!f.good()) return false;
    }
    // 0600 — the file contains the preimage in cleartext.
    if (::chmod(tmp.c_str(), S_IRUSR | S_IWUSR) != 0) { ::unlink(tmp.c_str()); return false; }
    if (::rename(tmp.c_str(), path.c_str()) != 0) { ::unlink(tmp.c_str()); return false; }
    return true;
}

BtcSwapRecord* BtcSwapStore::Find(const std::string& swap_id) {
    for (auto& r : records_) if (r.swap_id == swap_id) return &r;
    return nullptr;
}
const BtcSwapRecord* BtcSwapStore::Find(const std::string& swap_id) const {
    for (const auto& r : records_) if (r.swap_id == swap_id) return &r;
    return nullptr;
}

void BtcSwapStore::Upsert(const BtcSwapRecord& r) {
    for (auto& e : records_) {
        if (e.swap_id == r.swap_id) { e = r; return; }
    }
    records_.push_back(r);
}

// --------------------------------------------------------------------------
// Reconcile against the chain (idempotent, check-before-send)
// --------------------------------------------------------------------------

BtcWatchAction ReconcileBtcSwapWithChain(BtcSwapRecord& r, BitcoinBackend& backend,
                                         int64_t min_confirmations) {
    if (min_confirmations < 1) min_confirmations = 1;

    if (!backend.IsConfigured()) {
        // Option A / Null backend: no chain facts. Fail-closed — never Claim or
        // Refund without positive confirmation. Report the stored-state action.
        BtcChainFacts f;
        f.min_confirmations = min_confirmations;   // funding_state stays Unknown
        return DecideBtcWatchAction(r, f);
    }

    // 1. If we already have a claim tx recorded, let its on-chain status drive
    //    state — do NOT re-broadcast.
    if (!r.claim_txid.empty()) {
        auto st = backend.GetTransactionStatus(r.claim_txid);
        if (st.ok && st.state == BtcTxState::Confirmed) {
            ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRedeemable);
            ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);
            ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimConfirmed);
            r.last_confirmations = st.confirmations;
        } else if (st.ok && st.state == BtcTxState::InMempool) {
            ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRedeemable);
            ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);
        }
    }
    // 2. Same for a refund tx.
    if (!r.refund_txid.empty()) {
        auto st = backend.GetTransactionStatus(r.refund_txid);
        if (st.ok && st.state == BtcTxState::Confirmed) {
            ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRefundable);
            ApplyBtcSwapEvent(r, BtcSwapEvent::RefundBroadcast);
            ApplyBtcSwapEvent(r, BtcSwapEvent::RefundConfirmed);
            r.last_confirmations = st.confirmations;
        } else if (st.ok && st.state == BtcTxState::InMempool) {
            ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRefundable);
            ApplyBtcSwapEvent(r, BtcSwapEvent::RefundBroadcast);
        }
    }

    // 3. Funding status → advance to Locked when min-confirmed.
    BtcChainFacts f;
    f.min_confirmations = min_confirmations;
    auto h = backend.GetBlockHeight();
    if (h.ok) f.current_height = h.height;
    if (!r.funding_txid.empty()) {
        auto fs = backend.GetTransactionStatus(r.funding_txid);
        if (fs.ok) {
            f.funding_state = fs.state;
            f.funding_confirmations = fs.confirmations;
            if (fs.state != BtcTxState::NotFound) {
                ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
            }
            if (fs.state == BtcTxState::Confirmed && fs.confirmations >= min_confirmations) {
                ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
            }
        }
    }

    return DecideBtcWatchAction(r, f);
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
