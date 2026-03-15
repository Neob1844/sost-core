#include "sost/miner.h"
#include "sost/pow/casert.h"
#include <cstdio>
#include <cstring>
#include <chrono>
#include <ctime>

namespace sost {

MineResult mine_block(
    const std::vector<BlockMeta>& chain,
    const Bytes32& prev_hash,
    const Bytes32& merkle_root,
    int64_t timestamp,
    uint32_t powDiffQ,
    uint32_t max_nonce,
    uint32_t extra_nonce,  
    Profile prof)
{
    MineResult mr{};
    mr.found = false;
    mr.attempts = 0;

    int64_t h = (int64_t)chain.size();
    int32_t epoch = (int32_t)(h / BLOCKS_PER_EPOCH);

    ConsensusParams params = get_consensus_params(prof, h);
    auto cdec = casert_compute(chain, h, std::time(nullptr));
    params = casert_apply_profile(params, cdec);

    uint32_t expected = casert_next_bitsq(chain, h);
    if (powDiffQ != expected) {
        mr.error = "bad-difficulty";
        return mr;
    }

    Bytes32 skey = epoch_scratch_key(epoch, &chain);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);

    Bytes32 bk = compute_block_key(prev_hash);
    auto hc = build_header_core(prev_hash, merkle_root,
                                (uint32_t)timestamp, powDiffQ);

    auto t0 = std::chrono::steady_clock::now();

    for (uint32_t nonce = 0; nonce <= max_nonce; ++nonce) {
        mr.attempts++;

        auto res = convergencex_attempt(
            scratch.data(), scratch.size(), bk,
            nonce, extra_nonce,   
            params, hc.data(), epoch);

        if (res.is_stable && pow_meets_target(res.commit, powDiffQ)) {

            auto t1 = std::chrono::steady_clock::now();
            mr.elapsed_ms =
                std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

            mr.found = true;

            Block& b = mr.block;
            b.height = h;
            b.prev_hash = prev_hash;
            b.merkle_root = merkle_root;
            b.timestamp = timestamp;
            b.powDiffQ = powDiffQ;
            b.nonce = nonce;
            b.extra_nonce = extra_nonce;     
            b.commit = res.commit;
            b.checkpoints_root = res.checkpoints_root;
            b.stability_metric = res.stability_metric;
            b.x_bytes = res.x_bytes;
            b.subsidy_stocks = sost_subsidy_stocks(h);

            b.block_id = compute_block_id_from_parts(
                prev_hash,
                merkle_root,
                (uint32_t)timestamp,
                powDiffQ,
                res.checkpoints_root,
                nonce,
                extra_nonce,                
                res.commit);

            return mr;
        }
    }

    auto t1 = std::chrono::steady_clock::now();
    mr.elapsed_ms =
        std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

    mr.error = "exhausted-nonces";
    return mr;
}

int mine_chain(
    int32_t num_blocks,
    Profile prof,
    bool sim_time,
    uint32_t max_nonce,
    std::function<void(const Block&)> on_block)
{
    std::vector<BlockMeta> chain;

    Bytes32 prev{};
    prev.fill(0);

    Bytes32 mrkl{};
    mrkl.fill(0x11);

    int64_t ts = GENESIS_TIME;
    int64_t cw = 0;
    int32_t mined = 0;

    while (num_blocks == 0 || mined < num_blocks) {

        uint32_t powDiffQ =
            casert_next_bitsq(chain, (int64_t)chain.size());

        uint32_t extra = 0;
        bool found = false;

        while (!found) {

            auto mr = mine_block(
                chain, prev, mrkl, ts,
                powDiffQ,
                max_nonce,
                extra,          
                prof);

            if (mr.found) {

                found = true;
                mr.block.chainwork = cw;

                auto split =
                    coinbase_split(mr.block.subsidy_stocks);

                printf("[BLOCK %lld] id=%s nonce=%u extra=%u\n",
                    (long long)mr.block.height,
                    hex(mr.block.block_id).substr(0,16).c_str(),
                    mr.block.nonce,
                    mr.block.extra_nonce);

                auto vr = verify_block(
                    mr.block, chain, ts, prof, true);

                if (!vr.ok) {
                    printf("[VERIFY FAIL] %s\n", vr.reason.c_str());
                    return 1;
                }

                chain.push_back(to_meta(mr.block));
                prev = mr.block.block_id;

                if (on_block) on_block(mr.block);

                mined++;

                if (sim_time)
                    ts += TARGET_SPACING;
            }
            else {
                extra++;
                if (sim_time)
                    ts++;

                if (extra > 1000) {
                    printf("[FATAL] cannot find block after 1000 extra_nonce loops\n");
                    return 2;
                }
            }
        }
    }

    return 0;
}

} // namespace sost
