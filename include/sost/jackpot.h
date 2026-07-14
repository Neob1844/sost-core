// jackpot.h — V15 Historical DTD Jackpot (Gold Vault + PoPC wind-down).
// Spec: docs/V15_HISTORICAL_JACKPOT_SPEC.md  (Option A — progressive
// constitutional spend, supply-neutral).
//
// This header holds ONLY the pure, deterministic amount/cadence logic that both
// the miner and the validator must agree on. It has NO chain-state, NO UTXO, NO
// I/O — the constitutional spend of the real Gold/PoPC UTXOs (FIFO selection,
// change back to reserve, signature-bypass, UTXO apply/undo) lives separately in
// the block-connect path and is intentionally NOT in this header.
//
// The jackpot is hung off the DTD lottery cadence (NOT a second height%N timer):
// a jackpot OPPORTUNITY occurs on every HIST_JACKPOT_DTD_INTERVAL-th DTD LOTTERY
// block (height % 3 == 0) since V15 — ~every 288 blocks (APPROXIMATE, block times
// vary). An opportunity is INDEPENDENT of whether a winner exists:
//   - opportunity + eligible winner  -> pay (reuses the DTD winner already picked)
//   - opportunity + no eligible winner (empty set) OR reserve exhausted -> rollover
// Non-lottery blocks and pre-V15 blocks never trigger a jackpot opportunity.
#pragma once

#include "sost/params.h"        // HIST_JACKPOT_* constants
#include "sost/types.h"         // Bytes32
#include "sost/transaction.h"   // Transaction / TxInput / TxOutput, TX_TYPE_STANDARD, OUT_TRANSFER
#include "sost/tx_signer.h"     // PubKeyHash
#include "sost/tx_validation.h" // OutPoint, UTXOEntry
#include "sost/lottery.h"       // is_lottery_block (cadence)
#include <cstdint>
#include <vector>
#include <algorithm>
#include <map>

namespace sost::jackpot {

// Is this DTD lottery block a jackpot OPPORTUNITY (by index)?
//   lottery_opportunity_index_since_v15 = count of DTD LOTTERY blocks
//   (height % 3 == 0) strictly after V15_HEIGHT, including the current one
//   (1-based). Every INTERVAL-th is an opportunity. NOTE: an opportunity is
//   NOT the same as a payout — whether it actually pays depends on there being
//   an eligible winner (see compute_jackpot / spec §2).
inline bool is_jackpot_trigger(int64_t lottery_opportunity_index_since_v15) {
    return lottery_opportunity_index_since_v15 > 0
        && (lottery_opportunity_index_since_v15 % HIST_JACKPOT_DTD_INTERVAL) == 0;
}

// 1-based index of a lottery block within the jackpot cadence since V15.
// Returns 0 if `height` is pre-V15 or is NOT a DTD lottery block. Only lottery
// blocks can be jackpot opportunities; the 96th is the first (V15=20000 ->
// first lottery 20001 -> #96 = 20286). V15 is far past the DTD bootstrap window,
// so the steady 1-of-3 cadence holds (lottery blocks spaced by exactly 3).
inline int64_t jackpot_lottery_index(int64_t height, int64_t phase2_height, int64_t v15_height) {
    if (v15_height == INT64_MAX || height < v15_height) return 0;
    if (!sost::lottery::is_lottery_block(height, phase2_height)) return 0;
    int64_t first = v15_height;
    while (!sost::lottery::is_lottery_block(first, phase2_height)) ++first;   // <= 3 iterations
    if (height < first) return 0;
    return (height - first) / 3 + 1;
}

// Is this block a jackpot OPPORTUNITY? (a lottery block, every 96th since V15).
inline bool is_jackpot_opportunity(int64_t height, int64_t phase2_height, int64_t v15_height) {
    return is_jackpot_trigger(jackpot_lottery_index(height, phase2_height, v15_height));
}

struct JackpotResult {
    int64_t payout;         // stocks paid to the winner this jackpot (0 => rollover / wound down)
    int64_t pending_after;  // rollover carried to the next jackpot
};

// Deterministic jackpot amount. All inputs are non-negative stocks.
//
// Rules (spec §4):
//   target  = pending_before + base(100)
//   winner  -> payout = min(target, cap(500), reserve_remaining);
//              excess (target - payout) rolls into pending_after.
//   no win  -> payout = 0; pending grows by base but NEVER exceeds reserve.
//   reserve exhausted (<=0) -> payout 0, pending 0 (jackpot disabled forever).
//
// Hard invariants (checked by tests + asserted by consensus):
//   0 <= payout <= cap
//   payout <= reserve_remaining            (never pays more than exists)
//   payout + pending_after <= reserve_remaining  (never PROMISES more than exists)
inline JackpotResult compute_jackpot(int64_t pending_before,
                                     int64_t reserve_remaining,
                                     bool    has_eligible_winner) {
    if (reserve_remaining <= 0) return { 0, 0 };            // wound down — disabled forever
    if (pending_before < 0) pending_before = 0;

    // Overflow guard (consensus hygiene). `pending` is always maintained
    // <= reserve_remaining, and reserve_remaining <= total supply (<< INT64_MAX),
    // so `pending + base` cannot overflow. Clamp defensively in case a corrupted
    // or out-of-range `pending` is ever passed, so the sum below is always safe.
    if (pending_before > reserve_remaining) pending_before = reserve_remaining;

    const int64_t target = pending_before + HIST_JACKPOT_BASE_STOCKS;  // safe: both operands bounded

    if (!has_eligible_winner) {
        // Rollover: accumulate the base, but pending can never exceed the reserve.
        int64_t pend = target;
        if (pend > reserve_remaining) pend = reserve_remaining;
        return { 0, pend };
    }

    int64_t payout = target;
    if (payout > HIST_JACKPOT_CAP_STOCKS) payout = HIST_JACKPOT_CAP_STOCKS;  // per-payout cap
    if (payout > reserve_remaining)       payout = reserve_remaining;        // final partial payout

    int64_t pending_after = target - payout;                  // excess above cap rolls forward
    const int64_t rem_after = reserve_remaining - payout;
    if (pending_after > rem_after) pending_after = rem_after; // never promise more than remains
    if (pending_after < 0) pending_after = 0;
    return { payout, pending_after };
}

// ---------------------------------------------------------------------------
// Deterministic FIFO spend plan (the byte-exact root shared by miner + validator).
//
// The reserve (Gold Vault + PoPC UTXOs) is spent oldest-first. A reserve UTXO is
// projected into this view before planning; the FIFO key is a TOTAL order so
// every node on every architecture produces the identical plan for the same
// reserve set + payout.
// ---------------------------------------------------------------------------
struct ReserveUtxo {
    int64_t  height{0};   // creation height  — FIFO primary key
    Bytes32  txid{};      // FIFO tiebreak #1 (lexicographic on 32 bytes)
    uint32_t vout{0};     // FIFO tiebreak #2
    int64_t  amount{0};   // stocks
};

// Total FIFO order: oldest first (height ASC, then txid ASC, then vout ASC).
inline bool reserve_fifo_less(const ReserveUtxo& a, const ReserveUtxo& b) {
    if (a.height != b.height) return a.height < b.height;
    if (a.txid   != b.txid)   return a.txid   < b.txid;   // std::array<uint8_t,32> lexicographic
    return a.vout < b.vout;
}

struct JackpotSpendPlan {
    bool                     ok{false};        // false iff reserve total < payout (caller guards: payout<=reserve)
    std::vector<ReserveUtxo> inputs;           // FIFO-selected reserve UTXOs, IN FIFO ORDER
    int64_t                  input_sum{0};      // sum of selected inputs
    int64_t                  winner_amount{0};  // == payout
    int64_t                  change_amount{0};  // == input_sum - payout (0 => NO change output)
};

// Select FIFO-oldest reserve UTXOs summing to >= `payout`. `reserve` may be in any
// order (sorted internally). Deterministic: identical output for identical input on
// miner and validator. `payout` must already be <= sum(reserve) (compute_jackpot
// guarantees payout <= reserve_remaining); ok=false signals a caller bug otherwise.
inline JackpotSpendPlan plan_jackpot_spend(std::vector<ReserveUtxo> reserve, int64_t payout) {
    JackpotSpendPlan p;
    if (payout <= 0) { p.ok = true; return p; }              // nothing to spend
    std::sort(reserve.begin(), reserve.end(), reserve_fifo_less);
    int64_t sum = 0;
    for (const auto& u : reserve) {
        if (u.amount <= 0) continue;                          // ignore malformed/zero
        if (sum > INT64_MAX - u.amount) { p.ok = false; return p; }  // overflow guard (consensus hygiene)
        p.inputs.push_back(u);
        sum += u.amount;
        if (sum >= payout) break;
    }
    if (sum < payout) { p.ok = false; return p; }             // reserve below payout — must not happen
    p.ok            = true;
    p.input_sum     = sum;
    p.winner_amount = payout;
    p.change_amount = sum - payout;                            // 0 => change output omitted
    return p;
}

// ---------------------------------------------------------------------------
// Node adapter — enumerate the LIVE reserve UTXOs (Gold Vault + PoPC) from the
// UTXO set and project them into ReserveUtxo for the FIFO spend. This is the
// bridge from `UtxoSet::GetMap()` to the pure core. Deterministic: the caller
// passes the same map on miner and validator; plan_jackpot_spend then imposes
// the FIFO order. `creation_height` comes straight from UTXOEntry.height
// (verified present — utxo_set.cpp sets entry.height on connect).
// ---------------------------------------------------------------------------
inline std::vector<ReserveUtxo> collect_reserve_utxos(
    const std::map<OutPoint, UTXOEntry>& utxos,
    const PubKeyHash& gold_pkh,
    const PubKeyHash& popc_pkh)
{
    std::vector<ReserveUtxo> out;
    for (const auto& kv : utxos) {
        const UTXOEntry& e = kv.second;
        if (e.pubkey_hash != gold_pkh && e.pubkey_hash != popc_pkh) continue;  // reserve addresses only
        ReserveUtxo u;
        u.height = e.height;          // creation height (FIFO primary key)
        u.txid   = kv.first.txid;     // Hash256 == Bytes32
        u.vout   = kv.first.index;
        u.amount = e.amount;
        out.push_back(u);
    }
    return out;
}

// Live reserve balance = sum of all reserve UTXOs (the UTXO set IS the ledger;
// no consensus counter). Overflow-guarded (bounded by total supply << INT64_MAX).
inline int64_t reserve_sum(const std::vector<ReserveUtxo>& reserve) {
    int64_t s = 0;
    for (const auto& u : reserve)
        if (u.amount > 0 && s <= INT64_MAX - u.amount) s += u.amount;
    return s;
}

// ---------------------------------------------------------------------------
// Build the EXACT jackpot transaction from a spend plan. This is the single
// function BOTH the miner and the validator call; the validator then requires
// block.txs[1] to serialize byte-for-byte identically to this. There is no
// discretion, so no attack surface.
//
//   inputs   = plan.inputs (FIFO reserve UTXOs), each with NO signature
//              (constitutional spend — validity is byte-exactness, not a sig).
//   out[0]   = winner (payout, normal spendable OUT_TRANSFER).
//   out[1]   = change back to the reserve address (OUT_TRANSFER at reserve pkh),
//              omitted iff change == 0. It is re-locked by the V15 ADDRESS-based
//              consensus rule (TX_SPEC §6), so it can only be moved by a future
//              jackpot tx.
//
// Identified in a block by POSITION (txs[1]) + byte-exact match — NOT by a new
// tx_type. `tx_type` stays TX_TYPE_STANDARD; a standalone/mempool copy is
// rejected because it carries no signatures and spends reserve UTXOs (§6/§8b).
inline Transaction build_expected_jackpot_tx(const JackpotSpendPlan& plan,
                                             const PubKeyHash& winner_pkh,
                                             const PubKeyHash& reserve_change_pkh) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_STANDARD;
    tx.inputs.reserve(plan.inputs.size());
    for (const auto& u : plan.inputs) {
        TxInput in;
        in.prev_txid  = u.txid;      // Hash256 == Bytes32 (both array<uint8_t,32>)
        in.prev_index = u.vout;
        in.signature.fill(0);        // constitutional spend — NO signature
        in.pubkey.fill(0);
        tx.inputs.push_back(in);
    }
    TxOutput winner;
    winner.amount      = plan.winner_amount;
    winner.type        = OUT_TRANSFER;
    winner.pubkey_hash = winner_pkh;
    tx.outputs.push_back(winner);
    if (plan.change_amount > 0) {
        TxOutput change;
        change.amount      = plan.change_amount;
        change.type        = OUT_TRANSFER;        // normal type, but ADDRESS-locked by §6 (returns to reserve)
        change.pubkey_hash = reserve_change_pkh;  // = ADDR_GOLD_VAULT pkh
        tx.outputs.push_back(change);
    }
    return tx;
}

// ---------------------------------------------------------------------------
// Block-level jackpot validation (the consensus rule, pure + testable).
// Called from process_block() (the SINGLE common block-acceptance path:
// submitblock, P2P, reorg, chain-load). Given the block's txs, the height, the
// live UTXO set, the reserve addresses, and the DTD winner already selected,
// it: (a) enforces txs[1] == the exact jackpot tx when a payout is due, (b)
// enforces the reserve address-lock everywhere else, and (c) returns the
// jackpot_pending_after to persist. Pre-V15 is a no-op (byte-identical).
// ---------------------------------------------------------------------------
struct BlockJackpotResult {
    bool         ok{true};
    const char*  reject{nullptr};          // reason when !ok
    int64_t      jackpot_pending_after{0}; // value to store in StoredBlock
};

inline BlockJackpotResult validate_block_jackpot(
    const std::vector<Transaction>&        txs,
    int64_t height, int64_t phase2_height, int64_t v15_height,
    const std::map<OutPoint, UTXOEntry>&   utxos,
    const PubKeyHash& gold_pkh, const PubKeyHash& popc_pkh,
    bool has_winner, const PubKeyHash& winner_pkh,
    int64_t jackpot_pending_before)
{
    BlockJackpotResult r;
    r.jackpot_pending_after = jackpot_pending_before;              // default: carry forward
    if (v15_height == INT64_MAX || height < v15_height) return r;  // pre-V15: no-op

    auto spends_reserve = [&](const Transaction& tx) -> bool {
        for (const auto& in : tx.inputs) {
            OutPoint op; op.txid = in.prev_txid; op.index = in.prev_index;
            auto it = utxos.find(op);
            if (it != utxos.end() &&
                (it->second.pubkey_hash == gold_pkh || it->second.pubkey_hash == popc_pkh))
                return true;
        }
        return false;
    };

    if (is_jackpot_opportunity(height, phase2_height, v15_height)) {
        auto reserve = collect_reserve_utxos(utxos, gold_pkh, popc_pkh);
        const int64_t reserve_rem = reserve_sum(reserve);
        auto jr = compute_jackpot(jackpot_pending_before, reserve_rem, has_winner);
        r.jackpot_pending_after = jr.pending_after;

        if (has_winner && jr.payout > 0) {
            if (txs.size() < 2) { r.ok=false; r.reject="jackpot opportunity missing txs[1]"; return r; }
            auto plan = plan_jackpot_spend(reserve, jr.payout);
            if (!plan.ok) { r.ok=false; r.reject="jackpot FIFO plan failed (reserve<payout)"; return r; }
            Transaction expected = build_expected_jackpot_tx(plan, winner_pkh, gold_pkh);
            std::vector<Byte> eb, gb;
            if (!expected.Serialize(eb) || !txs[1].Serialize(gb) || eb != gb) {
                r.ok=false; r.reject="jackpot txs[1] not byte-exact"; return r;
            }
            for (size_t ti=2; ti<txs.size(); ++ti)
                if (spends_reserve(txs[ti])) { r.ok=false; r.reject="non-jackpot tx spends reserve"; return r; }
        } else {
            // opportunity but no winner / payout 0 -> no tx may spend reserve
            for (size_t ti=1; ti<txs.size(); ++ti)
                if (spends_reserve(txs[ti])) { r.ok=false; r.reject="reserve spend on no-payout jackpot block"; return r; }
        }
    } else {
        // not a jackpot opportunity -> no tx may spend reserve at all
        for (size_t ti=1; ti<txs.size(); ++ti)
            if (spends_reserve(txs[ti])) { r.ok=false; r.reject="reserve spend outside jackpot block"; return r; }
    }
    return r;
}

} // namespace sost::jackpot
