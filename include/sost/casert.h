#pragma once
#include "types.h"
#include "params.h"
#include <vector>
namespace sost {
CasertDecision casert_mode_from_chain(const std::vector<BlockMeta>& chain, int64_t next_height);
ConsensusParams casert_apply_overlay(const ConsensusParams& base, CasertMode mode);
} // namespace sost
