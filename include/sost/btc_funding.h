// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap BTC — HTLC funding coin-selection + orchestration (OTC-6)
// =============================================================================
//
// Closes the "funding is caller-supplied, no coin selection" gap. Given the
// spendable UTXOs the backend reported (BitcoinBackend::ListUnspent), a target
// HTLC amount and a fee rate, this picks inputs, computes the fee from a
// SegWit vsize model, and derives the change — dust-aware (a change output at
// or below the P2WPKH dust threshold is dropped and folded into the fee, never
// routed to a dust output).
//
// The selection is PURE (no network, no libwally) so it is exhaustively unit
// tested. Building/signing the actual funding tx is done by
// SignBtcHtlcLockFunding in the gated signing module; PlanBtcHtlcFunding ties
// the two together and, with SOST_BTC_HTLC_SIGNING=OFF (Option A), returns the
// plan WITHOUT a signed tx (fail-closed).
// =============================================================================
#pragma once

#include "sost/bitcoin_backend.h"   // BtcUtxo
#include "sost/atomic_swap_btc_signing.h"   // kBtcP2wpkhDustSats

#include <cstdint>
#include <string>
#include <vector>

namespace sost {
namespace atomic_swap {
namespace btc {

// SegWit vsize model (vbytes) for a P2WPKH-inputs → P2WSH-HTLC (+ optional
// P2WPKH change) funding tx. Deliberately slightly conservative.
struct BtcVsizeModel {
    int tx_overhead   = 11;   // version+locktime+segwit marker/flag+counts
    int per_p2wpkh_in = 68;   // one native-segwit input (incl. witness, weighted)
    int p2wsh_out     = 43;   // the HTLC output
    int p2wpkh_change = 31;   // an optional change output
};

// Compute the fee (sats) for `num_inputs` inputs, with/without a change output.
int64_t BtcFundingFee(const BtcVsizeModel& m, int num_inputs, bool with_change,
                      int64_t fee_rate_sat_vb);

// Result of a coin-selection.
struct BtcCoinSelection {
    bool                 ok = false;
    std::string          error;
    std::vector<BtcUtxo> selected;
    int64_t              total_in_sats = 0;
    int64_t              fee_sats = 0;
    int64_t              change_sats = 0;   // 0 if folded into fee (dust)
    bool                 has_change = false;
};

// Accumulative largest-first selection. Selects from `utxos` enough to cover
// `target_sats` (the HTLC amount) plus fee at `fee_rate_sat_vb`, recomputing
// the fee as inputs are added. A change output below kBtcP2wpkhDustSats is
// dropped and its value folded into the fee. Returns ok=false if the confirmed
// balance is insufficient or inputs/params are invalid.
BtcCoinSelection SelectBtcFundingUtxos(const std::vector<BtcUtxo>& utxos,
                                       int64_t target_sats,
                                       int64_t fee_rate_sat_vb,
                                       const BtcVsizeModel& model = {});

// Convenience for the current one-input signing API: pick the SINGLE best UTXO
// (smallest that still covers target+fee, to minimise change) or fail. Uses the
// same fee/dust math. Callers that need multi-input funding use the plural form
// above and a signing path that consumes N inputs (a signing-module extension).
BtcCoinSelection SelectSingleBtcFundingUtxo(const std::vector<BtcUtxo>& utxos,
                                            int64_t target_sats,
                                            int64_t fee_rate_sat_vb,
                                            const BtcVsizeModel& model = {});

// The plan produced by orchestrating selection + (gated) signing.
struct BtcFundingPlan {
    bool             ok = false;           // a valid plan was produced
    std::string      error;
    BtcCoinSelection selection;
    std::string      htlc_address;         // where the funding pays (P2WSH)
    int64_t          lock_amount_sats = 0;
    // Signed funding tx — populated ONLY when SOST_BTC_HTLC_SIGNING=ON and a
    // single-input selection succeeded. Empty (with signed=false) otherwise.
    bool             signed_tx = false;
    std::string      funding_raw_tx_hex;
    std::string      funding_note;         // human-readable status
};

// Orchestrate: select coins for `lock_amount_sats`, derive fee/change, and —
// if the signing backend is enabled AND a single UTXO suffices — build+sign the
// funding tx via SignBtcHtlcLockFunding. With signing disabled (Option A) the
// plan is returned with signed_tx=false and a note; the caller can still show
// the selection/fee. `funder_privkey` (32 bytes) and `funder_change_addr` are
// only used when signing is enabled; the key is never stored or logged.
BtcFundingPlan PlanBtcHtlcFunding(const std::vector<BtcUtxo>& utxos,
                                  int64_t lock_amount_sats,
                                  int64_t fee_rate_sat_vb,
                                  const std::vector<uint8_t>& redeem_script,
                                  const std::string& htlc_address,
                                  const std::array<uint8_t, 32>& funder_privkey,
                                  const std::string& funder_change_addr,
                                  const std::string& bitcoin_network,
                                  const BtcVsizeModel& model = {});

}  // namespace btc
}  // namespace atomic_swap
}  // namespace sost
