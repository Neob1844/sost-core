#pragma once
#include "types.h"
#include "params.h"
#include "crypto.h"
#include <vector>
namespace sost {
Bytes32 epoch_scratch_key(int32_t epoch);
std::vector<uint8_t> build_scratchpad(const Bytes32& seed_key, int32_t scratch_mb);
} // namespace sost
