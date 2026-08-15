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
#include "sost/address.h"       // V15 reserve freeze — decode ADDR_GOLD_VAULT/ADDR_POPC_POOL

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

// Derive the rollover carried INTO the jackpot block at `height`, purely from
// chain history — NO persisted StoredBlock field. `paid_at(h)` must return true
// iff the prior jackpot block at height h paid out (i.e. its block contains a
// TX_TYPE_JACKPOT). Replays the §4 accrual: a paid event resets rollover to 0
// (prize<=cap by the clamp), a miss accrues BASE clamped at CAP-BASE. Cost is
// one lookup per prior jackpot height (every cadence block), reproducible on
// every node from stored blocks alone.
template <typename PaidAtFn>
inline int64_t derive_rollover_before(int64_t height, PaidAtFn paid_at) {
    if (!is_hist_jackpot_height(height)) return 0;
    const int64_t roll_cap = HIST_JACKPOT_CAP_STOCKS - HIST_JACKPOT_BASE_STOCKS;
    int64_t rollover = 0;
    for (int64_t h = HIST_JACKPOT_FIRST_HEIGHT; h < height; h += HIST_JACKPOT_CADENCE_BLOCKS) {
        if (paid_at(h)) {
            rollover = 0;                                  // payout -> reset
        } else {
            const int64_t nr = rollover + HIST_JACKPOT_BASE_STOCKS;
            rollover = nr < roll_cap ? nr : roll_cap;      // miss -> accrue, clamped
        }
    }
    return rollover;
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

// ============================================================================
// V15 — CONSTITUTIONAL RESERVE FREEZE (BLOCKER 2)
// ============================================================================
// Until V15 the Gold Vault / PoPC Pool UTXOs were protected by NOTHING but key
// custody: docs/CONSTITUTIONAL_ADDRESSES_AUDIT.md states plainly that "no
// consensus rule prevents spending FROM Gold Vault or PoPC Pool — anyone with
// the private key CAN spend". Because the Historical Jackpot reserve is not a
// stored counter but simply "whatever those addresses hold" (jackpot_reserve.h)
// and the jackpot RETIRES for good once the reserve hits 0 (hist_jackpot_apply),
// one ordinary signed sweep would empty ~60 378 SOST and kill the jackpot
// permanently. Key custody is not a protocol guarantee.
//
// From RESERVE_FREEZE_ACTIVATION_HEIGHT (= V15_HEIGHT) consensus makes the
// reserve spendable EXCLUSIVELY by the canonical protocol transaction:
//
//   if any input of a tx spends a UTXO satisfying is_reserve_output(),
//   then tx.tx_type MUST be TX_TYPE_JACKPOT
//   (and that tx must still pass the byte-exact canonical reconstruction in
//    validate_block_jackpot / validate_live_jackpot, which is unchanged).
//
// Anything else — including a cryptographically VALID signature by the holder
// of the constitutional private key — is rejected by consensus and is not
// relayed by policy. The jackpot's own change output re-enters the sink as an
// OUT_COINBASE_GOLD at the Gold Vault address (jackpot_reserve.h), so it is
// frozen by the same rule: intended, and required for the reserve to survive
// between payouts.
//
// Height-gated strictly: below V15_HEIGHT the predicate is false and nothing
// changes, so blocks 0..V15_HEIGHT-1 replay byte-identical.
//
// INTERACTION WITH GOLD VAULT GOVERNANCE (G1-G5). A governance spend is an
// ORDINARY signed spend, so the freeze supersedes it: from V15_HEIGHT the Gold
// Vault is not spendable by any signature-authorised path, governed or not.
//   * MAINNET  — no interaction whatsoever: GV_SLICE1_ACTIVATION_HEIGHT is
//                INT64_MAX (gold_vault_slice1.h), so G1-G5 is completely inert
//                and nothing that used to be possible becomes impossible.
//   * TESTNET  — G1-G5 activates at V15_HEIGHT, and from that height the freeze
//                takes precedence over it. That is the intended ordering: the
//                Historical Jackpot reserve is not a treasury. Any future
//                governed outflow must be expressed as its own canonical
//                protocol transaction type, never as a signed sweep.
inline constexpr int64_t RESERVE_FREEZE_ACTIVATION_HEIGHT = V15_HEIGHT;

inline constexpr bool reserve_freeze_active_at(int64_t height) {
    return height >= RESERVE_FREEZE_ACTIVATION_HEIGHT;
}

// Constitutional reserve addresses, decoded once. These are compile-time
// constants of the protocol (params.h ADDR_GOLD_VAULT / ADDR_POPC_POOL); the
// decode is done lazily into a function-local static so every consensus caller
// sees the identical bytes with no per-input cost and no global-init ordering
// hazard. A decode failure would mean params.h itself is corrupt, so the
// accessors fall back to an all-zero pkh, which matches no real output.
inline const PubKeyHash& reserve_gold_pkh() {
    static const PubKeyHash k = [] {
        PubKeyHash p{};
        if (!address_decode(ADDR_GOLD_VAULT, p)) p = PubKeyHash{};
        return p;
    }();
    return k;
}
inline const PubKeyHash& reserve_popc_pkh() {
    static const PubKeyHash k = [] {
        PubKeyHash p{};
        if (!address_decode(ADDR_POPC_POOL, p)) p = PubKeyHash{};
        return p;
    }();
    return k;
}

// Convenience for validators: does this UTXO belong to the frozen reserve?
inline bool is_constitutional_reserve_utxo(uint8_t out_type, const PubKeyHash& pkh) {
    return is_reserve_output(out_type, pkh, reserve_gold_pkh(), reserve_popc_pkh());
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

// ---------------------------------------------------------------------------
// A1 — canonical TX_TYPE_JACKPOT construction + exact-match validation.
// The jackpot payout is a keyless protocol transaction (spec §5c). Its safety
// rests entirely on: the validator RECONSTRUCTS the canonical tx from chain
// state and requires an EXACT match. There is no signature to forge and no
// discretion — wrong winner / amount / inputs / ordering / change all fail.
// ---------------------------------------------------------------------------

// Build the canonical TX_TYPE_JACKPOT for one jackpot block. Returns true and
// fills out_tx iff a payout tx is required (jackpot height, winner exists,
// reserve non-empty, payout > 0). `sorted_reserve` MUST be pre-sorted by
// reserve_utxo_less. Deterministic: identical chain state -> identical tx.
inline bool build_canonical_jackpot_tx(int64_t height,
                                       bool winner_exists,
                                       const PubKeyHash& winner_pkh,
                                       int64_t reserve_before,
                                       int64_t rollover_before,
                                       const std::vector<ReserveUtxo>& sorted_reserve,
                                       const PubKeyHash& reserve_change_pkh,
                                       Transaction& out_tx) {
    const JackpotResult r = hist_jackpot_apply(height, winner_exists,
                                               reserve_before, rollover_before);
    if (!r.is_jackpot_block || !r.paid || r.payout <= 0) return false;

    const ReserveSelection sel = select_reserve_utxos(sorted_reserve, r.payout);
    if (!sel.sufficient || sel.indices.empty()) return false;  // must be covered

    out_tx = Transaction{};
    out_tx.version = 1;
    out_tx.tx_type = TX_TYPE_JACKPOT;

    // Inputs: exactly the selected reserve UTXOs, in canonical order, keyless
    // (zero signature/pubkey — like coinbase).
    for (size_t k = 0; k < sel.indices.size(); ++k) {
        const ReserveUtxo& u = sorted_reserve[sel.indices[k]];
        TxInput in;
        in.prev_txid  = u.txid;      // Hash256 and Bytes32 are the same 32-byte array
        in.prev_index = u.vout;
        in.signature.fill(0);
        in.pubkey.fill(0);
        out_tx.inputs.push_back(in);
    }

    // Output 0: payout -> winner (ordinary spendable OUT_TRANSFER).
    TxOutput w;
    w.amount = r.payout;
    w.type = OUT_TRANSFER;
    w.pubkey_hash = winner_pkh;
    out_tx.outputs.push_back(w);

    // Output 1 (only when change > 0): remainder -> canonical reserve sink,
    // re-entering the reserve set as an OUT_COINBASE_GOLD output (spec §5b).
    const int64_t change = sel.total - r.payout;
    if (change > 0) {
        TxOutput c;
        c.amount = change;
        c.type = OUT_COINBASE_GOLD;
        c.pubkey_hash = reserve_change_pkh;
        out_tx.outputs.push_back(c);
    }
    return true;
}

// True iff `tx` is EXACTLY the canonical jackpot tx for this chain state. If no
// jackpot tx is expected (not a jackpot block / no winner / empty reserve), any
// tx is a mismatch. This is the whole A1 authorization model.
inline bool jackpot_tx_matches_canonical(const Transaction& tx,
                                         int64_t height,
                                         bool winner_exists,
                                         const PubKeyHash& winner_pkh,
                                         int64_t reserve_before,
                                         int64_t rollover_before,
                                         const std::vector<ReserveUtxo>& sorted_reserve,
                                         const PubKeyHash& reserve_change_pkh) {
    Transaction expected;
    if (!build_canonical_jackpot_tx(height, winner_exists, winner_pkh,
                                    reserve_before, rollover_before,
                                    sorted_reserve, reserve_change_pkh, expected)) {
        return false;
    }
    // V15 FINAL — pin tx.version too. The canonical jackpot is EXEMPT from
    // ValidateTransactionConsensus in the node's block path (it is keyless, and
    // R2 forbids its type in the standalone validator), so R1's version check
    // never runs on it. Without this comparison a miner could ship the same
    // jackpot event with any version value: every amount, input and output would
    // still be canonical, but the serialization — and therefore the jackpot
    // tx's txid and the block's merkle root — would not be uniquely determined
    // by chain state. "Byte-exact canonical reconstruction" must mean all four
    // serialized fields (version, tx_type, inputs, outputs), not three.
    // Only reachable at jackpot heights (>= HIST_JACKPOT_FIRST_HEIGHT), which
    // are all in the future, so historical replay is unaffected.
    if (tx.version != expected.version)             return false;
    if (tx.tx_type != expected.tx_type)             return false;
    if (tx.inputs.size()  != expected.inputs.size())  return false;
    if (tx.outputs.size() != expected.outputs.size()) return false;
    for (size_t i = 0; i < expected.inputs.size(); ++i) {
        const TxInput& a = tx.inputs[i];
        const TxInput& b = expected.inputs[i];
        if (a.prev_txid  != b.prev_txid)  return false;
        if (a.prev_index != b.prev_index) return false;
        for (auto x : a.signature) if (x != 0) return false;  // keyless
        for (auto x : a.pubkey)    if (x != 0) return false;
    }
    for (size_t i = 0; i < expected.outputs.size(); ++i) {
        const TxOutput& a = tx.outputs[i];
        const TxOutput& b = expected.outputs[i];
        if (a.amount != b.amount)           return false;
        if (a.type   != b.type)             return false;
        if (a.pubkey_hash != b.pubkey_hash) return false;
        if (!a.payload.empty())             return false;
    }
    return true;
}

} // namespace sost::jackpot
