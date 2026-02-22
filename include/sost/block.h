#pragma once
#include "types.h"
#include "params.h"
#include "serialize.h"
#include "crypto.h"
#include "convergencex.h"
#include "emission.h"
#include "asert.h"
#include "casert.h"
#include "sostcompact.h"
#include "scratchpad.h"
#include <vector>
#include <string>
namespace sost {

size_t full_header_len();

std::vector<uint8_t> serialize_full_header(
    const Bytes32& prev, const Bytes32& mrkl, uint32_t ts, uint32_t powDiffQ,
    const Bytes32& cp_root, uint32_t nonce, uint32_t extra_nonce);

Bytes32 compute_block_id_from_parts(
    const Bytes32& prev, const Bytes32& mrkl, uint32_t ts, uint32_t powDiffQ,
    const Bytes32& cp_root, uint32_t nonce, uint32_t extra_nonce,
    const Bytes32& commit);

struct Block {
    int64_t height;
    Bytes32 prev_hash, merkle_root, block_id, commit, checkpoints_root;
    uint32_t powDiffQ, nonce, extra_nonce;
    int64_t timestamp;
    uint64_t stability_metric;
    int64_t subsidy_stockshis;
    int64_t chainwork;
    std::vector<uint8_t> x_bytes;
};

struct VerifyResult { bool ok; std::string reason; };

VerifyResult verify_block_basic(
    const Block& blk, const std::vector<BlockMeta>& chain, int64_t now, Profile prof);
VerifyResult verify_block_full(
    const Block& blk, const std::vector<BlockMeta>& chain, Profile prof);
VerifyResult verify_block(
    const Block& blk, const std::vector<BlockMeta>& chain,
    int64_t now, Profile prof, bool full = true);

inline BlockMeta to_meta(const Block& b) {
    return {b.block_id, b.height, b.timestamp, b.powDiffQ};
}
} // namespace sost
