#include "sost/pow/convergencex.h"
#include "sost/block.h"
#include "sost/pow/scratchpad.h"
#include <cstdio>
#include <ctime>
using namespace sost;

int main() {
    ACTIVE_PROFILE = Profile::MAINNET;
    
    Bytes32 prev{}; prev.fill(0);
    Bytes32 mrkl{}; mrkl.fill(0x11);
    uint32_t ts = 1772236800;
    uint32_t diff = GENESIS_BITSQ;
    
    auto bk = compute_block_key(prev);
    printf("block_key = %s\n", hex(bk).c_str());
    
    auto hc = build_header_core(prev, mrkl, ts, diff);
    auto params = get_consensus_params(Profile::MAINNET, 0);
    
    printf("Building %dMB scratchpad...\n", params.cx_scratch_mb);
    auto t0 = time(nullptr);
    auto esk = epoch_scratch_key(0);
    auto scratch = build_scratchpad(esk, params.cx_scratch_mb);
    printf("Scratchpad ready (%lds)\n", time(nullptr)-t0);
    
    printf("Running CX attempt (mainnet, nonce=0, %d rounds)...\n", params.cx_rounds);
    t0 = time(nullptr);
    auto cx = convergencex_attempt(
        scratch.data(), scratch.size(), bk, 0, 0,
        params, hc.data(), 0);
    printf("commit  = %s\n", hex(cx.commit).c_str());
    printf("cp_root = %s\n", hex(cx.checkpoints_root).c_str());
    printf("metric  = %lu\n", (unsigned long)cx.stability_metric);
    printf("stable  = %d\n", cx.is_stable ? 1 : 0);
    printf("elapsed = %lds\n", time(nullptr)-t0);
    return 0;
}
