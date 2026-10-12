// sost_lab_sign — LAB/DEVNET ONLY. Signs an unsigned SOST transaction (for
// example the hex printed by `sost-cli createhtlclock / claimhtlc / refundhtlc`)
// with keys from a plaintext devnet wallet. It is a standalone test tool: it is
// not part of sost-cli, the node or the miner, and it changes no consensus rule.
// It uses the same ComputeSighash / SignTransactionInput the wallet uses.
//
// usage: sost_lab_sign <wallet.json> <genesis_hash_hex> <unsigned_tx_hex>
//                      <amount>:<type>:<signer_address> ...   (one per input)
//   type = output type of the UTXO being spent (0 = transfer, 18 = HTLC lock)
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include "sost/wallet.h"
#include "sost/types.h"
#include <cstdio>
#include <string>
#include <vector>

static std::vector<sost::Byte> unhex(const std::string& s) {
    std::vector<sost::Byte> v;
    for (size_t i = 0; i + 1 < s.size(); i += 2) v.push_back((sost::Byte)std::stoul(s.substr(i, 2), nullptr, 16));
    return v;
}
static std::string tohex(const std::vector<sost::Byte>& v) {
    static const char* d = "0123456789abcdef"; std::string s;
    for (auto b : v) { s += d[b >> 4]; s += d[b & 15]; }
    return s;
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s wallet.json genesis_hex tx_hex amount:type:addr...\n", argv[0]); return 2; }
    sost::Wallet w; std::string err;
    if (!w.load(argv[1], &err)) { fprintf(stderr, "wallet: %s\n", err.c_str()); return 1; }
    sost::Hash256 genesis = sost::from_hex(argv[2]);
    sost::Transaction tx;
    if (!sost::Transaction::Deserialize(unhex(argv[3]), tx, &err)) { fprintf(stderr, "tx: %s\n", err.c_str()); return 1; }
    if ((size_t)(argc - 4) != tx.inputs.size()) { fprintf(stderr, "need %zu input specs\n", tx.inputs.size()); return 1; }
    for (size_t i = 0; i < tx.inputs.size(); ++i) {
        std::string spec = argv[4 + i];
        size_t a = spec.find(':'), b = spec.find(':', a + 1);
        if (a == std::string::npos || b == std::string::npos) { fprintf(stderr, "bad spec %s\n", spec.c_str()); return 1; }
        sost::SpentOutput sp; sp.amount = std::stoll(spec.substr(0, a)); sp.type = (uint8_t)std::stoi(spec.substr(a + 1, b - a - 1));
        const sost::WalletKey* k = w.find_key(spec.substr(b + 1));
        if (!k) { fprintf(stderr, "no key for %s\n", spec.substr(b + 1).c_str()); return 1; }
        if (!sost::SignTransactionInput(tx, i, sp, genesis, k->privkey, &err)) { fprintf(stderr, "sign: %s\n", err.c_str()); return 1; }
    }
    std::vector<sost::Byte> out;
    if (!tx.Serialize(out, &err)) { fprintf(stderr, "ser: %s\n", err.c_str()); return 1; }
    printf("%s\n", tohex(out).c_str());
    return 0;
}
