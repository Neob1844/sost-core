// Offline build equivalence: create_transaction(sign=false) + external SignTransactionInput
// must produce the SAME bytes as the normal signed create_transaction (same coin selection,
// same outputs, same change), and the watch-only path must need no private key.
#include "sost/wallet.h"
#include "sost/tx_signer.h"
#include "sost/address.h"
#include "sost/types.h"
#include <cstdio>
#include <vector>

using namespace sost;
static int fails = 0;
#define CHECK(c, m) do { if (!(c)) { printf("FAIL: %s\n", m); ++fails; } else printf("ok: %s\n", m); } while (0)

int main() {
    const Hash256 G = from_hex("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");
    Wallet w; auto k = w.generate_key("default");
    Wallet dst; auto to = dst.generate_key("x");
    Wallet watch;                                             // no keys at all
    for (int i = 0; i < 5; ++i) {
        WalletUTXO u{}; u.txid = from_hex(std::string(63, 'a') + char('1' + i)); u.vout = (uint32_t)i;
        u.amount = 1000000000LL * (i + 1); u.output_type = 0x00; u.pkh = k.pkh; u.height = 10; u.spent = false;
        w.add_utxo(u); watch.add_utxo(u);
    }
    for (int64_t amt : {150000000LL, 2500000000LL, 9000000000LL}) {
        for (bool with_capsule : {false, true}) {
            std::vector<Byte> cap = {'S','C','P','1', 1,1,0,0,0,0,4,0, 'h','i','!','!'};
            const std::vector<Byte>* cp = with_capsule ? &cap : nullptr;
            Transaction a, b; std::string err; std::vector<SpentOutput> sp;
            bool oka = w.create_transaction(to.address, amt, 2000, G, a, 1000, &err, cp, false, &k.pkh);
            bool okb = watch.create_transaction(to.address, amt, 2000, G, b, 1000, &err, cp, false, &k.pkh, nullptr, 10, false, &sp);
            CHECK(oka && okb, "both builds succeed");
            CHECK(b.inputs.size() == sp.size(), "spent list matches inputs");
            bool zero = true; for (auto& in : b.inputs) for (auto x : in.signature) if (x) zero = false;
            CHECK(zero, "unsigned build carries no signature");
            for (size_t i = 0; i < b.inputs.size(); ++i) SignTransactionInput(b, i, sp[i], G, k.privkey, &err);
            std::vector<Byte> ra, rb; a.Serialize(ra); b.Serialize(rb);
            CHECK(ra == rb, with_capsule ? "offline-signed bytes == wallet-signed bytes (capsule)" : "offline-signed bytes == wallet-signed bytes");
            for (size_t i = 0; i < b.inputs.size(); ++i) CHECK(VerifyTransactionInput(b, i, sp[i], G, k.pkh, &err), "signature verifies");
        }
    }
    // watch-only without an explicit source must refuse (never guess whose coins to spend)
    Transaction c; std::string err;
    CHECK(!watch.create_transaction(to.address, 100000000, 2000, G, c, 1000, &err, nullptr, false, nullptr, nullptr, 10, false, nullptr),
          "watch-only build without --from-address refused");
    // default path unchanged: a keyless wallet still cannot build a SIGNED tx
    CHECK(!watch.create_transaction(to.address, 100000000, 2000, G, c, 1000, &err, nullptr, false, &k.pkh),
          "signed build still needs the key");
    printf(fails ? "FAILED %d\n" : "ALL PASS\n", fails);
    return fails ? 1 : 0;
}
