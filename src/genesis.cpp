#include "sost/miner.h"
#include <cstdio>
#include <cstring>
#include <chrono>
#include <thread>
#include <fstream>

int main() {
    using namespace sost;
    
    printf("=== SOST GENESIS MINER ===\n");
    printf("Target: 2026-02-28 00:00:00 UTC (ts=%lld)\n\n", (long long)GENESIS_TIME);
    printf("Constitutional addresses:\n");
    printf("  Miner:      %s\n", ADDR_MINER_FOUNDER);
    printf("  Gold Vault: %s\n", ADDR_GOLD_VAULT);
    printf("  PoPC Pool:  %s\n", ADDR_POPC_POOL);
    
    // Subsidy and split for block 0
    int64_t subsidy = sost_subsidy_stocks(0);
    auto split = coinbase_split(subsidy);
    printf("\nBlock 0 reward: %lld stocks (%.8f SOST)\n", 
           (long long)subsidy, (double)subsidy / STOCKSHIS_PER_SOST);
    printf("  Miner:      %lld stocks\n", (long long)split.miner);
    printf("  Gold Vault: %lld stocks\n", (long long)split.gold_vault);
    printf("  PoPC Pool:  %lld stocks\n", (long long)split.popc_pool);
    printf("  Sum check:  %lld == %lld ? %s\n\n",
           (long long)(split.miner + split.gold_vault + split.popc_pool),
           (long long)subsidy,
           (split.miner + split.gold_vault + split.popc_pool == subsidy) ? "OK" : "FAIL");
    
    // Wait for genesis time
    auto now_epoch = std::chrono::system_clock::now().time_since_epoch();
    int64_t now_ts = std::chrono::duration_cast<std::chrono::seconds>(now_epoch).count();
    
    if (now_ts < GENESIS_TIME) {
        int64_t wait = GENESIS_TIME - now_ts;
        printf("Waiting %lld seconds until genesis time...\n", (long long)wait);
        printf("(Use Ctrl+C to abort, --now to skip wait)\n\n");
        
        // Countdown every 60s
        while (true) {
            now_epoch = std::chrono::system_clock::now().time_since_epoch();
            now_ts = std::chrono::duration_cast<std::chrono::seconds>(now_epoch).count();
            if (now_ts >= GENESIS_TIME) break;
            int64_t remaining = GENESIS_TIME - now_ts;
            printf("\r  T-%lldh %lldm %llds   ", remaining/3600, (remaining%3600)/60, remaining%60);
            fflush(stdout);
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        printf("\n\n");
    }
    
    printf(">>> GENESIS TIME REACHED <<<\n\n");
    
    // Build scratchpad (4GB, takes ~25s)
    printf("Building 4GB mainnet scratchpad...\n");
    Profile prof = Profile::MAINNET;
    ACTIVE_PROFILE = prof;
    int32_t epoch = 0;
    ConsensusParams params = get_consensus_params(prof, 0);
    Bytes32 skey = epoch_scratch_key(epoch);
    auto t0 = std::chrono::steady_clock::now();
    auto scratch = build_scratchpad(skey, params.cx_scratch_mb);
    auto t1 = std::chrono::steady_clock::now();
    auto scratch_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1-t0).count();
    printf("Scratchpad ready (%llds)\n\n", (long long)(scratch_ms/1000));
    
    // Genesis block inputs
    Bytes32 prev{}; prev.fill(0);       // block 0: prev = 0x00*32
    Bytes32 mrkl{}; mrkl.fill(0);       // block 0: no transactions yet
    int64_t ts = GENESIS_TIME;
    uint32_t powDiffQ = GENESIS_BITSQ;
    
    Bytes32 bk = compute_block_key(prev);
    auto hc = build_header_core(prev, mrkl, (uint32_t)ts, powDiffQ);
    
    printf("Mining genesis block (mainnet, 100k rounds, 4GB)...\n");
    printf("  prev_hash:  %s\n", hex(prev).c_str());
    printf("  merkle_root:%s\n", hex(mrkl).c_str());
    printf("  timestamp:  %lld\n", (long long)ts);
    printf("  powDiffQ:   %u\n", powDiffQ);
    printf("  block_key:  %s\n\n", hex(bk).c_str());
    
    auto mine_start = std::chrono::steady_clock::now();
    uint32_t attempts = 0;
    bool found = false;
    Block genesis{};
    
    for (uint32_t nonce = 0; nonce < 10000000; ++nonce) {
        attempts++;
        if (attempts % 10 == 1) {
            printf("\r  Attempt %u (nonce=%u)...", attempts, nonce);
            fflush(stdout);
        }
        
        auto res = convergencex_attempt(
            scratch.data(), scratch.size(), bk,
            nonce, 0, params, hc.data(), epoch);
        
        if (res.is_stable && pow_meets_target(res.commit, powDiffQ)) {
            auto mine_end = std::chrono::steady_clock::now();
            auto mine_ms = std::chrono::duration_cast<std::chrono::milliseconds>(mine_end - mine_start).count();
            
            genesis.height = 0;
            genesis.prev_hash = prev;
            genesis.merkle_root = mrkl;
            genesis.timestamp = ts;
            genesis.powDiffQ = powDiffQ;
            genesis.nonce = nonce;
            genesis.extra_nonce = 0;
            genesis.commit = res.commit;
            genesis.checkpoints_root = res.checkpoints_root;
            genesis.stability_metric = res.stability_metric;
            genesis.x_bytes = res.x_bytes;
            genesis.subsidy_stocks = subsidy;
            genesis.chainwork = 0;
            genesis.block_id = compute_block_id_from_parts(
                prev, mrkl, (uint32_t)ts, powDiffQ,
                res.checkpoints_root, nonce, 0, res.commit);
            
            printf("\n\n");
            printf("╔══════════════════════════════════════════════════════════════╗\n");
            printf("║              SOST GENESIS BLOCK MINED                       ║\n");
            printf("╚══════════════════════════════════════════════════════════════╝\n\n");
            printf("  block_id:         %s\n", hex(genesis.block_id).c_str());
            printf("  commit:           %s\n", hex(genesis.commit).c_str());
            printf("  checkpoints_root: %s\n", hex(genesis.checkpoints_root).c_str());
            printf("  stability_metric: %lu\n", (unsigned long)genesis.stability_metric);
            printf("  nonce:            %u\n", genesis.nonce);
            printf("  attempts:         %u\n", attempts);
            printf("  elapsed:          %llds\n", (long long)(mine_ms/1000));
            printf("  timestamp:        %lld (2026-02-28 00:00:00 UTC)\n", (long long)ts);
            printf("  subsidy:          %lld stocks\n", (long long)subsidy);
            printf("  miner_reward:     %lld → %s\n", (long long)split.miner, ADDR_MINER_FOUNDER);
            printf("  gold_vault:       %lld → %s\n", (long long)split.gold_vault, ADDR_GOLD_VAULT);
            printf("  popc_pool:        %lld → %s\n", (long long)split.popc_pool, ADDR_POPC_POOL);
            
            // Verify
            std::vector<BlockMeta> empty_chain;
            auto vr = verify_block(genesis, empty_chain, ts, prof, true);
            printf("\n  VERIFY: %s\n", vr.ok ? "PASSED" : vr.reason.c_str());
            
            // Save JSON
            FILE* f = fopen("genesis_block.json", "w");
            if (f) {
                fprintf(f, "{\n");
                fprintf(f, "  \"height\": 0,\n");
                fprintf(f, "  \"block_id\": \"%s\",\n", hex(genesis.block_id).c_str());
                fprintf(f, "  \"prev_hash\": \"%s\",\n", hex(genesis.prev_hash).c_str());
                fprintf(f, "  \"merkle_root\": \"%s\",\n", hex(genesis.merkle_root).c_str());
                fprintf(f, "  \"timestamp\": %lld,\n", (long long)genesis.timestamp);
                fprintf(f, "  \"timestamp_human\": \"2026-02-28T00:00:00Z\",\n");
                fprintf(f, "  \"powDiffQ\": %u,\n", genesis.powDiffQ);
                fprintf(f, "  \"nonce\": %u,\n", genesis.nonce);
                fprintf(f, "  \"extra_nonce\": 0,\n");
                fprintf(f, "  \"commit\": \"%s\",\n", hex(genesis.commit).c_str());
                fprintf(f, "  \"checkpoints_root\": \"%s\",\n", hex(genesis.checkpoints_root).c_str());
                fprintf(f, "  \"stability_metric\": %lu,\n", (unsigned long)genesis.stability_metric);
                fprintf(f, "  \"subsidy_stocks\": %lld,\n", (long long)genesis.subsidy_stocks);
                fprintf(f, "  \"subsidy_sost\": \"%.8f\",\n", (double)subsidy / STOCKSHIS_PER_SOST);
                fprintf(f, "  \"coinbase\": {\n");
                fprintf(f, "    \"miner\": { \"address\": \"%s\", \"amount\": %lld },\n", ADDR_MINER_FOUNDER, (long long)split.miner);
                fprintf(f, "    \"gold_vault\": { \"address\": \"%s\", \"amount\": %lld },\n", ADDR_GOLD_VAULT, (long long)split.gold_vault);
                fprintf(f, "    \"popc_pool\": { \"address\": \"%s\", \"amount\": %lld }\n", ADDR_POPC_POOL, (long long)split.popc_pool);
                fprintf(f, "  },\n");
                fprintf(f, "  \"verified\": %s,\n", vr.ok ? "true" : "false");
                fprintf(f, "  \"profile\": \"mainnet\",\n");
                fprintf(f, "  \"magic\": \"4358504f5733c6e88538\"\n");
                fprintf(f, "}\n");
                fclose(f);
                printf("\n  Saved: genesis_block.json\n");
            }
            
            found = true;
            break;
        }
    }
    
    if (!found) {
        printf("\n\nFATAL: Could not find genesis block after %u attempts\n", attempts);
        return 1;
    }
    
    printf("\n=== GENESIS COMPLETE ===\n");
    return 0;
}
