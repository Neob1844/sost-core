// =============================================================================
// sost-signtx — sign one input of an unsigned SOST transaction (founder tool).
//
// The HTLC builders (createhtlclock / claimhtlc / refundhtlc) and other tx
// builders emit UNSIGNED transactions. This tool signs a single input with a
// private key so the result can be broadcast via `sost-cli sendrawtransaction`.
// It uses the repo's consensus signer (SignTransactionInput) — same sighash the
// node validates — so the output is consensus-valid.
//
// Works for any input: a normal P2PKH funding spend (HTLC LOCK), or an HTLC
// LOCK being spent by CLAIM/REFUND — you just pass the spent UTXO's type+amount.
//
//   sost-signtx <unsigned_tx_hex> <privkey_hex32> <spent_amount_stocks> \
//               <spent_type> [input_index=0] [genesis_hex]
//
//   spent_type: 0  = OUT_TRANSFER  (normal UTXO — e.g. the LOCK's funding input)
//               18 = OUT_HTLC_LOCK (0x12 — the UTXO a CLAIM/REFUND spends)
//   genesis_hex defaults to SOST mainnet genesis.
//
// Prints the SIGNED tx hex on success and self-verifies the signature.
// Read-only w.r.t. the chain: signs locally, broadcasts nothing.
// =============================================================================
#include "sost/transaction.h"
#include "sost/tx_signer.h"
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <array>
#include <unistd.h>
#include <fcntl.h>

// The consensus signer (ComputeSighash, src/tx_signer.cpp) emits unconditional
// [SIGHASH-DEBUG] lines to stdout on every sign. We mute fd 1 → /dev/null for the
// whole run and emit the clean signed hex via write() to the saved real-stdout fd,
// avoiding any FILE* stdout buffer confusion from fd juggling.

using namespace sost;

static const char* MAINNET_GENESIS =
    "6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37";

static std::vector<Byte> from_hex(const std::string& h) {
    std::vector<Byte> v; v.reserve(h.size()/2);
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        v.push_back((Byte)std::stoul(h.substr(i,2), nullptr, 16));
    return v;
}
static std::string to_hex(const std::vector<Byte>& b) {
    static const char* hx="0123456789abcdef"; std::string s; s.reserve(b.size()*2);
    for (Byte c: b){ s+=hx[c>>4]; s+=hx[c&15]; } return s;
}

int main(int argc, char** argv) {
    if (argc < 5) {
        fprintf(stderr,
          "usage: sost-signtx <unsigned_tx_hex> <privkey_hex32> <spent_amount_stocks> "
          "<spent_type> [input_index=0] [genesis_hex]\n"
          "  spent_type: 0=OUT_TRANSFER (normal), 18=OUT_HTLC_LOCK (for CLAIM/REFUND)\n");
        return 1;
    }
    std::string tx_hex = argv[1], pk_hex = argv[2];
    int64_t spent_amount = std::stoll(argv[3]);
    int spent_type = std::stoi(argv[4]);
    size_t input_index = (argc > 5) ? (size_t)std::stoul(argv[5]) : 0;
    std::string genesis_hex = (argc > 6) ? argv[6] : MAINNET_GENESIS;

    auto raw = from_hex(tx_hex);
    Transaction tx; std::string err;
    if (!Transaction::Deserialize(raw, tx, &err)) {
        fprintf(stderr, "deserialize failed: %s\n", err.c_str()); return 2;
    }
    if (input_index >= tx.inputs.size()) {
        fprintf(stderr, "input_index %zu out of range (%zu inputs)\n", input_index, tx.inputs.size());
        return 2;
    }
    auto pkv = from_hex(pk_hex);
    if (pkv.size() != 32) { fprintf(stderr, "privkey must be 32 bytes (64 hex)\n"); return 2; }
    PrivKey priv{}; std::copy(pkv.begin(), pkv.end(), priv.begin());
    auto gv = from_hex(genesis_hex);
    if (gv.size() != 32) { fprintf(stderr, "genesis must be 32 bytes (64 hex)\n"); return 2; }
    Hash256 genesis{}; std::copy(gv.begin(), gv.end(), genesis.begin());

    SpentOutput spent{spent_amount, (uint8_t)spent_type};

    // Mute fd 1 for the signing run; keep the real stdout fd to emit clean hex.
    fflush(stdout);
    int real_stdout = dup(1);
    { int n = open("/dev/null", O_WRONLY); if (n >= 0) { dup2(n, 1); close(n); } }

    bool sign_ok = SignTransactionInput(tx, input_index, spent, genesis, priv, &err);
    bool ok = false;
    std::vector<Byte> out; bool ser = false;
    if (sign_ok) {
        PubKey pub{}; std::copy(tx.inputs[input_index].pubkey.begin(), tx.inputs[input_index].pubkey.end(), pub.begin());
        PubKeyHash pkh = ComputePubKeyHash(pub);
        std::string verr;
        ok = VerifyTransactionInput(tx, input_index, spent, genesis, pkh, &verr);
        ser = tx.Serialize(out, &err);
    }
    fflush(stdout);
    dup2(real_stdout, 1); close(real_stdout);   // restore real stdout

    if (!sign_ok) { fprintf(stderr, "sign failed: %s\n", err.c_str()); return 3; }
    if (!ser)     { fprintf(stderr, "serialize failed: %s\n", err.c_str()); return 4; }
    fprintf(stderr, "[sost-signtx] signed input %zu (spent_type=%d amount=%lld) — signature verifies: %s\n",
            input_index, spent_type, (long long)spent_amount, ok ? "YES" : "NO (check spent_type/amount/key)");
    std::string hexline = to_hex(out) + "\n";
    if (write(1, hexline.data(), hexline.size()) < 0) { /* ignore */ }
    return ok ? 0 : 5;
}
