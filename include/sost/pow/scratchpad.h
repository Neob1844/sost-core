#pragma once
#include "sost/types.h"
#include "sost/params.h"
#include "sost/crypto.h"
#include <vector>

namespace sost {

// The `chain` parameter is optional to preserve compatibility with legacy tests and call sites.
Bytes32 epoch_scratch_key(int32_t epoch, const std::vector<BlockMeta>* chain = nullptr);

std::vector<uint8_t> build_scratchpad(const Bytes32& seed_key, int32_t scratch_mb);

// O(1) single-block scratchpad access (for verification without full scratchpad)
// Returns 32 bytes at block_index * 32.
Bytes32 compute_single_scratch_block(const Bytes32& seed_key, uint64_t block_index);

} // namespace sost
