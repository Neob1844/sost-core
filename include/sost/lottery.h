// lottery.h — V11 Phase 2 component D: Proof-of-Participation lottery
//
// Spec: docs/V11_SPEC.md §4 + §10.5 (jackpot rollover)
// Status (C5): is_lottery_block — pure frequency function. Real
//              implementation (header-only inline). All other entry
//              points still SKELETON / abort-on-call (eligibility,
//              winner picking, rollover state, reorg) until C6+.
// Activation: V11_PHASE2_HEIGHT (params.h) — currently INT64_MAX.
//
// Lottery frequency schedule (height-only, no chain state needed):
//   With H = V11_PHASE2_HEIGHT and W = LOTTERY_HIGH_FREQ_WINDOW = 5000,
//   For h in [H, H + W):   triggered  ⟺  (height % 3) != 0  (2-of-3 bootstrap)
//   For h >= H + W:        triggered  ⟺  (height % 3) == 0  (1-of-3 permanent)
//
// CRITICAL: the rule uses `height % 3`, NOT `(height - H) % 3`. The
// schedule is anchored to absolute block height so a hypothetical
// reorg across the activation boundary cannot shift the trigger
// pattern. See is_lottery_block below.
//
// Eligibility (C6+):
//   addrs with at least 1 block in [0, h-1]
//     minus any block-reward winner in
//       [h - LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW, h-1]   (= 5 default)
//     minus the miner of block h itself.
//
// RNG domain tag (C6+):
//   "SOST_LOTTERY_V11" — defined as LOTTERY_RNG_DOMAIN below; consumed
//   by the deterministic winner-picking helper. Treated as raw bytes,
//   no trailing NUL.
//
// Coinbase shape on a triggered block (C8):
//   50 % miner / 50 % lottery winner (vs normal 50 / 25 / 25).
//
// Jackpot rollover (§10.5): if the eligibility set is empty on a
// triggered block, the would-be 50 % lottery share accumulates into
// the chain-state variable `pending_lottery_amount`. The next
// triggered block with a non-empty eligibility set pays
// `share + pending`. Implementation lands in C7-C8.
#pragma once

#include "sost/types.h"
#include "sost/params.h"      // V11_PHASE2_HEIGHT, LOTTERY_HIGH_FREQ_WINDOW
#include "sost/tx_signer.h"   // PubKeyHash
#include <cstdint>
#include <optional>
#include <vector>

namespace sost::lottery {

// ---------------------------------------------------------------------------
// Domain-separation tag for the deterministic lottery RNG.
// Consumed by pick_winner (C6+) as:
//   sha256(LOTTERY_RNG_DOMAIN || prev_block_hash || height_le)
// Treated as raw bytes; the trailing NUL is NOT included. Length helper
// is exposed for callers that prefer std::string_view-style access.
// ---------------------------------------------------------------------------
inline constexpr char    LOTTERY_RNG_DOMAIN[]    = "SOST_LOTTERY_V11";
inline constexpr size_t  LOTTERY_RNG_DOMAIN_LEN  = sizeof(LOTTERY_RNG_DOMAIN) - 1;

// ---------------------------------------------------------------------------
// V11 Phase 2 — height-only lottery trigger rule (C5, real, pure).
//
// Implementation is `inline` so this stays a header-only function and
// does NOT require src/lottery.cpp to be linked into sost-core. The
// remaining lottery functions (eligibility_set, pick_winner, apply_block,
// etc.) keep their abort-on-call stubs in src/lottery.cpp until C6+
// and are NOT linked into the production library yet.
//
// Rules:
//   1) phase2_height == INT64_MAX        →  return false (sentinel: Phase 2 dormant)
//   2) height < phase2_height            →  return false (pre-Phase 2 block)
//   3) offset = height - phase2_height
//      if offset < LOTTERY_HIGH_FREQ_WINDOW:
//          return (height % 3) != 0     (2-of-3 bootstrap, first 5000 blocks)
//      else:
//          return (height % 3) == 0     (1-of-3 permanent, after bootstrap)
//
// Production guarantee: while V11_PHASE2_HEIGHT == INT64_MAX in
// params.h, this function returns false for every real chain height.
// Tests pass a finite phase2_height to exercise the active path.
//
// CONSENSUS-CRITICAL: the schedule MUST be height-anchored, NOT
// offset-anchored, so a reorg across V11_PHASE2_HEIGHT does not
// shift the lottery cadence. Both miner and validator MUST go through
// this single helper.
//
// Phase 2 — REAL implementation. This is the only lottery function
// that does NOT abort.
inline bool is_lottery_block(int64_t height, int64_t phase2_height) {
    if (phase2_height == INT64_MAX) return false;
    if (height < phase2_height)     return false;

    const int64_t offset = height - phase2_height;
    if (offset < LOTTERY_HIGH_FREQ_WINDOW) {
        // Bootstrap: 2 of every 3 blocks.
        return (height % 3) != 0;
    }
    // Steady state: 1 of every 3 blocks, permanently.
    return (height % 3) == 0;
}

// ---------------------------------------------------------------------------
// Trigger result for a given height. Older 3-arg API kept aborting in
// the skeleton for backward-compat with tests written under the
// previous draft. Prefer is_lottery_block above.
//
// PHASE 2 — NOT IMPLEMENTED (still abort-on-call; superseded by
// is_lottery_block above).
bool is_triggered(int64_t height,
                  int64_t v11_phase2_height,
                  int64_t high_freq_window);

// ---------------------------------------------------------------------------
// V11 Phase 2 — eligibility set + deterministic winner selection (C6, real).
// ---------------------------------------------------------------------------
//
// Lightweight view of a mined block carrying ONLY the fields the
// lottery cares about. Deliberately decoupled from sost::StoredBlock
// (which lives in src/sost-node.cpp and carries many fields irrelevant
// to lottery) so this header has zero dependency on the node-runtime
// types. Callers (validator, miner, tests) project StoredBlock or
// any other in-memory representation into this view before calling
// the lottery API.
struct LotteryMinedBlockView {
    int64_t    height{0};
    PubKeyHash miner_pkh{};
    Bytes32    block_hash{};
};

// One entry in the lottery eligibility set.
//   pkh                  — the candidate winner address (sorted by raw
//                          lex order across the result vector).
//   first_mined_height   — earliest block height where this pkh won
//                          the block reward.
//   last_mined_height    — most recent block height where this pkh won.
//   blocks_mined         — total count of block-reward wins by this
//                          pkh in the chain history. Carried for
//                          analytics ONLY; lottery selection is
//                          uniform per pkh, NOT weighted by this
//                          count (see select_lottery_winner_index).
struct LotteryEligibilityEntry {
    PubKeyHash pkh{};
    int64_t    first_mined_height{0};
    int64_t    last_mined_height{0};
    int64_t    blocks_mined{0};
};

// Result type — provided for future C7/C8 callers that want to carry
// metadata alongside the entries. compute_lottery_eligibility_set
// itself returns just the entries vector.
struct LotteryEligibilityResult {
    std::vector<LotteryEligibilityEntry> eligible;
    int64_t                              height{0};
    int64_t                              exclusion_window{0};
};

// Compute the eligibility set for the lottery at `height`.
//
// Inputs:
//   blocks               — full chain history of mined-block views, all
//                          with `height < height_of_interest`. Order
//                          NOT required (we re-derive). Duplicates
//                          (same pkh winning multiple blocks) collapse
//                          to one entry whose `blocks_mined` counts
//                          all wins.
//   height               — the block whose lottery we're computing.
//                          (NOT yet in `blocks`.)
//   current_miner_pkh    — the pkh of the miner who won block `height`
//                          itself; ALWAYS excluded from this lottery.
//   exclusion_window     — how many recent blocks count for the
//                          recent-winner exclusion. Defaults to
//                          LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW
//                          (= 5 in the C5 default).
//
// Eligibility rule:
//   1. Address has won >= 1 block before `height`.
//   2. Address is NOT current_miner_pkh.
//   3. Address has NOT won a block in
//        [height - exclusion_window, height - 1].
//      (When exclusion_window == 0, only rule 2 applies on top of 1.)
//
// Output:
//   Vector of entries sorted lex by raw pkh bytes (stable across
//   x86 / ARM and across runs for the same input).
//
// Empty vector means no winner this block (rollover semantics live
// at the caller — C7).
std::vector<LotteryEligibilityEntry> compute_lottery_eligibility_set(
    const std::vector<LotteryMinedBlockView>& blocks,
    int64_t                                   height,
    const PubKeyHash&                         current_miner_pkh,
    int64_t                                   exclusion_window =
        LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW);

// Select the winning index into a lex-sorted eligibility vector.
//
// Determinism contract:
//   seed   = sha256(LOTTERY_RNG_DOMAIN || prev_block_hash || height_le)
//   roll   = read_u64_le(seed.data())
//   index  = roll % eligible.size()
//
// height is encoded as 8 bytes little-endian via append_u64_le; the
// SHA-256 implementation is the same `sha256()` used everywhere else
// in the repo (single-pass, NOT SHA-256d). Same inputs => bit-identical
// output on x86 and ARM.
//
// Returns -1 iff `eligible` is empty (rollover branch handled by
// caller). Otherwise returns an index in [0, eligible.size()).
int64_t select_lottery_winner_index(
    const std::vector<LotteryEligibilityEntry>& eligible,
    const Bytes32&                              prev_block_hash,
    int64_t                                     height);

// Helper: did `pkh` win a block-reward in any of
//   [height - exclusion_window, height - 1]
// for the given chain view? Used internally by
// compute_lottery_eligibility_set and exposed for test assertions.
//
// Returns false if exclusion_window == 0 (only the current-miner
// exclusion applies in that mode).
bool is_recent_reward_winner(
    const std::vector<LotteryMinedBlockView>& blocks,
    const PubKeyHash&                         pkh,
    int64_t                                   height,
    int64_t                                   exclusion_window);

// ---------------------------------------------------------------------------
// Pre-C6 placeholder pick_winner kept aborting for any caller that
// references it. New code should use select_lottery_winner_index above.
// PHASE 2 — NOT IMPLEMENTED (superseded).
std::optional<PubKeyHash> pick_winner(const Bytes32& prev_block_hash,
                                   int64_t height,
                                   const std::vector<PubKeyHash>& eligibility_sorted);

// ---------------------------------------------------------------------------
// V11 Phase 2 — rollover state machinery (C7, real, pure).
// ---------------------------------------------------------------------------
//
// These structs and functions implement the per-block transition for
// the jackpot rollover variable `pending_lottery_amount`. They are
// pure: no chain state, no I/O, no persistence — the inputs are passed
// in by value and the result carries every field a caller needs to
// (a) apply the transition, (b) undo it on reorg, and (c) recompute
// it deterministically.
//
// Invariant (mirrors include/sost/lottery.h top-of-file comment and
// docs/V11_SPEC.md §10.6):
//
//   IDLE     on !is_lottery_block(h):
//              pending_after = pending_before. NO payout. NO mutation.
//              NEVER pays out the jackpot, even if pending_before > 0.
//
//   UPDATE   on is_lottery_block(h) && eligible.empty():
//              pending_after = pending_before + lottery_amount.
//              NO payout this block. Caller emits 0 to vault and popc
//              outputs in the coinbase (C8).
//
//   PAYOUT   on is_lottery_block(h) && !eligible.empty():
//              winner_index = select_lottery_winner_index(...).
//              lottery_payout = pending_before + lottery_amount.
//              pending_after = 0.
//              Caller writes the payout into the lottery coinbase
//              output (C8).
//
// Persistent integration with chain state (StoredBlock fields,
// BlockUndo extension, chain.json serialization with backward-compat
// defaults) is intentionally deferred to C8, where it lands together
// with the coinbase shape change. The C7 pure functions are usable
// from any in-memory caller (tests, future C8 wiring, future
// validator).

struct LotteryApplyInput {
    int64_t                                     height;
    int64_t                                     phase2_height;
    int64_t                                     pending_before;
    int64_t                                     lottery_amount;
    PubKeyHash                                  current_miner_pkh;
    Bytes32                                     prev_block_hash;
    std::vector<LotteryEligibilityEntry>        eligible;
};

struct LotteryApplyResult {
    bool        triggered{false};        // is_lottery_block(h) result
    bool        paid_out{false};         // true iff a winner was chosen
    bool        ok{true};                // false on input validation failure
    int64_t     pending_before{0};       // copied from input for undo
    int64_t     pending_after{0};        // post-block pending value
    int64_t     lottery_amount{0};       // copied from input
    int64_t     lottery_payout{0};       // 0 on IDLE/UPDATE; pending+amount on PAYOUT
    int64_t     winner_index{-1};        // -1 on IDLE/UPDATE; valid on PAYOUT
    PubKeyHash  winner_pkh{};            // zero pkh on IDLE/UPDATE
    std::string error;                   // populated when !ok
};

// Apply the rollover state transition for one block.
//
// Validation:
//   - in.pending_before  >= 0
//   - in.lottery_amount  >= 0
//   - pending_before + lottery_amount must not overflow int64_t
//
// On any of the above failing, the result has ok=false and `error`
// describes the violation. State fields (pending_before, lottery_amount,
// winner_pkh) are copied from the input where applicable so the caller
// can log them for diagnostics.
LotteryApplyResult apply_lottery_block(const LotteryApplyInput& in);

// Undo helper for reorg paths.
//
// Returns the pre-block pending value, derived purely from the saved
// LotteryApplyResult. The caller restores chain state by writing this
// value back to its `pending_lottery_amount` storage. Symmetric with
// apply_lottery_block: apply(...).pending_before == undo_lottery_block(...).
//
// Pure — does NOT touch chain state itself; does NOT recompute from
// history.
int64_t undo_lottery_block(const LotteryApplyResult& applied);

// Jackpot rollover state. Lives in chain state (initialised to 0 at
// V11_PHASE2_HEIGHT, advanced block-by-block, restored from undo data
// on reorg). Cap: none.
struct RolloverState {
    uint64_t pending_lottery_amount = 0;  // stocks
};

// Per-block transition. `triggered` and `eligibility_empty` are inputs;
// `lottery_share` is the 50% subsidy amount the lottery would pay this
// block. Mutates `state` in place and writes the pre-block value into
// `out_pending_before` so the caller can save it as undo data.
//
// PHASE 2 — NOT IMPLEMENTED.
struct TransitionInputs {
    bool     triggered;
    bool     eligibility_empty;
    uint64_t lottery_share;
};

struct TransitionOutputs {
    uint64_t pending_before_block;       // for undo data
    uint64_t winner_payout;              // 0 if no winner this block
    bool     emit_winner_output;         // false on rollover blocks
};

void apply_block(RolloverState& state,
                 const TransitionInputs& in,
                 TransitionOutputs& out);

// Reorg helper — restore pending using the saved undo value.
// PHASE 2 — NOT IMPLEMENTED.
void undo_block(RolloverState& state, uint64_t pending_before_block);

} // namespace sost::lottery
