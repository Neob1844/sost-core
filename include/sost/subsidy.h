#pragma once
#include <cstdint>

namespace sost {

// Consensus-critical block subsidy in stockshis (1e-8 SOST).
// Smooth epoch-based decay, purely integer & deterministic.
int64_t sost_subsidy_stockshis(int64_t height);

} // namespace sost
