// src/genesis.cpp — SOST Genesis Miner (Phase 5+ compatible)
// Builds a ConvergenceX genesis using the CURRENT headers:
// - types.h (Bytes32, ConsensusParams, CXAttemptResult)
// - pow/convergencex.h (convergencex_attempt, compute_block_key, compute_block_id)
// - pow/scratchpad.h (epoch_scratch_key, build_scratchpad)
// - block_validation.h (GENESIS_TIMESTAMP, GENESIS_BITSQ)
// - sostcompact.h (pow_meets_target)
//
// NOTE:
// This executable mines the ConvergenceX "candidate" (commit/checkpoints_root)
// and emits genesis_block.json with the values needed as chainparams anchor.

#include "sost/types.h"
#include "sost/block_validation.h"
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/sostcompact.h"
#include "sost/serialize.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <thread>
#include <vector>
#include <string>

using namespace sost;

static CoinbaseSplit coinbase_split_50_25_25(int64_t subsidy_stocks) {
    CoinbaseSplit s{};
    s.gold_vault = subsidy_stocks / 4;
    s.popc_pool  = subsidy_stocks / 4;
    s.miner      = subsidy_stocks - s.gold_vault - s.popc_pool; // absorbs rounding
    s.total      = subsidy_stocks;
    return s;
}

// Build the 72-byte header_core exactly like Python: <32s32sII (LE)
static void build_header_core_72(uint8_t out72[72],
                                const Bytes32& prev_hash,
                                const Bytes32& merkle_root,
                                uint32_t ts_u32,
                                uint32_t powDiffQ_u32)
{
    // prev(32) || mrkl(32) || ts(4 LE) || powDiffQ(4 LE)
    std::memcpy(out72 + 0,  prev_hash.data(),   32);
    std::memcpy(out72 + 32, merkle_root.data(), 32);
    write_u32_le(out72 + 64, ts_u32);
    write_u32_le(out72 + 68, powDiffQ_u32);
}

// Full header bytes used by ConvergenceX block_id in your Python reference:
// MAGIC || "HDR2" || header_core(72) || checkpoints_root(32) || nonce_u32 || extra_u32
static std::vector<uint8_t> build_full_header_bytes(const uint8_t header_core72[72],
                                                    const Bytes32& checkpoints_root,
                                                    uint32_t nonce_u32,
                                                    uint32_t extra_u32)
{
    std::vector<uint8_t> buf;
    buf.reserve(10 + 4 + 72 + 32 + 4 + 4);

    append_magic(buf);               // MUST match the network magic used elsewhere
    append(buf, "HDR2", 4);
    append(buf, header_core72, 72);
    append(buf, checkpoints_root);
    append_u32_le(buf, nonce_u32);
    append_u32_le(buf, extra_u32);

    return buf;
}

static void usage(const char* argv0) {
    std::printf(
        "Usage: %s [--now] [--max-nonce N] [--extra X] [--mrkl-11|--mrkl-00] [--scratch-mb M] [--rounds R]\n"
        "\n"
        "Defaults:\n"
        "  timestamp   = GENESIS_TIMESTAMP (%lld)\n"
        "  bitsQ       = GENESIS_BITSQ (%u)\n"
        "  mrkl        = 0x11..11 (recommended, matches python default)\n"
        "  max_nonce   = 10000000\n"
        "  extra       = 0\n"
        "  scratch_mb  = 4096\n"
        "  rounds      = 100000\n",
        argv0,
        (long long)GENESIS_TIMESTAMP,
        (unsigned)GENESIS_BITSQ
    );
}

int main(int argc, char** argv) {
    // CRITICAL: Set profile before any function that uses append_magic()
    ACTIVE_PROFILE = Profile::MAINNET;

    bool now = false;
    uint32_t max_nonce = 10'000'000;
    uint32_t extra_nonce = 0;
    bool mrkl_11 = true;

    // Mainnet defaults (match your python narrative)
    int32_t scratch_mb = 4096;
    int32_t rounds = 100000;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--now") now = true;
        else if (a == "--max-nonce" && i + 1 < argc) max_nonce = (uint32_t)std::strtoul(argv[++i], nullptr, 10);
        else if (a == "--extra" && i + 1 < argc) extra_nonce = (uint32_t)std::strtoul(argv[++i], nullptr, 10);
        else if (a == "--mrkl-11") mrkl_11 = true;
        else if (a == "--mrkl-00") mrkl_11 = false;
        else if (a == "--scratch-mb" && i + 1 < argc) scratch_mb = (int32_t)std::strtol(argv[++i], nullptr, 10);
        else if (a == "--rounds" && i + 1 < argc) rounds = (int32_t)std::strtol(argv[++i], nullptr, 10);
        else {
            usage(argv[0]);
            return 2;
        }
    }

    std::printf("=== SOST GENESIS MINER (C++ / Phase5+) ===\n");
    std::printf("GENESIS_TIMESTAMP = %lld\n", (long long)GENESIS_TIMESTAMP);
    std::printf("GENESIS_BITSQ     = %u (Q16.16)\n", (unsigned)GENESIS_BITSQ);
    std::printf("scratch_mb        = %d\n", (int)scratch_mb);
    std::printf("rounds            = %d\n", (int)rounds);
    std::printf("max_nonce         = %u\n", (unsigned)max_nonce);
    std::printf("extra_nonce       = %u\n", (unsigned)extra_nonce);
    std::printf("merkle_root       = %s\n", mrkl_11 ? "11..11" : "00..00");
    std::printf("\n");

    // Wait for genesis time unless --now
    const int64_t ts64 = GENESIS_TIMESTAMP;
    if (!now) {
        auto now_epoch = std::chrono::system_clock::now().time_since_epoch();
        int64_t now_ts = std::chrono::duration_cast<std::chrono::seconds>(now_epoch).count();
        if (now_ts < ts64) {
            int64_t wait = ts64 - now_ts;
            std::printf("Waiting %lld seconds until genesis time...\n", (long long)wait);
            std::printf("(Use Ctrl+C to abort, --now to skip wait)\n\n");
            while (true) {
                now_epoch = std::chrono::system_clock::now().time_since_epoch();
                now_ts = std::chrono::duration_cast<std::chrono::seconds>(now_epoch).count();
                if (now_ts >= ts64) break;
                int64_t remaining = ts64 - now_ts;
                std::printf("\r  T-%lldh %lldm %llds   ",
                            (long long)(remaining / 3600),
                            (long long)((remaining % 3600) / 60),
                            (long long)(remaining % 60));
                std::fflush(stdout);
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
            std::printf("\n\n");
        }
    }

    // Consensus params for ConvergenceX (baseline mainnet)
    ConsensusParams params{};
    params.cx_n = 32;
    params.cx_rounds = rounds;
    params.cx_scratch_mb = scratch_mb;
    params.cx_lr_shift = 18;
    params.cx_lam = 100;
    params.cx_checkpoint_interval = std::max(1, rounds / 16);

    // B0 profile (genesis baseline) — profile_index=0 committed to block hash
    params.stab_scale = CX_STB_SCALE;   // 1
    params.stab_k = CX_STB_K;           // 4
    params.stab_margin = CX_STB_MARGIN; // 185 (B0)
    params.stab_steps = CX_STB_STEPS;   // 4
    params.stab_lr_shift = CX_STB_LR;   // 20
    params.stab_profile_index = 0;       // B0 — committed to commit hash

    // Genesis inputs
    Bytes32 prev = ZERO_HASH();
    Bytes32 mrkl{};
    mrkl.fill(mrkl_11 ? 0x11 : 0x00);

    const uint32_t ts_u32 = (uint32_t)GENESIS_TIMESTAMP; // safe (fits u32)
    const uint32_t bitsq = GENESIS_BITSQ;

    // Build scratchpad (epoch 0 key must match python: "EPOCH" 5 bytes)
    std::printf("Building scratchpad (%d MB)...\n", (int)scratch_mb);
    Bytes32 skey = epoch_scratch_key(0, nullptr);
    auto t0 = std::chrono::steady_clock::now();
    auto scratch = build_scratchpad(skey, scratch_mb);
    auto t1 = std::chrono::steady_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();
    std::printf("Scratchpad ready in %lld ms\n\n", (long long)ms);

    // Header core 72
    uint8_t hc72[72];
    build_header_core_72(hc72, prev, mrkl, ts_u32, bitsq);

    // Block key depends only on prev
    Bytes32 bk = compute_block_key(prev);

    std::printf("Mining genesis...\n");
    std::printf("  prev_hash   = %s\n", hex(prev).c_str());
    std::printf("  merkle_root = %s\n", hex(mrkl).c_str());
    std::printf("  timestamp   = %u\n", (unsigned)ts_u32);
    std::printf("  bitsq       = %u\n", (unsigned)bitsq);
    std::printf("  block_key   = %s\n\n", hex(bk).c_str());

    const int32_t epoch = 0;

    uint32_t found_nonce = 0;
    bool found = false;
    CXAttemptResult found_res{};

    auto mine_start = std::chrono::steady_clock::now();

    for (uint32_t nonce = 0; nonce <= max_nonce; ++nonce) {
        if ((nonce % 2500) == 0) {
            std::printf("\r  nonce=%u", (unsigned)nonce);
            std::fflush(stdout);
        }

        auto res = convergencex_attempt(
            scratch.data(), scratch.size(),
            bk, nonce, extra_nonce,
            params, hc72, epoch
        );

        if (res.is_stable && pow_meets_target(res.commit, bitsq)) {
            found = true;
            found_nonce = nonce;
            found_res = std::move(res);
            break;
        }
    }

    auto mine_end = std::chrono::steady_clock::now();
    auto mine_ms = std::chrono::duration_cast<std::chrono::milliseconds>(mine_end - mine_start).count();
    std::printf("\n");

    if (!found) {
        std::printf("FATAL: could not find genesis in nonce range [0..%u] (extra=%u)\n",
                    (unsigned)max_nonce, (unsigned)extra_nonce);
        return 1;
    }

    // Compute block_id from full header bytes + commit (matches python construction)
    auto full_hdr = build_full_header_bytes(hc72, found_res.checkpoints_root, found_nonce, extra_nonce);
    Bytes32 block_id = compute_block_id(full_hdr.data(), full_hdr.size(), found_res.commit);

    // Subsidy (consensus hook)
    int64_t subsidy = GetBlockSubsidy(0);
    auto split = coinbase_split_50_25_25(subsidy);

    // Hex encode x_bytes and final_state
    auto to_hex = [](const uint8_t* d, size_t n) -> std::string {
        static const char* hx = "0123456789abcdef";
        std::string s; s.reserve(n*2);
        for(size_t i=0;i<n;++i){s+=hx[d[i]>>4];s+=hx[d[i]&0xF];}
        return s;
    };
    std::string x_hex = to_hex(found_res.x_bytes.data(), found_res.x_bytes.size());
    std::string fs_hex = hex(found_res.final_state);

    std::printf("\n=== GENESIS FOUND ===\n");
    std::printf("block_id         = %s\n", hex(block_id).c_str());
    std::printf("commit           = %s\n", hex(found_res.commit).c_str());
    std::printf("checkpoints_root = %s\n", hex(found_res.checkpoints_root).c_str());
    std::printf("segments_root    = %s\n", hex(found_res.segments_root).c_str());
    std::printf("final_state      = %s\n", fs_hex.c_str());
    std::printf("x_bytes          = %s\n", x_hex.c_str());
    std::printf("stability_metric = %llu\n", (unsigned long long)found_res.stability_metric);
    std::printf("nonce            = %u\n", (unsigned)found_nonce);
    std::printf("extra_nonce      = %u\n", (unsigned)extra_nonce);
    std::printf("elapsed_ms       = %lld\n", (long long)mine_ms);

    std::printf("\nSubsidy height=0 = %lld stocks\n", (long long)subsidy);
    std::printf("  miner      = %lld\n", (long long)split.miner);
    std::printf("  gold_vault = %lld\n", (long long)split.gold_vault);
    std::printf("  popc_pool  = %lld\n", (long long)split.popc_pool);
    std::printf("  sum_check  = %lld %s\n",
                (long long)(split.miner + split.gold_vault + split.popc_pool),
                ((split.miner + split.gold_vault + split.popc_pool) == subsidy) ? "OK" : "FAIL");

    // Save genesis_block.json
    FILE* f = std::fopen("genesis_block.json", "w");
    if (f) {
        std::fprintf(f, "{\n");
        std::fprintf(f, "  \"timestamp\": %lld,\n", (long long)GENESIS_TIMESTAMP);
        std::fprintf(f, "  \"bits_q\": %u,\n", (unsigned)bitsq);
        std::fprintf(f, "  \"prev_hash\": \"%s\",\n", hex(prev).c_str());
        std::fprintf(f, "  \"merkle_root\": \"%s\",\n", hex(mrkl).c_str());
        std::fprintf(f, "  \"nonce\": %u,\n", (unsigned)found_nonce);
        std::fprintf(f, "  \"extra_nonce\": %u,\n", (unsigned)extra_nonce);
        std::fprintf(f, "  \"block_id\": \"%s\",\n", hex(block_id).c_str());
        std::fprintf(f, "  \"commit\": \"%s\",\n", hex(found_res.commit).c_str());
        std::fprintf(f, "  \"checkpoints_root\": \"%s\",\n", hex(found_res.checkpoints_root).c_str());
        std::fprintf(f, "  \"stability_metric\": %llu,\n", (unsigned long long)found_res.stability_metric);
        std::fprintf(f, "  \"x_bytes\": \"%s\",\n", x_hex.c_str());
        std::fprintf(f, "  \"final_state\": \"%s\",\n", fs_hex.c_str());
        std::fprintf(f, "  \"segments_root\": \"%s\",\n", hex(found_res.segments_root).c_str());
        std::fprintf(f, "  \"checkpoint_leaves\": [");
        for (size_t i = 0; i < found_res.checkpoint_leaves.size(); ++i) {
            if (i) std::fprintf(f, ",");
            std::fprintf(f, "\"%s\"", hex(found_res.checkpoint_leaves[i]).c_str());
        }
        std::fprintf(f, "],\n");
        std::fprintf(f, "  \"subsidy_stocks\": %lld,\n", (long long)subsidy);
        std::fprintf(f, "  \"coinbase_split\": {\n");
        std::fprintf(f, "    \"miner\": %lld,\n", (long long)split.miner);
        std::fprintf(f, "    \"gold_vault\": %lld,\n", (long long)split.gold_vault);
        std::fprintf(f, "    \"popc_pool\": %lld\n", (long long)split.popc_pool);
        std::fprintf(f, "  }\n");
        std::fprintf(f, "}\n");
        std::fclose(f);
        std::printf("\nSaved: genesis_block.json\n");
    } else {
        std::printf("\nWARN: could not write genesis_block.json\n");
    }

    return 0;
}
