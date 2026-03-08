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

} // namespace sost
