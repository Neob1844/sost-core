// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_btc_swap_state.cpp — BTC swap state machine + record persistence.

#include "sost/btc_swap_state.h"
#include "sost/crypto.h"

#include <array>
#include <cstdio>
#include <string>
#include <vector>

using namespace sost;
using namespace sost::atomic_swap::btc;

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); ++g_fail; } \
    else         { std::printf("ok:   %s\n", msg); } \
} while (0)

static std::string hex(const uint8_t* p, size_t n) {
    static const char* H = "0123456789abcdef";
    std::string s; for (size_t i=0;i<n;++i){ s.push_back(H[p[i]>>4]); s.push_back(H[p[i]&0xF]); } return s;
}

int main() {
    std::printf("=== test_btc_swap_state ===\n");

    // Happy claim path.
    {
        BtcSwapRecord r; r.swap_id = "s1"; r.party = BtcParty::Claimant;
        CHECK(r.state == BtcSwapState::Created, "starts Created");
        auto a = ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
        CHECK(a.ok && a.changed && r.state == BtcSwapState::FundingBroadcast, "Created→FundingBroadcast");
        auto b = ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
        CHECK(b.ok && b.changed && r.state == BtcSwapState::Locked, "FundingBroadcast→Locked");
        auto c = ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRedeemable);
        CHECK(c.ok && c.changed && r.state == BtcSwapState::Redeemable, "Locked→Redeemable");
        auto d = ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);
        CHECK(d.ok && d.changed && r.state == BtcSwapState::Redeeming, "Redeemable→Redeeming");
        auto e = ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimConfirmed);
        CHECK(e.ok && e.changed && r.state == BtcSwapState::Redeemed, "Redeeming→Redeemed");
        CHECK(IsBtcSwapTerminal(r.state), "Redeemed is terminal");
    }

    // Refund path.
    {
        BtcSwapRecord r; r.swap_id = "s2"; r.party = BtcParty::Funder;
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
        auto a = ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRefundable);
        CHECK(a.ok && a.changed && r.state == BtcSwapState::Refundable, "Locked→Refundable");
        auto b = ApplyBtcSwapEvent(r, BtcSwapEvent::RefundBroadcast);
        CHECK(b.ok && b.changed && r.state == BtcSwapState::Refunding, "Refundable→Refunding");
        auto c = ApplyBtcSwapEvent(r, BtcSwapEvent::RefundConfirmed);
        CHECK(c.ok && c.changed && r.state == BtcSwapState::Refunded, "Refunding→Refunded");
    }

    // Idempotency + double-spend guard.
    {
        BtcSwapRecord r; r.swap_id = "s3";
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
        ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRedeemable);
        auto first = ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);
        CHECK(first.ok && first.changed, "first ClaimBroadcast changes state (→ broadcast)");
        auto again = ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);
        CHECK(again.ok && !again.changed, "second ClaimBroadcast is idempotent no-op (NO re-broadcast)");
        auto fc = ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
        CHECK(fc.ok && !fc.changed, "late FundingConfirmed is idempotent no-op");
    }

    // Illegal transitions.
    {
        BtcSwapRecord r; r.swap_id = "s4";
        auto bad = ApplyBtcSwapEvent(r, BtcSwapEvent::ClaimBroadcast);   // from Created
        CHECK(!bad.ok, "ClaimBroadcast from Created is illegal");
        // reach Refundable, then a claim must be illegal (window closed)
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingConfirmed);
        ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRefundable);
        auto noredeem = ApplyBtcSwapEvent(r, BtcSwapEvent::BecameRedeemable);
        CHECK(!noredeem.ok, "BecameRedeemable from Refundable is illegal (no claim after window)");
    }

    // Fail semantics.
    {
        BtcSwapRecord r; r.swap_id = "s5";
        ApplyBtcSwapEvent(r, BtcSwapEvent::FundingBroadcast);
        auto f = ApplyBtcSwapEvent(r, BtcSwapEvent::Fail);
        CHECK(f.ok && f.changed && r.state == BtcSwapState::Failed, "Fail from non-terminal → Failed");
        auto f2 = ApplyBtcSwapEvent(r, BtcSwapEvent::Fail);
        CHECK(f2.ok && !f2.changed, "Fail again is no-op");

        BtcSwapRecord done; done.swap_id = "s6";
        ApplyBtcSwapEvent(done, BtcSwapEvent::FundingBroadcast);
        ApplyBtcSwapEvent(done, BtcSwapEvent::FundingConfirmed);
        ApplyBtcSwapEvent(done, BtcSwapEvent::BecameRedeemable);
        ApplyBtcSwapEvent(done, BtcSwapEvent::ClaimBroadcast);
        ApplyBtcSwapEvent(done, BtcSwapEvent::ClaimConfirmed);
        auto nf = ApplyBtcSwapEvent(done, BtcSwapEvent::Fail);
        CHECK(!nf.ok, "cannot Fail a completed (Redeemed) swap");
    }

    // Preimage ingest.
    {
        std::array<uint8_t,32> pre; pre.fill(0x42);
        Bytes32 hl = sha256(pre.data(), pre.size());
        BtcSwapRecord r; r.swap_id = "s7"; r.hashlock_hex = hex(hl.data(), hl.size());
        CHECK(!r.have_preimage, "no preimage initially");
        bool wrong = IngestBtcPreimage(r, std::string(64, '0'));
        CHECK(!wrong && !r.have_preimage, "non-matching preimage rejected");
        bool okp = IngestBtcPreimage(r, hex(pre.data(), pre.size()));
        CHECK(okp && r.have_preimage, "matching preimage accepted");
    }

    // Serialize / parse round-trip.
    {
        BtcSwapRecord r; r.swap_id = "swap-XYZ"; r.party = BtcParty::Claimant;
        r.network = "regtest"; r.hashlock_hex = std::string(64,'a');
        r.redeem_script_hex = "aabbcc"; r.htlc_address = "bcrt1qxyz";
        r.lock_amount_sats = 123456; r.refund_height = 800100;
        r.claim_dest_addr = "bcrt1qclaim"; r.refund_dest_addr = "bcrt1qrefund";
        r.fee_sats = 250; r.funding_txid = std::string(64,'f'); r.funding_vout = 2;
        r.claim_txid = std::string(64,'c'); r.last_confirmations = 4;
        r.have_preimage = true; r.preimage_hex = std::string(64,'e');
        r.state = BtcSwapState::Redeeming;

        std::string line = SerializeBtcSwapRecord(r);
        BtcSwapRecord back;
        bool ok = ParseBtcSwapRecord(line, back);
        CHECK(ok, "record parses");
        CHECK(back.swap_id == r.swap_id, "rt swap_id");
        CHECK(back.party == r.party, "rt party");
        CHECK(back.network == r.network, "rt network");
        CHECK(back.lock_amount_sats == r.lock_amount_sats, "rt amount");
        CHECK(back.refund_height == r.refund_height, "rt refund_height");
        CHECK(back.funding_txid == r.funding_txid, "rt funding_txid");
        CHECK(back.funding_vout == r.funding_vout, "rt funding_vout");
        CHECK(back.fee_sats == r.fee_sats, "rt fee");
        CHECK(back.have_preimage == r.have_preimage, "rt have_preimage");
        CHECK(back.preimage_hex == r.preimage_hex, "rt preimage");
        CHECK(back.state == r.state, "rt state");

        std::vector<BtcSwapRecord> list = { r, back };
        std::string blob = SerializeBtcSwapList(list);
        std::vector<BtcSwapRecord> parsed;
        ParseBtcSwapList(blob, parsed);
        CHECK(parsed.size() == 2, "list round-trip size");
    }

    std::printf("=== %s ===\n", g_fail == 0 ? "ALL PASS" : "FAILURES");
    return g_fail == 0 ? 0 : 1;
}
