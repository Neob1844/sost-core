// test_type_registry.cpp — type-registry ctest (NON-CONSENSUS, no runtime change)
//
// 1. Compile time: include/sost/type_registry.h static_asserts uniqueness, literal
//    pins, reserved ranges and the cross-namespace grandfather list.
// 2. Run time: sweeps the CURRENT validators (R2 tx-type allow-list, R11 output-type
//    allow-list) over all 256 codes at representative mainnet-build heights and
//    checks they accept exactly the set the registry says is creatable there. In
//    particular 0x50 (planned OUT_MULTISIG) and 0x20 (OUT_BURN) are rejected at
//    every height, including 40,000.
// 3. Legacy fence: the legacy script engine (script.h / OUT_SCRIPT_HASH = 0x30, which
//    collided with the live OUT_NODE_PROTOCOL = 0x30) and the PSBT library have been
//    DELETED (spec §2.3 step 3). The fence now asserts the files do not exist and that
//    no production source file references them.
//
// Usage: test-type-registry <source-dir>
#include "sost/type_registry.h"
#include "sost/tx_validation.h"
#include "sost/params.h"
#include "sost/atomic_swap.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include <dirent.h>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, msg) do { if (cond) { ++g_pass; } else { ++g_fail; \
    std::printf("  FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); } } while (0)

// The live meaning of output type 0x30 is OUT_NODE_PROTOCOL; it must never be
// reinterpreted (the deleted legacy engine used 0x30 as OUT_SCRIPT_HASH).
static_assert(OUT_NODE_PROTOCOL == 0x30, "0x30 is the live OUT_NODE_PROTOCOL output type");

class EmptyUtxoView : public IUtxoView {
public:
    std::optional<UTXOEntry> GetUTXO(const OutPoint&) const override { return std::nullopt; }
};

static Transaction base_tx(uint8_t tx_type, uint8_t out_type) {
    Transaction tx;
    tx.version = 1;
    tx.tx_type = tx_type;
    TxInput in;
    in.prev_txid.fill(0x11);
    in.prev_index = 0;
    tx.inputs.push_back(in);
    TxOutput o;
    o.amount = 1'000'000;
    o.type = out_type;
    o.pubkey_hash.fill(0x22);
    tx.outputs.push_back(o);
    return tx;
}

static TxValidationContext ctx_at(int64_t h) {
    TxValidationContext c;
    c.spend_height = h;
    return c;   // mainnet capsule/bond activation defaults
}

// Output types a non-coinbase tx may create at height h on THIS build, derived
// from the registry statuses plus the documented activation gates.
static std::set<int> expected_r11_active(int64_t h) {
    std::set<int> s = {OUT_TRANSFER, OUT_COINBASE_MINER, OUT_COINBASE_GOLD, OUT_COINBASE_POPC};
    if (h >= BOND_ACTIVATION_HEIGHT_MAINNET) { s.insert(OUT_BOND_LOCK); s.insert(OUT_ESCROW_LOCK); }
    if (atomic_swap_htlc_active_at(h)) { s.insert(OUT_HTLC_LOCK); s.insert(OUT_HTLC_CLAIM_WITNESS); }
    if (native_assets_active_at(h)) {
        for (const auto& e : type_registry::OUTPUT_TYPES)
            if (e.status == type_registry::Status::DORMANT) s.insert(e.code);
    }
    return s;
}
static std::set<int> expected_r2_allowed(int64_t h) {
    // ValidateTransactionConsensus routes COINBASE to its own validator (R2 here).
    std::set<int> s = {TX_TYPE_STANDARD};
    if (atomic_swap_htlc_active_at(h)) { s.insert(TX_TYPE_HTLC_CLAIM); s.insert(TX_TYPE_HTLC_REFUND); }
    if (native_assets_active_at(h)) {
        for (const auto& e : type_registry::TX_TYPES)
            if (e.status == type_registry::Status::DORMANT) s.insert(e.code);
    }
    return s;
}

static void sweep(int64_t h) {
    EmptyUtxoView v;
    const auto ctx = ctx_at(h);
    const auto exp_out = expected_r11_active(h);
    const auto exp_tx = expected_r2_allowed(h);
    int out_mismatch = 0, tx_mismatch = 0;
    for (int code = 0; code < 256; ++code) {
        auto r = ValidateTransactionConsensus(base_tx(TX_TYPE_STANDARD, (uint8_t)code), v, ctx);
        bool rejected_r11 = (!r.ok && r.code == TxValCode::R11_INACTIVE_TYPE);
        bool expect_active = exp_out.count(code) > 0;
        if (rejected_r11 == expect_active) {
            ++out_mismatch;
            std::printf("  R11 mismatch h=%lld out_type=0x%02x expected_active=%d got_code=%d\n",
                        (long long)h, code, (int)expect_active, (int)r.code);
        }
        auto t = ValidateTransactionConsensus(base_tx((uint8_t)code, OUT_TRANSFER), v, ctx);
        bool rejected_r2 = (!t.ok && t.code == TxValCode::R2_BAD_TX_TYPE);
        bool expect_allowed = exp_tx.count(code) > 0;
        if (rejected_r2 == expect_allowed) {
            ++tx_mismatch;
            std::printf("  R2 mismatch h=%lld tx_type=0x%02x expected_allowed=%d got_code=%d\n",
                        (long long)h, code, (int)expect_allowed, (int)t.code);
        }
    }
    char msg[160];
    std::snprintf(msg, sizeof msg, "R11 output-type allow-list == registry set at h=%lld", (long long)h);
    CHECK(out_mismatch == 0, msg);
    std::snprintf(msg, sizeof msg, "R2 tx-type allow-list == registry set at h=%lld", (long long)h);
    CHECK(tx_mismatch == 0, msg);

    // Explicit pins.
    auto r50 = ValidateTransactionConsensus(base_tx(TX_TYPE_STANDARD, type_registry::OUT_MULTISIG_PLANNED), v, ctx);
    std::snprintf(msg, sizeof msg, "0x50 (planned OUT_MULTISIG) rejected by R11 at h=%lld", (long long)h);
    CHECK(!r50.ok && r50.code == TxValCode::R11_INACTIVE_TYPE, msg);
    auto r20 = ValidateTransactionConsensus(base_tx(TX_TYPE_STANDARD, OUT_BURN), v, ctx);
    std::snprintf(msg, sizeof msg, "0x20 OUT_BURN rejected by R11 at h=%lld", (long long)h);
    CHECK(!r20.ok && r20.code == TxValCode::R11_INACTIVE_TYPE, msg);
    auto r30 = ValidateTransactionConsensus(base_tx(TX_TYPE_STANDARD, OUT_NODE_PROTOCOL), v, ctx);
    std::snprintf(msg, sizeof msg, "0x30 OUT_NODE_PROTOCOL not creatable by a standard tx at h=%lld", (long long)h);
    CHECK(!r30.ok && r30.code == TxValCode::R11_INACTIVE_TYPE, msg);
    // Version 2 is not a valid transaction version today, at any height.
    auto tv2 = base_tx(TX_TYPE_STANDARD, OUT_TRANSFER); tv2.version = 2;
    auto rv2 = ValidateTransactionConsensus(tv2, v, ctx);
    std::snprintf(msg, sizeof msg, "tx version 2 rejected by R1 at h=%lld", (long long)h);
    CHECK(!rv2.ok && rv2.code == TxValCode::R1_BAD_VERSION, msg);
}

// ---- legacy fence (source scan) -------------------------------------------
static bool read_file(const std::string& p, std::string& out) {
    std::ifstream f(p, std::ios::binary);
    if (!f) return false;
    std::ostringstream ss; ss << f.rdbuf(); out = ss.str();
    return true;
}
static std::vector<std::string> list_dir(const std::string& d) {
    std::vector<std::string> v;
    if (DIR* dp = opendir(d.c_str())) {
        while (dirent* e = readdir(dp)) {
            std::string n = e->d_name;
            if (n.size() > 2 && (n.rfind(".cpp") == n.size() - 4 || n.rfind(".h") == n.size() - 2))
                v.push_back(n);
        }
        closedir(dp);
    }
    return v;
}

static void legacy_fence(const std::string& root) {
    // The legacy engine is deleted: no production file may mention it. The registry
    // header documents the deletion and is the only allowed mention.
    const std::set<std::string> allowed = {"include/sost/type_registry.h"};
    for (const char* gone : {"include/sost/script.h", "src/script.cpp",
                             "include/sost/psbt.h", "src/psbt.cpp",
                             "tests/test_multisig.cpp", "tests/test_psbt.cpp"}) {
        std::string tmp;
        char m[160];
        std::snprintf(m, sizeof m, "legacy_files_absent: %s does not exist", gone);
        CHECK(!read_file(root + "/" + gone, tmp), m);
    }
    {
        std::string cm;
        CHECK(read_file(root + "/CMakeLists.txt", cm) &&
              cm.find("src/script.cpp") == std::string::npos &&
              cm.find("src/psbt.cpp") == std::string::npos &&
              cm.find("tests/test_psbt.cpp") == std::string::npos &&
              cm.find("tests/test_multisig.cpp") == std::string::npos,
              "legacy_files_absent: CMakeLists.txt no longer builds script/psbt or their tests");
    }
    const char* needles[] = {"sost/script.h", "sost/psbt.h", "OUT_SCRIPT_HASH", "eval_script",
                             "eval_p2sh", "MULTISIG_ACTIVATION_HEIGHT"};
    int scanned = 0, violations = 0;
    for (const char* dir : {"src", "src/pow", "include/sost"}) {
        for (const auto& n : list_dir(root + "/" + dir)) {
            std::string rel = std::string(dir) + "/" + n;
            if (allowed.count(rel)) continue;
            std::string body;
            if (!read_file(root + "/" + rel, body)) continue;
            ++scanned;
            for (const char* nd : needles) {
                if (body.find(nd) != std::string::npos) {
                    ++violations;
                    std::printf("  legacy reference '%s' in %s\n", nd, rel.c_str());
                }
            }
        }
    }
    char msg[160];
    std::snprintf(msg, sizeof msg, "source scan covered the tree (%d files)", scanned);
    CHECK(scanned > 50, msg);
    CHECK(violations == 0, "no production file references script.h / psbt.h / OUT_SCRIPT_HASH / eval_script");
    std::string reg;
    CHECK(read_file(root + "/include/sost/type_registry.h", reg) &&
          reg.find("{OUT_SCRIPT_HASH") == std::string::npos,
          "OUT_SCRIPT_HASH is not a registry entry");
}

int main(int argc, char** argv) {
    std::printf("=== type-registry (non-consensus inventory + fence) ===\n");
    std::printf("  tx types: %zu  output types: %zu  (compile-time invariants passed)\n",
                sizeof(type_registry::TX_TYPES) / sizeof(type_registry::TX_TYPES[0]),
                sizeof(type_registry::OUTPUT_TYPES) / sizeof(type_registry::OUTPUT_TYPES[0]));
#if defined(SOST_TESTNET_FORKS) || defined(SOST_DEVNET_FORKS)
    std::printf("  non-mainnet build: runtime sweep skipped (mainnet heights only)\n");
#else
    for (int64_t h : {(int64_t)7349, (int64_t)15999, (int64_t)16000, (int64_t)30000,
                      (int64_t)39999, (int64_t)40000, (int64_t)50000})
        sweep(h);
#endif
    if (argc >= 2) legacy_fence(argv[1]);
    else { ++g_fail; std::printf("  FAIL: source dir argument missing\n"); }
    std::printf("=== %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
