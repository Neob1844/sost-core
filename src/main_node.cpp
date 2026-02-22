#include "sost/node.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <unistd.h>
#include <thread>
using namespace sost;
int main(int argc, char** argv) {
    int blocks=5; int port=0; Profile prof=Profile::DEV; uint32_t mn=500000;
    for(int i=1;i<argc;++i){
        if(!strcmp(argv[i],"--blocks")&&i+1<argc) blocks=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--port")&&i+1<argc) port=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--profile")&&i+1<argc){
            ++i; if(!strcmp(argv[i],"mainnet"))prof=Profile::MAINNET;
            else if(!strcmp(argv[i],"testnet"))prof=Profile::TESTNET;
        }
        else if(!strcmp(argv[i],"--max-nonce")&&i+1<argc) mn=(uint32_t)atoi(argv[++i]);
    }
    printf("SOST Node v0.1\nProfile: %s | Blocks: %d | RPC: %d\n\n",
        prof==Profile::MAINNET?"mainnet":(prof==Profile::TESTNET?"testnet":"dev"), blocks, port);
    Node node(prof); Wallet wallet; wallet.generate_key();
    printf("Miner address: %s\n\n", wallet.default_address().c_str());
    if(port>0){
        std::thread rpc([&](){ run_rpc_server(node, wallet, port); });
        rpc.detach();
        printf("[RPC] Started on port %d\n", port);
    }
    int rc = node.mine_loop(blocks, wallet, mn);
    printf("\nFinal balance: %lld stockshis\n", (long long)wallet.balance());
    printf("Chain height: %lld\n", (long long)node.height());
    if(port>0){printf("[RPC] still running, Ctrl+C to stop\n");while(true)sleep(1);}
    return rc;
}
