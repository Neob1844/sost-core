// sost-miner.cpp — SOST Block Miner v0.2
//
// Mines blocks post-genesis using ConvergenceX with:
//   - Real coinbase transactions (50/25/25 split)
//   - Real merkle root (ComputeMerkleRootFromTxs)
//   - Optional mempool tx inclusion
//   - Chain state saved to chain.json
//
// Usage:
//   sost-miner --blocks 100 --genesis genesis_block.json --chain chain.json

#include "sost/types.h"
#include "sost/params.h"
#include "sost/pow/convergencex.h"
#include "sost/pow/asert.h"
#include "sost/pow/casert.h"
#include "sost/pow/scratchpad.h"
#include "sost/sostcompact.h"
#include "sost/serialize.h"
#include "sost/emission.h"
#include "sost/subsidy.h"
#include "sost/block_validation.h"
#include "sost/transaction.h"
#include "sost/merkle.h"
#include "sost/address.h"

#include <fstream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <string>
#include <vector>

using namespace sost;

// =============================================================================
// Chain state
// =============================================================================

static std::vector<BlockMeta> g_chain;
static Bytes32 g_tip_hash;

// Mined block record
struct MinedBlock {
    Bytes32  block_id, prev_hash, merkle_root, commit, checkpoints_root;
    int64_t  height, timestamp, subsidy;
    uint32_t bits_q, nonce, extra_nonce;
    uint64_t stability_metric;
    int64_t  miner_reward, gold_vault_reward, popc_pool_reward;
};
static std::vector<MinedBlock> g_mined_blocks;

// =============================================================================
// Full header builder (same as genesis.cpp)
// =============================================================================

static std::vector<uint8_t> build_full_header_bytes(
    const uint8_t hc72[72],
    const Bytes32& checkpoints_root,
    uint32_t nonce_u32,
    uint32_t extra_u32)
{
    std::vector<uint8_t> buf;
    buf.reserve(10 + 4 + 72 + 32 + 4 + 4);
    append_magic(buf);
    append(buf, "HDR2", 4);
    append(buf, hc72, 72);
    append(buf, checkpoints_root);
    append_u32_le(buf, nonce_u32);
    append_u32_le(buf, extra_u32);
    return buf;
}

static void build_hc72(uint8_t out[72],
                       const Bytes32& prev, const Bytes32& mrkl,
                       uint32_t ts, uint32_t bits) {
    std::memcpy(out, prev.data(), 32);
    std::memcpy(out + 32, mrkl.data(), 32);
    write_u32_le(out + 64, ts);
    write_u32_le(out + 68, bits);
}

// =============================================================================
// Coinbase transaction builder
// =============================================================================

static Transaction build_coinbase_tx(int64_t height, int64_t subsidy, const CoinbaseSplit& split) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = TX_TYPE_COINBASE;

    // Single coinbase input: prev_txid=0x00*32, prev_index=0xFFFFFFFF
    TxInput cin;
    cin.prev_txid.fill(0);
    cin.prev_index = 0xFFFFFFFF;
    cin.signature.fill(0);
    cin.pubkey.fill(0);
    // Encode height in first 8 bytes of signature (coinbase field)
    for (int i = 0; i < 8; ++i)
        cin.signature[i] = (uint8_t)((height >> (i * 8)) & 0xFF);
    tx.inputs.push_back(cin);

    // Output 0: miner reward
    TxOutput out_miner;
    out_miner.amount = split.miner;
    out_miner.type = 0x01; // OUT_COINBASE_MINER
    address_decode(ADDR_MINER_FOUNDER, out_miner.pubkey_hash);
    tx.outputs.push_back(out_miner);

    // Output 1: gold vault
    TxOutput out_gold;
    out_gold.amount = split.gold_vault;
    out_gold.type = 0x02; // OUT_COINBASE_GOLD
    address_decode(ADDR_GOLD_VAULT, out_gold.pubkey_hash);
    tx.outputs.push_back(out_gold);

    // Output 2: popc pool
    TxOutput out_popc;
    out_popc.amount = split.popc_pool;
    out_popc.type = 0x03; // OUT_COINBASE_POPC
    address_decode(ADDR_POPC_POOL, out_popc.pubkey_hash);
    tx.outputs.push_back(out_popc);

    return tx;
}

// =============================================================================
// JSON helpers
// =============================================================================

static std::string jstr(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return "";
    p = j.find('"', p + n.size() + 1); if (p == std::string::npos) return "";
    auto e = j.find('"', p + 1); if (e == std::string::npos) return "";
    return j.substr(p + 1, e - p - 1);
}
static int64_t jint(const std::string& j, const std::string& k) {
    std::string n = "\"" + k + "\"";
    auto p = j.find(n); if (p == std::string::npos) return -1;
    p = j.find(':', p + n.size()); if (p == std::string::npos) return -1;
    p++; while (p < j.size() && j[p] == ' ') p++;
    return std::stoll(j.substr(p));
}

// =============================================================================
// Genesis loader
// =============================================================================

static bool load_genesis(const std::string& path) {
    std::ifstream f(path); if (!f) return false;
    std::string json((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    std::string bid = jstr(json, "block_id"); if (bid.size() != 64) return false;

    BlockMeta gm;
    gm.block_id = from_hex(bid);
    gm.height = 0;
    gm.time = jint(json, "timestamp");
    gm.powDiffQ = (uint32_t)jint(json, "bits_q");
    g_chain.push_back(gm);
    g_tip_hash = gm.block_id;

    MinedBlock gb;
    gb.block_id = gm.block_id;
    gb.prev_hash = from_hex(jstr(json, "prev_hash"));
    gb.merkle_root = from_hex(jstr(json, "merkle_root"));
    gb.commit = from_hex(jstr(json, "commit"));
    gb.checkpoints_root = from_hex(jstr(json, "checkpoints_root"));
    gb.height = 0; gb.timestamp = gm.time; gb.bits_q = gm.powDiffQ;
    gb.nonce = (uint32_t)jint(json, "nonce");
    gb.extra_nonce = (uint32_t)jint(json, "extra_nonce");
    gb.stability_metric = (uint64_t)jint(json, "stability_metric");
    gb.subsidy = jint(json, "subsidy_stocks");
    auto sp = coinbase_split(gb.subsidy);
    gb.miner_reward = sp.miner; gb.gold_vault_reward = sp.gold_vault; gb.popc_pool_reward = sp.popc_pool;
    g_mined_blocks.push_back(gb);
    return true;
}

// =============================================================================
// Chain saver
// =============================================================================

static bool save_chain(const std::string& path) {
    std::ofstream f(path); if (!f) return false;
    f << "{\n  \"chain_height\": " << (int64_t)(g_chain.size() - 1)
      << ",\n  \"tip\": \"" << hex(g_tip_hash) << "\",\n  \"blocks\": [\n";
    for (size_t i = 0; i < g_mined_blocks.size(); ++i) {
        const auto& b = g_mined_blocks[i];
        f << "    {\"block_id\":\"" << hex(b.block_id) << "\",\"prev_hash\":\"" << hex(b.prev_hash)
          << "\",\"merkle_root\":\"" << hex(b.merkle_root)
          << "\",\"height\":" << b.height << ",\"timestamp\":" << b.timestamp
          << ",\"bits_q\":" << b.bits_q << ",\"nonce\":" << b.nonce
          << ",\"extra_nonce\":" << b.extra_nonce << ",\"subsidy\":" << b.subsidy
          << ",\"miner\":" << b.miner_reward << ",\"gold_vault\":" << b.gold_vault_reward
          << ",\"popc_pool\":" << b.popc_pool_reward
          << ",\"stability_metric\":" << b.stability_metric << "}"
          << (i + 1 < g_mined_blocks.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    return f.good();
}

// =============================================================================
// Mine one block
// =============================================================================

static bool mine_one_block(Profile prof, uint32_t max_nonce, bool sim_time) {
    int64_t h = (int64_t)g_chain.size();
    int32_t epoch = (int32_t)(h / BLOCKS_PER_EPOCH);

    // Difficulty
    uint32_t bits_q = asert_next_difficulty(g_chain, h);

    // Consensus params + CASERT overlay
    ConsensusParams params = get_consensus_params(prof, h);
    auto cdec = casert_mode_from_chain(g_chain, h);
    params = casert_apply_overlay(params, cdec.mode);

    // Scratchpad
    Bytes32 skey = epoch_scratch_key(epoch, &g_chain);
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);

    // Block key
    Bytes32 bk = compute_block_key(g_tip_hash);

    // Timestamp
    int64_t ts;
    if (sim_time) {
        ts = g_chain.back().time + TARGET_SPACING;
    } else {
        ts = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
    }

    // Subsidy & coinbase tx
    int64_t subsidy = sost_subsidy_stocks(h);
    auto split = coinbase_split(subsidy);
    Transaction coinbase_tx = build_coinbase_tx(h, subsidy, split);

    // TODO: include mempool txs here
    std::vector<Transaction> block_txs;
    block_txs.push_back(coinbase_tx);

    // Compute real merkle root
    Hash256 mrkl;
    std::string merr;
    if (!ComputeMerkleRootFromTxs(block_txs, mrkl, &merr)) {
        printf("[ERROR] merkle root failed: %s\n", merr.c_str());
        return false;
    }

    printf("[MINING] h=%lld diff=%u sub=%lld casert=%s merkle=%s\n",
           (long long)h, bits_q, (long long)subsidy, casert_mode_str(cdec.mode),
           hex(mrkl).substr(0, 16).c_str());

    // Header core 72 bytes
    uint8_t hc72[72];
    build_hc72(hc72, g_tip_hash, mrkl, (uint32_t)ts, bits_q);

    auto t0 = std::chrono::steady_clock::now();
    uint32_t extra_nonce = 0;
    bool found = false;

    while (!found) {
        for (uint32_t nonce = 0; nonce <= max_nonce; ++nonce) {
            if ((nonce % 5000) == 0 && nonce > 0) {
                printf("\r  nonce=%u extra=%u", nonce, extra_nonce);
                fflush(stdout);
            }

            auto res = convergencex_attempt(
                scratch.data(), scratch.size(), bk,
                nonce, extra_nonce,
                params, hc72, epoch);

            if (res.is_stable && pow_meets_target(res.commit, bits_q)) {
                auto t1 = std::chrono::steady_clock::now();
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();

                // Block ID (same as genesis.cpp)
                auto full_hdr = build_full_header_bytes(hc72, res.checkpoints_root, nonce, extra_nonce);
                Bytes32 block_id = compute_block_id(full_hdr.data(), full_hdr.size(), res.commit);

                printf("\r[BLOCK %lld] %s nonce=%u extra=%u %lldms txs=%zu\n",
                       (long long)h, hex(block_id).substr(0, 16).c_str(),
                       nonce, extra_nonce, (long long)elapsed, block_txs.size());
                printf("  sub=%lld miner=%lld gold=%lld popc=%lld\n",
                       (long long)subsidy, (long long)split.miner,
                       (long long)split.gold_vault, (long long)split.popc_pool);

                // Update chain
                BlockMeta meta;
                meta.block_id = block_id;
                meta.height = h;
                meta.time = ts;
                meta.powDiffQ = bits_q;
                g_chain.push_back(meta);
                g_tip_hash = block_id;

                // Store
                MinedBlock mb;
                mb.block_id = block_id;
                mb.prev_hash = g_chain[g_chain.size() - 2].block_id;
                mb.merkle_root = mrkl;
                mb.commit = res.commit;
                mb.checkpoints_root = res.checkpoints_root;
                mb.height = h; mb.timestamp = ts; mb.bits_q = bits_q;
                mb.nonce = nonce; mb.extra_nonce = extra_nonce;
                mb.stability_metric = res.stability_metric;
                mb.subsidy = subsidy;
                mb.miner_reward = split.miner;
                mb.gold_vault_reward = split.gold_vault;
                mb.popc_pool_reward = split.popc_pool;
                g_mined_blocks.push_back(mb);

                found = true;
                break;
            }
        }

        if (!found) {
            extra_nonce++;
            if (sim_time) ts++;
            // Update coinbase with new extra_nonce in signature field
            coinbase_tx.inputs[0].signature[8] = (uint8_t)(extra_nonce & 0xFF);
            coinbase_tx.inputs[0].signature[9] = (uint8_t)((extra_nonce >> 8) & 0xFF);
            block_txs[0] = coinbase_tx;
            // Recompute merkle root
            if (!ComputeMerkleRootFromTxs(block_txs, mrkl, &merr)) {
                printf("[ERROR] merkle recompute: %s\n", merr.c_str());
                return false;
            }
            build_hc72(hc72, g_tip_hash, mrkl, (uint32_t)ts, bits_q);
            if (extra_nonce > 1000) {
                printf("\n[FATAL] exhausted 1000 extra_nonce loops\n");
                return false;
            }
        }
    }
    return true;
}

// =============================================================================
// main
// =============================================================================

int main(int argc, char** argv) {
    ACTIVE_PROFILE = Profile::MAINNET;

    int num_blocks = 5;
    uint32_t max_nonce = 500000;
    Profile prof = Profile::MAINNET;
    bool sim_time = false; // mainnet uses real timestamps
    std::string genesis_path = "genesis_block.json";
    std::string chain_path = "chain.json";

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--blocks") && i + 1 < argc) num_blocks = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-nonce") && i + 1 < argc) max_nonce = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--genesis") && i + 1 < argc) genesis_path = argv[++i];
        else if (!strcmp(argv[i], "--chain") && i + 1 < argc) chain_path = argv[++i];
        else if (!strcmp(argv[i], "--realtime")) sim_time = false;
        else if (!strcmp(argv[i], "--profile") && i + 1 < argc) {
            ++i;
            if (!strcmp(argv[i], "testnet")) prof = Profile::TESTNET;
            else if (!strcmp(argv[i], "dev")) prof = Profile::DEV;
        }
        else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
            printf("SOST Miner v0.2\n");
            printf("  --blocks <n>       Blocks to mine (default: 5)\n");
            printf("  --max-nonce <n>    Max nonce (default: 500000)\n");
            printf("  --genesis <path>   Genesis JSON\n");
            printf("  --chain <path>     Output chain file (default: chain.json)\n");
            printf("  --profile <p>      mainnet|testnet|dev\n");
            printf("  --realtime         Real timestamps\n");
            return 0;
        }
    }

    printf("=== SOST Miner v0.2 (real coinbase + merkle) ===\n");
    printf("Profile: %s | Blocks: %d | Max nonce: %u\n\n",
           prof == Profile::MAINNET ? "mainnet" : (prof == Profile::TESTNET ? "testnet" : "dev"),
           num_blocks, max_nonce);

    if (!load_genesis(genesis_path)) {
        fprintf(stderr, "Error: cannot load genesis\n"); return 1;
    }
    printf("Genesis: %s\n\n", hex(g_tip_hash).c_str());

    int mined = 0;
    for (int i = 0; i < num_blocks; ++i) {
        if (!mine_one_block(prof, max_nonce, sim_time)) break;
        mined++;
        save_chain(chain_path);
    }

    printf("\n=== Done: %d blocks mined, height=%lld ===\n",
           mined, (long long)(g_chain.size() - 1));
    printf("Tip: %s\n", hex(g_tip_hash).c_str());
    printf("Chain: %s\n", chain_path.c_str());
    return 0;
}
