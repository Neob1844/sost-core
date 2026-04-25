#pragma once
/**
 * SOST — Automatic Adaptive Anti-Spam Shield
 *
 * Fully automatic, no manual activation needed.
 * Monitors mempool pressure and adjusts relay policy in real-time.
 *
 * Levels: GREEN → YELLOW → ORANGE → RED → BLACK
 * Hysteresis: fast to harden, slow to relax.
 * Emergency: BLACK escalates 250x → 1000x → 5000x automatically.
 *
 * Policy-only — does NOT change block validity or consensus rules.
 */

#include <sost/params.h>
#include <cstdint>
#include <string>
#include <chrono>

namespace sost {

enum class SpamLevel : int {
    GREEN  = 0,
    YELLOW = 1,
    ORANGE = 2,
    RED    = 3,
    BLACK  = 4,
};

struct SpamGuardState {
    SpamLevel level{SpamLevel::GREEN};
    int32_t   pressure_score{0};          // 0-100
    int64_t   relay_floor_multiplier{1};  // effective multiplier
    int64_t   effective_relay_floor{1};   // stocks/byte
    size_t    peer_tx_limit{30};          // tx/peer/min
    size_t    addr_tx_limit{25};          // tx/addr in mempool
    int64_t   black_entered_at{0};        // unix time when BLACK started
    int32_t   escalation_ticks{0};        // consecutive ticks above threshold
    int64_t   last_level_change{0};       // unix time

    std::string level_name() const {
        switch (level) {
            case SpamLevel::GREEN:  return "GREEN";
            case SpamLevel::YELLOW: return "YELLOW";
            case SpamLevel::ORANGE: return "ORANGE";
            case SpamLevel::RED:    return "RED";
            case SpamLevel::BLACK:  return "BLACK";
        }
        return "UNKNOWN";
    }
};

struct MempoolMetrics {
    size_t  total_tx{0};
    size_t  max_entries{5000};
    double  fill_ratio{0.0};        // 0.0-1.0
    double  low_fee_ratio{0.0};     // % of tx near floor
    double  tx_per_min_1m{0.0};     // arrival rate last 1 min
    double  tx_per_min_5m{0.0};     // arrival rate last 5 min
    int32_t rbf_churn_1m{0};        // replacements last 1 min
    double  peer_concentration{0.0}; // 0-1: how concentrated across peers
    int32_t reject_rate_1m{0};      // rejections last 1 min
};

class SpamGuard {
public:
    SpamGuard() = default;

    // Main tick — call periodically (e.g. every 10s) with current metrics
    void tick(const MempoolMetrics& metrics, int64_t chain_height);

    // Get current state
    const SpamGuardState& state() const { return state_; }

    // Get effective relay floor for this chain height
    int64_t effective_relay_floor(int64_t chain_height) const;

    // Get current limits
    size_t peer_tx_limit() const { return state_.peer_tx_limit; }
    size_t addr_tx_limit() const { return state_.addr_tx_limit; }

private:
    SpamGuardState state_;

    int32_t compute_pressure(const MempoolMetrics& m) const;
    SpamLevel score_to_level(int32_t score) const;
    void apply_level(SpamLevel new_level, int64_t now);
    void escalate_black(int64_t now);
};

} // namespace sost
