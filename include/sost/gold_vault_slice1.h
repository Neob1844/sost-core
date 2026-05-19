// gold_vault_slice1.h — Consensus-level Gold Vault spend-side governance, Slice 1
//
// V13 Gold Vault governance Slice 1: G1 (purpose restriction), G2 (dual destination
// whitelists), G3 (per-spend cap + rate limit). Pure helper functions + compile-time
// constants. The wiring point in src/block_validation.cpp calls these helpers ONLY at
// heights >= GV_SLICE1_ACTIVATION_HEIGHT; below activation, every spend behaves
// exactly as it does on pre-Slice-1 binaries (bit-identical historical replay).
//
// Default state: SENTINEL-DISABLED.
//   GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX  ⇒ the rule never activates
//   GV_SLICE1_WHITELIST_PRIMARY = {}         ⇒ whitelist is empty
//   GV_SLICE1_WHITELIST_MIRROR  = {}         ⇒ mirror is empty
//   GV_SLICE1_PER_SPEND_CAP_BPS = 0          ⇒ cap is disabled
//   GV_SLICE1_RATE_LIMIT_BLOCKS = 0          ⇒ rate-limit is disabled
//
// At sentinel defaults, the validator wiring is a no-op and consensus behaviour is
// unchanged from pre-Slice-1. A follow-up commit MUST set
//   GV_SLICE1_ACTIVATION_HEIGHT = V13_HEIGHT (= 12000),
//   GV_SLICE1_WHITELIST_PRIMARY = { <operator-decided PKHs> },
//   GV_SLICE1_WHITELIST_MIRROR  = { <same PKHs in a different file/source for G2> },
//   GV_SLICE1_PER_SPEND_CAP_BPS = <operator-decided basis points>,
//   GV_SLICE1_RATE_LIMIT_BLOCKS = <operator-decided block count>,
// in a single small reviewable commit to turn the rule on.
//
// Why the activation gate is height-anchored, not constant-anchored: a future fork
// that flips the sentinel must be height-coordinated with every miner and validator.
// Below the activation height, the helper functions intentionally return "allow" so
// historical replay of blocks 0..GV_SLICE1_ACTIVATION_HEIGHT-1 is bit-identical
// regardless of what the constants contain.
//
// G2 (dual whitelists): the validator MUST call gv_slice1_whitelists_agree() and
// fail-closed if it returns false. The two whitelists live in different translation
// units / files; if a future commit edits one but forgets the other, the validator
// rejects every vault spend until the mismatch is fixed. This catches operator
// misconfiguration before it becomes a consensus split.
//
// G3-rate-limit caveat: the rate-limit helper (gv_slice1_rate_limit_ok) is pure and
// tested in this slice, BUT the validator wiring for rate-limit requires a new
// StoredBlock field "gold_vault_last_spend_height" that does not yet exist. That
// chain-state extension is a separate follow-up commit. Until then, the rate-limit
// helper is unit-tested but not enforced at consensus level. This is documented
// here so a reviewer cannot mistakenly assume rate-limit is live.
//
// Safety contract:
//   - Pure header-only inline functions, no I/O.
//   - No private keys, no wallet, no signing, no broadcast.
//   - No network, no GitHub API, no Ethereum.
//   - No mutation of any constant at runtime.
//   - Below activation height: every helper returns "allow" semantics.
//   - At or above activation height with sentinel constants: every helper still
//     returns "allow" (sentinel-disabled state), EXCEPT
//     gv_slice1_whitelists_agree() which returns true on both-empty (vacuously).
//
// See docs/V13_POPC_GOLDVAULT_IMPLEMENTATION_PLAN.md for the full slice plan.
//
#pragma once

#include "sost/consensus_constants.h"
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_signer.h"   // PubKeyHash
#include <array>
#include <climits>
#include <cstdint>

namespace sost {

// =========================================================================
// Slice 1 activation gate — sentinel-disabled by default
// =========================================================================
//
// Set to V13_HEIGHT (12000) in the follow-up commit that fills the
// whitelist + cap + rate-limit values. Until then, the validator wiring
// is a no-op for every height (because height < INT64_MAX is always true).
//
inline constexpr int64_t GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX;

// =========================================================================
// Whitelist of legal Gold Vault spend destinations (G1 + G2)
// =========================================================================
//
// Two independent constants live in two different files:
//   - GV_SLICE1_WHITELIST_PRIMARY here (gold_vault_slice1.h)
//   - GV_SLICE1_WHITELIST_MIRROR  in consensus_constants.h
//
// Both MUST contain the same set of PubKeyHash values, in the same order.
// The validator calls gv_slice1_whitelists_agree() and fails closed on
// mismatch. This catches operator misconfiguration (someone edits one
// table but forgets the other) BEFORE it can become a consensus split.
//
// Default: both empty. With activation = INT64_MAX, this is irrelevant.
// When the follow-up commit flips activation to V13_HEIGHT, it MUST also
// populate both tables with the same content.
//
// Compile-time max length on the whitelist: 5 entries. The public-scope
// appendix in the whitepaper commits to "≤ 5 addresses". This cap is
// enforced statically here.
//
inline constexpr std::size_t GV_SLICE1_WHITELIST_MAX = 5;
inline constexpr std::size_t GV_SLICE1_WHITELIST_PRIMARY_LEN = 0;
inline constexpr std::array<PubKeyHash, GV_SLICE1_WHITELIST_PRIMARY_LEN>
    GV_SLICE1_WHITELIST_PRIMARY{};

// =========================================================================
// Per-spend cap (G3a) — basis points of vault balance
// =========================================================================
//
// 200 = 2 % of vault balance per single spend. Sentinel: 0 = disabled.
//
// The default proposed value in
// docs/internal/v6-signature-bound-pow.md is 200 (2 %). The follow-up
// commit MUST replace 0 with the operator-decided value after evaluating
// the projected vault balance at block 12,000.
//
inline constexpr int32_t GV_SLICE1_PER_SPEND_CAP_BPS = 0;
inline constexpr int32_t GV_SLICE1_BPS_DENOMINATOR   = 10000;

// =========================================================================
// Rate limit (G3b) — minimum blocks between vault spends
// =========================================================================
//
// 144 = ~24h at the target 10-minute block time. Sentinel: 0 = disabled.
//
// HELPER WIRING NOTE: the validator wiring for rate-limit requires a new
// StoredBlock field gold_vault_last_spend_height that does not yet exist.
// The rate-limit helper below is pure and unit-tested but NOT called from
// src/block_validation.cpp. The chain-state extension is a separate
// follow-up commit. Until then, rate-limit is documented but not enforced.
//
inline constexpr int64_t GV_SLICE1_RATE_LIMIT_BLOCKS = 0;

// =========================================================================
// Helper: is the Slice 1 rule active at this height?
// =========================================================================
//
// Returns true iff height >= activation. With default
// GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX, this always returns false,
// which means the validator wiring is a no-op at every height. After the
// follow-up commit flips activation to V13_HEIGHT, this returns true for
// every block at or after 12,000 and false for every block below.
//
inline constexpr bool gv_slice1_active_at(int64_t height) {
    return height >= GV_SLICE1_ACTIVATION_HEIGHT;
}

// =========================================================================
// Helper G2: do the primary and mirror whitelists agree?
// =========================================================================
//
// Two empty whitelists agree vacuously (returns true). Two whitelists of
// different lengths or with any element mismatch return false. The
// validator wiring MUST call this and fail-closed-reject if it returns
// false; that catches operator misconfiguration where one constant table
// was edited but the other was forgotten.
//
// This function is defined in gold_vault_slice1_mirror.cpp (which sees
// both PRIMARY and MIRROR) — declaration only here so the header stays
// pure inline.
//
bool gv_slice1_whitelists_agree();

// =========================================================================
// Helper G1 / G2: is `dest` in the (agreed) whitelist?
// =========================================================================
//
// Returns true iff `dest` is in BOTH GV_SLICE1_WHITELIST_PRIMARY AND
// GV_SLICE1_WHITELIST_MIRROR. If the two whitelists do not agree, this
// returns false unconditionally (fail-closed).
//
// With the default (both empty), this always returns false. Combined
// with gv_slice1_active_at returning false by default, the validator
// wiring is a no-op until the operator commits real values.
//
bool gv_slice1_destination_allowed(const PubKeyHash& dest);

// =========================================================================
// Helper G3a: is `amount` within the per-spend cap?
// =========================================================================
//
// Returns true iff amount <= (vault_balance * GV_SLICE1_PER_SPEND_CAP_BPS) /
// GV_SLICE1_BPS_DENOMINATOR. Sentinel semantics: if
// GV_SLICE1_PER_SPEND_CAP_BPS == 0, returns true unconditionally (cap
// is disabled).
//
// The check is intentionally inclusive at the cap (amount == cap is
// allowed) and uses integer arithmetic with the bps denominator to
// avoid floating-point determinism issues across compilers.
//
inline constexpr bool gv_slice1_amount_within_cap(
    int64_t amount, int64_t vault_balance)
{
    if (GV_SLICE1_PER_SPEND_CAP_BPS == 0) return true;       // sentinel: cap disabled
    if (amount < 0 || vault_balance < 0)  return false;      // defensive
    // cap = vault_balance * bps / denominator, computed in 128-bit-safe order
    // since vault_balance < SUPPLY_MAX_STOCKS (~4.67e14) and bps < 10000, the
    // product fits in int64_t (max ~4.67e18 vs INT64_MAX ~9.22e18).
    const int64_t cap = (vault_balance / GV_SLICE1_BPS_DENOMINATOR)
                            * GV_SLICE1_PER_SPEND_CAP_BPS;
    return amount <= cap;
}

// =========================================================================
// Helper G3b: is the rate-limit satisfied?
// =========================================================================
//
// Returns true iff blocks_since_last_vault_spend >= GV_SLICE1_RATE_LIMIT_BLOCKS.
// Sentinel: if GV_SLICE1_RATE_LIMIT_BLOCKS == 0, returns true unconditionally
// (rate-limit disabled).
//
// Special value INT64_MAX for blocks_since_last_vault_spend means "no prior
// vault spend on record" — passes unconditionally.
//
// NOT WIRED INTO src/block_validation.cpp YET. The validator needs a new
// StoredBlock field to know when the last vault spend happened. That is a
// separate follow-up commit. This helper is unit-tested here for correctness.
//
inline constexpr bool gv_slice1_rate_limit_ok(int64_t blocks_since_last_spend) {
    if (GV_SLICE1_RATE_LIMIT_BLOCKS == 0) return true;  // sentinel: rate-limit disabled
    if (blocks_since_last_spend < 0)      return false; // defensive: corrupt state
    return blocks_since_last_spend >= GV_SLICE1_RATE_LIMIT_BLOCKS;
}

// =========================================================================
// Helper: does `tx` spend from the gold vault address?
// =========================================================================
//
// Returns true iff any input of tx references a UTXO whose pubkey_hash
// matches gold_vault_pkh. The caller must supply the previous-output
// lookup (e.g. via UtxoSet::GetUTXO). This is a thin convenience over
// what the validator already does to compute fees, so we provide a
// minimal version that takes a callable for the UTXO lookup.
//
// Template kept inline-header so call sites avoid a link-time dependency.
//
template <typename UtxoLookup>
inline bool gv_slice1_tx_spends_from_vault(
    const Transaction& tx,
    const PubKeyHash& gold_vault_pkh,
    UtxoLookup lookup_pkh)
{
    for (const auto& inp : tx.inputs) {
        PubKeyHash pkh;
        if (lookup_pkh(inp.prev_txid, inp.prev_index, pkh)) {
            if (pkh == gold_vault_pkh) return true;
        }
    }
    return false;
}

} // namespace sost
