#pragma once
#include <cstdint>

namespace sost {

// Consensus-critical block subsidy in stocks (1e-8 SOST).
// Smooth epoch-based decay, purely integer & deterministic.
int64_t sost_subsidy_stocks(int64_t height);

// Cumulative emitted supply (stocks) through `height` inclusive: sum of all
// block subsidies 0..height with the SUPPLY_CAP applied. Read-only accessor
// used by the getsupplyinfo RPC so app/explorer share one source of truth.
int64_t sost_cumulative_emission_stocks(int64_t height);

} // namespace sost
