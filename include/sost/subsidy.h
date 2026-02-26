#pragma once
#include <cstdint>

namespace sost {

// Consensus-critical block subsidy in stocks (1e-8 SOST).
// Smooth epoch-based decay, purely integer & deterministic.
int64_t sost_subsidy_stocks(int64_t height);

} // namespace sost
