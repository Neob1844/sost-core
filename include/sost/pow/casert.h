#pragma once
#include "sost/types.h"
#include "sost/params.h"
#include <vector>
namespace sost {
CasertDecision casert_mode_from_chain(const std::vector<BlockMeta>& chain, int64_t next_height);
ConsensusParams casert_apply_overlay(const ConsensusParams& base, const CasertDecision& dec);
} // namespace sost
