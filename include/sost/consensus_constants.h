#pragma once
#include <cstdint>
#include <cstddef>

namespace sost {

inline constexpr int64_t STOCKSHIS_PER_SOST = 100'000'000LL;
inline constexpr int64_t SUPPLY_MAX_STOCKSHIS = 466'920'160'910'299LL;

inline constexpr int64_t  COINBASE_MATURITY         = 100;
inline constexpr int32_t  MAX_TX_BYTES_CONSENSUS    = 100'000;
inline constexpr int32_t  MAX_BLOCK_BYTES_CONSENSUS = 1'000'000;
inline constexpr uint16_t MAX_INPUTS_CONSENSUS      = 256;
inline constexpr uint16_t MAX_OUTPUTS_CONSENSUS     = 256;

} // namespace sost
