#include "sost/pow/asert.h"
#include <algorithm>
namespace sost {
int64_t median_time_past(const std::vector<BlockMeta>& chain, int32_t window) {
    if (chain.empty()) return 0;
    size_t take = std::min<size_t>(chain.size(), (size_t)window);
    std::vector<int64_t> times; times.reserve(take);
    for (size_t i = chain.size()-take; i < chain.size(); ++i) times.push_back(chain[i].time);
    std::sort(times.begin(), times.end());
    return times[times.size()/2];
}
std::pair<bool, const char*> validate_block_time(
    int64_t bt, const std::vector<BlockMeta>& chain, int64_t now) {
    int64_t mtp = median_time_past(chain);
    if (!chain.empty() && bt <= mtp) return {false, "time-too-old"};
    if (bt > now + MAX_FUTURE_DRIFT) return {false, "time-too-new"};
    return {true, "ok"};
}
uint32_t asert_next_difficulty(const std::vector<BlockMeta>& chain, int64_t next_height) {
    if (chain.empty() || next_height <= 0) return GENESIS_BITSQ;

    // Anchor: first block of current epoch (genesis for epoch 0)
    int64_t epoch = next_height / BLOCKS_PER_EPOCH;
    size_t anchor_idx = 0;
    if (epoch > 0) {
        int64_t ai = epoch * BLOCKS_PER_EPOCH - 1;
        anchor_idx = (size_t)std::max<int64_t>(0, std::min<int64_t>(ai, (int64_t)chain.size()-1));
    }
    auto anchor_time = chain[anchor_idx].time;
    auto anchor_bitsq = chain[anchor_idx].powDiffQ ? chain[anchor_idx].powDiffQ : GENESIS_BITSQ;

    // Time delta: negative when blocks arrive faster than target
    int64_t parent_idx = (int64_t)chain.size() - 1;
    int64_t expected_pt = anchor_time + (parent_idx - (int64_t)anchor_idx) * TARGET_SPACING;
    int64_t td = chain.back().time - expected_pt;

    // Exponential ASERT: next_bitsq = anchor_bitsq * 2^(-td / halflife)
    // Exponent in Q16.16: when td < 0 (fast), exponent > 0, difficulty rises
    int64_t exponent = ((-td) * (int64_t)Q16_ONE) / ASERT_HALF_LIFE;

    // Decompose into integer shifts and Q0.16 fractional part
    // Arithmetic right shift gives floor division for negative values
    int32_t shifts = (int32_t)(exponent >> 16);
    uint32_t frac = (uint32_t)(exponent & 0xFFFF);

    // Compute 2^frac via cubic polynomial (Horner's form)
    // 2^x ≈ 1 + x·ln2 + x²·ln2²/2 + x³·ln2³/6  for x ∈ [0,1)
    // Constants in Q0.16: ln2=45426, ln2²/2=15743, ln2³/6=3638
    int64_t x = (int64_t)frac;
    int64_t t = 3638;                       // c3
    t = 15743 + ((t * x) >> 16);            // c2 + c3·x
    t = 45426 + ((t * x) >> 16);            // c1 + (c2 + c3·x)·x
    int64_t factor = (int64_t)Q16_ONE + ((t * x) >> 16);  // 2^frac in Q16.16

    // result = anchor_bitsq * 2^frac  (divide by Q16_ONE to leave Q16.16 space)
    int64_t result = ((int64_t)anchor_bitsq * factor) >> 16;

    // Apply integer power-of-two shifts
    if (shifts > 0) {
        if (shifts > 24) result = (int64_t)MAX_BITSQ;
        else             result <<= shifts;
    } else if (shifts < 0) {
        int32_t rshifts = -shifts;
        if (rshifts > 24) result = 0;
        else              result >>= rshifts;
    }

    // Global clamp
    result = std::max<int64_t>((int64_t)MIN_BITSQ, std::min<int64_t>((int64_t)MAX_BITSQ, result));
    return (uint32_t)result;
}
} // namespace sost
