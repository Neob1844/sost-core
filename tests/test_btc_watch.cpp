// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_btc_watch.cpp — BTC-leg watch decision, restart-recovery store, and
// idempotent chain reconciliation (check-before-send).

#include "sost/btc_watch.h"

#include <cstdio>
#include <map>
#include <string>
#include <sys/stat.h>

using namespace sost::atomic_swap::btc;

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); ++g_fail; } \
    else         { std::printf("ok:   %s\n", msg); } \
} while (0)

// A programmable backend: returns canned statuses keyed by txid.
class MockBackend : public BitcoinBackend {
public:
    int64_t height = 800000;
    std::map<std::string, BtcTxStatus> statuses;

    std::string Name() const override { return "mock"; }
    bool IsConfigured() const override { return true; }
    std::string Network() const override { return "regtest"; }
    BtcBroadcastResult BroadcastRawTransaction(const std::string&) override { BtcBroadcastResult r; r.ok=true; r.txid=std::string(64,'b'); return r; }
    BtcRawTxResult GetRawTransaction(const std::string&) override { BtcRawTxResult r; r.ok=true; r.raw_tx_hex="00"; return r; }
    BtcTxStatus GetTransactionStatus(const std::string& txid) override {
        auto it = statuses.find(txid);
        if (it != statuses.end()) return it->second;
        BtcTxStatus s; s.ok=true; s.state=BtcTxState::NotFound; return s;
    }
    BtcHeightResult GetBlockHeight() override { BtcHeightResult r; r.ok=true; r.height=height; return r; }
    BtcFeeResult EstimateFeeRate(int) override { BtcFeeResult r; r.ok=true; r.sat_per_vbyte=5; return r; }
    BtcListUnspentResult ListUnspent(int, const std::string&) override { BtcListUnspentResult r; r.ok=true; return r; }
};

static BtcTxStatus confirmed(int64_t c) { BtcTxStatus s; s.ok=true; s.state=BtcTxState::Confirmed; s.confirmations=c; return s; }
static BtcTxStatus mempool()            { BtcTxStatus s; s.ok=true; s.state=BtcTxState::InMempool; return s; }

int main() {
    std::printf("=== test_btc_watch ===\n");

    // ---- Pure decision ----
    {
        BtcSwapRecord r; r.party = BtcParty::Claimant; r.refund_height = 800100; r.state = BtcSwapState::Created;
        BtcChainFacts f; f.min_confirmations = 1;
        CHECK(DecideBtcWatchAction(r, f) == BtcWatchAction::Wait, "Created + nothing → Wait");

        r.state = BtcSwapState::FundingBroadcast;
        f.funding_state = BtcTxState::InMempool; f.funding_confirmations = 0;
        CHECK(DecideBtcWatchAction(r, f) == BtcWatchAction::WaitConfirmations, "funding in mempool → WaitConfirmations");

        // funded, claimant, preimage, window open
        f.funding_state = BtcTxState::Confirmed; f.funding_confirmations = 3;
        f.current_height = 800000; r.have_preimage = true; r.state = BtcSwapState::Locked;
        CHECK(DecideBtcWatchAction(r, f) == BtcWatchAction::Claim, "funded+preimage+open → Claim");

        r.have_preimage = false;
        CHECK(DecideBtcWatchAction(r, f) == BtcWatchAction::Wait, "funded, no preimage → Wait");

        r.have_preimage = true; f.current_height = 800100;  // window closed
        CHECK(DecideBtcWatchAction(r, f) == BtcWatchAction::Done, "claimant window closed → Done");

        // funder
        BtcSwapRecord g; g.party = BtcParty::Funder; g.refund_height = 800100; g.state = BtcSwapState::Locked;
        BtcChainFacts gf; gf.funding_state = BtcTxState::Confirmed; gf.funding_confirmations = 6; gf.min_confirmations = 6;
        gf.current_height = 800050;
        CHECK(DecideBtcWatchAction(g, gf) == BtcWatchAction::Wait, "funder before timeout → Wait");
        gf.current_height = 800100;
        CHECK(DecideBtcWatchAction(g, gf) == BtcWatchAction::Refund, "funder at timeout → Refund");

        // reorg: was confirmed, confs drop below min → WaitConfirmations
        gf.funding_confirmations = 2;  // below min_confirmations=6
        CHECK(DecideBtcWatchAction(g, gf) == BtcWatchAction::WaitConfirmations, "reorg drops confs → WaitConfirmations");

        // spent → Done
        gf.funding_confirmations = 6; gf.htlc_output_spent = true;
        CHECK(DecideBtcWatchAction(g, gf) == BtcWatchAction::Done, "htlc spent → Done");
    }

    // ---- Store round-trip + 0600 ----
    {
        std::string path = "/tmp/claude-1001/btc_swaps_test.dat";
        BtcSwapStore store;
        BtcSwapRecord a; a.swap_id="A"; a.party=BtcParty::Funder; a.refund_height=800200; a.funding_txid=std::string(64,'f');
        a.state=BtcSwapState::Locked; a.lock_amount_sats=500000;
        BtcSwapRecord b; b.swap_id="B"; b.party=BtcParty::Claimant; b.have_preimage=true; b.preimage_hex=std::string(64,'e');
        b.state=BtcSwapState::Redeeming; b.claim_txid=std::string(64,'c');
        store.Upsert(a); store.Upsert(b);
        CHECK(store.Save(path), "store saves");

        struct stat st{};
        CHECK(::stat(path.c_str(), &st) == 0, "store file exists");
        CHECK((st.st_mode & 0777) == 0600, "store file is 0600");

        BtcSwapStore loaded;
        CHECK(loaded.Load(path), "store loads");
        CHECK(loaded.records().size() == 2, "two records reloaded");
        auto* pa = loaded.Find("A");
        CHECK(pa && pa->state == BtcSwapState::Locked && pa->lock_amount_sats == 500000, "record A survives restart");
        auto* pb = loaded.Find("B");
        CHECK(pb && pb->have_preimage && pb->claim_txid == std::string(64,'c'), "record B survives restart");

        // Upsert replaces.
        BtcSwapRecord a2 = a; a2.state = BtcSwapState::Refunded;
        loaded.Upsert(a2);
        CHECK(loaded.records().size() == 2, "upsert does not duplicate");
        CHECK(loaded.Find("A")->state == BtcSwapState::Refunded, "upsert replaces state");

        // missing file → empty, ok
        BtcSwapStore empty;
        CHECK(empty.Load("/tmp/claude-1001/does_not_exist_xyz.dat"), "missing file loads empty ok");
        CHECK(empty.records().empty(), "missing file → empty");
    }

    // ---- Reconcile: Null backend fail-closed ----
    {
        NullBitcoinBackend nb;
        BtcSwapRecord r; r.swap_id="N"; r.party=BtcParty::Funder; r.state=BtcSwapState::Locked; r.refund_height=1;
        auto act = ReconcileBtcSwapWithChain(r, nb, 1);
        CHECK(act != BtcWatchAction::Claim && act != BtcWatchAction::Refund,
              "Null backend never yields Claim/Refund (fail-closed)");
    }

    // ---- Reconcile: recorded claim confirmed → Redeemed, no re-broadcast ----
    {
        MockBackend mb;
        std::string ctxid = std::string(64,'c');
        mb.statuses[ctxid] = confirmed(3);
        BtcSwapRecord r; r.swap_id="R1"; r.party=BtcParty::Claimant; r.state=BtcSwapState::Redeeming;
        r.claim_txid = ctxid; r.refund_height = 900000; r.have_preimage = true;
        auto act = ReconcileBtcSwapWithChain(r, mb, 1);
        CHECK(r.state == BtcSwapState::Redeemed, "recorded claim confirmed → state Redeemed");
        CHECK(act == BtcWatchAction::Done, "reconciled Redeemed → Done (no re-broadcast)");
    }

    // ---- Reconcile: funding confirmed advances to Locked; funder past timeout → Refund ----
    {
        MockBackend mb; mb.height = 900100;
        std::string ftxid = std::string(64,'f');
        mb.statuses[ftxid] = confirmed(6);
        BtcSwapRecord r; r.swap_id="R2"; r.party=BtcParty::Funder; r.state=BtcSwapState::FundingBroadcast;
        r.funding_txid = ftxid; r.refund_height = 900000;
        auto act = ReconcileBtcSwapWithChain(r, mb, 6);
        CHECK(r.state == BtcSwapState::Locked, "funding confirmed → Locked");
        CHECK(act == BtcWatchAction::Refund, "funder past timeout after reconcile → Refund");
    }

    // ---- Reconcile: recorded claim in mempool → Redeeming (not re-broadcast) ----
    {
        MockBackend mb;
        std::string ctxid = std::string(64,'a');
        mb.statuses[ctxid] = mempool();
        BtcSwapRecord r; r.swap_id="R3"; r.party=BtcParty::Claimant; r.state=BtcSwapState::Redeemable;
        r.claim_txid = ctxid; r.refund_height = 900000; r.have_preimage = true;
        ReconcileBtcSwapWithChain(r, mb, 1);
        CHECK(r.state == BtcSwapState::Redeeming, "recorded claim in mempool → Redeeming");
    }

    std::printf("=== %s ===\n", g_fail == 0 ? "ALL PASS" : "FAILURES");
    return g_fail == 0 ? 0 : 1;
}
