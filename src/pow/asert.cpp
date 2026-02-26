#include "sost/asert.h"
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
    auto prev_powDiffQ = chain.back().powDiffQ;
    auto prev_time = chain.back().time;
    int64_t epoch = next_height / BLOCKS_PER_EPOCH;
    size_t anchor_idx = 0;
    if (epoch > 0) {
        int64_t ai = epoch * BLOCKS_PER_EPOCH - 1;
        anchor_idx = (size_t)std::max<int64_t>(0, std::min<int64_t>(ai, (int64_t)chain.size()-1));
    }
    auto anchor_time = chain[anchor_idx].time;
    auto anchor_powDiffQ = chain[anchor_idx].powDiffQ ? chain[anchor_idx].powDiffQ : prev_powDiffQ;
    int64_t parent_idx = (int64_t)chain.size()-1;
    int64_t expected_pt = anchor_time + (parent_idx-(int64_t)anchor_idx)*TARGET_SPACING;
    int64_t td = prev_time - expected_pt;
    int64_t adj = (td*(int64_t)Q16_ONE)/ASERT_HALF_LIFE;
    int64_t unc = (int64_t)anchor_powDiffQ - adj;
    int64_t dc = (int64_t)prev_powDiffQ - (int64_t)Q16_ONE*ASERT_DOWN_STEPS;
    int64_t uc = (int64_t)prev_powDiffQ + (int64_t)Q16_ONE*ASERT_UP_STEPS;
    int64_t r = std::max(dc, std::min(unc, uc));
    r = std::max<int64_t>((int64_t)MIN_BITSQ, std::min<int64_t>((int64_t)MAX_BITSQ, r));
    return (uint32_t)r;
}
} // namespace sost
