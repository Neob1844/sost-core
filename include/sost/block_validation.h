#pragma once
// =============================================================================
// SOST — Phase 5.5: Block Validation + Chain Connect (Atomic)
//
// L1: ValidateBlockStructure(block)
// L2: ValidateBlockHeaderContext(header, prev, now, expected_bits_q)
// L3: ValidateBlockTransactionsConsensus(block, utxos_view, tx_ctx_base, gold_pkh, popc_pkh)
// L4: ConnectValidatedBlockAtomic(block, utxo_set, out_undo)
//
// =============================================================================

#include <sost/block.h>
#include <sost/tx_validation.h>
#include <sost/utxo_set.h>

#include <cstdint>
#include <string>

namespace sost {

// Consensus limits (align with tx_validation.h)
inline constexpr size_t  MAX_BLOCK_SIZE_CONSENSUS = (size_t)MAX_BLOCK_BYTES_CONSENSUS; // 1,000,000
inline constexpr size_t  MAX_BLOCK_TXS_CONSENSUS  = 65536;
inline constexpr int64_t MAX_FUTURE_BLOCK_TIME    = 2 * 60 * 60; // 2 hours

// Genesis parameters (must match chainparams)
inline constexpr int64_t  GENESIS_TIMESTAMP = 1772236800; // 2026-02-28 00:00:00 UTC
inline constexpr uint32_t GENESIS_BITSQ     = 353075;     // Q16.16 initial difficulty

// ---------------------------------------------------------------------------
// L1
// ---------------------------------------------------------------------------
bool ValidateBlockStructure(
    const Block& block,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// L2
// ---------------------------------------------------------------------------
bool ValidateBlockHeaderContext(
    const BlockHeader& header,
    const BlockHeader* prev,
    int64_t current_time,
    uint32_t expected_bits_q,
    std::string* err = nullptr);

// ---------------------------------------------------------------------------
// L3
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
// L4
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
