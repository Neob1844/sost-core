#pragma once
// =============================================================================
// V17 (block #40,000) — reward accounting 80 / 15 / 5. PURE, header-only.
// Normative spec: docs/v40000/V17_ECONOMICS_NORMATIVE.md
//
// From V17_HEIGHT (params.h):
//   * BLOCK SUBSIDY split, canonical integer rule (miner absorbs the remainder):
//         dtd_subsidy   = subsidy * 15 / 100 (integer division, rounds down)
//         jackpot_j     = subsidy *  5 / 100 (integer division, rounds down)
//         miner_subsidy = subsidy - dtd_subsidy - jackpot_j
//     so miner_subsidy + dtd_subsidy + jackpot_j == subsidy EXACTLY.
//   * TRANSACTION FEES: 100 % to the block miner (never split):
//         miner_total = miner_subsidy + fees
//   * jackpot_j is NOT paid to anyone in the block that produces it. It is added
//     to the consensus accumulator J_BALANCE (no address, no UTXO, no key).
//   * Historical Jackpot payouts (cadence, base 100 SOST, rollover, cap 500 SOST,
//     Jackpot V2 winner) are UNCHANGED; only the FUNDING changes: the prize is
//     funded from the historical reserve H first and the remainder from J, in the
//     SAME jackpot block. The H part is the canonical TX_TYPE_JACKPOT (spends the
//     frozen reserve UTXOs, exactly as before); the J part is a coinbase output of
//     type OUT_COINBASE_JACKPOT paying the same winner (new value materialized from
//     J, which was withheld from emission earlier, so the total is supply-neutral).
//
// Below V17_HEIGHT none of this applies and every helper here is never consulted
// by the node: blocks < V17_HEIGHT validate exactly as before.
// =============================================================================
#include <cstdint>
#include <vector>
#include "sost/params.h"               // V17_HEIGHT, v17_active_at, HIST_JACKPOT_*
#include "sost/consensus_constants.h"  // SUPPLY_MAX_STOCKS
#include "sost/transaction.h"          // Transaction, OUT_COINBASE_JACKPOT

namespace sost::v17 {

inline constexpr int64_t SPLIT_DEN     = 100;
inline constexpr int64_t SPLIT_DTD_NUM = 15;   // Normal DTD share of the subsidy
inline constexpr int64_t SPLIT_J_NUM   = 5;    // Jackpot accumulator share of the subsidy
inline constexpr int64_t SPLIT_MINER_NUM = SPLIT_DEN - SPLIT_DTD_NUM - SPLIT_J_NUM;  // 80 (nominal)
static_assert(SPLIT_MINER_NUM == 80, "V17 split must be 80/15/5");

// -----------------------------------------------------------------------------
// 1. Subsidy split (canonical rounding rule).
// -----------------------------------------------------------------------------
struct SubsidySplit {
    bool    ok{false};          // false only for a negative subsidy (never produced by the schedule)
    int64_t subsidy{0};
    int64_t miner_subsidy{0};   // subsidy - dtd_subsidy - jackpot_j  (absorbs both remainders)
    int64_t dtd_subsidy{0};     // subsidy * 15 / 100 (integer division, rounds down)
    int64_t jackpot_j{0};       // subsidy *  5 / 100 (integer division, rounds down)
};

// Overflow-safe for every int64 subsidy >= 0 (the products are formed in __int128).
inline SubsidySplit subsidy_split(int64_t subsidy) {
    SubsidySplit s;
    s.subsidy = subsidy;
    if (subsidy < 0) return s;
    const __int128 sub = (__int128)subsidy;
    const int64_t dtd = (int64_t)((sub * SPLIT_DTD_NUM) / SPLIT_DEN);
    const int64_t j   = (int64_t)((sub * SPLIT_J_NUM)   / SPLIT_DEN);
    s.dtd_subsidy   = dtd;
    s.jackpot_j     = j;
    s.miner_subsidy = subsidy - dtd - j;   // >= 80% of subsidy, never negative
    s.ok = true;
    return s;
}

// Full V17 coinbase amounts for one block (fees 100 % to the miner).
struct CoinbaseAmounts {
    bool    ok{false};
    int64_t subsidy{0};
    int64_t fees{0};
    int64_t miner_subsidy{0};
    int64_t miner_total{0};     // miner_subsidy + fees  (coinbase output[0])
    int64_t dtd_subsidy{0};     // added to pending / paid with pending to the DTD winner
    int64_t jackpot_j{0};       // added to J_BALANCE
};

inline CoinbaseAmounts coinbase_amounts(int64_t subsidy, int64_t fees) {
    CoinbaseAmounts c;
    c.subsidy = subsidy;
    c.fees = fees;
    if (fees < 0 || fees > SUPPLY_MAX_STOCKS) return c;
    const SubsidySplit s = subsidy_split(subsidy);
    if (!s.ok) return c;
    const __int128 mt = (__int128)s.miner_subsidy + (__int128)fees;
    if (mt > (__int128)INT64_MAX) return c;
    c.miner_subsidy = s.miner_subsidy;
    c.miner_total   = (int64_t)mt;
    c.dtd_subsidy   = s.dtd_subsidy;
    c.jackpot_j     = s.jackpot_j;
    c.ok = true;
    return c;
}

// DTD output rule (V17). The DTD winner is paid dtd_subsidy + pending_before when the
// eligibility set is non-empty. If that amount is 0 (only possible for a subsidy of at
// most 6 stocks with nothing pending, i.e. at the very end of the emission schedule) no
// zero-value output is created: the block takes the UPDATE shape and pending stays 0.
inline bool dtd_paid_out(bool eligible_nonempty, int64_t dtd_subsidy, int64_t pending_before) {
    return eligible_nonempty && (dtd_subsidy + pending_before) > 0;
}

// -----------------------------------------------------------------------------
// 2. Jackpot funding from H (historical reserve) then J (V17 accumulator).
// -----------------------------------------------------------------------------
// All inputs are PRE-BLOCK chain state:
//   h_before        = sum of the frozen reserve UTXOs (discover_reserve_utxos)
//   j_before        = J_BALANCE after the parent block
//   rollover_before = derive_rollover_before(height, paid_at)  (0 .. CAP-BASE)
// Rule (unchanged prize mechanics):
//   prize = min(BASE + rollover_before, CAP)
//   no winner              -> nothing paid; rollover_after = min(rollover+BASE, CAP-BASE)
//   winner, H + J == 0     -> UNFUNDED: nothing paid, no tx/output; the event counts as
//                             unpaid, so rollover accrues exactly as for "no winner"
//   winner, H + J  > 0     -> payout = min(prize, H + J)
//                             h_part = min(payout, H); j_part = payout - h_part
//                             rollover_after = 0
//                             (payout < prize is UNDERFUNDED: everything available is
//                              paid, H first, then J — same as the pre-V17 reserve-limited
//                              rule, without the pre-V17 "retired" latch, since J refills)
// Impossible states (negative H/J, rollover outside [0, CAP-BASE], overflow) return
// ok=false and the block MUST be rejected.
struct JackpotFunding {
    bool    ok{false};
    bool    is_jackpot_block{false};
    bool    winner_exists{false};
    bool    paid{false};            // payout > 0 this block
    bool    unfunded{false};        // winner exists but H + J == 0
    bool    underfunded{false};     // 0 < payout < prize
    int64_t prize{0};               // min(BASE + rollover_before, CAP)
    int64_t payout{0};              // h_part + j_part
    int64_t h_part{0};              // paid by the canonical TX_TYPE_JACKPOT (reserve UTXOs)
    int64_t j_part{0};              // paid by the coinbase OUT_COINBASE_JACKPOT output
    int64_t h_after{0};
    int64_t j_after_payment{0};     // j_before - j_part (this block's J allocation NOT included)
    int64_t rollover_after{0};
};

inline JackpotFunding jackpot_funding(int64_t height, bool winner_exists,
                                      int64_t h_before, int64_t j_before,
                                      int64_t rollover_before) {
    JackpotFunding f;
    f.h_after = h_before;
    f.j_after_payment = j_before;
    f.rollover_after = rollover_before;
    const int64_t BASE = HIST_JACKPOT_BASE_STOCKS;
    const int64_t CAP  = HIST_JACKPOT_CAP_STOCKS;
    const int64_t ROLL_CAP = CAP - BASE;
    if (h_before < 0 || j_before < 0) return f;                      // impossible state
    if (h_before > SUPPLY_MAX_STOCKS || j_before > SUPPLY_MAX_STOCKS) return f;
    if (rollover_before < 0 || rollover_before > ROLL_CAP) return f;  // impossible state
    f.ok = true;
    if (!v17_active_at(height) || !is_hist_jackpot_height(height)) return f;  // no event
    f.is_jackpot_block = true;
    f.winner_exists = winner_exists;
    const int64_t prize_target = BASE + rollover_before;             // <= CAP
    f.prize = prize_target < CAP ? prize_target : CAP;
    const int64_t available = h_before + j_before;                   // <= 2*SUPPLY_MAX, no overflow
    if (!winner_exists || available == 0) {
        f.unfunded = winner_exists;                                   // winner but nothing to pay
        const int64_t roll = rollover_before + BASE;
        f.rollover_after = roll < ROLL_CAP ? roll : ROLL_CAP;
        return f;
    }
    f.payout = f.prize < available ? f.prize : available;
    f.h_part = f.payout < h_before ? f.payout : h_before;
    f.j_part = f.payout - f.h_part;
    f.paid = f.payout > 0;
    f.underfunded = f.payout < f.prize;
    f.h_after = h_before - f.h_part;
    f.j_after_payment = j_before - f.j_part;
    f.rollover_after = prize_target - f.prize;                        // 0 (prize_target <= CAP)
    if (f.underfunded) f.rollover_after = 0;
    return f;
}

// -----------------------------------------------------------------------------
// 3. J_BALANCE transition for one block.
// -----------------------------------------------------------------------------
//   height <  V17_HEIGHT : J must be 0 before and after, and nothing may be paid from J.
//   height >= V17_HEIGHT : j_after = j_before - j_paid + jackpot_j(subsidy),
//                          with 0 <= j_paid <= j_before (J is debited using the
//                          PRE-BLOCK balance; this block's own allocation is added after).
struct JTransition {
    bool    ok{false};
    int64_t j_before{0};
    int64_t j_alloc{0};
    int64_t j_paid{0};
    int64_t j_after{0};
};

inline JTransition j_transition(int64_t height, int64_t j_before, int64_t subsidy, int64_t j_paid) {
    JTransition t;
    t.j_before = j_before;
    t.j_paid = j_paid;
    if (j_before < 0 || j_paid < 0 || j_before > SUPPLY_MAX_STOCKS) return t;
    if (!v17_active_at(height)) {
        if (j_before != 0 || j_paid != 0) return t;
        t.ok = true;
        return t;
    }
    if (j_paid > j_before) return t;
    const SubsidySplit s = subsidy_split(subsidy);
    if (!s.ok) return t;
    t.j_alloc = s.jackpot_j;
    const __int128 a = (__int128)j_before - j_paid + s.jackpot_j;
    if (a < 0 || a > (__int128)SUPPLY_MAX_STOCKS) return t;
    t.j_after = (int64_t)a;
    t.ok = true;
    return t;
}

// -----------------------------------------------------------------------------
// 4. Coinbase helpers.
// -----------------------------------------------------------------------------
inline int count_jackpot_j_outputs(const Transaction& coinbase) {
    int n = 0;
    for (const auto& o : coinbase.outputs) if (o.type == OUT_COINBASE_JACKPOT) ++n;
    return n;
}
// Sum of the J-funded jackpot outputs in a coinbase (0 when there are none).
inline int64_t coinbase_jackpot_j_paid(const Transaction& coinbase) {
    int64_t s = 0;
    for (const auto& o : coinbase.outputs) if (o.type == OUT_COINBASE_JACKPOT) s += o.amount;
    return s;
}

// A jackpot EVENT at height h counts as PAID (resets the rollover) iff its block carries
// the canonical TX_TYPE_JACKPOT at index 1 (H part) OR, from V17, a coinbase
// OUT_COINBASE_JACKPOT output (J part). Below V17 no coinbase can carry that output type
// (the coinbase shape rules reject it), so this predicate is identical to the pre-V17
// "tx[1] is TX_TYPE_JACKPOT" predicate on every historical block.
inline bool jackpot_event_paid(int64_t height, bool tx1_is_jackpot, int64_t coinbase_j_outputs) {
    if (tx1_is_jackpot) return true;
    return v17_active_at(height) && coinbase_j_outputs > 0;
}

// -----------------------------------------------------------------------------
// 5. Supply accounting (documentation + test oracle).
// -----------------------------------------------------------------------------
// For every tip T (all heights, before and after V17):
//     sum(unspent outputs) + pending_lottery(T) + J_BALANCE(T)
//         == sum_{h <= T} subsidy(h)            (fees net to zero; jackpot H spends are
//                                                 value-conserving; J outputs re-emit
//                                                 exactly what J withheld)
// Per V17 block: sum(coinbase outputs) + (pending_after - pending_before)
//                + (J_after - J_before) == subsidy + fees.
inline bool v17_block_invariant(int64_t subsidy, int64_t fees, int64_t sum_coinbase_outputs,
                                int64_t pending_before, int64_t pending_after,
                                int64_t j_before, int64_t j_after) {
    const __int128 lhs = (__int128)sum_coinbase_outputs + ((__int128)pending_after - pending_before)
                       + ((__int128)j_after - j_before);
    return lhs == (__int128)subsidy + (__int128)fees;
}

} // namespace sost::v17
