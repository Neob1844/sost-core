#include <sost/subsidy.h>

#include <cstdint>
#include <limits>
#include <algorithm>

namespace sost {

// ===== Consensus constants (from your spec) =====
static constexpr int64_t  BLOCKS_PER_EPOCH = 131'553;                 // round(52560 * alpha_years)
static constexpr uint64_t Q_DEN           = 10'000'000'000'000'000ULL; // 1e16
static constexpr uint64_t Q_NUM           =  7'788'007'830'714'049ULL; // floor(Q_DEN * exp(-1/4))
static constexpr int64_t  R0_STOCKS    = 785'100'863LL;            // initial reward (height 0)

static inline uint64_t mul_q(uint64_t a, uint64_t b) {
    // floor((a*b)/Q_DEN) using __int128, deterministic
    __int128 prod = ( __int128)a * ( __int128)b;
    prod /= ( __int128)Q_DEN;
    if (prod < 0) return 0;
    if (prod > ( __int128)std::numeric_limits<uint64_t>::max())
        return std::numeric_limits<uint64_t>::max();
    return (uint64_t)prod;
}

static inline uint64_t pow_q(uint64_t exp) {
    // Returns q^exp in Q_DEN fixed-point (i.e., scaled by Q_DEN).
    // Start at 1.0 in Q space: Q_DEN
    uint64_t result = Q_DEN;
    uint64_t base   = Q_NUM;

    while (exp > 0) {
        if (exp & 1ULL) result = mul_q(result, base);
        exp >>= 1ULL;
        if (exp) base = mul_q(base, base);
        else break;
    }
    return result;
}

// Hard cap: total cumulative emission must never exceed SUPPLY_MAX_STOCKS.
// When the epoch-based formula would cause overshoot, subsidy is reduced
// to the remaining amount. When supply = max, subsidy = 0 (fees only).
static constexpr int64_t SUPPLY_CAP = 466'920'160'910'299LL; // ~4,669,201 SOST

// Compute cumulative emission through end of given height (sum of all subsidies 0..height).
// Uses the closed-form: sum = R0 * (1 - q^(E+1)) / (1 - q) * BLOCKS_PER_EPOCH
// approximated by iterating epochs up to height.
static int64_t cumulative_emission(int64_t height) {
    if (height < 0) return 0;
    int64_t total = 0;
    int64_t h = 0;
    while (h <= height) {
        uint64_t epoch = (uint64_t)(h / BLOCKS_PER_EPOCH);
        uint64_t qpow = pow_q(epoch);
        __int128 r = (__int128)R0_STOCKS * (__int128)qpow;
        r /= (__int128)Q_DEN;
        int64_t sub = (r < 0) ? 0 : (int64_t)r;

        // Remaining blocks in this epoch
        int64_t epoch_end = (int64_t)((epoch + 1) * BLOCKS_PER_EPOCH - 1);
        int64_t blocks_in_epoch = std::min(epoch_end, height) - h + 1;
        total += sub * blocks_in_epoch;
        if (total >= SUPPLY_CAP) return SUPPLY_CAP;
        h += blocks_in_epoch;
    }
    return total;
}

int64_t sost_subsidy_stocks(int64_t height) {
    if (height < 0) return 0;

    // epoch = height / BLOCKS_PER_EPOCH
    uint64_t epoch = (uint64_t)(height / BLOCKS_PER_EPOCH);

    // reward = floor(R0 * q^epoch)
    uint64_t qpow = pow_q(epoch); // scaled by Q_DEN

    __int128 r = ( __int128)R0_STOCKS * ( __int128)qpow;
    r /= ( __int128)Q_DEN;

    if (r < 0) return 0;
    if (r > ( __int128)std::numeric_limits<int64_t>::max())
        return std::numeric_limits<int64_t>::max();

    int64_t base_subsidy = (int64_t)r;

    // Hard cap enforcement: check if this subsidy would exceed max supply
    int64_t emitted_before = cumulative_emission(height - 1);
    if (emitted_before >= SUPPLY_CAP) return 0; // supply exhausted, fees only
    int64_t remaining = SUPPLY_CAP - emitted_before;
    if (base_subsidy > remaining) return remaining; // partial final subsidy

    return base_subsidy;
}

} // namespace sost
