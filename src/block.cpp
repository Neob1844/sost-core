#include "sost/block.h"
#include <cstring>
namespace sost {

size_t full_header_len() {
    // MAGIC(10) + "HDR2"(4) + header_core(72) + cp_root(32) + nonce(4) + extra(4) = 126
    return MAGIC_LEN + 4 + HEADER_CORE_LEN + 32 + 4 + 4;
}

std::vector<uint8_t> serialize_full_header(
    const Bytes32& prev, const Bytes32& mrkl, uint32_t ts, uint32_t powDiffQ,
    const Bytes32& cp_root, uint32_t nonce, uint32_t extra_nonce)
{
    std::vector<uint8_t> hdr;
    hdr.reserve(full_header_len());
    // PY: full_header = MAGIC(10) + "HDR2"(4) + core(72) + cp_root(32) + nonce(4) + extra(4)
    // MAGIC already contains "CXPOW3" + NETWORK_ID
    append_magic(hdr);
    append(hdr, "HDR2", 4);
    auto hc = build_header_core(prev, mrkl, ts, powDiffQ);
    append(hdr, hc.data(), HEADER_CORE_LEN);
    append(hdr, cp_root);
    append_u32_le(hdr, nonce);
    append_u32_le(hdr, extra_nonce);
    return hdr;
}

Bytes32 compute_block_id_from_parts(
    const Bytes32& prev, const Bytes32& mrkl, uint32_t ts, uint32_t powDiffQ,
    const Bytes32& cp_root, uint32_t nonce, uint32_t extra_nonce,
    const Bytes32& commit)
{
    auto hdr = serialize_full_header(prev, mrkl, ts, powDiffQ, cp_root, nonce, extra_nonce);
    return compute_block_id(hdr.data(), hdr.size(), commit);
}

VerifyResult verify_block_basic(
    const Block& blk, const std::vector<BlockMeta>& chain, int64_t now, Profile prof)
{
    int64_t h = (int64_t)chain.size();
    // Prev-link
    if (!chain.empty()) {
        if (blk.prev_hash != chain.back().block_id)
            return {false, "prev-mismatch"};
    }
    // Subsidy
    int64_t expected_sub = sost_subsidy_stockshis(h);
    if (blk.subsidy_stockshis != expected_sub)
        return {false, "bad-subsidy"};
    // Timestamp
    auto [tok, tmsg] = validate_block_time(blk.timestamp, chain, now);
    if (!tok && !chain.empty())
        return {false, tmsg};
    // ASERT difficulty
    uint32_t expected_diff = asert_next_difficulty(chain, h);
    if (blk.powDiffQ != expected_diff)
        return {false, "bad-difficulty"};
    // Target bounds
    if (!valid_bitsQ(blk.powDiffQ))
        return {false, "invalid-bitsQ"};
    // Commit <= target
    if (!pow_meets_target(blk.commit, blk.powDiffQ))
        return {false, "pow-not-meeting-target"};
    return {true, "ok"};
}

VerifyResult verify_block_full(
    const Block& blk, const std::vector<BlockMeta>& chain, Profile prof)
{
    int64_t h = (int64_t)chain.size();
    int32_t epoch = (int32_t)(h / BLOCKS_PER_EPOCH);
    ConsensusParams params = get_consensus_params(prof, h);
    // CASERT overlay
    auto cdec = casert_mode_from_chain(chain, h);
    params = casert_apply_overlay(params, cdec.mode);
    // Scratchpad
    Bytes32 skey = epoch_scratch_key(epoch);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);
    // Recompute
    Bytes32 bk = compute_block_key(blk.prev_hash);
    auto hc = build_header_core(blk.prev_hash, blk.merkle_root,
                                (uint32_t)blk.timestamp, blk.powDiffQ);
    auto res = convergencex_attempt(
        scratch.data(), scratch.size(), bk,
        blk.nonce, blk.extra_nonce, params, hc.data(), epoch);
    if (res.commit != blk.commit)
        return {false, "commit-mismatch"};
    if (res.checkpoints_root != blk.checkpoints_root)
        return {false, "cp-root-mismatch"};
    if (res.stability_metric != blk.stability_metric)
        return {false, "metric-mismatch"};
    if (!res.is_stable)
        return {false, "solution-unstable"};
    // Block ID
    Bytes32 bid = compute_block_id_from_parts(
        blk.prev_hash, blk.merkle_root, (uint32_t)blk.timestamp, blk.powDiffQ,
        res.checkpoints_root, blk.nonce, blk.extra_nonce, res.commit);
    if (bid != blk.block_id)
        return {false, "block-id-mismatch"};
    return {true, "ok"};
}

VerifyResult verify_block(
    const Block& blk, const std::vector<BlockMeta>& chain,
    int64_t now, Profile prof, bool full)
{
    auto r = verify_block_basic(blk, chain, now, prof);
    if (!r.ok) return r;
    if (!full) return {true, "ok-basic"};
    return verify_block_full(blk, chain, prof);
}
} // namespace sost
