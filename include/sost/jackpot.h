#pragma once
// ============================================================================
// V15 — Historical DTD Jackpot (J): PURE consensus core.
// Spec: docs/design/V15_HISTORICAL_DTD_JACKPOT_SPEC.md (Model A, LOCKED).
//
// This header holds ONLY pure, deterministic, side-effect-free helpers:
//   - the per-block payout / rollover / cap arithmetic (hist_jackpot_apply)
//   - reserve-UTXO membership (is_reserve_output)
//   - deterministic reserve-UTXO ordering + oldest-first selection
//
// It does NOT touch the UTXO set, coinbase construction, block validation,
// ConnectBlock/DisconnectBlock or reorg — that wiring lands in a later
// increment on top of this tested core (exactly as apply_lottery_block is a
// pure function wired separately). Nothing here mints SOST: the jackpot is a
// spend of existing Gold Vault / PoPC reserve UTXOs (supply-neutral).
// ============================================================================
#include <cstdint>
#include <vector>
#include <cstddef>
#include "sost/params.h"        // HIST_JACKPOT_* + is_hist_jackpot_height
#include "sost/types.h"         // Bytes32
#include "sost/tx_signer.h"     // PubKeyHash
#include "sost/transaction.h"   // OUT_COINBASE_GOLD/POPC

namespace sost::jackpot {

// Result of the pure per-block jackpot computation.
struct JackpotResult {
    bool    is_jackpot_block{false}; // height is cadence-aligned jackpot height
    bool    paid{false};             // a payout occurred this block
    int64_t payout{0};               // stocks paid to the DTD winner
    int64_t reserve_after{0};        // reserve remaining after this block
    int64_t rollover_after{0};       // carried prize after this block
    bool    retired{false};          // reserve exhausted at/after this block
};

// Pure payout computation for one block. All inputs are chain-derived:
//   height          : block height
//   winner_exists   : true iff this block has an eligible DTD winner
//   reserve_before  : historical reserve remaining before this block (stocks)
//   rollover_before : carried prize before this block (stocks)
//
// Rules (spec §4), all overflow-safe int64 stocks:
//   prize_target = BASE + rollover_before   (rollover is clamped <= CAP-BASE,
//                                            so prize_target <= CAP always)
//   prize        = min(prize_target, CAP)
//   winner       -> payout = min(prize, reserve_before); carry only the
//                   above-cap excess; if reserve-limited, drain + retire.
//   no winner    -> pay nothing; base accrues to rollover (clamped); reserve
//                   untouched.
//   reserve == 0 -> jackpot retired (one-way latch); no payout ever again.
inline JackpotResult hist_jackpot_apply(int64_t height,
                                        bool    winner_exists,
                                        int64_t reserve_before,
                                        int64_t rollover_before) {
    JackpotResult r;
    r.reserve_after  = reserve_before;
    r.rollover_after = rollover_before;

    // Defensive: never operate on negative state.
    if (reserve_before < 0 || rollover_before < 0) return r;
    if (!is_hist_jackpot_height(height)) return r;   // not a jackpot block
    r.is_jackpot_block = true;

    if (reserve_before == 0) { r.retired = true; r.rollover_after = 0; return r; }

    const int64_t BASE = HIST_JACKPOT_BASE_STOCKS;
    const int64_t CAP  = HIST_JACKPOT_CAP_STOCKS;

    const int64_t prize_target = BASE + rollover_before;   // <= CAP by clamp
    const int64_t prize        = prize_target < CAP ? prize_target : CAP;

    if (!winner_exists) {
        // No eligible winner: nothing paid; base accrues to rollover, clamped
        // so the next prize_target can never exceed CAP.
        const int64_t roll_cap = CAP - BASE;               // >= 0 (static_assert)
        const int64_t roll     = rollover_before + BASE;
        r.rollover_after = roll < roll_cap ? roll : roll_cap;
        r.reserve_after  = reserve_before;                 // untouched
        return r;
    }

    // Winner exists: pay min(prize, reserve).
    const int64_t payout = prize < reserve_before ? prize : reserve_before;
    r.paid          = payout > 0;
    r.payout        = payout;
    r.reserve_after = reserve_before - payout;
    if (payout == prize) {
        r.rollover_after = prize_target - prize;           // above-cap excess (>=0)
    } else {
        r.rollover_after = 0;                              // reserve-limited: drained
    }
    if (r.reserve_after == 0) r.retired = true;
    return r;
}

// Reserve membership (spec §5b): an output belongs to the Historical Jackpot
// reserve iff it is a Gold Vault or PoPC Pool coinbase output locked to its
// constitutional address. Pure predicate over (type, pkh) — no heuristics.
inline bool is_reserve_output(uint8_t out_type,
                              const PubKeyHash& pkh,
                              const PubKeyHash& gold_pkh,
                              const PubKeyHash& popc_pkh) {
    return (out_type == OUT_COINBASE_GOLD && pkh == gold_pkh)
        || (out_type == OUT_COINBASE_POPC && pkh == popc_pkh);
}

// A reserve UTXO, reduced to the fields consensus needs for deterministic
// selection. `txid` is the funding tx id, `vout` its output index.
struct ReserveUtxo {
    int64_t  height{0};
    Bytes32  txid{};
    uint32_t vout{0};
    int64_t  amount{0};
};

// Deterministic total order: oldest-first by (height, txid, vout). Bytes32 is
// std::array<uint8_t,32>, whose operator< is lexicographic — stable across
// nodes. This is the ONLY ordering consensus uses; wallet coin selection must
// never influence it.
inline bool reserve_utxo_less(const ReserveUtxo& a, const ReserveUtxo& b) {
    if (a.height != b.height) return a.height < b.height;
    if (a.txid   != b.txid)   return a.txid   < b.txid;
    return a.vout < b.vout;
}

struct ReserveSelection {
    std::vector<size_t> indices;   // indices into the caller-sorted vector
    int64_t total{0};              // sum of selected amounts
    bool    sufficient{false};     // total >= needed
};

// Oldest-first selection covering `needed` stocks. `sorted` MUST already be
// ordered by reserve_utxo_less (caller sorts once). Selects the fewest oldest
// UTXOs whose sum first reaches `needed`. If the whole reserve is insufficient,
// returns everything with sufficient=false (caller pays min(prize,reserve)).
inline ReserveSelection select_reserve_utxos(const std::vector<ReserveUtxo>& sorted,
                                             int64_t needed) {
    ReserveSelection s;
    if (needed <= 0) { s.sufficient = true; return s; }
    for (size_t i = 0; i < sorted.size() && s.total < needed; ++i) {
        s.indices.push_back(i);
        s.total += sorted[i].amount;
    }
    s.sufficient = s.total >= needed;
    return s;
}

} // namespace sost::jackpot
