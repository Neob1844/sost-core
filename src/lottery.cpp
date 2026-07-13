// lottery.cpp — V11 Phase 2 component D: Proof-of-Participation lottery
//
// Spec: docs/V11_SPEC.md §4 + §10.5 + docs/V11_PHASE2_DESIGN.md §5.
// Status (C6):
//   IMPLEMENTED:
//     - compute_lottery_eligibility_set
//     - select_lottery_winner_index
//     - is_recent_reward_winner
//     - is_lottery_block (header-only inline; defined in lottery.h)
//   STILL SKELETON (abort-on-call until C7 / C8):
//     - is_triggered (3-arg legacy API; superseded by is_lottery_block)
//     - pick_winner (legacy API; superseded by select_lottery_winner_index)
//     - apply_block / undo_block (rollover state — C7)
//
// CONSENSUS-CRITICAL: the C6 helpers are pure functions over a chain
// view. They do NOT touch coinbase, rewards, UTXO, chain state, or
// validation paths. Phase 2 activates at V11_PHASE2_HEIGHT = 7100
// (params.h, set by C13); pre-activation chain heights take the dormant
// branch because is_lottery_block returns false for every height < 7100.
#include "sost/lottery.h"

#include "sost/crypto.h"      // sha256()
#include "sost/serialize.h"   // append, append_u64_le, read_u64_le

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <string>

/*
 * Lottery module — Phase 2 (skeleton)
 *
 * IMPORTANT: read the lifecycle invariant in include/sost/lottery.h
 * BEFORE implementing any of the functions below. The invariant
 * describes when pending_lottery_amount is updated, paid out, or
 * left idle — violating it changes consensus rules.
 *
 * Phase 2 is NOT yet active in consensus. V11_PHASE2_HEIGHT remains
 * INT32_MAX (or equivalent sentinel) until Phase 2 ships.
 */

namespace sost::lottery {

// ============================================================================
// C6 — eligibility set + deterministic winner selection (real)
// ============================================================================

bool is_recent_reward_winner(
    const std::vector<LotteryMinedBlockView>& blocks,
    const PubKeyHash&                         pkh,
    int64_t                                   height,
    int64_t                                   exclusion_window)
{
    if (exclusion_window <= 0) return false;

    // Window: [height - exclusion_window, height - 1] inclusive on both ends.
    const int64_t window_lo = height - exclusion_window;
    const int64_t window_hi = height - 1;

    for (const auto& b : blocks) {
        if (b.height < window_lo || b.height > window_hi) continue;
        if (b.miner_pkh == pkh) return true;
    }
    return false;
}

std::vector<LotteryEligibilityEntry> compute_lottery_eligibility_set(
    const std::vector<LotteryMinedBlockView>& blocks,
    int64_t                                   height,
    const PubKeyHash&                         current_miner_pkh,
    int64_t                                   exclusion_window,
    int64_t                                   recent_miner_window)
{
    // -----------------------------------------------------------------------
    // C7.1 rule (revised from C6): the current block's winner is NO LONGER
    // auto-excluded from their own block's lottery. The only exclusion is
    // the recent-winner cooldown applied over the PREVIOUS `exclusion_window`
    // blocks (heights [height - exclusion_window, height - 1]).
    //
    // V13 extension (from height >= DTD_DOMINANCE_GATE_HEIGHT, params.h):
    // additionally exclude any pkh whose share of the previous
    // DTD_DOMINANCE_WINDOW blocks (default 288) is >= 10 %. The
    // dominance gate is INDEPENDENT of the recent-winner cooldown — a
    // pkh excluded by either filter is not in the eligibility set.
    //
    // V14 extension (from height >= DTD_POPC_ELIGIBILITY_HEIGHT, params.h):
    // additionally require has_active_canonical_popc(pkh, height) to
    // return true. The gate is wired but consensus-deferred: see
    // DTD_POPC_GATE_CONSENSUS_ACTIVE in params.h and the helper docs
    // in include/sost/lottery.h. While the flag is false (current build)
    // the helper returns true unconditionally and the gate is a no-op.
    //
    // The `current_miner_pkh` parameter is retained for source-level
    // compatibility with C6/C7 callers and tests; it is no longer
    // consumed by this function. A future API revision may drop it.
    // -----------------------------------------------------------------------
    (void)current_miner_pkh;

    // Step 1: aggregate per-pkh stats over the chain view. Only blocks
    // strictly before `height` count.
    //
    // std::map keyed by PubKeyHash gives a deterministic lex-sorted
    // iteration as a side-effect of std::array<uint8_t, 20>'s
    // operator<. We could equivalently aggregate into unordered_map
    // and sort at the end; the std::map path is simpler and the
    // benchmark is well below the C9 50 ms target on the test sizes.
    //
    // V13: in the same pass also accumulate per-pkh counts of blocks
    // that fall inside the dominance window [height - DTD_DOMINANCE_WINDOW,
    // height - 1], and count the total distinct heights observed in
    // that window. Two separate maps keep the dominance bookkeeping
    // cleanly separated from the genesis-to-now aggregation.
    std::map<PubKeyHash, LotteryEligibilityEntry> agg;
    std::map<PubKeyHash, int32_t> dominance_count;
    int32_t observed_window_blocks = 0;

    const int64_t dom_window_lo = height - DTD_DOMINANCE_WINDOW;
    const int64_t dom_window_hi = height - 1;

    for (const auto& b : blocks) {
        if (b.height >= height) continue;  // future / current — ignore
        auto& e = agg[b.miner_pkh];
        if (e.blocks_mined == 0) {
            // First time we see this pkh.
            e.pkh                = b.miner_pkh;
            e.first_mined_height = b.height;
            e.last_mined_height  = b.height;
        } else {
            if (b.height < e.first_mined_height) e.first_mined_height = b.height;
            if (b.height > e.last_mined_height)  e.last_mined_height  = b.height;
        }
        ++e.blocks_mined;

        // V13 dominance bookkeeping. We only need to do this when the
        // gate is at-or-past activation; the conditional is constant-
        // foldable per call and keeps pre-V13 cost flat. The block
        // counter is incremented once per block in the window
        // regardless of pkh (heights are unique in the chain view).
        if (height >= DTD_DOMINANCE_GATE_HEIGHT &&
            b.height >= dom_window_lo && b.height <= dom_window_hi) {
            ++dominance_count[b.miner_pkh];
            ++observed_window_blocks;
        }
    }

    // Step 2: build the recent-winner exclusion set in O(window) by
    // walking the same view once more and pulling out blocks whose
    // height falls into [height - exclusion_window, height - 1].
    // The current block (height == input.height) is NOT in this window.
    std::map<PubKeyHash, char> recent_winners;
    if (exclusion_window > 0) {
        const int64_t window_lo = height - exclusion_window;
        const int64_t window_hi = height - 1;
        for (const auto& b : blocks) {
            if (b.height < window_lo || b.height > window_hi) continue;
            recent_winners[b.miner_pkh] = 1;
        }
    }

    // Step 3: filter and project. std::map iteration is in lex order
    // of the key, which is exactly the sort order we want.
    //
    // Filters applied in order (any one excludes the pkh):
    //   (a) recent-winner cooldown (always, when exclusion_window > 0)
    //   (a2) V13.5 SbPoW-activity gate (height >= DTD_DOMINANCE_GATE_HEIGHT):
    //        the pkh's most recent block must be at height >= V11_PHASE2_HEIGHT
    //        (= 7100), i.e. it has at least one SbPoW-signed block (a real
    //        signed miner identity).
    //   (b) V13 anti-dominance (height >= DTD_DOMINANCE_GATE_HEIGHT)
    //   (c) V14 PoPC eligibility (height >= DTD_POPC_ELIGIBILITY_HEIGHT
    //       AND DTD_POPC_GATE_CONSENSUS_ACTIVE — the helper short-circuits
    //       to "eligible" until the flag flips)
    std::vector<LotteryEligibilityEntry> out;
    out.reserve(agg.size());
    for (const auto& kv : agg) {
        const auto& pkh = kv.first;

        // (a) recent-winner cooldown.
        if (exclusion_window > 0 && recent_winners.count(pkh)) continue;

        // (a1) V15 sliding recency window. When recent_miner_window > 0
        // (from V15_HEIGHT) an address must have mined at least one block
        // within [height - recent_miner_window, height - 1]. This REPLACES
        // the pre-V15 "mined ever" rule and drops dormant addresses. The
        // window reaches below the fork height at activation, so miners
        // active just before V15 are eligible immediately (no cliff).
        if (recent_miner_window > 0 &&
            kv.second.last_mined_height < height - recent_miner_window) {
            continue;
        }

        // (a2) V13.5 SbPoW-activity gate. A candidate must have at least one
        // SbPoW-signed block, proven by its most recent block being at height
        // >= V11_PHASE2_HEIGHT (= 7100). The helper short-circuits to true for
        // height < DTD_DOMINANCE_GATE_HEIGHT so pre-V13.5 replay is bit-identical.
        if (!is_sbpow_eligible(kv.second.last_mined_height, height)) continue;

        // (b) V13 anti-dominance gate. The helper short-circuits to
        // false for height < DTD_DOMINANCE_GATE_HEIGHT so pre-V13.5
        // behaviour is preserved bit-for-bit.
        if (height >= DTD_DOMINANCE_GATE_HEIGHT) {
            auto it = dominance_count.find(pkh);
            const int32_t mined_in_window = (it == dominance_count.end())
                ? 0
                : it->second;
            if (is_dtd_dominant(mined_in_window,
                                observed_window_blocks,
                                height)) {
                continue;
            }
        }

        // (c) Staged DTD-PoPC eligibility (P4c/P5). PoPC is required only from
        // DTD_POPC_ELIGIBILITY_HEIGHT (= V15_HEIGHT + grace) AND only when the
        // consensus flag is active — both encoded in popc_eligibility_enforced().
        // The flag ships false, so this branch is a no-op on eligibility today.
        if (popc_eligibility_enforced(height, DTD_POPC_GATE_CONSENSUS_ACTIVE) &&
            !has_active_canonical_popc(pkh, height)) {
            continue;
        }

        out.push_back(kv.second);
    }
    return out;
}

// V14 PoPC eligibility helper — preparatory implementation.
//
// While DTD_POPC_GATE_CONSENSUS_ACTIVE is false in params.h, this
// function returns true unconditionally so the V14 gate wired into
// compute_lottery_eligibility_set is a no-op on eligibility.
//
// When the flag flips to true (a future coordinated point release
// gated behind its own height + announcement), this body will be
// replaced with a deterministic check against chain-derived PoPC
// state. That migration is NOT part of this PR — see
// docs/V14_DTD_POPC_ELIGIBILITY.md for the migration prerequisites.
// P4a — chain-derived PoPC event source (registered by the node).
static PopcEventSource g_popc_src{};
void set_popc_event_source(PopcEventSource src) { g_popc_src = std::move(src); }

bool has_active_canonical_popc(const PubKeyHash& pkh, int64_t height) {
    // Pre-activation — including ALL mainnet heights while POPC_V15_ACTIVATION_HEIGHT
    // is INT64_MAX — behave exactly as before: eligible (no-op, byte-identical).
    if (!popc_v15_active_at(height)) return true;
    // V15 active: use the chain-derived active set, NEVER popc_registry.json.
    if (!g_popc_src) return true;                     // defensive: no source wired
    return popc_v15_owner_active(g_popc_src(height), pkh, height);
}

int64_t select_lottery_winner_index(
    const std::vector<LotteryEligibilityEntry>& eligible,
    const Bytes32&                              prev_block_hash,
    int64_t                                     height)
{
    if (eligible.empty()) return -1;

    // Domain-separated seed:
    //   sha256( LOTTERY_RNG_DOMAIN || prev_block_hash || height_le )
    //
    // Single-pass SHA-256 is used (NOT SHA-256d). Rationale:
    //   - The output is a uniform 256-bit value before reduction;
    //     double-hashing adds no entropy from a 16+32+8-byte input.
    //   - Bitcoin's "merkle hash" tradition uses double-SHA but for
    //     lottery selection a single SHA-256 is standard practice
    //     (matches the libsecp256k1 schnorrsig domain idiom).
    //   - All lottery RNG callers — miner and validator — go through
    //     this exact path, so byte-for-byte determinism is preserved.
    std::vector<uint8_t> buf;
    buf.reserve(LOTTERY_RNG_DOMAIN_LEN + 32 + 8);
    buf.insert(buf.end(),
               reinterpret_cast<const uint8_t*>(LOTTERY_RNG_DOMAIN),
               reinterpret_cast<const uint8_t*>(LOTTERY_RNG_DOMAIN)
                   + LOTTERY_RNG_DOMAIN_LEN);
    append(buf, prev_block_hash);
    append_u64_le(buf, (uint64_t)height);

    Bytes32 seed = sha256(buf);

    // Reduce the first 8 bytes of the seed to a 64-bit roll. Endian
    // controlled via read_u64_le so x86 and ARM produce identical
    // indices.
    const uint64_t roll = read_u64_le(seed.data());
    const uint64_t n    = (uint64_t)eligible.size();
    return (int64_t)(roll % n);
}

int64_t select_lottery_winner_index_from_history(
    const std::vector<LotteryEligibilityEntry>& eligible,
    const std::vector<LotteryMinedBlockView>&   blocks,
    int64_t                                     height)
{
    if (eligible.empty()) return -1;

    std::vector<LotteryMinedBlockView> window;
    window.reserve((size_t)LOTTERY_RNG_HISTORY_BLOCKS);
    const int64_t lo = height - LOTTERY_RNG_HISTORY_BLOCKS;
    const int64_t hi = height - 1;
    for (const auto& b : blocks) {
        if (b.height < lo || b.height > hi) continue;
        window.push_back(b);
    }

    std::sort(window.begin(), window.end(),
              [](const LotteryMinedBlockView& a, const LotteryMinedBlockView& b) {
                  return a.height < b.height;
              });

    std::vector<uint8_t> buf;
    buf.reserve(LOTTERY_RNG_DOMAIN_LEN + window.size() * 32 + 8);
    buf.insert(buf.end(),
               reinterpret_cast<const uint8_t*>(LOTTERY_RNG_DOMAIN),
               reinterpret_cast<const uint8_t*>(LOTTERY_RNG_DOMAIN)
                   + LOTTERY_RNG_DOMAIN_LEN);

    for (const auto& b : window) {
        append(buf, b.block_hash);
    }
    append_u64_le(buf, (uint64_t)height);

    Bytes32 seed = sha256(buf);
    const uint64_t roll = read_u64_le(seed.data());
    const uint64_t n    = (uint64_t)eligible.size();
    return (int64_t)(roll % n);
}

// ============================================================================
// C7 — rollover state machinery (real, pure)
// ============================================================================
//
// apply_lottery_block / undo_lottery_block are pure functions over
// LotteryApplyInput / LotteryApplyResult. They do NOT touch StoredBlock,
// BlockUndo, chain.json, coinbase, rewards, or any UTXO state. Wiring
// the result into persistent chain state lands in C8 alongside the
// coinbase shape change.

LotteryApplyResult apply_lottery_block(const LotteryApplyInput& in) {
    LotteryApplyResult r;
    r.pending_before = in.pending_before;
    r.lottery_amount = in.lottery_amount;

    // ---- Validation: defensive, no aborts ----
    if (in.pending_before < 0) {
        r.ok = false;
        r.error = "apply_lottery_block: pending_before < 0 ("
                + std::to_string((long long)in.pending_before) + ")";
        return r;
    }
    if (in.lottery_amount < 0) {
        r.ok = false;
        r.error = "apply_lottery_block: lottery_amount < 0 ("
                + std::to_string((long long)in.lottery_amount) + ")";
        return r;
    }

    // ---- IDLE — non-triggered block ----
    // Critical invariant: a non-triggered block NEVER pays out the
    // jackpot, even if pending_before > 0. Pending stays as-is.
    if (!is_lottery_block(in.height, in.phase2_height)) {
        r.triggered     = false;
        r.paid_out      = false;
        r.pending_after = in.pending_before;
        // winner_pkh / winner_index already zero / -1 by default.
        return r;
    }

    r.triggered = true;

    // ---- Overflow guard for pending_before + lottery_amount ----
    // Both operands are >= 0 (validated above). Use the standard signed
    // overflow test: a + b overflows iff a > INT64_MAX - b.
    if (in.lottery_amount > 0
        && in.pending_before > std::numeric_limits<int64_t>::max() - in.lottery_amount) {
        r.ok = false;
        r.error = "apply_lottery_block: pending_before + lottery_amount "
                  "would overflow int64_t (pending_before="
                + std::to_string((long long)in.pending_before)
                + ", lottery_amount="
                + std::to_string((long long)in.lottery_amount) + ")";
        // Leave pending_after at 0 — caller treats !ok as a hard reject.
        return r;
    }

    // ---- UPDATE — triggered, eligibility set empty ----
    if (in.eligible.empty()) {
        r.paid_out      = false;
        r.pending_after = in.pending_before + in.lottery_amount;
        // winner_pkh / winner_index stay as default zero / -1.
        return r;
    }

    // ---- PAYOUT — triggered, eligibility set non-empty ----
    const int64_t idx = select_lottery_winner_index(
        in.eligible, in.prev_block_hash, in.height);

    // select_lottery_winner_index returns -1 only on empty input; we
    // already filtered that. Defence in depth:
    if (idx < 0 || (size_t)idx >= in.eligible.size()) {
        r.ok = false;
        r.error = "apply_lottery_block: select_lottery_winner_index returned "
                "invalid index " + std::to_string((long long)idx)
                + " for eligible.size()=" + std::to_string(in.eligible.size());
        return r;
    }

    r.paid_out       = true;
    r.winner_index   = idx;
    r.winner_pkh     = in.eligible[(size_t)idx].pkh;
    // Total payout is the historical pending plus the current block's share.
    r.lottery_payout = in.pending_before + in.lottery_amount;
    // After paying out, pending resets to zero.
    r.pending_after  = 0;
    return r;
}

int64_t undo_lottery_block(const LotteryApplyResult& applied) {
    // Symmetric inverse of apply_lottery_block: the saved
    // pending_before is the value the caller restores to its
    // `pending_lottery_amount` storage on reorg.
    //
    // Note: this works correctly for ALL three branches —
    //   IDLE     pending_after == pending_before  (no-op restore)
    //   UPDATE   pending_after == pending_before + lottery_amount
    //                            -> restore to pending_before
    //   PAYOUT   pending_after == 0
    //                            -> restore to pending_before
    return applied.pending_before;
}

// ============================================================================
// Pre-C6 skeleton — kept aborting; legacy callers should not exist.
// ============================================================================

namespace {
[[noreturn]] void phase2_not_implemented(const char* fn) {
    std::fprintf(stderr,
        "FATAL: sost::lottery::%s called before V11 Phase 2 implementation. "
        "This is a skeleton — wire the real code before activating "
        "V11_PHASE2_HEIGHT.\n", fn);
    std::abort();
}
} // namespace

bool is_triggered(int64_t /*height*/,
                  int64_t /*v11_phase2_height*/,
                  int64_t /*high_freq_window*/)
{
    // Superseded by is_lottery_block (header-only inline). This
    // 3-arg legacy entry point is kept aborting to surface any
    // accidental caller.
    phase2_not_implemented("is_triggered");
}

std::optional<PubKeyHash> pick_winner(const Bytes32& /*prev_block_hash*/,
                                   int64_t /*height*/,
                                   const std::vector<PubKeyHash>& /*eligibility_sorted*/)
{
    // Superseded by select_lottery_winner_index. The new API returns
    // an index into a richer LotteryEligibilityEntry vector instead
    // of a bare PubKeyHash optional.
    phase2_not_implemented("pick_winner");
}

void apply_block(RolloverState& /*state*/,
                 const TransitionInputs& /*in*/,
                 TransitionOutputs& /*out*/)
{
    // Rollover state machinery — C7 territory.
    phase2_not_implemented("apply_block");
}

void undo_block(RolloverState& /*state*/, uint64_t /*pending_before_block*/) {
    // Reorg path for the rollover state — C7 territory.
    phase2_not_implemented("undo_block");
}

} // namespace sost::lottery
