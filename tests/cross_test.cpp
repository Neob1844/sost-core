#include "sost/convergencex.h"
#include "sost/block.h"
#include "sost/scratchpad.h"
#include <cstdio>
using namespace sost;

int main() {
    ACTIVE_PROFILE = Profile::DEV;
    
    // V1: block_key from zero prev_hash
    Bytes32 prev{}; prev.fill(0);
    Bytes32 bk = compute_block_key(prev);
    printf("block_key(0x00*32) = %s\n", hex(bk).c_str());
    
    // V2: header_core
    Bytes32 mrkl{}; mrkl.fill(0x11);
    uint32_t ts = 1772236800;
    uint32_t diff = GENESIS_BITSQ;
    auto hc = build_header_core(prev, mrkl, ts, diff);
    printf("header_core_sha = %s\n", hex(sha256(hc.data(), hc.size())).c_str());
    printf("header_core_len = %zu\n", hc.size());
    
    // V3: seed (nonce=0, extra=0)
    auto params = get_consensus_params(Profile::DEV, 0);
    // Manual seed: MAGIC||"SEED"||hc||bk||nonce(0)||extra(0)
    std::vector<uint8_t> sbuf;
    append_magic(sbuf);
    append(sbuf, "SEED", 4);
    append(sbuf, hc.data(), HEADER_CORE_LEN);
    append(sbuf, bk);
    uint8_t z8[8] = {0};
    append(sbuf, z8, 8); // nonce=0, extra=0
    Bytes32 seed = sha256(sbuf);
    printf("seed(n=0,e=0) = %s\n", hex(seed).c_str());
    
    // V4: epoch_scratch_key(0)
    Bytes32 esk = epoch_scratch_key(0);
    printf("epoch_key(0) = %s\n", hex(esk).c_str());
    
    // V5: full CX attempt (dev, nonce=0, extra=0)
    auto scratch = build_scratchpad(esk, params.cx_scratch_mb);
    auto cx = convergencex_attempt(
        scratch.data(), scratch.size(), bk, 0, 0,
        params, hc.data(), 0);
    printf("commit(n=0) = %s\n", hex(cx.commit).c_str());
    printf("cp_root(n=0) = %s\n", hex(cx.checkpoints_root).c_str());
    printf("metric(n=0) = %lu\n", (unsigned long)cx.stability_metric);
    printf("stable(n=0) = %d\n", cx.is_stable ? 1 : 0);
    
    // Print MAGIC for verification
    printf("MAGIC = ");
    auto m = magic_for_profile(Profile::DEV);
    for(int i=0;i<10;i++) printf("%02x",m[i]);
    printf("\n");
    
    return 0;
}
