// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
//
// =============================================================================
// Atomic Swap HTLC — V13 candidate scaffolding (DORMANT)
// =============================================================================
//
// THIS IS SCAFFOLDING ONLY.
//
// This header declares the activation gate for a future native HTLC
// (Hashed-Time-Locked Contract) transaction primitive that would enable
// non-custodial crypto-to-crypto atomic swaps between SOST and BTC / ETH /
// USDT / USDC / BNB / PAXG / XAUT.
//
// The full design lives in:
//   - docs/design/ATOMIC_SWAP_IMPLEMENTATION_MAP.md
//   - docs/design/ATOMIC_SWAP_HTLC_IMPLEMENTATION_PLAN.md
//   - docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md
//
// NO HTLC transaction type is added to include/sost/transaction.h in this
// scaffolding. NO validation rules are added to src/tx_validation.cpp.
// NO wallet / RPC paths exist yet. The constant below is DEFINED but is
// NOT REFERENCED from any .cpp file in this commit, so it is a no-op
// at runtime by construction.
//
// Future Phase 3 (a separate, dedicated multi-week sprint) will add:
//   - OUT_HTLC_LOCK   (proposed 0x12) — typed output locking SOST under hashlock+timelock
//   - OUT_HTLC_CLAIM  (proposed 0x13) — spend path requiring preimage before timeout
//   - OUT_HTLC_REFUND (proposed 0x14) — spend path requiring timeout
//   - serialization, mempool acceptance, block-validation rules
//   - wallet builders + RPC endpoints (createhtlclock, claimhtlc, refundhtlc,
//     decodehtlc, gethtlcstatus)
//   - exhaustive unit + integration + adversarial tests (~20+ test cases)
//   - external review of cryptographic and economic safety
//   - then flip ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT from INT64_MAX to a
//     finite block height in a single one-line activation commit.
//
// Rollback: revert to INT64_MAX. Same single-line change. No fork.
//
// PRECEDENT this file follows verbatim:
//   - include/sost/gold_vault_slice1.h    (GV_SLICE1_ACTIVATION_HEIGHT)
//   - include/sost/params.h               (BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT)
//   Both define a constant at INT64_MAX, document the activation procedure,
//   and expose a `is_active_at(height)` helper that returns false while
//   the gate is at the sentinel.
//
// =============================================================================
#pragma once

#include <cstdint>
#include <climits>

#include "sost/params.h"   // V14_HEIGHT / V15_HEIGHT (activation height source of truth)

namespace sost {

// -----------------------------------------------------------------------------
// Activation gate
// -----------------------------------------------------------------------------
//
// INT64_MAX = OFF (sentinel). While this constant equals INT64_MAX the
// helper `atomic_swap_htlc_active_at()` returns false for every height.
// This is the bit-identical behaviour required for V13 deployment in the
// "scaffolding only — no consensus impact" mode.
//
// To activate the rule in a future commit, the operator MUST first land
// the full Phase 3 implementation (output types, validation rules,
// serialization, mempool, block validator, wallet, RPC, tests, external
// review). Then in a SEPARATE one-line activation commit, replace
// INT64_MAX with the chosen activation block height.
//
// At the time this scaffolding header is committed, the project's earliest
// realistic activation candidate is V14 (block 15000). V13 (block 12000)
// is feasible only if Phase 3 can be completed, tested, and externally
// reviewed before the V13 freeze — which the implementation map flags as
// extremely unlikely given the remaining V13 cycle length.
// SAFETY-CLOSED. Gate moved BACK to INT64_MAX after Phase 3A scope-B
// (commit c8a315a5) shipped HTLC_LOCK structural validation only.
// HTLC_CLAIM and HTLC_REFUND spending paths are NOT yet implemented,
// so activating LOCK at any finite height would allow users to create
// a LOCK output that has no spend path — locking SOST permanently.
// To prevent any accidental loss-of-funds even in dev / test mode, the
// gate stays at INT64_MAX until ALL THREE of the following are true:
//
//   1. HTLC_CLAIM validation rules are implemented and tested
//      (preimage check, signature, timeout check, all adversarial
//      tests passing: wrong preimage, claim after timeout, etc.).
//   2. HTLC_REFUND validation rules are implemented and tested
//      (signature, timeout check, all adversarial tests passing:
//      refund before timeout, refund after claim, etc.).
//   3. External cryptographic and economic review of the full
//      LOCK + CLAIM + REFUND set has been completed.
//
// V15-era is the INTENDED activation height (params.h::V15_HEIGHT) once the
// 3-condition checklist is met. The gate stays at INT64_MAX until then. While
// deferred:
//   - LOCK outputs cannot appear in any valid block (R11 rejects).
//   - CLAIM / REFUND tx_types cannot appear (no validation yet
//     anyway, but R2_BAD_TX_TYPE would also reject).
//   - Pre-activation chain replay is bit-identical to the pre-patch
//     state for all historical and future blocks while the gate
//     stays at INT64_MAX.
//
// Rollback discipline: never flip this gate to a finite value
// without verifying the 3-condition checklist above. The flip is a
// single-line change and must be paired with a unit-test run + a
// full ctest --output-on-failure run before the commit lands.
// NOTE: V14_HEIGHT / V14_5_HEIGHT / V15_HEIGHT are defined in params.h — never
// redefined here.
//
// CTO DECISION (V14.5 activation — supersedes the earlier V14 plan):
// The atomic-swap HTLC was *declared* active at V14 (block 15000) but was
// NON-FUNCTIONAL on mainnet: a LOCK could be mined, but the CLAIM (0x10) /
// REFUND (0x11) txs were rejected on the block path (process_block /
// ConnectBlock "must be standard"), so locked funds could never settle.
//
// The corrected activation height is V14_5_HEIGHT (mainnet 16000 / testnet 30) —
// a dedicated milestone, SEPARATE from the V15 automation bundle (PoPC / Gold
// Vault) at 20000, which is left exactly as on main. One recompiled binary
// carries BOTH milestones: the HTLC fix at 16000 and V15 PoPC at 20000.
//
// This single source of truth makes the ENTIRE HTLC feature activate together:
//   - LOCK output acceptance (S9 allowlist + R11/R17 in tx_validation.cpp),
//   - the R17–R24 CLAIM/REFUND consensus rules, AND
//   - the CLAIM/REFUND block-path acceptance (sost-node.cpp + utxo_set.cpp),
// all flip at the same height. Below V14.5 the feature is fully inert, so there
// is no "stuck LOCK" window and the chain replay of blocks 0..16000 is
// byte-identical to the pre-patch binaries (verified: the live chain has zero
// HTLC txs today — listhtlclocks == []).
//
// Why this is safe: every historical block is below 16000, so
// atomic_swap_htlc_active_at(height) is false for all of them and every HTLC
// code path (S9, R-rules, block-path guards) is a no-op — replay stays
// bit-identical. V14.5 is a MANDATORY-BINARY-UPDATE fork: every node/miner MUST
// recompile + restart with this binary BEFORE block 16000 or it will diverge
// once the first HTLC tx is mined. Coordinated via the disclosure banner +
// BitcoinTalk announcement (recompile window: after block 15800, before 16000).
// EVM-only — SOST_BTC_HTLC_SIGNING stays OFF (BTC funding path still a stub).
//
// Testnet (-DSOST_TESTNET_FORKS) resolves V14_5_HEIGHT to 30 (params.h), keeping
// the activation low enough for the regtest/local soak to exercise the full
// LOCK→CLAIM→REFUND lifecycle. The mainnet value is 16000 and byte-identical.
inline constexpr int64_t ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_5_HEIGHT;

// -----------------------------------------------------------------------------
// is_height_active helper
// -----------------------------------------------------------------------------
//
// Returns true iff atomic-swap HTLC validation rules should be enforced
// at the given block height. With the gate at INT64_MAX this always
// returns false — every call site is a guaranteed no-op.
//
// Once Phase 3 lands, validators must call this helper at every consensus
// decision point that touches HTLC outputs / inputs. The helper is the
// SINGLE source of truth for the activation height.
inline constexpr bool atomic_swap_htlc_active_at(int64_t height) {
    return height >= ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT;
}

// -----------------------------------------------------------------------------
// V14.7 — relay/policy activation (the PR #63 fix), DECOUPLED from consensus
// -----------------------------------------------------------------------------
//
// atomic_swap_htlc_active_at (above, V14_5_HEIGHT / mainnet 16000) gates the
// CONSENSUS acceptance of HTLC outputs and CLAIM/REFUND txs — already live and
// UNCHANGED. This SEPARATE, LATER gate controls ONLY the relay/mempool policy
// layer: the capsule-policy exemption in ValidateTransactionPolicy that lets HTLC
// LOCK/CLAIM outputs be broadcast (sendrawtransaction) and included in block
// templates.
//
// It is deliberately set HIGHER than the consensus gate (V14_7_HEIGHT, mainnet
// 18000) so activation is a coordinated flag-day. Between V14_5_HEIGHT and
// V14_7_HEIGHT the HTLC feature is consensus-valid but NON-RELAYABLE
// (bad-capsule on broadcast), so no HTLC ever enters a template, every block
// stays txs=1, and mining is unaffected — the asymmetric-mempool degradation of
// the first (ungated) deploy cannot recur. At V14_7_HEIGHT every upgraded node
// flips together. This is a POLICY gate: it never decides block validity, so a
// non-upgraded node does not fork — but a coordinated recompile+restart in the
// window after block 17900, before 18000, keeps the network's mempools
// homogeneous (all txs=1 → all txs=N in lockstep). MANDATORY-BINARY-UPDATE.
inline constexpr int64_t ATOMIC_SWAP_RELAY_ACTIVATION_HEIGHT = V14_7_HEIGHT;

inline constexpr bool atomic_swap_relay_active_at(int64_t height) {
    return height >= ATOMIC_SWAP_RELAY_ACTIVATION_HEIGHT;
}

} // namespace sost
