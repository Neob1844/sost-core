// Quick equalizer benchmark — tests ALL profiles B0 through H6
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include "sost/emission.h"
#include "sost/sostcompact.h"
#include <cstdio>
#include <chrono>
#include <vector>
#include <numeric>
using namespace sost;
using clk = std::chrono::steady_clock;

int main() {
    ACTIVE_PROFILE = Profile::MAINNET;
    ConsensusParams base = get_consensus_params(Profile::MAINNET, 0);
    int N = 30;

    printf("Building scratchpad (256 MB)...\n");
    base.cx_scratch_mb = 256;
    auto scratch = build_scratchpad(epoch_scratch_key(0, nullptr), base.cx_scratch_mb);

    Bytes32 prev{}; prev.fill(0xAA);
    Bytes32 merkle{}; merkle.fill(0xBB);
    uint8_t hc72[72];
    std::memcpy(hc72, prev.data(), 32);
    std::memcpy(hc72 + 32, merkle.data(), 32);
    write_u32_le(hc72 + 64, (uint32_t)GENESIS_TIME);
    write_u32_le(hc72 + 68, GENESIS_BITSQ);
    Bytes32 bk = compute_block_key(prev);
    g_cx_dataset.generate(prev);

    printf("\n%-6s %6s %6s %8s %8s %10s\n", "PROFILE", "SCALE", "MARGIN", "STABLE%", "AVG(ms)", "ATT/s");
    printf("------------------------------------------------------\n");

    const char* names[] = {"E3","E2","E1","B0","H1","H2","H3","H4","H5","H6"};
    for (int pi = 0; pi < CASERT_PROFILE_COUNT; ++pi) {
        ConsensusParams p = base;
        p.stab_scale = CASERT_PROFILES[pi].scale;
        p.stab_steps = CASERT_PROFILES[pi].steps;
        p.stab_k = CASERT_PROFILES[pi].k;
        p.stab_margin = CASERT_PROFILES[pi].margin;

        int stable = 0;
        double total_ms = 0;
        for (int i = 0; i < N; ++i) {
            auto t0 = clk::now();
            auto res = convergencex_attempt(scratch.data(), scratch.size(), bk, (uint32_t)(pi*1000+i), 0, p, hc72, 0);
            double ms = std::chrono::duration<double, std::milli>(clk::now() - t0).count();
            total_ms += ms;
            if (res.is_stable) stable++;
        }
        double avg = total_ms / N;
        double rate = (double)stable / N * 100;
        printf("%-6s %6d %6d %7.1f%% %8.1f %10.2f\n",
               names[pi], p.stab_scale, p.stab_margin, rate, avg, 1000.0/avg);
    }
    return 0;
}
