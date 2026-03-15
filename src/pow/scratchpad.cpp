// src/scratchpad.cpp (Python-aligned)
// - Epoch key derivation matches Python reference:
//   epoch 0: chain-independent
//   epoch > 0: if chain has anchor at (epoch*BLOCKS_PER_EPOCH - 1), bind to that block_id
//
// NOTE: `chain` is optional to preserve compatibility with legacy tests/call sites.

#include "sost/pow/scratchpad.h"
#include "sost/serialize.h"
#include <cstring>
#include <algorithm>

namespace sost {

Bytes32 epoch_scratch_key(int32_t epoch, const std::vector<BlockMeta>* chain) {
    // Defensive normalization (Python treats negative epoch as invalid; we fail-closed to 0)
    if (epoch < 0) epoch = 0;

    // Python truth:
    // - Base: sha256(MAGIC || "EPOCH" || u32(epoch))
    // - If epoch > 0 and chain has anchor block at idx = epoch*BPE - 1:
    //     sha256(MAGIC || "EPOCH" || u32(epoch) || anchor.block_id)
    if (chain && epoch > 0) {
        const int64_t idx64 = (int64_t)epoch * (int64_t)BLOCKS_PER_EPOCH - 1;
        if (idx64 >= 0 && idx64 < (int64_t)chain->size()) {
            const Bytes32& anchor_id = (*chain)[(size_t)idx64].block_id;

            std::vector<uint8_t> buf;
            append_magic(buf);
            append(buf, "EPOCH", 5);                 // "EPOCH" (5 bytes) — match Python
            append_u32_le(buf, (uint32_t)epoch);
            append(buf, anchor_id);
            return sha256(buf);
        }
    }

    // Epoch 0 (or missing anchor): chain-independent key
    std::vector<uint8_t> buf;
    append_magic(buf);
    append(buf, "EPOCH", 5);                         // "EPOCH" (5 bytes) — match Python
    append_u32_le(buf, (uint32_t)epoch);
    return sha256(buf);
}

// V2 scratchpad: each 32-byte block is independently derivable.
// Miner builds full scratchpad for speed; verifier recomputes individual blocks.
// block[i] = SHA256(MAGIC || "SCR2" || seed_key || u64_le(i))

Bytes32 compute_single_scratch_block(const Bytes32& seed_key, uint64_t block_index) {
    std::vector<uint8_t> buf;
    append_magic(buf);
    append(buf, "SCR2", 4);
    append(buf, seed_key);
    uint8_t idx_le[8];
    for (int i = 0; i < 8; ++i) idx_le[i] = (uint8_t)((block_index >> (i * 8)) & 0xFF);
    append(buf, idx_le, 8);
    return sha256(buf);
}

std::vector<uint8_t> build_scratchpad(const Bytes32& seed_key, int32_t scratch_mb) {
    if (scratch_mb <= 0) scratch_mb = 1;

    size_t nbytes = (size_t)scratch_mb * 1024 * 1024;
    if (nbytes < 8) nbytes = 8;

    std::vector<uint8_t> out(nbytes);
    size_t num_blocks = (nbytes + 31) / 32;

    for (size_t i = 0; i < num_blocks; ++i) {
        Bytes32 block = compute_single_scratch_block(seed_key, (uint64_t)i);
        size_t pos = i * 32;
        size_t take = std::min<size_t>(32, nbytes - pos);
        std::memcpy(out.data() + pos, block.data(), take);
    }

    return out;
}

} // namespace sost
