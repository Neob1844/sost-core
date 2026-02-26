#include "sost/wallet.h"
#include "sost/emission.h"
#include <cstdio>
#include <cstring>
using namespace sost;

static void usage() {
    printf("Usage: sost-wallet <command>\n");
    printf("  generate        Generate new keypair\n");
    printf("  balance          Show balance\n");
    printf("  addresses        List addresses\n");
    printf("  utxos            List unspent outputs\n");
    printf("  save <file>      Save wallet\n");
    printf("  load <file>      Load wallet\n");
}

int main(int argc, char** argv) {
    if (argc < 2) { usage(); return 1; }
    Wallet w;
    if (argc >= 3 && !strcmp(argv[1], "load")) {
        if (!w.load(argv[2])) { printf("Failed to load %s\n", argv[2]); return 1; }
        printf("Loaded wallet from %s\n", argv[2]);
        printf("Addresses: %zu | Balance: %lld stocks\n", w.addresses().size(), (long long)w.balance());
    } else if (!strcmp(argv[1], "generate")) {
        auto kp = w.generate_key();
        printf("Address: %s\n", kp.addr.c_str());
        printf("Pubkey:  %s\n", hex(kp.pub).c_str());
        printf("Privkey: %s\n", hex(kp.priv).c_str());
    } else if (!strcmp(argv[1], "balance")) {
        printf("Balance: %lld stocks\n", (long long)w.balance());
    } else if (!strcmp(argv[1], "addresses")) {
        for (auto& a : w.addresses()) printf("  %s\n", a.c_str());
    } else { usage(); }
    if (argc >= 3 && !strcmp(argv[argc-2], "save")) {
        w.save(argv[argc-1]);
        printf("Saved to %s\n", argv[argc-1]);
    }
    return 0;
}
