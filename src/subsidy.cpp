#include <sost/subsidy.h>

#include <cstdint>
#include <limits>

namespace sost {

// ===== Consensus constants (from your spec) =====
static constexpr int64_t  BLOCKS_PER_EPOCH = 131'553;                 // round(52560 * alpha_years)
static constexpr uint64_t Q_DEN           = 10'000'000'000'000'000ULL; // 1e16
static constexpr uint64_t Q_NUM           =  7'788'007'830'714'049ULL; // floor(Q_DEN * exp(-1/4))
static constexpr int64_t  R0_STOCKSHIS    = 785'100'863LL;            // initial reward (height 0)

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

int64_t sost_subsidy_stockshis(int64_t height) {
    if (height < 0) return 0;

    // epoch = height / BLOCKS_PER_EPOCH
    uint64_t epoch = (uint64_t)(height / BLOCKS_PER_EPOCH);

    // reward = floor(R0 * q^epoch)
    uint64_t qpow = pow_q(epoch); // scaled by Q_DEN

    __int128 r = ( __int128)R0_STOCKSHIS * ( __int128)qpow;
    r /= ( __int128)Q_DEN;

    if (r < 0) return 0;
    if (r > ( __int128)std::numeric_limits<int64_t>::max())
        return std::numeric_limits<int64_t>::max();

    return (int64_t)r;
}

} // namespace sost
