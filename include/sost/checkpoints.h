// SOST Protocol — Copyright (c) 2026 SOST Foundation
// MIT License. See LICENSE file.
#pragma once
#include <string>
#include <vector>
#include <cstdint>

namespace sost {

struct SyncCheckpoint {
    uint32_t height;
    std::string block_hash;
};

// Hardcoded checkpoints verified by the development team.
// Blocks at or below LAST_CHECKPOINT_HEIGHT can skip full
// ConvergenceX recomputation during initial sync.
// Header, timestamp, difficulty, target, coinbase split,
// and UTXO updates are ALWAYS verified regardless.
//
// To force full verification: --full-verify
//
// Empty at genesis. Updated with each source release.
static const std::vector<SyncCheckpoint> SYNC_CHECKPOINTS = {
    // {height, "block_hash_hex"},
    // Example (do NOT add until blocks exist):
    // {1000, "abc123..."},
};

static const uint32_t LAST_CHECKPOINT_HEIGHT = 0;

// Returns true if the given height+hash matches a checkpoint
inline bool is_checkpointed(uint32_t height,
                             const std::string& hash) {
    if (height > LAST_CHECKPOINT_HEIGHT) return false;
    for (const auto& cp : SYNC_CHECKPOINTS) {
        if (cp.height == height && cp.block_hash == hash) {
            return true;
        }
    }
    // Blocks below last checkpoint but not in the list:
    // Also skip full verify (trusted range)
    return (height <= LAST_CHECKPOINT_HEIGHT &&
            LAST_CHECKPOINT_HEIGHT > 0);
}

} // namespace sost
