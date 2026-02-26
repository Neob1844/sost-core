#pragma once
#include "block.h"
#include <vector>
#include <functional>

namespace sost {

struct MineResult {
    bool found;
    Block block;
    int64_t elapsed_ms;
    uint32_t attempts;
    std::string error;
};

// Mine a single block
MineResult mine_block(
    const std::vector<BlockMeta>& chain,
    const Bytes32& prev_hash,
    const Bytes32& merkle_root,
    int64_t timestamp,
    uint32_t powDiffQ,
    uint32_t max_nonce,
    uint32_t extra_nonce,
    Profile prof);

// Mine a chain of blocks (integration miner)
int mine_chain(
    int32_t num_blocks, // 0 = infinite
    Profile prof,
    bool sim_time = true,
    uint32_t max_nonce = 500000,
    std::function<void(const Block&)> on_block = nullptr);

} // namespace sost
