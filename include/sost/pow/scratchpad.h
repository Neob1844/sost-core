#pragma once
#include "sost/types.h"
#include "sost/params.h"
#include "sost/crypto.h"
#include <vector>

namespace sost {

// The `chain` parameter is optional to preserve compatibility with legacy tests and call sites.
Bytes32 epoch_scratch_key(int32_t epoch, const std::vector<BlockMeta>* chain = nullptr);

std::vector<uint8_t> build_scratchpad(const Bytes32& seed_key, int32_t scratch_mb);

} // namespace sost
