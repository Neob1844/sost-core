#include "sost/miner.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
using namespace sost;

static void usage() {
    printf("Usage: sost-miner [options]\n");
    printf("  --blocks N     Mine N blocks (0=infinite, default=3)\n");
    printf("  --profile P    dev|testnet|mainnet (default=dev)\n");
    printf("  --max-nonce N  Nonce range (default=500000)\n");
    printf("  --sim-time     Use simulated time (default)\n");
    printf("  --live-time    Use wall clock\n");
}

int main(int argc, char** argv) {
    int32_t blocks = 3;
    Profile prof = Profile::DEV;
    uint32_t max_nonce = 500000;
    bool sim = true;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--blocks") && i+1 < argc) blocks = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--profile") && i+1 < argc) {
            ++i;
            if (!strcmp(argv[i], "mainnet")) prof = Profile::MAINNET;
            else if (!strcmp(argv[i], "testnet")) prof = Profile::TESTNET;
            else prof = Profile::DEV;
        }
        else if (!strcmp(argv[i], "--max-nonce") && i+1 < argc) max_nonce = (uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--sim-time")) sim = true;
        else if (!strcmp(argv[i], "--live-time")) sim = false;
        else if (!strcmp(argv[i], "--help")) { usage(); return 0; }
    }
    printf("SOST Miner - ConvergenceX PoW\n");
    printf("Profile: %s | Blocks: %d | MaxNonce: %u\n\n",
        prof == Profile::MAINNET ? "mainnet" : (prof == Profile::TESTNET ? "testnet" : "dev"),
        blocks, max_nonce);
    return mine_chain(blocks, prof, sim, max_nonce, nullptr);
}
