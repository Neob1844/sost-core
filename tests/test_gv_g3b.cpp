// =============================================================================
// test_gv_g3b.cpp — Gold Vault G3b: rate-limit (timelock) + cumulative cap.
//
// Proves:
//   (1) the pure G3b helpers (gv_g3b.h) behave for every edge case;
//   (2) the spec scenarios — valid spend, before-timelock, over-cumulative-cap,
//       over-per-spend-cap (G3a), bad-whitelist (G1) — resolve correctly;
//   (3) the LIVE consensus sentinels stay 0 (disabled) → G3b is wired but INERT,
//       so the chain replays byte-identical until a coordinated activation;
//   (4) the deriver algorithm (mirrored from gv_g3b_derive_state in
//       src/sost-node.cpp) is REPLAY-DETERMINISTIC and REORG-SAFE: it is a pure
//       function of the active chain, so a shorter (reorged) chain yields the
//       chain-appropriate cumulative outflow with nothing stale to roll back.
//
// Activates nothing; moves no funds; signs nothing.
// =============================================================================
#include "sost/gv_g3b.h"
#include "sost/gold_vault_slice1.h"   // G1 whitelist + G3a abs cap (cross-checks)
#include "sost/consensus_constants.h" // STOCKS_PER_SOST

#include <climits>
#include <cstdint>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

using namespace sost;

static int g_pass = 0, g_fail = 0;
#define TEST(name) \
    static void test_##name(); \
    struct reg_##name { reg_##name() { tests().push_back({#name, test_##name}); } } r_##name; \
    static void test_##name()
static std::vector<std::pair<std::string, void(*)()>>& tests() {
    static std::vector<std::pair<std::string, void(*)()>> t; return t;
}
#define EXPECT(c, m) do { if(!(c)){ std::cerr<<"  EXPECT failed: "<<m<<"  ["<<__FILE__<<":"<<__LINE__<<"]\n"; g_fail++; return; } } while(0)

static const int64_t SOST = STOCKS_PER_SOST;

// ---------------------------------------------------------------------------
// (1) Pure helpers — rate-limit
// ---------------------------------------------------------------------------
TEST(G3B01_rate_ok_disabled_sentinel) {
    EXPECT(gv_g3b_rate_ok(0, 0)   == true,  "rate_blocks 0 -> disabled -> ok");
    EXPECT(gv_g3b_rate_ok(0, -5)  == true,  "rate_blocks <0 -> disabled -> ok");
    EXPECT(gv_g3b_rate_ok(1, 0)   == true,  "disabled ignores blocks_since");
}
TEST(G3B02_rate_ok_enforced) {
    EXPECT(gv_g3b_rate_ok(144, 144) == true,  "exactly at window -> ok (inclusive)");
    EXPECT(gv_g3b_rate_ok(145, 144) == true,  "past window -> ok");
    EXPECT(gv_g3b_rate_ok(143, 144) == false, "before window -> blocked (timelock)");
    EXPECT(gv_g3b_rate_ok(0,   144) == false, "same block -> blocked");
    EXPECT(gv_g3b_rate_ok(-1,  144) == false, "defensive: negative -> blocked");
}

// ---------------------------------------------------------------------------
// (1) Pure helpers — cumulative cap
// ---------------------------------------------------------------------------
TEST(G3B03_cumulative_ok_disabled_sentinel) {
    EXPECT(gv_g3b_cumulative_ok(999999 * SOST, 0)  == true, "cap 0 -> disabled -> ok");
    EXPECT(gv_g3b_cumulative_ok(999999 * SOST, -1) == true, "cap <0 -> disabled -> ok");
}
TEST(G3B04_cumulative_ok_enforced) {
    int64_t cap = 10 * SOST;
    EXPECT(gv_g3b_cumulative_ok(10 * SOST, cap) == true,  "exactly at cap -> ok (inclusive)");
    EXPECT(gv_g3b_cumulative_ok(9  * SOST, cap) == true,  "under cap -> ok");
    EXPECT(gv_g3b_cumulative_ok(10 * SOST + 1, cap) == false, "1 stock over cap -> blocked");
    EXPECT(gv_g3b_cumulative_ok(11 * SOST, cap) == false, "over cap -> blocked");
    EXPECT(gv_g3b_cumulative_ok(-1, cap) == false, "defensive: negative/overflow -> blocked");
}

// ---------------------------------------------------------------------------
// (1) Pure helpers — blocks_since from derived state
// ---------------------------------------------------------------------------
TEST(G3B05_blocks_since) {
    GvG3bState none;                       // last_spend_height = -1
    EXPECT(gv_g3b_blocks_since(none, 5000) == INT64_MAX, "no prior spend -> INT64_MAX (rate trivially ok)");
    GvG3bState prior; prior.last_spend_height = 1000;
    EXPECT(gv_g3b_blocks_since(prior, 1144) == 144, "1144-1000 = 144");
    EXPECT(gv_g3b_blocks_since(prior, 1000) == 0,   "defensive: same height -> 0");
    EXPECT(gv_g3b_blocks_since(prior, 999)  == 0,   "defensive: non-monotonic -> 0");
}

// ---------------------------------------------------------------------------
// (2) Spec scenarios, using the PILOT target values via parameterised helpers
// ---------------------------------------------------------------------------
TEST(G3B06_valid_spend) {
    // First-ever spend of 1 SOST: no prior spend (rate trivially ok), cumulative 1 <= 10.
    GvG3bState st;  // none
    int64_t since = gv_g3b_blocks_since(st, 20000);
    EXPECT(gv_g3b_rate_ok(since, GV_G3B_PILOT_RATE_LIMIT_BLOCKS) == true, "no prior -> rate ok");
    int64_t cumulative_after = st.cumulative_outflow + 1 * SOST;
    EXPECT(gv_g3b_cumulative_ok(cumulative_after, GV_G3B_PILOT_CUMULATIVE_CAP_STOCKS) == true,
           "1 SOST <= 10 SOST cumulative");
    EXPECT(gv_slice1_amount_within_abs_cap(1 * SOST) == true, "1 SOST within G3a per-spend cap");
}
TEST(G3B07_before_timelock_blocked) {
    GvG3bState st; st.last_spend_height = 20000; st.cumulative_outflow = 1 * SOST;
    int64_t since = gv_g3b_blocks_since(st, 20000 + 100);   // only 100 < 144
    EXPECT(gv_g3b_rate_ok(since, GV_G3B_PILOT_RATE_LIMIT_BLOCKS) == false,
           "100 blocks since last spend < 144 -> timelock blocks it");
}
TEST(G3B08_over_cumulative_cap_blocked) {
    GvG3bState st; st.last_spend_height = 20000; st.cumulative_outflow = 9 * SOST + 50 * SOST/100;
    int64_t since = gv_g3b_blocks_since(st, 20000 + 200);    // 200 >= 144 -> rate ok
    EXPECT(gv_g3b_rate_ok(since, GV_G3B_PILOT_RATE_LIMIT_BLOCKS) == true, "rate ok at 200 blocks");
    int64_t cumulative_after = st.cumulative_outflow + 1 * SOST;  // 9.5 + 1 = 10.5 > 10
    EXPECT(gv_g3b_cumulative_ok(cumulative_after, GV_G3B_PILOT_CUMULATIVE_CAP_STOCKS) == false,
           "9.5 + 1 = 10.5 SOST > 10 SOST cumulative cap -> blocked");
}
TEST(G3B09_over_per_spend_cap_is_G3a) {
    // The per-spend cap is G3a (gold_vault_slice1.h); G3b sits on top of it.
    EXPECT(gv_slice1_amount_within_abs_cap(GV_SLICE1_PER_SPEND_CAP_STOCKS)     == true,  "at G3a cap ok");
    EXPECT(gv_slice1_amount_within_abs_cap(GV_SLICE1_PER_SPEND_CAP_STOCKS + 1) == false, "over G3a cap blocked");
}
TEST(G3B10_bad_whitelist_is_G1) {
    // Destination whitelist is G1; a non-whitelisted dest is rejected before G3b.
    const PubKeyHash& good = GV_SLICE1_WHITELIST_PRIMARY[0];
    PubKeyHash bad{};  // all-zero -> not the whitelisted PKH
    EXPECT(gv_slice1_destination_allowed(good) == true,  "whitelisted dest allowed (G1)");
    EXPECT(gv_slice1_destination_allowed(bad)  == false, "non-whitelisted dest rejected (G1)");
}

// ---------------------------------------------------------------------------
// (3) LIVE consensus sentinels stay disabled -> G3b wired but INERT
// ---------------------------------------------------------------------------
TEST(G3B11_live_sentinels_disabled) {
    EXPECT(GV_SLICE1_RATE_LIMIT_BLOCKS    == 0, "live rate-limit sentinel disabled (0)");
    EXPECT(GV_SLICE1_CUMULATIVE_CAP_STOCKS == 0, "live cumulative cap sentinel disabled (0)");
    // With both sentinels 0 the wired helpers are pure no-ops at consensus.
    EXPECT(gv_g3b_rate_ok(0, GV_SLICE1_RATE_LIMIT_BLOCKS) == true, "inert rate -> always ok");
    EXPECT(gv_g3b_cumulative_ok(INT64_MAX/2, GV_SLICE1_CUMULATIVE_CAP_STOCKS) == true,
           "inert cumulative -> always ok");
    // Pilot targets mirror the dry-run rails.
    EXPECT(GV_G3B_PILOT_RATE_LIMIT_BLOCKS == 144, "pilot rate target = 144 blocks");
    EXPECT(GV_G3B_PILOT_CUMULATIVE_CAP_STOCKS == 10 * SOST, "pilot cumulative target = 10 SOST");
}

// ---------------------------------------------------------------------------
// (4) Deriver algorithm mirror — replay determinism + reorg safety.
//     Mirrors gv_g3b_derive_state (src/sost-node.cpp): forward-scan a chain
//     tracking live vault outpoints, accumulating external outflow on each spend.
// ---------------------------------------------------------------------------
namespace {
struct TIn  { int from_tx; uint32_t vout; };   // references an earlier tx's output
struct TOut { bool to_vault; int64_t amount; };
struct TTx  { int64_t height; std::vector<TIn> ins; std::vector<TOut> outs; };

// Deterministic re-implementation of gv_g3b_derive_state over a synthetic chain.
GvG3bState derive(const std::vector<TTx>& chain) {
    GvG3bState st;
    std::vector<std::vector<bool>> live;   // live[tx][vout] = vault outpoint still unspent
    live.resize(chain.size());
    for (size_t t = 0; t < chain.size(); ++t) {
        const TTx& tx = chain[t];
        bool spends_vault = false;
        for (const auto& in : tx.ins) {
            if (in.from_tx >= 0 && (size_t)in.from_tx < live.size() &&
                in.vout < live[in.from_tx].size() && live[in.from_tx][in.vout]) {
                spends_vault = true;
                live[in.from_tx][in.vout] = false;   // consume
            }
        }
        if (spends_vault) {
            int64_t external = 0;
            for (const auto& o : tx.outs) if (!o.to_vault) external += o.amount;
            st.last_spend_height = tx.height;
            st.cumulative_outflow += external;
        }
        live[t].resize(tx.outs.size(), false);
        for (size_t o = 0; o < tx.outs.size(); ++o) live[t][o] = tx.outs[o].to_vault;
    }
    return st;
}
} // namespace

TEST(G3B12_derive_accumulates_across_spends) {
    // tx0: coinbase -> vault 5 SOST (vout0). tx1 @h100 spends it -> 2 SOST external + 3 change to vault.
    // tx2 @h300 spends the 3-SOST change -> 1 SOST external. Cumulative = 3 SOST, last = 300.
    std::vector<TTx> chain = {
        {  10, {},                 {{true, 5*SOST}} },                         // tx0
        { 100, {{0,0}},            {{false, 2*SOST}, {true, 3*SOST}} },        // tx1 spend
        { 300, {{1,1}},            {{false, 1*SOST}} },                        // tx2 spend
    };
    GvG3bState st = derive(chain);
    EXPECT(st.last_spend_height == 300, "last spend height = 300");
    EXPECT(st.cumulative_outflow == 3*SOST, "cumulative outflow = 2 + 1 = 3 SOST");
}
TEST(G3B13_replay_deterministic) {
    std::vector<TTx> chain = {
        {  10, {}, {{true, 5*SOST}} },
        { 100, {{0,0}}, {{false, 2*SOST}, {true, 3*SOST}} },
    };
    EXPECT(derive(chain).cumulative_outflow == derive(chain).cumulative_outflow,
           "same chain -> identical derived state (deterministic)");
    EXPECT(derive(chain).last_spend_height == 100, "deterministic last height");
}
TEST(G3B14_reorg_safe_truncation) {
    // Full chain has two spends (cumulative 3 SOST, last 300). A reorg that drops
    // the tx2 block re-derives to ONLY the surviving spend: cumulative 2, last 100.
    std::vector<TTx> full = {
        {  10, {}, {{true, 5*SOST}} },
        { 100, {{0,0}}, {{false, 2*SOST}, {true, 3*SOST}} },
        { 300, {{1,1}}, {{false, 1*SOST}} },
    };
    std::vector<TTx> reorged(full.begin(), full.begin() + 2);  // tx2 rolled back
    GvG3bState a = derive(full), b = derive(reorged);
    EXPECT(a.cumulative_outflow == 3*SOST && a.last_spend_height == 300, "full chain state");
    EXPECT(b.cumulative_outflow == 2*SOST && b.last_spend_height == 100,
           "reorg re-derives lower cumulative + earlier last spend (nothing stale)");
}

int main() {
    std::cout << "=== Gold Vault G3b (rate-limit + cumulative cap) Tests ===" << std::endl;
    for (auto& [name, fn] : tests()) {
        std::cout << "  " << name << " ... ";
        int prev = g_fail; fn();
        if (g_fail == prev) { g_pass++; std::cout << "PASS\n"; } else std::cout << "*** FAIL ***\n";
    }
    std::cout << "\n=== Results: " << g_pass << " passed, " << g_fail
              << " failed out of " << (g_pass + g_fail) << " ===" << std::endl;
    return g_fail > 0 ? 1 : 0;
}
