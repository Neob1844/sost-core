// test_v13_gold_vault_slice1.cpp
//
// Pure-function tests for the V13 Gold Vault Slice 1 helpers in
// include/sost/gold_vault_slice1.h + src/gold_vault_slice1.cpp.
//
// Two layers:
//
// 1. Sentinel-disabled regression — the default state of the constants
//    (GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX, both whitelists empty,
//    cap == 0, rate-limit == 0) MUST result in gv_slice1_active_at()
//    returning false at every height, gv_slice1_amount_within_cap() and
//    gv_slice1_rate_limit_ok() returning true (sentinel = disabled), and
//    gv_slice1_whitelists_agree() returning true vacuously. This is the
//    fail-closed-design contract: until the operator flips activation
//    and fills the constants, consensus behaviour is bit-identical to
//    pre-Slice-1.
//
// 2. Per-helper correctness — the pure helpers must produce the
//    documented outputs for the boundary inputs (zero balance, cap
//    boundary, rate-limit boundary, invalid inputs).
//
// What this file does NOT test (deferred to the follow-up that flips
// the activation gate + fills the whitelist):
//   - Validator-level wiring in src/block_validation.cpp. With the
//     sentinel state, the wiring block is unreachable, so there is no
//     observable behaviour to exercise. The wiring itself is reviewed
//     visually + by build success + by the existing block_validation
//     test suite continuing to pass.
//   - End-to-end rejection of a real non-whitelisted destination —
//     possible only once the operator commits real whitelist values.
//
#include "sost/gold_vault_slice1.h"
#include "sost/consensus_constants.h"
#include "sost/params.h"

#include <climits>
#include <cstdio>
#include <cstring>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(msg, cond) do { \
    if (cond) { std::printf("  PASS: %s\n", msg); g_pass++; } \
    else { std::printf("  *** FAIL: %s  [%s:%d]\n", msg, __FILE__, __LINE__); g_fail++; } \
} while (0)

// ---------------------------------------------------------------------------
// 1. Sentinel-disabled regression
// ---------------------------------------------------------------------------

static void test_sentinel_constants_pinned() {
    std::printf("\n=== 1) Sentinel constants pinned to disabled defaults ===\n");
#ifndef SOST_TESTNET_FORKS
    // MAINNET: Slice 1 gate stays DEFERRED until the full G1-G5 ships.
    TEST("GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX (mainnet deferred)",
         GV_SLICE1_ACTIVATION_HEIGHT == INT64_MAX);
#endif
    // B1: whitelist now CONFIGURED with the single genesis-miner destination.
    TEST("GV_SLICE1_WHITELIST_PRIMARY_LEN == 1",
         GV_SLICE1_WHITELIST_PRIMARY_LEN == 1);
    TEST("GV_SLICE1_WHITELIST_MIRROR_LEN == 1",
         GV_SLICE1_WHITELIST_MIRROR_LEN == 1);
    TEST("GV_SLICE1_PER_SPEND_CAP_BPS == 0",
         GV_SLICE1_PER_SPEND_CAP_BPS == 0);
    TEST("GV_SLICE1_RATE_LIMIT_BLOCKS == 0",
         GV_SLICE1_RATE_LIMIT_BLOCKS == 0);
    TEST("GV_SLICE1_WHITELIST_MAX == 5",
         GV_SLICE1_WHITELIST_MAX == 5);
    TEST("GV_SLICE1_BPS_DENOMINATOR == 10000",
         GV_SLICE1_BPS_DENOMINATOR == 10000);
    TEST("GV_SLICE1_PKH_LEN == 20",
         GV_SLICE1_PKH_LEN == 20);
}

static void test_activation_gate_sentinel_at_every_height() {
#ifdef SOST_TESTNET_FORKS
    std::printf("\n=== 2) [testnet build: Slice 1 active >= V14_HEIGHT, skipping deferred check] ===\n");
    return;
#endif
    std::printf("\n=== 2) Activation gate is INACTIVE at every height (mainnet deferred) ===\n");
    const int64_t test_heights[] = {
        0, 1, 100, 7100, 9999, 10000, 12000, 12100, 15000, 25000,
        100000, 1000000, INT64_MAX - 1
    };
    for (int64_t h : test_heights) {
        char buf[96];
        std::snprintf(buf, sizeof(buf),
                      "gv_slice1_active_at(h=%lld) == false (sentinel)",
                      (long long)h);
        TEST(buf, gv_slice1_active_at(h) == false);
    }
}

static void test_amount_within_cap_sentinel_disabled() {
    std::printf("\n=== 3) Per-spend cap sentinel-disabled (cap == 0) ===\n");
    // With sentinel cap == 0, every amount within reasonable bounds passes.
    TEST("amount=0, balance=0 → true",
         gv_slice1_amount_within_cap(0, 0) == true);
    TEST("amount=1, balance=1 → true",
         gv_slice1_amount_within_cap(1, 1) == true);
    TEST("amount=1_000_000, balance=1_000_000 → true",
         gv_slice1_amount_within_cap(1'000'000, 1'000'000) == true);
    TEST("amount=SUPPLY_MAX, balance=SUPPLY_MAX → true",
         gv_slice1_amount_within_cap(SUPPLY_MAX_STOCKS, SUPPLY_MAX_STOCKS) == true);
    TEST("amount > balance (overspend) → true (sentinel-disabled means cap not enforced)",
         gv_slice1_amount_within_cap(2'000'000, 1'000'000) == true);
}

static void test_rate_limit_sentinel_disabled() {
    std::printf("\n=== 4) Rate limit sentinel-disabled (rate == 0) ===\n");
    TEST("blocks_since=0 → true",
         gv_slice1_rate_limit_ok(0) == true);
    TEST("blocks_since=1 → true",
         gv_slice1_rate_limit_ok(1) == true);
    TEST("blocks_since=144 → true",
         gv_slice1_rate_limit_ok(144) == true);
    TEST("blocks_since=INT64_MAX → true",
         gv_slice1_rate_limit_ok(INT64_MAX) == true);
}

static void test_whitelists_agree_when_both_empty() {
    std::printf("\n=== 5) Whitelists agree vacuously when both empty ===\n");
    TEST("gv_slice1_whitelists_agree() == true",
         gv_slice1_whitelists_agree() == true);
}

static void test_destination_allowed_returns_false_when_whitelist_empty() {
    std::printf("\n=== 6) gv_slice1_destination_allowed(...) == false at sentinel ===\n");
    // Any candidate PKH should return false when the whitelist is empty.
    PubKeyHash zero_pkh{};
    PubKeyHash ones_pkh{};
    for (auto& b : ones_pkh) b = 0xff;
    PubKeyHash sample_pkh = {0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,
                             0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff,0x00,
                             0x11,0x22,0x33,0x44};
    TEST("zero PKH → not allowed",  gv_slice1_destination_allowed(zero_pkh)   == false);
    TEST("all-ones PKH → not allowed", gv_slice1_destination_allowed(ones_pkh) == false);
    TEST("sample PKH → not allowed", gv_slice1_destination_allowed(sample_pkh) == false);
}

// ---------------------------------------------------------------------------
// 7. Per-helper correctness (boundary conditions, defensive cases)
// ---------------------------------------------------------------------------

static void test_amount_within_cap_defensive() {
    std::printf("\n=== 7) Per-spend cap defensive cases ===\n");
    // Even with sentinel cap == 0 the helper must reject negative inputs
    // when we eventually enable a real cap. We exercise that path via a
    // constexpr-equivalent walkthrough: cap == 0 currently returns true
    // for negatives too (sentinel takes precedence). Document the
    // intended behaviour for the follow-up commit.
    //
    // Negative inputs (defensive): with sentinel == 0, helper returns
    // true unconditionally — this is acceptable because the validator
    // wiring is sentinel-disabled. Once the operator sets a non-zero
    // cap, negative inputs become false (defensive branch in the
    // helper).
    TEST("amount=-1, balance=1 → true (sentinel mode; defensive branch suppressed)",
         gv_slice1_amount_within_cap(-1, 1) == true);
    TEST("amount=1, balance=-1 → true (sentinel mode)",
         gv_slice1_amount_within_cap(1, -1) == true);
}

static void test_rate_limit_defensive() {
    std::printf("\n=== 8) Rate limit defensive cases ===\n");
    // Same pattern: sentinel mode returns true even for negative inputs.
    TEST("blocks_since=-1 → true (sentinel mode)",
         gv_slice1_rate_limit_ok(-1) == true);
    TEST("blocks_since=-1_000_000 → true (sentinel mode)",
         gv_slice1_rate_limit_ok(-1'000'000) == true);
}

// ---------------------------------------------------------------------------
// 9. tx-spends-from-vault helper (synthetic Transaction)
// ---------------------------------------------------------------------------

static void test_tx_spends_from_vault_via_lookup() {
    std::printf("\n=== 9) gv_slice1_tx_spends_from_vault uses the lookup callback ===\n");

    PubKeyHash vault_pkh = {0x11,0x11,0x11,0x11,0x11,0x11,0x11,0x11,
                            0x11,0x11,0x11,0x11,0x11,0x11,0x11,0x11,
                            0x11,0x11,0x11,0x11};
    PubKeyHash other_pkh = {0x22,0x22,0x22,0x22,0x22,0x22,0x22,0x22,
                            0x22,0x22,0x22,0x22,0x22,0x22,0x22,0x22,
                            0x22,0x22,0x22,0x22};

    Transaction tx;
    {
        TxInput in1;
        in1.prev_txid = Hash256{};
        in1.prev_index = 0;
        tx.inputs.push_back(in1);
    }
    {
        TxInput in2;
        in2.prev_txid = Hash256{};
        in2.prev_index = 1;
        tx.inputs.push_back(in2);
    }

    // Lookup returns vault PKH for the first input, other PKH for the second.
    auto lookup_a = [&](const Hash256&, uint32_t idx, PubKeyHash& out) -> bool {
        out = (idx == 0) ? vault_pkh : other_pkh;
        return true;
    };
    TEST("tx with one vault input → spends_from_vault == true",
         gv_slice1_tx_spends_from_vault(tx, vault_pkh, lookup_a) == true);

    // Lookup returns other PKH for both inputs.
    auto lookup_b = [&](const Hash256&, uint32_t, PubKeyHash& out) -> bool {
        out = other_pkh;
        return true;
    };
    TEST("tx with no vault input → spends_from_vault == false",
         gv_slice1_tx_spends_from_vault(tx, vault_pkh, lookup_b) == false);

    // Lookup returns false (UTXO not found) for every input.
    auto lookup_miss = [&](const Hash256&, uint32_t, PubKeyHash&) -> bool {
        return false;
    };
    TEST("tx with all-missing inputs → spends_from_vault == false",
         gv_slice1_tx_spends_from_vault(tx, vault_pkh, lookup_miss) == false);
}

// ---------------------------------------------------------------------------
// 10. Documentation regression — the comment in the header says the
//      validator wiring is a no-op at sentinel defaults. Pin a tiny
//      static check that no helper rejects in the default state.
// ---------------------------------------------------------------------------

static void test_sentinel_state_is_complete_noop() {
    std::printf("\n=== 10) Sentinel default state is a complete consensus no-op ===\n");
    // Every helper used by the validator wiring must return the "allow"
    // value at the default sentinel state, OR be gated behind
    // gv_slice1_active_at which returns false at every height.
    //
    // gv_slice1_active_at(h) — false at every height (test #2).
    // gv_slice1_whitelists_agree() — true (test #5).
    //   The wiring only calls this once active, but the documented
    //   contract says agreement holds vacuously at default.
    // gv_slice1_destination_allowed(...) — false at every PKH (test #6).
    //   The wiring only calls this once active. If activation is ever
    //   flipped without filling the whitelist, every destination
    //   becomes rejected (fail-closed). This is the intended safety
    //   net documented in include/sost/gold_vault_slice1.h.
    // gv_slice1_amount_within_cap(...) — true at every amount (test #3).
    //   Cap == 0 means cap-disabled, helper passes everything.
    // gv_slice1_rate_limit_ok(...) — true at every blocks_since (test #4).
    //   Rate-limit == 0 means disabled, helper passes everything.
#ifndef SOST_TESTNET_FORKS
    TEST("active_at any sample height is false (mainnet deferred)",
         gv_slice1_active_at(0) == false
         && gv_slice1_active_at(12000) == false
         && gv_slice1_active_at(INT64_MAX - 1) == false);
#endif
    TEST("whitelists_agree vacuously",
         gv_slice1_whitelists_agree() == true);
    TEST("amount_within_cap permits any amount",
         gv_slice1_amount_within_cap(0, 0) == true
         && gv_slice1_amount_within_cap(SUPPLY_MAX_STOCKS, 1) == true);
    TEST("rate_limit_ok permits any interval",
         gv_slice1_rate_limit_ok(0) == true
         && gv_slice1_rate_limit_ok(INT64_MAX) == true);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

int main() {
    std::printf("=== test_v13_gold_vault_slice1 (V13 Gold Vault Slice 1 G1-G3) ===\n");
    test_sentinel_constants_pinned();
    test_activation_gate_sentinel_at_every_height();
    test_amount_within_cap_sentinel_disabled();
    test_rate_limit_sentinel_disabled();
    test_whitelists_agree_when_both_empty();
    test_destination_allowed_returns_false_when_whitelist_empty();
    test_amount_within_cap_defensive();
    test_rate_limit_defensive();
    test_tx_spends_from_vault_via_lookup();
    test_sentinel_state_is_complete_noop();

    std::printf("\n=== Summary: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
