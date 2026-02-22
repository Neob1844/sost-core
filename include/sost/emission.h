#pragma once
#include "types.h"
#include "params.h"
namespace sost {
int64_t sost_subsidy_stockshis(int64_t height);
CoinbaseSplit coinbase_split(int64_t reward);
inline int64_t epoch_from_height(int64_t h) { return (h >= 0) ? h / BLOCKS_PER_EPOCH : 0; }
ConsensusParams get_consensus_params(Profile profile, int64_t height);
} // namespace sost
