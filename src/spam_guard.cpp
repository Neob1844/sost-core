/**
 * SOST — Automatic Adaptive Anti-Spam Shield
 *
 * Fully automatic. No manual activation.
 * Policy-only (not consensus).
 */

#include <sost/spam_guard.h>
#include <algorithm>
#include <ctime>

namespace sost {

// ── Pressure Score Calculation ──────────────────────────────────

int32_t SpamGuard::compute_pressure(const MempoolMetrics& m) const {
    // Weighted score 0-100
    double score = 0.0;

    // 1. Mempool fill ratio (0-30 points)
    score += m.fill_ratio * 30.0;

    // 2. TX arrival rate (0-25 points)
    // Normalize: >50 tx/min = high pressure
    score += std::min(25.0, m.tx_per_min_1m / 2.0);

    // 3. Low-fee ratio (0-15 points)
    // Many tx near the floor = spam signal
    score += m.low_fee_ratio * 15.0;

    // 4. RBF churn (0-10 points)
    score += std::min(10.0, (double)m.rbf_churn_1m);

    // 5. Peer concentration (0-10 points)
    // If most tx come from 1-2 peers = suspicious
    score += m.peer_concentration * 10.0;

    // 6. Reject rate (0-10 points)
    // High reject rate = someone testing limits
    score += std::min(10.0, (double)m.reject_rate_1m / 5.0);

    return std::min(100, std::max(0, (int32_t)score));
}

// ── Level Selection ─────────────────────────────────────────────

SpamLevel SpamGuard::score_to_level(int32_t score) const {
    if (score >= SPAM_LEVEL_BLACK)  return SpamLevel::BLACK;
    if (score >= SPAM_LEVEL_RED)    return SpamLevel::RED;
    if (score >= SPAM_LEVEL_ORANGE) return SpamLevel::ORANGE;
    if (score >= SPAM_LEVEL_YELLOW) return SpamLevel::YELLOW;
    return SpamLevel::GREEN;
}

// ── Apply Level ─────────────────────────────────────────────────

void SpamGuard::apply_level(SpamLevel new_level, int64_t now) {
    state_.level = new_level;
    state_.last_level_change = now;

    switch (new_level) {
        case SpamLevel::GREEN:
            state_.relay_floor_multiplier = SPAM_MULT_GREEN;
            state_.peer_tx_limit = SPAM_PEER_LIMIT_GREEN;
            state_.addr_tx_limit = SPAM_ADDR_LIMIT_GREEN;
            state_.black_entered_at = 0;
            break;
        case SpamLevel::YELLOW:
            state_.relay_floor_multiplier = SPAM_MULT_YELLOW;
            state_.peer_tx_limit = SPAM_PEER_LIMIT_YELLOW;
            state_.addr_tx_limit = SPAM_ADDR_LIMIT_YELLOW;
            state_.black_entered_at = 0;
            break;
        case SpamLevel::ORANGE:
            state_.relay_floor_multiplier = SPAM_MULT_ORANGE;
            state_.peer_tx_limit = SPAM_PEER_LIMIT_ORANGE;
            state_.addr_tx_limit = SPAM_ADDR_LIMIT_ORANGE;
            state_.black_entered_at = 0;
            break;
        case SpamLevel::RED:
            state_.relay_floor_multiplier = SPAM_MULT_RED;
            state_.peer_tx_limit = SPAM_PEER_LIMIT_RED;
            state_.addr_tx_limit = SPAM_ADDR_LIMIT_RED;
            state_.black_entered_at = 0;
            break;
        case SpamLevel::BLACK:
            state_.relay_floor_multiplier = SPAM_MULT_BLACK; // 250x initial
            state_.peer_tx_limit = SPAM_PEER_LIMIT_BLACK;
            state_.addr_tx_limit = SPAM_ADDR_LIMIT_BLACK;
            if (state_.black_entered_at == 0)
                state_.black_entered_at = now;
            break;
    }

    state_.effective_relay_floor = DYNAMIC_FEE_BASE * state_.relay_floor_multiplier;
}

// ── BLACK Escalation ────────────────────────────────────────────

void SpamGuard::escalate_black(int64_t now) {
    if (state_.level != SpamLevel::BLACK || state_.black_entered_at == 0) return;

    int64_t in_black = now - state_.black_entered_at;

    if (in_black >= SPAM_BLACK_ESCALATE_15MIN) {
        // 15+ min in BLACK → 5000x
        state_.relay_floor_multiplier = DYNAMIC_FEE_EMERGENCY_5000X;
    } else if (in_black >= SPAM_BLACK_ESCALATE_5MIN) {
        // 5+ min in BLACK → 1000x
        state_.relay_floor_multiplier = DYNAMIC_FEE_EMERGENCY_1000X;
    }
    // else stays at 250x (initial BLACK)

    state_.effective_relay_floor = DYNAMIC_FEE_BASE * state_.relay_floor_multiplier;
}

// ── Main Tick ───────────────────────────────────────────────────

void SpamGuard::tick(const MempoolMetrics& metrics, int64_t chain_height) {
    // Before activation height: do nothing
    if (chain_height < DYNAMIC_FEE_ACTIVATION_HEIGHT) {
        state_.pressure_score = 0;
        state_.level = SpamLevel::GREEN;
        state_.relay_floor_multiplier = 1;
        state_.effective_relay_floor = DYNAMIC_FEE_BASE;
        state_.peer_tx_limit = SPAM_PEER_LIMIT_GREEN;
        state_.addr_tx_limit = SPAM_ADDR_LIMIT_GREEN;
        return;
    }

    int64_t now = std::time(nullptr);
    int32_t score = compute_pressure(metrics);
    state_.pressure_score = score;

    SpamLevel target = score_to_level(score);

    // ESCALATION: fast (2 consecutive ticks above threshold)
    if ((int)target > (int)state_.level) {
        state_.escalation_ticks++;
        if (state_.escalation_ticks >= SPAM_ESCALATION_TICKS) {
            apply_level(target, now);
            state_.escalation_ticks = 0;
        }
    }
    // RELAXATION: slow (must stay below for SPAM_RELAXATION_SECONDS)
    else if ((int)target < (int)state_.level) {
        state_.escalation_ticks = 0;
        int64_t time_in_level = now - state_.last_level_change;
        if (time_in_level >= SPAM_RELAXATION_SECONDS) {
            // Drop one level at a time (gradual relaxation)
            int new_lvl = std::max((int)target, (int)state_.level - 1);
            apply_level((SpamLevel)new_lvl, now);
        }
    }
    // SAME LEVEL: reset escalation counter
    else {
        state_.escalation_ticks = 0;
    }

    // BLACK escalation (250x → 1000x → 5000x)
    if (state_.level == SpamLevel::BLACK) {
        escalate_black(now);
    }
}

// ── Effective Relay Floor ───────────────────────────────────────

int64_t SpamGuard::effective_relay_floor(int64_t chain_height) const {
    if (chain_height < DYNAMIC_FEE_ACTIVATION_HEIGHT) {
        return DYNAMIC_FEE_BASE;
    }
    return state_.effective_relay_floor;
}

} // namespace sost
