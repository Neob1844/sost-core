// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// btc_funding.cpp — HTLC funding coin-selection + (gated) signing orchestration.
// The selection math is pure and unit-tested; the signing tie-in is behind the
// SOST_BTC_HTLC_SIGNING gate and returns fail-closed in Option A.

#include "sost/btc_funding.h"

#include <algorithm>
#include <array>

namespace sost {
namespace atomic_swap {
namespace btc {

int64_t BtcFundingFee(const BtcVsizeModel& m, int num_inputs, bool with_change,
                      int64_t fee_rate_sat_vb) {
    if (num_inputs < 0) num_inputs = 0;
    if (fee_rate_sat_vb < 1) fee_rate_sat_vb = 1;
    int64_t vsize = m.tx_overhead
                  + (int64_t)num_inputs * m.per_p2wpkh_in
                  + m.p2wsh_out
                  + (with_change ? m.p2wpkh_change : 0);
    return vsize * fee_rate_sat_vb;
}

// Finalise a selection given the accumulated inputs — decide change vs fold.
static BtcCoinSelection finalise(std::vector<BtcUtxo> sel, int64_t total_in,
                                 int64_t target_sats, int64_t fee_rate_sat_vb,
                                 const BtcVsizeModel& model) {
    BtcCoinSelection s;
    int k = (int)sel.size();
    int64_t fee_wc = BtcFundingFee(model, k, /*with_change=*/true, fee_rate_sat_vb);
    int64_t change_wc = total_in - target_sats - fee_wc;
    if (change_wc > kBtcP2wpkhDustSats) {
        s.fee_sats = fee_wc;
        s.change_sats = change_wc;
        s.has_change = true;
    } else {
        // Change would be dust (or negative): drop the change output and fold
        // the surplus into the fee. Never create a dust output.
        s.fee_sats = total_in - target_sats;   // >= no-change fee (guaranteed by caller)
        s.change_sats = 0;
        s.has_change = false;
    }
    s.selected = std::move(sel);
    s.total_in_sats = total_in;
    s.ok = true;
    return s;
}

BtcCoinSelection SelectBtcFundingUtxos(const std::vector<BtcUtxo>& utxos,
                                       int64_t target_sats,
                                       int64_t fee_rate_sat_vb,
                                       const BtcVsizeModel& model) {
    BtcCoinSelection s;
    if (target_sats <= 0)       { s.error = "target amount must be positive"; return s; }
    if (fee_rate_sat_vb < 1)    { s.error = "fee rate must be >= 1 sat/vByte"; return s; }
    if (utxos.empty())          { s.error = "no spendable UTXOs"; return s; }

    std::vector<BtcUtxo> sorted = utxos;
    std::sort(sorted.begin(), sorted.end(),
              [](const BtcUtxo& a, const BtcUtxo& b) { return a.amount_sats > b.amount_sats; });

    std::vector<BtcUtxo> acc;
    int64_t total_in = 0;
    for (const auto& u : sorted) {
        if (u.amount_sats <= 0) continue;
        acc.push_back(u);
        total_in += u.amount_sats;
        int k = (int)acc.size();
        int64_t fee_nc = BtcFundingFee(model, k, /*with_change=*/false, fee_rate_sat_vb);
        if (total_in >= target_sats + fee_nc) {
            return finalise(std::move(acc), total_in, target_sats, fee_rate_sat_vb, model);
        }
    }
    s.error = "insufficient confirmed balance for amount + fee";
    s.total_in_sats = total_in;
    return s;
}

BtcCoinSelection SelectSingleBtcFundingUtxo(const std::vector<BtcUtxo>& utxos,
                                            int64_t target_sats,
                                            int64_t fee_rate_sat_vb,
                                            const BtcVsizeModel& model) {
    BtcCoinSelection s;
    if (target_sats <= 0)    { s.error = "target amount must be positive"; return s; }
    if (fee_rate_sat_vb < 1) { s.error = "fee rate must be >= 1 sat/vByte"; return s; }
    if (utxos.empty())       { s.error = "no spendable UTXOs"; return s; }

    int64_t fee_nc = BtcFundingFee(model, 1, /*with_change=*/false, fee_rate_sat_vb);
    int64_t need   = target_sats + fee_nc;

    // Smallest single UTXO that still covers target+fee (minimise change).
    const BtcUtxo* best = nullptr;
    for (const auto& u : utxos) {
        if (u.amount_sats < need) continue;
        if (!best || u.amount_sats < best->amount_sats) best = &u;
    }
    if (!best) {
        s.error = "no single UTXO covers amount + fee (multi-input funding needs "
                  "the N-input signing path)";
        return s;
    }
    std::vector<BtcUtxo> acc = { *best };
    return finalise(std::move(acc), best->amount_sats, target_sats, fee_rate_sat_vb, model);
}

// hex (display, big-endian) → 32 raw bytes. Returns false on bad input.
static bool hex64_to_bytes32(const std::string& hex, std::array<uint8_t, 32>& out) {
    if (hex.size() != 64) return false;
    auto hv = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < 32; ++i) {
        int hi = hv(hex[i*2]), lo = hv(hex[i*2+1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

BtcFundingPlan PlanBtcHtlcFunding(const std::vector<BtcUtxo>& utxos,
                                  int64_t lock_amount_sats,
                                  int64_t fee_rate_sat_vb,
                                  const std::vector<uint8_t>& redeem_script,
                                  const std::string& htlc_address,
                                  const std::array<uint8_t, 32>& funder_privkey,
                                  const std::string& funder_change_addr,
                                  const std::string& bitcoin_network,
                                  const BtcVsizeModel& model) {
    BtcFundingPlan plan;
    plan.htlc_address = htlc_address;
    plan.lock_amount_sats = lock_amount_sats;

    // The current signing API consumes a single input.
    BtcCoinSelection sel = SelectSingleBtcFundingUtxo(utxos, lock_amount_sats,
                                                      fee_rate_sat_vb, model);
    plan.selection = sel;
    if (!sel.ok) { plan.error = sel.error; return plan; }
    plan.ok = true;

    if (!IsBtcHtlcSigningEnabled()) {
        plan.signed_tx = false;
        plan.funding_note = "signing disabled (Option A / gate OFF) — selection only, no raw tx";
        return plan;
    }

    // Gate ON: build+sign the funding tx. NOTE: prev_txid byte-order and the
    // full sighash path are validated against a real bitcoind-regtest as a
    // separate step (owner-waived here); this path is never reached in the
    // deployed Option A build (0 signing symbols).
    const BtcUtxo& u = sel.selected.front();
    std::array<uint8_t, 32> prev_txid{};
    if (!hex64_to_bytes32(u.txid, prev_txid)) {
        plan.funding_note = "selected UTXO txid is not 32-byte hex";
        return plan;
    }
    BtcSigningResult r = SignBtcHtlcLockFunding(
        prev_txid, u.vout, u.amount_sats, funder_privkey, funder_change_addr,
        redeem_script, lock_amount_sats, sel.fee_sats, bitcoin_network);
    if (r.ok) {
        plan.signed_tx = true;
        plan.funding_raw_tx_hex = r.raw_tx_hex;
        plan.funding_note = "funding tx built + signed";
    } else {
        plan.signed_tx = false;
        plan.funding_note = std::string("signing failed: ") + r.error;
    }
    return plan;
}

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
