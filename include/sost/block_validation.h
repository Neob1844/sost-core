#pragma once
// =============================================================================
// SOST — Phase 5.5: Block Validation + Chain Connect (Atomic)
// =============================================================================
//
// This header defines the *consensus-facing* block validation pipeline:
//
//   L1: ValidateBlockStructure(block)
//   L2: ValidateBlockHeaderContext(header, prev, now, expected_bits_q)
//   L3: ValidateBlockTransactionsConsensus(block, utxos_view, tx_ctx_base, gold_pkh, popc_pkh)
//   L4: ConnectValidatedBlockAtomic(block, utxo_set, out_undo)
//
// Notes (consensus-critical):
// - Keep constants single-sourced to avoid accidental forks.
// - Genesis constants must match chainparams/miner/genesis tooling exactly.
// - Avoid duplicating GENESIS_BITSQ here: it is defined in <sost/params.h>.
//
// =============================================================================

#include <sost/block.h>
#include <sost/tx_validation.h>
#include <sost/utxo_set.h>
#include <sost/params.h>   // GENESIS_BITSQ lives here (single source of truth)

#include <cstdint>
#include <string>

namespace sost {

// =============================================================================
// Consensus limits (align with tx_validation.h)
// =============================================================================
inline constexpr size_t  MAX_BLOCK_SIZE_CONSENSUS = (size_t)MAX_BLOCK_BYTES_CONSENSUS; // 1,000,000
inline constexpr size_t  MAX_BLOCK_TXS_CONSENSUS  = 65536;
// Python-aligned: MAX_FUTURE_DRIFT = 600s (10 minutes)
inline constexpr int64_t MAX_FUTURE_BLOCK_TIME    = 10 * 60; // 600 seconds

// =============================================================================
// Genesis parameters (must match chainparams)
// =============================================================================
//
// GENESIS_TIMESTAMP is defined here because block validation needs it for
// header-time checks (genesis timestamp mismatch, future drift rules, etc.).
//
// GENESIS_BITSQ is defined in <sost/params.h> to ensure:
// - One canonical definition shared by PoW, miner, and validation.
// - No ODR/redefinition hazards when including pow headers.
// - Lower risk of accidental consensus divergence.
//
inline constexpr int64_t GENESIS_TIMESTAMP = 1773597600; // 2026-03-15 18:00:00 UTC
// GENESIS_BITSQ: defined in <sost/params.h>

// ---------------------------------------------------------------------------
// L1 — Structural validation (format / bounds)
// ---------------------------------------------------------------------------
bool ValidateBlockStructure(
    const Block& block,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// L2 — Header context validation (prev-link, time rules, expected difficulty)
// ---------------------------------------------------------------------------
bool ValidateBlockHeaderContext(
    const BlockHeader& header,
    const BlockHeader* prev,
    int64_t current_time,
    uint32_t expected_bits_q,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// L3 — Transaction consensus validation (fees, coinbase, UTXO semantics)
// ---------------------------------------------------------------------------
struct BlockConsensusResult {
    bool        ok{false};
    int64_t     total_fees{0};
    int64_t     subsidy{0};
    std::string message;

    static BlockConsensusResult Ok(int64_t fees, int64_t sub) {
        return {true, fees, sub, "ok"};
    }
    static BlockConsensusResult Fail(const std::string& msg) {
        return {false, 0, 0, msg};
    }
};

/// Validates all transactions and coinbase amounts exactly using Phase 3.
/// IMPORTANT: requires constitutional PKHs for CB6 checks.
BlockConsensusResult ValidateBlockTransactionsConsensus(
    const Block& block,
    const UtxoSet& utxos_view,
    const TxValidationContext& base_tx_ctx,
    const PubKeyHash& gold_vault_pkh,
    const PubKeyHash& popc_pool_pkh);

// ---------------------------------------------------------------------------
// L4 — Atomic chain connect/disconnect (apply UTXO diffs)
// ---------------------------------------------------------------------------
bool ConnectValidatedBlockAtomic(
    const Block& block,
    UtxoSet& utxo_set,
    BlockUndo& out_undo,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// Reorg support
// ---------------------------------------------------------------------------
bool DisconnectBlock(
    const Block& block,
    UtxoSet& utxo_set,
    const BlockUndo& undo,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// Subsidy hook (implementation may call your real schedule)
// ---------------------------------------------------------------------------
int64_t GetBlockSubsidy(int64_t height);

} // namespace sost
