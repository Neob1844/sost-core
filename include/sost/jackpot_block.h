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

} // namespace sost::jackpot
