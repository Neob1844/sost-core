// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// test_btc_funding.cpp — BTC HTLC funding coin-selection (pure) + gated plan.

#include "sost/btc_funding.h"

#include <array>
#include <cstdio>
#include <string>
#include <vector>

using namespace sost::atomic_swap::btc;

static int g_fail = 0;
#define CHECK(cond, msg) do { \
    if (!(cond)) { std::printf("FAIL: %s\n", msg); ++g_fail; } \
    else         { std::printf("ok:   %s\n", msg); } \
} while (0)

static BtcUtxo utxo(const std::string& id, uint32_t vout, int64_t sats, int64_t conf = 10) {
    BtcUtxo u; u.txid = id; u.vout = vout; u.amount_sats = sats; u.confirmations = conf; return u;
}

int main() {
    std::printf("=== test_btc_funding ===\n");
    BtcVsizeModel M;  // defaults

    // Fee model monotonicity.
    {
        int64_t f1 = BtcFundingFee(M, 1, false, 10);
        int64_t f1c = BtcFundingFee(M, 1, true, 10);
        int64_t f2 = BtcFundingFee(M, 2, false, 10);
        CHECK(f1c > f1, "change output costs more fee");
        CHECK(f2 > f1, "more inputs cost more fee");
        CHECK(f1 == (int64_t)(M.tx_overhead + M.per_p2wpkh_in + M.p2wsh_out) * 10, "fee formula (1 in, no change)");
    }

    // Selection with a clear change output.
    {
        std::vector<BtcUtxo> u = { utxo(std::string(64,'1'), 0, 1000000) };
        auto s = SelectBtcFundingUtxos(u, 500000, 10, M);
        CHECK(s.ok, "select ok (big utxo)");
        CHECK(s.selected.size() == 1, "one input selected");
        CHECK(s.has_change, "has change");
        CHECK(s.total_in_sats == 1000000, "total_in");
        CHECK(s.change_sats == s.total_in_sats - 500000 - s.fee_sats, "change = in - target - fee");
        CHECK(s.change_sats > kBtcP2wpkhDustSats, "change above dust");
    }

    // Dust change is folded into the fee (no dust output).
    {
        // Pick target so surplus after fee is < dust. fee(1,false)=... make
        // total_in = target + fee_nc + small(<dust).
        int64_t target = 100000;
        int64_t fee_nc = BtcFundingFee(M, 1, false, 5);
        int64_t total = target + fee_nc + 100;  // 100 sat surplus (< dust 294)
        std::vector<BtcUtxo> u = { utxo(std::string(64,'2'), 1, total) };
        auto s = SelectBtcFundingUtxos(u, target, 5, M);
        CHECK(s.ok, "select ok (dust surplus)");
        CHECK(!s.has_change, "no change output (dust folded)");
        CHECK(s.change_sats == 0, "change zero");
        CHECK(s.fee_sats == total - target, "surplus folded into fee");
    }

    // Insufficient funds.
    {
        std::vector<BtcUtxo> u = { utxo(std::string(64,'3'), 0, 1000) };
        auto s = SelectBtcFundingUtxos(u, 500000, 10, M);
        CHECK(!s.ok, "insufficient → not ok");
        CHECK(s.error.find("insufficient") != std::string::npos, "insufficient message");
    }

    // Multi-input accumulation (largest-first).
    {
        std::vector<BtcUtxo> u = {
            utxo(std::string(64,'a'), 0, 300000),
            utxo(std::string(64,'b'), 1, 300000),
            utxo(std::string(64,'c'), 2, 300000),
        };
        auto s = SelectBtcFundingUtxos(u, 700000, 8, M);
        CHECK(s.ok, "multi-input select ok");
        CHECK(s.selected.size() == 3, "needs all three inputs");
        CHECK(s.total_in_sats == 900000, "multi total_in");
    }

    // Single-UTXO selection picks the smallest that covers.
    {
        std::vector<BtcUtxo> u = {
            utxo(std::string(64,'a'), 0, 2000000),
            utxo(std::string(64,'b'), 1, 600000),   // smallest that covers 500k+fee
            utxo(std::string(64,'c'), 2, 5000000),
        };
        auto s = SelectSingleBtcFundingUtxo(u, 500000, 10, M);
        CHECK(s.ok, "single select ok");
        CHECK(s.selected.size() == 1, "single input");
        CHECK(s.selected[0].amount_sats == 600000, "picks smallest covering utxo");
    }
    {
        std::vector<BtcUtxo> u = { utxo(std::string(64,'a'), 0, 400000),
                                   utxo(std::string(64,'b'), 1, 450000) };
        auto s = SelectSingleBtcFundingUtxo(u, 500000, 10, M);
        CHECK(!s.ok, "no single utxo covers → fail (needs multi-input path)");
    }

    // Orchestration plan with signing gate OFF (Option A).
    {
        std::vector<BtcUtxo> u = { utxo(std::string(64,'1'), 0, 1000000) };
        std::vector<uint8_t> redeem = { 0x00, 0x01, 0x02 };
        std::array<uint8_t,32> key{}; key.fill(0x11);
        auto plan = PlanBtcHtlcFunding(u, 500000, 10, redeem, "bc1qhtlc...",
                                       key, "bc1qchange...", "mainnet", M);
        CHECK(plan.ok, "plan ok (selection produced)");
        CHECK(plan.selection.ok && plan.selection.selected.size() == 1, "plan carries selection");
        // In Option A (gate OFF) IsBtcHtlcSigningEnabled()==false → no signed tx.
        CHECK(!plan.signed_tx, "gate OFF → no signed tx");
        CHECK(plan.funding_raw_tx_hex.empty(), "gate OFF → empty raw tx");
        CHECK(plan.funding_note.find("disabled") != std::string::npos, "note says disabled");
    }

    std::printf("=== %s ===\n", g_fail == 0 ? "ALL PASS" : "FAILURES");
    return g_fail == 0 ? 0 : 1;
}
