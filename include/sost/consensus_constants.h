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

} // namespace sost
