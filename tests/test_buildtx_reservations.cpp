// buildtx reservation ledger (sost/utxo_reservations.h) + the exclusion rule buildtx applies:
// a second watch-only build that excludes the first build's inputs never reuses them, and
// fails with "insufficient" (never a conflicting tx) once every coin is taken.
#include "sost/utxo_reservations.h"
#include "sost/wallet.h"
#include "sost/address.h"
#include "sost/types.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <set>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

using namespace sost;
static int fails = 0;
#define CHECK(c, m) do { if (!(c)) { printf("FAIL: %s\n", m); ++fails; } else printf("ok: %s\n", m); } while (0)

static std::string to_hex(const uint8_t* d, size_t n) {
    static const char* H = "0123456789abcdef"; std::string o;
    for (size_t i = 0; i < n; ++i) { o += H[d[i] >> 4]; o += H[d[i] & 15]; }
    return o;
}
static std::string K(char c, uint32_t v) { return resv::outpoint_key(std::string(64, c), v); }

int main() {
    char tmpl[] = "/tmp/sost-resv-XXXXXX";
    const char* dir = mkdtemp(tmpl);
    if (!dir) { printf("FAIL: mkdtemp\n"); return 1; }
    const std::string path = std::string(dir) + "/r.json";

    // ---- load / save
    resv::Ledger l; std::string err;
    CHECK(resv::load(path, l, &err) && l.items.empty(), "missing ledger loads as empty");
    resv::Reservation a{"sost1aaa", "t1.json", "id1", 1000, 1000 + 3600, {K('a', 0), K('a', 1)}};
    resv::Reservation b{"sost1bbb", "t2.json", "id2", 1000, 1000 + 60, {K('b', 3)}};
    l.items = {a, b};
    CHECK(resv::save(path, l, &err), "save");
    struct stat st{}; stat(path.c_str(), &st);
    CHECK((st.st_mode & 0777) == 0600, "ledger written with mode 0600");
    resv::Ledger r2;
    CHECK(resv::load(path, r2, &err) && r2.items.size() == 2 && r2.items[0].outpoints == a.outpoints
          && r2.items[0].expires_at == a.expires_at && r2.items[1].from == "sost1bbb", "round trip");
    CHECK(access((path + ".tmp").c_str(), F_OK) != 0, "no temp file left behind");

    // ---- fail closed on damage (never silently forget reservations)
    for (const char* bad : {"", "{", "{\"format\":\"other\",\"reservations\":[]}",
                            "{\"format\":\"sost-buildtx-reservations-v1\",\"reservations\":[{\"from\":\"x\"}]}",
                            "{\"format\":\"sost-buildtx-reservations-v1\",\"reservations\":[{\"from\":\"x\",\"created_at\":1,\"expires_at\":2,\"outpoints\":[\"zz:1\"]}]}"}) {
        std::ofstream(path) << bad;
        resv::Ledger x;
        CHECK(!resv::load(path, x, &err), "damaged ledger refused");
    }

    // ---- reserved_for / expiry / prune / clear
    l.items = {a, b};
    auto ra = resv::reserved_for(l, "sost1aaa", 2000);
    CHECK(ra.size() == 2 && ra.count(K('a', 0)) && ra.count(K('a', 1)), "reserved_for returns the address's outpoints");
    CHECK(resv::reserved_for(l, "sost1bbb", 1060).empty(), "expired reservation does not hold coins");
    CHECK(resv::reserved_for(l, "sost1bbb", 1059).size() == 1, "unexpired reservation holds coins");
    {
        resv::Ledger p = l;
        size_t n = resv::prune(p, 2000, "sost1aaa", {K('a', 1), K('c', 9)});
        CHECK(n == 1 && p.items.size() == 1 && p.items[0].from == "sost1aaa", "prune drops expired entries, keeps one with a live outpoint");
        n = resv::prune(p, 2000, "sost1aaa", {K('c', 9)});
        CHECK(n == 1 && p.items.empty(), "prune drops an entry once none of its outpoints is unspent (confirmed)");
        resv::Ledger q = l;
        n = resv::prune(q, 1001, "sost1aaa", {});
        CHECK(n == 1 && q.items.size() == 1 && q.items[0].from == "sost1bbb", "prune never touches another address's live entry");
        resv::Ledger c = l;
        CHECK(resv::clear_from(c, "sost1aaa") == 1 && c.items.size() == 1 && c.items[0].from == "sost1bbb", "clear_from removes only that address");
    }

    // ---- exclusion rule as applied by buildtx (watch-only)
    const Hash256 G = from_hex("6517916b98ab9f807272bf94f89297011dd5512ecea477bd9d692fbafe699f37");
    Wallet src; auto k = src.generate_key("default");
    Wallet dst; auto to = dst.generate_key("x");
    std::vector<WalletUTXO> coins;
    for (int i = 0; i < 4; ++i) {
        WalletUTXO u{}; u.txid = from_hex(std::string(63, 'c') + char('1' + i)); u.vout = (uint32_t)i;
        u.amount = 1000000000LL; u.output_type = 0x00; u.pkh = k.pkh; u.height = 10; u.spent = false;
        coins.push_back(u);
    }
    auto build = [&](const std::set<std::string>& exclude, int64_t amount, Transaction& tx, std::string& e) {
        Wallet w;
        for (const auto& u : coins)
            if (!exclude.count(resv::outpoint_key(to_hex(u.txid.data(), 32), u.vout))) w.add_utxo(u);
        std::vector<SpentOutput> sp;
        return w.create_transaction(to.address, amount, 2000, G, tx, 1000, &e, nullptr, false, &k.pkh, nullptr, 10, false, &sp);
    };
    std::set<std::string> taken;
    Transaction t1, t2, t3; std::string e;
    CHECK(build(taken, 1500000000LL, t1, e), "build A");
    for (auto& in : t1.inputs) taken.insert(resv::outpoint_key(to_hex(in.prev_txid.data(), 32), in.prev_index));
    CHECK(build(taken, 1500000000LL, t2, e), "build B with A's inputs excluded");
    bool disjoint = true;
    for (auto& in : t2.inputs)
        if (taken.count(resv::outpoint_key(to_hex(in.prev_txid.data(), 32), in.prev_index))) disjoint = false;
    CHECK(disjoint, "build B uses inputs disjoint from build A");
    for (auto& in : t2.inputs) taken.insert(resv::outpoint_key(to_hex(in.prev_txid.data(), 32), in.prev_index));
    CHECK(!build(taken, 1500000000LL, t3, e) && e.find("insufficient") != std::string::npos,
          "build C with every coin taken fails as insufficient (no conflicting tx)");

    unlink(path.c_str()); rmdir(dir);
    printf(fails ? "FAILED %d\n" : "ALL PASS\n", fails);
    return fails ? 1 : 0;
}
