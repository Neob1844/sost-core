#pragma once
// =============================================================================
// V15 (J) live wiring — block-level Historical Jackpot rule ("validate BEFORE
// mutating chainstate"). PURE and header-only.
//
// This is the SOLE authorization for the keyless TX_TYPE_JACKPOT protocol spend.
// The signature exemption is NOT "type == JACKPOT -> skip signature". It is:
// a TX_TYPE_JACKPOT is accepted ONLY when, at this exact height and position,
// it is byte-for-field identical to the transaction the validator itself
// reconstructs from the PRE-BLOCK chainstate (reserve set + DTD winner +
// rollover). No other TX_TYPE_JACKPOT can ever be valid for a given pre-block
// state — so no attacker can craft an unsigned reserve spend.
//
// Rule enforced:
//   - non-jackpot event  -> EXACTLY ZERO TX_TYPE_JACKPOT in the block.
//   - jackpot event       -> EXACTLY ONE TX_TYPE_JACKPOT, at index 1 (right
//     after the coinbase, A1 §5c), byte-exact to the canonical reconstruction.
// The caller runs this BEFORE UtxoSet::ConnectBlock; on failure the block is
// rejected and chainstate is never mutated.
// =============================================================================
#include <vector>
#include <string>
#include "sost/jackpot.h"        // canonical build + exact-match, ReserveUtxo
#include "sost/transaction.h"    // Transaction, TX_TYPE_JACKPOT
#include "sost/v17_economics.h"  // V17 H-then-J jackpot funding

namespace sost::jackpot {

struct BlockJackpotResult {
    bool        ok{true};
    std::string reason;
    bool        jackpot_required{false};  // a canonical jackpot tx is required this block
};

// Number of TX_TYPE_JACKPOT transactions anywhere in the block.
inline int count_jackpot_txs(const std::vector<Transaction>& txs) {
    int n = 0;
    for (const auto& t : txs) if (t.tx_type == TX_TYPE_JACKPOT) ++n;
    return n;
}

// Decide whether `txs` satisfies the Historical Jackpot block rule for the given
// pre-block chainstate. `sorted_reserve` MUST be discover_reserve_utxos() output
// (pre-block); `reserve_before` its balance; winner_* the DTD winner of THIS
// block; rollover_before the carried prize; reserve_change_pkh the canonical
// reserve sink (ADDR_GOLD_VAULT). Deterministic — identical inputs on every node.
inline BlockJackpotResult validate_block_jackpot(const std::vector<Transaction>& txs,
                                                 int64_t height,
                                                 const std::vector<ReserveUtxo>& sorted_reserve,
                                                 bool winner_exists,
                                                 const PubKeyHash& winner_pkh,
                                                 int64_t reserve_before,
                                                 int64_t rollover_before,
                                                 const PubKeyHash& reserve_change_pkh) {
    BlockJackpotResult r;
    const int n = count_jackpot_txs(txs);

    // Reconstruct the canonical expectation from the pre-block state.
    Transaction expected;
    r.jackpot_required = build_canonical_jackpot_tx(height, winner_exists, winner_pkh,
                                                    reserve_before, rollover_before,
                                                    sorted_reserve, reserve_change_pkh, expected);

    if (!r.jackpot_required) {
        // No jackpot tx expected (non-jackpot height, no eligible winner, or empty
        // reserve). A rollover may still accrue in chain state, but NO tx is emitted.
        if (n != 0) {
            r.ok = false;
            r.reason = "TX_TYPE_JACKPOT present but none is authorized for this block";
        }
        return r;
    }

    // A canonical jackpot IS required: exactly one, at index 1, byte-exact.
    if (n != 1) {
        r.ok = false;
        r.reason = "expected exactly one TX_TYPE_JACKPOT, got " + std::to_string(n);
        return r;
    }
    if (txs.size() < 2 || txs[1].tx_type != TX_TYPE_JACKPOT) {
        r.ok = false;
        r.reason = "TX_TYPE_JACKPOT must be at index 1 (immediately after the coinbase)";
        return r;
    }
    if (!jackpot_tx_matches_canonical(txs[1], height, winner_exists, winner_pkh,
                                      reserve_before, rollover_before,
                                      sorted_reserve, reserve_change_pkh)) {
        r.ok = false;
        r.reason = "TX_TYPE_JACKPOT does not match the canonical consensus reconstruction";
        return r;
    }
    return r;  // ok
}

// =============================================================================
// V17 (height >= V17_HEIGHT) — block-level jackpot rule with H-then-J funding.
// `f` is sost::v17::jackpot_funding(height, winner_exists, H_before, J_before,
// rollover_before) computed from PRE-BLOCK state; `winner_pkh` the Jackpot V2
// winner. Enforced, in addition to the coinbase shape rules:
//   * f.h_part > 0  -> EXACTLY ONE TX_TYPE_JACKPOT, at index 1, byte-exact to
//                      build_jackpot_tx_for_payout(f.h_part, winner, reserve, sink)
//     f.h_part == 0 -> ZERO TX_TYPE_JACKPOT in the block
//   * f.j_part > 0  -> EXACTLY ONE coinbase output of type OUT_COINBASE_JACKPOT,
//                      amount == f.j_part, pkh == winner, empty payload
//     f.j_part == 0 -> ZERO OUT_COINBASE_JACKPOT outputs in the coinbase
//   * no TX other than the coinbase may carry an OUT_COINBASE_JACKPOT output
//     (R11 already rejects it in standard txs; checked here for every tx type)
// Non-jackpot V17 heights get f with h_part == j_part == 0, so the same rule
// requires zero jackpot txs and zero J outputs.
// =============================================================================
inline BlockJackpotResult validate_block_jackpot_v17(const std::vector<Transaction>& txs,
                                                     const sost::v17::JackpotFunding& f,
                                                     const PubKeyHash& winner_pkh,
                                                     const std::vector<ReserveUtxo>& sorted_reserve,
                                                     const PubKeyHash& reserve_change_pkh) {
    BlockJackpotResult r;
    if (!f.ok) { r.ok = false; r.reason = "V17 jackpot funding: impossible pre-block state"; return r; }
    if (txs.empty()) { r.ok = false; r.reason = "empty block"; return r; }
    for (size_t i = 1; i < txs.size(); ++i) {
        for (const auto& o : txs[i].outputs) {
            if (o.type == OUT_COINBASE_JACKPOT) {
                r.ok = false; r.reason = "OUT_COINBASE_JACKPOT outside the coinbase"; return r;
            }
        }
    }
    // ---- H part: canonical TX_TYPE_JACKPOT ----
    const int n = count_jackpot_txs(txs);
    r.jackpot_required = f.h_part > 0;
    if (!r.jackpot_required) {
        if (n != 0) {
            r.ok = false;
            r.reason = "TX_TYPE_JACKPOT present but none is authorized for this block (V17 H part = 0)";
            return r;
        }
    } else {
        if (n != 1) {
            r.ok = false; r.reason = "expected exactly one TX_TYPE_JACKPOT, got " + std::to_string(n); return r;
        }
        if (txs.size() < 2 || txs[1].tx_type != TX_TYPE_JACKPOT) {
            r.ok = false; r.reason = "TX_TYPE_JACKPOT must be at index 1 (immediately after the coinbase)"; return r;
        }
        Transaction expected;
        if (!build_jackpot_tx_for_payout(f.h_part, winner_pkh, sorted_reserve, reserve_change_pkh, expected)) {
            r.ok = false; r.reason = "V17 H part cannot be built from the reserve (impossible state)"; return r;
        }
        if (!jackpot_tx_equals_expected(txs[1], expected)) {
            r.ok = false; r.reason = "TX_TYPE_JACKPOT does not match the canonical V17 H-part reconstruction"; return r;
        }
    }
    // ---- J part: coinbase OUT_COINBASE_JACKPOT ----
    const Transaction& cb = txs[0];
    const int nj = sost::v17::count_jackpot_j_outputs(cb);
    if (f.j_part <= 0) {
        if (nj != 0) { r.ok = false; r.reason = "OUT_COINBASE_JACKPOT present but the V17 J part is 0"; return r; }
    } else {
        if (nj != 1) {
            r.ok = false; r.reason = "expected exactly one OUT_COINBASE_JACKPOT, got " + std::to_string(nj); return r;
        }
        for (const auto& o : cb.outputs) {
            if (o.type != OUT_COINBASE_JACKPOT) continue;
            if (o.amount != f.j_part) {
                r.ok = false; r.reason = "OUT_COINBASE_JACKPOT amount " + std::to_string(o.amount) +
                                         " != V17 J part " + std::to_string(f.j_part); return r;
            }
            if (o.pubkey_hash != winner_pkh) {
                r.ok = false; r.reason = "OUT_COINBASE_JACKPOT does not pay the jackpot winner"; return r;
            }
            if (!o.payload.empty()) {
                r.ok = false; r.reason = "OUT_COINBASE_JACKPOT payload must be empty"; return r;
            }
        }
    }
    return r;
}

} // namespace sost::jackpot
