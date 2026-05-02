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
// validation paths. Phase 2 stays dormant via V11_PHASE2_HEIGHT =
// INT64_MAX in params.h; the only callers of the new helpers today
// are tests/test_lottery_eligibility.cpp.
#include "sost/lottery.h"

#include "sost/crypto.h"      // sha256()
#include "sost/serialize.h"   // append, append_u64_le, read_u64_le

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <string>

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
    int64_t                                   exclusion_window)
{
    // Step 1: aggregate per-pkh stats over the chain view. Only blocks
    // strictly before `height` count (the current block is supplied via
    // current_miner_pkh and is excluded by rule 2 below).
    //
    // std::map keyed by PubKeyHash gives a deterministic lex-sorted
    // iteration as a side-effect of std::array<uint8_t, 20>'s
    // operator<. We could equivalently aggregate into unordered_map
    // and sort at the end; the std::map path is simpler and the
    // benchmark is well below the C9 50 ms target on the test sizes.
    std::map<PubKeyHash, LotteryEligibilityEntry> agg;
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
    }

    // Step 2: build the recent-winner exclusion set in O(window) by
    // walking the same view once more and pulling out blocks whose
    // height falls into [height - exclusion_window, height - 1].
    // Stored as a sorted-by-pkh std::set for deterministic membership.
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
    std::vector<LotteryEligibilityEntry> out;
    out.reserve(agg.size());
    for (const auto& kv : agg) {
        const auto& pkh = kv.first;
        // Rule 2: current block's miner is excluded.
        if (pkh == current_miner_pkh) continue;
        // Rule 3: recent reward winners are excluded.
        if (exclusion_window > 0 && recent_winners.count(pkh)) continue;
        out.push_back(kv.second);
    }
    return out;
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
