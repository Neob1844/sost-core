#pragma once
#include "types.h"
#include "params.h"
#include <vector>
#include <utility>
namespace sost {
uint32_t asert_next_difficulty(const std::vector<BlockMeta>& chain, int64_t next_height);
int64_t median_time_past(const std::vector<BlockMeta>& chain, int32_t window = MTP_WINDOW);
std::pair<bool, const char*> validate_block_time(
    int64_t block_time, const std::vector<BlockMeta>& chain, int64_t current_time);
} // namespace sost
