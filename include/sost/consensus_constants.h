// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once
#include <cstdint>
#include <cstddef>

namespace sost {

// Monetary unit
inline constexpr int64_t STOCKS_PER_SOST   = 100'000'000LL;              // 1e-8 SOST
inline constexpr int64_t SUPPLY_MAX_STOCKS = 466'920'160'910'299LL;      // ~4.669M SOST

// Consensus limits
inline constexpr int64_t  COINBASE_MATURITY         = 1000;
inline constexpr int32_t  MAX_TX_BYTES_CONSENSUS    = 100'000;
inline constexpr int32_t  MAX_BLOCK_BYTES_CONSENSUS = 1'000'000;
inline constexpr uint16_t MAX_INPUTS_CONSENSUS      = 256;
inline constexpr uint16_t MAX_OUTPUTS_CONSENSUS     = 256;

// Bond/Escrow activation — BOND_LOCK (0x10) and ESCROW_LOCK (0x11) become valid
// output types after this height. Before activation, R11 rejects them.
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_MAINNET = 5000;
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_TESTNET = 100;
inline constexpr int64_t  BOND_ACTIVATION_HEIGHT_DEV     = 1;

// Payload sizes for lock outputs
inline constexpr uint16_t BOND_LOCK_PAYLOAD_LEN   = 8;   // lock_until (uint64 LE)
inline constexpr uint16_t ESCROW_LOCK_PAYLOAD_LEN = 28;  // lock_until (8) + beneficiary_pkh (20)

// =========================================================================
// Gold Vault Governance — Consensus-level spending rules
// Activates at BOND_ACTIVATION_HEIGHT (5000). Before that, no restriction.
// =========================================================================

// Activation (same height as Bond/Escrow/Capsule)
inline constexpr int64_t  GV_GOVERNANCE_ACTIVATION = 5000;

// Signaling thresholds for large Gold Vault spends
inline constexpr int32_t  GV_THRESHOLD_EPOCH01  = 75;   // 75% in Epoch 0-1 (blocks 5000-263105)
inline constexpr int32_t  GV_THRESHOLD_EPOCH2   = 95;   // 95% in Epoch 2+ (blocks 263106+)
inline constexpr int32_t  GV_APPROVAL_WINDOW    = 288;  // ~48h voting window

// Foundation quality vote (expires at Epoch 2)
inline constexpr int32_t  GV_FOUNDATION_VOTE_PCT = 10;  // +10% equivalent signaling
// Foundation veto expires at FOUNDATION_VETO_EXPIRY_BLOCKS (263106) from proposals.h

// Monthly operational limit (no voting required below this)
inline constexpr int32_t  GV_MONTHLY_LIMIT_PCT  = 10;   // 10% of vault balance
inline constexpr int64_t  GV_MONTHLY_WINDOW     = 4320; // ~30 days at 10min/block

// Gold purchase payload marker
inline constexpr uint8_t  GV_PAYLOAD_GOLD_PURCHASE = 0x47; // 'G' — marks TX as gold purchase

} // namespace sost
