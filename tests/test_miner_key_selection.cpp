// V11 Phase 2 — Miner-key selection tests (Commit 3 scope).
//
// Exercises sost::sbpow::resolve_miner_key() against a Wallet fixture
// with two labelled keys. The test is self-contained: it builds the
// Wallet in-memory via Wallet::import_privkey() — no file I/O, no need
// to write a wallet.json fixture.
//
// Cases:
//   1. select by label succeeds → OK_SIGNING_KEY
//   2. missing label fails      → ERROR
//   3. --address matching the selected key is allowed
//   4. --address mismatching the selected key aborts
//   5. pre-Phase 2 path (no flags) does not require wallet key
//   6. Phase 2 path (no flags) requires wallet key
//   7. Phase 2 path (label only, --address mismatch) still aborts
//   8. label given but wallet has no keys at all → ERROR

#include "sost/sbpow.h"
#include "sost/wallet.h"
#include "sost/tx_signer.h"

#include <cstdio>
#include <cstring>
#include <string>

using namespace sost;
using namespace sost::sbpow;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { printf("  PASS: %s\n", msg); g_pass++; } \
    else { printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static PrivKey fixture_priv(uint8_t seed) {
    PrivKey p{};
    for (size_t i = 0; i < 32; ++i) p[i] = (uint8_t)(seed ^ (i * 5));
    return p;
}

static Wallet build_two_key_wallet(std::string& addr_mining,
                                   std::string& addr_payouts) {
    Wallet w;
    WalletKey k_mining  = w.import_privkey(fixture_priv(0x10), "mining");
    WalletKey k_payouts = w.import_privkey(fixture_priv(0x80), "payouts");
    addr_mining  = k_mining.address;
    addr_payouts = k_payouts.address;
    return w;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

static void test_label_match_succeeds() {
    printf("\n=== label match succeeds ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    auto res = resolve_miner_key(w, "mining", /*explicit_address=*/"",
                                 /*phase2_required=*/false);
    TEST("status == OK_SIGNING_KEY",
         res.status == MinerKeyResolution::Status::OK_SIGNING_KEY);
    TEST("resolved address matches mining-key address",
         res.address == addr_m);
    TEST("resolved label is 'mining'", res.label == "mining");
    TEST("pkh non-zero",
         res.pkh != PubKeyHash{});
}

static void test_label_match_succeeds_phase2() {
    printf("\n=== label match succeeds — phase2_required path ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    auto res = resolve_miner_key(w, "mining", /*explicit_address=*/"",
                                 /*phase2_required=*/true);
    TEST("Phase 2 + valid label -> OK_SIGNING_KEY",
         res.status == MinerKeyResolution::Status::OK_SIGNING_KEY);
}

static void test_missing_label_fails() {
    printf("\n=== missing label fails ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    auto res = resolve_miner_key(w, "this-label-does-not-exist", "",
                                 /*phase2_required=*/false);
    TEST("missing label -> ERROR",
         res.status == MinerKeyResolution::Status::ERROR);
    TEST("error mentions the missing label",
         res.error.find("this-label-does-not-exist") != std::string::npos);
}

static void test_address_matching_selected_key_allowed() {
    printf("\n=== --address matching selected key is allowed ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    auto res = resolve_miner_key(w, "mining", /*explicit_address=*/addr_m,
                                 /*phase2_required=*/false);
    TEST("matching --address -> OK_SIGNING_KEY",
         res.status == MinerKeyResolution::Status::OK_SIGNING_KEY);
    TEST("resolved address equals the explicit address",
         res.address == addr_m);
}

static void test_address_mismatch_aborts() {
    printf("\n=== --address mismatching selected key aborts ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    // Pass the OTHER key's address with label='mining' -> mismatch.
    auto res = resolve_miner_key(w, "mining", /*explicit_address=*/addr_p,
                                 /*phase2_required=*/false);
    TEST("mismatched --address -> ERROR",
         res.status == MinerKeyResolution::Status::ERROR);
    TEST("error mentions both addresses",
         res.error.find(addr_p) != std::string::npos &&
         res.error.find(addr_m) != std::string::npos);
}

static void test_address_mismatch_aborts_under_phase2() {
    printf("\n=== --address mismatch aborts under phase2_required too ===\n");
    std::string addr_m, addr_p;
    Wallet w = build_two_key_wallet(addr_m, addr_p);

    auto res = resolve_miner_key(w, "mining", /*explicit_address=*/addr_p,
                                 /*phase2_required=*/true);
    TEST("Phase 2 + mismatched --address -> ERROR",
         res.status == MinerKeyResolution::Status::ERROR);
}

static void test_pre_phase2_no_wallet_path_is_legacy() {
    printf("\n=== pre-Phase 2 + no wallet flags is legacy path ===\n");
    Wallet empty_w;  // no keys

    auto res = resolve_miner_key(empty_w, /*label=*/"",
                                 /*explicit_address=*/"sost1abc...",
                                 /*phase2_required=*/false);
    TEST("no label + pre-Phase 2 -> OK_PRE_PHASE2_LEGACY",
         res.status == MinerKeyResolution::Status::OK_PRE_PHASE2_LEGACY);

    // Same with both fields empty.
    auto res2 = resolve_miner_key(empty_w, "", "",
                                  /*phase2_required=*/false);
    TEST("empty everything + pre-Phase 2 -> OK_PRE_PHASE2_LEGACY",
         res2.status == MinerKeyResolution::Status::OK_PRE_PHASE2_LEGACY);
}

static void test_phase2_requires_wallet_key() {
    printf("\n=== Phase 2 requires --wallet + --mining-key-label ===\n");
    Wallet empty_w;

    // No flags, phase2_required.
    auto res = resolve_miner_key(empty_w, "", "", /*phase2_required=*/true);
    TEST("Phase 2 + no flags -> ERROR",
         res.status == MinerKeyResolution::Status::ERROR);
    TEST("error explains Phase 2 requirement",
         res.error.find("Phase 2") != std::string::npos);

    // --address only, phase2_required.
    auto res2 = resolve_miner_key(empty_w, "", "sost1abc...",
                                  /*phase2_required=*/true);
    TEST("Phase 2 + --address only -> ERROR",
         res2.status == MinerKeyResolution::Status::ERROR);
}

static void test_label_given_but_wallet_empty() {
    printf("\n=== label given but wallet has zero keys -> ERROR ===\n");
    Wallet empty_w;
    auto res = resolve_miner_key(empty_w, "mining", "", /*phase2_required=*/false);
    TEST("label vs empty wallet -> ERROR",
         res.status == MinerKeyResolution::Status::ERROR);
    TEST("error mentions the label",
         res.error.find("mining") != std::string::npos);
}

int main() {
    printf("=== test_miner_key_selection (V11 Phase 2 C3) ===\n");

    test_label_match_succeeds();
    test_label_match_succeeds_phase2();
    test_missing_label_fails();
    test_address_matching_selected_key_allowed();
    test_address_mismatch_aborts();
    test_address_mismatch_aborts_under_phase2();
    test_pre_phase2_no_wallet_path_is_legacy();
    test_phase2_requires_wallet_key();
    test_label_given_but_wallet_empty();

    printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
